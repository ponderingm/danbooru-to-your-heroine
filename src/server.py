"""
server.py
=========
danbooru_to_heroine.py（コアエンジン）と comfy_client.py の変換・生成処理を
FastAPI経由で呼び出すAPIサーバー。Tampermonkeyスクリプト等の外部クライアントから、
Danbooru投稿URLを渡すだけでプロンプト変換・画像生成ができるようにする。
同時に、生成履歴を眺めて再生成できるWebビューア（src/web/）も配信する。

起動:
    uv run uvicorn server:app --app-dir src --reload
    # または config.py の API_HOST/API_PORT を使って:
    uv run python src/server.py

エンドポイント:
    GET    /                 - Webビューア（src/web/index.html）
    GET    /heroines          - config.HEROINES の一覧
    POST   /convert           - URL→プロンプト変換のみ（画像生成なし）
    POST   /generate          - 変換 + ComfyUIでの画像生成を優先度付きキューに投入し、job_idを返す
    GET    /jobs/{id}         - /generateジョブの状態（queued/running/done/error）と結果を取得
    GET    /images            - 生成済み画像のmanifest一覧（新しい順、ページネーション・絞り込み対応）
    GET    /tags               - manifest全体のタグ一覧を集計して返す（共通クォリティタグは除く、絞り込みUI用）
    DELETE /images/{id}       - 生成履歴エントリと画像ファイルを削除
    POST   /generated_posts   - post_idの一覧を渡し、既に生成済み（manifestに記録済み）のものだけ返す
    POST   /batch/start       - 検索条件ベースの自動バッチ生成を開始（実行中の設定は1つのみ）
    POST   /batch/stop        - 自動バッチ生成を停止
    GET    /batch/status      - 自動バッチ生成の状態を取得
    GET    /output/{fn}       - 生成画像の静的配信

生成は単一のバックグラウンドワーカースレッドが優先度付きキュー（GENERATION_QUEUE）から
順に取り出して実行する。Webビューア/Tampermonkey経由の手動`/generate`は優先度0（高）、
自動バッチ生成のジョブは優先度10（低）で投入されるため、バッチ生成が裏で動いていても、
手動生成は「今実行中のジョブが終わった直後」に必ず割り込んで先に実行される
（実行中のジョブ自体を中断することはない）。

自動バッチ生成（/batch/start）は`database/generated_manifest.json`に既に記録済みの
post_id（手動生成も含む、どの経路で生成済みでも）を重複としてスキップする。
CLI版`danbooru_search_batch_generator.py`が使う進捗ファイル
（database/danbooru_search_batch_progress.json）とは別管理。

`/generate`はジョブキュー方式。POST直後は{"job_id": ..., "status": "queued"}が
返るだけなので、クライアントはGET /jobs/{job_id}をポーリングしてstatusが
"done"/"error"になるのを待つこと。ジョブ状態・バッチ状態はプロセスメモリ上にのみ
保持され、サーバー再起動で消える（永続化はしない）。
"""

import itertools
import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from danbooru_to_heroine import (
    extract_post_id, fetch_post, mutate_tags_to_heroine, build_prompt,
    build_heroine_negative_prompt, QUALITY_TAGS,
    mutate_raw_prompt_to_heroine, build_hybrid_prompt,
)

from model_adapter import adapt_prompt, get_negative_prompt, RATING_TAG_ALIASES
from comfy_client import (
    COMFYUI_URL, CUSTOM_COMFY_URL, ANIMA_COMFY_URL,
    compute_canvas_size, build_workflow_for_backend, resolve_backend, list_backends,
    submit_and_wait, check_comfy_online,
)
from danbooru_search_batch_generator import (
    parse_search_query, search_posts, matches_local_filters, is_solo_girl, is_realistic_style, is_blacklisted,
    _tokenize_search_query,
)
from notify import notify_failure, notify_success
from site_adapters import UnifiedPost


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "database", "generated_manifest.json")
MANIFEST_LOCK = threading.Lock()

app = FastAPI(title="danbooru-to-your-heroine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(config, "CORS_ORIGINS", []),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

os.makedirs(config.OUTPUT_DIR, exist_ok=True)
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")


class ConvertRequest(BaseModel):
    url: str
    heroine: Optional[str] = None
    model: Optional[str] = None
    include_artist: bool = False
    # keep=元投稿のartistタグ優先(無ければヒロインのartist_tagsへフォールバック) /
    # override=常にヒロインのartist_tagsを使う / none=完全除去。省略時はinclude_artistから決まる
    artist_mode: Optional[str] = None
    # 指定時はartist_modeより常に優先し、この文字列をartistタグとしてそのまま使う（"artist:"省略可）
    custom_artist: Optional[str] = None
    # config.GENERATION_BACKENDSに登録したid（Web UIのプルダウン等で選択）。
    # 指定時はmodel/use_custom/checkpointより優先される
    backend: Optional[str] = None
    # プロンプトソース: "booru" (デフォルト) / "raw" / "hybrid"
    prompt_source: Optional[str] = "booru"



class GenerateRequest(ConvertRequest):
    checkpoint: Optional[str] = None
    width: int = 832
    height: int = 1216
    use_custom: bool = False
    timeout: int = 180
    # 指定時は/convertが自動生成するプロンプトの代わりにこの文字列をそのまま使う
    # （Web UIの「プレビュー→手動編集」フローで使用）
    prompt_override: Optional[str] = None


def _resolve_settings(heroine: str, req: ConvertRequest):
    """ヒロインごとのdefault_model/default_checkpoint/default_negative_extraで
    リクエスト未指定値を補う。リクエストで明示指定された値は常に優先される。"""
    dna = config.HEROINES[heroine]
    backend_model = resolve_backend(req.backend)["model"] if req.backend else None
    model = req.model or backend_model or dna.get("default_model") or "illustrious"
    return dna, model


def _resolve_generation_backend(req: GenerateRequest, dna: dict, model: str) -> dict:
    """generate用の実効バックエンド設定を解決する。req.backend指定時はそれを優先し、
    未指定時は旧model/use_custom/checkpointパラメータから疑似backendを組み立てる（後方互換）"""
    if req.backend:
        backend = resolve_backend(req.backend)
    else:
        if "anima" in model.lower():
            workflow, comfy_url = "anima", ANIMA_COMFY_URL
        elif req.use_custom:
            workflow, comfy_url = "custom", CUSTOM_COMFY_URL
        else:
            workflow, comfy_url = "default", COMFYUI_URL
        backend = {
            "id": None, "label": "", "model": model, "workflow": workflow, "comfy_url": comfy_url,
            "checkpoint": None, "lora_name": None, "steps": None, "cfg": None, "sampler": None, "scheduler": None,
        }
    checkpoint = req.checkpoint or backend["checkpoint"] or dna.get("default_checkpoint") or config.DEFAULT_CHECKPOINT
    return {**backend, "checkpoint": checkpoint}


def _convert(req: ConvertRequest):
    heroine = req.heroine or config.DEFAULT_HEROINE
    if heroine not in config.HEROINES:
        raise HTTPException(status_code=400, detail=f"unknown heroine: {heroine}")
    dna, model = _resolve_settings(heroine, req)

    try:
        post = fetch_post(req.url, login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"API error: {e}")

    identity_tags, situation_tags, _removed = mutate_tags_to_heroine(
        post, heroine=heroine, include_artist=req.include_artist, artist_mode=req.artist_mode,
        custom_artist=req.custom_artist,
    )
    base_prompt = build_prompt(identity_tags, situation_tags)
    booru_prompt = adapt_prompt(base_prompt, model_type=model)

    raw_prompt_heroine = None
    hybrid_prompt = None
    raw_prompt = getattr(post, "raw_prompt", None)
    if raw_prompt:
        extra_ignore = (
            list(getattr(post, "character_tags", []))
            + list(getattr(post, "copyright_tags", []))
            + list(getattr(post, "artist_tags", []))
        )
        raw_mutated = mutate_raw_prompt_to_heroine(raw_prompt, heroine=heroine, extra_ignore_tags=extra_ignore)
        raw_prompt_heroine = adapt_prompt(raw_mutated, model_type=model)
        hybrid_prompt = build_hybrid_prompt(booru_prompt, raw_prompt_heroine)


    psource = getattr(req, "prompt_source", "booru") or "booru"
    if psource == "raw" and raw_prompt_heroine:
        selected_prompt = raw_prompt_heroine
    elif psource == "hybrid" and hybrid_prompt:
        selected_prompt = hybrid_prompt
    else:
        selected_prompt = booru_prompt

    detected_model = (post.generation_meta or {}).get("detected_model", "") if isinstance(post, UnifiedPost) else ""

    extras = {
        "booru_prompt": booru_prompt,
        "raw_prompt_heroine": raw_prompt_heroine,
        "hybrid_prompt": hybrid_prompt,
        "has_raw_prompt": bool(raw_prompt),
        "detected_model": detected_model,
        "removed_tags": _removed,
    }
    return post, heroine, selected_prompt, model, extras



def _load_manifest() -> list:
    """manifestを読み込み、idの無い旧形式エントリには一意なidを補って保存する"""
    if not os.path.exists(MANIFEST_PATH):
        return []
    with MANIFEST_LOCK:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        changed = False
        for entry in manifest:
            if "id" not in entry:
                entry["id"] = str(uuid.uuid4())
                changed = True
        if changed:
            _save_manifest_unlocked(manifest)
        return manifest


def _save_manifest_unlocked(manifest: list) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _append_manifest(entry: dict) -> None:
    entry.setdefault("id", str(uuid.uuid4()))
    with MANIFEST_LOCK:
        manifest = []
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        manifest.append(entry)
        _save_manifest_unlocked(manifest)



@app.get("/heroines")
def list_heroines():
    return {key: {"name": dna["name"]} for key, dna in config.HEROINES.items()}


@app.post("/convert")
def convert(req: ConvertRequest):
    post, heroine, prompt, model, extras = _convert(req)
    pid = post.post_id if isinstance(post, UnifiedPost) else post.get("id")
    site = post.source_site if isinstance(post, UnifiedPost) else "danbooru"
    return {
        "post_id": pid,
        "source_site": site,
        "original_url": req.url,
        "heroine": heroine,
        "model": model,
        "prompt": prompt,
        **extras,
    }


# ─────────────────────────────────────────────
# /generate ジョブキュー（ComfyUIの生成完了までリクエストをブロックしないよう、
# バックグラウンドスレッドで実行し、クライアントはjob_idで進捗をポーリングする）
# ─────────────────────────────────────────────

JOBS: dict = {}
JOBS_LOCK = threading.Lock()
MAX_KEPT_JOBS = 200  # 完了済みジョブをこの件数を超えて溜め込まない（メモリ上のみ保持のため）


def _prune_jobs_locked() -> None:
    if len(JOBS) <= MAX_KEPT_JOBS:
        return
    finished = sorted(
        (jid for jid, j in JOBS.items() if j["status"] in ("done", "error")),
        key=lambda jid: JOBS[jid]["created_at"],
    )
    for jid in finished[: len(JOBS) - MAX_KEPT_JOBS]:
        JOBS.pop(jid, None)


def _do_generate(req: GenerateRequest) -> dict:
    """実際の変換+ComfyUI生成処理本体（旧/generateの同期実装をジョブから呼び出す形に切り出したもの）"""
    post, heroine, prompt, model, _ = _convert(req)
    if req.prompt_override and req.prompt_override.strip():
        prompt = req.prompt_override.strip()

    dna = config.HEROINES[heroine]

    negative = build_heroine_negative_prompt(heroine, get_negative_prompt(model_type=model))

    backend = _resolve_generation_backend(req, dna, model)
    checkpoint = backend["checkpoint"]
    
    post_id = post.post_id if isinstance(post, UnifiedPost) else post.get("id")
    post_w = post.width if isinstance(post, UnifiedPost) else post.get("image_width")
    post_h = post.height if isinstance(post, UnifiedPost) else post.get("image_height")
    source_site = post.source_site if isinstance(post, UnifiedPost) else "danbooru"

    canvas_size = compute_canvas_size(post_w, post_h)
    gen_width, gen_height = canvas_size if canvas_size else (req.width, req.height)
    prefix = f"API_{source_site}_{post_id}_{int(time.time())}"

    wf = build_workflow_for_backend(
        backend, prompt_text=prompt, negative_text=negative, filename_prefix=prefix,
        width=gen_width, height=gen_height,
    )
    base_url = backend["comfy_url"]

    try:
        saved_files, duration = submit_and_wait(wf, timeout=req.timeout, base_url=base_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ComfyUI ({base_url}) に接続できなかった: {e}")

    if not saved_files:
        raise HTTPException(status_code=504, detail="ComfyUIの生成がタイムアウトした")

    entry = {
        "post_id": post_id,
        "source_site": source_site,
        "original_url": req.url,
        "heroine": heroine,
        "prompt": prompt,
        "model": model,
        "backend": backend["id"],
        "include_artist": req.include_artist,
        "artist_mode": req.artist_mode,
        "custom_artist": req.custom_artist,
        "checkpoint": checkpoint,
        "width": gen_width,
        "height": gen_height,
        "files": saved_files,
        "image_urls": [f"/output/{fn}" for fn in saved_files],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_manifest(entry)

    # Discord 成功通知（画像添付つき）
    first_image_path = os.path.join(config.OUTPUT_DIR, saved_files[0]) if saved_files else None
    notify_success(
        heroine=heroine,
        prompt=prompt,
        image_path=first_image_path,
        source_url=req.url,
        duration_sec=duration,
    )

    return {**entry, "duration_sec": round(duration, 1)}



def _run_generate_job(job_id: str, req: GenerateRequest) -> None:
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"
    try:
        result = _do_generate(req)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["result"] = result
    except HTTPException as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = e.detail
        notify_failure(f"/generate 失敗 (job {job_id})", str(e.detail))
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)
        notify_failure(f"/generate 失敗 (job {job_id})", str(e))


# 生成は単一ワーカースレッドが優先度付きキューから順に処理する。
# 手動生成(MANUAL_PRIORITY)は自動バッチ生成(BATCH_PRIORITY)より必ず先に取り出される
# （数値が小さいほど優先。実行中のジョブ自体は中断されない）。
GENERATION_QUEUE: "queue.PriorityQueue" = queue.PriorityQueue()
_QUEUE_SEQ = itertools.count()
MANUAL_PRIORITY = 0
BATCH_PRIORITY = 10


def _enqueue_generate_job(req: GenerateRequest, priority: int) -> str:
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        _prune_jobs_locked()
        JOBS[job_id] = {
            "status": "queued", "result": None, "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    GENERATION_QUEUE.put((priority, next(_QUEUE_SEQ), job_id, req))
    return job_id


def _generation_worker_loop() -> None:
    while True:
        _priority, _seq, job_id, req = GENERATION_QUEUE.get()
        try:
            _run_generate_job(job_id, req)
        finally:
            GENERATION_QUEUE.task_done()


threading.Thread(target=_generation_worker_loop, daemon=True).start()


@app.post("/generate")
def generate(req: GenerateRequest):
    job_id = _enqueue_generate_job(req, MANUAL_PRIORITY)
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"job_id": job_id, **job}


@app.get("/images")
def list_images(limit: int = 50, offset: int = 0, heroine: Optional[str] = None,
                 model: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                 tag: list[str] = Query(default=[])):
    manifest = _load_manifest()
    entries = list(reversed(manifest))

    if heroine:
        entries = [e for e in entries if e.get("heroine") == heroine]
    if model:
        entries = [e for e in entries if e.get("model") == model]
    if date_from:
        entries = [e for e in entries if e.get("created_at", "") >= date_from]
    if date_to:
        entries = [e for e in entries if e.get("created_at", "") <= f"{date_to}T23:59:59.999999+00:00"]
    if tag:
        # クエリ側のタグにもrating語のエイリアスを適用し、anima由来の生タグ(explicit等)で
        # 絞り込んでもIllustrious側のrating:explicit等と同じ扱いになるようにする
        tag_norms = {RATING_TAG_ALIASES.get(t, t) for t in (t.strip().lower() for t in tag if t.strip())}
        entries = [e for e in entries if tag_norms <= _entry_tags(e)]

    total = len(entries)
    page = entries[offset:offset + limit]
    # 旧形式（image_urls未保存）のエントリにも後方互換でimage_urlsを補う
    for entry in page:
        entry.setdefault("image_urls", [f"/output/{fn}" for fn in entry.get("files", [])])
    return {"total": total, "offset": offset, "limit": limit, "entries": page}


@app.delete("/images/{entry_id}")
def delete_image(entry_id: str, delete_files: bool = True):
    with MANIFEST_LOCK:
        manifest = []
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        idx = next((i for i, e in enumerate(manifest) if e.get("id") == entry_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"entry not found: {entry_id}")
        entry = manifest.pop(idx)
        _save_manifest_unlocked(manifest)

    if delete_files:
        for fn in entry.get("files", []):
            safe_fn = os.path.basename(fn)  # パストラバーサル対策
            for directory in (config.OUTPUT_DIR, config.WEB_OUTPUT_DIR):
                path = os.path.join(directory, safe_fn)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    return {"deleted": entry_id}


def _manifest_post_ids() -> set:
    return {e["post_id"] for e in _load_manifest() if e.get("post_id") is not None}


def _entry_tags(entry: dict) -> set:
    """エントリのpromptをカンマ区切りタグ集合に分解する（絞り込み・タグ集計用）
    Anima記法のrating語(safe/nsfw等)はIllustrious記法(rating:xxx)にエイリアスし、
    モデルが違っても同じrating概念を1つのタグとして絞り込めるようにする"""
    tags = {t.strip().lower() for t in entry.get("prompt", "").split(",") if t.strip()}
    return {RATING_TAG_ALIASES.get(t, t) for t in tags}


@app.get("/tags")
def list_tags():
    """manifest全体のpromptからタグ一覧を集計する（QUALITY_TAGSは除く、Webビューアの絞り込みUI用）"""
    quality_lower = {t.lower() for t in QUALITY_TAGS}
    counts: dict = {}
    for entry in _load_manifest():
        for tag in _entry_tags(entry):
            if tag in quality_lower:
                continue
            counts[tag] = counts.get(tag, 0) + 1
    tags = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"tags": [{"tag": t, "count": c} for t, c in tags]}


class PostIdsRequest(BaseModel):
    post_ids: list[int]


@app.post("/generated_posts")
def generated_posts(req: PostIdsRequest):
    """post_idの一覧を受け取り、既にmanifestに生成済み記録があるものだけ返す
    （Tampermonkeyの「生成済み」バッジ表示・自動バッチ生成の重複回避チェックに使う）"""
    known_ids = _manifest_post_ids()
    generated = [pid for pid in req.post_ids if pid in known_ids]
    return {"generated": generated}


# ─────────────────────────────────────────────
# 自動バッチ生成（検索条件を1つ設定して裏で回し続ける。手動/generateより優先度は低い）
# ─────────────────────────────────────────────

class BatchConfig(BaseModel):
    search: str
    heroine: Optional[str] = None
    model: Optional[str] = None
    artist_mode: Optional[str] = None
    custom_artist: Optional[str] = None
    use_custom: bool = False
    checkpoint: Optional[str] = None
    backend: Optional[str] = None
    width: int = 832
    height: int = 1216
    timeout: int = 180
    solo_girl_only: bool = True
    skip_realistic: bool = True
    skip_blacklisted: bool = True
    interval_sec: float = 1.0
    page_size: int = 20
    sort: Optional[str] = None  # searchにorder:が無い場合に自動付与する並び順（例: score, favcount, rank）
    lucky: bool = False  # I'm Feeling Luckyモード（random:Nで無作為抽出を無限ループ、CLIの--luckyと同等）


BATCH_LOCK = threading.Lock()
BATCH_STATE = {
    "config": None,
    "running": False,
    "stop_requested": False,
    "current_post_id": None,
    "total_checked": 0,
    "total_generated": 0,
    "last_error": None,
    "started_at": None,
}
# 検索条件に合致する投稿を使い切った後、再度ページ1から新着をチェックするまでの待機秒数
BATCH_EXHAUSTED_SLEEP_SEC = 60


def _batch_status_snapshot() -> dict:
    with BATCH_LOCK:
        return dict(BATCH_STATE)


def _batch_worker_loop(cfg: BatchConfig) -> None:
    search = cfg.search
    if cfg.sort and "order:" not in search:
        search = f"order:{cfg.sort} {search}".strip()

    if cfg.lucky:
        # order:randomは母集団全体をソートしタイムアウトしやすいため使わず、random:Nで無作為抽出する
        # （CLIの--luckyと同じ方式）。主キーワード1個+random:Nのみ送信し、残りは手元で判定する。
        _order_tag, keyword_tags, ratings, excluded_tags = _tokenize_search_query(search)
        local_filters = {
            "required_tags": set(keyword_tags[1:]),
            "excluded_tags": excluded_tags,
            "ratings": ratings,
        }
        lucky_tags = f"{keyword_tags[0] if keyword_tags else ''} random:{cfg.page_size}".strip()
    else:
        api_query, local_filters = parse_search_query(search)

    generated_ids = _manifest_post_ids()
    page = 0
    consecutive_failures = 0
    max_consecutive_failures = getattr(config, "MAX_CONSECUTIVE_FAILURES", 3)
    while True:
        with BATCH_LOCK:
            if BATCH_STATE["stop_requested"]:
                break
        try:
            if cfg.lucky:
                posts = search_posts(lucky_tags, limit=cfg.page_size, page=1,
                                      login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
            else:
                page += 1
                posts = search_posts(api_query, limit=cfg.page_size, page=page,
                                      login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
        except Exception as e:
            with BATCH_LOCK:
                BATCH_STATE["last_error"] = f"検索エラー: {e}"
            time.sleep(10)
            continue

        if not posts:
            if cfg.lucky:
                # ランダム抽出が0件だった（母集団が少ない等）。少し待ってもう一度引き直す
                time.sleep(BATCH_EXHAUSTED_SLEEP_SEC)
            else:
                # 検索条件に合致する投稿を使い切った。新着投稿を待ってページ1からやり直す
                page = 0
                time.sleep(BATCH_EXHAUSTED_SLEEP_SEC)
            continue

        new_in_round = 0
        for post in posts:
            with BATCH_LOCK:
                if BATCH_STATE["stop_requested"]:
                    break
            post_id = post.get("id")
            with BATCH_LOCK:
                BATCH_STATE["current_post_id"] = post_id
                BATCH_STATE["total_checked"] += 1

            if post_id in generated_ids:
                continue
            new_in_round += 1
            if local_filters and not matches_local_filters(post, local_filters):
                continue
            if cfg.solo_girl_only and not is_solo_girl(post):
                continue
            if cfg.skip_realistic and is_realistic_style(post):
                continue
            if cfg.skip_blacklisted and is_blacklisted(post):
                continue

            req = GenerateRequest(
                url=f"https://danbooru.donmai.us/posts/{post_id}",
                heroine=cfg.heroine, model=cfg.model, artist_mode=cfg.artist_mode,
                custom_artist=cfg.custom_artist,
                use_custom=cfg.use_custom, checkpoint=cfg.checkpoint, backend=cfg.backend,
                width=cfg.width, height=cfg.height, timeout=cfg.timeout,
            )
            job_id = _enqueue_generate_job(req, BATCH_PRIORITY)

            # このジョブが完了するまで待ってから次の投稿へ（手動生成は優先度でこのジョブより先に処理される）
            while True:
                time.sleep(0.5)
                with JOBS_LOCK:
                    status = JOBS[job_id]["status"]
                    error = JOBS[job_id].get("error")
                if status in ("done", "error"):
                    break

            generated_ids.add(post_id)
            with BATCH_LOCK:
                if status == "done":
                    BATCH_STATE["total_generated"] += 1
                    consecutive_failures = 0
                else:
                    BATCH_STATE["last_error"] = error
                    consecutive_failures += 1

            if consecutive_failures >= max_consecutive_failures:
                notify_failure(
                    "自動バッチ生成を停止",
                    f"{consecutive_failures}回連続で生成に失敗したため停止した"
                    f"（ComfyUIがダウンしている可能性）。最後のエラー: {error}",
                )
                with BATCH_LOCK:
                    BATCH_STATE["stop_requested"] = True
                break

            time.sleep(cfg.interval_sec)

        if cfg.lucky and new_in_round == 0:
            # 今回のラウンドは全件生成済みだった（母集団が少ない等）。少し待ってから引き直す
            time.sleep(cfg.interval_sec)

    with BATCH_LOCK:
        BATCH_STATE["running"] = False
        BATCH_STATE["current_post_id"] = None


@app.post("/batch/start")
def batch_start(cfg: BatchConfig):
    heroine = cfg.heroine or config.DEFAULT_HEROINE
    if heroine not in config.HEROINES:
        raise HTTPException(status_code=400, detail=f"unknown heroine: {heroine}")
    with BATCH_LOCK:
        if BATCH_STATE["running"]:
            raise HTTPException(status_code=409, detail="batch is already running; call /batch/stop first")
        BATCH_STATE.update({
            "config": cfg.model_dump(),
            "running": True,
            "stop_requested": False,
            "current_post_id": None,
            "total_checked": 0,
            "total_generated": 0,
            "last_error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
    threading.Thread(target=_batch_worker_loop, args=(cfg,), daemon=True).start()
    return _batch_status_snapshot()


@app.post("/batch/stop")
def batch_stop():
    with BATCH_LOCK:
        if not BATCH_STATE["running"]:
            raise HTTPException(status_code=409, detail="batch is not running")
        BATCH_STATE["stop_requested"] = True
    return _batch_status_snapshot()


@app.get("/batch/status")
def batch_status():
    return _batch_status_snapshot()


@app.get("/backends")
def get_backends():
    """config.GENERATION_BACKENDSの一覧（Web UIのプルダウン用）"""
    return {"backends": list_backends(), "default": getattr(config, "DEFAULT_BACKEND", None)}


@app.get("/comfy/status")
def comfy_status():
    """config.GENERATION_BACKENDSの各バックエンドについてComfyUI生存確認（ギャラリーのステータス表示用）"""
    backends = getattr(config, "GENERATION_BACKENDS", {})
    return {
        bid: ("online" if check_comfy_online(b.get("comfy_url", COMFYUI_URL)) else "offline")
        for bid, b in backends.items()
    }


class PurgeTagsRequest(BaseModel):
    purge_tags: list[str]
    unpurge_tags: Optional[list[str]] = None


@app.get("/purge_tags")
def get_purge_tags():
    """Base層・User層・マージ後の全パージタグ一覧を取得"""
    base_meta = getattr(config, "BASE_RULES", {}).get("meta_purge", [])
    base_artifact = getattr(config, "BASE_RULES", {}).get("artifact_purge", [])
    user_purge = getattr(config, "USER_CONFIG", {}).get("purge_tags", [])
    user_unpurge = getattr(config, "USER_CONFIG", {}).get("unpurge_tags", [])
    return {
        "effective_purge_tags": sorted(list(getattr(config, "EXTRA_PURGE_TAGS", []))),
        "user_purge_tags": sorted(user_purge),
        "user_unpurge_tags": sorted(user_unpurge),
        "base_meta_tags": sorted(base_meta),
        "base_artifact_tags": sorted(base_artifact),
    }


@app.post("/purge_tags")
def update_purge_tags(req: PurgeTagsRequest):
    """WebUIからUser層のパージタグを更新し、即座にconfig.yamlへ保存＆ホットリロード"""
    config.save_user_purge_tags(req.purge_tags, req.unpurge_tags)
    return {
        "status": "ok",
        "user_purge_tags": sorted(getattr(config, "USER_CONFIG", {}).get("purge_tags", [])),
        "user_unpurge_tags": sorted(getattr(config, "USER_CONFIG", {}).get("unpurge_tags", [])),
        "total_effective": len(getattr(config, "EXTRA_PURGE_TAGS", [])),
    }



class RestorePurgeTagsRequest(BaseModel):
    filename: str


@app.get("/purge_tags/backups")
def get_purge_tag_backups():
    """利用可能なパージタグのバックアップ一覧を取得"""
    return {"backups": config.list_backups()}


@app.post("/purge_tags/restore")
def restore_purge_tags(req: RestorePurgeTagsRequest):
    """指定されたバックアップからパージタグを復元"""
    try:
        res = config.restore_backup(req.filename)
        return {"status": "ok", **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/config/reload")
def trigger_reload_config():
    """YAML設定とBaseルールを手動でホットリロード"""
    config.reload_config()
    return {"status": "ok", "message": "config reloaded successfully"}


class NotificationConfigRequest(BaseModel):
    webhook_url: str
    notify_level: str
    include_image: bool


@app.get("/config/notification")
def get_notification_config():
    """現在のDiscord通知設定を取得"""
    discord_cfg = getattr(config, "USER_CONFIG", {}).get("discord", {})
    return {
        "webhook_url": discord_cfg.get("webhook_url", ""),
        "notify_level": discord_cfg.get("notify_level", "success"),
        "include_image": discord_cfg.get("include_image", True),
    }


@app.post("/config/notification")
def update_notification_config(req: NotificationConfigRequest):
    """Discord通知設定を保存してホットリロード"""
    config.save_notification_config(req.webhook_url, req.notify_level, req.include_image)
    return {"status": "ok"}


@app.post("/notify/test")
def test_discord_notification():
    """現在の設定でDiscordへテスト通知を送信"""
    from notify import send_test_notification
    ok = send_test_notification()
    if not ok:
        raise HTTPException(status_code=400, detail="Discordへの送信に失敗しました。Webhook URLが正しいか確認してください。")
    return {"status": "ok", "message": "テスト通知を送信しました"}


WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")



if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=getattr(config, "API_HOST", "127.0.0.1"), port=getattr(config, "API_PORT", 8000))

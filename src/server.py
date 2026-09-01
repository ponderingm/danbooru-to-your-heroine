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
from danbooru_to_heroine import extract_post_id, fetch_post, mutate_tags_to_heroine, build_prompt, QUALITY_TAGS
from model_adapter import adapt_prompt, get_negative_prompt, RATING_TAG_ALIASES
from comfy_client import (
    COMFYUI_URL, CUSTOM_COMFY_URL, ANIMA_COMFY_URL,
    compute_canvas_size, create_default_workflow, create_custom_workflow, create_anima_workflow,
    submit_and_wait,
)
from danbooru_search_batch_generator import (
    parse_search_query, search_posts, matches_local_filters, is_solo_girl, is_realistic_style, is_blacklisted,
)

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
    nsfw: bool = True
    include_artist: bool = False
    # keep=元投稿のartistタグ優先(無ければヒロインのartist_tagsへフォールバック) /
    # override=常にヒロインのartist_tagsを使う / none=完全除去。省略時はinclude_artistから決まる
    artist_mode: Optional[str] = None


class GenerateRequest(ConvertRequest):
    checkpoint: Optional[str] = None
    width: int = 832
    height: int = 1216
    use_custom: bool = False
    timeout: int = 180


def _resolve_settings(heroine: str, req: ConvertRequest):
    """ヒロインごとのdefault_model/default_checkpoint/default_negative_extraで
    リクエスト未指定値を補う。リクエストで明示指定された値は常に優先される。"""
    dna = config.HEROINES[heroine]
    model = req.model or dna.get("default_model") or "illustrious"
    return dna, model


def _convert(req: ConvertRequest):
    heroine = req.heroine or config.DEFAULT_HEROINE
    if heroine not in config.HEROINES:
        raise HTTPException(status_code=400, detail=f"unknown heroine: {heroine}")
    dna, model = _resolve_settings(heroine, req)

    try:
        post_id = extract_post_id(req.url)
        post = fetch_post(post_id, login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Danbooru API error: {e}")

    identity_tags, situation_tags, _removed = mutate_tags_to_heroine(
        post, heroine=heroine, nsfw=req.nsfw, include_artist=req.include_artist, artist_mode=req.artist_mode,
    )
    base_prompt = build_prompt(identity_tags, situation_tags)
    prompt = adapt_prompt(base_prompt, model_type=model, is_h_scene=req.nsfw)
    return post, heroine, prompt, model


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
    post, heroine, prompt, model = _convert(req)
    return {"post_id": post.get("id"), "original_url": req.url, "heroine": heroine, "model": model, "prompt": prompt}


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
    post, heroine, prompt, model = _convert(req)
    dna = config.HEROINES[heroine]

    negative = get_negative_prompt(model_type=model)
    extra_negative = dna.get("default_negative_extra")
    if extra_negative:
        negative = f"{negative}, {extra_negative}"
    checkpoint = req.checkpoint or dna.get("default_checkpoint") or config.DEFAULT_CHECKPOINT
    canvas_size = compute_canvas_size(post.get("image_width"), post.get("image_height"))
    gen_width, gen_height = canvas_size if canvas_size else (req.width, req.height)
    prefix = f"API_{post.get('id')}_{int(time.time())}"

    if "anima" in model.lower():
        # Anima v1.0 DiTはSDXL checkpointを使わないため、use_custom/checkpointの指定は無視する
        wf = create_anima_workflow(
            prompt_text=prompt, negative_text=negative, filename_prefix=prefix,
            width=gen_width, height=gen_height,
        )
        base_url = ANIMA_COMFY_URL
    elif req.use_custom:
        wf = create_custom_workflow(
            prompt_text=prompt, negative_text=negative, filename_prefix=prefix,
            checkpoint=checkpoint, width=gen_width, height=gen_height,
        )
        base_url = CUSTOM_COMFY_URL
    else:
        wf = create_default_workflow(
            prompt_text=prompt, negative_text=negative, filename_prefix=prefix,
            checkpoint=checkpoint, width=gen_width, height=gen_height,
        )
        base_url = COMFYUI_URL

    try:
        saved_files, duration = submit_and_wait(wf, timeout=req.timeout, base_url=base_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ComfyUI ({base_url}) に接続できなかった: {e}")

    if not saved_files:
        raise HTTPException(status_code=504, detail="ComfyUIの生成がタイムアウトした")

    entry = {
        "post_id": post.get("id"),
        "original_url": req.url,
        "heroine": heroine,
        "prompt": prompt,
        "model": model,
        "nsfw": req.nsfw,
        "include_artist": req.include_artist,
        "artist_mode": req.artist_mode,
        "use_custom": req.use_custom,
        "checkpoint": checkpoint,
        "width": gen_width,
        "height": gen_height,
        "files": saved_files,
        "image_urls": [f"/output/{fn}" for fn in saved_files],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_manifest(entry)

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
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)


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
    nsfw: bool = True
    use_custom: bool = False
    checkpoint: Optional[str] = None
    width: int = 832
    height: int = 1216
    timeout: int = 180
    solo_girl_only: bool = True
    skip_realistic: bool = True
    skip_blacklisted: bool = True
    interval_sec: float = 1.0
    page_size: int = 20


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
    api_query, local_filters = parse_search_query(cfg.search)
    generated_ids = _manifest_post_ids()
    page = 0
    while True:
        with BATCH_LOCK:
            if BATCH_STATE["stop_requested"]:
                break
        page += 1
        try:
            posts = search_posts(api_query, limit=cfg.page_size, page=page,
                                  login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
        except Exception as e:
            with BATCH_LOCK:
                BATCH_STATE["last_error"] = f"検索エラー: {e}"
            time.sleep(10)
            continue

        if not posts:
            # 検索条件に合致する投稿を使い切った。新着投稿を待ってページ1からやり直す
            page = 0
            time.sleep(BATCH_EXHAUSTED_SLEEP_SEC)
            continue

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
                nsfw=cfg.nsfw, use_custom=cfg.use_custom, checkpoint=cfg.checkpoint,
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
                else:
                    BATCH_STATE["last_error"] = error

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


WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=getattr(config, "API_HOST", "127.0.0.1"), port=getattr(config, "API_PORT", 8000))

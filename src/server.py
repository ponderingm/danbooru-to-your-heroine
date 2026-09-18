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
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict, Tuple

import urllib.parse
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from danbooru_to_heroine import (
    extract_post_id, fetch_post, mutate_tags_to_heroine, build_prompt,
    build_heroine_negative_prompt, QUALITY_TAGS,
    mutate_raw_prompt_to_heroine, build_hybrid_prompt,
)

from model_adapter import adapt_prompt, get_negative_prompt, RATING_TAG_ALIASES
from tag_classifier import classifier
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
APP_VERSION = "v3.0.0"
REPO_URL = "https://github.com/ponderingm/danbooru-to-your-heroine"
GIT_TIMEOUT_SEC = 2

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
    # 生成時の一時オーバーライドルール微調整 ("default" / "strict" / "source", 衣装は "heroine" / "mix" も可)
    override_breasts: Optional[str] = None
    override_skin: Optional[str] = None
    override_costume: Optional[str] = None
    override_art_style: Optional[str] = None
    # 複数人構図戦略: "capsule" (デフォルト/C) / "flat" (A: v2ライク) / "shared_costume" (B: 衣装共有)
    multi_mode: Optional[str] = "capsule"
    search_query: Optional[str] = None



class GenerateRequest(ConvertRequest):
    checkpoint: Optional[str] = None
    width: int = 832
    height: int = 1216
    use_custom: bool = False
    timeout: int = 180
    # 指定時は/convertが自動生成するプロンプトの代わりにこの文字列をそのまま使う
    # （Web UIの「プレビュー→手動編集」フローで使用）
    prompt_override: Optional[str] = None
    is_batch: bool = False  # 自動バッチ生成によるジョブかどうか（Discord通知の@silent制御等に利用）
    filename_prefix: Optional[str] = None  # 保存ファイル名のプレフィックス（指定時はこれを使用）
    filename: Optional[str] = None  # 保存ファイル名そのものを指定（拡張子付きまたはベース名）


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
        backend = resolve_backend(req.backend, fallback_online=True)
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

    adhoc_rules = {}
    if getattr(req, "override_breasts", None) and req.override_breasts != "default":
        adhoc_rules["breasts"] = req.override_breasts
    if getattr(req, "override_skin", None) and req.override_skin != "default":
        adhoc_rules["skin"] = req.override_skin
    if getattr(req, "override_costume", None) and req.override_costume != "default":
        adhoc_rules["costume"] = req.override_costume
    if getattr(req, "override_art_style", None) and req.override_art_style != "default":
        adhoc_rules["art_style"] = req.override_art_style

    res = mutate_tags_to_heroine(
        post, heroine=heroine, include_artist=req.include_artist, artist_mode=req.artist_mode,
        custom_artist=req.custom_artist, override_rules=adhoc_rules,
    )
    identity_tags, situation_tags, _removed = res[0], res[1], res[2]
    extra_neg = getattr(res, "extra_negative_tags", [])
    multi_mode = getattr(req, "multi_mode", "capsule") or "capsule"
    base_prompt = build_prompt(identity_tags, situation_tags, model_type=model, heroine_name=heroine, multi_mode=multi_mode)
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
    slots_map = classifier.classify_tags(identity_tags + situation_tags, fallback_llm=False)

    extras = {
        "booru_prompt": booru_prompt,
        "raw_prompt_heroine": raw_prompt_heroine,
        "hybrid_prompt": hybrid_prompt,
        "has_raw_prompt": bool(raw_prompt),
        "detected_model": detected_model,
        "identity_tags": identity_tags,
        "situation_tags": situation_tags,
        "removed_tags": _removed,
        "slots": slots_map,
        "multi_mode": multi_mode,
        "extra_negative_tags": extra_neg,
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


@app.get("/heroines/details")
def get_heroines_details():
    """全ヒロインの詳細定義を返す"""
    return {"heroines": getattr(config, "HEROINES", {})}


class AnalyzeHeroineRequest(BaseModel):
    character_name: str
    search_mode: Optional[str] = "auto"
    site: Optional[str] = "danbooru"


@app.post("/heroines/analyze")
def analyze_heroine_tags(req: AnalyzeHeroineRequest):
    """Booruからキャラクターのタグ頻度を分析してヒロイン設定を提案"""
    from heroine_helper import search_and_analyze_heroine
    try:
        res = search_and_analyze_heroine(
            character_name=req.character_name,
            search_mode=req.search_mode or "auto",
            site=req.site or "danbooru",
        )
        return {"status": "ok", **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class NaturalSearchRequest(BaseModel):
    query: str
    provider: Optional[str] = "auto"
    find_core: Optional[bool] = False


@app.post("/search/natural")
def natural_search_tags(req: NaturalSearchRequest):
    """自然言語からBooruタグを変換し、Gelbooru積集合から共起の輪の中心核（起爆剤タグ）を探索"""
    from natural_to_danbooru import resolve_tags
    try:
        res = resolve_tags(
            text=req.query,
            provider=req.provider or "auto",
            find_core=bool(req.find_core),
        )
        return {"status": "ok", **res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



class SaveHeroineRequest(BaseModel):
    key: str
    data: dict


@app.post("/heroines/save")
def save_heroine_config(req: SaveHeroineRequest):
    """ヒロイン設定を新規作成または更新して保存"""
    k = req.key.strip().replace(" ", "_").lower()
    if not k:
        raise HTTPException(status_code=400, detail="ヒロインID（英数キー）を指定してください")
    config.save_heroine(k, req.data)
    return {"status": "ok", "key": k}


@app.delete("/heroines/{key}")
def delete_heroine_config(key: str):
    """指定ヒロインを削除"""
    ok = config.delete_heroine(key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"ヒロイン '{key}' が見つかりませんでした")
    return {"status": "ok"}



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
    post, heroine, prompt, model, extras = _convert(req)
    if req.prompt_override and req.prompt_override.strip():
        prompt = req.prompt_override.strip()

    prompt_lower = prompt.lower()
    allow_comic = any(t in prompt_lower for t in ["comic", "monochrome", "greyscale", "grayscale", "manga"])
    base_neg = get_negative_prompt(model_type=model, allow_comic=allow_comic)
    extra_neg = extras.get("extra_negative_tags", []) if isinstance(extras, dict) else []
    negative = build_heroine_negative_prompt(heroine, base_neg, extra_tags=extra_neg)

    dna = config.HEROINES.get(heroine, {})
    backend = _resolve_generation_backend(req, dna, model)
    checkpoint = backend["checkpoint"]
    
    post_id = post.post_id if isinstance(post, UnifiedPost) else post.get("id")
    post_w = post.width if isinstance(post, UnifiedPost) else post.get("image_width")
    post_h = post.height if isinstance(post, UnifiedPost) else post.get("image_height")
    source_site = post.source_site if isinstance(post, UnifiedPost) else "danbooru"

    canvas_size = compute_canvas_size(post_w, post_h)
    gen_width, gen_height = canvas_size if canvas_size else (req.width, req.height)
    
    target_exact_filename = None
    if getattr(req, "filename", None) and req.filename.strip():
        target_exact_filename = os.path.basename(req.filename.strip())
        prefix = os.path.splitext(target_exact_filename)[0]
    elif req.filename_prefix and req.filename_prefix.strip():
        prefix = req.filename_prefix.strip()
    else:
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

    # Core APIで明示的に filename が指定された場合、ComfyUI出力ファイルをCore側で直接その名前に確定保存する
    if target_exact_filename and saved_files:
        if not os.path.splitext(target_exact_filename)[1]:
            orig_ext = os.path.splitext(saved_files[0])[1] or ".png"
            target_exact_filename = f"{target_exact_filename}{orig_ext}"
        
        orig_fn = saved_files[0]
        if orig_fn != target_exact_filename:
            for directory in (config.OUTPUT_DIR, config.WEB_OUTPUT_DIR):
                src_p = os.path.join(directory, orig_fn)
                dst_p = os.path.join(directory, target_exact_filename)
                if os.path.exists(src_p):
                    if os.path.exists(dst_p) and os.path.abspath(src_p) != os.path.abspath(dst_p):
                        try:
                            os.remove(dst_p)
                        except OSError:
                            pass
                    os.rename(src_p, dst_p)
            saved_files[0] = target_exact_filename

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
        "search_query": req.search_query,
        "override_breasts": req.override_breasts,
        "override_skin": req.override_skin,
        "override_costume": req.override_costume,
        "override_art_style": req.override_art_style,
        "multi_mode": getattr(req, "multi_mode", "capsule"),
        "identity_tags": extras.get("identity_tags", []),
        "situation_tags": extras.get("situation_tags", []),
        "removed_tags": extras.get("removed_tags", []),
        "slots": extras.get("slots", {}),
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
        silent=bool(getattr(req, "is_batch", False)),
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


def _manifest_seen_keys() -> set:
    """各サイトごとのpost_idまたはURLから、すでに生成済みのキー集合を返す"""
    keys = set()
    for e in _load_manifest():
        pid = e.get("post_id")
        site = e.get("source_site", "danbooru")
        if pid is not None:
            keys.add(f"{site}:{pid}")
            keys.add(str(pid))
        if e.get("original_url"):
            keys.add(e["original_url"])
    return keys


def _batch_fetch_posts(provider: str, query: str, page: int, limit: int, lucky: bool = False) -> list:
    """指定プロバイダ（danbooru / gelbooru / aibooru）から投稿一覧を取得する"""
    provider = (provider or "danbooru").lower()

    if provider == "danbooru":
        return search_posts(query, limit=limit, page=page,
                            login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)

    elif provider == "aibooru":
        headers = {"User-Agent": "danbooru-to-your-heroine/2.0"}
        params = {"tags": query, "limit": limit, "page": page}
        resp = requests.get("https://aibooru.online/posts.json", params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            posts = resp.json()
            return posts if isinstance(posts, list) else []
        elif resp.status_code == 404:
            return []
        resp.raise_for_status()

    elif provider == "gelbooru":
        user_id = getattr(config, "GELBOORU_USER_ID", None)
        api_key = getattr(config, "GELBOORU_API_KEY", None)
        if not user_id or not api_key:
            raise ValueError("GelbooruのAPIキーが未設定です。設定タブの「サイト認証」からUser IDとAPI Keyを登録してください")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        pid = max(0, page - 1)
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={urllib.parse.quote(query)}&limit={limit}&pid={pid}&user_id={user_id}&api_key={api_key}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("post") if isinstance(data, dict) else data
            if not posts:
                return []
            posts_list = posts if isinstance(posts, list) else [posts]
            normalized = []
            for p in posts_list:
                tags_str = p.get("tags", "")
                raw_rating = str(p.get("rating", "g")).lower()
                rating_char = raw_rating[0] if raw_rating else "g"
                normalized.append({
                    "id": p.get("id"),
                    "tag_string": tags_str,
                    "tag_string_general": tags_str,
                    "tag_string_character": "",
                    "tag_string_copyright": "",
                    "tag_string_artist": "",
                    "rating": rating_char,
                    "_source_site": "gelbooru",
                })
            return normalized
        elif resp.status_code == 404:
            return []
        resp.raise_for_status()

    else:
        raise ValueError(f"未対応のプロバイダです: {provider}")


def _batch_post_url(provider: str, post_id: Any) -> str:
    provider = (provider or "danbooru").lower()
    if provider == "danbooru":
        return f"https://danbooru.donmai.us/posts/{post_id}"
    elif provider == "aibooru":
        return f"https://aibooru.online/posts/{post_id}"
    elif provider == "gelbooru":
        return f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}"
    return f"https://danbooru.donmai.us/posts/{post_id}"


# --- 高度検索フィルタ定数 ---
COMMON_MEDIA_BLACKLIST = {
    "animated", "video", "sound", "audible_speech", "3d", "flash", "ugoira", "source_filmmaker", "webm", "mp4", "gif"
}
COMMON_QUALITY_BLACKLIST = {
    "comic", "manga", "greyscale", "monochrome", "sketch", "lineart", "bad_anatomy", "chibi", "super_deformed"
}
COMMON_DISTANT_BLACKLIST = {
    "wide_shot", "very_wide_shot", "distant_view", "full_body_from_afar"
}
GIRL_TAGS = {
    "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls", "multiple_girls", "girls", "female", "girl"
}


class PostSearchRequest(BaseModel):
    tag: Optional[str] = None
    query: Optional[str] = None
    rating: Optional[str] = "general"
    rejected_ids: Optional[List[int]] = None
    provider: Optional[str] = "danbooru"
    limit: Optional[int] = 40
    page: Optional[int] = 1
    solo_girl_only: Optional[bool] = True
    skip_realistic: Optional[bool] = True
    skip_blacklisted: Optional[bool] = True
    select_one: Optional[bool] = True

    # ★ 高度ホワイト/ブラックリスト連携パラメータ
    category: Optional[str] = None
    excluded_tags: Optional[List[str]] = None
    excluded_compositions: Optional[List[str]] = None
    preferred_compositions: Optional[List[str]] = None
    required_subject: Optional[str] = "1girl"
    allow_male_partner: Optional[bool] = False
    allow_nude: Optional[bool] = False
    prefer_isolated: Optional[bool] = True


def _evaluate_candidate_post(post: dict, req: PostSearchRequest, r_code: Optional[str],
                             rejected_ids: set, relax_composition: bool = False) -> Tuple[bool, int, str]:
    """
    イラスト候補を厳格に評価し (合格: bool, Tierスコア: int, 判定理由: str) を返す。
    Tier 1 (400): 孤立ポスト + 推奨ホワイト構図
    Tier 2 (300): 孤立ポスト + 標準構図通過
    Tier 3 (200): 関連ポスト + 推奨ホワイト構図
    Tier 4 (100): 関連ポスト + 標準構図通過
    """
    pid = post.get("id")
    if pid and (pid in rejected_ids or int(pid) in rejected_ids):
        return False, 0, "rejected_id"

    # レーティング厳格一致
    if r_code and (post.get("rating") or "").lower() != r_code:
        return False, 0, "rating_mismatch"

    # 静止画拡張子判定
    ext = (post.get("file_ext") or "").lower().lstrip(".")
    if ext and ext not in {"jpg", "jpeg", "png", "webp"}:
        return False, 0, "invalid_media_ext"

    tags = set((post.get("tag_string") or "").split())

    # 1. 共通メディア・品質ブラックリスト
    if tags & COMMON_MEDIA_BLACKLIST:
        return False, 0, "media_blacklist"
    if tags & COMMON_QUALITY_BLACKLIST:
        return False, 0, "quality_blacklist"

    # 2. 構図・遠景ブラックリスト（緩和フラグがオフの時のみ適用）
    if not relax_composition:
        comp_bl = set(req.excluded_compositions or []) | COMMON_DISTANT_BLACKLIST
        if tags & comp_bl:
            return False, 0, "composition_blacklist"

    # 3. 実写・3D調除外
    if req.skip_realistic and is_realistic_style(post):
        return False, 0, "realistic_style"

    # 4. Core共通ブラックリスト除外
    if req.skip_blacklisted and is_blacklisted(post):
        return False, 0, "core_blacklist"

    # 5. カテゴリ別除外タグ（未着用・全裸・プレイ外混入など）
    if req.excluded_tags:
        if tags & set(req.excluded_tags):
            return False, 0, "category_excluded_tag"

    # 6. 未着用 unworn_* パターン除外（衣装系・ヌード不許可時）
    if not req.allow_nude:
        if any(t.startswith("unworn_") for t in tags):
            return False, 0, "unworn_clothes_pattern"
        if bool({"completely_nude", "nude", "naked_dogeza"} & tags):
            return False, 0, "unwanted_nude"

    # 7. 主体（Subject）＆男性パートナー判定
    has_girl = bool(tags & GIRL_TAGS) or any(t.endswith("girl") or t.endswith("girls") for t in tags)
    is_pure_male_yaoi = not has_girl and bool({"1boy", "2boys", "3boys", "multiple_boys", "yaoi", "male_focus"} & tags)
    if is_pure_male_yaoi or "yaoi" in tags:
        return False, 0, "yaoi_forbidden"

    if not req.allow_male_partner and bool({"1boy", "2boys", "3boys", "multiple_boys", "male_focus"} & tags):
        return False, 0, "male_partner_forbidden"

    req_subject = req.required_subject or ("1girl" if req.solo_girl_only else "girl")
    if req_subject == "1girl":
        if "1girl" not in tags or bool(tags & {"2girls", "3girls", "4girls", "5girls", "6+girls", "multiple_girls"}):
            return False, 0, "subject_missing_1girl"
    else:
        if not has_girl:
            return False, 0, "subject_missing_girl"

    # 8. Tierスコアリング（孤立ポスト優先 ＆ 推奨ホワイト構図）
    is_isolated = (post.get("parent_id") is None and not post.get("has_children")
                   and not post.get("has_active_children") and not post.get("has_visible_children"))

    preferred = set(req.preferred_compositions or [])
    # Tier 1 から multiple_views を全カテゴリ共通で除外（なければTier 2等へフォールバック）
    has_multiple_views = "multiple_views" in tags
    is_preferred = bool(preferred and (tags & preferred)) and not has_multiple_views

    if is_isolated:
        tier_score = 400 if is_preferred else 300
    else:
        tier_score = 200 if is_preferred else 100

    if req.prefer_isolated is False:
        tier_score = 400 if is_preferred else 300

    reason = "valid"
    if has_multiple_views and bool(preferred and (tags & preferred)):
        reason = "valid_multiple_views_fallback"

    return True, tier_score, reason


@app.post("/posts/search")
def search_posts_api(req: PostSearchRequest):
    """
    指定プロバイダ（Danbooru等）から条件に合致する投稿を検索するAPI。
    select_one=True の場合は高度なホワイト/ブラックリスト判定＆Tier選定により、最適な2Dイラスト1件を返却。
    select_one=False の場合は合致する投稿リストを返却。
    """
    provider = (req.provider or "danbooru").lower()
    target_tag = (req.tag or req.query or "").strip()
    rejected_ids = set(req.rejected_ids or [])

    rating_map = {"general": "g", "sensitive": "s", "questionable": "q", "explicit": "e"}
    r_code = None
    if req.rating and req.rating.lower() not in ("all", "any", "none", "*"):
        r_code = rating_map.get(req.rating.lower(), req.rating.lower()[:1])

    # 1. 最適な1件を抽出（オンデマンド生成・再生成用）
    if req.select_one:
        if not target_tag:
            raise HTTPException(status_code=400, detail="tag または query を指定してください")

        if provider == "danbooru":
            has_meta = "order:" in target_tag or "rating:" in target_tag
            if has_meta:
                queries = [target_tag]
            else:
                r_filter = f"rating:{r_code}" if r_code else ""
                queries = [
                    f"order:score {target_tag} {r_filter}".strip(),
                    f"{target_tag} {r_filter}".strip(),
                    f"{target_tag} 1girl".strip(),
                    f"{target_tag}".strip(),
                ]

            for q_str in queries:
                try:
                    posts = _batch_fetch_posts(provider, q_str, page=req.page or 1, limit=req.limit or 40)
                except Exception:
                    continue
                if not posts or not isinstance(posts, list):
                    continue

                # フェーズ1: 構図除外を厳格適用して評価
                candidates = []
                for p in posts:
                    ok, tier, _ = _evaluate_candidate_post(p, req, r_code, rejected_ids, relax_composition=False)
                    if ok:
                        dan_score = min(max(int(p.get("score") or 0), 0), 9999)
                        total_rank = tier * 10000 + dan_score
                        candidates.append((total_rank, tier, p))

                # フェーズ2: 厳格判定で0件だった場合は構図除外を緩和して再評価
                if not candidates:
                    for p in posts:
                        ok, tier, _ = _evaluate_candidate_post(p, req, r_code, rejected_ids, relax_composition=True)
                        if ok:
                            dan_score = min(max(int(p.get("score") or 0), 0), 9999)
                            total_rank = tier * 10000 + dan_score
                            candidates.append((total_rank, tier, p))

                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best_rank, best_tier, best_post = candidates[0]
                    return {
                        "status": "ok",
                        "found": True,
                        "post": best_post,
                        "post_id": best_post.get("id"),
                        "url": _batch_post_url(provider, best_post.get("id")),
                        "rating": best_post.get("rating"),
                        "tier": best_tier,
                        "matched_query": q_str,
                    }

            return {
                "status": "ok",
                "found": False,
                "post": None,
                "post_id": None,
                "url": None,
                "message": f"No suitable post found for tag '{target_tag}' (rating: {req.rating})"
            }

        else:
            try:
                posts = _batch_fetch_posts(provider, target_tag, page=req.page or 1, limit=req.limit or 40)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

            candidates = []
            for p in posts:
                ok, tier, _ = _evaluate_candidate_post(p, req, r_code, rejected_ids, relax_composition=False)
                if ok:
                    dan_score = min(max(int(p.get("score") or 0), 0), 9999)
                    candidates.append((tier * 10000 + dan_score, tier, p))

            if not candidates:
                for p in posts:
                    ok, tier, _ = _evaluate_candidate_post(p, req, r_code, rejected_ids, relax_composition=True)
                    if ok:
                        dan_score = min(max(int(p.get("score") or 0), 0), 9999)
                        candidates.append((tier * 10000 + dan_score, tier, p))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, best_tier, best_post = candidates[0]
                return {
                    "status": "ok",
                    "found": True,
                    "post": best_post,
                    "post_id": best_post.get("id"),
                    "url": _batch_post_url(provider, best_post.get("id")),
                    "rating": best_post.get("rating"),
                    "tier": best_tier,
                }

            return {
                "status": "ok",
                "found": False,
                "post": None,
                "post_id": None,
                "url": None,
                "message": f"No suitable post found for '{target_tag}' on {provider}"
            }

    # 2. リスト検索（select_one = False）
    else:
        try:
            posts = _batch_fetch_posts(provider, target_tag, page=req.page or 1, limit=req.limit or 40)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        matched = []
        for p in posts:
            ok, _, _ = _evaluate_candidate_post(p, req, r_code, rejected_ids, relax_composition=False)
            if ok:
                matched.append(p)

        return {
            "status": "ok",
            "found": len(matched) > 0,
            "count": len(matched),
            "posts": matched,
        }


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


@app.api_route("/data/danbooru_tags.csv", methods=["GET", "HEAD"])
def get_danbooru_tags_csv():
    """Danbooruタグのオートコンプリート用CSVデータを配信する（未取得時は自動ダウンロード）"""
    csv_path = os.path.join(PROJECT_ROOT, "database", "danbooru_tags.csv")
    if not os.path.exists(csv_path):
        import urllib.request
        url = "https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv/resolve/main/danbooru_tags.csv"
        try:
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            urllib.request.urlretrieve(url, csv_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to download tags CSV: {e}")
    return FileResponse(csv_path, media_type="text/csv", headers={"Cache-Control": "public, max-age=86400"})


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
    provider: str = "danbooru"  # "danbooru" | "gelbooru" | "aibooru"
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
    rating: Optional[str] = None  # searchにrating:が無い場合に自動付与するレーティング（例: explicit, questionable, sensitive, general）
    lucky: bool = False  # I'm Feeling Luckyモード（random:Nで無作為抽出を無限ループ、CLIの--luckyと同等）
    override_breasts: Optional[str] = None
    override_skin: Optional[str] = None
    override_costume: Optional[str] = None
    override_art_style: Optional[str] = None
    multi_mode: Optional[str] = "capsule"


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


def _batch_worker_loop(cfg: BatchConfig, run_id: str) -> None:
    provider = getattr(cfg, "provider", "danbooru") or "danbooru"
    search = cfg.search
    if cfg.rating and "rating:" not in search:
        search = f"rating:{cfg.rating} {search}".strip()

    if provider == "gelbooru":
        # Gelbooru用構文: 複数タグ制限がなく、sort:random / sort:score を直接APIに渡せる
        if cfg.sort and "sort:" not in search and "order:" not in search:
            search = f"sort:{cfg.sort} {search}".strip()

        _order_tag, keyword_tags, ratings, excluded_tags = _tokenize_search_query(search)
        gel_query_parts = list(keyword_tags)
        for r in ratings:
            gel_query_parts.append(f"rating:{r}")
        for ex in excluded_tags:
            gel_query_parts.append(f"-{ex}")

        if cfg.lucky:
            if not any(t.startswith("sort:") for t in gel_query_parts):
                gel_query_parts.append("sort:random")

        api_query = " ".join(gel_query_parts).strip()
        lucky_tags = api_query
        local_filters = None
    else:
        # Danbooru / AIBooru用構文
        if cfg.sort and "order:" not in search:
            search = f"order:{cfg.sort} {search}".strip()

        if cfg.lucky:
            # order:randomは母集団全体をソートしタイムアウトしやすいため使わず、random:Nで無作為抽出する
            _order_tag, keyword_tags, ratings, excluded_tags = _tokenize_search_query(search)
            local_filters = {
                "required_tags": set(keyword_tags[1:]),
                "excluded_tags": excluded_tags,
                "ratings": ratings,
            }
            lucky_tags = f"{keyword_tags[0] if keyword_tags else ''} random:{cfg.page_size}".strip()
        else:
            api_query, local_filters = parse_search_query(search)

    seen_keys = _manifest_seen_keys()
    page = 0
    consecutive_failures = 0
    max_consecutive_failures = getattr(config, "MAX_CONSECUTIVE_FAILURES", 3)
    try:
        while True:
            with BATCH_LOCK:
                if BATCH_STATE["stop_requested"] or BATCH_STATE.get("run_id") != run_id:
                    break
            try:
                if cfg.lucky:
                    posts = _batch_fetch_posts(provider, lucky_tags, page=1, limit=cfg.page_size, lucky=True)
                else:
                    page += 1
                    posts = _batch_fetch_posts(provider, api_query, page=page, limit=cfg.page_size, lucky=False)
            except Exception as e:
                with BATCH_LOCK:
                    if BATCH_STATE.get("run_id") == run_id:
                        BATCH_STATE["last_error"] = f"検索エラー ({provider}): {e}"
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
                    if BATCH_STATE["stop_requested"] or BATCH_STATE.get("run_id") != run_id:
                        break
                post_id = post.get("id")
                with BATCH_LOCK:
                    if BATCH_STATE.get("run_id") == run_id:
                        BATCH_STATE["current_post_id"] = post_id
                        BATCH_STATE["total_checked"] += 1

                post_key = f"{provider}:{post_id}"
                post_url = _batch_post_url(provider, post_id)
                if post_key in seen_keys or str(post_id) in seen_keys or post_url in seen_keys:
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
                    url=post_url,
                    heroine=cfg.heroine, model=cfg.model, artist_mode=cfg.artist_mode,
                    custom_artist=cfg.custom_artist,
                    override_breasts=cfg.override_breasts,
                    override_skin=cfg.override_skin,
                    override_costume=cfg.override_costume,
                    override_art_style=cfg.override_art_style,
                    multi_mode=getattr(cfg, "multi_mode", "capsule"),
                    use_custom=cfg.use_custom, checkpoint=cfg.checkpoint, backend=cfg.backend,
                    width=cfg.width, height=cfg.height, timeout=cfg.timeout,
                    search_query=cfg.search,
                    is_batch=True,
                )
                job_id = _enqueue_generate_job(req, BATCH_PRIORITY)

                # このジョブが完了するまで待ってから次の投稿へ（手動生成は優先度でこのジョブより先に処理される）
                # NOTE: _prune_jobs_locked() で job_id が削除される場合があるため KeyError を明示的に補足する
                while True:
                    time.sleep(0.5)
                    with BATCH_LOCK:
                        if BATCH_STATE["stop_requested"] or BATCH_STATE.get("run_id") != run_id:
                            status = "aborted"
                            error = "強制終了"
                            break
                    with JOBS_LOCK:
                        job = JOBS.get(job_id)
                    if job is None:
                        # ジョブがパージ済み → done扱いで継続
                        status = "done"
                        error = None
                        break
                    status = job["status"]
                    error = job.get("error")
                    if status in ("done", "error"):
                        break

                if status == "aborted":
                    break

                seen_keys.add(post_key)
                seen_keys.add(str(post_id))
                seen_keys.add(post_url)

                with BATCH_LOCK:
                    if BATCH_STATE.get("run_id") == run_id:
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
                        if BATCH_STATE.get("run_id") == run_id:
                            BATCH_STATE["stop_requested"] = True
                    break

                time.sleep(cfg.interval_sec)

            if cfg.lucky and new_in_round == 0:
                # 今回のラウンドは全件生成済みだった（母集団が少ない等）。少し待ってから引き直す
                time.sleep(cfg.interval_sec)

    except Exception as e:
        # 未補足例外でスレッドが死んでもrunningを確実にFalseに戻し、再起動できるようにする
        print(f"[BATCH] ワーカースレッドが予期しない例外で終了: {e}")
        notify_failure("バッチワーカー異常終了", str(e))
        with BATCH_LOCK:
            if BATCH_STATE.get("run_id") == run_id:
                BATCH_STATE["last_error"] = f"ワーカー異常終了: {e}"
    finally:
        with BATCH_LOCK:
            if BATCH_STATE.get("run_id") == run_id:
                BATCH_STATE["running"] = False
                BATCH_STATE["current_post_id"] = None
                BATCH_STATE["stop_requested"] = False


@app.post("/batch/start")
def batch_start(cfg: BatchConfig):
    heroine = cfg.heroine or config.DEFAULT_HEROINE
    if heroine not in config.HEROINES:
        raise HTTPException(status_code=400, detail=f"unknown heroine: {heroine}")

    if cfg.provider == "gelbooru":
        if not getattr(config, "GELBOORU_USER_ID", None) or not getattr(config, "GELBOORU_API_KEY", None):
            raise HTTPException(
                status_code=400,
                detail="Gelbooruをプロバイダに指定する場合、設定タブでGelbooru User IDとAPI Keyの登録が必須となります。"
            )

    import uuid
    run_id = uuid.uuid4().hex

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
            "run_id": run_id,
        })
    threading.Thread(target=_batch_worker_loop, args=(cfg, run_id), daemon=True).start()
    return _batch_status_snapshot()


@app.post("/batch/stop")
def batch_stop():
    with BATCH_LOCK:
        if not BATCH_STATE["running"]:
            raise HTTPException(status_code=409, detail="batch is not running")
        BATCH_STATE["stop_requested"] = True
    return _batch_status_snapshot()


@app.post("/batch/reset")
def batch_reset():
    """ワーカースレッドが死んでrunning=Trueのまま詰まった場合の強制リセット。
    ワーカーが実際に生きている場合は停止リクエストも同時に送る。"""
    with BATCH_LOCK:
        BATCH_STATE["running"] = False
        BATCH_STATE["stop_requested"] = True
        BATCH_STATE["current_post_id"] = None
        BATCH_STATE["last_error"] = "(手動リセット)"
    return {"ok": True, "message": "バッチ状態を強制リセットしたわ。再起動できるようになったわよ。"}


@app.get("/batch/status")
def batch_status():
    return _batch_status_snapshot()


@app.get("/backends")
def get_backends(health: bool = True):
    """config.GENERATION_BACKENDSの一覧（Web UIのプルダウン用）。
    health=true の場合のみ各バックエンドのComfyUI生存確認を行う（初期表示用の高速レスポンスと分離）。
    """
    backends = getattr(config, "GENERATION_BACKENDS", {})
    default_id = getattr(config, "DEFAULT_BACKEND", None)

    if health:
        result = []
        for bid, b in backends.items():
            url = b.get("comfy_url", COMFYUI_URL)
            online = check_comfy_online(url, timeout=1.0)
            result.append({"id": bid, "label": b.get("label", bid), "online": online})

        # コンフィグのデフォルトがオンラインならそのまま使う。
        # オフラインなら、最初にオンラインのバックエンドを自動的に推奨デフォルトにする。
        if default_id and any(b["id"] == default_id and b["online"] for b in result):
            effective_default = default_id
        else:
            first_online = next((b["id"] for b in result if b["online"]), None)
            effective_default = first_online or default_id

        return {"backends": result, "default": effective_default, "config_default": default_id}
    else:
        # ヘルスチェックなし（高速）: online フィールドは None（未チェック）として返す
        result = [
            {"id": bid, "label": b.get("label", bid), "online": None}
            for bid, b in backends.items()
        ]
        return {"backends": result, "default": default_id, "config_default": default_id}


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
    user_cfg = getattr(config, "USER_CONFIG", {})
    user_purge = user_cfg.get("purge_tags") or user_cfg.get("user_purge_tags") or []
    user_unpurge = user_cfg.get("unpurge_tags") or user_cfg.get("user_unpurge_tags") or []
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
    user_cfg = getattr(config, "USER_CONFIG", {})
    saved_purge = user_cfg.get("purge_tags") or user_cfg.get("user_purge_tags") or []
    saved_unpurge = user_cfg.get("unpurge_tags") or user_cfg.get("user_unpurge_tags") or []
    return {
        "status": "ok",
        "user_purge_tags": sorted(saved_purge),
        "user_unpurge_tags": sorted(saved_unpurge),
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


class SiteAuthConfigRequest(BaseModel):
    civitai_api_key: Optional[str] = None
    danbooru_login: Optional[str] = None
    danbooru_api_key: Optional[str] = None
    gelbooru_user_id: Optional[str] = None
    gelbooru_api_key: Optional[str] = None


@app.get("/config/site_auth")
def get_site_auth_config():
    """各サイトのAPI認証情報を取得"""
    user_cfg = getattr(config, "USER_CONFIG", {})
    return {
        "civitai_api_key": user_cfg.get("civitai_api_key", "") or "",
        "danbooru_login": user_cfg.get("danbooru_login", "") or "",
        "danbooru_api_key": user_cfg.get("danbooru_api_key", "") or "",
        "gelbooru_user_id": user_cfg.get("gelbooru_user_id", "") or "",
        "gelbooru_api_key": user_cfg.get("gelbooru_api_key", "") or "",
    }


@app.post("/config/site_auth")
def update_site_auth_config(req: SiteAuthConfigRequest):
    """各サイトのAPI認証情報を保存してホットリロード"""
    config.save_site_auth_config(
        civitai_api_key=req.civitai_api_key,
        danbooru_login=req.danbooru_login,
        danbooru_api_key=req.danbooru_api_key,
        gelbooru_user_id=req.gelbooru_user_id,
        gelbooru_api_key=req.gelbooru_api_key,
    )
    return {"status": "ok"}


@app.get("/version")
def get_version():
    """バージョン情報・Gitコミット・ブランチ・デプロイ環境種別を返す"""
    commit = os.environ.get("SOURCE_COMMIT") or os.environ.get("GIT_COMMIT")
    if not commit:
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
            if res.returncode == 0:
                commit = res.stdout.strip()
        except Exception:
            pass
    commit = commit or "unknown"
    short_commit = commit[:7] if commit != "unknown" else "unknown"

    branch = os.environ.get("COOLIFY_BRANCH")
    if not branch:
        try:
            res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
            if res.returncode == 0:
                branch = res.stdout.strip()
        except Exception:
            pass
    branch = branch or "unknown"

    container_name = os.environ.get("COOLIFY_CONTAINER_NAME", "")

    # プレビュー環境判定 (PR ID 抽出)
    pr_id = None
    pr_match = re.search(r"pull/(\d+)/", branch) or re.search(r"-pr-(\d+)", container_name)
    if pr_match:
        pr_id = pr_match.group(1)

    is_preview = bool(pr_id or "-pr-" in container_name or "pull/" in branch)

    return {
        "version": APP_VERSION,
        "commit": short_commit,
        "full_commit": commit,
        "branch": branch,
        "is_preview": is_preview,
        "pr_id": pr_id,
        "repo_url": REPO_URL,
        "commit_url": f"{REPO_URL}/commit/{commit}" if commit != "unknown" else None,
        "pr_url": f"{REPO_URL}/pull/{pr_id}" if pr_id else None,
    }


WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=getattr(config, "API_HOST", "127.0.0.1"), port=getattr(config, "API_PORT", 8000))

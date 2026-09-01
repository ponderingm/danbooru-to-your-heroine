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
    GET  /            - Webビューア（src/web/index.html）
    GET  /heroines     - config.HEROINES の一覧
    POST /convert      - URL→プロンプト変換のみ（画像生成なし）
    POST /generate     - 変換 + ComfyUIで画像生成（同じpost/heroineでも再生成OK。重複判定は行わない）
    GET  /images       - 生成済み画像のmanifest一覧（新しい順）
    GET  /output/{fn}  - 生成画像の静的配信

バッチ生成（danbooru_search_batch_generator.py）は独自の進捗ファイル
（database/danbooru_search_batch_progress.json）でpost_id単位の重複をスキップするが、
このAPI/Webビューア経由の/generateはその進捗ファイルを一切参照しないため、
同じ投稿・同じヒロインでも何度でも再生成できる。
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from danbooru_to_heroine import extract_post_id, fetch_post, mutate_tags_to_heroine, build_prompt
from model_adapter import adapt_prompt, get_negative_prompt
from comfy_client import (
    COMFYUI_URL, CUSTOM_COMFY_URL, ANIMA_COMFY_URL,
    compute_canvas_size, create_default_workflow, create_custom_workflow, create_anima_workflow,
    submit_and_wait,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "database", "generated_manifest.json")

app = FastAPI(title="danbooru-to-your-heroine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(config, "CORS_ORIGINS", []),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

os.makedirs(config.OUTPUT_DIR, exist_ok=True)
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")


class ConvertRequest(BaseModel):
    url: str
    heroine: Optional[str] = None
    model: str = "illustrious"
    nsfw: bool = True
    include_artist: bool = False


class GenerateRequest(ConvertRequest):
    checkpoint: Optional[str] = None
    width: int = 832
    height: int = 1216
    use_custom: bool = False
    timeout: int = 180


def _convert(req: ConvertRequest):
    heroine = req.heroine or config.DEFAULT_HEROINE
    if heroine not in config.HEROINES:
        raise HTTPException(status_code=400, detail=f"unknown heroine: {heroine}")

    try:
        post_id = extract_post_id(req.url)
        post = fetch_post(post_id, login=config.DANBOORU_LOGIN, api_key=config.DANBOORU_API_KEY)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Danbooru API error: {e}")

    identity_tags, situation_tags, _removed = mutate_tags_to_heroine(
        post, heroine=heroine, nsfw=req.nsfw, include_artist=req.include_artist,
    )
    base_prompt = build_prompt(identity_tags, situation_tags)
    prompt = adapt_prompt(base_prompt, model_type=req.model, is_h_scene=req.nsfw)
    return post, heroine, prompt


def _append_manifest(entry: dict) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    manifest = []
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    manifest.append(entry)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


@app.get("/heroines")
def list_heroines():
    return {key: {"name": dna["name"]} for key, dna in config.HEROINES.items()}


@app.post("/convert")
def convert(req: ConvertRequest):
    post, heroine, prompt = _convert(req)
    return {"post_id": post.get("id"), "original_url": req.url, "heroine": heroine, "prompt": prompt}


@app.post("/generate")
def generate(req: GenerateRequest):
    post, heroine, prompt = _convert(req)

    negative = get_negative_prompt(model_type=req.model)
    checkpoint = req.checkpoint or config.DEFAULT_CHECKPOINT
    canvas_size = compute_canvas_size(post.get("image_width"), post.get("image_height"))
    gen_width, gen_height = canvas_size if canvas_size else (req.width, req.height)
    prefix = f"API_{post.get('id')}_{int(time.time())}"

    if "anima" in req.model.lower():
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
        "model": req.model,
        "nsfw": req.nsfw,
        "include_artist": req.include_artist,
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


@app.get("/images")
def list_images(limit: int = 50):
    if not os.path.exists(MANIFEST_PATH):
        return []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    entries = list(reversed(manifest[-limit:]))
    # 旧形式（image_urls未保存）のエントリにも後方互換でimage_urlsを補う
    for entry in entries:
        entry.setdefault("image_urls", [f"/output/{fn}" for fn in entry.get("files", [])])
    return entries


WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=getattr(config, "API_HOST", "127.0.0.1"), port=getattr(config, "API_PORT", 8000))

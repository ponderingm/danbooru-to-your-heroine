"""
comfy_client.py
===============
ComfyUI ワークフロー生成・送信・画像保存ロジック。

- default: ローカルComfyUI (config.COMFYUI_API_URL) + 通常のKSampler設定で生成
- custom : 別ComfyUIエンドポイント (config.CUSTOM_COMFY_URL) 向け。任意のLoRA・
           ステップ数・サンプラーを config.py で指定できる（高速化LoRA運用等を想定）
- anima  : Anima v1.0 DiT向け。SDXLのcheckpointとは別物のUNETLoader/CLIPLoader/VAELoader
           グラフを使う（config.ANIMA_COMFY_URL）

上記3種類のワークフローとComfyUIエンドポイントを名前付きでまとめたものが
config.GENERATION_BACKENDS。resolve_backend()/build_workflow_for_backend()経由で使う。
"""

import json
import math
import os
import random
import shutil
import time
import urllib.request
import urllib.parse

import config

COMFYUI_URL = config.COMFYUI_API_URL
CUSTOM_COMFY_URL = config.CUSTOM_COMFY_URL
CUSTOM_LORA_NAME = config.CUSTOM_LORA_NAME
CUSTOM_STEPS = config.CUSTOM_STEPS
CUSTOM_CFG = config.CUSTOM_CFG
CUSTOM_SAMPLER = config.CUSTOM_SAMPLER
CUSTOM_SCHEDULER = config.CUSTOM_SCHEDULER
ANIMA_COMFY_URL = config.ANIMA_COMFY_URL
ANIMA_UNET_NAME = config.ANIMA_UNET_NAME
ANIMA_CLIP_NAME = config.ANIMA_CLIP_NAME
ANIMA_VAE_NAME = config.ANIMA_VAE_NAME
ANIMA_STEPS = config.ANIMA_STEPS
ANIMA_CFG = config.ANIMA_CFG
ANIMA_SAMPLER = config.ANIMA_SAMPLER
ANIMA_SCHEDULER = config.ANIMA_SCHEDULER
OUTPUT_DIR = config.OUTPUT_DIR
WEB_OUTPUT_DIR = config.WEB_OUTPUT_DIR

# Danbooru元画像のアスペクト比を保ったまま、総ピクセル数を約1024x1024に近似させたSDXL向けキャンバスサイズを求める
TARGET_CANVAS_PIXELS = 1024 * 1024


def compute_canvas_size(orig_width, orig_height, target_pixels: int = TARGET_CANVAS_PIXELS,
                         multiple: int = 64, min_side: int = 512, max_side: int = 1536):
    if not orig_width or not orig_height:
        return None
    aspect = orig_width / orig_height
    w = math.sqrt(target_pixels * aspect)
    h = math.sqrt(target_pixels / aspect)

    def snap(x):
        x = round(x / multiple) * multiple
        return int(min(max(x, min_side), max_side))

    return snap(w), snap(h)


def create_default_workflow(prompt_text: str, negative_text: str, filename_prefix: str,
                             checkpoint: str, width: int = 832, height: int = 1216, seed: int = None) -> dict:
    if seed is None:
        seed = random.randint(100000, 99999999)
    return {
        "4": {"inputs": {"ckpt_name": checkpoint}, "class_type": "CheckpointLoaderSimple"},
        "6": {"inputs": {"text": prompt_text, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": negative_text, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "3": {
            "inputs": {
                "seed": seed, "steps": 25, "cfg": 5.5,
                "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
                "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "8": {"inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}, "class_type": "SaveImage"},
    }


def resolve_backend(backend_id: str = None) -> dict:
    """config.GENERATION_BACKENDSからbackend_idを引き、生成に必要な設定一式を返す。
    未指定/未登録ならconfig.DEFAULT_BACKENDにフォールバックする"""
    backends = getattr(config, "GENERATION_BACKENDS", {})
    if backend_id not in backends:
        backend_id = getattr(config, "DEFAULT_BACKEND", None)
    backend = backends.get(backend_id, {})
    return {
        "id": backend_id,
        "label": backend.get("label", backend_id or ""),
        "model": backend.get("model", "illustrious"),
        "workflow": backend.get("workflow", "default"),
        "comfy_url": backend.get("comfy_url", COMFYUI_URL),
        "checkpoint": backend.get("checkpoint") or config.DEFAULT_CHECKPOINT,
        "lora_name": backend.get("lora_name", CUSTOM_LORA_NAME),
        "steps": backend.get("steps", CUSTOM_STEPS),
        "cfg": backend.get("cfg", CUSTOM_CFG),
        "sampler": backend.get("sampler", CUSTOM_SAMPLER),
        "scheduler": backend.get("scheduler", CUSTOM_SCHEDULER),
    }


def list_backends() -> list:
    """Web UIのプルダウン等で使う{id,label}の一覧をconfig.GENERATION_BACKENDSの登録順で返す"""
    backends = getattr(config, "GENERATION_BACKENDS", {})
    return [{"id": bid, "label": b.get("label", bid)} for bid, b in backends.items()]


def create_custom_workflow(prompt_text: str, negative_text: str, filename_prefix: str,
                            checkpoint: str, width: int = 832, height: int = 1216,
                            seed: int = None, lora_name: str = None, steps: int = None,
                            cfg: float = None, sampler: str = None, scheduler: str = None) -> dict:
    """config.pyのCUSTOM_*設定（LoRA・ステップ数・サンプラー等）を使う任意ワークフロー。
    各引数はNoneならCUSTOM_*グローバル設定にフォールバックする（GENERATION_PRESETS経由の上書き用）"""
    if seed is None:
        seed = random.randint(100000, 99999999)
    if lora_name is None:
        lora_name = CUSTOM_LORA_NAME
    if steps is None:
        steps = CUSTOM_STEPS
    if cfg is None:
        cfg = CUSTOM_CFG
    if sampler is None:
        sampler = CUSTOM_SAMPLER
    if scheduler is None:
        scheduler = CUSTOM_SCHEDULER
    return {
        "1": {"inputs": {"ckpt_name": checkpoint}, "class_type": "CheckpointLoaderSimple"},
        "2": {
            "inputs": {
                "lora_name": lora_name, "strength_model": 1.0, "strength_clip": 1.0,
                "model": ["1", 0], "clip": ["1", 1],
            },
            "class_type": "LoraLoader",
        },
        "3": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "4": {"inputs": {"text": prompt_text, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "5": {"inputs": {"text": negative_text, "clip": ["2", 1]}, "class_type": "CLIPTextEncode"},
        "6": {
            "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
                "model": ["2", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["3", 0],
            },
            "class_type": "KSampler",
        },
        "7": {"inputs": {"samples": ["6", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "8": {"inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]}, "class_type": "SaveImage"},
    }


def create_anima_workflow(prompt_text: str, negative_text: str, filename_prefix: str,
                           width: int = 832, height: int = 1216, seed: int = None) -> dict:
    """Anima v1.0 DiT向けワークフロー。SDXL checkpointは使わず、UNETLoader/CLIPLoader/VAELoaderで構成する"""
    if seed is None:
        seed = random.randint(100000, 99999999)
    return {
        "1": {"inputs": {"unet_name": ANIMA_UNET_NAME, "weight_dtype": "default"}, "class_type": "UNETLoader"},
        "2": {"inputs": {"clip_name": ANIMA_CLIP_NAME, "type": "qwen_image"}, "class_type": "CLIPLoader"},
        "3": {"inputs": {"vae_name": ANIMA_VAE_NAME}, "class_type": "VAELoader"},
        "4": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "5": {"inputs": {"text": prompt_text, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        "6": {"inputs": {"text": negative_text, "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
        "7": {
            "inputs": {
                "seed": seed, "steps": ANIMA_STEPS, "cfg": ANIMA_CFG,
                "sampler_name": ANIMA_SAMPLER, "scheduler": ANIMA_SCHEDULER, "denoise": 1.0,
                "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["4", 0],
            },
            "class_type": "KSampler",
        },
        "8": {"inputs": {"samples": ["7", 0], "vae": ["3", 0]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}, "class_type": "SaveImage"},
    }


def build_workflow_for_backend(backend: dict, prompt_text: str, negative_text: str, filename_prefix: str,
                                width: int = 832, height: int = 1216, seed: int = None) -> dict:
    """resolve_backend()の戻り値からworkflow種別(default/custom/anima)に応じたワークフロー辞書を組み立てる
    （server.py/danbooru_search_batch_generator.py共通のバックエンド分岐ロジック）"""
    workflow = backend["workflow"]
    if workflow == "anima":
        return create_anima_workflow(
            prompt_text=prompt_text, negative_text=negative_text, filename_prefix=filename_prefix,
            width=width, height=height, seed=seed,
        )
    if workflow == "custom":
        return create_custom_workflow(
            prompt_text=prompt_text, negative_text=negative_text, filename_prefix=filename_prefix,
            checkpoint=backend["checkpoint"], width=width, height=height, seed=seed,
            lora_name=backend["lora_name"], steps=backend["steps"], cfg=backend["cfg"],
            sampler=backend["sampler"], scheduler=backend["scheduler"],
        )
    return create_default_workflow(
        prompt_text=prompt_text, negative_text=negative_text, filename_prefix=filename_prefix,
        checkpoint=backend["checkpoint"], width=width, height=height, seed=seed,
    )


def check_comfy_online(base_url: str, timeout: float = 3) -> bool:
    """ComfyUIサーバーの生存確認（単発リクエストのみ、wait_for_comfyuiと違いリトライ待機はしない）"""
    try:
        req = urllib.request.Request(f"{base_url}/system_stats")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except Exception:
        return False


def wait_for_comfyui(base_url: str = COMFYUI_URL) -> None:
    attempt = 0
    while True:
        try:
            req = urllib.request.Request(f"{base_url}/system_stats")
            with urllib.request.urlopen(req, timeout=5) as resp:
                json.loads(resp.read().decode("utf-8"))
                if attempt > 0:
                    print("\n✨ ComfyUI is ONLINE! Resuming batch...")
                return
        except Exception as e:
            attempt += 1
            wait_sec = min(5 + attempt * 2, 30)
            print(f"⚠️ ComfyUI ({base_url}) unreachable ({e}). Retrying in {wait_sec}s...", end="\r", flush=True)
            time.sleep(wait_sec)


def submit_and_wait(workflow: dict, timeout: int = 180, base_url: str = COMFYUI_URL):
    req_data = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/prompt", data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        prompt_id = json.loads(resp.read().decode("utf-8")).get("prompt_id")

    start_t = time.time()
    saved_files = []
    while time.time() - start_t < timeout:
        try:
            hist_req = urllib.request.Request(f"{base_url}/history/{prompt_id}")
            with urllib.request.urlopen(hist_req, timeout=5) as resp:
                hist = json.loads(resp.read().decode("utf-8"))
            if prompt_id in hist:
                for _, nout in hist[prompt_id].get("outputs", {}).items():
                    for img in nout.get("images", []):
                        fn = img.get("filename")
                        img_url = f"{base_url}/view?filename={urllib.parse.quote(fn)}&type=output"
                        dest_path = os.path.join(OUTPUT_DIR, fn)
                        web_dest_path = os.path.join(WEB_OUTPUT_DIR, fn)
                        urllib.request.urlretrieve(img_url, dest_path)
                        # OUTPUT_DIR/WEB_OUTPUT_DIRが同一パスの場合、copyfileだとSameFileErrorになるため回避
                        if os.path.abspath(dest_path) != os.path.abspath(web_dest_path):
                            shutil.copyfile(dest_path, web_dest_path)
                        saved_files.append(fn)
                if saved_files:
                    return saved_files, time.time() - start_t
        except Exception:
            pass
        time.sleep(2)
    return saved_files, time.time() - start_t

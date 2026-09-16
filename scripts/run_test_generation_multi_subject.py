"""
run_test_generation_multi_subject.py
====================================
GPD ComfyUI (illustrious_4step_slow) を用いて、
複数人構図における「フラット方式」と「BREAK隔離方式」の
実際の画像生成をテスト・比較するスクリプト。
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import config
import comfy_client
from danbooru_to_heroine import get_heroine_dna
from test_multi_subject_separation import (
    separate_multi_subject_tags,
    build_flat_baseline_prompt,
    build_illustrious_prompt,
)

OUTPUT_DIR = Path(config.OUTPUT_DIR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_generation():
    backend_config = config.GENERATION_BACKENDS.get("illustrious_4step_slow")
    if not backend_config:
        print("Error: backend illustrious_4step_slow not found.")
        return

    # テスト用タグ (1girl 1boy のヘテロ構図サンプル)
    raw_danbooru_post_tags = [
        "score_9", "score_8", "score_7", "masterpiece", "best quality", "explicit", "highres",
        "1girl", "1boy", "hetero", "couple", "fellatio", "cum in mouth",
        "blonde hair", "blue eyes", "pale skin", "large breasts",
        "short black hair", "muscular male", "tall male", "penis",
        "bedroom", "night", "bed"
    ]
    
    # ユーザー設定からヒロインDNAを安全にロード
    heroine_cfg = get_heroine_dna("")
    heroine_dna = (
        heroine_cfg.get("identity_tags", [])
        + heroine_cfg.get("face_tags", [])
        + heroine_cfg.get("body_tags", [])
    )
    if not heroine_dna:
        heroine_dna = ["1girl", "brown hair", "short hair", "dark skin", "small breasts", "red eyes"]

    separated = separate_multi_subject_tags(raw_danbooru_post_tags, heroine_dna)
    prompt_flat = build_flat_baseline_prompt(separated)
    prompt_break = build_illustrious_prompt(separated)
    negative_prompt = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry"

    base_url = backend_config.get("comfy_url", comfy_client.COMFYUI_URL)

    print("=== [実証画像生成テスト: GPD ComfyUI (4-step)] ===")
    
    # テスト1: BREAK隔離方式
    print("\n🚀 [テスト 1/2] BREAK隔離方式 (新方式) で生成中...")
    print("Prompt:", prompt_break)
    t0 = time.time()
    try:
        wf_break = comfy_client.build_workflow_for_backend(
            backend=backend_config,
            prompt_text=prompt_break,
            negative_text=negative_prompt,
            filename_prefix="test_v3_break_separated",
            seed=42,
        )
        filenames_break, dt = comfy_client.submit_and_wait(wf_break, base_url=base_url)
        print(f"✅ 生成成功 ({dt:.2f}秒): {filenames_break}")
    except Exception as e:
        print(f"❌ 生成失敗: {e}")

    # テスト2: フラット方式
    print("\n🚀 [テスト 2/2] フラット方式 (旧方式・比較用) で生成中...")
    print("Prompt:", prompt_flat)
    t0 = time.time()
    try:
        wf_flat = comfy_client.build_workflow_for_backend(
            backend=backend_config,
            prompt_text=prompt_flat,
            negative_text=negative_prompt,
            filename_prefix="test_v3_flat_baseline",
            seed=42,
        )
        filenames_flat, dt = comfy_client.submit_and_wait(wf_flat, base_url=base_url)
        print(f"✅ 生成成功 ({dt:.2f}秒): {filenames_flat}")
    except Exception as e:
        print(f"❌ 生成失敗: {e}")


if __name__ == "__main__":
    test_generation()

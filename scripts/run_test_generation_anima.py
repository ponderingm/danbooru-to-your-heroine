"""
run_test_generation_anima.py
============================
GPD ComfyUI (anima_turbo_slow) を用いて、
Anima (Qwen LLMエンコーダー) における「前置詞カプセル化方式」
の実際の画像生成をテストするスクリプト。
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
    build_anima_prompt,
    build_flat_baseline_prompt,
)

OUTPUT_DIR = Path(config.OUTPUT_DIR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_anima():
    backend_config = config.GENERATION_BACKENDS.get("anima_turbo_slow")
    if not backend_config:
        print("Error: backend anima_turbo_slow not found.")
        return

    # テスト用タグ (1girl 1boy のヘテロ構図サンプル)
    raw_danbooru_post_tags = [
        "masterpiece", "best quality", "explicit", "highres",
        "1girl", "1boy", "hetero", "couple", "fellatio", "cum in mouth",
        "blonde hair", "blue eyes", "pale skin", "large breasts",
        "short black hair", "muscular male", "tall male", "penis",
        "bedroom", "night", "bed"
    ]
    
    # ユーザー設定からヒロインDNAを安全にロード
    heroine_cfg = get_heroine_dna("")
    heroine_name = heroine_cfg.get("name", "")
    heroine_dna = (
        heroine_cfg.get("identity_tags", [])
        + heroine_cfg.get("face_tags", [])
        + heroine_cfg.get("body_tags", [])
    )
    if not heroine_dna:
        heroine_dna = ["1girl", "brown hair", "short hair", "dark skin", "small breasts", "red eyes"]

    separated = separate_multi_subject_tags(raw_danbooru_post_tags, heroine_dna)
    prompt_anima = build_anima_prompt(separated, heroine_name=heroine_name)
    negative_prompt = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry"

    base_url = backend_config.get("comfy_url", comfy_client.COMFYUI_URL)

    print("=== [実証画像生成テスト: GPD ComfyUI (Anima Turbo)] ===")
    print("\n🚀 Qwen前置詞カプセル化方式で生成中...")
    print("Prompt:", prompt_anima)
    t0 = time.time()
    try:
        wf = comfy_client.build_workflow_for_backend(
            backend=backend_config,
            prompt_text=prompt_anima,
            negative_text=negative_prompt,
            filename_prefix="test_v3_anima_capsule",
            seed=42,
        )
        filenames, dt = comfy_client.submit_and_wait(wf, base_url=base_url, timeout=300)
        print(f"✅ 生成成功 ({dt:.2f}秒): {filenames}")
    except Exception as e:
        print(f"❌ 生成失敗: {e}")


if __name__ == "__main__":
    test_anima()

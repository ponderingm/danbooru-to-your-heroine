"""
bootstrap_tag_db_from_manifest.py
==================================
生成済みマニフェスト (database/generated_manifest.json) から
実績タグの出現頻度を集計し、LLM (Gemini / Ollama) を用いて
7大スロット＆サブプロパティ体系へ一括分類して初期Base辞書
(src/rules/tags_classification_base.json) を生成・更新するスクリプト。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# プロジェクトルートのパス解決
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config

MANIFEST_PATH = PROJECT_ROOT / "database" / "generated_manifest.json"
BASE_DB_PATH = PROJECT_ROOT / "src" / "rules" / "tags_classification_base.json"
PROMPT_FILE = PROJECT_ROOT / "src" / "prompts" / "tag_classification_system_instruction.md"

# 許可される親スロット一覧
VALID_PARENT_SLOTS = {
    "meta_quality",
    "subject",
    "character_dna",
    "costume",
    "accessories",
    "action_pose",
    "environment",
}


def load_system_instruction() -> str:
    """MarkdownファイルからLLM用システム指示文をロードする"""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"プロンプト指示ファイルが見つかりません: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def extract_tags_from_manifest(min_count: int = 1) -> List[tuple[str, int]]:
    """マニフェストからプロンプトタグを抽出・集計する"""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"マニフェストファイルが存在しません: {MANIFEST_PATH}")

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tag_counter = Counter()

    for entry in data:
        prompt = entry.get("prompt", "")
        # カンマ区切りで分割
        for raw_tag in prompt.split(","):
            t = raw_tag.strip().lower()
            if not t:
                continue
            # 単純なノイズ除去（数字単体など）
            if len(t) <= 1:
                continue
            tag_counter[t] += 1

    # 出現回数順にフィルタ・ソート
    filtered = [(tag, count) for tag, count in tag_counter.most_common() if count >= min_count]
    return filtered


def clean_json_response(raw_text: str) -> str:
    """Markdownコードブロックなどを取り除き、純粋なJSONテキストを抽出する"""
    text = raw_text.strip()
    # ```json ... ``` を除去
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def classify_tags_chunk_gemini(
    tags: List[str],
    system_instruction: str,
    api_key: Optional[str] = None,
    model: str = "gemini-2.5-flash",
) -> Dict[str, str]:
    """Gemini API を用いて1チャンク（50〜100タグ）を一括分類する"""
    key = api_key or os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None)
    if not key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    
    prompt_payload = {
        "tags_to_classify": tags
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"以下のタグリストを分類してください:\n{json.dumps(prompt_payload, ensure_ascii=False)}"}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        },
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError(f"Gemini APIから応答がありませんでした: {result}")

    raw_text = candidates[0]["content"]["parts"][0]["text"]
    cleaned_json = clean_json_response(raw_text)
    return json.loads(cleaned_json)


def classify_tags_chunk_ollama(
    tags: List[str],
    system_instruction: str,
    model: str = "qwen2.5:latest",
    ollama_url: str = "http://127.0.0.1:11434",
) -> Dict[str, str]:
    """Ollama API を用いて1チャンクを一括分類する"""
    url = f"{ollama_url.rstrip('/')}/api/generate"
    prompt_payload = {"tags_to_classify": tags}

    payload = {
        "model": model,
        "system": system_instruction,
        "prompt": f"以下のタグリストを分類してください:\n{json.dumps(prompt_payload, ensure_ascii=False)}",
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw_text = result.get("response", "")
    cleaned_json = clean_json_response(raw_text)
    return json.loads(cleaned_json)


def validate_classified_chunk(raw_dict: Dict[str, Any]) -> Dict[str, str]:
    """分類結果のキーとスロットパスを検証・正規化する"""
    valid_res = {}
    for tag, slot in raw_dict.items():
        if not isinstance(tag, str) or not isinstance(slot, str):
            continue
        cleaned_tag = tag.strip().lower()
        cleaned_slot = slot.strip().lower()
        
        # 決定論的ルール（自明なプレフィックスの自動補正）
        if cleaned_tag.startswith("@") or cleaned_tag.startswith("drawn by"):
            valid_res[cleaned_tag] = "meta_quality.artist"
            continue
        if cleaned_tag.startswith("score_"):
            valid_res[cleaned_tag] = "meta_quality.quality"
            continue

        # 親スロットの妥当性確認
        parent = cleaned_slot.split(".")[0]
        if parent in VALID_PARENT_SLOTS:
            valid_res[cleaned_tag] = cleaned_slot
    return valid_res


def main():
    parser = argparse.ArgumentParser(description="マニフェストからタグ分類DBをブートストラップ構築するスクリプト")
    parser.add_argument("--limit", type=int, default=1000, help="分類対象とする上位タグ件数の上限 (デフォルト: 1000)")
    parser.add_argument("--min-count", type=int, default=2, help="対象とするタグの最低出現回数 (デフォルト: 2)")
    parser.add_argument("--chunk-size", type=int, default=50, help="LLMへの1リクエストあたりのタグ数 (デフォルト: 50)")
    parser.add_argument("--provider", choices=["auto", "gemini", "ollama"], default="auto", help="LLMプロバイダ")
    parser.add_argument("--dry-run", action="store_true", help="LLMを呼ばずにタグ集計と対象件数のみ表示")

    args = parser.parse_args()

    print("📊 マニフェストからタグ頻度を集計中...")
    tags_with_count = extract_tags_from_manifest(min_count=args.min_count)
    print(f"集計完了: 最低出現回数 {args.min_count} 以上のユニークタグ = {len(tags_with_count)} 件")

    # 既存DBのロード（差分学習のため）
    existing_db: Dict[str, str] = {}
    if BASE_DB_PATH.exists():
        try:
            existing_db = json.loads(BASE_DB_PATH.read_text(encoding="utf-8"))
            print(f"既存の分類DBロード完了: {len(existing_db)} 件登録済み")
        except Exception as e:
            print(f"既存DB読み込み失敗 (新規作成します): {e}")

    # 上位N件から、まだ未分類のタグを抽出
    target_tags = []
    for t, count in tags_with_count:
        if t not in existing_db:
            target_tags.append((t, count))
        if len(target_tags) >= args.limit:
            break

    print(f"今回の分類対象 (未登録タグ): {len(target_tags)} 件 (上限: {args.limit})")

    if not target_tags:
        print("✨ すべての対象タグは既に分類DBに登録されています。処理を終了します。")
        return

    if args.dry_run:
        print("\n[Dry Run] 上位20件の未分類タグ:")
        for t, c in target_tags[:20]:
            print(f"  - {t:<30} (出現回数: {c})")
        print("\nDry-run 完了。")
        return

    system_instruction = load_system_instruction()
    tags_only = [t for t, _ in target_tags]
    total_chunks = (len(tags_only) + args.chunk_size - 1) // args.chunk_size

    # プロバイダ決定
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None))
    provider = "gemini" if (args.provider == "gemini" or (args.provider == "auto" and has_gemini)) else "ollama"
    print(f"使用プロバイダ: {provider} (チャンク数: {total_chunks}, チャンクサイズ: {args.chunk_size})")

    success_count = 0
    for idx in range(0, len(tags_only), args.chunk_size):
        chunk = tags_only[idx : idx + args.chunk_size]
        chunk_num = (idx // args.chunk_size) + 1
        print(f"[{chunk_num}/{total_chunks}] {len(chunk)} 件のタグを分類中... ({chunk[0]} 〜 {chunk[-1]})")

        classified = {}
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if provider == "gemini":
                    classified = classify_tags_chunk_gemini(chunk, system_instruction)
                else:
                    classified = classify_tags_chunk_ollama(chunk, system_instruction)
                break
            except Exception as e:
                print(f"⚠️ チャンク {chunk_num} (試行 {attempt}/{max_retries}) でエラー: {e}")
                if attempt < max_retries:
                    time.sleep(3)
                else:
                    print(f"❌ チャンク {chunk_num} の分類をスキップします")

        valid_chunk = validate_classified_chunk(classified)
        existing_db.update(valid_chunk)
        success_count += len(valid_chunk)
        print(f"  -> {len(valid_chunk)} 件の分類に成功 (有効率: {len(valid_chunk)}/{len(chunk)})")

        # 随時セーブして安全性を担保
        BASE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASE_DB_PATH.write_text(json.dumps(existing_db, ensure_ascii=False, indent=2), encoding="utf-8")

        # APIレートリミット配慮
        if provider == "gemini":
            time.sleep(0.5)

    print(f"\n🎉 バッチ分類完了！ 新規登録: {success_count} 件, DB総登録数: {len(existing_db)} 件")
    print(f"保存先: {BASE_DB_PATH}")


if __name__ == "__main__":
    main()

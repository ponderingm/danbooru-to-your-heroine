"""
natural_to_danbooru.py
======================
自然言語入力（日本語・英語）からLLMを用いて最小限の基本タグを抽出し、
必要に応じてGelbooru積集合から「共起の輪の中心核（起爆剤タグ）」を発見して
Danbooru / Gelbooru 向けの最適な検索クエリを生成するCLIおよびコアロジック。
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from cooccurrence_finder import find_cooccurrence_ring

# プロンプト定義ファイル
PROMPT_FILE = Path(__file__).parent / "prompts" / "natural_search_system_instruction.md"


def load_system_instruction() -> str:
    """MarkdownファイルからLLM用システム指示文をロードする"""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"プロンプト指示ファイルが見つかりません: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def convert_natural_to_tags_gemini(text: str, api_key: Optional[str] = None, model: str = "gemini-2.5-flash") -> str:
    """Gemini API (REST) を直接呼び出して自然言語からタグを抽出する"""
    key = api_key or os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None)
    if not key:
        raise ValueError("Gemini API Keyが設定されていません。環境変数 GEMINI_API_KEY または config.yaml を確認してください。")

    system_instruction = load_system_instruction()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"ユーザー要望: {text}"}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        },
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 100,
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    try:
        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini APIから応答が得られませんでした: {result}")
        raw_text = candidates[0]["content"]["parts"][0]["text"].strip()
        # 不要な改行やバッククォートがあれば除去
        clean_tags = raw_text.replace("`", "").strip().split("\n")[0]
        return clean_tags
    except (KeyError, IndexError) as e:
        raise ValueError(f"Gemini APIレスポンスの解析に失敗しました: {e}, Raw: {result}")


def convert_natural_to_tags_ollama(
    text: str,
    model: str = "qwen2.5:latest",
    ollama_url: str = "http://127.0.0.1:11434"
) -> str:
    """ローカル Ollama API を呼び出して自然言語からタグを抽出する"""
    system_instruction = load_system_instruction()
    url = f"{ollama_url.rstrip('/')}/api/generate"

    payload = {
        "model": model,
        "system": system_instruction,
        "prompt": f"ユーザー要望: {text}",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 100,
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw_text = result.get("response", "").strip()
    clean_tags = raw_text.replace("`", "").strip().split("\n")[0]
    return clean_tags


def resolve_tags(
    text: str,
    provider: str = "auto",
    gemini_key: Optional[str] = None,
    find_core: bool = False,
) -> Dict[str, Any]:
    """
    自然言語からタグを抽出し、必要に応じて共起の輪の中心核（起爆剤タグ）を特定する。
    """
    tags_str = ""
    used_provider = ""

    # プロバイダ決定
    has_gemini = bool(gemini_key or os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None))
    
    if provider == "gemini" or (provider == "auto" and has_gemini):
        tags_str = convert_natural_to_tags_gemini(text, api_key=gemini_key)
        used_provider = "gemini"
    else:
        try:
            tags_str = convert_natural_to_tags_ollama(text)
            used_provider = "ollama"
        except Exception as e:
            if has_gemini:
                tags_str = convert_natural_to_tags_gemini(text, api_key=gemini_key)
                used_provider = "gemini"
            else:
                raise RuntimeError(f"タグ抽出に失敗しました (Ollamaエラー: {e})。Gemini API Keyを設定するかOllamaを起動してください。")

    tag_list = [t for t in tags_str.split() if t]
    
    res = {
        "input_text": text,
        "provider": used_provider,
        "extracted_tags": tag_list,
        "query_string": " ".join(tag_list),
        "cooccurrence_ring": None,
    }

    # Gelbooru積集合による共起の中心核探索
    if find_core and tag_list:
        try:
            core_info = find_cooccurrence_ring(tag_list, limit=30, top_k=5)
            res["cooccurrence_ring"] = core_info
        except Exception as e:
            res["cooccurrence_ring"] = {"error": str(e)}

    return res


def main():
    parser = argparse.ArgumentParser(description="自然言語からDanbooru/Gelbooru検索タグを生成・共起解析するCLI")
    parser.add_argument("query", help="イラストのシチュエーションや要望（日本語または英語）")
    parser.add_argument("--provider", choices=["auto", "gemini", "ollama"], default="auto", help="LLMプロバイダ")
    parser.add_argument("--find-core", action="store_true", help="Gelbooru積集合から共起の輪の中心核（起爆剤タグ）を探索する")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    try:
        result = resolve_tags(args.query, provider=args.provider, find_core=args.find_core)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["query_string"])
            if result.get("cooccurrence_ring") and result["cooccurrence_ring"].get("core_candidates"):
                print("\n[共起の輪の中心核候補 (xxxxx ring)]:")
                for c in result["cooccurrence_ring"]["core_candidates"]:
                    print(f" - {c['tag']} (頻度: {c['frequency_percent']}%, {c['count']}件)")
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

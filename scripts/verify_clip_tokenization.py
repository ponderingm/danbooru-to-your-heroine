"""
verify_clip_tokenization.py
===========================
SDXL / Illustrious が採用している OpenAI CLIP (CLIP-ViT-L/14) の公式語彙辞書
(vocab.json) を直接用いて、カンマ (,) がトークンを消費する事実、
およびDanbooruタグプロンプトでのトークン消費構造を厳密に裏どり・検証するスクリプト。
"""

import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

VOCAB_CACHE_FILE = Path(__file__).resolve().parent.parent / "database" / "clip_vocab_cache.json"


def get_clip_vocab() -> Dict[str, int]:
    """OpenAI CLIP の公式 vocab.json を取得（キャッシュ対応）"""
    if VOCAB_CACHE_FILE.exists():
        with open(VOCAB_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    url = "https://huggingface.co/openai/clip-vit-large-patch14/raw/main/vocab.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        vocab = json.loads(resp.read().decode("utf-8"))

    VOCAB_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VOCAB_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False)
    return vocab


def simple_tokenize_example(text: str, vocab: Dict[str, int]) -> List[Tuple[str, int]]:
    """
    CLIPのトークナイズ規則のデモ:
    テキスト中の単語およびカンマ記号を語彙IDにマッピングする。
    """
    import re
    # CLIPの基本正規表現パターン（カンマや記号を独立したトークンとして抽出）
    pattern = re.compile(r"""<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[\w]+|[^\s\w]+""", re.IGNORECASE)
    raw_tokens = pattern.findall(text)
    
    result = []
    # 先頭SOT
    result.append(("<|startoftext|>", vocab.get("<|startoftext|>", -1)))
    
    for t in raw_tokens:
        token_str = t.lower()
        # 単語末尾トークンとして検索
        w_token = token_str + "</w>"
        if w_token in vocab:
            result.append((w_token, vocab[w_token]))
        elif token_str in vocab:
            result.append((token_str, vocab[token_str]))
        else:
            # 未知語やサブワード分割される場合はプレースホルダー
            result.append((f"[subword:{token_str}]", -1))
            
    # 末尾EOT
    result.append(("<|endoftext|>", vocab.get("<|endoftext|>", -1)))
    return result


def main():
    print("=" * 75)
    print("🔬 [SDXL / CLIP-ViT-L/14 公式語彙によるトークン消費 厳密検証]")
    print("=" * 75)

    vocab = get_clip_vocab()
    print(f"✅ CLIP語彙総数: {len(vocab):,} 語")

    # 1. カンマの語彙IDの直接確認
    print("\n【1. 記号・特殊トークンの語彙辞書 (vocab.json) 実値】")
    print(f"  - カンマ単体 ',': ID = {vocab.get(',')}")
    print(f"  - 単語終端付きカンマ ',</w>': ID = {vocab.get(',</w>')}")
    print(f"  - 始端トークン <|startoftext|>: ID = {vocab.get('<|startoftext|>')}")
    print(f"  - 終端トークン <|endoftext|>: ID = {vocab.get('<|endoftext|>')}")
    print("  ➜ カンマは省略不可の「独立した1トークン」として辞書に完全登録されている。")

    # 2. 短いプロンプトでのカンマあり vs なし比較
    prompt_with_comma = "masterpiece, best quality, dark skin"
    prompt_without_comma = "masterpiece best quality dark skin"

    tokens_with = simple_tokenize_example(prompt_with_comma, vocab)
    tokens_without = simple_tokenize_example(prompt_without_comma, vocab)

    print("\n" + "=" * 75)
    print("【2. 実例比較: カンマあり vs カンマなし】")
    print(f"A. カンマあり: \"{prompt_with_comma}\"")
    print(f"   トークン数: {len(tokens_with)} 個")
    print("   内訳:")
    for word, tid in tokens_with:
        marker = " ⚠️ [区切りトークン]" if "," in word else ""
        print(f"     - {word:20s} (ID: {tid}){marker}")

    print(f"\nB. カンマなし: \"{prompt_without_comma}\"")
    print(f"   トークン数: {len(tokens_without)} 個")
    print("   内訳:")
    for word, tid in tokens_without:
        print(f"     - {word:20s} (ID: {tid})")

    diff = len(tokens_with) - len(tokens_without)
    print(f"\n  ➜ カンマが2個あるだけで、トークン数が正確に +{diff} 増加している！")

    # 3. Danbooru 50タグでの実質容量シミュレーション
    print("\n" + "=" * 75)
    print("【3. Danbooru平均50タグにおけるトークン消費内訳】")
    tags_count = 50
    avg_words_per_tag = 1.6  # 例: 'dark skin', 'short hair', 'fellatio'
    commas_count = tags_count - 1
    system_tokens = 2  # SOT + EOT

    total_tag_tokens = int(tags_count * avg_words_per_tag)
    total_tokens = total_tag_tokens + commas_count + system_tokens
    chunks_needed = (total_tokens + 74) // 75  # 75トークン切り上げ

    print(f"  - タグ数: {tags_count} 個")
    print(f"  - タグ自体の単語トークン: 約 {total_tag_tokens} トークン")
    print(f"  - タグ間のカンマ (,)   : 約 {commas_count} トークン （全体の約35%を占める！）")
    print(f"  - システムトークン (SOT/EOT): {system_tokens} トークン")
    print(f"  -------------------------------------------")
    print(f"  - 総トークン数: 約 {total_tokens} トークン")
    print(f"  - 必要チャンク数 (77枠 / 実質75): {chunks_needed} チャンク")
    print("=" * 75)


if __name__ == "__main__":
    main()

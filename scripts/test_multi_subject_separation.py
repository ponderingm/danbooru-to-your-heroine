"""
test_multi_subject_separation.py
================================
複数人構図（1girl 1boy / 2girls）におけるヒロインDNA吸収・属性汚染（Concept Bleeding）
を防ぐためのスロット分離＆モデル別構文（Illustrious BREAK vs Anima Qwenカプセル化）
のプロトタイプ検証スクリプト。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tag_classifier import classifier
from prompt_sorter import sorter

# 男性の身体・役割に関する典型キーワード
MALE_ATTR_KEYWORDS = {
    "1boy", "boy", "male", "man", "guy", "penis", "muscular male", "tall male",
    "facial hair", "beard", "mustache", "short black hair", "short hair, black hair"
}


def separate_multi_subject_tags(
    raw_tags: List[str],
    heroine_dna_tags: List[str],
) -> Dict[str, Any]:
    """
    複数人構図において、タグを「ヒロイン属性」「パートナー属性」「共通アクション・環境」へ分離する
    """
    slot_map = classifier.classify_tags(raw_tags, fallback_llm=False)
    
    # 複数人判定（1boy または 2girls 等が存在するか）
    is_multi_person = any(t.lower() in ("1boy", "2girls", "multiple girls", "hetero", "couple") for t in raw_tags)
    has_male = any("boy" in t.lower() or "male" in t.lower() for t in raw_tags)

    female_dna_slots = {}
    male_slots = []
    common_meta_slots = []
    common_action_slots = []
    common_env_slots = []
    unknown_slots = []

    # 1. ヒロインDNAをスロット登録
    heroine_slot_map = classifier.classify_tags(heroine_dna_tags, fallback_llm=False)
    for ht in heroine_dna_tags:
        h_slot = heroine_slot_map.get(ht.lower(), "character_dna.body.marks")
        female_dna_slots[h_slot] = ht

    # 2. 元絵タグの振り分け
    for t in raw_tags:
        clean_t = t.strip()
        if not clean_t:
            continue
        low_t = clean_t.lower()
        slot = slot_map.get(low_t, "unknown")
        parent = slot.split(".")[0]

        # 男性固有タグの検出
        if any(mk in low_t for mk in ["boy", "male", "penis", "muscular", "tall"]):
            male_slots.append(clean_t)
            continue

        # 元絵の女性身体特徴（ヒロインDNAのスロットと競合するもの）はパージ
        if slot in female_dna_slots:
            continue
        if parent == "character_dna":
            # ヒロイン未定義の身体特徴であっても、元絵の固有DNA（金髪や巨乳等）はパージ
            continue

        if parent == "meta_quality":
            common_meta_slots.append(clean_t)
        elif parent in ("action_pose", "accessories", "costume"):
            common_action_slots.append(clean_t)
        elif parent == "environment":
            common_env_slots.append(clean_t)
        elif parent == "subject":
            if "girl" in low_t:
                pass # ヒロイン側で管理
            else:
                male_slots.append(clean_t)
        else:
            unknown_slots.append(clean_t)

    return {
        "is_multi_person": is_multi_person,
        "has_male": has_male,
        "female_dna_tags": list(female_dna_slots.values()),
        "male_tags": male_slots,
        "meta_tags": common_meta_slots,
        "action_costume_tags": common_action_slots,
        "env_tags": common_env_slots,
        "unknown_tags": unknown_slots,
    }


def build_illustrious_prompt(separated: Dict[str, Any]) -> str:
    """Illustrious向け（BREAK チャンク分離 ＆ 役割バインド自動昇格）プロンプト構築"""
    # 役割バインド自動昇格（dark skin ➜ dark-skinned female 等）
    promoted_female_dna = []
    for t in separated["female_dna_tags"]:
        if t.lower() == "dark skin":
            promoted_female_dna.append("dark-skinned female")
        elif t.lower() == "small breasts":
            promoted_female_dna.append("small breasts")
        else:
            promoted_female_dna.append(t)

    # チャンク1: 品質・メタ ＋ アクション・構図
    chunk1_tags = sorter.sort_tags(
        separated["meta_tags"] + ["1girl", "1boy", "hetero"] + separated["action_costume_tags"] + separated["env_tags"]
    )
    chunk1_str = ", ".join(chunk1_tags)

    # チャンク2: ヒロイン側DNA完全隔離
    chunk2_tags = sorter.sort_tags(promoted_female_dna)
    chunk2_str = ", ".join(chunk2_tags)

    # チャンク3: パートナー（男性側）完全隔離
    chunk3_tags = sorter.sort_tags(separated["male_tags"])
    chunk3_str = ", ".join(chunk3_tags)

    return f"{chunk1_str}, BREAK, 1girl, {chunk2_str}, BREAK, {chunk3_str}"


def build_anima_prompt(separated: Dict[str, Any], heroine_name: str = "") -> str:
    """Anima向け（Qwen LLM自然言語カプセル化 ＆ 前置詞バインド）プロンプト構築"""
    meta_str = ", ".join(sorter.sort_tags(separated["meta_tags"]))
    action_str = ", ".join(sorter.sort_tags(separated["action_costume_tags"]))
    env_str = ", ".join(sorter.sort_tags(separated["env_tags"]))

    female_dna_str = ", ".join(separated["female_dna_tags"])
    male_dna_str = ", ".join(separated["male_tags"])

    # Qwen向け前置詞カプセル化
    name_clause = f" ({heroine_name})" if heroine_name else ""
    female_clause = f"1girl{name_clause} with ({female_dna_str})"
    male_clause = f"1boy with ({male_dna_str})"

    parts = [meta_str, female_clause, male_clause, action_str, env_str]
    return ", ".join([p for p in parts if p.strip()])


def build_flat_baseline_prompt(separated: Dict[str, Any]) -> str:
    """従来のフラットなタグ羅列（ベースライン）"""
    all_tags = (
        separated["meta_tags"]
        + ["1girl", "1boy", "hetero"]
        + separated["female_dna_tags"]
        + separated["male_tags"]
        + separated["action_costume_tags"]
        + separated["env_tags"]
    )
    return ", ".join(sorter.sort_tags(all_tags))


def main():
    # 典型的なカップル・フェラチオのDanbooruタグ（元絵は金髪・巨乳・白肌の女性 ＋ 黒髪・筋肉質の男性）
    raw_danbooru_post_tags = [
        "score_9", "score_8", "score_7", "masterpiece", "best quality", "explicit", "highres",
        "1girl", "1boy", "hetero", "couple", "fellatio", "cum in mouth", "deepthroat",
        "blonde hair", "blue eyes", "pale skin", "large breasts",
        "short black hair", "muscular male", "tall male", "penis", "erection",
        "bedroom", "night", "bed", "dim lighting"
    ]

    # ユーザー設定からヒロインDNAを安全にロード
    try:
        from danbooru_to_heroine import get_heroine_dna
        heroine_cfg = get_heroine_dna("")
        heroine_name = heroine_cfg.get("name", "")
        heroine_dna = (
            heroine_cfg.get("identity_tags", [])
            + heroine_cfg.get("face_tags", [])
            + heroine_cfg.get("body_tags", [])
        )
    except Exception:
        heroine_name = "example heroine"
        heroine_dna = ["1girl", "brown hair", "short hair", "dark skin", "small breasts", "red eyes"]

    print("=== [テスト検証: 複数人(1girl + 1boy)構図の属性分離] ===")
    print("\n【元絵のDanbooru投稿タグ】:")
    print(" ", ", ".join(raw_danbooru_post_tags))

    print(f"\n【換装ヒロイン ({heroine_name})】:")
    print(" ", ", ".join(heroine_dna))

    separated = separate_multi_subject_tags(raw_danbooru_post_tags, heroine_dna)

    print("\n--- [スロット分離結果] ---")
    print(" 👩 ヒロイン側DNAスロット:", separated["female_dna_tags"])
    print(" 👨 パートナー(男性)スロット:", separated["male_tags"])
    print(" 🎬 共通アクション・構図:", separated["action_costume_tags"])
    print(" 🌃 環境・背景:", separated["env_tags"])

    print("\n" + "=" * 60)
    print("パターン 1: 従来のフラット方式（比較対象: 属性汚染が起きるベースライン）")
    print("=" * 60)
    print(build_flat_baseline_prompt(separated))

    print("\n" + "=" * 60)
    print("パターン 2: Illustrious向け（BREAK構文 物理隔離 ＆ 役割バインド自動昇格）")
    print("=" * 60)
    print(build_illustrious_prompt(separated))

    print("\n" + "=" * 60)
    print("パターン 3: Anima向け（Qwen自然言語カプセル化 ＆ 前置詞バインド）")
    print("=" * 60)
    print(build_anima_prompt(separated))


if __name__ == "__main__":
    main()

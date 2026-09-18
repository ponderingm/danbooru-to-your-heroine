"""
multi_subject_adapter.py
========================
複数人構図（1girl 1boy / 2girls 等）におけるヒロインDNA吸収・属性汚染（Concept Bleeding）
を防止するための主語分離＆モデル別構文（Illustrious BREAK vs Anima Qwenカプセル化）アダプタ。
"""

import re
from typing import Any, Dict, List, Set, Tuple

from prompt_sorter import sorter
from tag_classifier import classifier

# 複数人（ヘテロ・カップル・複数人数）を判定するキーワード群
MULTI_PERSON_KEYWORDS: Set[str] = {
    "1boy", "2girls", "3girls", "multiple girls", "multiple boys",
    "hetero", "couple", "group sex", "gangbang", "threesome",
    "fellatio", "cunnilingus", "paizuri", "anal", "oral", "penetration", "sex"
}

# 男性の身体・役割に関する典型キーワード群
MALE_ATTR_KEYWORDS: Set[str] = {
    "1boy", "boy", "male", "man", "guy", "penis", "muscular male", "tall male",
    "facial hair", "beard", "mustache", "short black hair", "short hair, black hair",
    "erection", "ejaculation", "condom", "male focus"
}

# 複数人構図プロンプト戦略モード
MULTI_MODE_CAPSULE = "capsule"          # C: カプセル完全隔離 (BREAK / 1girl with (...))
MULTI_MODE_FLAT = "flat"                # A: フラット配置・自然分散 (v2ライク)
MULTI_MODE_SHARED_COSTUME = "shared_costume"  # B: 衣装タグ共有注入 (ヒロインにも服を着せる)
VALID_MULTI_MODES: Set[str] = {MULTI_MODE_CAPSULE, MULTI_MODE_FLAT, MULTI_MODE_SHARED_COSTUME}

# 着衣時にヒロインDNAから抑制する露出・日焼け系タグ
CLOTHED_SUPPRESS_DNA_TAGS: Set[str] = {
    "one-piece tan", "bikini tan", "tanlines", "tan lines"
}


def is_multi_subject(tags: List[str]) -> bool:
    """プロンプトまたはタグリストに複数人（特に1girl + 1boyなど）が含まれるかを判定する"""
    for t in tags:
        low = t.replace("_", " ").lower().strip()
        if low in MULTI_PERSON_KEYWORDS:
            return True
        if "boy" in low or "male" in low:
            return True
    return False


def separate_multi_subject_tags(
    raw_tags: List[str],
    heroine_dna_tags: List[str],
) -> Dict[str, Any]:
    """
    複数人構図において、タグを「ヒロイン属性」「パートナー属性」「共通アクション・構図」「衣装」「環境」へ分離する
    """
    clean_raw = [t.replace("_", " ").strip() for t in raw_tags if t.strip()]
    clean_dna = [t.replace("_", " ").strip() for t in heroine_dna_tags if t.strip()]

    slot_map = classifier.classify_tags(clean_raw, fallback_llm=False)
    heroine_slot_map = classifier.classify_tags(clean_dna, fallback_llm=False)

    female_dna_slots: Dict[str, str] = {}
    male_slots: List[str] = []
    common_meta_slots: List[str] = []
    costume_slots: List[str] = []
    common_action_slots: List[str] = []
    common_env_slots: List[str] = []
    unknown_slots: List[str] = []

    # 1. ヒロインDNAをスロット登録
    for ht in clean_dna:
        h_slot = heroine_slot_map.get(ht.lower(), "character_dna.body.marks")
        female_dna_slots[h_slot] = ht

    # 2. 元絵タグの振り分け
    for t in clean_raw:
        low_t = t.lower()
        slot = slot_map.get(low_t, "unknown")
        parent = slot.split(".")[0]

        # 男性特有の属性判定
        if any(kw in low_t for kw in MALE_ATTR_KEYWORDS):
            male_slots.append(t)
            continue

        # 品質・メタ
        if parent == "meta_quality":
            common_meta_slots.append(t)
            continue

        # 人数・主体
        if parent == "subject":
            if any(k in low_t for k in ("2girls", "3girls", "multiple girls", "multiple boys")):
                common_meta_slots.append(t)
            elif "boy" in low_t or "male" in low_t:
                male_slots.append(t)
            elif "girl" in low_t or "female" in low_t:
                female_dna_slots.setdefault("subject.gender", t)
            else:
                common_meta_slots.append(t)
            continue

        # 衣装・装飾
        if parent in ("costume", "accessories"):
            costume_slots.append(t)
            common_action_slots.append(t)
            continue

        # 身体・顔・髪・アクション・ポーズ・構図
        if parent in ("character_dna", "action_pose"):
            common_action_slots.append(t)
            continue

        # 環境・背景
        if parent == "environment":
            common_env_slots.append(t)
            continue

        unknown_slots.append(t)

    return {
        "meta_tags": sorter.sort_tags(common_meta_slots),
        "female_dna_tags": list(female_dna_slots.values()),
        "male_tags": sorter.sort_tags(male_slots),
        "costume_tags": sorter.sort_tags(costume_slots),
        "action_costume_tags": sorter.sort_tags(common_action_slots),
        "env_tags": sorter.sort_tags(common_env_slots),
        "unknown_tags": sorter.sort_tags(unknown_slots),
    }


def build_illustrious_multi_prompt(
    separated: Dict[str, Any],
    mode: str = MULTI_MODE_CAPSULE,
) -> str:
    """
    Illustrious / SDXL向け複数人プロンプト構築:
    - "capsule" (C: デフォルト): BREAKによるチャンク物理隔離
    - "flat" (A: v2風): BREAKを使わずセマンティック黄金順でフラット配置
    - "shared_costume" (B: 衣装共有): ヒロイン側チャンクにも衣装タグを共有注入し、日焼け跡等の露出タグを抑制
    """
    # 役割バインド自動昇格（例: dark skin ➜ dark-skinned female）
    promoted_female_dna = []
    for t in separated["female_dna_tags"]:
        low = t.lower()
        if low == "dark skin":
            promoted_female_dna.append("dark-skinned female")
        elif low == "pale skin":
            promoted_female_dna.append("pale-skinned female")
        elif low == "tanned":
            promoted_female_dna.append("tanned female")
        else:
            promoted_female_dna.append(t)

    has_male = bool(separated["male_tags"]) or any(
        any(k in t.lower() for k in ("1boy", "2boys", "multiple boys", "hetero", "yaoi"))
        for t in separated["meta_tags"]
    )

    # 1. Mode A: flat (v2風フラット配置)
    if mode == MULTI_MODE_FLAT:
        flat_tags = (
            separated["meta_tags"]
            + [t for t in promoted_female_dna if t.lower() != "1girl"]
            + (["1girl"] if "1girl" not in separated["meta_tags"] else [])
            + separated["action_costume_tags"]
            + separated["env_tags"]
            + separated["unknown_tags"]
        )
        if has_male:
            flat_tags += [t for t in separated["male_tags"] if t.lower() != "1boy"] + (["1boy"] if "1boy" not in separated["meta_tags"] else [])
        sorted_flat = sorter.sort_tags(flat_tags, model="illustrious")
        return ", ".join(sorted_flat)

    # 2. Mode B: shared_costume (衣装共有)
    if mode == MULTI_MODE_SHARED_COSTUME:
        costume_tags = separated.get("costume_tags", [])
        filtered_dna = [t for t in promoted_female_dna if t.lower() not in CLOTHED_SUPPRESS_DNA_TAGS] if costume_tags else promoted_female_dna
        chunk2_tags = [t for t in sorter.sort_tags(filtered_dna + costume_tags) if t.lower() != "1girl"]
    else:
        # Mode C: capsule (通常カプセル完全隔離)
        chunk2_tags = [t for t in sorter.sort_tags(promoted_female_dna) if t.lower() != "1girl"]

    # チャンク1: 品質・メタ ＋ アクション・構図・環境
    gender_meta = ["1girl", "1boy", "hetero"] if has_male else []
    chunk1_tags = sorter.sort_tags(
        separated["meta_tags"]
        + [t for t in gender_meta if t not in separated["meta_tags"]]
        + separated["action_costume_tags"]
        + separated["env_tags"]
        + separated["unknown_tags"]
    )
    chunk1_str = ", ".join(chunk1_tags)

    chunk2_str = ", ".join(["1girl"] + chunk2_tags)

    # チャンク3: パートナー（男性側）完全隔離（男性が存在する場合のみ）
    chunk3_str = ""
    if has_male:
        chunk3_tags = [t for t in sorter.sort_tags(separated["male_tags"]) if t.lower() != "1boy"]
        chunk3_str = ", ".join(["1boy"] + chunk3_tags) if chunk3_tags or "1boy" in [t.lower() for t in separated["male_tags"]] else "1boy"

    parts = [chunk1_str]
    if chunk2_str:
        parts.append(f"BREAK, {chunk2_str}")
    if chunk3_str:
        parts.append(f"BREAK, {chunk3_str}")

    return ", ".join(parts)


def build_anima_multi_prompt(
    separated: Dict[str, Any],
    heroine_name: str = "",
    mode: str = MULTI_MODE_CAPSULE,
) -> str:
    """
    Anima (Qwen LLM) 向け複数人プロンプト構築:
    - "capsule" (C: デフォルト): 自然言語構文による前置詞カプセル化 (1girl (heroine) with (...))
    - "flat" (A: v2風): カプセル化を行わずセマンティック黄金順でフラット配置
    - "shared_costume" (B: 衣装共有): ヒロインカプセル内にも衣装タグを共有注入し、日焼け跡等の露出タグを抑制
    """
    has_male = bool(separated["male_tags"]) or any(
        any(k in t.lower() for k in ("1boy", "2boys", "multiple boys", "hetero", "yaoi"))
        for t in separated["meta_tags"]
    )

    name_clause = f" ({heroine_name})" if heroine_name else ""

    # 1. Mode A: flat (v2風フラット配置)
    if mode == MULTI_MODE_FLAT:
        flat_tags = (
            separated["meta_tags"]
            + (["1girl" + name_clause] if "1girl" not in separated["meta_tags"] else [])
            + [t for t in separated["female_dna_tags"] if t.lower() != "1girl"]
            + separated["action_costume_tags"]
            + separated["env_tags"]
            + separated["unknown_tags"]
        )
        if has_male:
            flat_tags += [t for t in separated["male_tags"] if t.lower() != "1boy"] + (["1boy"] if "1boy" not in separated["meta_tags"] else [])
        sorted_flat = sorter.sort_tags(flat_tags, model="anima")
        return ", ".join(sorted_flat)

    # 2. Mode B: shared_costume (衣装共有)
    if mode == MULTI_MODE_SHARED_COSTUME:
        costume_tags = separated.get("costume_tags", [])
        filtered_dna = [
            t for t in separated["female_dna_tags"]
            if t.lower() not in CLOTHED_SUPPRESS_DNA_TAGS and t.lower() != "1girl"
        ] if costume_tags else [t for t in separated["female_dna_tags"] if t.lower() != "1girl"]
        female_dna_clean = sorter.sort_tags(filtered_dna + costume_tags, model="anima")
    else:
        # Mode C: capsule (通常カプセル完全隔離)
        female_dna_clean = [t for t in sorter.sort_tags(separated["female_dna_tags"], model="anima") if t.lower() != "1girl"]

    meta_str = ", ".join(sorter.sort_tags(separated["meta_tags"]))
    action_str = ", ".join(sorter.sort_tags(separated["action_costume_tags"]))
    env_str = ", ".join(sorter.sort_tags(separated["env_tags"]))
    unknown_str = ", ".join(sorter.sort_tags(separated["unknown_tags"]))

    female_dna_str = ", ".join(female_dna_clean)
    female_clause = f"1girl{name_clause} with ({female_dna_str})" if female_dna_str else f"1girl{name_clause}"

    male_clause = ""
    if has_male:
        male_dna_clean = [t for t in sorter.sort_tags(separated["male_tags"]) if t.lower() != "1boy"]
        male_dna_str = ", ".join(male_dna_clean)
        male_clause = f"1boy with ({male_dna_str})" if male_dna_str else "1boy"

    parts = [meta_str, female_clause, male_clause, action_str, env_str, unknown_str]
    return ", ".join([p for p in parts if p.strip()])

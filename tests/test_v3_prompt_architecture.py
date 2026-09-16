"""
test_v3_prompt_architecture.py
==============================
v3 プロンプト構造化アーキテクチャの自動テストスイート:
1. ソロ構図の黄金順ソート（75トークン内主要DNA集約）
2. 複数人構図（Illustrious BREAKチャンク物理隔離）
3. 複数人構図（Anima Qwen前置詞カプセル化）
4. BREAKタグの重複排除除外動作
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from danbooru_to_heroine import build_prompt
from model_adapter import adapt_prompt, _dedupe_tags
from multi_subject_adapter import is_multi_subject, separate_multi_subject_tags


def test_solo_prompt_golden_sorting():
    """ソロ構図で品質 -> 主体 -> ヒロインDNA -> 衣装 -> 表情 -> ポーズ -> 背景 の順に整列するか"""
    identity_tags = ["1girl", "dark skin", "short hair", "small breasts"]
    situation_tags = ["masterpiece", "bedroom", "bikini", "smile", "lying on bed"]
    
    prompt = build_prompt(identity_tags, situation_tags, model_type="illustrious")
    tags = [t.strip() for t in prompt.split(",") if t.strip()]

    # 1girl が先頭寄りに存在すること
    assert "1girl" in tags[:5]
    # ヒロインDNA（dark skin / small breasts）が背景（bedroom）より前に配置されていること
    idx_skin = tags.index("dark skin")
    idx_bedroom = tags.index("bedroom")
    assert idx_skin < idx_bedroom


def test_multi_subject_detection():
    """複数人構図の判定が正しく機能するか"""
    assert is_multi_subject(["1girl", "1boy", "couple"]) is True
    assert is_multi_subject(["fellatio", "bed"]) is True
    assert is_multi_subject(["1girl", "solo", "sitting"]) is False


def test_illustrious_break_separation():
    """Illustrious向けBREAK物理隔離構文が3チャンクで正しく生成されるか"""
    identity_tags = ["1girl", "dark skin", "small breasts"]
    situation_tags = ["masterpiece", "1boy", "tall male", "penis", "fellatio", "bedroom"]

    prompt = build_prompt(identity_tags, situation_tags, model_type="illustrious")
    chunks = prompt.split("BREAK")

    assert len(chunks) == 3
    # Chunk 1: 共通構図・アクション
    assert "fellatio" in chunks[0]
    assert "bedroom" in chunks[0]
    # Chunk 2: ヒロインDNA（dark-skinned femaleへ役割昇格）
    assert "dark-skinned female" in chunks[1]
    assert "small breasts" in chunks[1]
    assert "penis" not in chunks[1]
    # Chunk 3: 男性側
    assert "tall male" in chunks[2]
    assert "penis" in chunks[2]
    assert "dark-skinned female" not in chunks[2]


def test_anima_qwen_capsulation():
    """Anima向け前置詞カプセル化構文が正しく生成されるか"""
    identity_tags = ["1girl", "dark skin", "small breasts"]
    situation_tags = ["masterpiece", "1boy", "tall male", "penis", "fellatio", "bedroom"]

    prompt = build_prompt(identity_tags, situation_tags, model_type="anima", heroine_name="Example")
    assert "1girl (Example) with (" in prompt
    assert "1boy with (" in prompt
    assert "fellatio" in prompt


def test_break_preservation_in_model_adapter():
    """_dedupe_tags で BREAK が重複排除されず全て維持されるか"""
    raw = "masterpiece, 1girl, BREAK, 1girl, brown hair, BREAK, 1boy, black hair"
    deduped = _dedupe_tags(raw)
    assert deduped.count("BREAK") == 2


def test_slot_driven_mutation():
    """元絵の髪色・瞳・肌・胸タグがヒロインDNAのスロットにより自動置換されるか"""
    from danbooru_to_heroine import mutate_tags_to_heroine, get_heroine_dna

    fake_post = {
        "tag_string_general": "blonde_hair blue_eyes pale_skin large_breasts bed smile",
        "tag_string_character": "original_character",
        "tag_string_copyright": "",
        "tag_string_artist": "",
        "tag_string_meta": "",
    }

    res = mutate_tags_to_heroine(fake_post, heroine="")
    identity_tags, situation_tags, removed_tags = res[0], res[1], res[2]

    # 元絵の blonde hair, blue eyes, pale skin, large breasts が置換除去されていること
    assert "blonde hair" in removed_tags
    assert "blue eyes" in removed_tags
    assert "pale skin" in removed_tags
    assert "large breasts" in removed_tags

    # 競合しないシチュエーション（bed, smile）は保持されていること
    assert "bed" in situation_tags
    assert "smile" in situation_tags

    # ヒロインDNA（brown hair, twintails, dark skin, small breasts）が注入されていること
    joined_identity = " ".join(identity_tags)
    assert "dark skin" in joined_identity
    assert "small breasts" in joined_identity
    assert "brown hair" in joined_identity


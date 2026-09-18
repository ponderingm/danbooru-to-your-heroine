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


def test_female_only_multi_subject():
    """2girls / yuri 等の女子ペア構図で 1boy が絶対に含まれないか"""
    identity_tags = ["1girl", "dark skin", "small breasts"]
    situation_tags = ["masterpiece", "2girls", "yuri", "straddling", "uniform", "bedroom"]

    # Illustrious
    ill_prompt = build_prompt(identity_tags, situation_tags, model_type="illustrious")
    assert "1boy" not in ill_prompt
    assert "hetero" not in ill_prompt
    assert "2girls" in ill_prompt

    # Anima
    anima_prompt = build_prompt(identity_tags, situation_tags, model_type="anima", heroine_name="Yukikaze")
    assert "1boy" not in anima_prompt
    assert "hetero" not in anima_prompt
    assert "2girls" in anima_prompt
    assert "1girl (Yukikaze)" in anima_prompt


def test_multi_mode_strategies():
    """複数人構図戦略の全モード (capsule / flat / shared_costume) の挙動検証"""
    identity_tags = ["1girl", "dark skin", "small breasts", "one-piece tan"]
    situation_tags = ["masterpiece", "2girls", "yuri", "school uniform", "pleated skirt", "bedroom"]

    # 1. Mode C (capsule / デフォルト)
    c_ill = build_prompt(identity_tags, situation_tags, model_type="illustrious", multi_mode="capsule")
    assert "BREAK" in c_ill
    # チャンク2のヒロインDNAカプセルには衣装タグが入っていないこと
    chunks_c = c_ill.split("BREAK")
    assert "school uniform" not in chunks_c[1]

    c_anima = build_prompt(identity_tags, situation_tags, model_type="anima", heroine_name="Yukikaze", multi_mode="capsule")
    assert "1girl (Yukikaze) with (" in c_anima
    # カプセル内に school uniform は入っていないこと
    capsule_part = c_anima.split("with (")[1].split(")")[0]
    assert "school uniform" not in capsule_part

    # 2. Mode A (flat / v2風フラット配置)
    a_ill = build_prompt(identity_tags, situation_tags, model_type="illustrious", multi_mode="flat")
    assert "BREAK" not in a_ill
    assert "2girls" in a_ill
    assert "dark-skinned female" in a_ill
    assert "school uniform" in a_ill

    a_anima = build_prompt(identity_tags, situation_tags, model_type="anima", heroine_name="Yukikaze", multi_mode="flat")
    assert "with (" not in a_anima
    assert "2girls" in a_anima
    assert "dark skin" in a_anima
    assert "school uniform" in a_anima

    # 3. Mode B (shared_costume / 衣装共有注入)
    b_ill = build_prompt(identity_tags, situation_tags, model_type="illustrious", multi_mode="shared_costume")
    assert "BREAK" in b_ill
    chunks_b = b_ill.split("BREAK")
    # ヒロインチャンクに school uniform が注入されていること
    assert "school uniform" in chunks_b[1]
    # 着衣により露出バイアスの強い one-piece tan が抑制されていること
    assert "one-piece tan" not in chunks_b[1]

    b_anima = build_prompt(identity_tags, situation_tags, model_type="anima", heroine_name="Yukikaze", multi_mode="shared_costume")
    assert "1girl (Yukikaze) with (" in b_anima
    capsule_b = b_anima.split("with (")[1].split(")")[0]
    assert "school uniform" in capsule_b
    assert "one-piece tan" not in capsule_b


def test_normalize_heroine_v3_schema():
    """v2形式のフラットデータがv3の7大スロット階層スキーマへ自動正規化されるか"""
    from config import normalize_heroine_v3_schema

    legacy_data = {
        "name": "テストヒロイン",
        "identity_tags": ["heroine_chan", "sample_series \\(series\\)"],
        "face_tags": ["blonde hair", "twintails", "blue eyes"],
        "breasts_tags": ["small breasts"],
        "skin_tags": ["pale skin"],
        "body_other_tags": ["slender"],
        "costume_tags": ["sailor uniform", "pleated skirt"],
        "override_rules": {
            "breasts": "strict",
            "skin": "strict",
            "costume": "source",
            "multi_mode": "shared_costume"
        }
    }

    norm = normalize_heroine_v3_schema(legacy_data)
    assert norm["name"] == "テストヒロイン"
    assert norm["identity"]["character"] == "heroine_chan"
    assert norm["identity"]["series"] == "sample_series \\(series\\)"
    assert norm["dna"]["hair"]["color"] == "blonde hair"
    assert norm["dna"]["hair"]["style"] == "twintails"
    assert norm["dna"]["face"]["eyes"] == "blue eyes"
    assert norm["dna"]["body"]["skin"] == "pale skin"
    assert norm["dna"]["body"]["breasts"] == "small breasts"
    assert norm["dna"]["body"]["build"] == "slender"
    assert norm["override_rules"]["multi_mode"] == "shared_costume"
    assert "default" in norm["costume"]


def test_manifest_structured_fields(monkeypatch):
    """/convert 時に identity_tags, situation_tags, removed_tags, slots が正しく返却されるか"""
    import server
    from server import _convert, ConvertRequest
    from site_adapters.base import UnifiedPost

    fake_post = UnifiedPost(
        post_id="999999",
        source_site="danbooru",
        url="https://danbooru.donmai.us/posts/999999",
        general_tags=["blonde_hair", "blue_eyes", "smile", "bedroom", "bikini"],
        character_tags=[],
        artist_tags=[],
        copyright_tags=[],
        meta_tags=["highres"],
        all_tags=["blonde_hair", "blue_eyes", "smile", "bedroom", "bikini", "highres"]
    )

    # fetch_post をモックして fake_post を返却
    monkeypatch.setattr(server, "fetch_post", lambda url, **kwargs: fake_post)

    req = ConvertRequest(
        url="https://danbooru.donmai.us/posts/999999",
        heroine="yukikaze",
        multi_mode="capsule"
    )

    post, heroine, prompt, model, extras = _convert(req)
    assert "identity_tags" in extras
    assert "situation_tags" in extras
    assert "removed_tags" in extras
    assert "slots" in extras
    assert "multi_mode" in extras

    # スロット辞書に bedroom や smile が分類されていること
    assert any("environment" in s for s in extras["slots"].values())
    # 除去タグに元絵の blonde hair や blue eyes が含まれていること
    assert "blonde hair" in extras["removed_tags"]





"""
danbooru_to_heroine.py
=======================
DanbooruのURLからタグを収集し、キャラクター特性を config.py で定義した
任意のヒロインに書き換えたStable Diffusionプロンプトを生成するスクリプト。

ヒロインの定義（identity_tags/body_tags等）は config.py の HEROINES を参照。
新しいヒロインを追加・編集したい場合は config.py を編集すること。

Usage:
    uv run python danbooru_to_heroine.py <danbooru_url>
    uv run python danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345
    uv run python danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --heroine example_heroine
"""

import re
import sys
import json
import argparse
from typing import Union, Dict, Any
import requests

import config
from site_adapters import resolve_adapter, fetch_unified_post, UnifiedPost
from prompt_sorter import sorter
from tag_classifier import classifier
from multi_subject_adapter import (
    is_multi_subject,
    separate_multi_subject_tags,
    build_illustrious_multi_prompt,
    build_anima_multi_prompt,
)

# ─────────────────────────────────────────────
# 共通ルール・タグ分類（すべて rules/default_rules.yaml および config.py 由来）
# ─────────────────────────────────────────────
CHARACTER_IDENTITY_BLACKLIST = getattr(config, "CHARACTER_IDENTITY_BLACKLIST", {})
META_TAG_BLACKLIST = getattr(config, "META_TAG_BLACKLIST", set())
QUALITY_TAGS = getattr(config, "QUALITY_TAGS", set())
BREAST_TAGS = getattr(config, "BREAST_TAGS", set())
SKIN_TAGS = getattr(config, "SKIN_TAGS", set())
CENSORING_BLACKLIST = getattr(config, "CENSORING_BLACKLIST", set())

# ヒロインDNA置換時にも絶対に誤消去してはならない一般身体部位・露出・メイク・装飾タグ
GENERAL_BODY_PRESERVE_TAGS = {
    "thighs", "armpits", "collarbone", "bare shoulders", "bare arms", "bare legs",
    "cleavage", "sideboob", "underboob", "navel", "fingernails", "long fingernails",
    "nail polish", "pink nails", "black nails", "red nails",
    "makeup", "lipstick", "pink lips", "red lips", "eyeshadow", "body blush",
    "stomach", "midriff", "legs", "feet", "toes", "back", "butt", "ass",
    "groin", "pubic hair", "crotch",
}

# Danbooruのratingフィールド(g/s/q/e) → Illustrious系モデルが学習済みのratingタグ
RATING_TAG_MAP = {
    "g": "rating:general",
    "s": "rating:sensitive",
    "q": "rating:questionable",
    "e": "rating:explicit",
}


def build_art_style_set() -> set:
    """config（default_rules.yaml + ユーザー設定）から画風タグ集合を取得する"""
    return getattr(config, "ART_STYLE_TAGS", set())


def get_art_style_presets() -> dict:
    """config（default_rules.yaml + ユーザー設定）から画風プリセット辞書を取得する"""
    return getattr(config, "ART_STYLE_PRESETS", {})


DANBOORU_API_BASE = "https://danbooru.donmai.us"


# ─────────────────────────────────────────────
# Danbooru API
# ─────────────────────────────────────────────

def extract_post_id(url: str) -> Union[int, str]:
    """URLまたはIDからpost IDを抽出する（Danbooru, Gelbooru, AIBooru, Civitai対応）"""
    adapter = resolve_adapter(url)
    pid = adapter.extract_post_id(url)
    return int(pid) if pid.isdigit() else pid


def fetch_post(post_id_or_url: Union[int, str], login: str = None, api_key: str = None) -> UnifiedPost:
    """URLまたはPost IDから統一投稿オブジェクト（UnifiedPost）を取得する"""
    url_str = str(post_id_or_url)
    if "gelbooru" in url_str.lower():
        user_id = getattr(config, "GELBOORU_USER_ID", None)
        g_key = getattr(config, "GELBOORU_API_KEY", None)
        return fetch_unified_post(url_str, user_id=user_id, api_key=g_key)
    elif "civitai" in url_str.lower():
        c_key = getattr(config, "CIVITAI_API_KEY", None)
        return fetch_unified_post(url_str, api_key=c_key)
    else:
        login = login or getattr(config, "DANBOORU_LOGIN", None)
        api_key = api_key or getattr(config, "DANBOORU_API_KEY", None)
        return fetch_unified_post(url_str, login=login, api_key=api_key)



# ─────────────────────────────────────────────
# タグ変換エンジン
# ─────────────────────────────────────────────

def build_blacklist_set() -> set:
    bl = set()
    attr_dict = getattr(config, "CHARACTER_IDENTITY_BLACKLIST", CHARACTER_IDENTITY_BLACKLIST)
    for tags in attr_dict.values():
        for t in tags:
            bl.add(t.lower())
    return bl


def build_purge_set() -> set:
    """config.EXTRA_PURGE_TAGSを正規化した集合として返す（未定義環境向けにgetattrでフォールバック）
    ここに含まれるタグはプロンプトから除去されるが、画像生成自体はスキップされない（例: フキダシ等）"""
    return {t.replace("_", " ").lower() for t in getattr(config, "EXTRA_PURGE_TAGS", set())}


def extract_heroine_slots(raw_dna: dict) -> Dict[str, str]:
    """
    新型ヒロイン定義 (v3 スロット構造化スキーマ) から {スロットパス: タグ名} の完全マッピングを展開する。
    """
    slots: Dict[str, str] = {}
    if not isinstance(raw_dna, dict):
        return slots

    # 1. アイデンティティ (subject / meta)
    ident = raw_dna.get("identity", {})
    if isinstance(ident, dict):
        if ident.get("character"):
            slots["subject.character"] = str(ident["character"])
        if ident.get("series"):
            slots["meta_quality.series"] = str(ident["series"])
        for extra in ident.get("extra", []):
            slots[f"subject.extra.{extra}"] = str(extra)

    # 2. ヒロインDNA (character_dna: hair / face / body)
    dna_block = raw_dna.get("dna", {})
    if isinstance(dna_block, dict):
        # 髪 (hair)
        hair = dna_block.get("hair", {})
        if isinstance(hair, dict):
            for k in ("color", "style", "feature"):
                if hair.get(k):
                    slots[f"character_dna.hair.{k}"] = str(hair[k])

        # 顔 (face)
        face = dna_block.get("face", {})
        if isinstance(face, dict):
            for k in ("eyes", "marks"):
                if face.get(k):
                    slots[f"character_dna.face.{k}"] = str(face[k])

        # 身体 (body)
        body = dna_block.get("body", {})
        if isinstance(body, dict):
            for k in ("skin", "breasts", "build", "marks"):
                if body.get(k):
                    slots[f"character_dna.body.{k}"] = str(body[k])

    # 3. 衣装 (costume)
    costume_block = raw_dna.get("costume", {})
    if isinstance(costume_block, dict):
        default_costume = costume_block.get("default", [])
        if isinstance(default_costume, list):
            for idx, c in enumerate(default_costume):
                slots[f"costume.default.{idx}"] = str(c)
        elif isinstance(default_costume, dict):
            for k, v in default_costume.items():
                if v:
                    slots[f"costume.{k}"] = str(v)

    return slots


def build_known_character_tags() -> set:
    """config.HEROINESの全identity + config.OTHER_KNOWN_CHARACTER_TAGSを統合した既知キャラタグ集合"""
    tags = set(config.OTHER_KNOWN_CHARACTER_TAGS)
    for raw in config.HEROINES.values():
        ident = raw.get("identity", {})
        if isinstance(ident, dict):
            for v in ident.values():
                if isinstance(v, str):
                    tags.add(v.replace("_", " ").lower())
                elif isinstance(v, list):
                    for x in v:
                        tags.add(str(x).replace("_", " ").lower())
    return tags


def get_heroine_dna(heroine: str) -> dict:
    """ヒロイン名からv3構造化スロットおよび各種属性リストを展開して返却する"""
    if heroine and heroine in config.HEROINES:
        raw = config.HEROINES[heroine]
    elif config.DEFAULT_HEROINE and config.DEFAULT_HEROINE in config.HEROINES:
        raw = config.HEROINES[config.DEFAULT_HEROINE]
    elif config.HEROINES:
        raw = next(iter(config.HEROINES.values()))
    else:
        raw = {}

    slots = extract_heroine_slots(raw)

    identity_tags = [v for k, v in slots.items() if k.startswith("subject.") or k.startswith("meta_quality.series")]
    face_tags = [v for k, v in slots.items() if k.startswith("character_dna.hair.") or k.startswith("character_dna.face.")]
    body_tags = [v for k, v in slots.items() if k.startswith("character_dna.body.")]
    costume_tags = [v for k, v in slots.items() if k.startswith("costume.")]

    return {
        "name": raw.get("name", heroine or "Unknown"),
        "raw": raw,
        "slots": slots,
        "identity_tags": identity_tags,
        "face_tags": face_tags,
        "body_tags": body_tags,
        "costume_tags": costume_tags,
        "override_rules": raw.get("override_rules", {}),
        "negative_tags": raw.get("negative_tags", []),
        "artist_tags": raw.get("artist_tags", []),
        "default_backend": raw.get("default_backend"),
    }


class MutatedTagsResult(tuple):
    """(identity_tags, situation_tags, removed_tags) の3要素タプルとして後方互換性を保ちつつ、
    extra_negative_tags などの追加メタデータを安全に保持するコンテナ"""
    def __new__(cls, identity_tags, situation_tags, removed_tags, extra_negative_tags=None):
        return super().__new__(cls, (identity_tags, situation_tags, removed_tags))

    def __init__(self, identity_tags, situation_tags, removed_tags, extra_negative_tags=None):
        self.identity_tags = identity_tags
        self.situation_tags = situation_tags
        self.removed_tags = removed_tags
        self.extra_negative_tags = extra_negative_tags or []


def build_heroine_negative_prompt(heroine: str, base_negative: str, extra_tags: list = None) -> str:
    """ヒロイン固有のnegative_tagsと旧default_negative_extra、およびスマート肌色ポリシー等からの追加タグをnegative promptへ追記する。"""
    dna = get_heroine_dna(heroine)
    extras = list(dna.get("negative_tags", []))
    legacy_extra = dna.get("default_negative_extra")
    if legacy_extra:
        extras.extend(tag.strip() for tag in legacy_extra.split(","))
    if extra_tags:
        extras.extend(extra_tags)

    if not extras:
        return base_negative

    parts = [p.strip() for p in base_negative.split(",") if p.strip()]
    seen = {p.replace("_", " ").lower() for p in parts}
    for tag in extras:
        normalized = tag.strip().replace("_", " ").lower()
        if normalized and normalized not in seen:
            parts.append(tag.strip())
            seen.add(normalized)
    return ", ".join(parts)


def mutate_tags_to_heroine(post: Union[UnifiedPost, dict], heroine: str = None,
                            include_artist: bool = False, artist_mode: str = None,
                            custom_artist: str = None, override_rules: dict = None):
    """
    artist_mode: "keep"(元投稿のartistタグを使う、無ければdna.artist_tagsへフォールバック) /
                 "override"(元投稿のartistタグは無視し、常にdna.artist_tagsを使う) /
                 "none"(artistタグを完全除去)。省略時はinclude_artistから決める(True→keep, False→none)
    custom_artist: 指定時はartist_modeより常に優先し、元投稿のartistタグを除去した上でこの文字列を
                   そのままartistタグとして使う（"artist:"省略時は自動で付与する）
    """
    if heroine is None:
        heroine = config.DEFAULT_HEROINE
    dna = get_heroine_dna(heroine)

    effective_rules = dict(dna.get("override_rules", {}))
    if override_rules:
        for k, v in override_rules.items():
            if v and v != "default":
                effective_rules[k] = v

    if artist_mode is None or artist_mode == "default":
        artist_mode = effective_rules.get("artist", "keep" if include_artist else "none")
    blacklist = build_blacklist_set()
    purge_set = build_purge_set()
    known_character_tags = build_known_character_tags()
    negative_tags = {t.replace("_", " ").lower() for t in dna.get("negative_tags", [])}

    if isinstance(post, UnifiedPost):
        general_tags = set(post.general_tags or post.all_tags)
        character_tags = set(post.character_tags)
        copyright_tags = set(post.copyright_tags)
        artist_tags = set(post.artist_tags)
        meta_tags = set(post.meta_tags)
    else:
        general_tags = set(post.get("tag_string_general", "").split())
        character_tags = set(post.get("tag_string_character", "").split())
        copyright_tags = set(post.get("tag_string_copyright", "").split())
        artist_tags = set(post.get("tag_string_artist", "").split())
        meta_tags = set(post.get("tag_string_meta", "").split())

    removed_tags = []
    situation_tags = []

    # キャラクタータグ → 全除去（ヒロインIDで置換）
    for tag in character_tags:
        removed_tags.append(tag.replace("_", " "))

    # 著作権タグ → config.SERIES_TAG_KEEP_KEYWORDSに合致するものだけ保持
    keep_keywords = [kw.lower() for kw in config.SERIES_TAG_KEEP_KEYWORDS]
    for tag in copyright_tags:
        tag_norm = tag.replace("_", " ").lower()
        if keep_keywords and any(kw in tag_norm for kw in keep_keywords):
            situation_tags.append(tag.replace("_", " "))
        else:
            removed_tags.append(tag.replace("_", " "))

    # アーティストタグ → custom_artist指定時は最優先、以後はartist_modeに応じて維持/上書き/無効化する
    if custom_artist and custom_artist.strip():
        for tag in artist_tags:
            removed_tags.append(f"artist:{tag.replace('_', ' ')}")
        custom_tag = custom_artist.strip()
        if not custom_tag.lower().startswith("artist:"):
            custom_tag = f"artist:{custom_tag}"
        situation_tags.append(custom_tag)
    elif artist_mode == "override":
        situation_tags.extend(dna.get("artist_tags", []))
        for tag in artist_tags:
            removed_tags.append(f"artist:{tag.replace('_', ' ')}")
    elif artist_mode == "keep":
        if artist_tags:
            for tag in artist_tags:
                situation_tags.append(f"artist:{tag.replace('_', ' ')}")
        else:
            situation_tags.extend(dna.get("artist_tags", []))
    else:  # "none"
        for tag in artist_tags:
            removed_tags.append(f"artist:{tag.replace('_', ' ')}")

    # メタタグ → 不要な投稿管理タグを除去して保持
    for tag in meta_tags:
        tag_norm = tag.replace("_", " ").lower()
        if tag_norm in blacklist:
            removed_tags.append(tag_norm)
            continue
        if tag_norm in META_TAG_BLACKLIST:
            removed_tags.append(tag_norm)
            continue
        if tag_norm in negative_tags:
            removed_tags.append(tag_norm)
            continue
        if tag_norm in purge_set:
            removed_tags.append(tag_norm)
            continue
        situation_tags.append(tag.replace("_", " "))

    # レーティングタグ → post側のrating値をIllustrious系のrating:xタグとしてそのまま保持
    if isinstance(post, UnifiedPost):
        raw_r = post.rating.lower()
        if raw_r.startswith("e"):
            rating_tag = "rating:explicit"
        elif raw_r.startswith("q"):
            rating_tag = "rating:questionable"
        elif raw_r.startswith("s"):
            rating_tag = "rating:sensitive"
        else:
            rating_tag = "rating:general"
    else:
        rating_code = post.get("rating")
        rating_tag = RATING_TAG_MAP.get(rating_code)
    if rating_tag:
        situation_tags.append(rating_tag)

    breasts_mode = effective_rules.get("breasts", "strict")
    skin_mode = effective_rules.get("skin", "strict")
    costume_mode = effective_rules.get("costume", "source")
    art_style_mode = effective_rules.get("art_style", "source")

    detected_source_breasts = set()
    detected_source_skin = set()
    detected_source_monster_skin = set()
    detected_source_human_skin = set()
    detected_source_style = set()

    skin_tags_set = getattr(config, "SKIN_TAGS", set())
    monster_skin_set = getattr(config, "MONSTER_SKIN_TAGS", set())
    human_skin_set = getattr(config, "HUMAN_SKIN_TAGS", set())
    dark_skin_set = getattr(config, "DARK_SKIN_TAGS", set())
    art_style_set = build_art_style_set()
    heroine_slots = dna.get("slots", {})
    clean_general = [t.replace("_", " ").lower().strip() for t in general_tags if t.strip()]
    tag_slots = classifier.classify_tags(clean_general, fallback_llm=False)

    # 一般タグ → ブラックリスト・パージタグ除去 → 構図・服装として保持
    for tag in general_tags:
        tag_norm = tag.replace("_", " ").lower()

        # 1. 優先除外判定（ネガティブ・ブロック・パージ・検閲ノイズ・別キャラ属性）
        if tag_norm in negative_tags:
            removed_tags.append(tag_norm)
            continue

        if tag_norm in blacklist:
            removed_tags.append(tag_norm)
            continue

        if tag_norm in purge_set:
            removed_tags.append(tag_norm)
            continue

        if tag_norm in CENSORING_BLACKLIST:
            removed_tags.append(tag_norm)
            continue

        if tag_norm in known_character_tags:
            removed_tags.append(tag_norm)
            continue

        # 2. 画風判定（オーバーライドルール: source = 元絵維持, それ以外は元絵画風を全パージして指定画風へ転換）
        if tag_norm in art_style_set:
            if art_style_mode == "source":
                situation_tags.append(tag.replace("_", " "))
                detected_source_style.add(tag_norm)
                continue
            else:
                removed_tags.append(tag_norm)
                continue

        # 3. 胸サイズ判定（オーバーライドルール: strict = ヒロイン固定, source = 元絵維持）
        if tag_norm in BREAST_TAGS:
            if breasts_mode == "source":
                situation_tags.append(tag.replace("_", " "))
                detected_source_breasts.add(tag_norm)
                continue
            else:  # "strict" or default
                removed_tags.append(tag_norm)
                continue

        # 4. 肌色判定（スマート肌色ポリシー: strict = ヒロイン固定, source = 元絵維持）
        if tag_norm in skin_tags_set or tag_norm in monster_skin_set:
            if skin_mode == "source":
                # モンスター肌（blue skin, slime girl等）なら元絵を優先維持
                if tag_norm in monster_skin_set:
                    situation_tags.append(tag.replace("_", " "))
                    detected_source_monster_skin.add(tag_norm)
                    detected_source_skin.add(tag_norm)
                    continue
                # 人間系肌（pale skin, fair skin等）なら、元絵はパージしてヒロインの褐色肌を適用
                elif tag_norm in human_skin_set:
                    removed_tags.append(tag_norm)
                    detected_source_human_skin.add(tag_norm)
                    continue
                else:
                    situation_tags.append(tag.replace("_", " "))
                    detected_source_skin.add(tag_norm)
                    continue
            else:
                removed_tags.append(tag_norm)
                continue

        # 5. v3 スロット駆動DNA置換
        # 元絵タグのスロットがヒロインDNAのスロットと競合する場合、自動的に元絵属性を除去・置換する
        slot = tag_slots.get(tag_norm)
        if slot and slot.startswith("character_dna."):
            # 一般身体部位・露出・メイク・装飾タグは保護（DNA置換の巻き添えにしない）
            if tag_norm not in GENERAL_BODY_PRESERVE_TAGS:
                # 男性側属性（short black hair, penis等）は誤消去しないよう保護
                if not any(kw in tag_norm for kw in ("boy", "male", "man", "penis", "beard")):
                    # 直接競合するDNAスロット（髪、胸、肌色、瞳色）のみ置換対象
                    slot_prefix = ".".join(slot.split(".")[:3])  # 例: character_dna.hair.color
                    if slot_prefix in (
                        "character_dna.hair.color",
                        "character_dna.hair.style",
                        "character_dna.hair.feature",
                        "character_dna.body.breasts",
                        "character_dna.body.skin",
                        "character_dna.face.eyes",
                    ):
                        if any(k.startswith(slot_prefix) for k in heroine_slots):
                            removed_tags.append(tag_norm)
                            continue

        situation_tags.append(tag.replace("_", " "))

    # ヒロインDNAの組み立て（顔・体・衣装の3大カテゴリ）
    face_tags = dna.get("face_tags", [])
    body_tags = list(dna.get("body_tags", []))
    costume_tags = dna.get("costume_tags", [])

    # 元絵の胸タグが維持(source)された場合、ヒロイン側の胸タグと二重にならないよう除外
    if detected_source_breasts:
        body_tags = [b for b in body_tags if b.replace("_", " ").lower() not in BREAST_TAGS]

    extra_negative_tags = []
    # スマート肌色ポリシー適用:
    if skin_mode == "source":
        if detected_source_monster_skin:
            # モンスター肌（青肌スライム等）検出時:
            # 1. ヒロイン側の褐色系タグをプロンプトから完全除去（モンスター肌で上書き）
            body_tags = [
                b for b in body_tags
                if b.replace("_", " ").lower() not in skin_tags_set and b.replace("_", " ").lower() not in dark_skin_set
            ]
            # 2. キャラタグのバイアスで顔が褐色になるのを防ぐため、褐色タグをネガティブへ自動注入！
            extra_negative_tags.extend(["dark skin", "dark-skinned female", "tan", "tanlines", "brown skin"])
        else:
            # 人間系肌（pale skin等）または肌タグなし時:
            # 元絵が人間ならヒロイン本来の褐色肌（body_tags）をそのまま適用！
            pass
    elif detected_source_skin:
        body_tags = [b for b in body_tags if b.replace("_", " ").lower() not in skin_tags_set]

    # 衣装モード判定
    active_costumes = []
    if costume_mode in ("heroine", "mix"):
        active_costumes = costume_tags

    # 画風オーバーライドによるタグ注入
    if art_style_mode and art_style_mode not in ("source", "default"):
        presets = get_art_style_presets()
        injected = presets.get(art_style_mode)
        if injected:
            situation_tags.extend(injected)
        elif art_style_mode not in ("color", "clean", "none"):
            situation_tags.append(art_style_mode.replace("_", " "))

    identity_tags = dna.get("identity_tags", []) + face_tags + body_tags + active_costumes
    return MutatedTagsResult(identity_tags, situation_tags, removed_tags, extra_negative_tags=extra_negative_tags)



def escape_tag_parentheses(tag: str) -> str:
    """Danbooruタグ等の未エスケープ丸括弧を \\( \\) にエスケープする"""
    tag = re.sub(r'(?<!\\)\(', r'\(', tag)
    tag = re.sub(r'(?<!\\)\)', r'\)', tag)
    return tag


def build_prompt(
    identity_tags: list,
    situation_tags: list,
    quality_prefix: list = None,
    model_type: str = "illustrious",
    heroine_name: str = "",
) -> str:
    if quality_prefix is None:
        quality_prefix = ["masterpiece", "best quality", "highly detailed"]

    purge_set = build_purge_set()
    filtered_situation = [t for t in situation_tags if t.replace("_", " ").lower() not in purge_set]

    # 1. 複数人構図判定（1girl 1boy / 2girls 等）
    if is_multi_subject(filtered_situation):
        separated = separate_multi_subject_tags(raw_tags=filtered_situation, heroine_dna_tags=identity_tags)
        if "anima" in model_type.lower():
            return build_anima_multi_prompt(separated, heroine_name=heroine_name)
        else:
            return build_illustrious_multi_prompt(separated)

    # 2. ソロ構図: 黄金順ソート（75トークン内に主要ヒロインDNAを集約）
    quality_in_situation = [t for t in filtered_situation if t.lower() in QUALITY_TAGS]
    rest_situation = [t for t in filtered_situation if t.lower() not in QUALITY_TAGS]

    all_quality = quality_prefix[:]
    for t in quality_in_situation:
        if t not in all_quality:
            all_quality.append(t)

    # セマンティックスロット順（黄金順）に最適ソート
    sorted_tags = sorter.sort_tags(all_quality + identity_tags + rest_situation, model=model_type)

    seen = set()
    deduped = []
    for p in sorted_tags:
        escaped_p = escape_tag_parentheses(p)
        key = escaped_p.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(escaped_p)

    return ", ".join(deduped)


def mutate_raw_prompt_to_heroine(raw_prompt: str, heroine: str = None, extra_ignore_tags: list = None) -> str:
    """生プロンプト（メタデータ）のキャラ属性をヒロインDNAに置換し、シチュエーション構文を抽出・再構成する"""
    if not raw_prompt:
        return ""
    if heroine is None:
        heroine = config.DEFAULT_HEROINE
    dna = get_heroine_dna(heroine)
    blacklist = build_blacklist_set()
    purge_set = build_purge_set()
    known_character_tags = build_known_character_tags()
    if extra_ignore_tags:
        for t in extra_ignore_tags:
            known_character_tags.add(t.replace("_", " ").lower())
    negative_tags = {t.replace("_", " ").lower() for t in dna.get("negative_tags", [])}

    cleaned_situation = []
    seen = set()
    for part in raw_prompt.split(","):
        t = part.strip()
        if not t:
            continue
        core = re.sub(r"^[\(\[\{]+|[\)\]\}]+$", "", t)
        core = re.sub(r":\d+(\.\d+)?$", "", core).strip()
        norm = core.replace("_", " ").lower()

        if norm in blacklist or norm in purge_set or norm in CENSORING_BLACKLIST:
            continue
        if norm in known_character_tags or norm in negative_tags:
            continue
        if norm not in seen:
            cleaned_situation.append(core.replace("_", " "))
            seen.add(norm)

    face_tags = dna.get("face_tags", [])
    body_tags = dna.get("body_tags", [])
    costume_tags = dna.get("costume_tags", [])
    identity_tags = list(dna.get("identity_tags", [])) + face_tags + body_tags + costume_tags
    return build_prompt(identity_tags, cleaned_situation)



def build_hybrid_prompt(booru_prompt: str, raw_prompt_heroine: str) -> str:
    """Booruタグから構築したプロンプトと、生プロンプト置換版をマージ（重複排除）してハイブリッド化する"""
    if not raw_prompt_heroine:
        return booru_prompt
    if not booru_prompt:
        return raw_prompt_heroine

    parts = [p.strip() for p in booru_prompt.split(",") if p.strip()]
    seen = {p.lower() for p in parts}

    for raw_part in raw_prompt_heroine.split(","):
        p = raw_part.strip()
        if p and p.lower() not in seen:
            parts.append(p)
            seen.add(p.lower())
    return ", ".join(parts)



# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def run(url: str, heroine: str = None, login: str = None,
        api_key: str = None, verbose: bool = False,
        include_artist: bool = False, artist_mode: str = None,
        custom_artist: str = None) -> str:
    if heroine is None:
        heroine = config.DEFAULT_HEROINE
    heroine_name = get_heroine_dna(heroine)["name"]
    print(f"\n⚡ Danbooru → {heroine_name} プロンプト変換", file=sys.stderr)
    print(f"  URL: {url}", file=sys.stderr)

    post_id = extract_post_id(url)
    print(f"  Post ID: {post_id}", file=sys.stderr)

    print(f"  Danbooru API にアクセス中...", file=sys.stderr)
    post = fetch_post(post_id, login=login, api_key=api_key)

    all_tags = post.get("tag_string", "").split()
    n_char = len(post.get("tag_string_character", "").split())
    n_gen = len(post.get("tag_string_general", "").split())
    n_copy = len(post.get("tag_string_copyright", "").split())
    n_art = len(post.get("tag_string_artist", "").split())
    n_meta = len(post.get("tag_string_meta", "").split())
    print(f"  取得タグ数: {len(all_tags)} "
          f"(キャラ:{n_char} 一般:{n_gen} 著作権:{n_copy} アーティスト:{n_art} メタ:{n_meta})",
          file=sys.stderr)

    if verbose:
        char_tags = post.get("tag_string_character", "")
        print(f"\n--- 元キャラタグ ---\n  {char_tags}", file=sys.stderr)
        general_preview = post.get("tag_string_general", "")[:400]
        print(f"\n--- 元 general タグ (先頭400文字) ---\n  {general_preview}...", file=sys.stderr)

    identity_tags, situation_tags, removed_tags = mutate_tags_to_heroine(
        post, heroine=heroine, include_artist=include_artist, artist_mode=artist_mode,
        custom_artist=custom_artist,
    )

    if verbose:
        print(f"\n--- 除去タグ ({len(removed_tags)}件) ---", file=sys.stderr)
        print(f"  {', '.join(removed_tags[:60])}", file=sys.stderr)
        print(f"\n--- 追加 Identity タグ ---", file=sys.stderr)
        print(f"  {', '.join(identity_tags)}", file=sys.stderr)

    prompt = build_prompt(identity_tags, situation_tags)
    return prompt


def main():
    parser = argparse.ArgumentParser(
        description="⚡ Danbooru URL → お好みのヒロイン Stable Diffusion プロンプト変換ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", help="Danbooru の投稿 URL")
    parser.add_argument(
        "--heroine", "-H",
        choices=list(config.HEROINES.keys()),
        default=config.DEFAULT_HEROINE,
        help=f"変換先ヒロイン (デフォルト: {config.DEFAULT_HEROINE}) [{', '.join(config.HEROINES.keys())}]",
    )
    parser.add_argument("--login", "-l", default=None, help="Danbooru ログイン名（任意）")
    parser.add_argument("--api-key", "-k", default=None, help="Danbooru API キー（任意）")
    parser.add_argument("--include-artist", action="store_true", help="artist:タグをプロンプトに含める（デフォルトは除外。--artist-mode指定時は無視される）")
    parser.add_argument("--artist-mode", choices=["keep", "override", "none"], default=None,
                        help="画風(artistタグ)の扱い: keep=元投稿優先(無ければヒロインのartist_tags) / "
                             "override=常にヒロインのartist_tagsを使う / none=完全除去（省略時は--include-artistから決定）")
    parser.add_argument("--custom-artist", default=None,
                        help="artistタグを自由記述で指定する（指定時は--artist-modeより優先。'artist:'省略可）")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログを表示する")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON 形式で出力する")

    args = parser.parse_args()

    try:
        prompt = run(
            url=args.url,
            heroine=args.heroine,
            login=args.login,
            api_key=args.api_key,
            verbose=args.verbose,
            include_artist=args.include_artist,
            artist_mode=args.artist_mode,
            custom_artist=args.custom_artist,
        )

        if args.output_json:
            print(json.dumps({"url": args.url, "heroine": args.heroine, "prompt": prompt},
                             ensure_ascii=False, indent=2))
        else:
            heroine_name = get_heroine_dna(args.heroine)["name"]
            print(f"\n{'=' * 60}")
            print(f"⚡ {heroine_name} プロンプト")
            print("=" * 60)
            print(prompt)
            print("=" * 60)

    except requests.HTTPError as e:
        print(f"\n[ERROR] Danbooru API エラー: {e}", file=sys.stderr)
        if hasattr(e, "response"):
            if e.response.status_code == 403:
                print("  → 認証が必要な投稿かも。--login と --api-key を指定してみなさいよ", file=sys.stderr)
            elif e.response.status_code == 404:
                print("  → 投稿が見つからなかったわ。URLを確認して", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 予期せぬエラー: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

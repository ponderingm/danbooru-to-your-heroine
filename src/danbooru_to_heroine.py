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
    uv run python danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --heroine rinko
"""

import re
import sys
import json
import argparse
from typing import Union, Dict, Any
import requests

import config
from site_adapters import resolve_adapter, fetch_unified_post, UnifiedPost

# ─────────────────────────────────────────────
# 除去すべき「元キャラ固有タグ」パターン（属性カテゴリはヒロインに依らず共通）
# ─────────────────────────────────────────────
CHARACTER_IDENTITY_BLACKLIST = {
    "skin": [
        "light skin", "fair skin", "pale skin", "white skin",
        "tan skin", "brown skin", "dark skin",
        "dark-skinned female", "dark-skinned male",
    ],
    "breasts": [
        "flat chest", "small breasts", "medium breasts", "large breasts",
        "huge breasts", "gigantic breasts", "enormous breasts",
        "big breasts", "massive breasts", "petite",
    ],
    "hair_color": [
        "blonde hair", "brown hair", "red hair", "orange hair",
        "purple hair", "green hair", "blue hair", "white hair",
        "silver hair", "pink hair", "grey hair", "gray hair",
        "black hair", "light brown hair", "dark brown hair",
        "multicolored hair", "streaked hair", "gradient hair",
    ],
    "hair_style": [
        "long hair", "short hair", "medium hair", "very long hair",
        "ponytail", "twintails", "twin tails", "braid", "braids",
        "side ponytail", "double bun", "bun", "hair bun",
        "bob cut", "pixie cut", "drill hair", "curly hair",
        "wavy hair", "straight hair", "ahoge",
        "low twintails", "high ponytail",
    ],
    "eye_color": [
        "blue eyes", "green eyes", "red eyes", "purple eyes",
        "brown eyes", "golden eyes", "yellow eyes", "silver eyes",
        "grey eyes", "gray eyes", "black eyes", "heterochromia",
        "pink eyes", "aqua eyes", "teal eyes",
    ],
    "eye_shape": [
        "tsurime", "tareme",
    ],
}

# 画にならない不要メタタグ（投稿管理用タグなど）
META_TAG_BLACKLIST = {
    "bad pixiv id", "bad id", "bad twitter id", "bad deviantart id",
    "bad nicoseiga id", "bad tumblr id", "bad source id",
    "translated", "translation request", "partial translation",
    "commentary", "commentary request", "commentary typo", "check commentary", "partial commentary",
    "personification", "character request", "artist request","photoshop (medium)"
    "duplicate", "revision", "resized", "non-web source", "third-party edit","third-party source","english commentary", 
}

QUALITY_TAGS = {
    "masterpiece", "best quality", "high quality", "ultra quality",
    "highly detailed", "detailed", "absurdres", "highres", "4k", "8k", "hdr",
}

BREAST_TAGS = {
    "flat chest", "small breasts", "medium breasts", "large breasts",
    "huge breasts", "gigantic breasts", "enormous breasts", "big breasts", "massive breasts", "petite",
}
LARGE_BREAST_FAMILY = {
    "large breasts", "huge breasts", "gigantic breasts", "enormous breasts", "big breasts", "massive breasts",
}
SMALL_BREAST_FAMILY = {
    "flat chest", "small breasts", "petite",
}


# モザイク等の検閲タグ（画像には映らない/生成時に不要なので除去）
CENSORING_BLACKLIST = {
    "censored", "mosaic censoring", "bar censor",
    "character censor", "steam censor", "smoke censor", "light censor",
    "heart censor", "novelty censor", "shadow censor",
    "sparkle censor",
    "artist name","copyright name","cover", "cover name","content rating","signature",
    "watermark","cover page","doujin cover",
    "speech bubble", "thought bubble", "sound effect","colored speech bubble",
    "character age",
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
    login = login or getattr(config, "DANBOORU_LOGIN", None)
    api_key = api_key or getattr(config, "DANBOORU_API_KEY", None)
    return fetch_unified_post(str(post_id_or_url), login=login, api_key=api_key)



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


def build_known_character_tags() -> set:
    """config.HEROINESの全identity_tags + config.OTHER_KNOWN_CHARACTER_TAGSを統合した既知キャラタグ集合"""
    tags = set(config.OTHER_KNOWN_CHARACTER_TAGS)
    for dna in config.HEROINES.values():
        for t in dna.get("identity_tags", []):
            tags.add(t.replace("_", " ").lower())
    return tags


def get_heroine_dna(heroine: str) -> dict:
    if heroine and heroine in config.HEROINES:
        return config.HEROINES[heroine]
    if config.DEFAULT_HEROINE and config.DEFAULT_HEROINE in config.HEROINES:
        return config.HEROINES[config.DEFAULT_HEROINE]
    if config.HEROINES:
        return next(iter(config.HEROINES.values()))
    return {
        "name": heroine or "Unknown",
        "identity_tags": [],
        "face_tags": [],
        "body_tags": [],
        "costume_tags": [],
        "override_rules": {},
        "negative_tags": [],
        "series_tags": [],
        "artist_tags": [],
    }


def build_heroine_negative_prompt(heroine: str, base_negative: str) -> str:
    """ヒロイン固有のnegative_tagsと旧default_negative_extraをnegative promptへ追記する。"""
    dna = get_heroine_dna(heroine)
    extras = list(dna.get("negative_tags", []))
    legacy_extra = dna.get("default_negative_extra")
    if legacy_extra:
        extras.extend(tag.strip() for tag in legacy_extra.split(","))

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
    detected_source_style = set()
    skin_tags_set = {"dark skin", "light skin", "pale skin", "fair skin", "white skin", "tan", "tanned", "sun tan", "one-piece tan"}
    art_style_set = build_art_style_set()

    # 一般タグ → ブラックリスト除去 → 構図・服装として保持
    for tag in general_tags:
        tag_norm = tag.replace("_", " ").lower()

        # 画風判定（オーバーライドルール: source = 元絵維持, それ以外は元絵画風を全パージして指定画風へ転換）
        if tag_norm in art_style_set:
            if art_style_mode == "source":
                situation_tags.append(tag.replace("_", " "))
                detected_source_style.add(tag_norm)
                continue
            else:
                removed_tags.append(tag_norm)
                continue

        # 胸サイズ判定（オーバーライドルール: strict = ヒロイン固定, source = 元絵維持）
        if tag_norm in BREAST_TAGS:
            if breasts_mode == "source":
                situation_tags.append(tag.replace("_", " "))
                detected_source_breasts.add(tag_norm)
                continue
            else:  # "strict" or default
                removed_tags.append(tag_norm)
                continue

        # 肌色判定（オーバーライドルール: strict = ヒロイン固定, source = 元絵維持）
        if tag_norm in skin_tags_set:
            if skin_mode == "source":
                situation_tags.append(tag.replace("_", " "))
                detected_source_skin.add(tag_norm)
                continue
            else:
                removed_tags.append(tag_norm)
                continue

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

        situation_tags.append(tag.replace("_", " "))

    # ヒロインDNAの組み立て（顔・体・衣装の3大カテゴリ）
    face_tags = dna.get("face_tags", [])
    body_tags = list(dna.get("body_tags", []))
    costume_tags = dna.get("costume_tags", [])

    # 元絵の胸タグが維持(source)された場合、ヒロイン側の胸タグと二重にならないよう除外
    if detected_source_breasts:
        body_tags = [b for b in body_tags if b.replace("_", " ").lower() not in BREAST_TAGS]

    # 元絵の肌色タグが維持(source)された場合、ヒロイン側の肌色タグを除外
    if detected_source_skin:
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
    return identity_tags, situation_tags, removed_tags



def build_prompt(identity_tags: list, situation_tags: list, quality_prefix: list = None) -> str:
    if quality_prefix is None:
        quality_prefix = ["masterpiece", "best quality", "highly detailed"]

    quality_in_situation = [t for t in situation_tags if t.lower() in QUALITY_TAGS]
    rest_situation = [t for t in situation_tags if t.lower() not in QUALITY_TAGS]

    all_quality = quality_prefix[:]
    for t in quality_in_situation:
        if t not in all_quality:
            all_quality.append(t)

    parts = all_quality + identity_tags + rest_situation

    seen = set()
    deduped = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(p)

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

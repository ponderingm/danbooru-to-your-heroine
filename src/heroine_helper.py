"""
heroine_helper.py
=================
Danbooru / Gelbooru から指定キャラクターの投稿群を取得し、
タグの出現頻度（採用率%）を統計解析して、ヒロインのアイデンティティ（身体特徴・衣装・作品・絵師・反意ネガティブ）
の初期設定を全自動サジェストするヘルパーモジュール。
"""

import re
import urllib.parse
from collections import Counter
from typing import Any, Dict, List, Optional
import requests
import config


def search_and_analyze_heroine(
    character_name: str,
    search_mode: str = "auto",  # "auto" | "official" | "popular" | "all"
    site: str = "danbooru",     # "danbooru" | "gelbooru"
    limit: int = 40,
) -> Dict[str, Any]:
    """
    指定キャラクター名でBooruを検索し、タグ頻度を分析してヒロイン設定候補を生成する。
    """
    clean_char = character_name.strip().replace(" ", "_").lower()
    if not clean_char:
        raise ValueError("キャラクター名を入力してください")

    posts = _fetch_character_posts(clean_char, search_mode, site, limit)
    total_posts = len(posts)
    if total_posts == 0:
        raise ValueError(f"{site} で '{clean_char}' に一致する投稿が見つかりませんでした")

    # タグ出現頻度を集計
    general_counts = Counter()
    char_counts = Counter()
    copy_counts = Counter()
    artist_counts = Counter()

    for p in posts:
        for t in p.get("general", []):
            general_counts[t.replace("_", " ").lower()] += 1
        for t in p.get("character", []):
            char_counts[t.replace("_", " ").lower()] += 1
        for t in p.get("copyright", []):
            copy_counts[t.replace("_", " ").lower()] += 1
        for t in p.get("artist", []):
            artist_counts[t.replace("_", " ").lower()] += 1

    # Baseルールの身体属性辞書（skin, breasts, hair_color, hair_style, eye_color等）
    base_attrs = getattr(config, "CHARACTER_IDENTITY_BLACKLIST", {})
    all_attr_tags = {}
    for category, tags in base_attrs.items():
        for t in tags:
            all_attr_tags[t.replace("_", " ").lower()] = category

    # 1. 顔（head/face）と身体（body）の分離判定
    face_categories = {"hair_color", "hair_style", "eye_color", "eye_shape"}
    body_categories = {"skin", "breasts"}

    face_candidates = []
    body_candidates = []
    for tag, count in general_counts.most_common():
        rate = round((count / total_posts) * 100, 1)
        if tag in all_attr_tags:
            cat = all_attr_tags[tag]
            item = {
                "tag": tag,
                "count": count,
                "rate": rate,
                "category": cat,
            }
            if cat in face_categories:
                face_candidates.append(item)
            elif cat in body_categories:
                body_candidates.append(item)

    # 2. 作品名候補 (series_tags)
    series_candidates = []
    for tag, count in copy_counts.most_common(5):
        rate = round((count / total_posts) * 100, 1)
        series_candidates.append({
            "tag": tag,
            "count": count,
            "rate": rate,
        })

    # 3. 代表絵師候補 (artist_tags)
    artist_candidates = []
    for tag, count in artist_counts.most_common(5):
        rate = round((count / total_posts) * 100, 1)
        artist_candidates.append({
            "tag": f"artist:{tag}",
            "count": count,
            "rate": rate,
        })

    # 4. 代表衣装・小物候補 (頻度25%以上の一般タグで、身体タグやメタタグ・品質タグでないもの)
    quality_tags = getattr(config, "QUALITY_TAGS", set())
    purge_tags = getattr(config, "EXTRA_PURGE_TAGS", set())
    costume_candidates = []
    ignored_generals = {"1girl", "solo", "looking at viewer", "blush", "smile", "open mouth", "closed mouth", "standing", "sitting", "multiple girls"}

    for tag, count in general_counts.most_common(50):
        rate = round((count / total_posts) * 100, 1)
        if rate < 20.0:
            continue
        if tag in all_attr_tags or tag in quality_tags or tag in purge_tags or tag in ignored_generals:
            continue
        costume_candidates.append({
            "tag": tag,
            "count": count,
            "rate": rate,
        })

    # 5. 対立・反意ネガティブタグ候補 (negative_tags)
    negative_candidates = []
    selected_body_tags = {b["tag"] for b in body_candidates[:6]}

    # 肌色
    if any("dark skin" in b or "tan" in b or "brown skin" in b for b in selected_body_tags):
        for opp in ["fair skin", "pale skin", "white skin", "light skin"]:
            if opp not in selected_body_tags:
                negative_candidates.append({"tag": opp, "reason": "褐色・日焼け肌と対立"})
    elif any("fair skin" in b or "pale skin" in b or "light skin" in b for b in selected_body_tags):
        for opp in ["dark skin", "tan", "brown skin"]:
            if opp not in selected_body_tags:
                negative_candidates.append({"tag": opp, "reason": "色白肌と対立"})

    # 胸
    is_small_chest = any("small breasts" in b or "flat chest" in b or "petite" in b for b in selected_body_tags)
    is_large_chest = any("large breasts" in b or "huge breasts" in b or "big breasts" in b or "gigantic breasts" in b for b in selected_body_tags)

    if is_small_chest:
        for opp in ["large breasts", "huge breasts", "gigantic breasts", "big breasts"]:
            if opp not in selected_body_tags:
                negative_candidates.append({"tag": opp, "reason": "貧乳・小胸と対立"})
    elif is_large_chest:
        for opp in ["small breasts", "flat chest", "petite"]:
            if opp not in selected_body_tags:
                negative_candidates.append({"tag": opp, "reason": "巨乳・豊満胸と対立"})

    # 6. オーバーライドルールの初期推奨判定
    suggested_override_rules = {
        "skin": "strict",
        "costume": "source",
    }
    if is_small_chest:
        suggested_override_rules["breasts"] = "strict"    # ユキカゼ等: 小胸は絶対に変化させない絶対遵守
    elif is_large_chest:
        suggested_override_rules["breasts"] = "flexible"  # 不知火等: large〜giganticまで柔軟に追従
    else:
        suggested_override_rules["breasts"] = "strict"

    # キャラクター自身のタグ
    char_display = clean_char.replace("_", " ")
    top_series = series_candidates[0]["tag"] if series_candidates else ""
    suggested_identity = [char_display]
    if top_series:
        series_esc = top_series.replace("(", "\\(").replace(")", "\\)")
        suggested_identity.append(series_esc)

    return {
        "character_name": char_display,
        "search_site": site,
        "total_posts_analyzed": total_posts,
        "suggested_identity_tags": suggested_identity,
        "suggested_face_tags": [f["tag"] for f in face_candidates[:6]],
        "suggested_body_tags": [b["tag"] for b in body_candidates[:6]],
        "suggested_costume_tags": [c["tag"] for c in costume_candidates[:6]],
        "suggested_series_tags": [s["tag"] for s in series_candidates[:2]],
        "suggested_override_rules": suggested_override_rules,
        "face_candidates": face_candidates[:12],
        "body_candidates": body_candidates[:12],
        "series_candidates": series_candidates,
        "artist_candidates": artist_candidates,
        "costume_candidates": costume_candidates[:12],
        "negative_candidates": negative_candidates,
    }



def _fetch_character_posts(character: str, search_mode: str, site: str, limit: int) -> List[Dict[str, List[str]]]:
    """サイトとモードに応じて投稿群を取得し、正規化リストとして返す"""
    if site == "danbooru":
        return _fetch_from_danbooru(character, search_mode, limit)
    elif site == "gelbooru":
        return _fetch_from_gelbooru(character, search_mode, limit)
    return _fetch_from_danbooru(character, search_mode, limit)


def _fetch_from_danbooru(character: str, search_mode: str, limit: int) -> List[Dict[str, List[str]]]:
    headers = {"User-Agent": "danbooru-to-your-heroine/2.0"}
    login = getattr(config, "DANBOORU_LOGIN", None)
    api_key = getattr(config, "DANBOORU_API_KEY", None)

    queries = []
    if search_mode == "official":
        queries = [f"{character} official_art"]
    elif search_mode == "popular":
        queries = [f"{character} 1girl solo order:score"]
    elif search_mode == "all":
        queries = [character]
    else:  # auto
        queries = [
            f"{character} official_art",
            f"{character} 1girl solo",
            character,
        ]

    for q in queries:
        params = {"tags": q, "limit": limit}
        if login and api_key:
            params["login"] = login
            params["api_key"] = api_key
        try:
            res = requests.get("https://danbooru.donmai.us/posts.json", params=params, headers=headers, timeout=12)
            if res.status_code == 200:
                posts = res.json()
                if isinstance(posts, list) and len(posts) >= 3:
                    return [
                        {
                            "general": p.get("tag_string_general", "").split(),
                            "character": p.get("tag_string_character", "").split(),
                            "copyright": p.get("tag_string_copyright", "").split(),
                            "artist": p.get("tag_string_artist", "").split(),
                        }
                        for p in posts
                        if isinstance(p, dict)
                    ]
        except Exception:
            continue

    return []


def _fetch_from_gelbooru(character: str, search_mode: str, limit: int) -> List[Dict[str, List[str]]]:
    user_id = getattr(config, "GELBOORU_USER_ID", None)
    api_key = getattr(config, "GELBOORU_API_KEY", None)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    queries = [f"{character} 1girl", character]
    for q in queries:
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={urllib.parse.quote(q)}&limit={limit}"
        if user_id and api_key:
            url += f"&user_id={user_id}&api_key={api_key}"
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200:
                data = res.json()
                posts = data.get("post", []) if isinstance(data, dict) else data
                if isinstance(posts, list) and len(posts) >= 3:
                    return [
                        {
                            "general": p.get("tags", "").split(),
                            "character": [character],
                            "copyright": [],
                            "artist": [],
                        }
                        for p in posts
                        if isinstance(p, dict)
                    ]
        except Exception:
            continue

    return []

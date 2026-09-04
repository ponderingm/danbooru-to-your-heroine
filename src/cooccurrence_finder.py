"""
cooccurrence_finder.py
======================
自然言語または複数タグの積集合（Gelbooru AND検索）から、
投稿群の共起ネットワークを統計解析し、
Danbooruのタグ共起継承を最大発揮させる「中心核ワード（起爆剤タグ）」を発見・抽出するモジュール。
"""

import re
import urllib.parse
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple
import requests
import config

# 共起分析で除外すべき自明・頻出メタタグ
COMMON_STOP_TAGS = {
    "1girl", "solo", "looking_at_viewer", "highres", "absurdres",
    "bad_anatomy", "bad_hands", "translation_request", "translated",
    "text", "watermark", "signature", "artist_name",
}


def fetch_gelbooru_intersection_posts(
    tags: List[str],
    limit: int = 40,
    rating: Optional[str] = None,
    sort: str = "score",
) -> List[Dict[str, Any]]:
    """
    Gelbooru の AND 検索（積集合）を用いて、複数条件に合致する母集団投稿を取得する。
    """
    query_parts = [t.strip().replace(" ", "_") for t in tags if t.strip()]
    if sort:
        query_parts.append(f"sort:{sort}")
    if rating:
        query_parts.append(f"rating:{rating}")
    
    query = " ".join(query_parts)
    encoded_query = urllib.parse.quote(query)
    
    user_id = getattr(config, "GELBOORU_USER_ID", None)
    api_key = getattr(config, "GELBOORU_API_KEY", None)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={encoded_query}&limit={limit}"
    if user_id and api_key:
        url += f"&user_id={user_id}&api_key={api_key}"
        
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    posts = data.get("post", []) if isinstance(data, dict) else data
    if isinstance(posts, list):
        return [p for p in posts if isinstance(p, dict)]
    return []


def analyze_cooccurrence_core(
    posts: List[Dict[str, Any]],
    input_tags: List[str],
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    母集団投稿のタグ共起頻度および関連度を解析し、
    共起の輪（xxxxx ring）の中心核となる「起爆剤タグ」候補を特定する。
    """
    input_tag_set = {t.strip().replace(" ", "_").lower() for t in input_tags if t.strip()}
    total_posts = len(posts)
    if total_posts == 0:
        return {
            "total_posts": 0,
            "core_candidates": [],
            "all_cooccurring_tags": [],
        }

    tag_counts = Counter()
    for p in posts:
        # Gelbooruのtagsフィールドはスペース区切り
        raw_tags = p.get("tags", "").split()
        for t in raw_tags:
            norm_t = t.strip().lower()
            if not norm_t:
                continue
            if norm_t in input_tag_set or norm_t in COMMON_STOP_TAGS:
                continue
            tag_counts[norm_t] += 1

    # 出現頻度（採用率%）と共起スコアの計算
    candidates = []
    for tag, count in tag_counts.most_common(50):
        ratio = round((count / total_posts) * 100, 1)
        # 短すぎるタグやノイズを除外
        if len(tag) <= 2:
            continue
        candidates.append({
            "tag": tag,
            "count": count,
            "frequency_percent": ratio,
        })

    return {
        "total_posts_analyzed": total_posts,
        "input_tags": list(input_tag_set),
        "core_candidates": candidates[:top_k],
    }


def find_cooccurrence_ring(
    tags: List[str],
    limit: int = 40,
    rating: Optional[str] = None,
    sort: str = "score",
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    ワンストップAPI: 複数タグのGelbooru積集合から共起の輪の中心を特定する。
    """
    posts = fetch_gelbooru_intersection_posts(tags=tags, limit=limit, rating=rating, sort=sort)
    analysis = analyze_cooccurrence_core(posts, input_tags=tags, top_k=top_k)
    return analysis

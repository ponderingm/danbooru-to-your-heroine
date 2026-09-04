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


def fetch_danbooru_tag_counts(tags: List[str]) -> Dict[str, int]:
    """
    Danbooru APIから複数タグのグローバル総登録件数（post_count）を一括取得する。
    登録件数が少ない（希少である）ほど高い情報量（特異性）を持つ。
    """
    if not tags:
        return {}
    
    headers = {"User-Agent": "danbooru-to-your-heroine/2.0"}
    login = getattr(config, "DANBOORU_LOGIN", None)
    api_key = getattr(config, "DANBOORU_API_KEY", None)
    
    # tags[name_comma] で最大100件まで一括問い合わせ可能
    tag_meta = {}
    chunk_size = 50
    for i in range(0, len(tags), chunk_size):
        chunk = tags[i:i + chunk_size]
        query_str = ",".join(chunk)
        params = {"search[name_comma]": query_str, "limit": len(chunk)}
        if login and api_key:
            params["login"] = login
            params["api_key"] = api_key
        try:
            resp = requests.get("https://danbooru.donmai.us/tags.json", params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        name = item.get("name")
                        count = item.get("post_count", 0)
                        cat = item.get("category", 0)
                        if name:
                            tag_meta[name] = {"post_count": count, "category": cat}
        except Exception:
            continue

    return tag_meta


def analyze_cooccurrence_core(
    posts: List[Dict[str, Any]],
    input_tags: List[str],
    top_k: int = 10,
    check_rarity: bool = True,
) -> Dict[str, Any]:
    """
    母集団投稿のタグ共起頻度および希少度（特異性）を解析し、
    共起の輪（xxxxx ring）の中心核となる「起爆剤タグ」候補を特定する。
    「登録件数が少ないニッチなタグほど美しい」という思想に基づき、
    母集団内での共起率 × 特異性（逆頻度IDF相当）でスコアリングする。
    """
    input_tag_set = {t.strip().replace(" ", "_").lower() for t in input_tags if t.strip()}
    total_posts = len(posts)
    if total_posts == 0:
        return {
            "total_posts": 0,
            "core_candidates": [],
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

    # 上位候補の抽出（出現回数が2回以上のものを対象）
    initial_candidates = []
    for tag, count in tag_counts.most_common(60):
        if count < 2:
            continue
        if len(tag) <= 2:
            continue
        initial_candidates.append((tag, count))

    # Danbooruでのグローバル登録件数（希少度）を取得
    rarity_map = {}
    if check_rarity and initial_candidates:
        candidate_tags = [t for t, _ in initial_candidates]
        rarity_map = fetch_danbooru_tag_counts(candidate_tags)

    scored_candidates = []
    # Danbooru全体総投稿数の目安スケール（約8,000,000）
    TOTAL_BOORU_SCALE = 8_000_000

    for tag, local_count in initial_candidates:
        meta = rarity_map.get(tag, {"post_count": 100_000, "category": 0})
        global_count = meta.get("post_count", 100_000)
        category = meta.get("category", 0)
        
        # カテゴリ分類: 0=一般, 1=絵師, 3=作品, 4=キャラクター, 5=メタ
        # 共起の核（シチュエーション・装飾・フェチ）としては一般タグ（0）を最優先する
        if category in (1, 3, 4, 5):
            continue

        local_ratio = local_count / total_posts
        
        # 特異性スコア: ローカル共起率 × IDF^1.5
        # グローバル件数が少ないタグ（例: 200件の labia_ring）ほどスコアが跳ね上がる
        import math
        idf_weight = max(1.0, math.log(TOTAL_BOORU_SCALE / max(10, global_count)))
        rarity_score = round(local_ratio * 100 * (idf_weight ** 1.5), 2)

        scored_candidates.append({
            "tag": tag,
            "local_count": local_count,
            "frequency_percent": round(local_ratio * 100, 1),
            "global_post_count": global_count,
            "category": category,
            "rarity_score": rarity_score,
        })

    # 特異性スコア順にソート（希少で美しい中心核タグが首位に来る）
    scored_candidates.sort(key=lambda x: x["rarity_score"], reverse=True)

    return {
        "total_posts_analyzed": total_posts,
        "input_tags": list(input_tag_set),
        "core_candidates": scored_candidates[:top_k],
    }


def find_cooccurrence_ring(
    tags: List[str],
    limit: int = 40,
    rating: Optional[str] = None,
    sort: str = "score",
    top_k: int = 5,
    check_rarity: bool = True,
) -> Dict[str, Any]:
    """
    ワンストップAPI: 複数タグのGelbooru積集合から、希少性の高い共起の輪の中心を特定する。
    """
    posts = fetch_gelbooru_intersection_posts(tags=tags, limit=limit, rating=rating, sort=sort)
    analysis = analyze_cooccurrence_core(posts, input_tags=tags, top_k=top_k, check_rarity=check_rarity)
    return analysis


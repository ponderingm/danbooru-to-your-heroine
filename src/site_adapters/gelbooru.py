"""
site_adapters/gelbooru.py
========================
Gelbooru (gelbooru.com) 用アダプタ
"""

import re
import requests
from .base import BaseSiteAdapter, UnifiedPost


class GelbooruAdapter(BaseSiteAdapter):
    SITE_NAME = "gelbooru"
    BASE_URL = "https://gelbooru.com"
    API_ENDPOINT = "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "gelbooru.com" in url

    @classmethod
    def extract_post_id(cls, url: str) -> str:
        # id=12345 または /posts/12345 等
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)
        match_slash = re.search(r"/(\d+)(?:[/?#]|$)", url)
        if match_slash:
            return match_slash.group(1)
        raise ValueError(f"GelbooruのURLからpost IDを抽出できなかったわ: {url}")

    def fetch_post(self, post_id: str, **kwargs) -> UnifiedPost:
        url = f"{self.API_ENDPOINT}&id={post_id}"
        headers = {"User-Agent": "danbooru-to-your-heroine/2.0"}
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Gelbooru API は {"post": [...]} または 直接リスト形式の場合がある
        posts = data.get("post") if isinstance(data, dict) else data
        if not posts:
            raise ValueError(f"Gelbooru投稿が見つからなかったわ (ID: {post_id})")
        post = posts[0] if isinstance(posts, list) else posts

        raw_tags = post.get("tags", "").strip()
        all_tags = [t for t in raw_tags.split() if t]

        raw_rating = str(post.get("rating", "general")).lower()
        if raw_rating.startswith("e"):
            rating = "explicit"
        elif raw_rating.startswith("q"):
            rating = "questionable"
        elif raw_rating.startswith("s"):
            rating = "sensitive"
        else:
            rating = "general"

        return UnifiedPost(
            post_id=str(post_id),
            source_site=self.SITE_NAME,
            url=f"{self.BASE_URL}/index.php?page=post&s=view&id={post_id}",
            width=int(post.get("width") or 832),
            height=int(post.get("height") or 1216),
            rating=rating,
            character_tags=[],     # Gelbooruはtagsにまとまっているためall_tagsへ
            general_tags=all_tags,
            artist_tags=[],
            copyright_tags=[],
            meta_tags=[],
            all_tags=all_tags,
            raw_prompt=None,
            raw_negative=None,
            generation_meta=post,
        )

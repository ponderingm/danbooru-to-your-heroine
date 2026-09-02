"""
site_adapters/danbooru.py
========================
Danbooru (danbooru.donmai.us) 用アダプタ
"""

import re
import requests
from .base import BaseSiteAdapter, UnifiedPost


class DanbooruAdapter(BaseSiteAdapter):
    SITE_NAME = "danbooru"
    API_BASE = "https://danbooru.donmai.us"
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "danbooru.donmai.us" in url or (url.strip().isdigit() and not url.startswith("http"))

    @classmethod
    def extract_post_id(cls, url: str) -> str:
        match = re.search(r"/posts/(\d+)", url)
        if match:
            return match.group(1)
        if url.strip().isdigit():
            return url.strip()
        raise ValueError(f"DanbooruのURLからpost IDを抽出できなかったわ: {url}")

    def fetch_post(self, post_id: str, login: str = None, api_key: str = None, **kwargs) -> UnifiedPost:
        endpoint = f"{self.API_BASE}/posts/{post_id}.json"
        params = {}
        if login and api_key:
            params["login"] = login
            params["api_key"] = api_key
        headers = {"User-Agent": "danbooru-to-your-heroine/2.0"}
        
        resp = requests.get(endpoint, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        rating_map = {
            "g": "general",
            "s": "sensitive",
            "q": "questionable",
            "e": "explicit",
        }
        raw_rating = data.get("rating", "g")
        rating = rating_map.get(raw_rating, "general")
        
        char_tags = [t for t in data.get("tag_string_character", "").split() if t]
        gen_tags = [t for t in data.get("tag_string_general", "").split() if t]
        art_tags = [t for t in data.get("tag_string_artist", "").split() if t]
        cpy_tags = [t for t in data.get("tag_string_copyright", "").split() if t]
        meta_tags = [t for t in data.get("tag_string_meta", "").split() if t]
        all_tags = [t for t in data.get("tag_string", "").split() if t]
        
        return UnifiedPost(
            post_id=str(post_id),
            source_site=self.SITE_NAME,
            url=f"{self.API_BASE}/posts/{post_id}",
            width=int(data.get("image_width") or 832),
            height=int(data.get("image_height") or 1216),
            rating=rating,
            character_tags=char_tags,
            general_tags=gen_tags,
            artist_tags=art_tags,
            copyright_tags=cpy_tags,
            meta_tags=meta_tags,
            all_tags=all_tags,
            raw_prompt=None,
            raw_negative=None,
            generation_meta=data,
        )

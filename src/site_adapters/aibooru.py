"""
site_adapters/aibooru.py
=======================
AIBooru (aibooru.online) 用アダプタ（Danbooru互換API）
"""

import re
from .danbooru import DanbooruAdapter


class AIBooruAdapter(DanbooruAdapter):
    SITE_NAME = "aibooru"
    API_BASE = "https://aibooru.online"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "aibooru" in url.lower()

    @classmethod
    def extract_post_id(cls, url: str) -> str:
        match = re.search(r"/posts/(\d+)", url)
        if match:
            return match.group(1)
        match_digits = re.search(r"(\d+)", url)
        if match_digits:
            return match_digits.group(1)
        raise ValueError(f"AIBooruのURLからpost IDを抽出できなかったわ: {url}")


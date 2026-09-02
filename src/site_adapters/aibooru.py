"""
site_adapters/aibooru.py
=======================
AIBooru (aibooru.online) 用アダプタ（Danbooru互換API）
"""

from .danbooru import DanbooruAdapter


class AIBooruAdapter(DanbooruAdapter):
    SITE_NAME = "aibooru"
    API_BASE = "https://aibooru.online"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "aibooru.online" in url

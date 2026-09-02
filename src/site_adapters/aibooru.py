"""
site_adapters/aibooru.py
=======================
AIBooru (aibooru.online) 用アダプタ（Danbooru互換API）
"""

import re
from .base import UnifiedPost
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

    def fetch_post(self, post_id: str, **kwargs) -> "UnifiedPost":
        post = super().fetch_post(post_id, **kwargs)
        data = post.generation_meta or {}
        model_name = data.get("tag_string_model", "").strip()

        # 画像ファイルの先頭チャンクから生プロンプト（parameters）を抽出
        raw_prompt = None
        raw_negative = None
        file_url = data.get("file_url") or data.get("large_file_url")
        if file_url and file_url.endswith((".png", ".webp")):
            try:
                import requests
                headers = {"Range": "bytes=0-65535", "User-Agent": "danbooru-to-your-heroine/2.0"}
                res = requests.get(file_url, headers=headers, timeout=5)
                if res.status_code in (200, 206):
                    content = res.content
                    idx = content.find(b"parameters\x00")
                    if idx != -1:
                        text = content[idx + 11 : idx + 3000].decode("utf-8", errors="ignore")
                        if "Negative prompt:" in text:
                            p_part, n_part = text.split("Negative prompt:", 1)
                            raw_prompt = p_part.strip()
                            raw_negative = n_part.split("Steps:")[0].strip()
                        else:
                            raw_prompt = text.split("Steps:")[0].strip()
            except Exception as e:
                pass

        return UnifiedPost(
            post_id=post.post_id,
            source_site=self.SITE_NAME,
            url=post.url,
            width=post.width,
            height=post.height,
            rating=post.rating,
            character_tags=post.character_tags,
            general_tags=post.general_tags,
            artist_tags=post.artist_tags,
            copyright_tags=post.copyright_tags,
            meta_tags=post.meta_tags,
            all_tags=post.all_tags,
            raw_prompt=raw_prompt,
            raw_negative=raw_negative,
            generation_meta={
                **data,
                "detected_model": model_name,
            },
        )



"""
site_adapters/civitai.py
=======================
Civitai (civitai.com) 用アダプタ
"""

import re
import requests
from .base import BaseSiteAdapter, UnifiedPost


class CivitaiAdapter(BaseSiteAdapter):
    SITE_NAME = "civitai"
    BASE_URL = "https://civitai.com"
    API_ENDPOINT = "https://civitai.com/api/v1/images"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "civitai" in url.lower()

    @classmethod
    def extract_post_id(cls, url: str) -> str:
        # https://civitai.com/images/1234567
        match = re.search(r"/images/(\d+)", url)
        if match:
            return match.group(1)
        match_query = re.search(r"[?&]imageId=(\d+)", url)
        if match_query:
            return match_query.group(1)
        match_digits = re.search(r"(\d+)", url)
        if match_digits:
            return match_digits.group(1)
        raise ValueError(f"CivitaiのURLから画像IDを抽出できなかったわ: {url}")

    def fetch_post(self, post_id: str, api_key: str = None, **kwargs) -> UnifiedPost:
        import config
        api_key = api_key or getattr(config, "CIVITAI_API_KEY", None) or getattr(config, "USER_CONFIG", {}).get("civitai_api_key")

        # nsfw=X または nsfwLevel=31 で全NSFW画像を取得可能にする
        url = f"{self.API_ENDPOINT}?imageId={post_id}&nsfw=X"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key.strip()}"

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 401:
            raise ValueError(f"CivitaiのNSFW画像を取得するにはAPI Key（Personal Access Token）が必要よ！設定タブからCivitai API Keyを登録してね♪ (ID: {post_id})")
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            if not api_key:
                raise ValueError(f"Civitai画像情報が見つからなかったわ (ID: {post_id})。NSFW画像の場合は設定タブからCivitai API Key（無料）の登録が必要よ！")
            raise ValueError(f"Civitai画像情報が見つからなかったわ (ID: {post_id})")
        item = items[0]


        meta = item.get("meta") or {}
        raw_prompt = meta.get("prompt", "")
        raw_negative = meta.get("negativePrompt", "")

        # カンマ区切りのプロンプトからタグを抽出
        raw_tags = [t.strip().replace(" ", "_") for t in raw_prompt.split(",") if t.strip()]
        
        # NSFW判定
        nsfw_level = item.get("nsfwLevel", 1)
        if nsfw_level >= 16:
            rating = "explicit"
        elif nsfw_level >= 4:
            rating = "questionable"
        elif nsfw_level >= 2:
            rating = "sensitive"
        else:
            rating = "general"

        return UnifiedPost(
            post_id=str(post_id),
            source_site=self.SITE_NAME,
            url=f"{self.BASE_URL}/images/{post_id}",
            width=int(meta.get("width") or item.get("width") or 832),
            height=int(meta.get("height") or item.get("height") or 1216),
            rating=rating,
            character_tags=[],
            general_tags=raw_tags,
            artist_tags=[],
            copyright_tags=[],
            meta_tags=[],
            all_tags=raw_tags,
            raw_prompt=raw_prompt,
            raw_negative=raw_negative,
            generation_meta=item,
        )

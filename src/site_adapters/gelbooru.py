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
        return "gelbooru" in url.lower()

    @classmethod
    def extract_post_id(cls, url: str) -> str:
        # id=12345 または /posts/12345 等
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)
        match_slash = re.search(r"/(\d+)(?:[/?#]|$)", url)
        if match_slash:
            return match_slash.group(1)
        match_digits = re.search(r"(\d+)", url)
        if match_digits:
            return match_digits.group(1)
        raise ValueError(f"GelbooruのURLからpost IDを抽出できなかったわ: {url}")


    def fetch_post(self, post_id: str, user_id: str = None, api_key: str = None, **kwargs) -> UnifiedPost:
        user_id = user_id or kwargs.get("login")
        api_key = api_key or kwargs.get("api_key")

        # APIキーがある場合は公式APIを試行
        if user_id and api_key:
            url = f"{self.API_ENDPOINT}&id={post_id}&user_id={user_id}&api_key={api_key}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("post") if isinstance(data, dict) else data
                    if posts:
                        post = posts[0] if isinstance(posts, list) else posts
                        return self._build_post_from_api(post_id, post)
            except Exception:
                pass

        # APIキーがない、または401/エラーの場合は高精度HTMLスクレイピング・フォールバック
        return self._fetch_post_via_html(post_id)

    def _build_post_from_api(self, post_id: str, post: dict) -> UnifiedPost:
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
            character_tags=[],
            general_tags=all_tags,
            artist_tags=[],
            copyright_tags=[],
            meta_tags=[],
            all_tags=all_tags,
            raw_prompt=None,
            raw_negative=None,
            generation_meta=post,
        )

    def _fetch_post_via_html(self, post_id: str) -> UnifiedPost:
        """APIキー不要：Webページ（HTML）から全タグおよびカテゴリ属性を高精度に抽出する"""
        import urllib.parse
        url = f"{self.BASE_URL}/index.php?page=post&s=view&id={post_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"{self.BASE_URL}/",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # 1. 画像コンテナ（section.image-container）から基本情報を抽出
        width, height = 832, 1216
        rating = "general"
        container = re.search(r"<section[^>]+class=[\"'][^\"']*image-container[^\"']*[\"'][^>]*>", html)
        if container:
            tag_str = container.group(0)
            m_rating = re.search(r"data-rating=[\"']([^\"']+)[\"']", tag_str)
            if m_rating:
                r_val = m_rating.group(1).lower()
                rating = "explicit" if "explicit" in r_val else ("questionable" if "question" in r_val else ("sensitive" if "sensit" in r_val else "general"))
            m_w = re.search(r"data-width=[\"'](\d+)[\"']", tag_str)
            m_h = re.search(r"data-height=[\"'](\d+)[\"']", tag_str)
            if m_w and m_h:
                width, height = int(m_w.group(1)), int(m_h.group(1))

        # 2. li.tag-type-* からカテゴリ別タグを高精度抽出
        categories = {"character": [], "copyright": [], "artist": [], "metadata": [], "general": []}
        pattern = r"<li[^>]+class=[\"'][^\"']*tag-type-([a-z]+)[^\"']*[\"'][^>]*>.*?tags=([^\"'&]+)"
        for m in re.finditer(pattern, html, re.DOTALL):
            cat = m.group(1)
            raw_tag = urllib.parse.unquote(m.group(2)).strip()
            if raw_tag and raw_tag != "?" and cat in categories:
                categories[cat].append(raw_tag)

        # all_tags は全カテゴリの合算
        all_tags = (
            categories["character"]
            + categories["copyright"]
            + categories["artist"]
            + categories["general"]
            + categories["metadata"]
        )

        # 万が一カテゴリが取れなかった場合のフォールバック（data-tags）
        if not all_tags and container:
            m_tags = re.search(r"data-tags=[\"']([^\"']+)[\"']", container.group(0))
            if m_tags:
                all_tags = [t.strip() for t in m_tags.group(1).split() if t.strip()]
                categories["general"] = all_tags

        if not all_tags:
            raise ValueError(f"Gelbooruの投稿からタグを抽出できなかったわ (ID: {post_id})")

        return UnifiedPost(
            post_id=str(post_id),
            source_site=self.SITE_NAME,
            url=url,
            width=width,
            height=height,
            rating=rating,
            character_tags=categories["character"],
            general_tags=categories["general"],
            artist_tags=categories["artist"],
            copyright_tags=categories["copyright"],
            meta_tags=categories["metadata"],
            all_tags=all_tags,
            raw_prompt=None,
            raw_negative=None,
            generation_meta={"scraped_via_html": True},
        )


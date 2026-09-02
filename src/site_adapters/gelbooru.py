"""
site_adapters/gelbooru.py
========================
Gelbooru (gelbooru.com) 用アダプタ
"""

import re
import html
import urllib.parse
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
        """Gelbooruから高精度なUnifiedPostを取得する。
        Gelbooruの公式API(dapi)はタグカテゴリ(character/artist/copyright)を返さず全て一般タグ扱いにしてしまうため、
        キメラ化やパージ漏れを防ぐべく、カテゴリ分類が完璧なWebページ(HTML)スクレイピングを最優先(Primary)とする。
        万が一HTML取得に失敗した場合のみ、公式APIにフォールバックする。
        """
        # 1. 高精度HTMLスクレイピング（キャラ名・絵師名・作品名の分離が100%可能）
        try:
            return self._fetch_post_via_html(post_id)
        except Exception as e:
            pass

        # 2. HTMLが失敗した場合はAPIフォールバック
        user_id = user_id or kwargs.get("login")
        api_key = api_key or kwargs.get("api_key")
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
                        return self._build_post_from_api(post_id, post, user_id=user_id, api_key=api_key)
            except Exception:
                pass

        raise ValueError(f"Gelbooruからの投稿データ取得に失敗したわ (ID: {post_id})")

    def _build_post_from_api(self, post_id: str, post: dict, user_id: str = None, api_key: str = None) -> UnifiedPost:
        raw_tags = post.get("tags", "").strip()
        all_tags = [html.unescape(t) for t in raw_tags.split() if t]

        raw_rating = str(post.get("rating", "general")).lower()
        if raw_rating.startswith("e"):
            rating = "explicit"
        elif raw_rating.startswith("q"):
            rating = "questionable"
        elif raw_rating.startswith("s"):
            rating = "sensitive"
        else:
            rating = "general"

        # APIフォールバック時：タグAPI(s=tag)を叩いてカテゴリ分類を復元試行
        categories = {"character": [], "copyright": [], "artist": [], "metadata": [], "general": []}
        if all_tags and user_id and api_key:
            try:
                # 最大100タグまで一括問い合わせ
                batch_tags = "+".join(urllib.parse.quote(t) for t in all_tags[:100])
                tag_api_url = f"https://gelbooru.com/index.php?page=dapi&s=tag&q=index&json=1&names={batch_tags}&user_id={user_id}&api_key={api_key}"
                t_resp = requests.get(tag_api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if t_resp.status_code == 200:
                    t_data = t_resp.json()
                    t_items = t_data.get("tag", [])
                    if isinstance(t_items, list):
                        type_map = {item.get("name"): item.get("type") for item in t_items}
                        for t in all_tags:
                            t_type = type_map.get(t, 0)
                            if t_type == 4:  # character
                                categories["character"].append(t)
                            elif t_type == 1:  # artist
                                categories["artist"].append(t)
                            elif t_type == 3:  # copyright
                                categories["copyright"].append(t)
                            elif t_type == 5:  # metadata
                                categories["metadata"].append(t)
                            else:
                                categories["general"].append(t)
            except Exception:
                categories["general"] = all_tags
        else:
            categories["general"] = all_tags

        return UnifiedPost(
            post_id=str(post_id),
            source_site=self.SITE_NAME,
            url=f"{self.BASE_URL}/index.php?page=post&s=view&id={post_id}",
            width=int(post.get("width") or 832),
            height=int(post.get("height") or 1216),
            rating=rating,
            character_tags=categories["character"],
            general_tags=categories["general"] if categories["general"] else all_tags,
            artist_tags=categories["artist"],
            copyright_tags=categories["copyright"],
            meta_tags=categories["metadata"],
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
        html_content = resp.text

        # 1. 画像コンテナ（section.image-container）から基本情報を抽出
        width, height = 832, 1216
        rating = "general"
        container = re.search(r"<section[^>]+class=[\"'][^\"']*image-container[^\"']*[\"'][^>]*>", html_content)
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
        for m in re.finditer(pattern, html_content, re.DOTALL):
            cat = m.group(1)
            raw_tag = html.unescape(urllib.parse.unquote(m.group(2))).strip()
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


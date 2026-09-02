"""
site_adapters/__init__.py
========================
URLから適切なSiteAdapterを自動判定・インスタンス化するファクトリ。
"""

from typing import Tuple
from .base import BaseSiteAdapter, UnifiedPost
from .danbooru import DanbooruAdapter
from .gelbooru import GelbooruAdapter
from .aibooru import AIBooruAdapter
from .civitai import CivitaiAdapter

ADAPTER_CLASSES = [
    AIBooruAdapter,
    GelbooruAdapter,
    CivitaiAdapter,
    DanbooruAdapter,
]



def resolve_adapter(url_or_id: str) -> BaseSiteAdapter:
    """URLまたはIDから適切なアダプタインスタンスを返す"""
    url_str = str(url_or_id).strip()
    for cls in ADAPTER_CLASSES:
        if cls.can_handle(url_str):
            return cls()
    # デフォルトはDanbooruとして扱う
    return DanbooruAdapter()


def fetch_unified_post(url_or_id: str, **kwargs) -> UnifiedPost:
    """URLまたはIDを渡すだけで、自動判別してUnifiedPostを取得する総合関数"""
    adapter = resolve_adapter(url_or_id)
    post_id = adapter.extract_post_id(url_or_id)
    return adapter.fetch_post(post_id, **kwargs)

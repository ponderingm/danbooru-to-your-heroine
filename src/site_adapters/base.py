"""
site_adapters/base.py
====================
各イラスト・プロンプト投稿サイトのメタデータを統一的に扱うための基底クラスおよびデータ構造。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class UnifiedPost:
    """異なるサイト間で正規化された投稿メタデータ"""
    post_id: str
    source_site: str                  # "danbooru" | "gelbooru" | "aibooru" | "civitai"
    url: str
    width: int = 832
    height: int = 1216
    rating: str = "general"           # "general" | "sensitive" | "questionable" | "explicit"
    
    # カテゴリ別タグ（取得可能な場合）
    character_tags: List[str] = field(default_factory=list)
    general_tags: List[str] = field(default_factory=list)
    artist_tags: List[str] = field(default_factory=list)
    copyright_tags: List[str] = field(default_factory=list)
    meta_tags: List[str] = field(default_factory=list)
    
    # 全タグの統合リスト（スペース区切りやカンマ区切りの素のタグ）
    all_tags: List[str] = field(default_factory=list)
    
    # Civitai等の生成メタ情報（あれば）
    raw_prompt: Optional[str] = None
    raw_negative: Optional[str] = None
    generation_meta: Dict[str, Any] = field(default_factory=dict)


class BaseSiteAdapter:
    """各サイトのアダプタ基底クラス"""
    
    SITE_NAME: str = "base"
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        """指定されたURLがこのアダプタで処理可能かを判定する"""
        raise NotImplementedError
        
    @classmethod
    def extract_post_id(cls, url: str) -> str:
        """URLから投稿IDを抽出する"""
        raise NotImplementedError
        
    def fetch_post(self, post_id: str, **kwargs) -> UnifiedPost:
        """API等を通じて投稿メタデータを取得し、UnifiedPostを返す"""
        raise NotImplementedError

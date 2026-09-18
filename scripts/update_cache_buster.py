#!/usr/bin/env python3
"""
scripts/update_cache_buster.py
==============================
src/web/index.html 内の静的資産（app.js, style.css 等）のクエリパラメータ
（?v=YYYYMMDD_HHMM）を現在日時に自動更新する開発用スクリプト。
"""

import re
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT_DIR / "src" / "web" / "index.html"


def update_cache_busters() -> str:
    if not INDEX_HTML.exists():
        raise FileNotFoundError(f"File not found: {INDEX_HTML}")

    content = INDEX_HTML.read_text(encoding="utf-8")
    now_version = datetime.now().strftime("%Y%m%d_%H%M")

    # 正規表現で ?v=... パターンを現在日時に置換
    # 1) <script src="app.js?v=...">
    updated_content = re.sub(
        r'(\b(?:src|href)=["\'][^"\']+\.(?:js|css))\?v=[^"\']*([\'"])',
        rf"\g<1>?v={now_version}\g<2>",
        content,
    )

    if content == updated_content:
        print(f"ℹ️ No query parameter changes needed (or already up to date with {now_version}).")
    else:
        INDEX_HTML.write_text(updated_content, encoding="utf-8")
        print(f"✅ Cache-busting query params updated to: ?v={now_version}")

    return now_version


if __name__ == "__main__":
    update_cache_busters()

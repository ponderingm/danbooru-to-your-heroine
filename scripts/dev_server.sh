#!/usr/bin/env bash
# ==============================================================================
# Danbooru to Your Heroine - Local Development Server
# ==============================================================================
# 本番Dockerコンテナ（8899）と競合しないよう、デフォルトポート8898で起動します。
# ホスト上の src/web を直接配信するため、ファイルの保存・リロードだけで即座に変更が反映されます。
# ==============================================================================

set -euo pipefail

DEV_PORT="${PORT:-8898}"
DEV_HOST="${HOST:-0.0.0.0}"

echo "========================================================"
echo "🚀 Starting Local Dev Server on http://${DEV_HOST}:${DEV_PORT}"
echo "📁 Live Web Directory: $(pwd)/src/web"
echo "💡 Edit src/web/* files and refresh browser to test instantly."
echo "========================================================"

PORT="${DEV_PORT}" HOST="${DEV_HOST}" uv run python src/server.py

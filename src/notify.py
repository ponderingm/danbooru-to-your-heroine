"""
notify.py
=========
生成失敗時にDiscord Webhookへ通知するための最小ヘルパー。
config.DISCORD_WEBHOOK_URL が未設定（空文字）の場合は何もしない。
通知自体の失敗でアプリ本体を落とさないよう、例外は全てbest-effortで握りつぶす。
"""

import json
import urllib.request

import config


def notify_failure(context: str, detail: str) -> None:
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return
    content = f"⚠️ **{context}**\n```{detail}```"
    body = json.dumps({"content": content[:1990]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=body,
        headers={
            "Content-Type": "application/json",
            # DiscordのCloudflare WAFがurllibデフォルトUser-Agent(Python-urllib/x.y)を
            # 403(error 1010)でブロックするため、ブラウザ相当のUser-Agentを明示する
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except Exception:
        pass

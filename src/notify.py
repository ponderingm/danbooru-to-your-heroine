"""
notify.py
=========
Discord Webhook への多機能通知ヘルパー。
- 4段階ログレベル (debug / success / error_only / none)
- multipart/form-data による生成画像の実体添付 (大画面Embedプレビュー)
- 例外は全て best-effort で安全に握りつぶし、本体の生成処理を絶対に阻害しない
"""

import json
import os
from typing import Optional
import requests
import config


def _should_notify(target_level: str) -> bool:
    """現在のDISCORD_NOTIFY_LEVELに基づいて通知を送信すべきか判定する"""
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        return False
    current_level = getattr(config, "DISCORD_NOTIFY_LEVEL", "success").lower()
    if current_level == "none":
        return False
    if current_level == "debug":
        return True
    if current_level == "success":
        return target_level in ("success", "error")
    if current_level == "error_only":
        return target_level == "error"
    return False


def notify_debug(title: str, detail: str) -> None:
    """デバッグ用詳細通知（DISCORD_NOTIFY_LEVEL == 'debug' のみ送信）"""
    if not _should_notify("debug"):
        return
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    content = f"🔍 **[DEBUG] {title}**\n```{detail[:1500]}```"
    try:
        requests.post(webhook_url, json={"content": content}, timeout=5)
    except Exception:
        pass


def notify_failure(context: str, detail: str) -> None:
    """生成失敗・エラー通知 (debug, success, error_only で送信)"""
    if not _should_notify("error"):
        return
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    content = f"⚠️ **{context}**\n```{detail[:1800]}```"
    try:
        requests.post(webhook_url, json={"content": content}, timeout=5)
    except Exception:
        pass


def notify_success(
    heroine: str,
    prompt: str,
    image_path: Optional[str] = None,
    source_url: Optional[str] = None,
    duration_sec: Optional[float] = None,
    silent: bool = False,
) -> None:
    """生成成功通知 (debug, success で送信。画像実体を添付してEmbed表示。silent=True時は@silentで通知音を抑制)"""
    if not _should_notify("success"):
        return
    webhook_url = getattr(config, "DISCORD_WEBHOOK_URL", "")
    include_image = getattr(config, "DISCORD_INCLUDE_IMAGE", True)

    time_text = f" ({duration_sec:.1f}s)" if duration_sec else ""
    desc_lines = []
    if source_url:
        desc_lines.append(f"🔗 **元投稿:** {source_url}")
    desc_lines.append(f"⏱ **所要時間:** {time_text.strip(' ()')}")
    desc_lines.append(f"📝 **プロンプト:**\n```{prompt[:500]}...```" if len(prompt) > 500 else f"📝 **プロンプト:**\n```{prompt}```")

    embed = {
        "title": f"⚡ 生成完了: {heroine}{time_text}",
        "description": "\n".join(desc_lines),
        "color": 0x7928CA,  # アクセントカラー（パープル）
    }

    # 画像添付のハンドリング
    has_image = bool(include_image and image_path and os.path.exists(image_path))

    payload = {
        "embeds": [embed],
    }
    if silent:
        payload["content"] = "@silent"
        payload["flags"] = 4096  # SUPPRESS_NOTIFICATIONS

    try:
        if has_image:
            embed["image"] = {"url": "attachment://generated.png"}
            with open(image_path, "rb") as f:
                files = {
                    "files[0]": ("generated.png", f, "image/png"),
                }
                data = {"payload_json": json.dumps(payload)}
                requests.post(webhook_url, data=data, files=files, timeout=15)
        else:
            requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ [notify.py] Discord通知送信エラー (無視): {e}")


def send_test_notification(webhook_url: Optional[str] = None) -> bool:
    """Discord Webhook への疎通テスト通知を送信する"""
    url = (webhook_url or getattr(config, "DISCORD_WEBHOOK_URL", "")).strip()
    if not url:
        return False
    embed = {
        "title": "⚡ 【通知テスト】danbooru-to-your-heroine",
        "description": "Discord Webhook 通知の疎通テストに成功したわ！\n生成完了時やエラー時の通知がここへ届くようになるわよ♪",
        "color": 0x7928CA,
    }
    try:
        res = requests.post(url, json={"embeds": [embed]}, timeout=8)
        return res.status_code in (200, 204)
    except Exception as e:
        print(f"⚠️ [notify.py] テスト通知送信エラー: {e}")
        return False


"""
config.py
=========
YAML設定ファイル (config.yaml) および公式ベースルール (rules/default_rules.yaml) を
読み込み、システム全体へ型変換・マージ済みの定数・設定を提供するローダーモジュール。

既存の `import config` との下位互換性を100%維持しつつ、
設定の実体を `config.yaml` 単一ファイルへ集約する。
"""

from pathlib import Path
from typing import Any, Dict, Set
import yaml

CONFIG_DIR = Path(__file__).resolve().parent
CONFIG_YAML_PATH = CONFIG_DIR / "config.yaml"
CONFIG_EXAMPLE_YAML_PATH = CONFIG_DIR / "config.example.yaml"
DEFAULT_RULES_PATH = CONFIG_DIR / "rules" / "default_rules.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"⚠️ [config.py] YAMLロード失敗 ({path}): {e}")
        return {}


def _save_yaml(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def reload_config() -> None:
    """YAML設定およびBaseルールを再読み込みし、モジュールグローバル変数を更新する（ホットリロード対応）"""
    global COMFYUI_API_URL, CUSTOM_COMFY_URL, CUSTOM_LORA_NAME, CUSTOM_STEPS, CUSTOM_CFG, CUSTOM_SAMPLER, CUSTOM_SCHEDULER
    global DEFAULT_CHECKPOINT, ANIMA_COMFY_URL, ANIMA_UNET_NAME, ANIMA_CLIP_NAME, ANIMA_VAE_NAME
    global ANIMA_STEPS, ANIMA_CFG, ANIMA_SAMPLER, ANIMA_SCHEDULER
    global GENERATION_BACKENDS, DEFAULT_BACKEND, OUTPUT_DIR, WEB_OUTPUT_DIR
    global DANBOORU_LOGIN, DANBOORU_API_KEY, CORS_ORIGINS, API_HOST, API_PORT
    global DISCORD_WEBHOOK_URL, DISCORD_NOTIFY_LEVEL, DISCORD_INCLUDE_IMAGE
    global MAX_CONSECUTIVE_FAILURES, HEROINES, DEFAULT_HEROINE, SERIES_TAG_KEEP_KEYWORDS
    global OTHER_KNOWN_CHARACTER_TAGS, EXTRA_PURGE_TAGS, GENERATION_BLACKLIST_TAGS
    global QUALITY_TAGS, CHARACTER_IDENTITY_BLACKLIST, BASE_RULES, USER_CONFIG

    # 1. ユーザー設定ロード（config.yaml が無ければ config.example.yaml をフォールバック）
    user_path = CONFIG_YAML_PATH if CONFIG_YAML_PATH.exists() else CONFIG_EXAMPLE_YAML_PATH
    USER_CONFIG = _load_yaml(user_path)

    # 2. 公式Baseルールロード
    BASE_RULES = _load_yaml(DEFAULT_RULES_PATH)

    # 3. サーバー・接続設定
    COMFYUI_API_URL = USER_CONFIG.get("comfyui_api_url", "http://127.0.0.1:8188")
    CUSTOM_COMFY_URL = USER_CONFIG.get("custom_comfy_url", "http://127.0.0.1:8189")
    CUSTOM_LORA_NAME = USER_CONFIG.get("custom_lora_name", "your_custom_lora.safetensors")
    CUSTOM_STEPS = int(USER_CONFIG.get("custom_steps", 4))
    CUSTOM_CFG = float(USER_CONFIG.get("custom_cfg", 1.5))
    CUSTOM_SAMPLER = USER_CONFIG.get("custom_sampler", "euler")
    CUSTOM_SCHEDULER = USER_CONFIG.get("custom_scheduler", "sgm_uniform")

    DEFAULT_CHECKPOINT = USER_CONFIG.get("default_checkpoint", "waiIllustriousSDXL_v160.safetensors")

    ANIMA_COMFY_URL = USER_CONFIG.get("anima_comfy_url", COMFYUI_API_URL)
    ANIMA_UNET_NAME = USER_CONFIG.get("anima_unet_name", "anima-base-v1.0.safetensors")
    ANIMA_CLIP_NAME = USER_CONFIG.get("anima_clip_name", "qwen_3_06b_base.safetensors")
    ANIMA_VAE_NAME = USER_CONFIG.get("anima_vae_name", "qwen_image_vae.safetensors")
    ANIMA_STEPS = int(USER_CONFIG.get("anima_steps", 28))
    ANIMA_CFG = float(USER_CONFIG.get("anima_cfg", 4.5))
    ANIMA_SAMPLER = USER_CONFIG.get("anima_sampler", "euler")
    ANIMA_SCHEDULER = USER_CONFIG.get("anima_scheduler", "normal")

    GENERATION_BACKENDS = USER_CONFIG.get("backends", {})
    DEFAULT_BACKEND = USER_CONFIG.get("default_backend", "illustrious_fast")

    OUTPUT_DIR = USER_CONFIG.get("output_dir", "/tmp/generated")
    WEB_OUTPUT_DIR = USER_CONFIG.get("web_output_dir", OUTPUT_DIR)

    DANBOORU_LOGIN = USER_CONFIG.get("danbooru_login")
    DANBOORU_API_KEY = USER_CONFIG.get("danbooru_api_key")
    CIVITAI_API_KEY = USER_CONFIG.get("civitai_api_key")
    GELBOORU_USER_ID = USER_CONFIG.get("gelbooru_user_id")
    GELBOORU_API_KEY = USER_CONFIG.get("gelbooru_api_key")


    CORS_ORIGINS = USER_CONFIG.get("cors_origins", ["https://danbooru.donmai.us", "https://gelbooru.com"])
    API_HOST = USER_CONFIG.get("api_host", "0.0.0.0")
    API_PORT = int(USER_CONFIG.get("api_port", 8899))

    discord_cfg = USER_CONFIG.get("discord", {})
    DISCORD_WEBHOOK_URL = discord_cfg.get("webhook_url", "")
    DISCORD_NOTIFY_LEVEL = discord_cfg.get("notify_level", "success")
    DISCORD_INCLUDE_IMAGE = bool(discord_cfg.get("include_image", True))

    MAX_CONSECUTIVE_FAILURES = int(USER_CONFIG.get("max_consecutive_failures", 3))

    # 4. ヒロイン定義
    HEROINES = USER_CONFIG.get("heroines", {})
    DEFAULT_HEROINE = USER_CONFIG.get("default_heroine", next(iter(HEROINES)) if HEROINES else "")
    SERIES_TAG_KEEP_KEYWORDS = USER_CONFIG.get("series_tag_keep_keywords", [])
    OTHER_KNOWN_CHARACTER_TAGS = set(USER_CONFIG.get("other_known_character_tags", []))

    # 5. ルールマージ（Base層 + User層 - User除外解除）
    user_purge = {t.replace("_", " ").lower() for t in USER_CONFIG.get("purge_tags", [])}
    user_unpurge = {t.replace("_", " ").lower() for t in USER_CONFIG.get("unpurge_tags", [])}
    base_meta = {t.replace("_", " ").lower() for t in BASE_RULES.get("meta_purge", [])}
    base_artifact = {t.replace("_", " ").lower() for t in BASE_RULES.get("artifact_purge", [])}
    EXTRA_PURGE_TAGS = (user_purge | base_meta | base_artifact) - user_unpurge

    user_block = {t.replace("_", " ").lower() for t in USER_CONFIG.get("block_tags", [])}
    base_block = {t.replace("_", " ").lower() for t in BASE_RULES.get("default_block_tags", [])}
    GENERATION_BLACKLIST_TAGS = user_block | base_block

    QUALITY_TAGS = {t.replace("_", " ").lower() for t in BASE_RULES.get("quality_tags", [])}
    CHARACTER_IDENTITY_BLACKLIST = BASE_RULES.get("identity_attributes", {})



BACKUP_DIR = CONFIG_DIR.parent / "database" / "backups"


def _create_backup() -> None:
    """現在のconfig.yamlからバックアップを作成する（最大20世代保持）"""
    if not CONFIG_YAML_PATH.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"purge_tags_{now_str}.yaml"
    
    current = _load_yaml(CONFIG_YAML_PATH)
    backup_data = {
        "created_at": datetime.now().isoformat(),
        "purge_tags": current.get("purge_tags", []),
        "block_tags": current.get("block_tags", []),
    }
    _save_yaml(backup_file, backup_data)
    
    # 20件を超えた古いバックアップを削除
    backups = sorted(list(BACKUP_DIR.glob("purge_tags_*.yaml")), key=lambda p: p.stat().st_mtime)
    while len(backups) > 20:
        oldest = backups.pop(0)
        try:
            oldest.unlink()
        except Exception:
            pass


def list_backups() -> list:
    """利用可能なバックアップ一覧（新しい順）を返す"""
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for p in sorted(BACKUP_DIR.glob("purge_tags_*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _load_yaml(p)
        backups.append({
            "filename": p.name,
            "created_at": data.get("created_at", p.stat().st_mtime),
            "tag_count": len(data.get("purge_tags", [])),
            "purge_tags": data.get("purge_tags", []),
        })
    return backups


def restore_backup(backup_filename: str) -> dict:
    """指定されたバックアップファイルからパージタグを復元する"""
    backup_path = BACKUP_DIR / backup_filename
    if not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError(f"バックアップファイルが見つかりません: {backup_filename}")
    
    # 復元する前にも直前状態をバックアップ
    _create_backup()
    
    backup_data = _load_yaml(backup_path)
    current_cfg = _load_yaml(CONFIG_YAML_PATH)
    current_cfg["purge_tags"] = backup_data.get("purge_tags", [])
    if "block_tags" in backup_data:
        current_cfg["block_tags"] = backup_data.get("block_tags", [])
    _save_yaml(CONFIG_YAML_PATH, current_cfg)
    reload_config()
    return {
        "restored_from": backup_filename,
        "purge_tags": current_cfg["purge_tags"],
    }


def save_user_purge_tags(new_purge_tags: list, new_unpurge_tags: list = None) -> None:
    """WebUI等から追加されたパージタグおよび除外解除タグを src/config.yaml に保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    data["purge_tags"] = sorted(list(set(new_purge_tags)))
    if new_unpurge_tags is not None:
        data["unpurge_tags"] = sorted(list(set(new_unpurge_tags)))
    _save_yaml(CONFIG_YAML_PATH, data)
    reload_config()



def save_user_block_tags(new_block_tags: list) -> None:
    """WebUI等から追加されたブロックタグを src/config.yaml に保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    data["block_tags"] = sorted(list(set(new_block_tags)))
    _save_yaml(CONFIG_YAML_PATH, data)
    reload_config()


def save_notification_config(webhook_url: str, notify_level: str, include_image: bool) -> None:
    """WebUI等からDiscord通知設定を更新して保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    if "discord" not in data:
        data["discord"] = {}
    data["discord"]["webhook_url"] = webhook_url.strip()
    data["discord"]["notify_level"] = notify_level.strip()
    data["discord"]["include_image"] = bool(include_image)
    _save_yaml(CONFIG_YAML_PATH, data)
    reload_config()


def save_site_auth_config(civitai_api_key: str = None, danbooru_login: str = None, danbooru_api_key: str = None, gelbooru_user_id: str = None, gelbooru_api_key: str = None) -> None:
    """WebUI等から各外部サイトの認証APIキーを保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    if civitai_api_key is not None:
        data["civitai_api_key"] = civitai_api_key.strip()
    if danbooru_login is not None:
        data["danbooru_login"] = danbooru_login.strip()
    if danbooru_api_key is not None:
        data["danbooru_api_key"] = danbooru_api_key.strip()
    if gelbooru_user_id is not None:
        data["gelbooru_user_id"] = gelbooru_user_id.strip()
    if gelbooru_api_key is not None:
        data["gelbooru_api_key"] = gelbooru_api_key.strip()
    _save_yaml(CONFIG_YAML_PATH, data)
    reload_config()


def save_heroine(heroine_key: str, heroine_data: dict) -> None:

    """WebUI等からヒロイン設定を保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    if "heroines" not in data:
        data["heroines"] = {}
    data["heroines"][heroine_key] = heroine_data
    _save_yaml(CONFIG_YAML_PATH, data)
    reload_config()


def delete_heroine(heroine_key: str) -> bool:
    """WebUI等からヒロイン設定を削除し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    if "heroines" in data and heroine_key in data["heroines"]:
        del data["heroines"][heroine_key]
        _save_yaml(CONFIG_YAML_PATH, data)
        reload_config()
        return True
    return False


# モジュール初回ロード時に実行
reload_config()





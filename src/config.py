"""
config.py
=========
YAML設定ファイル (config.yaml) および公式ベースルール (rules/default_rules.yaml) を
読み込み、システム全体へ型変換・マージ済みの定数・設定を提供するローダーモジュール。

既存の `import config` との下位互換性を100%維持しつつ、
設定の実体を `config.yaml` 単一ファイルへ集約する。
"""

import os
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
    global DANBOORU_LOGIN, DANBOORU_API_KEY, CIVITAI_API_KEY, GELBOORU_USER_ID, GELBOORU_API_KEY, CORS_ORIGINS, API_HOST, API_PORT
    global OLLAMA_URL, OLLAMA_MODEL
    global DISCORD_WEBHOOK_URL, DISCORD_NOTIFY_LEVEL, DISCORD_INCLUDE_IMAGE
    global MAX_CONSECUTIVE_FAILURES, HEROINES, DEFAULT_HEROINE, SERIES_TAG_KEEP_KEYWORDS
    global OTHER_KNOWN_CHARACTER_TAGS, EXTRA_PURGE_TAGS, GENERATION_BLACKLIST_TAGS
    global QUALITY_TAGS, CHARACTER_IDENTITY_BLACKLIST, BASE_RULES, USER_CONFIG
    global ART_STYLE_TAGS, ART_STYLE_PRESETS
    global META_TAG_BLACKLIST, CENSORING_BLACKLIST, BREAST_TAGS, SKIN_TAGS
    global MONSTER_SKIN_TAGS, HUMAN_SKIN_TAGS, DARK_SKIN_TAGS

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

    OLLAMA_URL = USER_CONFIG.get("ollama_url", "http://127.0.0.1:11434")
    OLLAMA_MODEL = USER_CONFIG.get("ollama_model", "qwen2.5:latest")

    CORS_ORIGINS = USER_CONFIG.get("cors_origins", ["https://danbooru.donmai.us", "https://gelbooru.com"])
    API_HOST = os.environ.get("API_HOST") or os.environ.get("HOST") or USER_CONFIG.get("api_host", "0.0.0.0")
    API_PORT = int(os.environ.get("API_PORT") or os.environ.get("PORT") or USER_CONFIG.get("api_port", 8899))

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
    user_purge_raw = USER_CONFIG.get("purge_tags") or USER_CONFIG.get("user_purge_tags") or []
    user_unpurge_raw = USER_CONFIG.get("unpurge_tags") or USER_CONFIG.get("user_unpurge_tags") or []
    user_block_raw = USER_CONFIG.get("block_tags") or USER_CONFIG.get("user_block_tags") or []

    user_purge = {t.replace("_", " ").lower() for t in user_purge_raw}
    user_unpurge = {t.replace("_", " ").lower() for t in user_unpurge_raw}
    base_meta = {t.replace("_", " ").lower() for t in BASE_RULES.get("meta_purge", [])}
    base_artifact = {t.replace("_", " ").lower() for t in BASE_RULES.get("artifact_purge", [])}

    # gray <-> grey の英米綴り同義語展開（パージ漏れ・不整合を完全防止）
    purge_variants = set()
    for t in (user_purge | base_meta | base_artifact):
        if "grey" in t:
            purge_variants.add(t.replace("grey", "gray"))
        if "gray" in t:
            purge_variants.add(t.replace("gray", "grey"))

    unpurge_variants = set()
    for t in user_unpurge:
        if "grey" in t:
            unpurge_variants.add(t.replace("grey", "gray"))
        if "gray" in t:
            unpurge_variants.add(t.replace("gray", "grey"))
    user_unpurge |= unpurge_variants

    EXTRA_PURGE_TAGS = ((user_purge | base_meta | base_artifact | purge_variants) - user_unpurge)

    user_block = {t.replace("_", " ").lower() for t in user_block_raw}
    base_block = {t.replace("_", " ").lower() for t in BASE_RULES.get("default_block_tags", [])}
    GENERATION_BLACKLIST_TAGS = user_block | base_block

    QUALITY_TAGS = {t.replace("_", " ").lower() for t in BASE_RULES.get("quality_tags", [])}
    CHARACTER_IDENTITY_BLACKLIST = BASE_RULES.get("identity_attributes", {})
    META_TAG_BLACKLIST = {t.replace("_", " ").lower() for t in BASE_RULES.get("meta_purge", [])}
    CENSORING_BLACKLIST = {t.replace("_", " ").lower() for t in BASE_RULES.get("artifact_purge", [])}
    BREAST_TAGS = {t.replace("_", " ").lower() for t in CHARACTER_IDENTITY_BLACKLIST.get("breasts", [])}
    SKIN_TAGS = {t.replace("_", " ").lower() for t in CHARACTER_IDENTITY_BLACKLIST.get("skin", [])}
    HAIR_COLOR_TAGS = {t.replace("_", " ").lower() for t in CHARACTER_IDENTITY_BLACKLIST.get("hair_color", [])}
    HAIR_STYLE_TAGS = {t.replace("_", " ").lower() for t in CHARACTER_IDENTITY_BLACKLIST.get("hair_style", [])}
    EYE_COLOR_TAGS = {t.replace("_", " ").lower() for t in CHARACTER_IDENTITY_BLACKLIST.get("eye_color", [])}
    MONSTER_SKIN_TAGS = {t.replace("_", " ").lower() for t in BASE_RULES.get("monster_skin_tags", [])}
    HUMAN_SKIN_TAGS = {t.replace("_", " ").lower() for t in BASE_RULES.get("human_skin_tags", [])}
    DARK_SKIN_TAGS = {t.replace("_", " ").lower() for t in BASE_RULES.get("dark_skin_tags", [])}

    # 6. 画風・媒体カタログ（default_rules.yaml + config.yaml）
    base_styles = set()
    for cat_tags in BASE_RULES.get("art_styles", {}).values():
        if isinstance(cat_tags, list):
            base_styles.update(t.replace("_", " ").lower() for t in cat_tags)
    user_styles = {t.replace("_", " ").lower() for t in USER_CONFIG.get("art_styles", [])}
    ART_STYLE_TAGS = base_styles | user_styles

    base_presets = dict(BASE_RULES.get("art_style_presets", {}))
    user_presets = dict(USER_CONFIG.get("art_style_presets", {}))
    ART_STYLE_PRESETS = {**base_presets, **user_presets}



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


def normalize_heroine_v3_schema(raw: dict) -> dict:
    """
    ヒロイン設定辞書を v3 の 7大スロット階層スキーマに完全正規化する。
    旧形式（face_tags, body_tags等のフラット配列）が渡された場合も自動で階層化する。
    """
    if not isinstance(raw, dict):
        return {}

    result = {
        "name": raw.get("name", ""),
    }

    # 1. identity
    ident = raw.get("identity")
    if isinstance(ident, dict):
        result["identity"] = dict(ident)
    else:
        ident_tags = raw.get("identity_tags", [])
        if isinstance(ident_tags, str):
            ident_tags = [t.strip() for t in ident_tags.split(",") if t.strip()]
        series_tags = raw.get("series_tags", [])
        if isinstance(series_tags, str):
            series_tags = [t.strip() for t in series_tags.split(",") if t.strip()]

        char_name = ident_tags[0] if ident_tags else ""
        series_name = series_tags[0] if series_tags else (ident_tags[1] if len(ident_tags) > 1 and "series" in ident_tags[1] else "")
        extra_tags = [t for t in ident_tags if t != char_name and t != series_name]

        result["identity"] = {
            "character": char_name,
            "series": series_name,
        }
        if extra_tags:
            result["identity"]["extra"] = extra_tags

    # 2. dna (hair, face, body)
    dna = raw.get("dna")
    if isinstance(dna, dict):
        result["dna"] = dict(dna)
    else:
        face_tags = raw.get("face_tags", [])
        if isinstance(face_tags, str):
            face_tags = [t.strip() for t in face_tags.split(",") if t.strip()]

        breasts_tags = raw.get("breasts_tags", [])
        if isinstance(breasts_tags, str):
            breasts_tags = [t.strip() for t in breasts_tags.split(",") if t.strip()]

        skin_tags = raw.get("skin_tags", [])
        if isinstance(skin_tags, str):
            skin_tags = [t.strip() for t in skin_tags.split(",") if t.strip()]

        other_body_tags = raw.get("body_other_tags", [])
        if isinstance(other_body_tags, str):
            other_body_tags = [t.strip() for t in other_body_tags.split(",") if t.strip()]

        hair_color = ""
        hair_style = ""
        eyes_color = ""
        face_marks = []
        for t in face_tags:
            low = t.lower()
            if "eyes" in low or "eye" in low:
                eyes_color = t
            elif any(c in low for c in ("hair", "twintails", "ponytail", "braid", "bob", "bangs", "ahoge")):
                if any(col in low for col in ("brown", "black", "blonde", "blue", "red", "white", "silver", "pink", "green", "purple")):
                    hair_color = t
                else:
                    hair_style = t
            else:
                face_marks.append(t)

        result["dna"] = {
            "hair": {
                "color": hair_color,
                "style": hair_style,
            },
            "face": {
                "eyes": eyes_color,
            },
            "body": {
                "skin": ", ".join(skin_tags) if skin_tags else "",
                "breasts": ", ".join(breasts_tags) if breasts_tags else "",
                "build": ", ".join(other_body_tags) if other_body_tags else "",
            }
        }
        if face_marks:
            result["dna"]["face"]["marks"] = ", ".join(face_marks)

    # 空の内部キーを整理
    for block in ("hair", "face", "body"):
        if block in result.get("dna", {}) and isinstance(result["dna"][block], dict):
            result["dna"][block] = {k: v for k, v in result["dna"][block].items() if v}

    # 3. costume
    costume = raw.get("costume")
    if isinstance(costume, dict):
        result["costume"] = dict(costume)
    else:
        costume_tags = raw.get("costume_tags", [])
        if isinstance(costume_tags, str):
            costume_tags = [t.strip() for t in costume_tags.split(",") if t.strip()]
        result["costume"] = {"default": costume_tags}

    # 4. override_rules
    rules = raw.get("override_rules", {})
    result["override_rules"] = {
        "breasts": rules.get("breasts", "strict"),
        "skin": rules.get("skin", "strict"),
        "costume": rules.get("costume", "source"),
        "art_style": rules.get("art_style", "source"),
        "artist": rules.get("artist", "none"),
        "multi_mode": rules.get("multi_mode", "capsule"),
    }

    # 5. その他オプション
    for opt_key in ("artist_tags", "negative_tags", "default_checkpoint", "default_backend"):
        if opt_key in raw and raw[opt_key]:
            result[opt_key] = raw[opt_key]

    return result


def save_heroine(heroine_key: str, heroine_data: dict) -> None:
    """WebUI等からヒロイン設定を保存し、即座にリロードする"""
    _create_backup()
    data = _load_yaml(CONFIG_YAML_PATH)
    if "heroines" not in data:
        data["heroines"] = {}
    normalized = normalize_heroine_v3_schema(heroine_data)
    data["heroines"][heroine_key] = normalized
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





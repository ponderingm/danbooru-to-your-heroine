"""
config.example.py
==================
個人環境設定のテンプレート。このファイルをコピーして config.py を作成してください。
config.py はGitに含めない（.gitignore対象）ので、各自の環境に合わせて値を書き換える。

    cp config.example.py config.py
"""

# デフォルトのComfyUIサーバー（通常のKSampler設定で生成）
# 注: この名前は「ワークフローの種類」を表すだけで「どの物理サーバーか」とは無関係。
# 例えばブラウザから逐次生成する用の高速サーバーをここに割り当てる、といった使い方を想定
COMFYUI_API_URL = "http://127.0.0.1:8188"

# カスタムワークフロー用ComfyUIサーバー（--custom使用時。任意、使わないなら適当な値のままでOK）
# 例: 高速化LoRA(DMD2/Turbo等)を使う別ノードや、別のサンプラー設定を試したい場合に使用。
# 低消費電力だが遅いバッチ生成専用サーバーをここに割り当てる、といった使い方も想定
CUSTOM_COMFY_URL = "http://127.0.0.1:8189"
CUSTOM_LORA_NAME = "your_custom_lora.safetensors"
CUSTOM_STEPS = 4
CUSTOM_CFG = 1.5
CUSTOM_SAMPLER = "euler"
CUSTOM_SCHEDULER = "sgm_uniform"

# 生成バックエンド：モデル構文(illustrious/anima)・ComfyUIエンドポイント・checkpoint/LoRA設定を
# 1つにまとめて名前付き登録し、Web UIのプルダウン/CLIの`--backend name`/APIの`backend`パラメータで
# 切り替える（省略時はDEFAULT_BACKENDが使われる）。各キーは以下の通り（すべて任意、省略時は
# 対応するCUSTOM_*/ANIMA_*/DEFAULT_CHECKPOINTにフォールバック）:
# - label: プルダウン等での表示名
# - model: "illustrious" か "anima"（プロンプト構文の切り替えに使う）
# - workflow: "default"(LoRAなしの素のKSampler) / "custom"(LoRA+可変sampler設定) / "anima"(Anima DiT専用構造)
# - comfy_url: このバックエンドが向くComfyUIサーバーのURL
# - checkpoint: workflow="default"/"custom"で使うcheckpointファイル名
# - lora_name/steps/cfg/sampler/scheduler: workflow="custom"の場合のみ使用
# 例: 高速機でillustrious/animaを逐次生成、低消費電力な別機で4-Step LoRAのバッチ生成、という
# 3バックエンド構成を想定したサンプル
GENERATION_BACKENDS = {
    "illustrious_fast": {
        "label": "Illustrious（高速機）",
        "model": "illustrious",
        "workflow": "default",
        "comfy_url": "http://127.0.0.1:8188",
        "checkpoint": "waiIllustriousSDXL_v160.safetensors",
    },
    "anima_fast": {
        "label": "Anima（高速機）",
        "model": "anima",
        "workflow": "anima",
        "comfy_url": "http://127.0.0.1:8188",
    },
    "illustrious_4step_slow": {
        "label": "Illustrious 4-step LoRA（低速機）",
        "model": "illustrious",
        "workflow": "custom",
        "comfy_url": "http://127.0.0.1:8189",
        "checkpoint": "waiIllustriousSDXL_v160.safetensors",
        "lora_name": "your_4step_lora.safetensors",
        "steps": 4,
        "cfg": 1.5,
        "sampler": "euler",
        "scheduler": "sgm_uniform",
    },
}
# --backend/backendパラメータを省略した場合に使われるデフォルトのバックエンドid
DEFAULT_BACKEND = "illustrious_fast"

# デフォルトで使うSDXL/Illustrious系checkpointファイル名
DEFAULT_CHECKPOINT = "waiIllustriousSDXL_v160.safetensors"

# Anima v1.0 DiT用ワークフロー設定（--model anima使用時。SDXLのcheckpointとは別物で
# UNETLoader/CLIPLoader/VAELoaderを使う。ComfyUIの models/unet, models/clip, models/vae に
# 該当ファイルを配置しておくこと。同一ComfyUIインスタンスに別モデルとして置いてもOK）
ANIMA_COMFY_URL = COMFYUI_API_URL
ANIMA_UNET_NAME = "anima-base-v1.0.safetensors"
ANIMA_CLIP_NAME = "qwen_3_06b_base.safetensors"
ANIMA_VAE_NAME = "qwen_image_vae.safetensors"
ANIMA_STEPS = 28
ANIMA_CFG = 4.5
ANIMA_SAMPLER = "euler"
ANIMA_SCHEDULER = "normal"

# 生成画像の保存先ディレクトリ
OUTPUT_DIR = "/path/to/generated_images"
WEB_OUTPUT_DIR = "/path/to/generated_images"

# Danbooru認証（任意、匿名利用なら None のままでOK）
DANBOORU_LOGIN = None
DANBOORU_API_KEY = None

# APIサーバー（server.py）のCORS許可オリジン。Tampermonkeyスクリプト等からブラウザ経由で
# 呼び出す場合、その配信元オリジンを指定する
CORS_ORIGINS = ["https://danbooru.donmai.us"]

# APIサーバー（server.py）のbind先host/port（`uv run python src/server.py`で起動した場合に使用）。
# LAN内の他端末（Tampermonkey実行環境等）からも受け付けたい場合はAPI_HOSTを"0.0.0.0"にする
API_HOST = "127.0.0.1"
API_PORT = 8000

# 生成失敗時に通知するDiscord Webhook URL（任意、空文字なら通知しない）
DISCORD_WEBHOOK_URL = ""

# バッチ生成（danbooru_search_batch_generator.py / /batch/start）で、これだけ連続して
# 生成に失敗したらComfyUIが落ちているとみなしてループを停止する（成功で連続カウントはリセット）
MAX_CONSECUTIVE_FAILURES = 3

# ─────────────────────────────────────────────
# ヒロイン定義（--heroine で指定するキャラクターDNA）
# ─────────────────────────────────────────────
# name:          表示名
# identity_tags: キャラクターを特定するタグ（キャラ名・作品名など）
# body_tags:     体格・髪型・瞳などの特徴タグ（元投稿の同カテゴリタグを置き換える）
# artist_tags:   (任意) artist_mode="keep"で元投稿にartistタグが無い場合のフォールバック、
#                artist_mode="override"では常にこれが使われる
# negative_tags: (任意) positive promptから除去し、negative promptへ追加するタグ
# 以下は全て任意（未指定ならグローバル設定/引数の値を使う）。API/CLIで明示指定された値が
# 常に優先され、ヒロイン側の値はその「省略時のデフォルト」としてのみ働く。
# default_model:          このヒロインを使うときのデフォルトmodel（illustrious/anima）
# default_checkpoint:     このヒロインを使うときのデフォルトcheckpointファイル名
# default_negative_extra: get_negative_prompt()の結果に追記する、このヒロイン専用の追加ネガティブタグ
HEROINES = {
    "example_heroine": {
        "name": "サンプルヒロイン",
        "identity_tags": ["example_character_name", "example_series"],
        "body_tags": [
            "fair skin", "medium breasts", "long hair", "blue eyes",
        ],
        "artist_tags": [],
        "negative_tags": ["example unwanted tag"],
        # "default_model": "illustrious",
        # "default_checkpoint": "your_checkpoint.safetensors",
        # "default_negative_extra": "example negative tag",
    },
}

# --heroine を省略した場合に使うデフォルトのヒロインキー（HEROINESのキーのいずれか）
DEFAULT_HEROINE = "example_heroine"

# 元投稿の著作権(copyright)タグのうち、これらのキーワードを含むものだけ保持する
# （自分の作品世界に統一したい場合に使用。空リストなら著作権タグは常に除去される）
SERIES_TAG_KEEP_KEYWORDS = []

# HEROINESに定義していない「その他の既知キャラクタータグ」。元投稿に混入している場合、
# ヒロイン識別タグと衝突しないよう常に除去する
OTHER_KNOWN_CHARACTER_TAGS = set()

# 追加パージリスト：ここに書いたタグはプロンプトから除去するが、画像生成自体は行う
# （例: フキダシ等の画面ノイズ系タグ。半角スペース/アンダースコアどちらでも可、大文字小文字区別なし）
EXTRA_PURGE_TAGS = {
    "speech bubble",
}

# 自動バッチ生成（danbooru_search_batch_generator.py / server.pyの/batch/start）専用の追加ブラックリスト。
# ここに書いたタグを含む投稿は自動生成時にスキップする（例: グロ系タグ）。
# 手動変換（danbooru_to_heroine.py単体実行・/convert・/generate）には適用されない
GENERATION_BLACKLIST_TAGS = {
    "guro",
}

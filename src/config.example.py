"""
config.example.py
==================
個人環境設定のテンプレート。このファイルをコピーして config.py を作成してください。
config.py はGitに含めない（.gitignore対象）ので、各自の環境に合わせて値を書き換える。

    cp config.example.py config.py
"""

# デフォルトのComfyUIサーバー（通常のKSampler設定で生成）
COMFYUI_API_URL = "http://127.0.0.1:8188"

# カスタムワークフロー用ComfyUIサーバー（--custom使用時。任意、使わないなら適当な値のままでOK）
# 例: 高速化LoRA(DMD2/Turbo等)を使う別ノードや、別のサンプラー設定を試したい場合に使用
CUSTOM_COMFY_URL = "http://127.0.0.1:8189"
CUSTOM_LORA_NAME = "your_custom_lora.safetensors"
CUSTOM_STEPS = 4
CUSTOM_CFG = 1.5
CUSTOM_SAMPLER = "euler"
CUSTOM_SCHEDULER = "sgm_uniform"

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

# ─────────────────────────────────────────────
# ヒロイン定義（--heroine で指定するキャラクターDNA）
# ─────────────────────────────────────────────
# name:          表示名
# identity_tags: キャラクターを特定するタグ（キャラ名・作品名など）
# body_tags:     体格・髪型・瞳などの特徴タグ（元投稿の同カテゴリタグを置き換える）
# artist_tags:   (任意) アーティストタグ未取得時に使うフォールバック
HEROINES = {
    "example_heroine": {
        "name": "サンプルヒロイン",
        "identity_tags": ["example_character_name", "example_series"],
        "body_tags": [
            "fair skin", "medium breasts", "long hair", "blue eyes",
        ],
        "artist_tags": [],
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

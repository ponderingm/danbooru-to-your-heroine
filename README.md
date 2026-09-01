# danbooru-to-your-heroine

Danbooruの投稿タグを取得し、`src/config.py` で定義した任意のヒロインのキャラクター
特性に書き換えたStable Diffusionプロンプトを生成し、ComfyUI経由で連続的に画像生成するツール群。

`taimanin_prompt_project` から独立した単体プロジェクトとして切り出したもの。

## ディレクトリ構成

```
config.example.py, config.py 等は src/ にまとめてある
src/
  danbooru_to_heroine.py            # コアエンジン（単一投稿の変換）
  danbooru_search_batch_generator.py  # 検索結果の連続生成バッチ
  comfy_client.py                   # ComfyUIワークフロー生成・送信
  model_adapter.py                  # モデル別プロンプト構文アダプタ
  server.py                         # FastAPI APIサーバー（Webビューアも配信）
  web/                              # Webビューア静的ファイル（index.html/style.css/app.js）
  config.py / config.example.py     # 個人環境設定
tampermonkey/
  danbooru-to-heroine.user.js       # Danbooru投稿ページ用の生成ボタンスクリプト
database/                           # 進捗ファイル・生成manifest等の生成物
```

## セットアップ

```bash
cp src/config.example.py src/config.py
# src/config.py を自分の環境（ComfyUIのURL・保存先ディレクトリ・checkpoint名等）に合わせて編集する
uv sync
```

`src/config.py` は個人環境設定のため `.gitignore` 対象。リポジトリには含めない。

### ヒロインを設定する

変換先ヒロインは `config.py` の `HEROINES` 辞書で定義する（ハードコードされたキャラクターは無し）。

```python
HEROINES = {
    "my_heroine": {
        "name": "マイヒロイン",                          # 表示名
        "identity_tags": ["my_character_name", "my_series"],  # キャラを特定するタグ
        "body_tags": [                                    # 体格・髪型・瞳などの特徴タグ
            "fair skin", "medium breasts", "long hair", "blue eyes",
        ],
        "artist_tags": [],                                # (任意) アーティストタグ未取得時のフォールバック
    },
}
DEFAULT_HEROINE = "my_heroine"   # --heroine 省略時に使うキー

# 元投稿の著作権(copyright)タグをこのキーワードに合致するものだけ残したい場合に指定
SERIES_TAG_KEEP_KEYWORDS = []

# HEROINESに登録していない「その他の既知キャラクタータグ」（混入時は常に除去）
OTHER_KNOWN_CHARACTER_TAGS = set()
```

`--heroine` には `HEROINES` に登録したキーを指定する。

## ツール

### 1. `danbooru_to_heroine.py` — 単一投稿の変換

```bash
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --heroine my_heroine
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --no-nsfw
```

### 2. `danbooru_search_batch_generator.py` — 検索結果を連続生成

```bash
# 通常の検索バッチ生成
uv run python src/danbooru_search_batch_generator.py "micro_bikini" --limit 30 --pages 2

# order:/rating:/除外タグ(-tag)を含む複雑な検索（匿名利用の2タグ制限は自動的に回避される）
uv run python src/danbooru_search_batch_generator.py "order:score rating:explicit micro_bikini beach 1girl" --limit 10

# 検索条件に合致する投稿が尽きるまで全件処理
uv run python src/danbooru_search_batch_generator.py "order:favcount swimsuit -competition_swimsuit" --all

# I'm Feeling Lucky（ランダム抽出を無限ループ、Ctrl+Cで停止）
uv run python src/danbooru_search_batch_generator.py "rating:explicit" --lucky

# カスタムワークフロー（config.pyのCUSTOM_COMFY_URL/CUSTOM_LORA_NAME等）で高速生成
uv run python src/danbooru_search_batch_generator.py "micro_bikini" --custom
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--heroine {config.pyのHEROINESキー}` | 変換先ヒロイン（デフォルト: `config.DEFAULT_HEROINE`） |
| `--model {illustrious,anima,animagine}` | 生成モデル構文 |
| `--no-nsfw` | NSFWタグを除去 |
| `--allow-multi-girl` | ヒロインが複数人登場する投稿も対象に含める |
| `--allow-realistic` | 実写・3DCG調の投稿も対象に含める |
| `--no-auto-canvas` | 元画像アスペクト比に合わせた自動キャンバスサイズ調整を無効化 |
| `--all` | 検索条件に合致する投稿が尽きるまで全件処理 |
| `--lucky` / `--lucky-interval` | ランダム抽出を無限ループ生成 |
| `--custom` | デフォルトComfyUIの代わりに`config.py`の`CUSTOM_COMFY_URL`（+LoRA・ステップ数等）で生成 |
| `--sort SORT` | `order:`が無い場合に自動付与する並び順 |

進捗は `database/danbooru_search_batch_progress.json` に自動保存され、`--no-resume` を付けない限り中断・再開できる。

## 生成バックエンド（default / custom / anima）

- **default**: `config.COMFYUI_API_URL` に対して通常のKSampler設定で生成する（追加指定不要）。
- **custom**: `--custom` 指定時、`config.CUSTOM_COMFY_URL` に対して `CUSTOM_LORA_NAME` / `CUSTOM_STEPS` / `CUSTOM_CFG` / `CUSTOM_SAMPLER` / `CUSTOM_SCHEDULER` を使った任意のワークフローで生成する。高速化LoRA(DMD2/Turbo等)を使う別ノードなど、個人環境固有の構成を想定したもので、値はすべて `config.py` 側で自由に変更できる。
- **anima**: `--model anima` 指定時、`config.ANIMA_COMFY_URL` に対して Anima v1.0 DiT 専用のワークフロー（`UNETLoader` + `CLIPLoader` + `VAELoader`、`config.ANIMA_UNET_NAME` / `ANIMA_CLIP_NAME` / `ANIMA_VAE_NAME` / `ANIMA_STEPS` / `ANIMA_CFG` / `ANIMA_SAMPLER` / `ANIMA_SCHEDULER`）で生成する。SDXL/Illustrious系checkpointは使わないアーキテクチャのため、`--custom`や`--checkpoint`の指定より優先される。

ComfyUI関連の実処理（ワークフロー生成・送信・画像保存）は [src/comfy_client.py](src/comfy_client.py) にまとめられており、[src/danbooru_search_batch_generator.py](src/danbooru_search_batch_generator.py) はそれを呼び出すだけの構成になっている。

### 3. `server.py` — APIサーバー

`src/danbooru_to_heroine.py` のコア変換ロジックと `comfy_client.py` の生成処理をFastAPI経由で呼び出すためのサーバー。Tampermonkeyスクリプト等の外部クライアントから、プロンプト変換・画像生成をHTTP経由で利用できるようにする。

```bash
uv run uvicorn server:app --app-dir src --reload
# または config.py の API_HOST/API_PORT を使って起動
uv run python src/server.py
```

現時点のエンドポイント:

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/` | Webビューア（生成履歴の閲覧・新規生成・再生成） |
| `GET` | `/heroines` | `config.HEROINES` の一覧を返す |
| `POST` | `/convert` | URLからプロンプト文字列のみ生成（画像生成なし） |
| `POST` | `/generate` | 変換 + ComfyUIで画像生成し、`database/generated_manifest.json` に記録 |
| `GET` | `/images` | 生成済み画像のmanifest一覧（新しい順） |
| `GET` | `/output/{filename}` | 生成画像の静的配信 |

`danbooru_search_batch_generator.py`は`database/danbooru_search_batch_progress.json`でpost_id単位に生成済み投稿をスキップするが、この`/generate`（APIサーバー・Webビューア・Tampermonkeyスクリプト経由）はその進捗ファイルを一切参照しないため、同じ投稿・同じヒロインを何度でも再生成できる。

### Webビューア

サーバー起動後、ブラウザで `http://127.0.0.1:8000/` を開くと、Danbooru投稿URLを入力して直接生成したり、生成履歴（`/images`）を一覧してカードの「🔁 再生成」ボタンから同じ設定（ヒロイン・モデル・NSFW・custom等）で再生成したりできる。サムネイルをクリックすると画像を拡大表示できる（もう一度クリックまたはEscで閉じる）。静的ファイルは [src/web/](src/web/) にある（`index.html` / `style.css` / `app.js`、追加のビルド不要）。

### Tampermonkeyスクリプト

[tampermonkey/danbooru-to-heroine.user.js](tampermonkey/danbooru-to-heroine.user.js) をTampermonkeyに登録すると、Danbooruの投稿ページ（`https://danbooru.donmai.us/posts/*`）右下にヒロイン・モデル・NSFW・custom生成を選べる生成パネルが表示され、その場でAPIサーバーの`/generate`を呼び出せる。

- 初回はパネルの ⚙️ からAPIサーバーのURL（デフォルト `http://127.0.0.1:8000`。別ホストで動かす場合はLAN上のURLに変更する）を設定する。
- サーバー側の `config.CORS_ORIGINS` に `https://danbooru.donmai.us` が含まれている必要がある（`config.example.py`にデフォルトで設定済み）。
- 生成完了後、サムネイルとWebビューアへのリンクがパネル内に表示される。

## Docker

`server.py`（APIサーバー + Webビューア）をコンテナで動かせる。ComfyUI自体はコンテナに含めず、既存のComfyUIサーバー（ホスト上またはLAN上）に接続する構成。

```bash
cp src/config.example.py src/config.py
# src/config.py を編集（ComfyUIのURL・保存先ディレクトリ・HEROINES等）
docker compose up --build
```

- `src/config.py` はイメージに焼き込まず、`docker-compose.yml`でボリュームマウントする（`.dockerignore`で除外済み）。
- `OUTPUT_DIR` / `WEB_OUTPUT_DIR` に指定した絶対パスは、`docker-compose.yml`で**同じパス**をホスト側ディレクトリとしてマウントするのが手軽（config.py側の値を変更しなくて済む）。
- `network_mode: host`（Linux専用）を既定にしている。これにより `config.COMFYUI_API_URL = "http://127.0.0.1:8188"` のようにホスト上で動くComfyUIへ、コンテナ内から変更なしで到達できる。
- Mac/Windows等host networkが使えない環境では、`docker-compose.yml`の`network_mode: host`を削除して`ports: ["8000:8000"]`を有効化し、`config.API_HOST`を`"0.0.0.0"`に、`config.COMFYUI_API_URL`を`http://host.docker.internal:8188`等ホストから見えるアドレスに変更すること。

Docker Composeを使わない場合:

```bash
docker build -t danbooru-to-your-heroine .
docker run --network host \
  -v "$(pwd)/src/config.py:/app/src/config.py:ro" \
  -v "$(pwd)/database:/app/database" \
  danbooru-to-your-heroine
```

## 今後の開発要素・カスタマイズポイント

現状は基本的なプロトタイプ（単一投稿変換・検索バッチ・APIサーバー・Webビューア・Tampermonkeyボタン）が一通り動く段階。以下は未着手のアイデア・改善候補（優先度・要否は今後判断）。

**Webビューア**
- ページネーション/無限スクロール（現状`/images?limit=`で件数を絞るのみ）
- ヒロイン・モデル・日付での絞り込みフィルタ
- 履歴エントリの削除機能（`generated_manifest.json`からの削除・画像ファイル削除）
- 再生成前にプロンプトを手動編集できるオプション
- 生成中（ComfyUI処理中）のリアルタイム進捗表示（現状は完了まで応答をブロックして待つだけ）

**Tampermonkeyスクリプト**
- Danbooruの検索結果一覧ページから複数投稿をまとめて生成キューに投入する機能
- 生成キュー・進捗のパネル内表示（現状は1件ずつ同期的に待つのみ）
- API_BASEの初期値をインストール時に案内する設定UIの改善

**APIサーバー**
- 認証（APIキー等）の追加。現状は`CORS_ORIGINS`のみでLAN外からの想定利用は考慮していない
- `/generate`の非同期化（ジョブキュー + WebSocket/ポーリングでの進捗通知）。現状は生成完了までリクエストをブロックする作りで、ComfyUI側が詰まると素直にタイムアウトする
- `/images`のページネーション（`limit`のみで`offset`が無い）
- 履歴削除・再生成失敗時のリトライ等の管理系エンドポイント

**設定まわり**
- ヒロインごとにデフォルトモデル・ネガティブプロンプト・チェックポイントを上書きできるようにする（現状はグローバル設定のみ）
- チェックポイント・LoRAのプリセットを複数登録して`--checkpoint-preset`のように切り替えられるようにする

**バッチ生成**
- 並列生成（現状は1件ずつ逐次処理）
- 生成失敗時の自動リトライ


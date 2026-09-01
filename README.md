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
        "artist_tags": [],                                # (任意) artist_mode=keepのフォールバック/overrideで常時使用

        # 以下は全て任意。省略時はリクエスト側の指定 or グローバル設定(config.DEFAULT_CHECKPOINT等)を使う
        "default_model": "illustrious",                   # このヒロインで生成する際のデフォルトモデル
        "default_checkpoint": "my_checkpoint.safetensors", # このヒロインで生成する際のデフォルトcheckpoint
        "default_negative_extra": "extra negative words", # ネガティブプロンプトに追記するヒロイン固有ワード
    },
}
DEFAULT_HEROINE = "my_heroine"   # --heroine 省略時に使うキー

# 元投稿の著作権(copyright)タグをこのキーワードに合致するものだけ残したい場合に指定
SERIES_TAG_KEEP_KEYWORDS = []

# HEROINESに登録していない「その他の既知キャラクタータグ」（混入時は常に除去）
OTHER_KNOWN_CHARACTER_TAGS = set()

# 追加パージリスト：ここに書いたタグはプロンプトから除去するが、画像生成自体は行う（例: speech bubble等の画面ノイズ系タグ）
EXTRA_PURGE_TAGS = set()

# 自動バッチ生成（CLIの danbooru_search_batch_generator.py / APIの /batch/start）専用の追加ブラックリスト。
# ここに書いたタグを含む投稿は自動生成時にスキップする（例: guro等）。手動変換(danbooru_to_heroine.py単体実行・/convert・/generate)には適用されない
GENERATION_BLACKLIST_TAGS = set()
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
| `--artist-mode {keep,override,none}` | artistタグの扱い（`keep`=元投稿優先+ヒロインの`artist_tags`にフォールバック / `override`=常にヒロインの`artist_tags` / `none`=完全除去。省略時は`--include-artist`の有無から決まる） |
| `--no-nsfw` | NSFWタグを除去 |
| `--allow-multi-girl` | ヒロインが複数人登場する投稿も対象に含める |
| `--allow-realistic` | 実写・3DCG調の投稿も対象に含める |
| `--allow-blacklisted` | `config.py`の`GENERATION_BLACKLIST_TAGS`に合致する投稿も対象に含める（デフォルトはスキップ） |
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
| `POST` | `/generate` | 変換 + ComfyUI画像生成を優先度付きキューに投入し、即座に`{"job_id": ..., "status": "queued"}`を返す |
| `GET` | `/jobs/{job_id}` | `/generate`ジョブの状態（`queued`/`running`/`done`/`error`）と結果を取得（404の場合はジョブ不明） |
| `GET` | `/images` | 生成済み画像のmanifest一覧。`limit`/`offset`でページネーション、`heroine`/`model`/`date_from`/`date_to`（`YYYY-MM-DD`）で絞り込み可能。レスポンスは`{"total": ..., "entries": [...]}` |
| `DELETE` | `/images/{entry_id}` | 生成履歴エントリとその画像ファイルを削除 |
| `POST` | `/generated_posts` | `post_ids`の配列を渡し、既にmanifestに生成済み記録がある`post_id`だけ`{"generated": [...]}`で返す（Tampermonkeyの生成済みバッジ表示に使用） |
| `POST` | `/batch/start` | 検索条件ベースの自動バッチ生成を開始（実行中の設定は同時に1つのみ、409で拒否） |
| `POST` | `/batch/stop` | 自動バッチ生成を停止 |
| `GET` | `/batch/status` | 自動バッチ生成の状態（`running`/`total_checked`/`total_generated`/`last_error`等）を取得 |
| `GET` | `/output/{filename}` | 生成画像の静的配信 |

`danbooru_search_batch_generator.py`は`database/danbooru_search_batch_progress.json`でpost_id単位に生成済み投稿をスキップするが、この`/generate`（APIサーバー・Webビューア・Tampermonkeyスクリプト経由）はその進捗ファイルを一切参照しないため、同じ投稿・同じヒロインを何度でも再生成できる（一方`/batch/start`の自動バッチ生成は`database/generated_manifest.json`を見て重複をスキップする。後述）。

生成は単一のバックグラウンドワーカースレッドが優先度付きキューから順に取り出して実行する。Webビューア/Tampermonkey経由の手動`/generate`は優先度（高）、`/batch/start`の自動バッチ生成のジョブは優先度（低）で投入されるため、バッチ生成が裏で動いていても手動生成は今実行中のジョブが終わった直後に必ず割り込んで先に処理される（実行中のジョブ自体が中断されることはない）。`/generate`はPOST直後に返る`job_id`を使って`GET /jobs/{job_id}`をポーリングし、`status`が`"done"`になったら`result`フィールドに旧来の生成結果（`duration_sec`込み）が入る。`status`が`"error"`の場合は`error`フィールドにエラーメッセージが入る。ジョブ状態・バッチ状態はプロセスメモリ上にのみ保持（ジョブは最大200件、古い完了済みものから間引く）なので、サーバー再起動で消える。

### 自動バッチ生成

`POST /batch/start`にDanbooru検索クエリ（`danbooru_search_batch_generator.py`と同じ構文。`order:`/`rating:`/除外タグ等も使える）とヒロイン・モデル・artist_mode等を渡すと、その検索条件に合致する投稿を新しい順にチェックし続け、`generated_manifest.json`に記録の無いもの（かつ`config.py`の`GENERATION_BLACKLIST_TAGS`に合致しないもの）だけを優先度（低）でジョブキューに投入するワーカースレッドが起動する。検索結果を使い切ったら60秒待って新着をチェックし直す（無限ループ、Ctrl+C相当は`POST /batch/stop`）。Webビューアの「自動バッチ生成」パネルから開始・停止・進捗確認ができる。

### Webビューア

サーバー起動後、ブラウザで `http://127.0.0.1:8000/` を開くと、Danbooru投稿URLを入力して直接生成したり、生成履歴（`/images`）を一覧してカードの「🔁 再生成」ボタンから同じ設定（ヒロイン・モデル・artistタグ・NSFW・custom等）で再生成したりできる。サムネイルをクリックすると画像を拡大表示できる（もう一度クリックまたはEscで閉じる）。生成中はジョブをポーリングして進捗を待つため画面がブロックされない。生成履歴はヒロイン・モデル・期間で絞り込み、「もっと見る」でページネーションでき、各カードの「🗑 削除」から履歴・画像ファイルを削除できる。静的ファイルは [src/web/](src/web/) にある（`index.html` / `style.css` / `app.js`、追加のビルド不要）。

### Tampermonkeyスクリプト

[tampermonkey/danbooru-to-heroine.user.js](tampermonkey/danbooru-to-heroine.user.js) をTampermonkeyに登録すると、Danbooruの投稿ページ（`https://danbooru.donmai.us/posts/*`）右下にヒロイン・モデル・artistタグ・NSFW・custom生成を選べる生成パネルが表示され、その場でAPIサーバーの`/generate`を呼び出せる（内部では`/jobs/{job_id}`をポーリングして完了を待つ）。また、投稿ページ・一覧/検索結果ページ（`https://danbooru.donmai.us/posts*`）の両方で、`/generated_posts`への問い合わせにより既にヒロイン化生成済みの投稿にはサムネイル左上に「✅ 生成済み」バッジ（投稿ページではパネル上部にも通知）が表示される。

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
- 再生成前にプロンプトを手動編集できるオプション

**Tampermonkeyスクリプト**
- Danbooruの検索結果一覧ページから複数投稿をまとめて生成キューに投入する機能
- 生成キュー・進捗のパネル内表示（現状は1件ずつ同期的に待つのみ）
- API_BASEの初期値をインストール時に案内する設定UIの改善

**APIサーバー**
- 優先度（低）：認証（APIキー等）の追加。現状は`CORS_ORIGINS`のみでLAN外からの想定利用は考慮していない
- 優先度（低）：再生成失敗時の自動リトライ等の管理系エンドポイント

**設定まわり**
- チェックポイント・LoRAのプリセットを複数登録して`--checkpoint-preset`のように切り替えられるようにする

**バッチ生成**
- 優先度（低）：並列生成（現状は1件ずつ逐次処理）
- 生成失敗時の自動リトライ


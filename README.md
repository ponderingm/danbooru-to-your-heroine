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

# バックエンド指定（config.pyのGENERATION_BACKENDSに登録した構成で生成）
uv run python src/danbooru_search_batch_generator.py "micro_bikini" --backend illustrious_4step_slow
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--heroine {config.pyのHEROINESキー}` | 変換先ヒロイン（デフォルト: `config.DEFAULT_HEROINE`） |
| `--backend {config.pyのGENERATION_BACKENDSキー}` | 使用するバックエンド（モデル構文・ComfyUIエンドポイント・checkpoint/LoRA設定をまとめて選択。デフォルト: `config.DEFAULT_BACKEND`） |
| `--checkpoint` | checkpointファイル名（`--backend`側の値を上書きしたい場合のみ指定） |
| `--artist-mode {keep,override,none}` | artistタグの扱い（`keep`=元投稿優先+ヒロインの`artist_tags`にフォールバック / `override`=常にヒロインの`artist_tags` / `none`=完全除去。省略時は`--include-artist`の有無から決まる） |
| `--custom-artist TAG` | artistタグを自由記述で指定（指定時は`--artist-mode`より常に優先。`artist:`プレフィックスは省略可） |
| `--allow-multi-girl` | ヒロインが複数人登場する投稿も対象に含める |
| `--allow-realistic` | 実写・3DCG調の投稿も対象に含める |
| `--allow-blacklisted` | `config.py`の`GENERATION_BLACKLIST_TAGS`に合致する投稿も対象に含める（デフォルトはスキップ） |
| `--no-auto-canvas` | 元画像アスペクト比に合わせた自動キャンバスサイズ調整を無効化 |
| `--all` | 検索条件に合致する投稿が尽きるまで全件処理 |
| `--lucky` / `--lucky-interval` | ランダム抽出を無限ループ生成 |
| `--sort SORT` | `order:`が無い場合に自動付与する並び順 |

進捗は `database/danbooru_search_batch_progress.json` に自動保存され、`--no-resume` を付けない限り中断・再開できる。

## 生成バックエンド（config.GENERATION_BACKENDS）

モデル構文(illustrious/anima)・ComfyUIエンドポイント・checkpoint/LoRA設定を1つにまとめて名前付き登録したものが`config.GENERATION_BACKENDS`。CLIの`--backend name`、APIの`backend`パラメータ、Web UIのプルダウンで選択する（省略時は`config.DEFAULT_BACKEND`）。各バックエンドは以下を持つ:

- `label`: プルダウン等での表示名
- `model`: `illustrious` か `anima`（プロンプト構文の切り替えに使う）
- `workflow`: `default`(LoRAなしの素のKSampler) / `custom`(LoRA+可変サンプラー設定) / `anima`(Anima DiT専用構造)
- `comfy_url`: このバックエンドが向くComfyUIサーバーのURL
- `checkpoint` / `lora_name` / `steps` / `cfg` / `sampler` / `scheduler`: 各ワークフロー用の設定（省略可、省略時は対応するCUSTOM_*/ANIMA_*/DEFAULT_CHECKPOINTにフォールバック）

`comfy_url`にはそれぞれ好きなComfyUIサーバーのアドレスを設定してよい（同じアドレスを複数のバックエンドに設定してもよい）。例えば「ブラウザから逐次生成する用の高速サーバー」を使う`illustrious_fast`/`anima_fast`と、「低消費電力だが遅いバッチ生成専用サーバー」でDMD2 4-Step LoRAを使う`illustrious_4step_slow`、という3バックエンド構成が想定される（詳細は`config.example.py`のコメント・サンプル参照）。

ComfyUI関連の実処理（ワークフロー生成・送信・画像保存、および`resolve_backend()`/`build_workflow_for_backend()`/`list_backends()`によるバックエンド解決）は [src/comfy_client.py](src/comfy_client.py) にまとめられており、[src/danbooru_search_batch_generator.py](src/danbooru_search_batch_generator.py) や [src/server.py](src/server.py) はそれを呼び出すだけの構成になっている。

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

`POST /batch/start`にDanbooru検索クエリ（`danbooru_search_batch_generator.py`と同じ構文。`order:`/`rating:`/除外タグ等も使える）とヒロイン・モデル・artist_mode（custom_artistで自由記述指定も可）等を渡すと、その検索条件に合致する投稿を新しい順にチェックし続け、`generated_manifest.json`に記録の無いもの（かつ`config.py`の`GENERATION_BLACKLIST_TAGS`に合致しないもの）だけを優先度（低）でジョブキューに投入するワーカースレッドが起動する。検索結果を使い切ったら60秒待って新着をチェックし直す（無限ループ、Ctrl+C相当は`POST /batch/stop`）。Webビューアの「自動バッチ生成」パネルから開始・停止・進捗確認ができる。

- `sort`: 検索クエリに`order:`が無い場合に自動付与する並び順（例: `score`/`favcount`/`rank`）。Webビューアではプルダウンから選べる
- `lucky`: `true`にするとCLIの`--lucky`と同じ「I'm Feeling Lucky」モードになり、`sort`を無視して`random:N`でDanbooru全体から無作為抽出した投稿を無限ループで生成し続ける（Webビューアではチェックボックスで切り替え）

### Webビューア

サーバー起動後、ブラウザで `http://127.0.0.1:8000/` を開くと、Danbooru投稿URLを入力して直接生成したり、生成履歴（`/images`）を一覧してカードの「🔁 再生成」ボタンから同じ設定（ヒロイン・モデル・artistタグ・custom等）で再生成したりできる。サムネイルをクリックすると画像を拡大表示できる（もう一度クリックまたはEscで閉じる）。生成中はジョブをポーリングして進捗を待つため画面がブロックされない。生成履歴はヒロイン・モデル・期間で絞り込み、「もっと見る」でページネーションでき、各カードの「🗑 削除」から履歴・画像ファイルを削除できる。静的ファイルは [src/web/](src/web/) にある（`index.html` / `style.css` / `app.js`、追加のビルド不要）。

### Tampermonkeyスクリプト

[tampermonkey/danbooru-to-heroine.user.js](tampermonkey/danbooru-to-heroine.user.js) をTampermonkeyに登録すると、Danbooruの投稿ページ・一覧/検索結果ページ（`https://danbooru.donmai.us/posts*`）にヒロイン化生成UIが追加される。

- **投稿ページ**（右下パネル）: ヒロイン・バックエンド（`config.GENERATION_BACKENDS`から取得）・artistタグ（モード選択 + 自由記述欄。自由記述欄に入力があればモード選択より常に優先される）を選んで「生成キューに投入」を押すと、その場でAPIサーバーの`/generate`を呼び出す。生成は即座にキューへ積まれ、待たずに次の操作ができる（進捗は後述の生成キューパネルで確認）
- **一覧/検索結果ページ**（右下パネル）: サムネイル右上のチェックボックスで複数投稿を選択し、「選択した投稿をキューに投入」で一括生成できる
- **生成キューパネル**（左下、両ページ共通）: 投入した全ジョブの状態（待機中/生成中/完了/エラー）を`/jobs/{job_id}`のポーリングで表示する。`GM_setValue`で永続化されるため、ページ遷移をまたいでも履歴が残る。「🖼 ギャラリーを開く」ボタンからWebビューア（設定したAPIサーバーのURL）を新しいタブで開ける
- **生成済みバッジ**: 両ページで`/generated_posts`への問い合わせにより、既にヒロイン化生成済みの投稿にはサムネイル左上に「✅ 生成済み」バッジ（投稿ページではパネル上部にも通知）が表示される
- **接続バー**（右上、🔌）: APIサーバーのURLを設定する場所。初回起動時、または疎通確認（`/heroines`）に失敗した場合は自動的に展開され、URLの入力を促す（デフォルト `http://127.0.0.1:8000`。別ホストで動かす場合はLAN上のURLに変更する）
### スマートフォン（Android）からの利用（HTTP Shortcuts）

Android端末のブラウザ等でDanbooruを閲覧中、Androidの「共有」メニューから直接生成キューへPOSTできる。
オープンソースの [HTTP Shortcuts](https://http-shortcuts.rmen.ch/)（F-Droid / Google Play）を使用する。

#### 設定手順

1. **HTTP Shortcuts** アプリで新規ショートカットを作成（HTTP Request）
2. **基本設定**:
   - **Method**: `POST`
   - **URL**: `http://<サーバーのLAN_IP>:8000/generate`（例: `http://192.168.1.50:8000/generate`）
3. **リクエストボディ (Request Body)**:
   - **Content-Type**: `application/json`
   - **Body (JSON)**:
     ```json
     {
       "url": "{shared_text}",
       "heroine": "my_heroine"
     }
     ```
     ※ `backend` や `artist_mode` などを指定したい場合はキーを追加する。
4. **共有メニュー連携 (Share / Intent)**:
   - 設定内の **「Share Target / 共有」**（またはTrigger）を開く
   - **「Accept Shared Text」** を有効化
   - 共有テキストの格納先変数として `shared_text` を割り当てる（ブラウザから共有されたDanbooru投稿URLがここに入る）
5. **レスポンス・通知設定**:
   - **Response Handling**: Toast（トースト通知）または「何も表示しない」に設定
   - `/generate` は即座に `{"job_id": "...", "status": "queued"}` を返すため、タイムアウトを待たずに数秒でキュー投入が完了する

これで、スマホでDanbooruを見ていて「このシチュエーションで生成したい」と思った瞬間、ブラウザの **「共有」→「HTTP Shortcuts」** をタップするだけで自宅サーバーの生成キューに投入される。

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

現状は基本的なプロトタイプ（単一投稿変換・検索バッチ・APIサーバー・Webビューア・Tampermonkeyボタン）が一通り動く段階。更なるクオリティアップと拡張に向けた今後の計画・アイデア一覧。

**Webビューア & UIの洗練**
- ✅ 完了: 再生成前にプロンプトを手動編集できるオプション
- ✅ 完了: ComfyUIの生存確認表示（ヘッダーでのonline/offlineステータス）
- 優先度（高）：パージ対象タグのWebUI管理・永続化。WebUI上から除外対象タグ（`EXTRA_PURGE_TAGS` 等）を直接登録・編集・保存し、次回サーバー再起動時にも確実に反映される仕組み
- 優先度（高）：表記のシンプル化・リファイン。冗長な説明文や長文ラベルを削ぎ落とし、アイコン＋ミニマルな語句で直感的に扱えるモダンなUIへの整理
- 優先度（中）：バッチ生成の検索履歴保持・ログ機能強化。過去に実行した検索クエリの履歴保存（ワンクリック再実行）や、生成進捗・スキップ理由・エラーログの詳細表示
- 優先度（中）：ジョブキューと生成履歴のシームレスな統合（WebSocketによるリアルタイムプログレス・プレビュー表示）
- 優先度（低）：モバイル・省スペース表示へのレスポンシブ最適化

**除外ワード・タグ変換エンジンの洗練 & 対応サイト拡充**
- 優先度（高）：**タグ除外ルールの2層マージ化（Git管理Base ＋ config.yaml統合）とホットリロード**。
  - **フォーマット**: 手動エディタ編集時の快適性（コメント記述可能・`- item`形式のリスト・クォートやカンマの構文エラー回避）を重視し、JSONではなく**YAML形式**を採用。
  - **Base層（Git管理・共有資産）**: `src/rules/default_rules.yaml`。品質向上のための普遍的なノイズタグ・メタタグ・アイデンティティ分類リスト。Gitでバージョン管理され、アップデート（`git pull`）で最新知見を取り込む。
  - **User層（単一ファイル集約・.gitignore）**: `src/config.yaml`（または `config.py` からの段階的移行）。ユーザーが触る設定ファイルが分散するのを防ぐため、独自パージタグやブロックタグもこの単一YAML内のセクション（`purge_tags:` / `block_tags:`）に一元化。手動編集もWebUIからの即時書き込みもここ1箇所に集約する。
  - **マージ機構**: 実行時に Base（`default_rules.yaml`） ＋ User（`config.yaml`）を自動マージしてメモリ展開。これにより「**公式ルールのGit進化**」「**ユーザー設定の一元化**」「**手編集のしやすさ（YAML）**」「**WebUI編集の先祖返り防止**」を完全両立する。
- 優先度（高）：**タグ除外用語の体系的整理（Terminology Unification）**。現状混同されている「Blacklist / Purge / NG」を目的別に厳密に定義・リファクタリング:
  1. `Purge Tags`（プロンプト除外タグ：生成はするがプロンプトから削る。メタ情報・画面ノイズ・元キャラの身体特徴など）
  2. `Block / Skip Tags`（生成拒否タグ：元投稿に該当タグが含まれる場合、生成ジョブ自体を破棄・スキップする）
  3. `Negative Tags`（ネガティブ注入タグ：ネガティブプロンプトへ追加するタグ）
- 優先度（高）：**Gelbooru対応**。Danbooruに加えてGelbooru（`gelbooru.com`）の投稿URL・APIにも対応し、より幅広い画像ソースからタグを取得・ヒロイン変換できるようにする
- 優先度（高）：競合タグのインテリジェント自動パージ。元キャラの髪型・髪色・体型・固有装飾タグをメタデータや辞書から自動抽出し、ヒロインの特徴と衝突する要素を完全に根こそぎ除去する仕組みの強化
- 優先度（中）：除外ルール（パージタグ／ネガティブ）のカテゴリ別プリセット化（画面ノイズ系・画風競合系・メタ情報・NGシチュエーション等）
- 優先度（中）：ワイルドカードや正規表現、タグ重要度（ウェイト）の自動調整サポート
- *※なお、コスチュームや表情の高度なオーバーライドは、機械的なルール置換よりもLLMによる文脈構造化（過去のL11システム等）が適しているため、本ツールのコア機能としては深追いせず、後述の外部LLM連携側に責務を委ねる方針。*

**ComfyUI カスタムノード化**
- 優先度（高）：単体カスタムノード化（`ComfyUI-Danbooru-To-Heroine`）。外部サーバーを常駐させずとも、ComfyUIワークフロー内に直接ノードを配置して「Danbooru URL/Post ID → ヒロイン置換プロンプト出力」を直結できるようにする独立パッケージ化
- 優先度（中）：ノード上でのヒロインプリセット選択、LoRA連動切り替えのネイティブ対応

**Tampermonkeyスクリプト**
- ✅ 完了: Danbooruの検索結果一覧ページから複数投稿をまとめて生成キューに投入する機能
- ✅ 完了: 生成キュー・進捗のパネル内表示
- ✅ 完了: API_BASEの初期値を案内する接続設定バーの整備
- 優先度（中）：Gelbooru対応に伴う、Gelbooruページ上での生成ボタン・キュー連携スクリプトの提供
- 優先度（低）：投稿プレビューへのワンクリックヒロイン変換オーバーレイ

**APIサーバー & バッチ生成 & 通知**
- 優先度（高）：**Discord通知の強化（ログレベル分け ＆ 画像ペイロード添付）**
  - **レベル切り替え**: `debug`（開始・タグ変換等の詳細）、`success`（生成完了＋エラー）、`error_only`（異常時のみ通知）、`none`（無効）をYAMLで設定可能に
  - **画像の実体添付**: `multipart/form-data` を利用し、生成成功通知のDiscord Embedに生成された画像ファイルを直接添付・プレビュー表示（出先スマホのDiscordで成果物を即確認！）
- 優先度（中）：生成失敗時の自動リトライ・ComfyUI再接続ハンドリング
- 優先度（低）：並列生成（複数GPUや複数インスタンスへのディスパッチ）
- 優先度（低）：API認証（LAN外公開用のAPIキー制御）

**外部連携・発展構想（独立プロジェクト案）**
- **LLM連携：ヒロイン敗北文学 4コマ/4ステップ・ストーリージェネレーター**
  - 元投稿のDanbooruタグからシチュエーション・敵・舞台をLLMが解析し、ヒロイン敗北文学の王道4幕構成（**遭遇 → 屈服 → 快楽/絶頂 → 順応/同化**）に合わせたプロンプト差分4枚分を自動生成。
  - 生成された4つのプロンプトを本プロジェクトの `/generate` API（`prompt_override`）に連続投入し、一連の起承転結イラスト群を一撃で出力する上位オーケストレーター。
  - 本プロジェクトの「単一投稿タグのヒロイン換装エンジン」としての責務を保つため、独立した外部ツール/クライアントとして切り出して実装するのが理想的。


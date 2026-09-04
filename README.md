# danbooru-to-your-heroine (v2.0)

Danbooru / Gelbooru / AIBooru / Civitai の投稿・画像生成メタデータを解析し、設定した任意のヒロインのキャラクター特性（DNA・身体特徴・衣装・画風）に換装したプロンプトを構築して、ComfyUI経由で高品質に連続再生成するツール群。

マルチサイト対応、Base層（公式共通ルール）とUser層（個人設定）の2層マージアーキテクチャ、FastAPIバックエンド、3タブ構成のモダンWebUI、およびブラウザ拡張（Tampermonkeyスクリプト）を備える。

---

## 🌟 主な特徴

- 🌐 **マルチサイト対応**: Danbooru, Gelbooru, AIBooru, Civitai（`civitai.com/images`）のURL/IDを統一解析（[`UnifiedPost`](src/site_adapters/base.py)）。
- 🧬 **2層ルール・マージ構造**:
  - **Base層（Git管理・公式共通ルール）**: 普遍的なメタタグ・画面ノイズ除去、身体属性辞書、画風カタログ（[`src/rules/default_rules.yaml`](src/rules/default_rules.yaml)）。
  - **User層（非公開・個人設定）**: ヒロイン定義、ComfyUI接続先、個別追加パージ/ブロックタグ（[`src/config.yaml`](src/config.yaml)）。
  - 実行時に自動マージされ、サーバー再起動不要の**ホットリロード**（`/config/reload`）に対応。
- 🤖 **Booru統計解析によるヒロイン自動設定**: Danbooru / Gelbooru を横断検索し、指定キャラクターのタグ出現頻度（採用率%）から髪型・瞳・体型・衣装・代表絵師・反意ネガティブを全自動サジェスト（[`src/heroine_helper.py`](src/heroine_helper.py)）。
- 🎛️ **柔軟な実行時オーバーライド**: 胸サイズ・肌色・衣装（元絵維持 / ヒロイン衣装 / ハイブリッド）・画風（アニメ・水彩・厚塗り・レトロ等）・絵師（維持 / 固定 / 自由記述）を単一生成・バッチ生成の双方で自在に制御。
- 🖥️ **3タブ構成モダンWebUI**:
  - ⚡ **生成**: 単一生成（プレビュー＆プロンプト手動編集可能） / 検索バッチ生成（進捗監視・Lucky無限生成・強制リセット）。
  - 🖼️ **ギャラリー**: 生成履歴・拡大ライトボックス・タグ/日付/モデル絞り込み・ワンクリック再生成・削除。
  - ⚙️ **設定**: ヒロインDNA管理（2ペインエディタ＋出現頻度分析サジェスト）・除外タグ管理（タイムマシーン復元バックアップ対応）・サイト認証・Discord通知設定。
- 🐵 **Tampermonkeyスクリプト (v2.1.0)**: Danbooru / Gelbooru / AIBooru / Civitai の投稿ページ・検索一覧ページにUIを直接埋め込み、ワンクリックでキュー投入・一括投入。
- 🔔 **Discord通知エンジン**: 生成結果のEmbed通知、`multipart/form-data` による生成画像の実体添付、4段階ログレベル、バッチ時の `@silent` 制御（[`src/notify.py`](src/notify.py)）。
- 🔀 **マルチバックエンド対応**: Illustrious / Anima DiT / LoRA高速化など、モデル構文・サンプラー・サーバーURLをバックエンドIDとしてまとめて切り替え可能。

---

## 📁 ディレクトリ構成

```
danbooru-to-your-heroine/
├── README.md                           # 本ドキュメント
├── Dockerfile                          # APIサーバー・WebUI用コンテナ定義
├── docker-compose.yml                  # Docker Compose設定
├── pyproject.toml / uv.lock            # Pythonプロジェクト・依存関係定義 (uv)
├── src/
│   ├── config.py                       # 設定ローダー & ホットリロード & バックアップエンジン
│   ├── config.example.yaml             # 公開用設定テンプレート
│   ├── config.yaml                     # 個人環境設定（.gitignore対象、非公開）
│   ├── danbooru_to_heroine.py          # 投稿URL解析・プロンプト変換コアエンジン
│   ├── danbooru_search_batch_generator.py # 検索結果の連続生成バッチCLI
│   ├── comfy_client.py                 # ComfyUIワークフロー生成・送信・ポーリング
│   ├── model_adapter.py                # モデルアーキテクチャ別（illustrious/anima）構文アダプタ
│   ├── heroine_helper.py               # Booru統計解析によるヒロインDNA自動サジェスト
│   ├── notify.py                       # Discord通知エンジン（ログレベル・画像添付）
│   ├── server.py                       # FastAPI APIサーバー（ジョブキュー・各種API）
│   ├── rules/
│   │   └── default_rules.yaml          # 公式Baseルール辞書（Git管理・共有資産）
│   ├── site_adapters/                  # マルチサイト対応アダプタ群
│   │   ├── __init__.py                 # URL判別・ファクトリ関数
│   │   ├── base.py                     # UnifiedPostデータモデル & 基底クラス
│   │   ├── danbooru.py                 # Danbooru アダプタ
│   │   ├── gelbooru.py                 # Gelbooru アダプタ
│   │   ├── aibooru.py                  # AIBooru アダプタ
│   │   └── civitai.py                  # Civitai アダプタ
│   └── web/                            # モダンWebUI（静的ファイル、ビルド不要）
│       ├── index.html                  # UI構造（⚡生成 / 🖼️ギャラリー / ⚙️設定）
│       ├── style.css                   # スタイル定義
│       └── app.js                      # UIロジック・APIクライアント
├── tampermonkey/
│   └── danbooru-to-heroine.user.js     # 4サイト対応ユーザースクリプト (v2.1.0)
└── database/                           # 実行時データ・マニフェスト（.gitignore対象）
    ├── generated_manifest.json         # 生成履歴マニフェスト
    ├── danbooru_tags.csv               # オートコンプリート用タグ辞書
    └── backups/                        # 設定変更時の自動退避スナップショット（最大20世代）
```

---

## 🚀 セットアップ

本プロジェクトは Python 環境管理に `uv` を使用します。

```bash
# 1. リポジトリのクローン & 移動
git clone https://github.com/ponderingm/danbooru-to-your-heroine.git
cd danbooru-to-your-heroine

# 2. 設定ファイルの作成
cp src/config.example.yaml src/config.yaml

# 3. 依存パッケージのインストール
uv sync
```

`src/config.yaml` は個人環境設定のため `.gitignore` 対象です。外部に公開されないプライベート設定として管理されます。

---

## ⚙️ 設定ガイド (`src/config.yaml`)

設定は [`src/config.example.yaml`](src/config.example.yaml) を雛形として編集します。

```yaml
# ─── ComfyUI 接続・バックエンド設定 ───
comfyui_api_url: "http://127.0.0.1:8188"
default_checkpoint: "waiIllustriousSDXL_v160.safetensors"

backends:
  illustrious_fast:
    label: "Illustrious（高速機）"
    model: "illustrious"
    workflow: "default"
    comfy_url: "http://127.0.0.1:8188"
    checkpoint: "waiIllustriousSDXL_v160.safetensors"
  anima_fast:
    label: "Anima（高速機）"
    model: "anima"
    workflow: "anima"
    comfy_url: "http://127.0.0.1:8188"
  illustrious_4step_slow:
    label: "Illustrious 4-step LoRA"
    model: "illustrious"
    workflow: "custom"
    comfy_url: "http://127.0.0.1:8189"
    checkpoint: "waiIllustriousSDXL_v160.safetensors"
    lora_name: "your_4step_lora.safetensors"
    steps: 4
    cfg: 1.5

default_backend: "illustrious_fast"

# ─── 画像保存先 & サーバー設定 ───
output_dir: "/path/to/generated_images"
web_output_dir: "/path/to/generated_images"
api_host: "127.0.0.1"
api_port: 8899

# ─── Discord 通知設定 ───
discord:
  webhook_url: ""          # Discord Webhook URL
  notify_level: "success"  # debug | success | error_only | none
  include_image: true      # 生成画像の実体をEmbed添付するかどうか

# ─── ヒロイン定義 (DNA) ───
heroines:
  example_heroine:
    name: "サンプルヒロイン"
    identity_tags:
      - "example_character_name"
      - "example_series"
    body_tags:
      - "fair skin"
      - "medium breasts"
      - "long hair"
      - "blue eyes"
    artist_tags: []
    negative_tags:
      - "extra negative keywords"

default_heroine: "example_heroine"

# ─── ユーザー追加除外ルール ───
# プロンプトから削るタグ（画像生成は行う）
purge_tags:
  - "speech bubble"

# 生成自体を拒否・スキップするタグ（バッチ生成用）
block_tags:
  - "guro"

# Base層の除外ルールを意図的に打ち消して残したいタグ
unpurge_tags: []
```

### 🛡️ 2層ルール構造の仕組み

1. **Base層 ([`src/rules/default_rules.yaml`](src/rules/default_rules.yaml))**:
   - リポジトリでGit追跡される共有資産。
   - `meta_purge`（ID番号、翻訳文、ユーザー名等）、`artifact_purge`（モザイク、透かし、吹き出し、文字ゴミ）、身体属性一覧（`breasts`, `skin`, `hair_color`, `eye_color` 等）、画風カタログ（`art_styles`）を定義。
2. **User層 ([`src/config.yaml`](src/config.yaml))**:
   - 各自の環境固有設定。ユーザー追加の `purge_tags` や `block_tags` を定義。
3. **実効ルールのマージ計算**:
   - `実効パージタグ = (Baseメタ + Baseノイズ + Userパージ) - User除外解除(unpurge)`
   - `実効ブロックタグ = Baseブロック ∪ Userブロック`
   - WebUI上の操作でパージタグを編集・保存した際も、`src/config.yaml` に自動保存され、直前状態が `database/backups/` に世代バックアップ（最大20件）されます。

---

## 🛠️ 各ツールの使い方


### 1. `danbooru_to_heroine.py` — 単一投稿のプロンプト変換

Danbooru / Gelbooru / AIBooru / Civitai のURLからタグを抽出し、指定ヒロインに換装したプロンプトを構築・出力します。

```bash
# Danbooru の投稿をデフォルトヒロインに変換
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345

# Gelbooru / Civitai / AIBooru のURLも直接指定可能
uv run python src/danbooru_to_heroine.py https://gelbooru.com/index.php?page=post&s=view&id=67890
uv run python src/danbooru_to_heroine.py https://civitai.com/images/1234567

# 変換先ヒロインを指定
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --heroine my_heroine

# 画風(artistタグ)の指定
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --artist-mode override
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --custom-artist "artist:favorite_artist"

# JSON形式で出力
uv run python src/danbooru_to_heroine.py https://danbooru.donmai.us/posts/12345 --json
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--heroine {KEY}`, `-H` | 変換先ヒロイン（デフォルト: `config.DEFAULT_HEROINE`） |
| `--include-artist` | artist:タグをプロンプトに含める（デフォルトは除外） |
| `--artist-mode {keep,override,none}` | 絵師タグの扱い（`keep`: 元絵優先 / `override`: ヒロイン代表絵師 / `none`: 除去） |
| `--custom-artist {TAG}` | 絵師タグを自由記述で指定（`--artist-mode` より優先） |
| `--json` | 結果をJSON形式で出力 |
| `--verbose`, `-v` | 詳細ログを表示 |

---

### 2. `danbooru_search_batch_generator.py` — 検索結果を連続生成

Danbooru の検索結果を順次取得し、ヒロイン換装を行ってComfyUIへ生成ジョブを自動投入します。

```bash
# 通常の検索バッチ生成（1ページ20件）
uv run python src/danbooru_search_batch_generator.py "micro_bikini" --limit 20 --pages 1

# order:/rating:/除外タグ(-tag)を含む複合検索
uv run python src/danbooru_search_batch_generator.py "order:score rating:explicit micro_bikini beach 1girl" --limit 10

# 検索条件に合致する投稿が尽きるまで全件処理
uv run python src/danbooru_search_batch_generator.py "order:favcount swimsuit -competition_swimsuit" --all

# I'm Feeling Lucky モード（無作為抽出を無限ループ生成）
uv run python src/danbooru_search_batch_generator.py "rating:explicit" --lucky

# バックエンドを指定して生成
uv run python src/danbooru_search_batch_generator.py "micro_bikini" --backend illustrious_4step_slow
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--heroine {KEY}` | 変換先ヒロイン（デフォルト: `config.DEFAULT_HEROINE`） |
| `--backend {KEY}` | 使用するバックエンドID（デフォルト: `config.DEFAULT_BACKEND`） |
| `--checkpoint {FILE}` | checkpointファイル名を一時上書き |
| `--artist-mode {keep,override,none}` | 絵師タグの扱い（`keep`: 元絵優先 / `override`: ヒロイン代表絵師 / `none`: 除去） |
| `--custom-artist {TAG}` | 絵師タグを自由記述で指定（`--artist-mode` より優先） |
| `--allow-multi-girl` | 複数ヒロイン登場投稿（`2girls` 等）も対象に含める |
| `--allow-realistic` | 実写・3DCG調の投稿も対象に含める |
| `--allow-blacklisted` | `block_tags` に合致する投稿もスキップせず処理する |
| `--no-auto-canvas` | 元画像アスペクト比に応じた自動解像度計算を無効化し、`--width`/`--height` を固定使用 |
| `--all` | 検索結果が尽きるまで全件処理する |
| `--lucky` / `--lucky-interval` | ランダム抽出の無限ループ生成 |
| `--sort {SORT}` | 検索式に `order:` が無い場合に自動付与するソート順（`score`, `favcount`, `rank` 等） |
| `--no-resume` | `database/danbooru_search_batch_progress.json` の進捗を無視して先頭から実行 |

進捗は `database/danbooru_search_batch_progress.json` に自動保存され、`--no-resume` を付けない限り中断・再開が可能です。

---

## 🔀 生成バックエンド（`backends`）

モデル構文（illustrious / anima）・ComfyUIエンドポイント・checkpoint/LoRA設定を1つにまとめて名前付き登録したものが `backends` です。CLIの `--backend`、APIの `backend` パラメータ、WebUIのプルダウンから選択できます。

- `label`: 表示名
- `model`: `illustrious` または `anima`（プロンプト構文やrating制御の切り替え）
- `workflow`: `default` (LoRAなし標準KSampler) / `custom` (LoRA+可変サンプラー設定) / `anima` (Anima DiT専用構造)
- `comfy_url`: このバックエンドが接続するComfyUIサーバーのURL
- `checkpoint` / `lora_name` / `steps` / `cfg` / `sampler` / `scheduler`: ワークフロー固有の設定

ComfyUI関連の実処理（ワークフロー生成・送信・画像保存、およびバックエンド解決）は [`src/comfy_client.py`](src/comfy_client.py) に集約されています。

---

### 3. `server.py` — APIサーバー ＆ WebUI

[`src/danbooru_to_heroine.py`](src/danbooru_to_heroine.py) のコア変換ロジックと [`src/comfy_client.py`](src/comfy_client.py) の生成エンジンをFastAPI経由で提供するサーバーです。WebUIの静的ファイル配信、ジョブキュー、履歴配信、パージ管理、ホットリロード、Discordテスト送信などを行います。

```bash
# サーバー起動 (config.yaml の api_host / api_port を使用)
uv run python src/server.py

# または uvicorn 直接起動
uv run uvicorn server:app --app-dir src --host 0.0.0.0 --port 8899 --reload
```

#### 主要 API エンドポイント一覧

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/` | WebUI（3タブ構成コンソール） |
| `GET` | `/heroines` | 登録ヒロインのキー一覧を取得 |
| `GET` | `/heroines/details` | 登録ヒロインの詳細設定（DNA辞書）を取得 |
| `POST` | `/heroines/analyze` | キャラクタータグからBooru出現頻度を統計解析しヒロイン設定をサジェスト |
| `POST` | `/heroines/save` | ヒロイン定義を保存・更新（`config.yaml` に永続化） |
| `DELETE` | `/heroines/{key}` | 指定ヒロインを削除 |
| `POST` | `/convert` | URLから換装プロンプトを構築（画像生成なし・プレビュー用） |
| `POST` | `/generate` | 優先度付きキューへ画像生成ジョブを投入（即座に `job_id` を返却） |
| `GET` | `/jobs/{job_id}` | ジョブの状態（`queued`/`running`/`done`/`error`）と結果を取得 |
| `GET` | `/images` | 生成済み履歴（マニフェスト）。ヒロイン・モデル・日付・タグ絞り込み対応 |
| `DELETE` | `/images/{entry_id}` | 生成履歴エントリおよび画像実体を削除 |
| `POST` | `/generated_posts` | 指定投稿ID群が生成済みかどうかを一括判定（拡張機能のバッジ用） |
| `POST` | `/batch/start` | 検索条件に基づく自動バッチ生成ワーカーを開始 |
| `POST` | `/batch/stop` | 自動バッチ生成ワーカーを停止 |
| `POST` | `/batch/reset` | バッチワーカー状態の強制リセット |
| `GET` | `/batch/status` | 自動バッチ生成の進行状況を取得 |
| `GET` | `/backends` | 有効なバックエンド構成一覧を取得 |
| `GET` | `/comfy/status` | ComfyUIサーバーの死活監視ステータスを取得 |
| `GET` | `/purge_tags` | パージタグ一覧（Base/User/Unpurge統合）を取得 |
| `POST` | `/purge_tags` | パージタグを更新・自動バックアップ退避 |
| `GET` | `/purge_tags/backups` | パージタグの世代バックアップ一覧を取得 |
| `POST` | `/purge_tags/restore` | 過去のバックアップスナップショットから設定を復元 |
| `POST` | `/config/reload` | `src/config.yaml` を再読込しホットリロード |
| `GET` / `POST` | `/config/notification`| Discord通知設定（Webhook URL・ログレベル等）の取得・更新 |
| `POST` | `/notify/test` | Discord通知の疎通テスト送信 |
| `GET` / `POST` | `/config/site_auth` | 各サイト（Danbooru/Gelbooru/Civitai）の認証APIキー設定の取得・更新 |
| `GET` | `/output/{filename}` | 生成画像の静的ファイル配信 |

#### 優先度付きキュー機構
単一のバックグラウンドワーカースレッドが優先度付きキューから順に取り出して処理します。
- **優先度（高）**: WebUI / Tampermonkey / スマホからの手動 `/generate`
- **優先度（低）**: `/batch/start` による自動バッチ生成
バッチ生成が裏で稼働していても、手動生成は現在実行中のジョブが完了した直後に最優先で割り込み処理されます。

---

## 💻 WebUI コンソール機能紹介

ブラウザで `http://127.0.0.1:8899/` を開いて利用します。ヘッダー右上にComfyUIの死活監視ステータス（online / offline / error）がリアルタイム表示されます。

### 1. ⚡ 生成タブ (Generate)
- **単一生成**:
  - Danbooru / Gelbooru / AIBooru / Civitai のURLを入力。
  - ヒロイン、バックエンドを選択。
  - **🎛️ オプション（一時オーバーライド）**:
    - 🍒 胸サイズ: デフォルト / 🔒 ヒロイン固定 / 🎨 元絵維持
    - ☀️ 肌色: デフォルト / 🔒 ヒロイン固定 / 🎨 元絵維持
    - 👗 衣装: デフォルト / 👗 元絵衣装 / 🦸 ヒロイン衣装 / ✨ ハイブリッド
    - 🖌️ 画風: 元絵維持 / アニメ調 / モノクロ漫画 / 水彩 / 厚塗り / 90年代風 / ちび / ドット絵
    - 🧑‍🎨 絵師: `none` / `keep` / `override` / 作家名自由入力（入力履歴オートコンプリート）
  - 「👁 プレビュー / 手動編集」: 生成前に構築プロンプトを確認し、手動で加筆・修正したプロンプトで生成可能。
  - 「⚡ 生成キューに投入」: 即座にジョブキューへ投入され、画面をブロックせずに待機。
- **自動バッチ生成**:
  - 検索クエリ、並び順（`score`/`favcount` 等）、I'm Feeling Lucky（無作為抽出ループ）を指定して自動実行。
  - 進行状況・生成枚数・エラー表示、およびワーカーの「強制リセット」に対応。

### 2. 🖼️ ギャラリータブ (Gallery)
- 生成画像のグリッド表示（無限スクロール / 「もっと見る」）。
- ヒロイン、モデル、日付範囲（開始日〜終了日）、タグによる多角的絞り込み。
- サムネイルクリックによる拡大モーダル（プロンプト全文・所要時間・元URL・メタデータ表示）。
- 「🔁 再生成」ボタンで、当時の設定を完全再現して即座に再生成。
- 「🗑 削除」ボタンで履歴エントリおよび生成画像本体を削除。

### 3. ⚙️ 設定タブ (Settings)
- **👸 ヒロイン管理・DNA**:
  - 登録済みヒロインのマスターディテール2ペインエディタ。
  - **🤖 Booruタグ出現頻度分析ヘルパー**: キャラクタータグ名を入力して検索するだけで、Booru上の頻出タグ（採用率%）から髪・瞳・肌・胸・衣装・代表絵師・反意ネガティブを自動解析し、ワンクリックで新規ヒロインとして登録可能。
- **🛡️ 除外タグ・品質ルール**:
  - Base層とUser層のマージ結果をカテゴリ別に確認。
  - パージタグの追加・削除と即時反映。
  - **タイムマシーン復元**: 設定保存時に自動作成される最大20世代のバックアップ一覧から、過去の状態へいつでも復元可能。
- **🔑 サイト認証・APIキー**:
  - Danbooru / Gelbooru / Civitai の認証キーをWebUI上から管理。
- **🔔 通知・システム設定**:
  - Discord Webhook URL、ログレベル（`debug`/`success`/`error_only`/`none`）、画像添付トグル。
  - 「🧪 テスト通知を送信」ボタンで接続テスト。
  - 「🔄 設定をホットリロード」でサーバーを落とさずに最新設定を再読込。

---

## 🐵 ブラウザ拡張機能 (Tampermonkey)

[`tampermonkey/danbooru-to-heroine.user.js`](tampermonkey/danbooru-to-heroine.user.js) をブラウザにインストールすると、イラストサイト上で直接ヒロイン換装キューへ投入できます。

### 対応サイト
- **Danbooru**: `https://danbooru.donmai.us/posts*`
- **Gelbooru**: `https://gelbooru.com/*`
- **AIBooru**: `https://aibooru.online/posts*`
- **Civitai**: `https://civitai.com/images*`

### 提供される機能
- **個別投稿ページ**: 画面右下にフローティングパネルを展開。ヒロイン・バックエンド・絵師モードを選んで「生成キューに投入」。
- **一覧/検索結果ページ**: サムネイル右上にチェックボックスが付き、複数選択して「選択した投稿をキューに投入」で一括生成。
- **生成キューパネル（左下）**: 投入した全ジョブの進捗状態をリアルタイム表示。`GM_setValue` によりページ遷移しても進捗が維持されます。
- **生成済みバッジ**: 既に生成履歴に存在する投稿にはサムネイル上に「✅ 生成済み」バッジが自動付与。
- **接続設定バー（右上 🔌）**: APIサーバーのURL（デフォルト: `http://127.0.0.1:8899`）を設定・確認。

---

## 📱 スマートフォン連携 (HTTP Shortcuts)

Android 端末のブラウザ等でイラストを閲覧中、共有メニューからワンタップで自宅サーバーの生成キューへPOSTできます。

1. **HTTP Shortcuts**（F-Droid / Google Play）をインストール。
2. 新規ショートカットを作成:
   - **Method**: `POST`
   - **URL**: `http://<サーバーのLAN_IP>:8899/generate`
   - **Request Body (JSON)**:
     ```json
     {
       "url": "{shared_text}",
       "heroine": "example_heroine"
     }
     ```
3. **共有メニュー連携**:
   - 設定の「Share Target」を開き、「Accept Shared Text」を有効化。
   - 共有テキストの格納先に `{shared_text}` を割り当て。
4. ブラウザで作品を表示中に **「共有」→「HTTP Shortcuts」** を選ぶだけで、数秒で自宅サーバーのキューに積まれます。Discord通知を有効にしておけば、完成した画像がスマホに届きます。

---

## 🐳 Docker 環境での運用

```bash
# 1. 設定ファイルの準備
cp src/config.example.yaml src/config.yaml

# 2. Docker Compose で起動
docker compose up --build -d
```

- Linux環境では `network_mode: host` を使用しているため、ホスト上の ComfyUI（`127.0.0.1:8188`）にそのまま到達できます。
- Mac / Windows 環境等では `docker-compose.yml` の `network_mode: host` を削除して `ports: ["8899:8899"]` を有効化し、`src/config.yaml` の `api_host` を `"0.0.0.0"`、`comfyui_api_url` を `http://host.docker.internal:8188` に設定してください。

---

## 🗺️ 開発ロードマップ

- ✅ **完了**: タグ除外ルールの2層マージ化（Base層: `default_rules.yaml` ＋ User層: `config.yaml`）とホットリロード
- ✅ **完了**: タグ除外用語の体系的整理（`purge_tags` / `block_tags` / `unpurge_tags`）
- ✅ **完了**: マルチサイト対応（Gelbooru / AIBooru / Civitai アダプタ統合）
- ✅ **完了**: Discord通知エンジン（4段階ログレベル ＆ 生成画像実体のEmbed添付）
- ✅ **完了**: WebUIでの除外タグ管理 ＆ タイムマシーン復元（世代バックアップ）
- ✅ **完了**: Booru統計解析によるヒロインDNA自動サジェスト（`heroine_helper.py`）
- ✅ **完了**: 一時オーバーライド制御（胸・肌・衣装・画風・絵師）
- ✅ **完了**: ComfyUI死活監視ステータス表示
- ✅ **完了**: Tampermonkeyスクリプトの4サイト対応 (v2.1.0)
- 📌 **今後の検討・拡張アイデア**:
  - **ComfyUI カスタムノード化 (`ComfyUI-Danbooru-To-Heroine`)**: 外部サーバーを起動せず、ComfyUIワークフロー内でURL/IDから直接ノード上でヒロイン置換を行う単体パッケージ化。
  - **生成失敗時の自動リトライ・再接続機構**: ネットワーク瞬断やComfyUI一時エラーに対する自動復帰ハンドリング。
  - **複数GPU / 複数インスタンスへのディスパッチ**: バックエンドごとのキュー並列分散処理。
  - **外部LLM連携オーケストレーター**: 元投稿のシチュエーションを解析し、連続プロンプト差分を生成してストーリー展開を一撃で出力する上位クライアントの連携。


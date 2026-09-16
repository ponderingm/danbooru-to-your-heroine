# 🚀 danbooru-to-your-heroine v2.0 リリースノート・アップデート総括

- **バージョン**: v2.0 (Stable Release)
- **リリース日**: 2026-09-16
- **対象ブランチ**: `master` (merged from `v2-beta`)

---

## 1. 🌟 v2.0 のコアコンセプト

v1系が持っていた「Danbooruのタグ置換と単一生成」から大幅に進化し、**「マルチサイト対応」「2層ルール分離アーキテクチャ」「モダンWebUI」「自動バッチ生成パイプライン」「ブラウザ拡張連携」**を統合した、本格的なローカルAI画像生成プラットフォームへと刷新されました。

---

## 2. 📋 主なアップデート内容

### 🌐 1. マルチサイト対応アダプタ群 (Site Adapters)
- **4サイト横断対応**:
  - **Danbooru** ([`src/site_adapters/danbooru.py`](../src/site_adapters/danbooru.py))
  - **Gelbooru** ([`src/site_adapters/gelbooru.py`](../src/site_adapters/gelbooru.py))
  - **AIBooru** ([`src/site_adapters/aibooru.py`](../src/site_adapters/aibooru.py))
  - **Civitai** ([`src/site_adapters/civitai.py`](../src/site_adapters/civitai.py))
- **統一データモデル ([`UnifiedPost`](../src/site_adapters/base.py))**: サイトごとの差異（API構造、タグ体系、レーティング表現）を正規化。
- **Civitai 生成メタデータ解析**: `civitai.com/images` の投稿から ComfyUI / Stable Diffusion WebUI の生生成パラメータ（Prompt, Negative, Sampler, Seed）を直接抽出。
- **Gelbooru 高精度HTMLスクレイピングフォールバック**: APIのフラットタグ返却制限に対し、HTML構造からキャラクター・作品・絵師タグを高精度に分離し完全パージ。

### 🧬 2. 2層ルール分離アーキテクチャ (Base層 ＋ User層)
- **Base層（Git管理・共有資産）**: [`src/rules/default_rules.yaml`](../src/rules/default_rules.yaml)
  - 普遍的なメタタグ（`bad source`, `watermark`, `commentary` 等）のパージ辞書。
  - 画面ノイズ除去、身体属性衝突辞書、豊富な画風プリセット定義。
- **User層（非公開・個人環境）**: `src/config.yaml`
  - ヒロインDNA定義、ComfyUI接続先、個人固有の追加除外タグ（`user_purge_tags` / `user_block_tags`）。
  - `.gitignore` による完全な秘匿情報保護。
- **ホットリロード＆自動バックアップ**:
  - サーバー稼働中に `POST /config/reload` で設定を即時再読込（サーバー再起動不要）。
  - 設定保存時に最大20世代の自動スナップショットを退避し、WebUIからワンクリックで過去状態へ復元できる「タイムマシーン復元」を実装。

### 🤖 3. ヒロインDNA管理 ＆ Booru統計解析ヘルパー
- **3層カテゴリ分離**: 顔・髪（Face）、身体特徴（Body）、衣装（Costume）を独立定義。
- **出現頻度分析サジェスト ([`src/heroine_helper.py`](../src/heroine_helper.py))**:
  - キャラクタータグを入力するだけで、Danbooru / Gelbooru から出現頻度（採用率%）を統計解析。
  - 代表的な髪型・瞳・体型・衣装・絵師・反意ネガティブを全自動判定し、新規ヒロインとしてワンクリック登録。

### 🎛️ 4. 柔軟な実行時オーバーライド (Runtime Options)
- 単一生成・自動バッチ生成の両方で、元絵の要素とヒロインの要素をきめ細かく制御可能:
  - **胸サイズ**: デフォルト / 🔒 ヒロイン固定 / 🎨 元絵維持
  - **肌色**: デフォルト / 🔒 ヒロイン固定 / 🎨 元絵維持
  - **衣装**: デフォルト / 👗 元絵衣装 / 🦸 ヒロイン衣装 / ✨ ハイブリッド
  - **画風**: 元絵維持 / アニメ調 / モノクロ漫画 / 水彩 / 厚塗り / 90年代風 / ちび / ドット絵
  - **絵師**: `none` / `keep` / `override` / 作家名自由入力（入力履歴オートコンプリート）

### 🖥️ 5. 3タブ構成モダンWebUIコンソール
- **⚡ 生成タブ (Generate)**:
  - 単一生成: リアルタイムプレビュー＆手動プロンプト編集機能。
  - 自動バッチ生成: 複数条件AND検索、並び順指定、進捗監視、I'm Feeling Lucky（無作為抽出ループ）、強制リセットボタン。
- **🖼️ ギャラリータブ (Gallery)**:
  - 無限スクロール対応の履歴グリッド、ヒロイン・モデル・日付・タグ絞り込み。
  - 拡大ライトボックス（プロンプト全文・所要時間・元URL表示）、ワンクリック再生成、削除機能。
- **⚙️ 設定タブ (Settings)**:
  - 2ペインマスターディテール方式のヒロインDNA管理。
  - 除外タグ管理とタイムマシーン世代復元。
  - サイト認証キー（Danbooru/Gelbooru/Civitai）およびDiscord通知のWebUI設定。
- **ComfyUIリアルタイム死活監視**: ヘッダー右上に接続ステータス（online / offline / error）を表示。

### 🐵 6. ブラウザ拡張機能 (Tampermonkey v2.1.0)
- [`tampermonkey/danbooru-to-heroine.user.js`](../tampermonkey/danbooru-to-heroine.user.js)
- Danbooru / Gelbooru / AIBooru / Civitai の4サイトに対応。
- 個別投稿ページでの生成パネル埋め込み、検索一覧での複数選択一括投入。
- `GM_setValue` を用いたページ遷移をまたぐキュー常駐パネル。
- `POST /generated_posts` APIによる「✅ 生成済み」バッジ表示。

### ⚡ 7. 優先度付きジョブキュー ＆ 安定化
- **割り込み優先制御**: 手動生成（高優先度）がバッチ生成（低優先度）に即座に割り込むスマートキュー設計。
- **マルチバックエンド対応**: Illustrious / Anima DiT などの構文やサンプラー定義をID単位で一括切り替え。
- **モザイク・検閲タグ対策**: Turboモデル（CFG 1.0）の数式特性や絵師タグ共起の分析に基づき、プロンプト処理とネガティブ注入を最適化。

### 🔔 8. Discord通知エンジン
- 生成完了時のEmbed通知および画像実体の `multipart/form-data` 添付。
- 4段階ログレベル（`debug` / `success` / `error_only` / `none`）。
- バッチ生成時の `@silent`（プッシュ通知音抑制）制御。

---

## 3. 🔮 次期バージョン（v3.0）へのロードマップ

v2.0 ではシステムのコア機能と安定運用基盤が完成しました。以下のテーマは **次期メジャーアップデート（v3.0）** の主軸として開発を推進します。

1. **🧠 LLM連携＆共起の輪のフロントエンド本格統合**:
   - v2.0で先行開発された自然言語変換エンジン（[`src/natural_to_danbooru.py`](../src/natural_to_danbooru.py)）および共起ファインダー（[`src/cooccurrence_finder.py`](../src/cooccurrence_finder.py)）を、WebUIやバッチ生成パイプラインへUIとして直接統合。
   - 「自然言語プロンプトからの一発シチュエーション生成」や「共起の輪タグレコメンド」のUI実装。
2. **🧩 汎用アドオン・フレームワーク（Generic Addon Framework）**:
   - 衣装（Costumes）、MGE種族（魔物娘図鑑）、シチュエーション等の外部概念データベースをホットリロード可能なプラグインパックとして統一管理（詳細は [`docs/costume_addon_design_spec.md`](../docs/costume_addon_design_spec.md) 参照）。
3. **📦 ComfyUI カスタムノード化 (`ComfyUI-Danbooru-To-Heroine`)**:
   - ComfyUI単体内で完結するカスタムノードパッケージの提供。

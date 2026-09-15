# 実装TODO: Ranbell Image フォーク＆リッチギャラリー統合計画

## 🎯 目的
[Ranbell Image](https://github.com/ranbell/ranbell_image) をフォークし、`danbooru_yukikaze_tool` の生成画像・カタログをセマンティック検索・Danbooruタグ共起分析・カラー検索できる専用リッチギャラリー（Web UI）として稼働させる。さらに、RanbellのUIから直接ヒロイン置換・再生成をトリガーできるシームレスな統合を実現する。

---

## 📋 フェーズ別ロードマップ

### Phase 1: GitHub フォーク & ローカル動作検証
- [ ] **1-1. リポジトリのフォーク**:
  - `ranbell/ranbell_image` を `ponderingm/ranbell_image` にフォーク。
  - Raspberry Pi 上（`/home/pi/ranbell_image` 等）にクローン。
- [ ] **1-2. WD14 の無効化・軽量化設定**:
  - WD14モデルのダウンロードと推論パイプラインをバイパス。
  - Qdrant の ARM64 動作確認。
  - ComfyUI の接続先をリモートGPUサーバー（ポート 8188）に設定。
  - Ollama の接続先をリモートGPUサーバー（ポート 11434）に設定し、`embeddinggemma:300m` の導通確認。
- [ ] **1-3. 疎通テスト**:
  - `docker compose up -d` でコンテナ起動。
  - `http://localhost:3100` で管理診断画面のパスを確認（WD14なしで正常稼働することを確認）。

---

### Phase 2: データ連携（メタデータ直接インポート & 自動インデックス）
- [ ] **2-1. 生成画像ディレクトリのマウント設定**:
  - `danbooru_yukikaze_tool` の生成画像出力先（`OUTPUT_DIR`）を Ranbell の `/mnt/image/source/heroine_archive:ro` としてマウント。
- [ ] **2-2. 正解タグ直接インポート（WD14スキップ）の実装**:
  - `danbooru_yukikaze_tool` の `database/generated_manifest.json`（またはPNGメタデータ）から、正解Danbooruタグ（キャラ/衣装/シチュエーション/絵師等）とプロンプト情報を直接読み出し、Qdrantペイロードへ一括登録するインジェスターを作成。
  - **必須サニタイズ処理**:
    - **メタタグ・品質修飾タグの剥ぎ取り**: `rules/default_rules.yaml` の `meta_purge`（`translated`, `commentary`, `bad id`, `highres` 等）およびモデル品質タグ（`score_9`, `masterpiece` 等）を自動除去し、純粋な視覚コンテンツタグのみを抽出。
    - **実ファイル存在確認＆消失スキップ**: マニフェストに記録されていてもディスク上（`OUTPUT_DIR`）にファイルが存在しない・サイズ0の画像は確実にスキップ。過去に登録されて後に削除された画像はQdrantから削除（ガベージコレクション）。
  - 100%正確なタグ情報による高速インデックス化（推論ゼロ、数秒で完了）を検証。
- [ ] **2-3. ギャラリー検証**:
  - ギャラリーUIで Danbooru タグ絞り込み、セマンティック検索、カラー検索が正しく機能することを確認。
  - 画像リンク切れや不要なメタタグ（translated等）が表示されていないことを確認。
- [ ] **2-4. 自動取り込み（バックフィル）設定**:
  - 新規生成画像が追加された際の自動検知・インポート設定。

---

### Phase 3: ヒロイン置換・再生成アクションのカスタム統合
- [ ] **3-1. Ranbell 側フロントエンド（Vue 3）のカスタム**:
  - 画像詳細モーダル（Detail View）に「⚡ ヒロイン変換で再生成」「🔁 プロンプト再生成」ボタンを新設。
- [ ] **3-2. API ブリッジの実装**:
  - Ranbell バックエンド（FastAPI）に `danbooru_yukikaze_tool` へのプロキシエンドポイントを追加、またはフロントエンドから直接 `http://127.0.0.1:8899/generate` / `/convert` を叩けるよう CORS を確認。
  - 元の Danbooru Post ID やタグ情報を `danbooru_yukikaze_tool` に送信し、ワンクリックでヒロイン置換パイプラインに投入。
- [ ] **3-3. コントロールルーム連携**:
  - `danbooru_yukikaze_tool` のジョブキュー進捗を Ranbell のコントロールルームまたはステータスバーに表示できるか検証。

---

### Phase 4: Coolify 自動デプロイ & 外部アクセス
- [ ] **4-1. Coolify アプリケーション登録**:
  - GitHub `ponderingm/ranbell_image` と Coolify を連携し、プッシュ自動ビルド環境を構成。
  - 必要な永続ボリューム（Qdrant データ、設定ファイル）とストレージバインドマウント（画像フォルダ）を設定。
- [ ] **4-2. 独自ドメイン & 認証連携**:
  - Cloudflare Zero Trust の背後で `*.hannya.org`（例: `gallery.hannya.org`）として安全に公開。
- [ ] **4-3. 動作完了レビュー**:
  - PCおよびスマートフォンからの快適なブラウジングと生成トリガーの動作を確認。

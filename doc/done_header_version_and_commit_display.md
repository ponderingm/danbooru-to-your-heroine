# 完了報告: WebUIヘッダーへの動的バージョン・Gitコミット・PRプレビュー表示機能の実装

## 1. 概要
WebUIヘッダーが従来の静的な「v2.0」表記のままとなっており、プレビュー環境（PR #1）や最新のv3.0アーキテクチャ稼働状態が判別しづらかった問題を解決するため、サーバーおよびクライアントの動的バージョン情報連携機構を構築した。

---

## 2. 実装内容

### 1. サーバー側: `/version` エンドポイントの実装 ([`src/server.py`](file:///home/pi/danbooru_yukikaze_tool/src/server.py))
- **提供情報**:
  - `version`: アプリケーションバージョン（`v3.0.0`）
  - `commit` / `full_commit`: Gitコミットハッシュ（短縮7文字 / 完全40文字）
    - Coolifyの提供する環境変数 `SOURCE_COMMIT` またはホスト上の `git rev-parse HEAD` から自動解決
  - `branch`: Gitブランチ名（`COOLIFY_BRANCH` または `git rev-parse --abbrev-ref HEAD`）
  - `is_preview`: PRプレビュー環境かどうかの真偽値判定
  - `pr_id`: プルリクエスト番号（例: `1`）
  - `repo_url` / `commit_url` / `pr_url`: GitHubへの直通リンクURL
- **定数化・分離**: ルール5に基づき、定数（`APP_VERSION`, `REPO_URL`, `GIT_TIMEOUT_SEC`）をファイル冒頭に集約。

### 2. クライアント側: 動的バッジ描画 & Cache-Busting ([`src/web/app.js`](file:///home/pi/danbooru_yukikaze_tool/src/web/app.js), [`src/web/index.html`](file:///home/pi/danbooru_yukikaze_tool/src/web/index.html), [`src/web/style.css`](file:///home/pi/danbooru_yukikaze_tool/src/web/style.css))
- **`loadVersionInfo()`**:
  - ページ読み込み時に `/version` を取得し、ヘッダーバッジと `document.title` を動的更新。
  - プレビュー環境の場合:
    - 表示: `v3.0 PR#1 (b3c3d9b)`
    - スタイル: アンバーカラーの `.version-badge.preview`（プレビューであることが一目瞭然）
    - 各リンクをクリックすると GitHub の PR ページやコミット詳細ページへ直接遷移可能。
  - 本番環境の場合:
    - 表示: `v3.0 (コミットハッシュ)`（パープルカラー）
- **Cache-Busting (ルール7)**:
  - `index.html` 内の `style.css?v=20260916_1730` および `app.js?v=20260916_1730` にクエリパラメータを更新し、ブラウザキャッシュを即座に破棄。

### 3. 自動テストの配備 ([`tests/test_version_endpoint.py`](file:///home/pi/danbooru_yukikaze_tool/tests/test_version_endpoint.py))
- `get_version()` 関数の単体テストを作成し、既存の6件のプロンプトテストと合わせた計7件のテストが正常パスすることを確認。

---

## 3. 動作検証
- ホスト環境での `get_version()` テスト: PASS (`v3.0.0`, short commit, branch 取得正常)
- プレビューコンテナのバインドマウント経由での `index.html` 配信: HTTP 200 OK (`danbooru-to-your-heroine v3.0` の即時反映を確認)

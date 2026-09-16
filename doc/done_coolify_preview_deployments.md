# 完了報告: Coolify Preview Deployments（PRプレビュー環境）の構築と動作確認

## 1. 概要
GitHub 上でのプルリクエスト（PR）作成・更新時に、Coolify が自動的に一時的なプレビュー環境（Preview Deployment）をビルド・起動し、動作検証が行えるパイプラインを構築・実証した。

---

## 2. 実施内容

### 1. Coolify アプリケーション設定の更新
- **対象アプリケーション**: `danbooru-to-your-heroine` (UUID: `n7ego2hxamt39iv9bt44gdtg`)
- **ベースブランチ**: `master`
- **GitHub連携**: GitHub App (`coolify-hannya`)
- **Preview Deployments 有効化**:
  - `is_preview_deployments_enabled`: `true`
  - `is_pr_deployments_public_enabled`: `true`
  - `preview_url_template`: `{{pr_id}}.{{domain}}` ➜ `http://{{pr_id}}.danbooru.hannya.org`

### 2. GitHub Webhook の連携
- リポジトリ `ponderingm/danbooru-to-your-heroine` に Coolify イベント受信用 Webhook を配備。
  - 対象イベント: `push`, `pull_request`
  - エンドポイント: `https://manage.hannya.org/webhooks/source/github/events/manual`

### 3. ボリュームマウント（Storages）の最適化
- **課題**: Coolifyのデフォルト挙動では、プレビュー環境のボリュームパスに `-pr-N` サフィックス（例: `src/config.yaml-pr-1`）が付与され、ホスト側にファイルがないためDockerが空ディレクトリとして自動作成してしまい、設定ファイル（`config.yaml`）やWebUI静的ファイル（`web/`）がマウント不能になる問題が発生。
- **解決策**: 各ボリューム（`LocalPersistentVolume`）の `is_preview_suffix_enabled` を `false` に設定。プレビュー環境でもホスト側の `src/config.yaml`、`src/web`、`database`、外部画像ディレクトリがそのまま安全にバインドマウントされるよう改修。

---

## 3. 実証結果

### プルリクエスト
- **PR #1**: [feat(v3): Heroine DNA structuring, slot-driven mutation & multi-subject separation](https://github.com/ponderingm/danbooru-to-your-heroine/pull/1)

### プレビュー環境ステータス
- **Preview URL**: [http://1.danbooru.hannya.org](http://1.danbooru.hannya.org)
- **コンテナ名**: `n7ego2hxamt39iv9bt44gdtg-pr-1`
- **HTTP ステータス**: **`200 OK`**
- **エンドポイント検証**:
  - `/` (WebUIフロントエンド): 正常表示
  - `/heroines` (API): v3スロット構造化された全ヒロイン定義が正常応答
  - `/backends` (API): GPD ComfyUI バックエンドがオンライン認識

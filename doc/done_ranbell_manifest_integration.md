# 実装完了: Danbooru to Your Heroine 生成ログベースの Ranbell Image データベース構築

## 実施日
2026-09-15

## 概要
OSS AI画像ビューア「Ranbell Image」をフォークしたプライベートリポジトリ（`ponderingm/ranbell_image`）において、ディスク上の全ファイル（約1.7万枚）を無差別に走査するのではなく、`danbooru_yukikaze_tool` の生成ログ（`generated_manifest.json`、5,388件）を真実のソース（Source of Truth）としてQdrantデータベースを構築・インポートする機能を実装し、Coolify上で本番稼働させました。

---

## 主な実装内容

### 1. マニフェスト（生成ログ）連携 & ボリュームマウント
- `docker-compose.yml` / `docker-compose.yaml` において、ホスト側のマニフェストファイルを backend コンテナにマウント：
  `- /home/pi/danbooru_yukikaze_tool/database/generated_manifest.json:/mnt/manifest/generated_manifest.json:ro`
- 環境変数 `MANIFEST_PATH=/mnt/manifest/generated_manifest.json` を設定。
- `backend/app/config.py` に `manifest_path: Path | None = None` を追加。

### 2. 生成ログ基準の画像収集と消失ファイルの自動スキップ
- `backend/app/scanner/scanner.py` に `_load_manifest_metadata()` を実装。
- `_collect_all_files()` をマニフェスト優先モードに対応：
  - ディスク全数（1.7万枚）の探索をバイパスし、マニフェストに記録されたファイル名のみを対象化。
  - ディスク（`/mnt/external_hdd/yukikaze_generated`）に現存する 4,344〜4,351 件のみを抽出。
  - ディスクから削除・消失した 1,000 件以上のレコードは自動スキップ（存在しないファイルのゴーストポイント作成を防止）。

### 3. メタタグ・品質タグの剥離（サニタイズ）とWD14推論バイパス
- マニフェストに記録されたプロンプトから `sanitize_danbooru_tags()` を通して以下を徹底除去：
  - 品質ボイラープレート（`score_9`, `score_8`, `masterpiece`, `best quality`, `highres` 等）
  - メタ除外タグ（`meta_purge` 記載の `bad id`, `translated`, `commentary` 等）
  - レーティング・構文記号（`explicit`, `@aoi nagisa` 等）
- サニタイズされた高純度Danbooruタグ群を `wd14_tags`（スコア 1.0）として初期登録。
- WD14（推論モデル）の実行をスキップし、初期インジェスト直後から高速・高精度なDanbooruタグ検索が可能。

### 4. リッチメタデータのQdrant統合
- Qdrantのペイロードに以下の属性を直接保存：
  - `danbooru_post_id`: Danbooru ポスト番号
  - `danbooru_url`: 元絵の Danbooru URL
  - `heroine`: キャラクター名（`yukikaze_future`, `yukikaze` 等）
  - `backend`: 生成バックエンド（`anima_turbo_slow` 等）
  - `checkpoint`: チェックポイント名
  - `search_query`: 検索クエリ

### 5. フロントエンドUI拡張 & キャッシュバスター
- `frontend/src/App.vue`:
  - 画像詳細モーダルに「Danbooru Source」カードを追加。
  - Danbooru 元絵への直接リンク（`#5216059 ↗`）、ヒロインバッジ、バックエンド名、モデル名を分かりやすく表示。
- `frontend/index.html`:
  - キャッシュバスター（`v=20260915_0927`）を付与（Rule 7準拠）。

### 6. 自律マニフェスト監視 & 完全自動同期（danbooru側のコード変更ゼロ）
- `backend/app/scanner/watcher.py`:
  - `ImageDirectoryWatcher` に `_manifest_poll_loop()` を新設。
  - 2秒間隔で `settings.manifest_path` の `st_mtime` / `st_size` を監視（CPU負荷ゼロ）。
  - マニフェスト変更（新規生成追加）を検知すると、ファイル書き込み完了待機（1.5秒デバウンス）後に `scan_heal` ジョブを自動投入。
  - フロントエンドのSSE（Server-Sent Events）ジョブストリームと連動し、スキャン完了時にブラウザ画面側も自動で `fetchImages(true)` が実行され、リロード不要で新画像が即時表示される。

---

## 稼働・検証結果
- **Coolify自動デプロイ**: コミット `2f84f5e`, `8850b87` が自動ビルド・デプロイ成功（Queue 961, 963）。
- **コンテナ状態**: `frontend`, `backend`, `qdrant` の全3コンテナが正常稼働（`Up`）。
- **初回スキャン結果**: 全4,344件のインジェスト・サムネイル生成・タグサニタイズが数分で完了。
- **動的自動同期検証**: ホスト側マニフェストの更新から2秒以内にコンテナが変更を検知し、`scan_heal` が自動トリガーされることを実証・確認済み。
- **URL**:
  - ローカル: `http://localhost:3100/`
  - 公開FQDN: `http://gallery.hannya.org`


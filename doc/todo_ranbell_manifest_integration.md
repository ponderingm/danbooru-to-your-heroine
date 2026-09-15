# TODO: Danbooru to Your Heroine 生成ログベースの Ranbell Image データベース構築

## 概要
Ranbell Image（画像ビューア・ギャラリー）において、ディスク上の全ファイル（約1.7万枚）を無差別に走査するのではなく、`danbooru_yukikaze_tool` の生成ログ（`generated_manifest.json`、5,388件）を真実のソース（Source of Truth）としてQdrantデータベースを構築・インポートする。

## 要件
1. **生成ログ（マニフェスト）の連携**:
   - ホスト側の `/home/pi/danbooru_yukikaze_tool/database/generated_manifest.json` をコンテナ内の `/mnt/manifest/generated_manifest.json` にマウント。
   - `MANIFEST_PATH` 環境変数を設定。
2. **対象の限定と消失画像のスキップ**:
   - マニフェストに記録された画像ファイル（`files` フィールド）のみをインジェスト対象とする。
   - ディスク（`/mnt/external_hdd/yukikaze_generated`）に現存する 4,351 件のみを取り込む。
   - ディスク上に存在しない 1,037 件はスキップし、不要なポイント作成を防止する。
3. **メタタグ・品質タグの剥離（サニタイズ）**:
   - マニフェストの `prompt` から `sanitize_danbooru_tags()` を通して `meta_purge` タグおよび `score_\d+`, `masterpiece` などのボイラープレートを除去。
   - サニタイズ済みタグを `wd14_tags`（スコア 1.0）として初期登録（WD14推論スキップ・即時タグ検索可能）。
4. **リッチメタデータの統合**:
   - `danbooru_post_id`, `danbooru_url`, `heroine`, `backend`, `checkpoint`, `search_query` をQdrantのpayloadに保存。
5. **UI表示の拡張**:
   - 画像詳細モーダルに Danbooru 元絵（`#post_id` リンク）、ヒロイン名、バックエンド、モデル情報を表示。
6. **Coolify自動デプロイと動作検証**:
   - GitHubへプッシュし、Coolify上で自動ビルド・デプロイ。
   - スキャンを実行し、4,351件の正常インジェストを確認。

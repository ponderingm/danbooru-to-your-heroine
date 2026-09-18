# DONE: フロントエンド静的資産更新の標準フロー策定と自動化

## 実施日時
2026-09-18 16:26

## 実施内容
1. **キャッシュバスター自動更新ツールの作成**:
   - [`scripts/update_cache_buster.py`](file:///home/pi/danbooru_yukikaze_tool/scripts/update_cache_buster.py) を作成。
   - `src/web/index.html` 内の `<script src="app.js?v=...">` および `<link rel="stylesheet" href="style.css?v=...">` を現在のタイムスタンプ（`?v=YYYYMMDD_HHMM`）で自動更新する機能を実装・動作確認。
2. **スキル `frontend_static_assets_workflow` の登録**:
   - プロジェクトおよびグローバルの `roles/programming_partner/skills/frontend_static_assets_workflow/SKILL.md` に登録。
   - 「ローカル開発（ビルド不要） ➜ キャッシュバスター更新 ➜ PR Preview 検証 ➜ 本番イミュータブルデプロイ」の4ステップ標準を定義。
3. **最新キャッシュバスターの適用**:
   - `index.html` のクエリパラメータを最新化（`?v=20260918_1625`）。

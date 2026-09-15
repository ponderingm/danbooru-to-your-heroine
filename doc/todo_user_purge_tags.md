# 作業計画: User独自パージタグ反映・grayscale等の確実なパージ対応

## 目的
ユーザー指定の独自パージタグ（`purge_tags` / `user_purge_tags`）が画風設定（`art_style`）や胸/肌色判定に遮られることなく、最優先で確実にプロンプトからパージされるように修正する。

## 作業タスク
- [ ] 1. `src/danbooru_to_heroine.py` の修正
  - `mutate_tags_to_heroine` の一般タグ処理ループで、除外系判定（`negative_tags`, `blacklist`, `purge_set`, `CENSORING_BLACKLIST`, `known_character_tags`）を `art_style_set` / `BREAST_TAGS` / `skin_tags_set` より前に移動
  - `meta_tags` ループにも `blacklist` 判定を追加
  - `build_prompt` において `purge_set` による二重防御フィルタを追加
- [ ] 2. `src/config.py` の修正
  - `USER_CONFIG.get("purge_tags") or USER_CONFIG.get("user_purge_tags")` などのキー互換性確保
  - `EXTRA_PURGE_TAGS` 構築時に `grey` ↔ `gray` の相互同義語自動展開を適用
  - `unpurge_tags` 構築時にも同様に同義語自動展開を適用
- [ ] 3. `src/config.yaml` & `src/config.example.yaml` の修正
  - `purge_tags` リストに `grayscale` を追加
- [ ] 4. `src/server.py` のキー互換性確保
  - `/purge_tags` エンドポイントでのキー参照フォールバック追加
- [ ] 5. 検証テストの実施
  - `grayscale`, `greyscale`, `monochrome` 等を含むタグ群で `mutate_tags_to_heroine` を実行し、正しくパージされることを検証
  - 単体テスト・構文チェック `python3 -m py_compile src/*.py` の実行
- [ ] 6. 完了ドキュメント `doc/done_user_purge_tags.md` の作成

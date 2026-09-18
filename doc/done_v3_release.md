# DONE: v3.0.0 正式リリース完了

## リリース日時
2026-09-18 16:40

## リリース概要
- **プルリクエスト**: [PR #1](https://github.com/ponderingm/danbooru-to-your-heroine/pull/1) を `master` ブランチへマージ完了。
- **リリースタグ**: [`v3.0.0`](https://github.com/ponderingm/danbooru-to-your-heroine/releases/tag/v3.0.0) を作成・プッシュ。
- **本番デプロイ**: Coolify が master の最新コミット（`a3de6f0`）を自動検知し、本番コンテナ（ポート 8899）のビルド・デプロイが完了。
- **実機検証**: `http://127.0.0.1:8899/version` にて `version: "v3.0.0"`, `branch: "master"`, `is_preview: false` の正常稼働を確認。

## v3.0.0 主な機能
1. **ヒロインDNA構造化 & スロット駆動ミューテーション**:
   - `dna: {hair, face, body}`, `identity`, `costume`, `override_rules` のスキーマ階層化。
   - 相互排他置換の厳密化とメイク・装飾タグの過剰削除防止。
2. **3層Tag DB & 黄金順ソート（Golden Sorting）**:
   - 50スロット分類（600+ベースタグ）による第1チャンク（75トークン）最適化。
   - GPD Ollama / Gemini Flash-Lite による自動分類。
3. **複数人・百合構図（Multi-Subject）戦略の全実装**:
   - 女子ペア構図での `1boy` 誤爆根絶。
   - Mode C（カプセル分離）、Mode A（フラット分散）、Mode B（衣装共有注入）の完全サポート。
4. **マニフェスト保存のV3構造化 & WebUI エディタ追従**:
   - スロット分類情報・複数人モードの完全記録。
   - WebUI ヘッダーに動的バージョン、コミットハッシュ、PR Preview バッジ表示。
5. **開発標準 & キャッシュバスター自動化**:
   - `scripts/dev_server.sh` によるポート 8898 での即時UI開発（ビルド待ちゼロ）。
   - `scripts/update_cache_buster.py` による静的資産キャッシュ事故防止。
   - スキル `frontend_static_assets_workflow` の登録。

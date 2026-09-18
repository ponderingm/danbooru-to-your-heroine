# 🧬 [v3.0 TODO] マニフェスト構造化＆ヒロインエディタ・設定オプションのV3完全準拠

- **計画バージョン**: v3.0
- **作成日**: 2026-09-16
- **ステータス**: 実装着手

---

## 1. 🎯 目的と概要
v3プロンプト構造化エンジンの導入に伴い、データ永続化層（マニフェスト）およびUI設定層（ヒロインエディタ・生成オプション）を新スキーマ（7大スロット体系・複数人戦略）へ完全整合・同期させる。

---

## 2. 📝 実装タスク一覧

### タスク1: マニフェスト保存のV3構造化 (`database/generated_manifest.json` & `src/server.py`)
- [ ] `_convert_core` で算出される `identity_tags`, `situation_tags`, `removed_tags`, `slots`（タグ別スロット分類マップ）を `extras` または戻り値として保持。
- [ ] `_do_generate` のマニフェストエントリ（`entry`）に以下を記録：
  - `identity_tags`: 適用ヒロインDNAタグ
  - `situation_tags`: 元絵から保持されたシチュエーション・構図タグ
  - `removed_tags`: スロット競合等で除去されたタグ
  - `slots`: 採用された主要タグのスロット分類マッピング（例: `{"dark skin": "character_dna.body.skin", ...}`）
  - `multi_mode`: 適用された複数人戦略 (`capsule` / `flat` / `shared_costume`)
- [ ] ギャラリーカード等の既存機能との100%後方互換性維持。

### タスク2: ヒロイン設定スキーマ＆エディタのV3完全追従 (`src/config.py`, `src/web/index.html`, `src/web/app.js`)
- [ ] `src/config.py` の `save_heroine` / `get_heroine_dna` が新スキーマ（`identity`, `dna: {hair, face, body}`, `signature_costumes`, `override_rules`）をそのままロスなく双方向シリアライズできるよう整備。
- [ ] Web UI のヒロイン編集フォーム（`#heroine-form`）のUI刷新：
  - 髪 (hair): `color`, `style`, `feature`
  - 顔 (face): `eyes`, `marks`
  - 身体 (body): `skin`, `breasts`, `build`, `marks`
  - デフォルト複数人戦略 (`default_multi_mode`: capsule / flat / shared_costume) の設定セレクタ追加
- [ ] Booruタグ分析ヘルパー（`#heroine-helper-details`）の出力結果が新スロットへ正しく流し込めるように連携改修。

### タスク3: その他設定オプションのV3統一とキャッシュバスター更新
- [ ] 単一生成、バッチ生成、個別再生成、ヒロイン設定の全レイヤーでオプション項目（胸・肌・衣装・画風・複数人戦略）を完全連動。
- [ ] `src/web/index.html` のキャッシュバスターを更新。
- [ ] 自動テストスイート（`tests/`）の拡充と実行検証。

# v2.0 正式リリース・masterマージ完了報告

- **対象バージョン**: v2.0 (Stable Release)
- **マージ元ブランチ**: `v2-beta`
- **マージ先ブランチ**: `master`
- **完了日**: 2026-09-16

---

## 1. 概要

`danbooru-to-your-heroine` v2.0-beta における各種機能の実装および実環境での稼働検証が完了し、安定稼働が確認されたため、ドキュメントの最終整備、セキュリティ監査（トークン等の非公開化）、および `master` ブランチへのマージを実施した。

---

## 2. 実施内容

### 2.1 セキュリティ・機密情報の分離監査
- **ルール遵守確認**: [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) に基づき、User層設定・個人情報・トークン類が追跡対象ファイルに混入していないかを全走査。
- **ハードコードトークンの排除**:
  - [`scripts/check_deployment.py`](../scripts/check_deployment.py)
  - [`scripts/deploy_coolify_app.py`](../scripts/deploy_coolify_app.py)
  - [`scripts/register_coolify_app.py`](../scripts/register_coolify_app.py)
  - 上記スクリプト内に存在していた一時デプロイ用トークンを `os.environ.get("COOLIFY_TOKEN", "")` 経由の環境変数取得方式へ修正。
- **公開用設定テンプレート**:
  - [`src/config.example.yaml`](../src/config.example.yaml) 内に実在の版権キャラクターや秘密トークンが含まれていないことを確認。

### 2.2 ドキュメントの整備
- **[README.md](../README.md)**:
  - 主要APIエンドポイント一覧に `POST /posts/search`（Booru横断検索・Tier判定API）を追加。
  - `POST /generate` の説明に `filename_prefix` オプション対応を明記。
  - ディレクトリ構成ツリーに [`src/cooccurrence_finder.py`](../src/cooccurrence_finder.py) および [`src/natural_to_danbooru.py`](../src/natural_to_danbooru.py) を追加。
  - 開発ロードマップの完了項目を更新。
- **[doc/research_mosaic_censorship_causes.md](research_mosaic_censorship_causes.md)**:
  - Anima Turbo（CFG 1.0）におけるモザイク発生要因（アーティストタグとR18モザイクの共起、ネガティブプロンプトの数式相殺）の分析および実用的結論を追記・確定。

### 2.3 構文検証と動作確認
- `python3 -m py_compile src/*.py scripts/*.py` による全Pythonスクリプトの構文チェック。

### 2.4 ブランチマージ
- `v2-beta` の変更をコミットし、`master` ブランチへマージ。

---

## 3. 次期開発への展望 (v3.0)

- 汎用アドオン・フレームワーク（Generic Addon Framework）による衣装・MGE種族・シチュエーションのパック拡張（[docs/costume_addon_design_spec.md](../docs/costume_addon_design_spec.md) 参照）。
- ComfyUI カスタムノード化の検討。

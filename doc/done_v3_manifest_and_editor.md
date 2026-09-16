# 🧬 [v3.0] マニフェスト構造化＆ヒロインエディタ・設定オプションのV3完全準拠 実装完了

## 1. 課題と背景
v3プロンプト構造化エンジンの導入に伴い、以下の2つの重要コンポーネントにv2とのギャップが存在していた：
1. **マニフェスト（`database/generated_manifest.json`）の非構造化**:
   - `prompt` 文字列やパラメータのみが記録され、どのタグがヒロインDNA（`identity_tags`）で、どのタグが元絵継承（`situation_tags`）で、どのタグが除去（`removed_tags`）されたか、また各タグがどの7大スロットに分類されたかの情報が欠落していた。
2. **ヒロイン設定エディタ（Web UI）のv2フラット依存**:
   - Web UIのエディタからヒロインを保存すると、v3の7大スロット階層構造（`identity`, `dna: {hair, face, body}`, `override_rules`）ではなく、v2のフラット配列（`face_tags`, `body_tags`）で上書き保存されてしまい、スロット情報が退行するリスクがあった。
   - 新機能である「複数人構図戦略デフォルト（`multi_mode`）」がヒロインエディタで設定できなかった。

## 2. 実施した実装内容

### ① マニフェスト保存のV3構造化 (`src/server.py`)
- `_convert` / `_convert_core` 内で採用タグ群のセマンティックスロットマッピング（`slots`）を高速生成。
- マニフェストエントリ（`manifest`）に以下の構造化フィールドを完全記録：
  - `identity_tags`: 注入されたヒロイン固有DNAタグ群
  - `situation_tags`: 元絵から継承されたシチュエーション・構図タグ群
  - `removed_tags`: スロット排他制御等で置換・除去された元絵タグ群
  - `slots`: 各タグの7大スロット分類辞書（例: `{"dark skin": "character_dna.body.skin", ...}`）
  - `multi_mode`: 適用された複数人構図戦略（`capsule` / `flat` / `shared_costume`）

### ② バックエンドでのヒロインスキーマ自動正規化 (`src/config.py`)
- `normalize_heroine_v3_schema(raw: dict) -> dict` を実装：
  - UIやAPIからフラット配列（`face_tags`, `body_tags` 等）が渡された場合でも、自動的に v3 の 7大スロット階層スキーマ（`identity: {character, series}`, `dna: {hair, face, body}`, `costume`, `override_rules: {multi_mode, ...}`）へ完全正規化して `config.yaml` へ保存。
  - スキーマの退行・破壊を完全に防止。

### ③ Web UI ヒロイン設定エディタのV3追従 (`src/web/index.html`, `src/web/app.js`)
- **UI側への複数人戦略デフォルト設定の追加**:
  - ヒロイン編集画面のオプションカードに「👥 複数人構図デフォルト戦略（`hm-rule-multi-mode`）」セレクタを新設。
- **フォーム読み込み・展開のv3対応**:
  - `populateHeroineForm`: `dna.hair`, `dna.face`, `dna.body`, `identity`, `override_rules.multi_mode` の階層データを自動展開・反映。
- **ヒロイン選択時の自動連動**:
  - 単一生成・バッチ生成でヒロインを切り替えた際、そのヒロインのデフォルト複数人戦略がフォームのセレクタへ自動同期。
- **キャッシュバスター更新**:
  - `app.js?v=20260916_2230` に更新。

### ④ テストスイート整備 (`tests/test_v3_prompt_architecture.py`)
- `test_normalize_heroine_v3_schema`: 旧フラットデータからのv3階層スキーマ自動変換の正常性を検証。
- `test_manifest_structured_fields`: `/convert` 時の構造化フィールド（`identity_tags`, `situation_tags`, `removed_tags`, `slots`, `multi_mode`）の返却を検証。
- 全11テストが自動合格。

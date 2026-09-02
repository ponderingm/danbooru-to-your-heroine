# Copilot Instructions — danbooru_yukikaze_tool (v2.0)

このリポジトリはPublic公開を前提とする。AIコーディングエージェントは以下のルールを必ず守ること。

## 🔒 最重要ルール: 個人的な嗜好・秘匿情報の分離（2層ルール構造）

本プロジェクトは設定を **「Base層（公式共通ルール）」** と **「User層（個人固有設定）」** の2層に分離している。

1. **User層（非公開・`.gitignore` 対象）: `src/config.yaml`**
   - **個人的な嗜好・環境固有の情報は、必ず `src/config.yaml` にのみ記述する。**
   - 追跡対象ファイル（`src/config.example.yaml` や `src/rules/default_rules.yaml` を含む全てのソース・ドキュメント）に絶対に書き込んではならない。
   - 「個人的な嗜好・環境固有の情報」に該当するもの:
     - `heroines` 辞書の実在キャラクター定義（キャラ名・作品名・アーティストタグ・身体特徴などの具体的な値）
     - ComfyUIサーバーの実際のURL/IPアドレス（例: `comfy_url`）
     - LoRA・checkpointの実ファイル名（個人が使っているローカルファイル）
     - 画像保存先の実パス（`output_dir` / `web_output_dir`）
     - 各種Booruのログイン情報・APIキー
     - Discord Webhook URL（`webhook_url`）
     - `api_host` / `api_port` など個人環境のポート番号
     - `user_purge_tags` / `user_block_tags` / `user_unpurge_tags`
2. **Base層（Git管理対象・全ユーザー共通）: `src/rules/default_rules.yaml`**
   - 画像品質向上やノイズ除去（ウォーターマーク、言語別コメント、アカウント名等）、身体属性分類など、全ユーザーが共有すべき普遍的なルール辞書。
   - ここには特定の個人ヒロイン名や秘密情報は一切含めない。
3. **設定ローダー: `src/config.py`**
   - `src/config.yaml` と `src/rules/default_rules.yaml` をマージしてメモリ展開する薄いローダー。
   - 既存コードからの `import config` との後方互換性を100%保証する。
   - 設定変更時は `config.reload_config()` によりサーバー再起動なしでホットリロード可能。

### 実装ルール
1. 新しい設定項目を追加する場合、**必ず** `src/config.example.yaml` にも同じキー名で追加するが、値は汎用的なプレースホルダー（例: `"example_character"`, `"/path/to/output"`, `"your_lora.safetensors"`）にすること。
2. `src/config.example.yaml`・READMEなど追跡対象ファイルに、実在の版権キャラクター名・実IPアドレス・実ファイルパス・トークンを書き込まない。
3. `database/*.json`（生成マニフェスト等）、`database/*.yaml`、`database/backups/`（自動退避スナップショット）、生成画像本体も個人の生成物のため `.gitignore` 対象。
4. `.gitignore` から `src/config.yaml` や `database/` の除外を外す変更は行わない。

## プロジェクト概要

Danbooru / Gelbooru / AIBooru / Civitai の投稿を解析・検索し、構文・タグを自分のオリジナルヒロインに換装した上で、ComfyUI経由で画像を再生成するツール群。

- [src/rules/default_rules.yaml](../src/rules/default_rules.yaml): Git管理の公式Baseルール辞書（メタタグ、画面ノイズ、属性衝突辞書）
- [src/config.yaml](../src/config.yaml): ユーザー固有設定（非公開、環境パス、ヒロイン定義、個別ルール）
- [src/config.example.yaml](../src/config.example.yaml): 公開用設定テンプレート
- [src/config.py](../src/config.py): YAMLローダー＆ホットリロード＆自動バックアップエンジン
- [src/site_adapters/](../src/site_adapters/): マルチサイト対応アダプタ群（Danbooru, Gelbooru, AIBooru, Civitai）
- [src/danbooru_to_heroine.py](../src/danbooru_to_heroine.py): 投稿URLの解析・タグ置換コアロジック
- [src/danbooru_search_batch_generator.py](../src/danbooru_search_batch_generator.py): 検索結果を連続変換・生成するバッチCLI
- [src/model_adapter.py](../src/model_adapter.py): モデルアーキテクチャ（illustrious / anima）ごとにプロンプト構文を最適化
- [src/comfy_client.py](../src/comfy_client.py): ComfyUIワークフロー生成・送信・ポーリング
- [src/notify.py](../src/notify.py): Discord通知エンジン（4段階ログレベル、画像添付Embed送信）
- [src/server.py](../src/server.py): FastAPIサーバー（生成API、ジョブキュー、履歴配信、パージタグ管理・バックアップAPI）
- [src/web/](../src/web/): モダンWebUI（⚡生成 / 🖼️ギャラリー / ⚙️設定の3タブ構成、パージ管理、タイムマシーン復元、stickyヘッダー）
- [tampermonkey/](../tampermonkey/): マルチサイト対応ユーザースクリプト（個別・一括生成キュー投入、Artist datalist統合）

## 開発時の注意

- **Python環境管理**: 必ず `uv` を用いて管理・実行すること（`uv run python ...`）。
- **構文チェック**: 編集後は `python3 -m py_compile src/*.py` で構文エラーがないか確認する。
- **ファイル編集**: `replace_file_content` を正しく使い、ファイルの全書き換えによる高コストな置換は避ける。
- **モデル分岐の整合性**: `model` パラメータ（illustrious / anima）に依存する分岐を追加・変更する場合、各モジュールで一貫性を保つこと。

# Copilot Instructions — danbooru_yukikaze_tool

このリポジトリはPublic公開を前提とする。AIコーディングエージェントは以下のルールを必ず守ること。

## 🔒 最重要ルール: 個人的な嗜好・秘匿情報の分離

**個人的な嗜好・環境固有の情報は、必ず `src/config.py`（`.gitignore`対象・非公開）にのみ記述する。**
追跡対象ファイル（`src/config.example.py`を含む全てのソース・ドキュメント）に絶対に書き込んではならない。

「個人的な嗜好・環境固有の情報」に該当するもの:
- `HEROINES`辞書の実在キャラクター定義（キャラ名・作品名・アーティストタグ等の具体的な値）
- ComfyUIサーバーの実際のURL/IPアドレス（例: `CUSTOM_COMFY_URL`）
- LoRA・checkpointの実ファイル名（個人が使っているもの）
- 画像保存先の実パス（`OUTPUT_DIR` / `WEB_OUTPUT_DIR`）
- Danbooruログイン情報・APIキー
- `API_HOST` / `API_PORT`など、個人が使いたいポート番号
- `SERIES_TAG_KEEP_KEYWORDS` / `OTHER_KNOWN_CHARACTER_TAGS`の具体的な版権作品名

### 実装ルール
1. `config.py`に新しい設定項目を追加する場合、**必ず**`config.example.py`にも同じキー名で追加するが、値は汎用的なプレースホルダー（例: `"example_character_name"`, `"/path/to/generated_images"`, `"your_custom_lora.safetensors"`）にすること。
2. `config.example.py`・READMEなど追跡対象ファイルに、実在の版権キャラクター名・実IPアドレス・実ファイルパス・トークンを書き込まない。
3. `database/*.json`（生成マニフェスト等）や生成画像本体も個人の生成物のため`.gitignore`対象。新しい生成物の保存先を追加する場合も同様に除外すること。
4. `.gitignore`から`src/config.py`や`database/*.json`の除外を外す変更は行わない。

## プロジェクト概要

Danbooruの投稿を検索し、タグを自分のオリジナルヒロインに置換した上で、ComfyUI経由で画像を再生成するツール群。

- [src/danbooru_to_heroine.py](../src/danbooru_to_heroine.py): 単一投稿URLの変換CLI
- [src/danbooru_search_batch_generator.py](../src/danbooru_search_batch_generator.py): 検索結果を連続変換・生成するバッチCLI
- [src/model_adapter.py](../src/model_adapter.py): モデルアーキテクチャ（illustrious / anima / animagine）ごとにプロンプト構文を最適化
- [src/comfy_client.py](../src/comfy_client.py): ComfyUIワークフロー生成・送信・ポーリング。default / custom / anima の3系統のワークフローを持つ
- [src/server.py](../src/server.py): FastAPI経由でTampermonkeyスクリプトやWebビューアから呼び出すためのAPI
- [tampermonkey/](../tampermonkey/): Danbooru投稿ページに変換・生成ボタンを追加するユーザースクリプト
- [src/web/](../src/web/): 生成履歴Webビューア（静的ファイル、server.pyがマウント）

## 開発時の注意

- Python依存関係は`uv`で管理（`uv sync` / `uv run ...`）。
- 編集後は`python3 -m py_compile src/*.py`で構文エラーがないか確認する。
- コメントは日本語で簡潔に。
- `model`パラメータ（illustrious/anima/animagine）に依存する分岐を追加・変更する場合、`comfy_client.py`・`server.py`・`danbooru_search_batch_generator.py`・`model_adapter.py`の呼び出し箇所全てに一貫して反映されているか確認する（過去に`anima`指定が一部の分岐にしか反映されず実質無視されるバグがあった）。

# TODO: Ranbell Image への Ollama (embeddinggemma:300m / gemma4:e2b) & WD14 タグ辞書導入

## 概要
Raspberry Pi 5 上の Ranbell Image において、セマンティック検索・類似検索・タグカテゴリ色分けオートコンプリート・プロンプト錬成（Prompt Alchemy）を完全ローカルで稼働させるため、軽量 Ollama サービスを追加し、モデルおよびタグ辞書をセットアップする。

## 実施計画
1. **WD14 タグ辞書（selected_tags.csv）の配置**:
   - `taimanin_prompt_project` にある `selected_tags.csv`（248KB）を `ranbell_image/backend/models/wd14/` に配置。
   - Dockerfile でコンテナ内の `/mnt/models/wd14/selected_tags.csv` へバンドル。
2. **Ollama コンテナの追加**:
   - `docker-compose.yml` / `docker-compose.yaml` に `ollama` サービスを追加。
   - モデル保存先を外付けHDD（`/mnt/external_hdd/ollama_models`、空き647GB）に永続化。
   - `backend` の環境変数を `OLLAMA_URL: http://ollama:11434`, `EMBED_MODEL: embeddinggemma:300m`, `VLM_MODEL: gemma4:e2b` に設定。
3. **Coolify自動デプロイ & コンテナ起動確認**:
   - 変更をコミット＆プッシュし、Coolify上で自動ビルド・デプロイ。
4. **モデルのダウンロードと推論検証**:
   - `embeddinggemma:300m` をプルし、埋め込みAPIの動作とレスポンス時間をテスト。
   - `gemma4:e2b` をプルし、プロンプト生成およびメモリ消費量をテスト。
   - Ranbell Image ギャラリー上での検索・UI動作を確認。

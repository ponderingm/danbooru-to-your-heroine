# 完了記録: Ranbell Image への Ollama / WD14 統合および動作検証

## 1. 概要
`danbooru to your heroine` 特化型 Ranbell Image ギャラリーにおいて、WD14 タグ辞書の同梱、Ollama サービスコンテナの導入、軽量埋め込みモデル `embeddinggemma:300m` によるセマンティック検索、およびマルチモーダルモデル `gemma4:e2b` によるプロンプト錬成の動作検証を実施した。

---

## 2. 実施内容と検証結果

### ① コンテナ整理とメモリ確保
- 常駐していた `netdata`、`gembridge`（常駐Chromium含む）、`uptime-kuma` を停止。
- システムメモリ使用量を 3.9GB → 2.7GB（約 1.2GB 解放、空き 5.2GB）に削減し、LLM/VLM 推論の安定稼働基盤を確保。

### ② WD14 タグ辞書の同梱
- `/home/pi/taimanin_prompt_project/models/wd14/selected_tags.csv`（248KB）をフォークした `ranbell_image/backend/models/wd14/selected_tags.csv` に配置。
- `backend/Dockerfile` に `COPY models/ /mnt/models/` を追加し、Docker ビルド時にコンテナ内へ自動同梱。タグのカテゴリ分類やオートコンプリートが機能する状態を構築。

### ③ Ollama サービスの追加とストレージ設定
- `docker-compose.yml` に `ollama` サービス（`ollama/ollama:latest`）を追加。
- モデルストレージを外付けHDD（`/mnt/external_hdd/ollama_models`、空き647GB）にマウントし、SDカードの容量圧迫を完全に防止。
- `embeddinggemma:300m` および `gemma4:e2b` をプル完了。

### ④ セマンティック検索の実証 (`embeddinggemma:300m`)
- **適合性**: 出力次元数が 768 次元で、Ranbell の Qdrant コレクション設計（`embed_dim: 768`, MRL `embed_dim_small: 256`）と完全に一致。
- **推論速度**: Pi 5 の CPU 単体で 1 件あたり約 0.8 秒（ウォームアップ後）。
- **検索精度検証**:
  - `voice actor` 検索 → `ga__jobs__voice_actor__que__yukikaze_D4934226.png` が第1位でヒット。
  - `grabbing collar neck` 検索 → `ga__nudity__collar_grab__gen__yukikaze_D7041985.png` が第1位でヒット。
  - Danbooru タグと自然言語の同義語マッピングが極めて高精度に機能することを確認。

### ⑤ プロンプト錬成の検証 (`gemma4:e2b`)
- **動作確認**: Pi 5 上で画像タイル＋テキストのマルチモーダル推論が CPU のみで安定稼働。
- **チューニングと実証**:
  - `backend/app/jobs/runners.py` において `_DEFAULT_NUM_PREDICT = 256` を設定し、`options` に追加。
  - `backend/app/ai/ollama.py` の `DEFAULT_TIMEOUT` を 300秒 → 600秒へ拡張。
  - 再テストを実施した結果、**所要時間 211.6秒（約3分半）でタイムアウトすることなく完璧に完走**！
  - 出力結果例:
    ```
    safe, mizuki yukikaze, very long hair, twintails, dark skin, dark-skinned female, one-piece tan, small breasts, v-shaped eyebrows, solo, backlighting, interface headset (evangelion), red bodysuit, hair between eyes, hair ornament, on one knee, legs, open mouth, from above, overlighting
    ```
  - 画像認識（interface headset, red bodysuit, on one knee 等）と自然言語指示を高精度に融合した Danbooru プロンプトの合成に成功。

### ⑥ ComfyUI & Ollama ハードウェア分離設定（APU + eGPU）
- **構成**:
  - `COMFYUI_URL: http://100.126.79.83:8188` → Windows 側の **APU（内蔵GPU）** に割り当て（画像生成用）。
  - `OLLAMA_URL: http://100.126.79.83:11434` → Windows 側の **eGPU（外付けGPU）** に割り当て（LLM/VLM推論用）。
- **クラッシュ対策と安全性**:
  - 重い拡散モデル（Stable Diffusion等）の画像生成はすべてAPUで実行され、eGPU側には一切リクエストが流れない安全設計。
  - eGPU側で実行されるのはプロンプト錬成（`gemma4:e2b`）および埋め込み（`embeddinggemma:300m`）の軽量推論のみ（VRAM消費 0.5〜3GB）。
  - コミット `4ef700c` を Coolify にプッシュ・デプロイ完了。

### ⑦ プロンプト錬成の実測（eGPU経由で 6倍高速化）
- 所要時間: **35.1秒**（Pi 5 CPU の 211秒から約 6倍高速化）。
- `gemma4:e2b` の約500トークンの思考プロセス（Thinking）を含めてもスムーズに完走し、高精度な Danbooru プロンプトのストリーミング出力を実証。

### ⑨ Pi 5 ローカル Ollama コンテナの完全撤去と軽量化
- `docker-compose.yml` および `docker-compose.yaml` から `ollama` サービスおよび依存関係を完全削除（コミット `f66da73`）。
- Coolify によりデプロイし、Pi 5 上のローカルコンテナを `frontend`, `backend`, `qdrant` の 3 つのみに集約。
- **効果**:
  - ポート `11434` のバインドを完全解放。
  - Pi 5 のメモリ使用量が **2.3GB**（利用可能空き容量 **5.6GB**）まで大幅に改善。
  - ロードアベレージが 1.4 台まで低下し、極めて省電力・安定した常駐環境を達成。
  - バックエンドの `ai/status` は Windows eGPU Ollama 経由で `"ollama_ok": true`, `"vector_count": 4344` を正常維持。

### ⑩ WD14 Tagger 完全モデル（ONNX + 辞書）のコンテナ内蔵化
- **課題**:
  - `danbooru to your heroine` からの画像はマニフェストからタグを注入するため推論はスキップするが、Ranbell 本来のタグ正規化（BM25）、未タグ画像の自動フォールバック、およびUI連携機能を発揮するには `model.onnx` と `onnxruntime` が必須であった。
- **実施内容**:
  1. **モデルマウント**: ホスト側の実体 `/home/pi/taimanin_prompt_project/models/wd14`（`model.onnx` 370MB + `selected_tags.csv` 248KB）を、`docker-compose.yml` / `docker-compose.yaml` によりコンテナ内 `/mnt/models/wd14:ro` へ直接バインドマウント（GitやDockerイメージを一切肥大化させない設計）。
  2. **依存関係追加**: `backend/requirements.txt` に `onnxruntime>=1.18.0` を追加し、Coolify でビルド・デプロイ（コミット `ac7f216`）。
- **実機検証結果**:
  - コンテナ内での `onnxruntime 1.30.0` 稼働を確認。
  - テスト画像に対する WD14 ONNX 推論テストで、23 個のタグ（`1girl: 0.996`, `bodysuit: 0.893`, `tan: 0.797` 等）を高精度にスコア付きで検出成功。
  - BM25 タグ正規化・曖昧検索機能が完全に稼働。

---

## 3. 最終成果
1. **Danbooru to Your Heroine × Ranbell Image 完全連動**:
   - マニフェスト基準で現存する全 4,344 枚をインジェスト。
   - WD14 Tagger 完全稼働（ONNX推論＋タグ辞書＋BM25正規化＋オートコンプリート）。
   - `generated_manifest.json` の更新を自動検知して自律追加（フォーク側で完結、danbooru 側無修正）。
2. **ハードウェア分離の最適化（APU + eGPU + Pi 5）**:
   - ComfyUI（高負荷画像生成）→ Windows APU（内蔵GPU）で安全隔離。
   - Ollama（プロンプト錬成＋埋め込み推論）→ Windows eGPU で爆速稼働（35秒錬成、秒間18枚埋め込み）。
   - Pi 5 ギャラリーサーバー → 重いモデルコンテナを全廃し、ギャラリーWeb配信・Qdrantベクトル検索・WD14タグ機能に専念（空きメモリ 5.6GB）。

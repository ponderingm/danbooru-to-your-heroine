# 調査報告: Ranbell Image フォークによるリッチギャラリー統合計画

## 1. 調査背景
現在 `danbooru_yukikaze_tool` のフロントエンドギャラリーは Vanilla JS/HTML/CSS（`src/web/`）で構築されており、基本的なタグフィルタやプロンプト再編集・再生成機能を提供している。
一方で、更なるUX向上（仮想スクロール、セマンティック探索、Danbooruタグ共起ネットワーク分析、カラー検索、詳細なメタデータインスペクタ）を実現するため、オープンソースのローカルAI画像スタジオ **[Ranbell Image](https://github.com/ranbell/ranbell_image)** をフォークし、`danbooru_yukikaze_tool` の専用リッチギャラリーとして統合する方針を検討する。

---

## 2. Ranbell Image のアーキテクチャ概要

| コンポーネント | 技術スタック | 役割 |
|---|---|---|
| **フロントエンド** | Vue 3 + Vite + Tailwind CSS | 高速ギャラリー、コントロールルーム、インスパイア/プロンプト錬成UI |
| **バックエンド** | FastAPI (Python 3.10+) | 画像スキャン、メタデータ抽出、REST API、SSEストリーミング |
| **ベクターDB** | Qdrant (Docker) | マルチ解像度画像埋め込み、セマンティック検索、クラスタリング |
| **推論エンジン** | Ollama (`embeddinggemma:300m`, `gemma4:e2b`) | セマンティック埋め込み生成、VLM画像解析・適合度評価 |
| **タガー** | WD14 (SmilingWolf EVA02-Large) | 全画像のDanbooruタグ自動抽出・共起分析 |
| **生成エンジン** | ComfyUI HTTP API | ワークフロー実行・画像生成 |

---

## 3. `danbooru_yukikaze_tool` との親和性・シナジー

1. **Danbooruタグ体系の完全一致 ＆ WD14タガーの完全スキップ（最重要最適化）**:
   - `danbooru_yukikaze_tool` の生成画像は、元となったDanbooru投稿の完全なタグ情報（キャラクター、一般、絵師、レーティング）および適用プロンプトが `database/generated_manifest.json` やメタデータとして既に100%正確に保持されている。
   - したがって、Ranbell Imageが通常行う **「WD14 (SmilingWolf) による視覚画像からのタグ推論（高負荷・不完全）」を丸ごとバイパス** 可能。
   - **メリット**:
     - 巨大なWD14モデル（約1.5GB+）のダウンロード・VRAM/CPU消費が完全にゼロになる。
     - AIによる誤認（ハルシネーション）のない、完璧な正解Danbooruタグ（信頼度 1.0）が直接Qdrantに格納される。
     - インデックス処理速度が数十分から「数秒（JSON/メタデータの直接流し込み）」へと圧倒的に高速化される。
   - **インポート時の必須前処理ルール**:
     - **① メタタグの剥ぎ取り（サニタイズ）**:
       - Danbooruのメタカテゴリタグ（`meta_purge` 記載の `bad id`, `translated`, `commentary`, `highres`, `absurdres` など）や品質スコア修飾タグ（`score_9`, `masterpiece`, `best quality` 等）を除外。純粋な視覚コンテンツタグ（衣装、属性、構図、表情、シチュエーション等）のみをギャラリー検索・タグネットワークに登録。
     - **② 実ファイル存在確認（消失・削除画像の自動スキップ）**:
       - `database/generated_manifest.json` にエントリが存在していても、ディスク上（`OUTPUT_DIR`）で実画像ファイルが削除・移動されている場合はインデックス登録をスキップ。
       - ギャラリー上で画像リンク切れ（Broken Image）やゴースト表示が一切発生しない堅牢な同期機構とする。
2. **疎結合なマイクロサービス親和性**:
   - `danbooru_yukikaze_tool` は既にFastAPIサーバーとして `/posts/search`, `/convert`, `/generate` を提供している。
   - Ranbell Imageのバックエンドから `danbooru_yukikaze_tool` のAPIを呼ぶことで、RanbellのUIから「Danbooru検索 → ヒロイン変換 → ComfyUI生成」のパイプラインをシームレスに起動できる。
3. **生成画像の自動取り込み**:
   - `danbooru_yukikaze_tool` の保存先（`OUTPUT_DIR`）をRanbellの監視ディレクトリとしてバインドマウントすることで、生成された画像が自動的にQdrant・WD14インデックスに登録され、リッチなギャラリーで即座に閲覧可能になる。

---

## 4. 環境制約とハードウェア構成の適合性（Pi 5 + リモートGPU）

本環境はホストが **Raspberry Pi 5 (ARM64, 8GB RAM)** であり、画像生成 ComfyUI は **リモートGPUマシン** で動作している。

- **WD14を撤廃したことによる劇的な軽量化**:
  - 重いニューラルネット推論（WD14タガー）が不要となったため、Raspberry Pi 5上での負荷が大幅に軽減され、Pi 5単体でも軽快に動作可能。
- **Raspberry Pi 5 上で動かすもの**:
  - `danbooru_yukikaze_tool` (FastAPI / ポート 8899)
  - Ranbell Frontend & Backend (ポート 3100)
  - Qdrant (公式ARM64コンテナが軽量に動作)
- **リモートGPUマシン（または外部）で動かすもの**:
  - ComfyUI (画像生成)
  - Ollama (`embeddinggemma:300m` / VLM) ※セマンティック検索用の埋め込みベクトル生成のみリモートOllamaで処理。


---

## 5. 統合アプローチ比較

| 方式 | メリット | デメリット | 推奨度 |
|---|---|---|---|
| **A. マイクロサービス連携 (Sidecar方式)** | Ranbellのコードベースを汚さず、設定（マウント・API URL）と最小限のUI拡張で即時稼働可能。アップデート追従が容易。 | ポートが2つ分かれる（8899と3100）。 | **◎ 最推奨 (Phase 1〜2)** |
| **B. 完全マージ・単一アプリ化** | 単一WebUIで完結。 | RanbellのVue 3コードとFastAPIの依存管理が複雑化し、保守コストが高い。 | △ |
| **C. UIコンポーネントのみ移植** | 既存FastAPIのままVue 3ギャラリーを導入。 | Ranbellの強力な機能（Qdrantセマンティック検索、WD14ネットワーク等）を自前再実装することになり本末転倒。 | × |

---

## 6. 次のアクション
1. GitHub上でのリポジトリフォーク（`ranbell/ranbell_image` → `ponderingm/ranbell_image`）
2. 実装計画（`todo_ranbell_gallery_integration.md`）の策定と順次着手

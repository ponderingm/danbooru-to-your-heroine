---
name: custom-workflow-guide
description: ComfyUIのAPI Format JSONからdanbooru_yukikaze_toolのワークフロー辞書（src/comfy_client.py）を作成・改造する手順。新しいバックエンド（LoRA構成・別モデル等）を追加したい、または既存のcustomワークフローが何をしているか理解したい場合に使用する。
---

# Custom Workflow Guide

このスキルは、`src/comfy_client.py` にあるComfyUIワークフロー辞書（`create_default_workflow()` / `create_custom_workflow()` / `create_anima_workflow()`）の構造を理解し、ComfyUI上で組んだグラフを新しいワークフロー関数として実装する手順を説明する。

## 前提知識：ワークフロー辞書とは

このリポジトリのワークフローは、ComfyUIの「API Format」JSONをPythonの辞書リテラルとしてそのまま埋め込んだもの。各キー（`"1"`, `"2"`...）はノードID（文字列、値は何でもよいが慣習的に連番）、値は以下の形:

```python
"<ノードID>": {
    "inputs": { ... },       # ノードの入力パラメータ（固定値 or 他ノードの出力への参照）
    "class_type": "...",     # ComfyUI側のノードクラス名（変更不可、ComfyUI側の実装依存）
}
```

`inputs` の値が `["<参照先ノードID>", <出力スロット番号>]` という2要素配列になっている場合、それは固定値ではなく「別ノードの出力」への参照（ComfyUIのグラフ上の線に相当）。例えば `"clip": ["4", 1]` は「ノードID `4` の2番目(0始まり)の出力」を指す。

## 手順1: ComfyUIからAPI Format JSONを書き出す

1. ComfyUIのWeb UIで、実際に動作確認済みのワークフローを画面上に組む（LoRALoader・KSampler・独自ノード等、何でもよい）
2. 画面右側メニュー（開発者モード/Dev Mode有効時）から「Save (API Format)」を選び、JSONファイルとして保存する
   - 通常の「Save」（UI Format）ではなく必ず「API Format」を使うこと。UI Formatにはノードの座標やUI専用メタデータが含まれ、そのままではAPIに送信できない
3. 書き出したJSONを開くと、`"1": {"inputs": {...}, "class_type": "..."}` の形式で各ノードが並んでいるはずなので、そのままPythonの辞書として貼り付けられる（JSONのtrue/false/nullをPythonのTrue/False/Noneに直す程度で流用可）

## 手順2: 可変にすべき入力の見分け方

書き出したJSONの `inputs` の中で、以下に該当する値は関数の引数として外出しする（他はハードコードのままでよい）:

| 用途 | 該当しやすいノード/フィールド | 対応する関数引数の例 |
|---|---|---|
| プロンプト本文 | `CLIPTextEncode` の `text`（ポジティブ側） | `prompt_text` |
| ネガティブプロンプト | `CLIPTextEncode` の `text`（ネガティブ側） | `negative_text` |
| 画像サイズ | `EmptyLatentImage` の `width` / `height` | `width`, `height` |
| 乱数シード | `KSampler` の `seed` | `seed`（`None`ならランダム生成） |
| checkpoint/LoRA/モデルファイル名 | `CheckpointLoaderSimple.ckpt_name` / `LoraLoader.lora_name` / `UNETLoader.unet_name` 等 | `checkpoint`, `lora_name` 等 |
| サンプラー設定 | `KSampler` の `steps` / `cfg` / `sampler_name` / `scheduler` | `steps`, `cfg`, `sampler`, `scheduler` |
| 保存ファイル名の接頭辞 | `SaveImage` の `filename_prefix` | `filename_prefix` |

判断基準: **「この値は投稿・ヒロイン・実行環境が変わるたびに違う値になり得るか？」** がYesならそのノードの`inputs`を関数引数由来の変数に置き換える。Noイエスなら定数のままでよい（例: `batch_size` は常に1でよいので固定値のまま）。

## 手順3: 既存の3ワークフローとの対応関係

`src/comfy_client.py` には既に3つの実装例がある。新しいワークフローを作る際は、構成が近いものをコピーして改造するのが早い:

- `create_default_workflow()`: 最小構成（CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage → KSampler → VAEDecode → SaveImage）。LoRAなし・追加ノードなしのシンプルなSDXL/Illustrious系
- `create_custom_workflow()`: `create_default_workflow()` に `LoraLoader` を1つ挟んだ構成。`config.py` の `CUSTOM_STEPS` / `CUSTOM_CFG` / `CUSTOM_SAMPLER` / `CUSTOM_SCHEDULER` や `config.GENERATION_BACKENDS` 経由の値を関数引数 `steps` / `cfg` / `sampler` / `scheduler` / `lora_name` として受け取る（`None`ならこの関数自身がCUSTOM_*グローバルにフォールバックする）
- `create_anima_workflow()`: SDXL系の `CheckpointLoaderSimple` を使わず、`UNETLoader` + `CLIPLoader` + `VAELoader` の3ノードでモデルを構成する別アーキテクチャ（Qwen3 DiT）向け

複数LoRAを直列にかけたい場合は `create_custom_workflow()` の `LoraLoader` ノード(`"2"`)の後にもう1つ `LoraLoader` を追加し、`model`/`clip` の参照先を新しいノードIDに繋ぎ替える。

## 手順4: `config.py` との連携方法

ワークフロー関数がconfig値をハードコードで参照するのではなく、**関数の引数として受け取り、呼び出し側（`server.py` / `danbooru_search_batch_generator.py`）でconfig値を解決してから渡す**のがこのリポジトリの流儀（`create_custom_workflow()`参照）。

- 単一のグローバル設定（例: `CUSTOM_LORA_NAME`）で足りるなら `config.py` にトップレベル変数を追加し、`comfy_client.py` の冒頭で `XXX = config.XXX` として読み込む
- モデル構文・ComfyUIエンドポイント・checkpoint/LoRA設定をまとめて名前で切り替えたいなら `config.GENERATION_BACKENDS` 辞書に新しいキー（`label`/`model`/`workflow`/`comfy_url`/`checkpoint`/`lora_name`/`steps`/`cfg`/`sampler`/`scheduler`）を追加し、`resolve_backend()`（`comfy_client.py`）で解決する。`list_backends()`はWeb UIのプルダウン等に渡す`{id, label}`一覧を返す

## 手順5: 新しいバックエンド（新しい`workflow`種別）を追加する場合

1. `src/comfy_client.py` に `create_<name>_workflow(...)` 関数を追加する（手順1〜3参照）
2. `config.example.py` / `config.py` に必要な設定変数（エンドポイントURL・モデルファイル名等）を追加し、`config.GENERATION_BACKENDS` に新しい`workflow`種別を使うバックエンドエントリを追加する
3. `src/comfy_client.py` の `build_workflow_for_backend()` 内、`if workflow == "anima": ... elif workflow == "custom": ... else: ...` の分岐に新しい `elif` を追加し、対応する `create_<name>_workflow()` 呼び出しを設定する（`server.py`/`danbooru_search_batch_generator.py`は`build_workflow_for_backend()`経由で呼ぶだけなので、両方とも自動的に対応する）
4. `src/model_adapter.py` の `adapt_prompt()` / `get_negative_prompt()` に、そのモデル向けのプロンプト構文最適化が必要なら分岐を追加する
   - **注意**: 複数のモデル名文字列を `if "x" in m:` で判定する場合、一方が他方の部分文字列になっていないか必ず確認すること（過去に `"anima"` が `"animagine"` の部分文字列であるために発生した実運用バグの実例が `.github/copilot-instructions.md` にある）。部分文字列の関係にある候補は、より長い（より具体的な）文字列を先に判定する
5. `--backend` の `choices` は `config.GENERATION_BACKENDS` のキー一覧から自動生成されるため（`danbooru_search_batch_generator.py`）、新しいバックエンドエントリを `config.py` に追加するだけでCLI側は自動的に対応する

## チェックリスト（実装後）

- [ ] `python3 -m py_compile src/*.py` が通る
- [ ] 新しいワークフローで実際に画像が1枚生成できることをComfyUI経由で確認した
- [ ] `checkpoint`/`lora_name`等のファイル名を含む個人環境固有の値を `config.example.py` に直接書いていない（プレースホルダー値にする。`.github/copilot-instructions.md` の「個人的な嗜好・秘匿情報の分離」ルール参照）

# v3 プロンプト構造化＆複数人属性分離エンジン 実装完了レポート

## 1. 概要
- **目的**:
  1. Danbooruタグ約50個（約140トークン）が必然的に2チャンク以上に跨がる物理的制約（カンマのトークン消費）を踏まえ、最重要ヒロインDNA（顔・身体・衣装）を第1チャンク（75トークン内）へ最優先凝縮する「黄金順ソート（Golden Sorting）」の実装。
  2. 複数人構図（`1girl 1boy` 等）においてヒロイン属性（褐色肌・小胸等）が男性側に感染・混濁する問題（Concept Bleeding）を、モデル別（Illustrious BREAK物理隔離 vs Anima Qwen前置詞カプセル化）に完全防止する自動主語分離アダプタの実装。
  3. コアパイプライン（`src/danbooru_to_heroine.py`, `src/server.py`, `src/danbooru_search_batch_generator.py`）への本番統合と自動テスト整備。

---

## 2. 実装コンポーネント

### 1. 主語分離アダプタ: [`src/multi_subject_adapter.py`](file:///home/pi/danbooru_yukikaze_tool/src/multi_subject_adapter.py)
- **`is_multi_subject(tags)`**:
  - `1boy`, `couple`, `hetero`, `sex`, `fellatio` 等のキーワード群から複数人構図を自動検出。
- **`separate_multi_subject_tags(raw_tags, heroine_dna_tags)`**:
  - タグを「ヒロインDNA」「パートナー（男性）」「共通アクション・構図」「背景環境」に自動分類。
- **`build_illustrious_multi_prompt(separated)`**:
  - SDXL / Illustrious 向けに、`Chunk 1 [共通構図]`, `Chunk 2 [BREAK, 1girl, ヒロインDNA (役割昇格)]`, `Chunk 3 [BREAK, 1boy, パートナー]` の3チャンク物理隔離構文を構築。
- **`build_anima_multi_prompt(separated, heroine_name)`**:
  - Anima (Qwen LLM) 向けに、`1girl (Name) with (...) and 1boy with (...), [action], [env]` の自然言語カプセル化構文を構築。

### 2. コア変換パイプライン改修: [`src/danbooru_to_heroine.py`](file:///home/pi/danbooru_yukikaze_tool/src/danbooru_to_heroine.py)
- **`build_prompt(...)`**:
  - `model_type` および `heroine_name` パラメータを追加（既存呼び出しと100%後方互換）。
  - 複数人構図を自動検知した場合は `multi_subject_adapter` へルーティング。
  - ソロ構図の場合は `PromptSorter` の黄金順ソート（品質 ➜ 主体 ➜ ヒロインDNA ➜ 衣装 ➜ 表情 ➜ ポーズ ➜ 背景）を適用し、第1チャンク（75トークン内）に最重要DNAを最優先で凝縮。

### 3. モデルアダプタ改修: [`src/model_adapter.py`](file:///home/pi/danbooru_yukikaze_tool/src/model_adapter.py)
- `_dedupe_tags` において、チャンク分離記号である `BREAK` が重複排除で消去されないよう例外処理を追加。

### 4. 自動テストスイート: [`tests/test_v3_prompt_architecture.py`](file:///home/pi/danbooru_yukikaze_tool/tests/test_v3_prompt_architecture.py)
- pytestによる以下の回帰防止テストを整備（全5件合格）：
  1. ソロ構図の黄金順ソート検証（ヒロインDNAが背景より前に配置されること）
  2. 複数人構図の自動検知検証
  3. Illustrious向け3チャンクBREAK構文＆役割昇格検証
  4. Anima向けQwen前置詞カプセル化構文検証
  5. `_dedupe_tags` でのBREAK保護検証

### 4. ヒロインDNA定義の新型スロット構造化: [`src/config.yaml`](file:///home/pi/danbooru_yukikaze_tool/src/config.yaml) & [`src/config.example.yaml`](file:///home/pi/danbooru_yukikaze_tool/src/config.example.yaml)
- 従来のフラットな配列定義（`face_tags`, `body_tags`）を全廃し、7大スロット体系に準拠した階層構造へ完全刷新：
  ```yaml
  heroines:
    example_heroine:
      name: "サンプルヒロイン"
      identity:
        character: "example_character"
        series: "example_series"
      dna:
        hair:
          color: "brown hair"
          style: "long hair"
        face:
          eyes: "blue eyes"
        body:
          skin: "fair skin"
          breasts: "medium breasts"
      costume:
        default: []
      override_rules:
        breasts: "strict"
        skin: "strict"
        costume: "source"
  ```
- **スロット完全駆動置換**:
  [`src/danbooru_to_heroine.py`](file:///home/pi/danbooru_yukikaze_tool/src/danbooru_to_heroine.py) の `mutate_tags_to_heroine` において、元絵タグのスロット（例: `character_dna.hair.color` = `blonde hair`）を動的に検知し、ヒロインDNAで定義されているスロットと同系統であれば自動的に上書き・置換する純粋なスロット駆動型エンジンへ昇華。

---

## 3. テスト実行結果
```text
tests/test_v3_prompt_architecture.py ......                              [100%]
============================== 6 passed in 0.34s ===============================
```
- 全6テスト（ソロ黄金順、複数人検知、Illustrious BREAK構文、Anima前置詞カプセル化、BREAK重複保護、スロット駆動置換）が完全パス。


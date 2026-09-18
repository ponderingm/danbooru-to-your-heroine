---
name: clip_token_budget_optimization
description: CLIPの75トークン物理制限・記号トークン消費・BREAKチャンク境界制御およびQwen前置詞カプセル化によるプロンプト設計最適化技法
---

# CLIP Token Budget Optimization & Subject Separation

## 概要
画像生成モデル（SD1.5, SDXL, Illustrious, Anima等）におけるプロンプト設計において、CLIP Text Encoderの物理的制約（77トークン制限、カンマのトークン消費）および自己回帰LLM（Qwen）の文法特性を理解し、属性汚染（Concept Bleeding）を完全に防止するための最適化設計手法。

---

## 1. CLIPのトークン消費の物理原則
- **語彙辞書の実値**:
  - カンマ `,` は単なる区切り文字ではなく、独立した記号トークン（Token ID: 11 / `,</w>`: 267）として **1トークンを必ず消費する**。
  - プロンプトの先頭 `<|startoftext|>`（ID: 49406）と末尾 `<|endoftext|>`（ID: 49407）で2トークン消費される。
  - したがって、1チャンク（77トークン枠）で実際に使用可能なのは **最大75トークン**。
- **50タグの物理限界**:
  - Danbooru等の50個のタグ群は、単語トークン（約80）＋ カンマ49個（49トークン）＋ SOT/EOT（2）＝ **約131トークン** となり、**原理的に必ず2チャンク以上に跨がる**。
  - カンマを省略するとモデルの構文認識（概念境界）が崩壊するため、カンマを前提としてチャンク配置を能動制御する。

---

## 2. ソロ構図（1girl）の最適化
- **黄金順ソート（Golden Sorting）**:
  - 第1チャンク（先頭75トークン）に **「品質・メタ ➜ ヒロインDNA（顔・身体） ➜ 主要衣装」** を集約・凝縮する。
  - 同一チャンク内の完全な相互自己注意（Global Self-Attention）を最重要属性に100%集中させ、背景・細微装飾などの溢れた要素を第2チャンクに逃がす。

---

## 3. 複数人構図（1girl 1boy / 2girls）の属性分離（Concept Bleeding防止）
同一チャンク内に複数の主語属性（女性の褐色肌・小胸と、男性の筋肉質・短髪など）が混在すると、CLIPのSelf-Attention（$A = \text{Softmax}(QK^T / \sqrt{d})$）によって属性が相互汚染する。

### A. SDXL / Illustrious系（CLIP Text Encoder）
- **BREAKによる物理チャンク遮断**:
  - `BREAK` を挿入すると、CLIPは直ちに現在のチャンクをパディングして終了し、次の中身を新しい77トークンチャンクの先頭へ送り込む。
  - CLIPはチャンク境界を跨いでのSelf-Attention計算を行わないため、**主語間の干渉を数学的にゼロ（Attention Weight = 0）に遮断**できる。
- **役割バインド自動昇格（Role Binding）**:
  - `dark skin` ➜ `dark-skinned female` のように主語を明示した複合タグへ昇格させ、属性の帰属先を確定させる。
- **3チャンク構造**:
  - `Chunk 1`: 共通構図・アクション・背景（`masterpiece, 1girl, 1boy, hetero, fellatio, bedroom, night`）
  - `Chunk 2`: ヒロインDNA完全隔離（`BREAK, 1girl, character_name, twintails, dark-skinned female, small breasts`）
  - `Chunk 3`: パートナー完全隔離（`BREAK, 1boy, couple, tall male, muscular male, penis`）

### B. Anima系（Qwen LLM / DiT）
- **Qwen前置詞カプセル化（Syntactic Binding）**:
  - AnimaはLLM（自己回帰トランスフォーマー）を採用しているため、`BREAK`（CLIPチャンク境界）は無効。
  - 代わりにQwenの高度な文法理解力を活かし、前置詞句と括弧によるカプセル化を行う。
  - `1girl (character_name) with (hair, eyes, skin, breasts) and 1boy with (hair, body, parts), [action], [environment]`

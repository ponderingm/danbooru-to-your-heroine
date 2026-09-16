# 調査・考察: Post 5090505 等でモザイク修正（検閲）が発生する根本原因

## 1. 調査対象（Post 5090505）の情報
- **Danbooru元投稿**: `https://danbooru.donmai.us/posts/5090505`
  - Rating: `e`（Explicit）
  - 元タグ: `bar_censor`, `censored`, `penis`, `surrounded_by_penises`, `gangbang`, `foursome`, `group_sex`, `cum`, `hairjob`, `nipples`, `bad_source` 等
  - 元画像: 商業/同人CG（性器部に黒バー/モザイク修正あり）
- **生成マニフェスト（generated_manifest.json）**:
  - バックエンド: `anima_turbo_slow` (Model: `anima`)
  - UNet: `anima_turboV11.safetensors`, CLIP: `qwen_3_06b_base.safetensors`
  - パラメータ: `steps: 10`, `cfg: 1.0`, `sampler: euler`, `scheduler: normal`
  - ポジティブプロンプト: `midriff, gangbang, grabbing another's hair, hetero, cum on breasts, facial, breasts, fishnets, hairjob, cum, torn thighhighs, 1 girl, rape, torn clothes, cum in mouth, group sex, foursome, nipple stimulation, nipples, solo focus, cum on body, holding another's hair, multiple boys, penis, navel, nipple tweak, thighhighs, surrounded by penises, 3boys, looking at viewer, bad source`
  - ネガティブプロンプト: `worst quality, low quality, score_1, score_2, score_3, ... censored, mosaic, mosaic censoring, bar censor, cleavage`

---

## 2. モザイクが発生する原因の分析

### 原因 ①: 学習データの極端な共起バイアス（最大の要因）
- Danbooru / 日本のイラスト・同人CGの学習データセットにおいて、`penis`, `surrounded_by_penises`, `gangbang`, `foursome` などのハードな性描写タグが付与されている画像の9割以上は、日本の法律（刑法175条）に従って**性器にモザイクや黒バーがかけられている**。
- そのため、AIモデル（特に和製データでファインチューンされた Anima や Illustrious）の潜在空間において、`penis` などの男性器タグは「モザイク状のピクセルパターン」と不可分に結びついている。
- 単にプロンプトから `bar_censor` や `censored` を削っただけでは、`penis` という強力なポジティブタグが「モザイクの視覚特徴」を呼び出してしまう。

### 原因 ②: ポジティブプロンプトに `uncensored` が入っていない
- Booru系モデルは、Danbooruのタグ体系に従い `uncensored`（無修正）というタグで無修正の解剖学的構造を学習している。
- ネガティブプロンプトが「モザイクを避けろ」と指示しても、ポジティブ側で「無修正を描け」という明示的な誘導（`uncensored`）がない場合、モデルは学習頻度の圧倒的に高い「モザイク付きの性器」に回帰してしまう。

### 原因 ③: Anima Turbo（CFG = 1.0）におけるネガティブプロンプトの完全無効化（決定的要因）
- 今回の生成で使用された `anima_turbo_slow` は、蒸留（Turbo）モデルの仕様上 **`cfg: 1.0`** で動作している。
- Classifier-Free Guidance（CFG）の計算式:
  $$\text{Guidance} = \text{Negative} + \text{CFG} \times (\text{Positive} - \text{Negative})$$
- $\text{CFG} = 1.0$ の場合:
  $$\text{Guidance} = \text{Positive}$$
- つまり、**ネガティブプロンプトの項は数式上完全に相殺され、一切反映されない（寄与度0%）**。
- ネガティブプロンプトにいくら `mosaic, bar censor, censored` を入れても、Turboモデル（CFG 1.0）ではモデルに届いていなかった。

### 原因 ④: `bad source` メタタグの混入（副次的要因）
- `default_rules.yaml` の `meta_purge` に `bad source id` はあったが、`bad source`（単体）が抜けていたため、ポジティブプロンプトに残留していた。
- 画質低下やノイズを誘発し、モザイクのような荒れを助長する一因となる。

---

## 3. 今後の恒久対策案

1. **ポジティブプロンプトへの `uncensored` 自動注入（最重要・特効薬）**
   - R18/Explicit な生成時、あるいは全生成の品質プレフィックス/シチュエーション構築時に、ポジティブプロンプトへ `uncensored` を自動付与する。
   - これにより、CFG 1.0 の Turbo モデルであってもポジティブ条件付けとして「モザイクのないクリアな描写」へ強力に誘導できる。
2. **`default_rules.yaml` の更新**
   - `meta_purge` に `bad source` を追加。
3. **Turbo モデル使用時の注意・CFG の最適化**
   - Turboモデルでどうしてもネガティブを利かせたい場合の微小CFG（1.1〜1.2）の実験、または高精度なネガティブ制御が必要な場合の通常モデル（Illustrious等）の使い分け。

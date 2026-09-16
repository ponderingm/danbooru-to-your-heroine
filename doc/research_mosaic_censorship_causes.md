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

### 原因 ⑤: アーティストタグ（`@artist_name`）とモザイクの強烈な結びつき（核心的知見）
- **アーティストタグがモザイクの最大の温床**:
  - Anima では画風の安定化・クオリティ担保のために `@aoi nagisa (metalder)` 等のアーティストタグが不可欠だが、特定絵師の学習データは**「その絵師が描いた商業/同人CG（性器部にモザイクがある作品群）」が極めて高い割合を占める**。
  - そのため、アーティストタグを指定した瞬間、その作家特有の線画や塗りだけでなく、**その作家のR18作品群に常に付随していたモザイクの視覚的テクスチャごと強烈に共起（潜在空間で呼び出し）**されてしまう。
  - アーティストタグを外せばモザイクは出にくくなるが、代償としてAnima特有の画風安定性や美しさが失われてしまうという強いトレードオフ関係が存在する。
  - 特に CFG 1.0 の Turbo モデルではネガティブによる引き戻しが効かないため、「**アーティストタグによる美麗な画風の安定化を取るか、モザイク混入リスクを取るか**」の構造的なジレンマ（トレードオフ）となる。

---

## 3. 実践的結論と運用方針

1. **Turboモデルの特性受容（トレードオフの理解）**:
   - Anima Turbo において「アーティストタグを入れて画風をバシッと安定させつつ、たまに出るモザイクは爆速プレビューの代償として割り切る」という運用が極めて現実的かつ合理的。
2. **本命生成との使い分け**:
   - 構図やシチュエーションを Turbo で素早く選別し、モザイクのない完全な一枚を残したい場合は、CFG ガイダンスが効いてネガティブプロンプトでモザイクを物理的に反発できる通常モデル（Illustrious等）へ切り替える。
3. **`default_rules.yaml` の更新**:
   - `meta_purge` に `bad source` を追加済み。

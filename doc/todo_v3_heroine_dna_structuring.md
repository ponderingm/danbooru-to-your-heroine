# 🧬 [v3.0 TODO] ヒロインDNA管理の強化：タグ羅列プロンプトの構造化（LLMによる分類）

- **計画バージョン**: v3.0
- **作成日**: 2026-09-16
- **ステータス**: 構想・要件定義フェーズ

---

## 1. 🎯 課題と背景

### 1.1 現状（v2.0）の課題
- v2.0 ではヒロインDNAを `face`, `body`, `costume`, `negative` の3層カテゴリに大別して管理しているが、各カテゴリ内のプロンプトは依然として**フラットなカンマ区切りタグの羅列**（例: `"brown hair, short hair, flower hair ornament, brown eyes"`）となっている。
- そのため、元絵から特定の部位（例: 「髪飾りだけをヒロインのものに変えたい」「衣装のうちインナーだけを差し替えたい」「装飾品を残して服だけを剥ぎたい」等）をピンポイントで置換・合成・判定する際、タグ文字列の単純なテキスト照合やリスト引き算に頼らざるを得ない。

### 1.2 目指す姿（v3.0）
- LLMを活用して、ヒロインの全特徴タグおよび元絵のプロンプトタグを**意味論的（セマンティック）にスロット分解・構造化**する。
- 単なるタグの足し引きを超え、身体部位や衣装レイヤーごとの高精度な換装パイプラインを構築する。

---

## 2. 💡 構造化モデル：7大スロット ＆ サブプロパティ体系 (Dot Notation)

各タグは **`親スロット.サブカテゴリ`** のドット記法で一意にスロット付けされ、細やかな部分置換やモデル向け整列を可能にする。

### 2.1 スロット ＆ サブプロパティ一覧

| 親スロット | サブプロパティ (Path) | 具体例タグ | 換装・整列時の制御用途 |
|---|---|---|---|
| **1. `meta_quality`** | `.quality`<br>`.artist`<br>`.format` | `masterpiece`, `score_9`<br>`@aoi nagisa (metalder)`<br>`absurdres`, `highres` | プロンプト最前列固定、絵師プリセット制御 |
| **2. `subject`** | `.count`<br>`.gender` | `1girl`, `solo`, `2girls`<br>`female`, `tomboy` | 構図の基本主体を確定 |
| **3. `character_dna`** | `.hair.color`<br>`.hair.style`<br>`.hair.feature`<br>`.face.eyes`<br>`.face.marks`<br>`.body.skin`<br>`.body.breasts`<br>`.body.build`<br>`.body.marks` | `brown_hair`, `blonde_hair`<br>`short_hair`, `twintails`<br>`bangs`, `ahoge`<br>`brown_eyes`, `gentle_eyes`<br>`mole_under_eye`, `freckles`<br>`dark_skin`, `pale_skin`<br>`small_breasts`, `large_breasts`<br>`slender`, `wide_hips`<br>`tanlines`, `navel` | **ヒロイン不変DNAスロット**<br>元絵の同一サブ属性を完全パージし、ヒロインの固有特徴を差し替え。<br>「髪型だけ元絵に寄せる（コスプレモード）」などの部分オーバーライドも可能。 |
| **4. `costume`** | `.outer`<br>`.top`<br>`.bottom`<br>`.full_body`<br>`.inner`<br>`.legwear`<br>`.footwear` | `jacket`, `cloak`<br>`halterneck`, `blouse`<br>`pleated_skirt`, `shorts`<br>`dress`, `night_dress`, `maid_uniform`<br>`micro_bikini`, `bra`, `panties`<br>`thighhighs`, `stockings`<br>`high_heels`, `boots`, `barefoot` | **衣装レイヤードスロット**<br>「上着は脱がせてインナーだけ残す」「靴だけヒロイン指定のピンヒールにする」「衣装アドオン（722着）を丸ごと着せる」等の高度な衣装制御。 |
| **5. `accessories`** | `.head`<br>`.eyes`<br>`.neck`<br>`.arms`<br>`.body`<br>`.jewelry`<br>`.item` | `flower_hair_ornament`, `ribbon`<br>`glasses`, `eyepatch`<br>`white_lace_shawl`, `choker`<br>`black_see-through_long_gloves`<br>`gold_garter_ring`, `sash`<br>`gold_bracelet`, `labia_ring`<br>`cocktail_glass`, `sword` | **装飾・小物スロット**<br>元絵の神絵師特有の共起装飾を継承しつつ、ヒロインの象徴装飾（左側頭部の一輪花や金ブレスレット等）と衝突なく重ね着。 |
| **6. `action_pose`** | `.expression`<br>`.pose`<br>`.gaze`<br>`.framing`<br>`.interaction` | `smile`, `blush`, `open_mouth`<br>`sitting`, `lying`, `standing`<br>`looking_at_viewer`<br>`upper_body`, `cowboy_shot`, `pov`<br>`holding_glass`, `eating` | **構図・シチュエーションスロット**<br>元絵の魅力的なポーズ・表情・フェチ構図を100%継承。 |
| **7. `environment`** | `.location`<br>`.time_weather`<br>`.lighting`<br>`.effects`<br>`.background` | `bar`, `beach`, `bedroom`<br>`night`, `sunset`, `rain`<br>`sunlight`, `shadow`, `glowing`<br>`depth_of_field`, `sparkles`<br>`simple_background`, `white_background` | **環境・空気感スロット**<br>末尾に配置してシーンの背景ノイズやライティングを確定。 |

---

### 2.2 ヒロイン定義スキーマ例 (v3.0)

```yaml
heroine_id: yukikaze_future
identity:
  dna:
    hair:
      color: "brown hair"
      style: "short hair"
      feature: "bangs"
    face:
      eyes: "brown eyes, gentle eyes"
    body:
      skin: "dark skin, sun-kissed tan"
      breasts: "small breasts, B77"
      build: "slender, wide hips, H86"
      marks: "navel"
  signature_costumes:
    night_dress:
      costume:
        full_body: "black halterneck dress, backless dress, high leg, deep slit"
        inner: "black see-through lingerie"
        legwear: "bare legs"
        footwear: "black high heels, stiletto heels"
      accessories:
        head: "single white flower, hair flower"
        neck: "white lace shawl"
        arms: "black see-through long gloves, gold bracelet"
        body: "crimson sash, gold glitter"
        jewelry: "gold garter ring, gold anklet"
```

---

## 3. 🚀 構造化の絶大なメリット

### 3.1 ① ヒロインDNAの保持・分離の堅牢化
- **属性の混濁を物理的に根絶**:
  - フラットなタグ羅列では「元絵の金髪（`blonde hair`）」と「ヒロインの茶髪（`brown hair`）」が同時に紛れ込んだり、元絵の服の一部が意図せずヒロイン衣装と混ざり合う事故が発生しやすい。
  - スロット単位（`hair.color`, `body.breasts`, `costume.inner` 等）で厳密に管理することで、元絵の同一スロットタグを完全に消去し、ヒロインDNAのスロット値を注入できるため、ヒロインの一貫性が強固に保たれる。

### 3.2 ② モデル特性を極限まで引き出すプロンプト最適整列（Optimal Slot Sorting）
- **Text EncoderのAttention特性に適合**:
  - SDXL（CLIP）やAnima（T5/DiT）の言語モデルは、**プロンプトの先頭トークンほど強烈なアテンション（重み）**を受け、中盤〜後方にかけて緩やかに減衰する。
  - また、タグの並び順（例: `品質/メタ` ➜ `主題/人数` ➜ `ヒロインDNA(顔・髪・体)` ➜ `衣装・装飾` ➜ `ポーズ・表情・行為` ➜ `背景・環境・ライティング`）によって生成画像の整合性とクオリティが劇的に変化する。
  - タグがスロット構造化されていれば、使用するモデル（Illustrious / Anima / SDXL）のアーキテクチャ特性に合わせた**「黄金の整列順」へプロンプトを全自動ソート**してComfyUIへ引き渡すことが可能になる。

### 3.3 ③ 神絵師の共起構図 × ヒロインDNAのピンポイント結合 ＆ アドオン互換
- 元絵が持つゴージャスな微細装飾（チェーン、アクセサリー等）だけをヒロインに移植、あるいはヒロインのシグネチャ装飾と美しくレイヤード。
- `docs/costume_addon_design_spec.md` で計画されている汎用衣装パック（722着等）とのスロット単位での完全着脱・重ね着が可能になる。

---

## 4. 🛠️ 実装アーキテクチャ：自己増殖型ハイブリッド分類DB

「生成のたびに毎回LLMを呼ぶと遅いしコストがかかる」という課題を、**『事前構築DB ＋ オンデマンドLLM推論（自動キャッシュ蓄積）』**のハイブリッド方式で美しく解決する。

```mermaid
flowchart TD
    InputTag["入力タグ (例: pleated_skirt, labia_ring)"] --> CheckDB{"ローカル分類DBに<br/>登録済みか？"}
    CheckDB -- "Yes (90%以上 / 数ミリ秒)" --> SlotAssigned["スロット割り当て確定<br/>(costume.bottom / body.pierce)"]
    CheckDB -- "No (未知タグ)" --> CallLLM["LLM推論<br/>(Ollama / Gemini API)"]
    CallLLM --> Classify["スロット分類判定"]
    Classify --> SaveDB["ローカル分類DBへ自動保存<br/>(自己増殖キャッシュ)"]
    SaveDB --> SlotAssigned
    SlotAssigned --> SortEngine["モデル別 最適整列エンジン<br/>(Prompt Slot Sorter)"]
    SortEngine --> FinalPrompt["ComfyUI用 黄金順プロンプト"]
```

### 4.1 構造の詳細
1. **Base層 ＆ User層の2層ストレージ設計**:
   - **Base層（Git管理・共通資産）: `src/rules/tags_classification_base.json`**
     - マニフェストから分類した約1万件のマスター辞書。クローンした誰もが最初から使える共通の軽量JSON辞書。
   - **User層（非公開・.gitignore対象）: `database/tags_classification_cache.json`**
     - 個人の生成運用中にオンデマンドLLM推論によって自動追記される未知タグの自己増殖キャッシュ。
   - 実行時に両者をマージしてメモリ展開（ハッシュマップ）し、**$O(1)$・数ミリ秒で即座に引き当て**。
2. **1タグ ＝ 1スロット（Primary Path）の原則**:
   - 複合タグ（例: `striped_bikini`）は最も支配的な単一スロット（例: `costume.inner`）へ割り当て、二重計上やソート時の重複バグを完全防止。
3. **Chunkingバッチ分類戦略（50〜100タグ一括）**:
   - 12,800個のタグを1件ずつ投げるのではなく、50〜100件を1つのLLMプロンプトにまとめてJSON構造で一括返却させる。
   - 約130〜200リクエストで完了し、Gemini APIなら数分で初期DBが完成。
4. **v2ヒロイン設定との完全後方互換性**:
   - 従来のカンマ区切りフラット文字列も、この分類DBを通すことで自動的にスロット構造へ昇華させるアダプタを搭載。過去の設定を壊さずシームレスに移行可能。

### 4.2 💡 最強のコールドスタート戦略：生成済みマニフェストからの逆算構築
- **大衆Danbooruタグではなく「実績データ」を活用**:
  - Danbooru全体（数百万件）から無作為に抽出すると、使わないメタタグや無関係な作品タグが大量に混入してしまう。
  - [`database/generated_manifest.json`](../database/generated_manifest.json) に蓄積された**生成実績データ（約5,900件・約12,800ユニークタグ）**からタグを抽出し、出現頻度順に集約。
  - あなたの制作環境で「実際に使われ、愛用されている厳選タグ群」だけをLLMで一括分類することで、**初日から実戦適合率（ヒット率）99%を誇る最高純度の初期分類DB**をノーコストかつ瞬時にブートストラップ可能。

---

## 5. 📝 開発ロードマップ（v3.0）

- [ ] **Step 1: LLM分類用システムプロンプトの作成** (`src/prompts/tag_classification_system_instruction.md`)
- [ ] **Step 2: マニフェスト逆算バッチスクリプトの実装** (`scripts/bootstrap_tag_db_from_manifest.py`): `database/generated_manifest.json` からタグ頻度を抽出しLLM一括分類して `src/rules/tags_classification_base.json` を生成
- [ ] **Step 3: ハイブリッド分類DBローダー ＆ オンデマンド自動蓄積エンジンの実装** (`src/tag_classifier.py`)
- [ ] **Step 4: モデル別プロンプト最適整列ソーターの実装** (`src/prompt_sorter.py`)
- [ ] **Step 5: プロンプトビルダー（`danbooru_to_heroine.py`）へのスロット結合 ＆ 後方互換アダプタ**
- [ ] **Step 6: WebUIのヒロイン設定タブでのスロット別チップエディタUI実装**


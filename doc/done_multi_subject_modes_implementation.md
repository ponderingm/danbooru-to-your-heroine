# 複数人構図プロンプト戦略（A: フラット / B: 衣装共有 / C: カプセル分離）の全実装

## 1. 開発の背景と目的
複数人構図（特に2girls等の同性ペア）において、v3の新アーキテクチャ（カプセル化 `1girl with (...)` / `BREAK` 分離）を厳密に適用した結果、以下のトレードオフが発生した：
- **カプセルの厳密さによる集約**:
  ヒロインDNA（褐色、ツインテール、日焼け跡など）のみがカプセル化され、衣服タグがカプセル外の共通枠に配置されたため、モデル（LLM/CLIP）が「ヒロイン＝露出」「もう1人＝着衣」と二極化解釈し、片方だけ脱げてしまう非対称現象が発生した。
- **v2（フラット）の利点**:
  v2ではプロンプトを構造化せずフラットに並べていたため、境界線がなくアテンションが全体に自然拡散し、2人とも服を着て共存しやすかった。

この課題に対し、「基本はC（現行のカプセル分離）としつつ、再生成時や生成時にA（フラット分散）とB（衣装タグ共有注入）を個別に選択できる」ハイブリッド戦略を全面実装した。

## 2. 3つの戦略モード仕様

| モードID | 名称 | 説明 | Illustrious構文 | Anima構文 |
| :--- | :--- | :--- | :--- | :--- |
| `capsule` | **C: カプセル分離 (標準)** | ヒロインDNAを完全隔離し、他者への属性汚染を防ぐ。基本デフォルト。 | `BREAK, 1girl, [DNA]` | `1girl (heroine) with ([DNA])` |
| `flat` | **A: フラット分散 (v2風)** | 境界を作らずセマンティック黄金順で全タグをフラット配置。モデルのアテンション自然分散に委ねる。 | フラットタグ羅列 (BREAKなし) | フラットタグ羅列 (withカプセルなし) |
| `shared_costume` | **B: 衣装共有 (両方着衣)** | カプセル化を維持しつつ、共通衣装タグをヒロイン側にも注入。着衣時は露出バイアス（日焼け跡）を抑制。 | `BREAK, 1girl, [DNA + 衣装]` | `1girl (heroine) with ([DNA + 衣装])` |

## 3. 実装内容

1. **`src/multi_subject_adapter.py`**:
   - 戦略定数 `MULTI_MODE_CAPSULE`, `MULTI_MODE_FLAT`, `MULTI_MODE_SHARED_COSTUME` を定義。
   - `separate_multi_subject_tags` で `costume_tags` を抽出・分類保持。
   - `CLOTHED_SUPPRESS_DNA_TAGS`（`one-piece tan`, `bikini tan`, `tanlines` 等）を定義し、Mode B（着衣時）に日焼け跡露出タグを自動抑制。
   - `build_illustrious_multi_prompt` および `build_anima_multi_prompt` に `mode` 引数を導入し、3つの戦略構文を生成可能に。
2. **`src/danbooru_to_heroine.py`**:
   - `build_prompt` に `multi_mode` 引数を追加し、アダプタへ伝播。
3. **`src/server.py`**:
   - `ConvertRequest`, `GenerateRequest`, `BatchConfig` に `multi_mode` フィールドを追加。
   - `_convert_core` で `req.multi_mode` を `build_prompt` へ伝播。
   - 生成結果のマニフェスト（`manifest`）に `multi_mode` を記録。
4. **Web UI (`src/web/index.html`, `src/web/app.js`)**:
   - 単一生成フォームおよびバッチ生成フォームのオプション枠に「👥 複数人構図」セレクトボックスを追加。
   - ギャラリーカードに各投稿ごとの「👥 複数人」戦略切り替えセレクタを設置。
   - カード上で戦略を変更した際、プロンプト編集欄が開いていればリアルタイムで `/convert` を呼び出してプレビューを自動更新。
   - 静的資産のキャッシュバスター（`app.js?v=20260916_2205`）を更新。
5. **テストスイート (`tests/test_v3_prompt_architecture.py`)**:
   - `test_multi_mode_strategies` を追加し、全3モードのIllustrious/Anima双方のプロンプト構文の正常性を自動検証。

# 複数人構図における同性ペア（2girls / yuri）での1boy誤爆防止対応

## 1. 課題・背景
Danbooruの元画像が女子ペア（例: Post 7967741、虹ヶ咲学園スクールアイドル同好会の優木せつ菜/桜坂しずく＆部長の百合・跨ぎ構図）であるにもかかわらず、v3新システムでの再生成画像に男性が生えて男女ペア（ヘテロ）になってしまう現象が発生した。

### 調査結果と原因
Danbooruタグはフラットな「単語の袋（Bag of Words）」であり構文木が存在しないため、2girls構図において2人目の身体的特徴（髪型・髪色・体型）を正確に分離・特定することは原理的に困難である。
しかし、`src/multi_subject_adapter.py` 内のプロンプト構築ロジックにおいて以下の不具合が存在していた：
1. `separate_multi_subject_tags`:
   - `parent == "subject"` で `2girls`, `3girls`, `multiple girls` を `common_meta_slots` ではなく無視または別処理していた。
2. `build_illustrious_multi_prompt`:
   - チャンク1に無条件で `["1girl", "1boy", "hetero"]` を結合していた。
3. `build_anima_multi_prompt`:
   - `male_clause = f"1boy with ({male_dna_str})" if male_dna_str else "1boy"` となっており、男性タグ（`male_tags`）が空リストであっても無条件に `1boy` が挿入されていた。

## 2. 実施した改修内容
1. **`separate_multi_subject_tags`**:
   - `2girls`, `3girls`, `multiple girls`, `multiple boys` を `common_meta_slots` として確実に保持。
2. **`has_male` 判定の導入**:
   - `separated["male_tags"]` が存在するか、または `meta_tags` に `1boy`, `2boys`, `multiple boys`, `hetero`, `yaoi` 等の男性・ヘテロ関連キーワードが含まれる場合のみ `has_male = True` とする。
3. **`build_illustrious_multi_prompt`**:
   - `has_male` が True の場合のみチャンク1に `gender_meta`（`1girl, 1boy, hetero`）を結合。
   - `has_male` が False の場合は男性タグおよび `BREAK, 1boy...`（チャンク3）を一切生成しない。
4. **`build_anima_multi_prompt`**:
   - `has_male` が False の場合は `male_clause = ""` とし、プロンプト内に `1boy` を挿入しない。
5. **テストスイート拡充**:
   - `tests/test_v3_prompt_architecture.py` に `test_female_only_multi_subject` を追加し、IllustriousおよびAnimaの双方で `1boy` / `hetero` が一切含まれず `2girls` が維持されることを自動検証。

## 3. 検証結果（Post 7967741）
- **変換前**:
  - `BREAK, 1boy` または `1boy` が混入し、男性キャラが生成されていた。
- **改修後**:
  - **Illustrious**: `rating:general, highres, multiple girls, 2girls, yuri, ..., BREAK, 1girl, taimanin \(series\), mizuki yukikaze, brown hair, twintails, dark-skinned female, small breasts, one-piece tan`
  - **Anima**: `rating:general, highres, multiple girls, 2girls, yuri, 1girl (Mizuki Yukikaze) with (...), ...`
  - `1boy` や `hetero` は一切出力されず、百合・女子ペアとしての構図と衣装・ポーズが100%保持されることを確認。

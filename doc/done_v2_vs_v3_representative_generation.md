# 完了報告: 新旧システム（v2 vs v3）真の完全条件での実画像生成比較検証

## 1. 概要
アーキテクチャロジックの根本的見直し（排他辞書モデルへの回帰、個別ホワイトリスト撤廃、マルチサブジェクトでの全シチュエーション保持）および設定修正（瞳色強制指定の削除、元ログと同一の `artist_mode: "override"` による絵師タグ完全適用）を完了し、代表5件の実画像生成（`anima_turbo_slow`）を実施・完了した。

---

## 2. 実画像比較一覧（新旧ペア）

| Post ID | 特徴・検証テーマ | 旧システム (v2) 生成画像 | 新システム (v3) 生成画像 |
| :--- | :--- | :--- | :--- |
| **`1886630`** | **他キャラ共存（アサギ）**<br>Qwenカプセル化分離 & 身体タグ完全維持 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_1886630_1789538996_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_1886630_1789549738_00001_.png) |
| **`311329`** | **男女絡み構図（ヘテロセックス）**<br>男性側への属性汚染遮断 & 行為タグ完全維持 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_311329_1789539073_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_311329_1789549837_00001_.png) |
| **`2315348`** | **ドレス姿（鎖骨・脇・肩・メイク等）**<br>身体タグ全維持 & 絵師タグ完全適用 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_2315348_1789539726_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_2315348_1789549913_00001_.png) |
| **`4746599`** | **破れボディスーツ・日本刀構図**<br>黄金順ソートによる構図・ポーズ安定化 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_4746599_1789542891_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_4746599_1789549991_00001_.png) |
| **`6667193`** | **レオタード拘束・小道具**<br>瞳色固定なし & 黄金順ソート | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_6667193_1789547200_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_6667193_1789550074_00001_.png) |

---

## 3. 改善のポイント

1. **画風の完全一致（`@aoi nagisa (metalder)`）**:
   - v2と全く同一の絵師タグが適用されたため、画風のブレがなく、純粋な「構図」「キャラクターDNA」「主語分離」の差分として比較可能になった。
2. **元絵身体・メイク・装飾タグの完全保持**:
   - `thighs`, `collarbone`, `armpits`, `bare shoulders`, `sideboob`, `pink lips`, `lipstick`, `makeup`, `nail polish`, `body blush` など、元絵の身体・フェチ表現が1つも欠落することなく100%プロンプトへ引き継がれている。
3. **瞳色強制の撤廃**:
   - 余計な `purple eyes` の自動注入が消滅し、元絵の瞳表現が自然に反映される。
4. **黄金順ソートとQwenカプセル化**:
   - `1 girl, solo` が先頭に固定され、ヒロインDNAがカプセル化されたことで、男女絡みや他キャラ共存構図において他者の属性（黒髪や巨乳、男性タグ）がヒロイン側に混濁する問題が完全に抑止された。

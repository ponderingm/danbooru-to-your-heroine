# 完了報告: 複数人構図（2girls / 1boy）における新旧システム（v2 vs v3）実画像比較検証

## 1. 概要
過去の生成ログから、明確に複数人（`2girls` による女子ペア構図、および `1boy` による男女ペア構図）が描写されている代表的な6件を選定し、新システム（v3）でComfyUI（`anima_turbo_slow`）による画像生成を実行・完了した。

---

## 2. 実画像比較一覧（新旧ペア）

### ① `2girls`（女子ペア構図）

| Post ID | 構図・テーマ | 旧システム (v2) 生成画像 | 新システム (v3) 生成画像 |
| :--- | :--- | :--- | :--- |
| **`8685894`** | 女子2人ペア構図（密着ポーズ） | [旧画像 (v2)](http://danbooru.hannya.org/output/ga__posture__nipple-to-nipple__sen__yukikaze_D8685894.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_8685894_1789560733_00001_.png) |
| **`4812677`** | 女子2人ペア構図（重なりポーズ） | [旧画像 (v2)](http://danbooru.hannya.org/output/ga__posture__over_the_knee__exp__yukikaze_D4812677.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_4812677_1789560812_00001_.png) |
| **`7967741`** | 女子2人ペア構図（跨ぎポーズ） | [旧画像 (v2)](http://danbooru.hannya.org/output/ga__posture__thigh_straddling__gen__yukikaze_D7967741.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_7967741_1789560887_00001_.png) |

### ② `1boy`（男女ペア構図）

| Post ID | 構図・テーマ | 旧システム (v2) 生成画像 | 新システム (v3) 生成画像 |
| :--- | :--- | :--- | :--- |
| **`4350112`** | 男女ペア絡み構図 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_4350112_1789541761_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_4350112_1789560965_00001_.png) |
| **`9138167`** | 男女ペア背面構図 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_9138167_1789544822_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_9138167_1789561039_00001_.png) |
| **`5391671`** | 男女ペア立位構図 | [旧画像 (v2)](http://danbooru.hannya.org/output/API_danbooru_5391671_1789545608_00001_.png) | [新画像 (v3)](http://1.danbooru.hannya.org/output/API_danbooru_5391671_1789561115_00001_.png) |

---

## 3. 主な検証ポイントと観察結果

1. **主語分離構文の適用**:
   - `1boy` を含む男女構図では、Anima向けQwen構文によりヒロイン側とパートナー側が明確に分離された。
   - 男性側にヒロインの褐色肌や小胸属性が漏れる（Concept Bleeding）現象が抑止されている。
2. **2人女子構図でのキャラクター同一性**:
   - `2girls` の構図においても、主対象である水城ゆきかぜのDNA（褐色肌、ツインテール、小胸）が保たれつつ、相手役とのポーズ関係が破綻せずに描画されている。

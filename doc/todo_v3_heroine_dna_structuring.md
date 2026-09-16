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

## 2. 💡 構造化モデル（構想）

LLMによって、ヒロインおよび投稿タグを以下のような構造化JSON/スキーマへ自動分類・展開する：

```json
{
  "heroine_id": "example_heroine",
  "identity": {
    "hair": {
      "color": "brown",
      "style": "short_hair",
      "bangs": "bangs",
      "accessories": ["flower_hair_ornament", "single_white_flower"]
    },
    "face": {
      "eyes": ["brown_eyes", "gentle_eyes"],
      "expression_defaults": ["smile", "calm"]
    },
    "body": {
      "skin": ["dark_skin", "sun-kissed_tan"],
      "breasts": "small_breasts",
      "build": ["slender", "wide_hips", "athletic_thighs"]
    },
    "signature_costumes": {
      "night_dress": {
        "outer": ["black_halterneck", "backless_dress"],
        "accents": ["crimson_sash", "gold_glitter"],
        "accessories": ["white_lace_shawl", "gold_bracelet", "gold_anklet"],
        "gloves": ["black_see-through_long_gloves"],
        "footwear": ["black_high_heels"]
      }
    }
  }
}
```

---

## 3. 🚀 期待される効果と活用用途

1. **神絵師の共起構図 × ヒロインDNAのピンポイント結合**:
   - 元絵が「ピアスやネックレス等の微細装飾」を持っている場合、ヒロインの耳や首元のスロットと衝突判定を行い、装飾だけを自然にヒロイン仕様へ置き換える、あるいは元絵のゴージャスな装飾をヒロインに移植する。
2. **衣装アドオン（Costume Addon）との完全互換**:
   - `docs/costume_addon_design_spec.md` で計画されている汎用アドオンパック（722着の衣装等）と組み合わせる際、構造化されたスロット単位で「下着」「上着」「小物」を自在にレイヤード合成可能。
3. **WebUIのDNAエディタの飛躍的進化**:
   - プレーンテキスト入力ではなく、スロット別（髪・瞳・肌・アクセサリ等）の直感的なチップUIとして編集・プレビュー可能にする。

---

## 4. 📝 開発ロードマップ（v3.0）

- [ ] LLMプロンプト設計: タグ羅列からスロット構造化JSONを抽出するシステムインストラクションの作成
- [ ] ヒロインDNAスキーマ（Pydanticモデル）の定義
- [ ] `heroine_helper.py` の拡張（出現頻度解析 ＋ LLM構造化の自動パイプライン）
- [ ] プロンプトビルダー（`danbooru_to_heroine.py`）のスロットベース合成エンジンの実装
- [ ] WebUIのヒロイン設定タブでのスロット別チップエディタUI実装

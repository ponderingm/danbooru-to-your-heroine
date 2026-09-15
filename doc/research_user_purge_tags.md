# 調査結果: User独自パージタグが反映されず grayscale 等がパージされない原因

## 1. 現象
- `config.yaml` や WebUI でパージタグ（`purge_tags`）に `greyscale` や `grayscale`、`monochrome` などを指定しても、プロンプト生成時に除去（パージ）されず `situation_tags` に残存してしまう。
- プロンプトに `grayscale` や `monochrome` が残ることで、`server.py` の `allow_comic` フラグが True になり、ネガティブプロンプト側のコミック/モノクロ抑制も解除されてモノクロ画像が生成される原因となっていた。

## 2. 原因調査

### (A) タグ処理ループの評価順序（最重要原因）
`src/danbooru_to_heroine.py` の `mutate_tags_to_heroine()` において、一般タグ（`general_tags`）を走査する際の条件判定順序が以下のようになっていた：
```python
for tag in general_tags:
    tag_norm = tag.replace("_", " ").lower()

    # 1. 画風判定
    if tag_norm in art_style_set:
        if art_style_mode == "source":
            situation_tags.append(tag.replace("_", " "))
            detected_source_style.add(tag_norm)
            continue
        else:
            removed_tags.append(tag_norm)
            continue

    # 2. 胸サイズ判定
    ...
    # 3. 肌色判定
    ...
    # 4. negative_tags
    ...
    # 5. blacklist
    ...
    # 6. purge_set
    if tag_norm in purge_set:
        removed_tags.append(tag_norm)
        continue
```
- `src/rules/default_rules.yaml` の `art_styles.manga_comic` に `grayscale`, `greyscale`, `monochrome` 等が定義されている。
- ヒロイン設定の `override_rules.art_style` のデフォルト値は `"source"`（元絵維持）。
- そのため、元絵に `grayscale` や `monochrome` がある場合、`tag_norm in art_style_set` に合致し、`art_style_mode == "source"` によって **即座に `situation_tags.append()` されて `continue`** されていた。
- 結果として、後続にある `if tag_norm in purge_set:` の判定まで一度も到達せず、パージタグが完全にバイパスされていた。

### (B) 英米綴り（gray / grey）の差異と非対称性
- Danbooru では英国式綴り `greyscale` を主タグとし、`grayscale` をエイリアスとしている。
- 一方、Gelbooru 等の他サイトやユーザーの直接入力では米国式綴り `grayscale` が使われることが多い。
- `config.yaml` の初期パージタグには `- greyscale` のみが登録されており、`grayscale` が単体で来た場合に文字列表致しないリスクがあった。
- さらに、ユーザーが `grayscale` を登録しても `greyscale` がパージされない、あるいはその逆の非対称性があった。

### (C) 設定キーのフォールバック
- ドキュメント上 `user_purge_tags` と `purge_tags` の表記揺れがあるが、`config.py` 側では `USER_CONFIG.get("purge_tags")` のみ参照していたため、手動設定時のフォールバックを持たせるべきであった。

## 3. 解決方針
1. `src/danbooru_to_heroine.py` の `mutate_tags_to_heroine()` において、`negative_tags`, `blacklist`, `purge_set`, `CENSORING_BLACKLIST`, `known_character_tags` の除外判定を `art_style_set`・`BREAST_TAGS`・`skin_tags_set` より**前（最優先）**に実行する。
2. `src/config.py` において、パージタグおよび除外解除タグのロード時に `grey` ↔ `gray` の自動同義語展開を行い、どちらの綴りが指定されても双方確実にパージ対象とする。
3. `src/config.yaml` および `src/config.example.yaml` の初期 `purge_tags` に `grayscale` を明示的に追加する。
4. `src/config.py` と `src/server.py` で `purge_tags` と `user_purge_tags` の両キーを安全にフォールバック取得する。

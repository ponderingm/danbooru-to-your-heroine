# 完了報告: 標準ネガティブプロンプトへのモザイク・バー検閲抑止タグ追加

## 1. 概要
AIモデル（Illustrious-XL / Anima）が生成時に自発的にモザイクや修正バーを描画してしまう現象を防止するため、[src/model_adapter.py](file:///home/pi/danbooru_yukikaze_tool/src/model_adapter.py) の標準ネガティブプロンプト生成関数 `get_negative_prompt()` に `mosaic`, `mosaic censoring`, `bar censor` を追加した。

## 2. 実施した変更
- **ファイル**: [src/model_adapter.py](file:///home/pi/danbooru_yukikaze_tool/src/model_adapter.py)
  - `get_negative_prompt()` において：
    - **Illustrious-XL**: `base_tags` の末尾付近に `"mosaic"`, `"mosaic censoring"`, `"bar censor"` を追加。
    - **Anima**: `neg` 文字列に `"censored"`, `"mosaic"`, `"mosaic censoring"`, `"bar censor"` を追加。

## 3. 検証
- テストスクリプトにて Illustrious、Anima、およびヒロイン合成後のネガティブプロンプト出力すべてに `mosaic`, `mosaic censoring`, `bar censor` が含まれることを確認。
- `py_compile` による全ソースの構文チェックをパス。

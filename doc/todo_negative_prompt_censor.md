# 作業計画: 標準ネガティブプロンプトへのモザイク・バー検閲抑止タグ追加

## 目的
画像生成時にモデルが自発的にモザイクや修正バーを描画するのを防ぐため、標準ネガティブプロンプトに `mosaic`, `mosaic censoring`, `bar censor` を追加する。

## 作業タスク
- [ ] 1. `src/model_adapter.py` の `get_negative_prompt()` を修正
  - Illustrious-XL 向け `base_tags` に `mosaic`, `mosaic censoring`, `bar censor` を追加
  - Anima 向け `neg` に `censored`, `mosaic`, `mosaic censoring`, `bar censor` を追加
- [ ] 2. 動作確認・テスト
  - `get_negative_prompt()` の出力を確認するテストスクリプトを実行
  - `python3 -m py_compile src/*.py` による構文チェック
- [ ] 3. 完了報告ドキュメント `doc/done_negative_prompt_censor.md` の作成

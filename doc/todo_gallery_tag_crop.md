# TODO: ギャラリーのタグ追加ドロップダウンのスマホ表示崩れ対策（タグ表示クロップ & 幅制限）

## 背景・課題
- スマホ表示時、ギャラリー画面の「タグ追加」ドロップダウン（`#filter-tag-select`）内のタグ名が長い場合（Danbooruタグは30〜50文字を超えるものがある）、`<select>` 要素の幅が最長テキスト長に合わせて自動拡張される。
- これによりスマホの画面幅（360px〜430px）を突き抜け、親コンテナおよび画面全体の横幅が押し広げられて横スクロールやレイアウト崩れが発生する。

## 対応方針
1. **JavaScript側の対策（タグ表示文字列のクロップ）**:
   - `src/web/app.js` 冒頭に `GALLERY_FILTER_TAG_MAX_LENGTH`（例: 24文字）を定義。
   - タグの表示用フォーマット関数 `formatDisplayTag(tag, maxLength)` を用意し、指定文字数を超える場合は末尾を `…` に切り詰める。
   - `<option>` 要素の `value` は完全なタグ名を保持（絞り込み機能には影響ゼロ）。
   - `<option>` 要素の `title` 属性に完全なタグ名とカウントを付与し、ツールチップ等で確認可能にする。
2. **CSS側の対策（max-width制限）**:
   - `src/web/style.css` にて `#filter-tag-select` の `max-width` を設定（デスクトップ・スマホ共通およびスマホ個別）。
   - `@media (max-width: 768px)` にて `.form-row select` および `#filter-tag-select` が親幅（100% / calc(100vw - 32px)）を超えないようスタイルを追加。
3. **キャッシュバスター更新**:
   - `src/web/index.html` の `<link rel="stylesheet" href="style.css?v=...">` および `<script src="app.js?v=...">` のクエリパラメータを最新化。
4. **作業完了ドキュメント記録**:
   - `doc/done_gallery_tag_crop.md` に実施内容と検証結果を記録。

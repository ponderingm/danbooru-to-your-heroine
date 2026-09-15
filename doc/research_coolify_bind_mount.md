# 調査結果: Coolify環境における静的ファイル（WebUI）のバインドマウント構成比較

## 背景
- `danbooru_yukikaze_tool` の WebUI 修正時、GitHub への push および Coolify の自動デプロイを待たずに即時反映したい。
- 参考元である `yukikaze_grand_archive` の構成を調査した。

## `yukikaze_grand_archive`（Application ID: 28）の構成
Coolify の `local_persistent_volumes`（Storages設定）にて、以下のホストパスがコンテナ内へ個別バインドマウントされている：
- `/home/pi/yukikaze_grand_archive/index.html` -> `/app/index.html`
- `/home/pi/yukikaze_grand_archive/style.css` -> `/app/style.css`
- `/home/pi/yukikaze_grand_archive/app.js` -> `/app/app.js`
- `/home/pi/yukikaze_grand_archive/tag_editor.html` -> `/app/tag_editor.html`
- `/home/pi/yukikaze_grand_archive/jobs.html` -> `/app/jobs.html`
- `/home/pi/yukikaze_grand_archive/data` -> `/app/data`
- `/home/pi/yukikaze_grand_archive/logs` -> `/app/logs`
- `/mnt/external_hdd/yukikaze_generated` -> `/app/output`

これにより、ホスト側のファイルを直接書き換えるだけで、Dockerコンテナ内のファイルも即座に更新され、WebUIの配信内容にリアルタイム反映される仕組みとなっていた。

## `danbooru_yukikaze_tool`（Application ID: 27）の現状
現在のバインドマウント設定：
- `/home/pi/danbooru_yukikaze_tool/database` -> `/app/database`
- `/home/pi/danbooru_yukikaze_tool/src/config.yaml` -> `/app/src/config.yaml`
- `/mnt/external_hdd/yukikaze_generated` -> `/mnt/external_hdd/yukikaze_generated`
※ `src/web` 配下の静的ファイルはマウントされておらず、Dockerイメージビルド時のスナップショットが配信されていた。

## 解決策
CoolifyのStorages（永続化ボリューム）設定に以下を追加することで、`yukikaze_grand_archive` と同様にホスト側ファイルの即時反映が可能となる：
- **Host Path**: `/home/pi/danbooru_yukikaze_tool/src/web`
- **Mount Path**: `/app/src/web`
（または `index.html`, `style.css`, `app.js` を個別指定）
ディレクトリごと `/app/src/web` をバインドマウントすれば、新規ファイル追加時にも再設定不要となる。

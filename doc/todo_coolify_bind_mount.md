# TODO: Coolifyにおける WebUI 静的ファイルのバインドマウント設定

## 目的
`danbooru-to-your-heroine`（Application ID: 27）において、ホスト側の `src/web` 配下の変更が GitHub への push や Coolify のリビルドを待たずに即時反映されるよう、`local_persistent_volumes`（Storages）にバインドマウントを追加し、コンテナを再起動する。

## 手順
1. Coolify の `local_persistent_volumes` テーブルの既存レコード定義と制約を確認。
2. Application 27 用にマウントレコードを作成・挿入：
   - name: `n7ego2hxamt39iv9bt44gdtg-danbooru-web`
   - mount_path: `/app/src/web`
   - host_path: `/home/pi/danbooru_yukikaze_tool/src/web`
   - resource_id: `27`
   - resource_type: `App\Models\Application`
3. Coolify からアプリケーションの再デプロイ / 再起動を実施。
4. コンテナ内のマウント状態（`docker inspect`）を確認し、ホスト側の変更がリアルタイムに反映されるかを検証。
5. 作業完了ドキュメント `doc/done_coolify_bind_mount.md` を作成。

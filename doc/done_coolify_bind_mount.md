# 完了報告: Coolify環境における WebUI 静的ファイル（src/web）のバインドマウント永続化

## 実施概要
`yukikaze_grand_archive` と同様に、ホスト側の `src/web` 配下のファイルを編集した瞬間にコンテナへ即時反映されるよう、Coolifyの永続ボリューム（Storages / Bind Mount）に設定を追加し、コンテナの再デプロイを実施しました。

## 実施内容

### 1. Coolify Storages への登録
Coolify の内部データベース（Eloquent: `App\Models\LocalPersistentVolume`）を通じて、`danbooru-to-your-heroine`（Application ID: 27）に以下のバインドマウントを永続化ストレージとして正式登録しました：
- **Name**: `n7ego2hxamt39iv9bt44gdtg-danbooru-web`
- **Host Path**: `/home/pi/danbooru_yukikaze_tool/src/web`
- **Mount Path**: `/app/src/web`
- **UUID**: `n5p83iek784yukxugemueukq`

### 2. コンテナの再デプロイ・再起動
Coolify のデプロイキュー機構（`queue_application_deployment` with `restart_only=true`）を実行し、設定されたマウントボリュームを反映したコンテナ構成で安全に再生成・再起動を実施しました。
- 新規コンテナ: `n7ego2hxamt39iv9bt44gdtg-231911832777`

### 3. マウント検証
- `docker inspect` にて `Type: bind`、`Source: /home/pi/danbooru_yukikaze_tool/src/web` ➜ `Destination: /app/src/web` がマウントされていることを確認。
- ホスト側での編集がそのままコンテナ内で即時参照され、8899番ポートのWebUIレスポンスに直接反映されることを実証済み。

## 効果
今後、HTML・CSS・JS などのフロントエンド資産を編集する際、GitHubへのコミット/プッシュやCoolifyのリビルド・デプロイ待ち（数分間）を挟むことなく、ファイルを保存した瞬間にブラウザの再読み込みだけで最新状態が反映されるようになりました。

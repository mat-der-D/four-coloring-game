# 配置（Cloudflare Workers の静的アセット）

サーバー側の処理は持たない。`npm run build` で作った `dist/` の静的ファイルを、Cloudflare Workers の静的アセットとして配る。設定は `wrangler.jsonc`。

| | Worker 名 | URL | 配置のしかた |
|---|---|---|---|
| 本番 | `four-coloring-game` | https://four-coloring.smooth-pudding.net/ | GitHub の main に push すると、Cloudflare（Workers Builds）が自動で配置する |
| 開発用 | `four-coloring-game-dev` | https://four-coloring-game-dev.smooth-pudding-1017.workers.dev/ | 手元で `npm run deploy:dev`（要 `npx wrangler login`） |

- 共有の文面に入れる URL は、どちらの環境でも本番の URL（`src/share.js` の `SHARE_URL`）
- 地図のデータ（`public/maps/`、`public/thumbs/`、`src/data/stages.json`）はリポジトリに入れてある。配置のときに地図の加工（`scripts/build_maps.py`、13 分ほどかかり、元データも要る）は走らない。地図を作り直したら、生成物ごとコミットする

## 本番の初回設定（Cloudflare の画面で、人間が行う）

前提: `smooth-pudding.net` の DNS を、同じ Cloudflare アカウントで管理していること（`wrangler.jsonc` の `routes` で、`four-coloring.smooth-pudding.net` を Worker のカスタムドメインにする。DNS のレコードと証明書は Cloudflare が自動で作る）。

1. Cloudflare のダッシュボード → **Workers & Pages** → **Create** → **Import a repository**
2. GitHub と連携し、リポジトリ `mat-der-D/four-coloring-game` を選ぶ
3. 設定
   - **Project name**: `four-coloring-game`（`wrangler.jsonc` の `name` と同じにする。違うと配置で失敗する）
   - **Build command**: `npm run build`
   - **Deploy command**: `npx wrangler deploy`
   - **Production branch**: `main`
   - Node のバージョンは、リポジトリの `.node-version`（22）が使われる
4. **Deploy** を押す。初回の配置が終わると、`four-coloring.smooth-pudding.net` で開ける

以後は main に push するたびに自動で配置される。main 以外のブランチの push で、確認用の URL（プレビュー）を作る設定もある（Settings → Builds → Non-production branch builds）。

## 鍵の扱い

- 本番は GitHub 連携で配置するので、手元に Cloudflare の鍵は要らない
- 開発用の配置に使う `wrangler login` は、この PC にアカウント全体を操作できる広い権限の鍵を置く。使い終わったら `npx wrangler logout` で消せる。権限を絞りたいときは、「Workers Scripts: Edit」だけの API トークンを作り、環境変数 `CLOUDFLARE_API_TOKEN` で渡す

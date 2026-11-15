# 配置

サーバー側の処理は持たない。`npm run build` で作った `dist/` の静的ファイルを Cloudflare で配る。

| | 仕組み | URL | 配置のしかた |
|---|---|---|---|
| 本番 | Cloudflare Pages（プロジェクト `four-coloring-game`） | https://four-coloring.smooth-pudding.net/ | GitHub の main に push すると、Pages が自動でビルドして配置する |
| 開発用 | Cloudflare Workers の静的アセット（Worker `four-coloring-game-dev`、設定は `wrangler.jsonc`） | https://four-coloring-game-dev.smooth-pudding-1017.workers.dev/ | 手元で `npm run deploy:dev`（要 `npx wrangler login`） |

- 共有の文面に入れる URL は、どちらの環境でも本番の URL（`src/share.js` の `SHARE_URL`）
- 地図のデータ（`public/maps/`、`public/thumbs/`、`src/data/stages.json`）はリポジトリに入れてある。配置のときに地図の加工（`scripts/build_maps.py`、元データが必要）は走らない。地図を作り直したら、生成物ごとコミットする

## 本番が Pages である理由

`smooth-pudding.net` の DNS は XServer で管理していて、同じドメインで VPS のサービスが動いている。Workers のカスタムドメインは、ドメインの DNS を Cloudflare で管理していることが前提で、使えなかった（2026-11-15、`wrangler deploy` が「ゾーンを推定できない」で失敗）。Pages はサブドメインなら、外部の DNS に CNAME を 1 行足すだけでつなげる（[Cloudflare Pages: Custom domains](https://developers.cloudflare.com/pages/platform/custom-domains/)）。既存のサービスの DNS に触らずに済むので、Pages にした（人間の判断）。

## 本番の初回設定（Cloudflare と XServer の画面で、人間が行う）

1. Cloudflare のダッシュボード → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → リポジトリ `mat-der-D/four-coloring-game`
   - Project name: `four-coloring-game`
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Production branch: `main`
   - 手元から上げる方式（Direct Upload）で作ると、あとから GitHub 連携に切り替えられない。最初から Git につないで作る
   - Node のバージョンは、リポジトリの `.node-version`（22）が使われる
2. 初回の配置が終わったら、プロジェクトの **Custom domains** に `four-coloring.smooth-pudding.net` を追加する。**DNS より先にこちらを登録する**（逆だと名前が引けない）
3. XServer の DNS 設定で CNAME を追加する: ホスト名 `four-coloring`、内容 `four-coloring-game.pages.dev`。ホスト名の欄はドメインが自動で付くので、`four-coloring` だけを入れる
4. Cloudflare の画面に戻り、**Check DNS** で確認する

以後は main に push するたびに本番へ配置される。main 以外のブランチへの push では、確認用の URL（プレビュー）が作られる。

## 鍵の扱い

- 本番は GitHub 連携で配置するので、手元に Cloudflare の鍵はいらない
- 開発用の配置に使う `wrangler login` は、この PC にアカウント全体を操作できる広い権限の鍵を置く。使い終わったら `npx wrangler logout` で消せる。権限を絞りたいときは、「Workers Scripts: Edit」だけの API トークンを作り、環境変数 `CLOUDFLARE_API_TOKEN` で渡す

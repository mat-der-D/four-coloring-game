# 四色ぬりわけ

隣どうしが同じ色にならないよう、日本の地図を 4 色でなるべく早く塗り分けるハイパーカジュアルゲーム。

- 本番: https://four-coloring.smooth-pudding.net/
- 仕様書: https://claude.ai/artifact/5LsjGgoao8uW32vUDHdvr4（要点と決定事項は `docs/SPEC.md`）

## 動かし方

```sh
npm install
npm run dev        # http://localhost:5173/
npm run build      # dist/ に静的ファイルを出力
npm run preview    # dist/ を確認
npm run deploy:dev # 開発用の環境に配置（docs/DEPLOY.md）
```

スマホの実機で試すときは、開発用の環境に配置して開く。端末の共有機能は HTTPS のページでしか動かないので、`npm run dev -- --host` の `http://192.168.…` では試せない。

## 構成

| パス | 内容 |
|---|---|
| `index.html` | 画面の骨組み（選択・県の一覧・ゲーム・クリア・共有シート） |
| `src/main.js` | 選択画面とゲーム本体 |
| `src/render.js` | 地図の描画で共通に使うもの（4 色、模様、地図の SVG） |
| `src/share.js` | 共有画像、共有の文面、SNS の投稿画面 |
| `src/style.css` | 見た目（地図帳の紙面） |
| `src/data/stages.json` | ステージの一覧と、選択画面の小さな地図（生成物） |
| `public/maps/` | ステージごとの地図（生成物） |
| `public/thumbs/` | 県ごとの小さな地図（生成物） |
| `scripts/build_maps.py` | 地図の加工。国土数値情報から上の 3 つを作る |
| `scripts/areas.py` | 県を分けるときの地域区分（出典つき） |
| `docs/` | 仕様の要点（SPEC）、地図データ（DATA）、配置（DEPLOY） |

## 地図データを作り直す

```sh
uv sync
uv run python scripts/build_maps.py   # 初回は 15 分ほど。2 回目以降はキャッシュが効く
```

元データ（国土数値情報 行政区域）の取得と利用条件は `docs/DATA.md`。元データとキャッシュは `data-raw/`（git 管理外）に置く。

## 出典

国土交通省 国土数値情報（行政区域データ）をもとに加工して作成。SNS のロゴは [Simple Icons](https://simpleicons.org/)（CC0）。

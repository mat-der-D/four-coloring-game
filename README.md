# 四色ぬりわけ

隣どうしが同じ色にならないよう、日本の地図を 4 色でなるべく早く塗り分けるハイパーカジュアルゲーム。

- 仕様書: https://claude.ai/artifact/5LsjGgoao8uW32vUDHdvr4
- 試作品: https://claude.ai/artifact/Dr5uTxMQLgtnghh4PFfCdj

## 動かし方

```sh
npm install
npm run dev      # http://localhost:5173/
npm run build    # dist/ に静的ファイルを出力
npm run preview  # dist/ を確認
```

スマホの実機で試すときは `npm run dev -- --host` で起動し、同じネットワークから表示する。

## 構成

| パス | 内容 |
|---|---|
| `index.html` | 画面の骨組み（選択・ゲーム・共有） |
| `src/main.js` | ゲーム本体（試作品から移したもの） |
| `src/style.css` | スタイル |
| `src/data/dummy-maps.json` | ダミーの地図データ（試作品のランダム生成） |
| `docs/SPEC.md` | 仕様の要点と、次の段階 |

現状は試作品をそのまま移した段階で、地図はダミーである。実データへの置き換えは `docs/SPEC.md` を参照。

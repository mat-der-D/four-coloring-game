# CLAUDE.md（four-coloring-game）

四色ぬりわけ。概要・動かし方は `README.md`、仕様の要点と決定事項は `docs/SPEC.md`、配置は `docs/DEPLOY.md`。正本の仕様書は README にある。

## 運用の権限（人間の許可、2026-11-15）
- **このリポジトリに限り**、Claude の判断で main へ直接 commit・push してよい。PR やマージの承認待ちは不要
- 範囲はこのリポジトリだけ。他のリポジトリ、外部サービスへの公開（Cloudflare の設定変更など）、force push、履歴の書き換えには及ばない
- CLAUDE.md も自由に編集してよい
- **注意**: 本番は Cloudflare Pages の GitHub 連携（docs/DEPLOY.md）。連携すると main への push がそのまま本番への公開になり、上の 2 つの決まりがぶつかる。連携後に main へ push してよいかは、人間の決定を待つ（2026-11-15 時点で未決）。決まるまでは、main 以外のブランチに push して、プレビューの URL で確かめる
- 開発用の環境（`four-coloring-game-dev`）への配置は、人間の依頼で行ってきた（`npm run deploy:dev`）

## 開発
- 静的 Web アプリ（Vite + バニラ JS）。`npm run dev` で起動、`npm run build` で `dist/`
- 画面の動作確認は headless Chrome（puppeteer-core）で実際に操作して確かめる。開発時だけ、`#m番号` でステージを直接開ける。`window.__tap(k)` で地域のタップを呼べる（どちらも本番のビルドには入らない）
- 地図の生成物（`public/maps/`、`public/thumbs/`、`src/data/stages.json`）はコミットする。配置のときに地図の加工は走らない
- Python が要る作業（地図データの加工）は uv を使う。`pip install` はしない
- 外部サーバーからのデータ取得は、`~/CLAUDE.md` の規則に従う（robots.txt 確認、直列・3 秒以上の間隔、申告と許可）
- 元データは `data-raw/`（git 管理外）に置き、消さない

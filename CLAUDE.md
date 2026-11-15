# CLAUDE.md（four-coloring-game）

四色ぬりわけ。概要・動かし方は `README.md`、仕様の要点は `docs/SPEC.md`、正本は README にある仕様書。

## 運用の権限（人間の許可、2026-11-15）
- **このリポジトリに限り**、Claude の判断で main へ直接 commit・push してよい。PR やマージの承認待ちは不要
- 範囲はこのリポジトリだけ。他のリポジトリ、外部サービスへの公開（Cloudflare の設定変更など）、force push、履歴の書き換えには及ばない
- CLAUDE.md も自由に編集してよい

## 開発
- 静的 Web アプリ（Vite + バニラ JS）。`npm run dev` で起動、`npm run build` で `dist/`
- Python が要る作業（地図データの加工）は uv を使う。`pip install` はしない
- 外部サーバーからのデータ取得は、`~/CLAUDE.md` の規則に従う（robots.txt 確認、直列・3 秒以上の間隔、申告と許可）
- 元データは `data-raw/`（git 管理外）に置き、消さない

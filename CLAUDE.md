# CLAUDE.md（four-coloring-game）

四色ぬりわけ。概要・動かし方は `README.md`、仕様の要点と決定事項は `docs/SPEC.md`、配置は `docs/DEPLOY.md`。正本の仕様書は README にある。

## 運用の権限（人間の許可、2026-11-15）
- **このリポジトリに限り**、Claude の判断で main へ直接 commit・push してよい。PR やマージの承認待ちは不要
- 範囲はこのリポジトリだけ。他のリポジトリ、外部サービスへの公開（Cloudflare の設定変更など）、force push、履歴の書き換えには及ばない
- CLAUDE.md も自由に編集してよい
- **main への push は本番への公開**（Cloudflare Pages の GitHub 連携、docs/DEPLOY.md）。それでも main への push は Claude の判断でしてよい（人間の許可、2026-11-15）。push のたびに本番の配置が走ることを勘案し、確かめてから push する。確かめが必要な変更は、別のブランチに push してプレビューの URL（`https://〈ブランチ名〉.four-coloring-game.pages.dev/`）で見てから main に入れる
- **Pages の無料プランはビルドが月 500 回まで**（main もほかのブランチも、push 1 回で 1 回）。無駄なビルドを減らす: 文書だけ（`docs/`、`*.md`、`scripts/` だけ）のコミットはメッセージに `[CI Skip]` を付ける。小さな修正はまとめてから push する。サブエージェントにブランチを push させるときも回数を意識させる
- 県のサイトなど外部への取得は、相手の robots.txt と利用条件で許されている範囲なら行ってよい（人間の許可、2026-11-15）。**同じサイトへは直列・3 秒以上の間隔**を守る。**別々のサイトへは並行してよい**（人間の許可、同日）。決まりの目的は「相手のサイトに負荷をかけないこと」で、間隔や直列はサイトごとに考える
- 時間のかかる作業（地図の加工、調査など）はサブエージェントに任せ、人間と話せる状態を保つ（人間の指示、2026-11-15）
- 開発用の環境（`four-coloring-game-dev`）への配置は、人間の依頼で行ってきた（`npm run deploy:dev`）

## 開発
- 静的 Web アプリ（Vite + バニラ JS）。`npm run dev` で起動、`npm run build` で `dist/`
- 画面の動作確認は headless Chrome（puppeteer-core）で実際に操作して確かめる。開発時だけ、`#m番号` でステージを直接開ける。`window.__tap(k)` で地域のタップを呼べる（どちらも本番のビルドには入らない）
- 地図の生成物（`public/maps/`、`public/thumbs/`、`src/data/stages.json`）はコミットする。配置のときに地図の加工は走らない
- Python が必要な作業（地図データの加工）は uv を使う。`pip install` はしない
- 外部サーバーからのデータ取得は、`~/CLAUDE.md` の規則に従う（robots.txt 確認、直列・3 秒以上の間隔、申告と許可）
- 元データは `data-raw/`（git 管理外）に置き、消さない

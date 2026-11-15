// 共有: 共有画像（地図・ステージ名・タイムだけ）、共有の文面、SNS の投稿画面
import { COLORS, INK, SUB, parts, mapSVG, unitsPerPx } from "./render.js";

const MINCHO = `"BIZ UDPMincho", "Hiragino Mincho ProN", serif`;
const GOTHIC = `"BIZ UDPGothic", "Hiragino Sans", sans-serif`;

// 文字が幅に収まるまで小さくする
function fit(g, text, weight, family, size, maxW) {
  let s = size;
  for (;;) {
    g.font = `${weight} ${s}px ${family}`;
    if (g.measureText(text).width <= maxW || s <= size * 0.45) return s;
    s *= 0.94;
  }
}

/**
 * 共有画像を描いたキャンバスを返す。見た目はクリア画面の板（二重の枠と方眼）と同じ。
 * 縦長・正方形は「名前 → 地図 → タイム」を縦に、横長は「地図 ｜ 名前とタイム」を横に並べる。
 */
export async function drawShareImage(stage, fills, time, { width = 1080, height = 1350 } = {}) {
  const W = width, H = height;
  const R = Math.min(W, H) / 450; // 画面の 1px（クリア画面の大きさ）が画像の何 px か
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const g = cv.getContext("2d");
  await Promise.all([document.fonts.load(`700 40px "BIZ UDPMincho"`), document.fonts.load(`700 40px "BIZ UDPGothic"`)]).catch(() => {});

  // 紙・二重の枠・方眼
  g.fillStyle = "#F4F7F8"; g.fillRect(0, 0, W, H);
  const o = Math.round(Math.min(W, H) * 0.037), i2 = o + 5 * R;
  g.fillStyle = "#fff"; g.fillRect(o, o, W - 2 * o, H - 2 * o);
  g.strokeStyle = INK; g.lineWidth = 1.5 * R; g.strokeRect(o, o, W - 2 * o, H - 2 * o);
  g.save(); g.beginPath(); g.rect(i2, i2, W - 2 * i2, H - 2 * i2); g.clip();
  g.strokeStyle = "#DCE6EB"; g.lineWidth = R;
  for (let x = i2; x < W; x += 30 * R) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
  for (let y = i2; y < H; y += 30 * R) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  g.restore();
  g.strokeStyle = INK; g.lineWidth = R; g.strokeRect(i2, i2, W - 2 * i2, H - 2 * i2);

  const [pre, nm] = parts(stage);
  const pad = 16 * R;
  const landscape = W / H > 1.2;
  // 文字の列: 横長なら右側、それ以外は全幅
  const colW = landscape ? (W - 2 * i2) * 0.36 : W - 2 * i2 - 2 * pad;
  const colX = landscape ? W - i2 - pad - colW : i2 + pad;

  // ステージ名
  g.textBaseline = "top"; g.textAlign = "left";
  let y = i2 + pad;
  if (pre) {
    g.fillStyle = SUB; fit(g, pre, 400, MINCHO, 15 * R, colW);
    g.fillText(pre, colX, y); y += 20 * R;
  }
  g.fillStyle = INK; const ns = fit(g, nm, 700, MINCHO, 30 * R, colW);
  g.fillText(nm, colX, y); y += ns * 1.25;

  // タイムとロゴ
  const logo = (right, bottom) => {
    g.textBaseline = "alphabetic"; g.textAlign = "right"; g.fillStyle = INK;
    g.font = `400 ${13 * R}px ${MINCHO}`;
    g.fillText("四色ぬりわけ", right, bottom);
    const lw = g.measureText("四色ぬりわけ").width;
    COLORS.forEach((c, k) => { g.fillStyle = c; g.fillRect(right - lw - 30 * R + (k % 2) * 13 * R, bottom - 24 * R + Math.floor(k / 2) * 13 * R, 11 * R, 11 * R); });
    g.textAlign = "left";
  };
  const timeBlock = (x, base, maxW) => {
    g.textBaseline = "alphabetic"; g.fillStyle = SUB;
    g.font = `400 ${13 * R}px ${GOTHIC}`;
    g.fillText("タイム", x, base - 2 * R);
    const tw = g.measureText("タイム").width + 8 * R;
    g.fillStyle = INK; fit(g, time, 700, GOTHIC, 46 * R, maxW - tw);
    g.fillText(time, x + tw, base);
  };

  let mapRect;
  if (landscape) {
    // 右の列: 名前の下に区切り線とタイム、いちばん下にロゴ
    const ly = y + 6 * R;
    g.strokeStyle = INK; g.lineWidth = R; g.beginPath(); g.moveTo(colX, ly); g.lineTo(colX + colW, ly); g.stroke();
    timeBlock(colX, ly + 60 * R, colW);
    logo(colX + colW, H - i2 - pad);
    // 列の左に縦の区切り線
    g.beginPath(); g.moveTo(colX - pad, i2); g.lineTo(colX - pad, H - i2); g.stroke();
    mapRect = [i2 + pad, i2 + pad, colX - 2 * pad - (i2 + pad), H - 2 * (i2 + pad)];
  } else {
    const fy = H - i2 - 70 * R;
    g.strokeStyle = INK; g.lineWidth = R; g.beginPath(); g.moveTo(colX, fy); g.lineTo(colX + colW, fy); g.stroke();
    timeBlock(colX, H - i2 - 14 * R, colW * 0.62);
    logo(colX + colW, H - i2 - 16 * R);
    mapRect = [colX, y + 10 * R, colW, fy - 10 * R - (y + 10 * R)];
  }

  // 地図（模様はクリア画面と同じ細かさにする）
  const [mx, my, mw, mh] = mapRect.map(Math.round);
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(mapSVG(stage, fills, { id: "sp", u: unitsPerPx(stage.box, mw, mh) * R, attrs: `width="${mw}" height="${mh}"` }));
  await img.decode();
  g.drawImage(img, mx, my, mw, mh);
  return cv;
}

export const toBlob = (cv) => new Promise((res) => cv.toBlob(res, "image/png"));

// ---------- 共有の文面 ----------
export const stageTitle = (stage) => parts(stage).filter(Boolean).join(" ");

// 文面の候補（モックで比べるため複数持つ。決まったら 1 つにする）
export const TEXTS = {
  short: ({ title, time }) => `${title}を ${time} で塗り分けた！\n#四色ぬりわけ`,
  record: ({ title, time, n }) => `【四色ぬりわけ】${title}（${n} 地域）を ${time}`,
  explain: ({ title, time, n }) => `${title}の ${n} 地域を、隣どうし違う色に塗り分けました。タイムは ${time}。\n#四色ぬりわけ`,
};

// ---------- SNS の投稿画面 ----------
// どれも渡せるのは文面と URL だけ（画像は渡せない）。画像付きで投稿するには、端末の共有か、画像の保存・コピーが要る
export const SNS = [
  { id: "x", label: "X", href: (text, url) => `https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}` },
  { id: "line", label: "LINE", href: (text, url) => `https://line.me/R/share?text=${encodeURIComponent(text + "\n" + url)}` },
  { id: "threads", label: "Threads", href: (text, url) => `https://www.threads.net/intent/post?text=${encodeURIComponent(text + "\n" + url)}` },
  { id: "bluesky", label: "Bluesky", href: (text, url) => `https://bsky.app/intent/compose?text=${encodeURIComponent(text + "\n" + url)}` },
  { id: "facebook", label: "Facebook", href: (_text, url) => `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}` },
];

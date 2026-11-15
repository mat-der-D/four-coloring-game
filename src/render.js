// 地図の描画で、ゲーム画面・クリア画面・共有画像が共通に使うもの

export const COLORS = ["#F4D35E", "#7EC4EA", "#EE8B3A", "#2F8F7A"]; // 黄・水色・橙・緑。赤は「同じ色の隣りあい」専用
export const BLANK = "#E7E3D7";
export const INK = "#1E2B38";
export const SUB = "#5C6B78";
export const CONF = "#D7263D";

// 「愛知県 名古屋市」-> ["愛知県", "名古屋市"]。県全体（「愛知県」）は「愛知県全体」と出す
export function parts(s) {
  const i = s.name.indexOf(" ");
  if (i > 0) return [s.name.slice(0, i), s.name.slice(i + 1)];
  if (s.isWhole) return ["", `${s.name}全体`];
  return ["", s.name];
}

// 塗りの模様。色だけに頼らないための目印（黄: なし／水色: 点／橙: 斜線／緑: 格子）。
// u は「画面の 1px が地図の何単位か」。拡大しても、画面上の模様の細かさを保つ
export function patternDefs(id, u) {
  const sz = (v) => (v * u).toFixed(4);
  const ink = "rgba(30,43,56,.24)", wh = "rgba(255,255,255,.36)";
  return `<pattern id="${id}0" patternUnits="userSpaceOnUse" width="${sz(8)}" height="${sz(8)}"><rect width="${sz(8)}" height="${sz(8)}" fill="${COLORS[0]}"/></pattern>` +
    `<pattern id="${id}1" patternUnits="userSpaceOnUse" width="${sz(7)}" height="${sz(7)}"><rect width="${sz(7)}" height="${sz(7)}" fill="${COLORS[1]}"/><circle cx="${sz(3.5)}" cy="${sz(3.5)}" r="${sz(1.15)}" fill="${ink}"/></pattern>` +
    `<pattern id="${id}2" patternUnits="userSpaceOnUse" width="${sz(6)}" height="${sz(6)}" patternTransform="rotate(45)"><rect width="${sz(6)}" height="${sz(6)}" fill="${COLORS[2]}"/><rect width="${sz(1.3)}" height="${sz(6)}" fill="${ink}"/></pattern>` +
    `<pattern id="${id}3" patternUnits="userSpaceOnUse" width="${sz(8)}" height="${sz(8)}"><rect width="${sz(8)}" height="${sz(8)}" fill="${COLORS[3]}"/><path d="M0 0H${sz(8)}M0 0V${sz(8)}" stroke="${wh}" stroke-width="${sz(1.4)}"/></pattern>`;
}

// 塗り終えた地図の SVG（クリア画面と共有画像で使う）。u は「画面の 1px が地図の何単位か」
export function mapSVG(m, fills, { id = "cp", u = 1, line = 1.2, attrs = "" } = {}) {
  const [x, y, w, h] = m.box, px = w * 0.03, py = h * 0.03;
  let s = `<svg xmlns="http://www.w3.org/2000/svg" ${attrs} viewBox="${x - px} ${y - py} ${w + 2 * px} ${h + 2 * py}" preserveAspectRatio="xMidYMid meet">` +
    `<defs>${patternDefs(id, u)}</defs>`;
  m.regions.forEach((r, i) => (s += `<path d="${r.d}" fill="url(#${id}${fills[i]})" stroke="${COLORS[fills[i]]}" stroke-width="${0.6 * u}"/>`));
  return s + `<path d="${m.border}" fill="none" stroke="${INK}" stroke-width="${line * u}" stroke-linejoin="round"/></svg>`;
}

// 表示する枠（width × height px）に box を収めたとき、1px が地図の何単位か
export const unitsPerPx = (box, width, height) => Math.max((box[2] * 1.06) / (width || 300), (box[3] * 1.06) / (height || 300));

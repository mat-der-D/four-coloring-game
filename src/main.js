import "./style.css";
// 一覧（地方 -> 都道府県 -> ステージ）。地図そのものはステージを選んだときに public/maps/ から読む
import DATA from "./data/stages.json";
import { COLORS, BLANK, INK, CONF, parts, patternDefs, mapSVG, unitsPerPx } from "./render.js";
import { drawShareImage, toBlob, stageTitle, TEXTS } from "./share.js";

const $ = (id) => document.getElementById(id);
const BASE = import.meta.env.BASE_URL;
const fmt = (ms) => { const s = ms / 1000; return Math.floor(s / 60) + ":" + (s % 60).toFixed(1).padStart(4, "0"); };
const short = (name) => (name === "北海道" ? name : name.replace(/[都府県]$/, ""));
// 地域数: 大きな数字と縮尺バー（長さは地域数の対数）
const count = (n) => `<span class="cnt"><span class="v num">${n}<small>地域</small></span>` +
  `<span class="scale" style="width:${Math.round(14 + 66 * Math.log(Math.max(n, 2)) / Math.log(200))}px"></span></span>`;
const markHTML = () => COLORS.map((c, k) => `<i class="${k ? "p" + k : ""}" style="background-color:${c}"></i>`).join("");

// ---------- サムネイル（選択画面の小さな地図。解が見えないよう、塗らずに輪郭だけ） ----------
// t: {vb, land, lines}。hl を渡すと、その部分だけ濃く塗る（県のページで、県全体のうちどこかを示す）
function thumbSVG(t, { vb = t.vb, d: hl = null } = {}) {
  return `<svg class="th" viewBox="${vb.join(" ")}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">` +
    `<path d="${t.land}" fill="${hl ? "#EEEBE2" : BLANK}"/>` +
    (hl ? `<path d="${hl}" fill="${INK}"/>` : "") +
    `<path d="${t.lines}" fill="none" stroke="${INK}" stroke-opacity="${hl ? 0.35 : 0.8}" stroke-width="0.8" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}
const thumbCache = {};
const loadThumb = (f) => (thumbCache[f] ??= fetch(`${BASE}thumbs/${f}`).then((r) => r.json()));

// ---------- 選択画面 ----------
let selPref = null; // 県のページを開いているときはその県
function show(id) {
  for (const s of document.querySelectorAll(".screen")) s.classList.toggle("on", s.id === id);
}
function renderTop() {
  const top = $("top");
  top.innerHTML = `<div class="top-h"><h1 class="logo"><span class="mark">${markHTML()}</span>四色ぬりわけ</h1>
    <p>地域をタップして色を変え、隣りあう地域を<br>すべて違う色にすればクリア。</p></div>`;
  const hero = document.createElement("button");
  hero.className = "hero gridbg";
  hero.innerHTML = `<div class="in"><div class="nm">日本地図<span>47 都道府県</span></div>${count(DATA.zenkoku.n)}</div>${thumbSVG(DATA.zenkoku.thumb)}`;
  hero.onclick = () => start(DATA.zenkoku);
  top.appendChild(hero);
  for (const b of DATA.blocks) {
    const sec = document.createElement("section");
    sec.className = "blk";
    // 地方のステージが、その地方の入口
    const e = document.createElement("button");
    e.className = "entry";
    e.innerHTML = `${thumbSVG(b.thumb)}<span class="t">${b.stage.name}</span>${count(b.stage.n)}`;
    e.onclick = () => start(b.stage);
    sec.appendChild(e);
    const g = document.createElement("div");
    g.className = "prefs";
    for (const p of b.prefs) {
      const k = p.stages.length + (p.whole ? 1 : 0);
      const btn = document.createElement("button");
      btn.className = "pref";
      btn.innerHTML = `${short(p.name)}<small>${k} ステージ</small>`;
      btn.onclick = () => renderPref(p, b);
      g.appendChild(btn);
    }
    sec.appendChild(g);
    top.appendChild(sec);
  }
  top.insertAdjacentHTML("beforeend", `<p class="credit">出典：<a href="https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2025.html">国土交通省 国土数値情報（行政区域データ 2025年）</a>をもとに加工して作成</p>`);
}
// 県のページ: 部分のステージは、県全体の輪郭の中でその部分を濃く示す。県全体は二重の枠で分ける
async function renderPref(p, b) {
  selPref = { p, b };
  $("pref-name").textContent = p.name;
  $("pref-sub").textContent = b.name === "北海道" ? "" : `${b.name}地方`;
  const list = $("pref-list");
  list.innerHTML = "";
  show("pref");
  $("pref").querySelector(".scroll").scrollTop = 0;
  const t = await loadThumb(p.thumb);
  if (selPref?.p !== p) return; // 読み込み中に別の県へ移った
  // 分けていない県は、ステージが県全体の 1 つだけ
  const whole = p.whole || p.stages[0];
  const partStages = p.whole ? p.stages : [];
  partStages.forEach((s, i) => {
    const r = document.createElement("button");
    r.className = "st";
    r.innerHTML = `${thumbSVG(t, t.parts[i])}<span class="t">${parts(s)[1]}</span>${count(s.n)}`;
    r.onclick = () => start(s);
    list.appendChild(r);
  });
  whole.isWhole = true;
  const w = document.createElement("button");
  w.className = "whole";
  const note = partStages.length ? `上の ${partStages.length} ステージをひとつにした地図` : "県全体をひとつの地図で";
  w.innerHTML = `<div class="in gridbg"><div class="hd"><div class="t">${p.name}全体<span>${note}</span></div>${count(whole.n)}</div>${thumbSVG(t)}</div>`;
  w.onclick = () => start(whole);
  list.appendChild(w);
}
$("pref-back").onclick = () => { selPref = null; show("sel"); };
renderTop();

$("legend").insertAdjacentHTML("afterbegin", markHTML());

// 境界の折れ線の中点（同じ色の隣りあいの × 印を置く場所）
function midpoint(d) {
  const segs = [];
  let last = null;
  for (const [, c, x, y] of d.matchAll(/([ML])\s*([-\d.]+)[ ,]([-\d.]+)/g)) {
    const p = [+x, +y];
    if (c === "L" && last) segs.push([last, p]);
    last = p;
  }
  if (!segs.length) return last || [0, 0];
  const len = (s) => Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]);
  let half = segs.reduce((t, s) => t + len(s), 0) / 2;
  for (const s of segs) {
    const l = len(s);
    if (half <= l) { const t = l ? half / l : 0; return [s[0][0] + (s[1][0] - s[0][0]) * t, s[0][1] + (s[1][1] - s[0][1]) * t]; }
    half -= l;
  }
  return segs[0][0];
}

// ---------- ゲーム ----------
let S, color, adj, pairD, pairMid, conflicts, t0, timerId, done, view, lastTime;
const key = (a, b) => (a < b ? a + "-" + b : b + "-" + a);

async function start(s) {
  S = s;
  if (!S.regions) {
    const res = await fetch(`${BASE}maps/${S.file}`);
    Object.assign(S, await res.json());
  }
  color = new Array(S.n).fill(-1);
  adj = Array.from({ length: S.n }, () => []);
  pairD = new Map();
  pairMid = new Map();
  for (const [a, b, d] of S.pairs) { adj[a].push(b); adj[b].push(a); pairD.set(key(a, b), d); }
  conflicts = new Set(); t0 = null; done = false; clearInterval(timerId);
  const [pre, nm] = parts(S);
  $("g-pref").textContent = pre;
  $("title").textContent = nm;
  $("timer").textContent = "0:00.0";
  $("clear").classList.remove("on", "show");
  const g = $("regs");
  g.innerHTML = "";
  S.regions.forEach((r, k) => {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", r.d); p.setAttribute("class", "reg"); p.dataset.r = k;
    p.style.fill = BLANK; p.style.stroke = BLANK;
    g.appendChild(p);
  });
  $("border").setAttribute("d", S.border);
  show("game");
  fitView(); drawConflicts(); updateLeft();
}

function tapRegion(k) {
  if (done) return;
  if (t0 === null) { t0 = performance.now(); timerId = setInterval(() => ($("timer").textContent = fmt(performance.now() - t0)), 100); }
  color[k] = (color[k] + 1) % 4;
  const el = $("regs").children[k];
  el.style.fill = `url(#gp${color[k]})`; el.style.stroke = COLORS[color[k]];
  for (const u of adj[k]) { const kk = key(k, u); if (color[u] === color[k]) conflicts.add(kk); else conflicts.delete(kk); }
  drawConflicts(); updateLeft();
  if (!color.includes(-1)) {
    if (conflicts.size === 0) finish(k);
    else if (!$("hl").checked) toast(`同じ色の隣りあいが ${conflicts.size} か所`);
  }
}
// 同じ色の隣りあい: 白で縁取った太い赤線と、境界の中ほどに赤い丸の ×。× は画面上で同じ大きさにする
function drawConflicts() {
  const on = $("hl").checked && conflicts.size > 0;
  $("note").hidden = !on;
  $("nconf").textContent = conflicts.size;
  if (!on) { $("conf").innerHTML = ""; return; }
  const d = [...conflicts].map((k) => pairD.get(k)).join("");
  const u = 1 / (committed ? committed.k : 1);
  let s = `<path d="${d}" fill="none" stroke="#fff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` +
    `<path d="${d}" fill="none" stroke="${CONF}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
  for (const k of conflicts) {
    if (!pairMid.has(k)) pairMid.set(k, midpoint(pairD.get(k)));
    const [cx, cy] = pairMid.get(k);
    s += `<g transform="translate(${cx} ${cy}) scale(${u})"><circle r="13" fill="#fff"/><circle r="11" fill="${CONF}"/>` +
      `<path d="M-4.6 -4.6L4.6 4.6M4.6 -4.6L-4.6 4.6" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></g>`;
  }
  $("conf").innerHTML = s;
}
function updateLeft() {
  const left = color.filter((c) => c < 0).length;
  $("left").innerHTML = left ? `のこり<b class="num">${left}</b>地域` : "";
}
$("hl").onchange = drawConflicts;

let toastT;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 1600); }

function finish(lastK) {
  done = true; clearInterval(timerId);
  const ms = performance.now() - t0;
  lastTime = fmt(ms);
  $("timer").textContent = lastTime;
  fitView(true);
  // 最後にタップした地域から、波が広がるように一度だけ弾む
  const [ox, oy] = S.regions[lastK].c;
  let maxD = 1;
  S.regions.forEach((r) => (maxD = Math.max(maxD, Math.hypot(r.c[0] - ox, r.c[1] - oy))));
  [...$("regs").children].forEach((el, k) => {
    const d = Math.hypot(S.regions[k].c[0] - ox, S.regions[k].c[1] - oy);
    el.classList.remove("pop"); void el.getBBox(); el.style.animationDelay = (d / maxD) * 0.5 + "s"; el.classList.add("pop");
  });
  setTimeout(showClear, 1100);
}

// クリア画面: 共有画像と同じ見た目の板
function showClear() {
  if (!done) return;
  const [pre, nm] = parts(S);
  $("c-pref").textContent = pre;
  $("c-name").textContent = nm;
  $("c-time").textContent = lastTime;
  $("c-mark").innerHTML = markHTML();
  const cv = $("clear");
  cv.classList.add("on");
  const svg = $("c-map");
  const r = svg.getBoundingClientRect();
  svg.outerHTML = mapSVG(S, color, { u: unitsPerPx(S.box, r.width, r.height), attrs: 'id="c-map"' });
  requestAnimationFrame(() => cv.classList.add("show"));
}

// ---------- 拡大・移動・タップ ----------
// committed は SVG に描いた状態、view は今の見た目。
// 操作中は SVG 要素ごと CSS transform で動かす（描き直さないので軽い）。指を離したら描き直す
let committed = null;
function fitView(animate) {
  const st = $("stage").getBoundingClientRect();
  const [bx, by, bw, bh] = S.box;
  const k = Math.min(st.width / bw, (st.height * 0.88) / bh) * 0.94;
  view = { k, x: (st.width - bw * k) / 2 - bx * k, y: (st.height - bh * k) / 2 - by * k };
  if (animate && committed) {
    const m = $("map");
    m.style.transition = "transform .45s ease";
    applyView();
    setTimeout(() => { m.style.transition = "none"; commitView(); }, 460);
  } else commitView();
}
function applyView() {
  const c = committed, s = view.k / c.k;
  const m = $("map");
  m.style.willChange = "transform";
  m.style.transform = `translate(${view.x - s * c.x}px,${view.y - s * c.y}px) scale(${s})`;
}
function commitView() {
  committed = { ...view };
  $("vp").setAttribute("transform", `translate(${view.x} ${view.y}) scale(${view.k})`);
  $("pats").innerHTML = patternDefs("gp", 1 / view.k); // 模様と × 印は、画面上の大きさを保つ
  drawConflicts();
  const m = $("map");
  m.style.transform = ""; m.style.willChange = "";
}
let wheelT;
const pts = new Map();
let gesture = null;
const stageEl = $("stage");
$("map").addEventListener("pointerdown", (e) => {
  $("map").setPointerCapture(e.pointerId);
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY });
  if (pts.size === 1) gesture = { moved: false, base: { ...view } };
  if (pts.size === 2) {
    const [a, b] = [...pts.values()];
    gesture = { moved: true, pinch: true, d0: Math.hypot(a.x - b.x, a.y - b.y), m0: [(a.x + b.x) / 2, (a.y + b.y) / 2], base: { ...view } };
  }
});
$("map").addEventListener("pointermove", (e) => {
  const p = pts.get(e.pointerId);
  if (!p || !gesture) return;
  p.x = e.clientX; p.y = e.clientY;
  const r = stageEl.getBoundingClientRect();
  if (gesture.pinch && pts.size === 2) {
    const [a, b] = [...pts.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y), m = [(a.x + b.x) / 2, (a.y + b.y) / 2];
    const s = d / gesture.d0, B = gesture.base;
    const k = Math.max(0.3, Math.min(B.k * s, 40));
    const mx = gesture.m0[0] - r.left, my = gesture.m0[1] - r.top;
    view = { k, x: mx - (mx - B.x) * (k / B.k) + (m[0] - gesture.m0[0]), y: my - (my - B.y) * (k / B.k) + (m[1] - gesture.m0[1]) };
    applyView();
  } else if (pts.size === 1) {
    const dx = p.x - p.sx, dy = p.y - p.sy;
    if (!gesture.moved && Math.hypot(dx, dy) > 8) gesture.moved = true;
    if (gesture.moved && !done) { view = { ...gesture.base, x: gesture.base.x + dx, y: gesture.base.y + dy }; applyView(); }
  }
});
function up(e) {
  const p = pts.get(e.pointerId);
  if (!p) return;
  pts.delete(e.pointerId);
  if (gesture && !gesture.moved && pts.size === 0) {
    const t = document.elementFromPoint(e.clientX, e.clientY);
    if (t && t.dataset && t.dataset.r !== undefined) tapRegion(+t.dataset.r);
  }
  if (pts.size === 1) { const q = [...pts.values()][0]; q.sx = q.x; q.sy = q.y; gesture = { moved: true, base: { ...view } }; }
  if (pts.size === 0) { if (gesture && gesture.moved) commitView(); gesture = null; }
}
$("map").addEventListener("pointerup", up);
$("map").addEventListener("pointercancel", (e) => { pts.delete(e.pointerId); if (!pts.size) { gesture = null; commitView(); } });
$("map").addEventListener("wheel", (e) => {
  e.preventDefault();
  if (done) return;
  const r = stageEl.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const k = Math.max(0.3, Math.min(view.k * Math.exp(-e.deltaY * 0.0015), 40));
  view = { k, x: mx - (mx - view.x) * (k / view.k), y: my - (my - view.y) * (k / view.k) };
  applyView();
  clearTimeout(wheelT); wheelT = setTimeout(commitView, 150);
}, { passive: false });
window.addEventListener("resize", () => { if (S && $("game").classList.contains("on")) fitView(); });

// ---------- ボタン ----------
function backToList() {
  clearInterval(timerId);
  if (selPref) renderPref(selPref.p, selPref.b); else show("sel");
}
$("back").onclick = backToList;
$("b-list").onclick = backToList;
$("b-again").onclick = () => start(S);
$("b-share").onclick = share;

// ---------- 共有: 画像（地図・ステージ名・タイムだけ）と文面 ----------
async function share() {
  const blob = await toBlob(await drawShareImage(S, color, lastTime));
  const file = new File([blob], "nuriwake.png", { type: "image/png" });
  const text = TEXTS.short({ title: stageTitle(S), time: lastTime, n: S.n });
  const url = location.origin + BASE;
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], text, url }); return; }
  } catch (err) { if (err && err.name === "AbortError") return; }
  $("sh-img").src = URL.createObjectURL(blob);
  $("share").classList.add("on");
}
$("share").onclick = (e) => { if (e.target.id === "share" || e.target.id === "sh-close") $("share").classList.remove("on"); };

// 開発用: URL の #m番号 で地図ファイル（public/maps/番号.json）のステージを直接開く（例 #m138）
{
  const mm = location.hash.match(/^#m(\d{3})$/);
  const all = [DATA.zenkoku, ...DATA.blocks.flatMap((b) => [b.stage, ...b.prefs.flatMap((p) => [...p.stages, p.whole])])].filter(Boolean);
  const hit = mm && all.find((s) => s.file === `${mm[1]}.json`);
  if (hit) start(hit);
}

// 開発用: 動作確認のスクリプトから地域のタップを呼べるようにする（本番のビルドには入らない）
if (import.meta.env.DEV) window.__tap = (k) => tapRegion(k);

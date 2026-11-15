import "./style.css";
import DATA from "./data/dummy-maps.json";
const STAGES = [];
const COLORS = ["#F2C14E","#7BC47F","#5E9BE0","#EA8DB2"];
const BLANK = "#ece8de";
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";

// ---------- select screen ----------
function addSection(tag, title, note) {
  const h = document.createElement("div"); h.className = "sec";
  h.innerHTML = `<span class="tag">${tag}</span>${title}${note ? `<small>${note}</small>` : ""}`;
  $("list").appendChild(h);
}
function addStage(s, label, parent) {
  const i = STAGES.push(s) - 1;
  const b = document.createElement("button");
  b.className = "stage";
  b.innerHTML = `<span>${label || s.name}</span><span class="n">${s.n}</span>`;
  b.onclick = () => start(i);
  (parent || $("list")).appendChild(b);
}
addSection("入門", "地方");
DATA.chiho.forEach((s) => addStage(s));
addSection("本編", "地域");
DATA.chiiki.forEach(({ pref, stages }) => {
  if (stages.length === 1) { addStage(stages[0]); return; }
  const grp = document.createElement("div"); grp.className = "grp";
  grp.innerHTML = `<div class="gname">${pref}</div>`;
  stages.forEach((s) => addStage(s, s.name.replace(pref + " ", ""), grp));
  const whole = DATA.ken.find((k) => k.name === pref);
  if (whole) addStage(whole, `まるごと <span class="adv">上級</span>`, grp);
  $("list").appendChild(grp);
});
addSection("全国", "47都道府県");
addStage(DATA.zenkoku, "日本地図（ダミー）");

// ---------- game state ----------
let S, color, adj, pairD, conflicts, t0, timerId, done, view;
function start(i) {
  S = STAGES[i];
  color = new Array(S.n).fill(-1);
  adj = Array.from({ length: S.n }, () => []);
  pairD = new Map();
  for (const [a, b, d] of S.pairs) { adj[a].push(b); adj[b].push(a); pairD.set(key(a, b), d); }
  conflicts = new Set(); t0 = null; done = false; clearInterval(timerId);
  $("title").textContent = S.name;
  $("timer").textContent = "0:00.0";
  $("clear").classList.remove("on");
  const g = $("regs"); g.innerHTML = "";
  S.regions.forEach((r, k) => {
    const p = document.createElementNS(SVGNS, "path");
    p.setAttribute("d", r.d); p.setAttribute("class", "reg"); p.dataset.r = k;
    p.style.fill = BLANK; p.style.stroke = BLANK;
    g.appendChild(p);
  });
  $("border").setAttribute("d", S.border);
  $("conf").setAttribute("d", "");
  $("sel").classList.remove("on"); $("game").classList.add("on");
  fitView(); updateLeft();
}
const key = (a, b) => (a < b ? a + "-" + b : b + "-" + a);
function fmt(ms) { const s = ms / 1000; return Math.floor(s / 60) + ":" + (s % 60).toFixed(1).padStart(4, "0"); }

function tapRegion(k) {
  if (done) return;
  if (t0 === null) { t0 = performance.now(); timerId = setInterval(() => $("timer").textContent = fmt(performance.now() - t0), 100); }
  color[k] = (color[k] + 1) % 4;
  const el = $("regs").children[k];
  el.style.fill = COLORS[color[k]]; el.style.stroke = COLORS[color[k]];
  for (const u of adj[k]) { const kk = key(k, u); if (color[u] === color[k]) conflicts.add(kk); else conflicts.delete(kk); }
  drawConflicts(); updateLeft();
  if (!color.includes(-1)) {
    if (conflicts.size === 0) finish(k);
    else if (!$("hl").checked) toast(`同じ色の隣りあいが ${conflicts.size} か所`);
  }
}
function drawConflicts() { $("conf").setAttribute("d", $("hl").checked ? [...conflicts].map((k) => pairD.get(k)).join("") : ""); }
function updateLeft() { const left = color.filter((c) => c < 0).length; $("left").textContent = left ? `のこり ${left}` : ""; }
$("hl").onchange = drawConflicts;

let toastT;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 1600); }

function finish(lastK) {
  done = true; clearInterval(timerId);
  const ms = performance.now() - t0; $("timer").textContent = fmt(ms);
  fitView(true);
  const [ox, oy] = S.regions[lastK].c;
  let maxD = 1; S.regions.forEach((r) => maxD = Math.max(maxD, Math.hypot(r.c[0] - ox, r.c[1] - oy)));
  [...$("regs").children].forEach((el, k) => {
    const d = Math.hypot(S.regions[k].c[0] - ox, S.regions[k].c[1] - oy);
    el.classList.remove("pop"); void el.getBBox(); el.style.animationDelay = (d / maxD * 0.5) + "s"; el.classList.add("pop");
  });
  $("badge").querySelector(".nm").textContent = S.name;
  $("badge").querySelector(".tm").textContent = fmt(ms);
  $("clear").classList.add("on");
  lastTime = fmt(ms);
}
let lastTime = "";

// ---------- pan / zoom / tap ----------
function fitView(animate) {
  const st = $("stage").getBoundingClientRect();
  const [bx, by, bw, bh] = S.box;
  const padTop = 0.12;
  const k = Math.min(st.width / bw, st.height * (1 - padTop * 2) / bh) * 0.94;
  view = { k, x: (st.width - bw * k) / 2 - bx * k, y: (st.height - bh * k) / 2 - by * k };
  applyView(animate);
}
function applyView(animate) {
  const vp = $("vp");
  vp.style.transition = animate ? "transform .45s ease" : "none";
  vp.style.transform = `translate(${view.x}px,${view.y}px) scale(${view.k})`;
}
const pts = new Map(); let gesture = null;
const stageEl = $("stage");
$("map").addEventListener("pointerdown", (e) => {
  $("map").setPointerCapture(e.pointerId);
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, target: e.target });
  if (pts.size === 1) gesture = { moved: false, base: { ...view } };
  if (pts.size === 2) { const [a, b] = [...pts.values()]; gesture = { moved: true, pinch: true, d0: Math.hypot(a.x - b.x, a.y - b.y), m0: [(a.x + b.x) / 2, (a.y + b.y) / 2], base: { ...view } }; }
});
$("map").addEventListener("pointermove", (e) => {
  const p = pts.get(e.pointerId); if (!p || !gesture) return;
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
  const p = pts.get(e.pointerId); if (!p) return;
  pts.delete(e.pointerId);
  if (gesture && !gesture.moved && pts.size === 0) {
    const t = document.elementFromPoint(e.clientX, e.clientY);
    if (t && t.dataset && t.dataset.r !== undefined) tapRegion(+t.dataset.r);
  }
  if (pts.size === 1) { const q = [...pts.values()][0]; q.sx = q.x; q.sy = q.y; gesture = { moved: true, base: { ...view } }; }
  if (pts.size === 0) gesture = null;
}
$("map").addEventListener("pointerup", up);
$("map").addEventListener("pointercancel", (e) => { pts.delete(e.pointerId); if (!pts.size) gesture = null; });
$("map").addEventListener("wheel", (e) => {
  e.preventDefault(); if (done) return;
  const r = stageEl.getBoundingClientRect(); const mx = e.clientX - r.left, my = e.clientY - r.top;
  const k = Math.max(0.3, Math.min(view.k * Math.exp(-e.deltaY * 0.0015), 40));
  view = { k, x: mx - (mx - view.x) * (k / view.k), y: my - (my - view.y) * (k / view.k) }; applyView();
}, { passive: false });
window.addEventListener("resize", () => { if (S && $("game").classList.contains("on")) fitView(); });

// ---------- buttons ----------
$("back").onclick = () => { clearInterval(timerId); $("game").classList.remove("on"); $("sel").classList.add("on"); };
$("b-list").onclick = $("back").onclick;
$("b-again").onclick = () => start(STAGES.indexOf(S));
$("b-share").onclick = share;

// ---------- share image: map + name + time only ----------
async function share() {
  const W = 1080, H = 1080, [bx, by, bw, bh] = S.box;
  const k = Math.min(W * 0.86 / bw, H * 0.70 / bh);
  const ox = (W - bw * k) / 2 - bx * k, oy = 250 + (H * 0.72 - bh * k) / 2 - by * k;
  const regs = S.regions.map((r, i) => `<path d="${r.d}" fill="${COLORS[color[i]]}" stroke="${COLORS[color[i]]}" stroke-width="${1 / k * 1.5}"/>`).join("");
  const svg = `<svg xmlns="${SVGNS}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect width="${W}" height="${H}" fill="#faf8f3"/>
    <text x="${W / 2}" y="110" text-anchor="middle" font-family="sans-serif" font-size="46" font-weight="600" fill="#2b2a27">${S.name}</text>
    <text x="${W / 2}" y="215" text-anchor="middle" font-family="sans-serif" font-size="96" font-weight="700" fill="#2b2a27">${lastTime}</text>
    <g transform="translate(${ox} ${oy}) scale(${k})">${regs}<path d="${S.border}" fill="none" stroke="#4a4844" stroke-width="${2.2 / k}" stroke-linejoin="round"/></g>
  </svg>`;
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  await img.decode();
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  cv.getContext("2d").drawImage(img, 0, 0);
  const blob = await new Promise((res) => cv.toBlob(res, "image/png"));
  const file = new File([blob], "nuriwake.png", { type: "image/png" });
  const text = `${S.name}を ${lastTime} で塗り分けた！ #四色ぬりわけ`;
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], text }); return; }
  } catch (err) { if (err && err.name === "AbortError") return; }
  const url = URL.createObjectURL(blob);
  $("sh-img").src = url; $("share").classList.add("on");
}
$("share").onclick = (e) => { if (e.target.id === "share" || e.target.id === "sh-close") $("share").classList.remove("on"); };

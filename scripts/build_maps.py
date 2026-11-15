"""国土数値情報 N03 から、ゲームが読む地図データ（src/data/real-maps.json）を作る。

手順: 地域に束ねる -> 隣接を求める（簡略化の前） -> 座標を平面に落とす -> 簡略化 -> SVG のパスにする
          -> 4 色で塗り分けられるか確認する

使い方: uv run python scripts/build_maps.py [--jobs N]（N はプロセス数。既定は CPU 数と 8 の小さいほう）
入力  : data-raw/n03-2025/N03-20250101.shp（docs/DATA.md 参照）
出力  : src/data/stages.json（一覧）と public/maps/NNN.json（ステージごと）
"""
import hashlib
import json
import math
import multiprocessing
import os
import sys
import time
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import MultiLineString, MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
SHP = ROOT / "data-raw/n03-2025/N03-20250101.shp"
CACHE = ROOT / "data-raw/n03-2025/units.gpkg"
INDEX = ROOT / "src/data/stages.json"  # ステージの一覧（名前と地域数）
MAPS_DIR = ROOT / "public/maps"  # ステージごとの地図
SIZE = 1000.0  # 1 ステージの長辺（画面座標）
SIMPLIFY = 2.0  # 簡略化の許容誤差（画面座標）の上限。初期表示で 1px 未満
SIMPLIFY_K = 40  # 許容誤差 = 地域の大きさ（中央値）/ SIMPLIFY_K。simplify_tol を参照
SIMPLIFY_MIN = 0.1  # 許容誤差の下限。出力の座標は 0.1 単位に丸めるので、これより細かくしても意味がない
MIN_ISLAND_KM2 = 0.05  # これより小さい島（実際の面積、km²）は落とす。人の住む島は残し、無人の岩は消えてよい（人間の判断、2026-11-15）


# ---------- 束ねる ----------
def load_units() -> gpd.GeoDataFrame:
    """行政区域コードごとに 1 つの地域（飛び地は MultiPolygon）にする。"""
    if CACHE.exists():
        return gpd.read_file(CACHE)
    g = gpd.read_file(SHP, encoding="utf-8")
    u = g.dissolve(by="N03_007", aggfunc="first").reset_index()
    u.to_file(CACHE, driver="GPKG")
    return u


def merge_by(u: gpd.GeoDataFrame, keys) -> gpd.GeoDataFrame:
    """u.dissolve(by=keys, aggfunc="first") と同じもの。形の union はまとまりごとに独立なので、子プロセスに分けて行う。"""
    u = u.fillna({"N03_002": "", "N03_003": ""})
    data = u.drop(columns=u.geometry.name).groupby(keys).agg("first")
    parts = [list(g) for _, g in u.groupby(keys)[u.geometry.name]]
    merged = POOL.map(shapely.union_all, parts, chunksize=8)
    g = gpd.GeoDataFrame(geometry=list(merged), index=data.index, crs=u.crs)
    return g.join(data).reset_index()


# ---------- ステージを作る ----------
def to_plane(geoms):
    """経緯度 -> 平面（緯度で経度を縮める）。長辺が SIZE になるように拡大する。"""
    f = plane_fn(geoms)
    return [shapely.transform(g, f) for g in geoms]


def plane_fn(geoms):
    """to_plane の座標変換（geoms の範囲で決まる）。"""
    allb = shapely.total_bounds(geoms)
    lat0 = (allb[1] + allb[3]) / 2
    cx = math.cos(math.radians(lat0))
    w, h = (allb[2] - allb[0]) * cx, allb[3] - allb[1]
    s = SIZE / max(w, h)

    def f(xy):
        return np.column_stack([(xy[:, 0] - allb[0]) * cx * s, (allb[3] - xy[:, 1]) * s])

    return f


def adjacency(geoms):
    """境界線を共有している組（点だけの接触は除く）。簡略化の前の形で求める。"""
    eps, minlen = 0.004, 0.02
    tree = STRtree(geoms)
    bounds = [g.boundary for g in geoms]
    pairs = []
    for i, g in enumerate(geoms):
        x0, y0, x1, y1 = g.bounds
        for j in tree.query(shapely.box(x0 - eps, y0 - eps, x1 + eps, y1 + eps)):
            if j <= i:
                continue
            # N03 は隣どうしが境界の頂点を共有しているので、まず境界線の交わりをそのまま見る（速い）
            if bounds[i].intersection(bounds[j]).length > minlen:
                pairs.append((i, int(j)))
            # 頂点がずれているときだけ、ずらし幅をつけて見る（遅い）
            elif g.distance(geoms[j]) < eps and bounds[i].intersection(geoms[j].buffer(eps)).length > minlen:
                pairs.append((i, int(j)))
    return pairs


def drop_specks(deg, plane):
    """実際の面積が MIN_ISLAND_KM2 より小さい島を落とす（最大の部分は必ず残す）。

    deg は経緯度の形、plane は同じ形を to_plane で平面に落としたもの（部分の並びが同じ）。
    判定は deg の面積で行い、plane の部分を返す。ステージの縮尺には左右されないので、
    日本地図や地方のような粗いステージでも、人の住む島は拡大すれば見える。
    面積は度の面積を km² に直した近似（111.32² × cos(緯度)）。
    """
    dp = shapely.get_parts(deg)
    pp = shapely.get_parts(plane)
    km2 = shapely.area(dp) * 111.32**2 * np.cos(np.radians(shapely.get_y(shapely.centroid(dp))))
    keep = (km2 >= MIN_ISLAND_KM2) | (np.arange(len(dp)) == np.argmax(km2))
    kept = list(pp[keep])
    return kept[0] if len(kept) == 1 else MultiPolygon(kept)


def simplify_tol(geoms):
    """簡略化の許容誤差（画面座標）。ステージの範囲ではなく、プレイヤーがタップする地域の大きさで決める。

    地域の大きさは sqrt(面積) の中央値。範囲だけが広いステージ（沖縄県全体は大東から与那国まで約 1000 km）で
    一律に SIMPLIFY を使うと、数 km の市町村が三角形になる（沖縄県全体は地域の大きさ 6 に対して誤差 2）。
    SIMPLIFY_K = 40 は、地域が画面で 100px に見えるとき誤差 2.5px。今までのふつうのステージ（地域の大きさの中央値が
    120 前後で誤差 2、つまり 1/60）と同じくらいの細かさ。地域の大きさが 80 以上のステージは今までどおり SIMPLIFY。
    100 にすると地図の合計が 1.8 倍、北海道全体が 890KB になる（2026-11-15 に測定）。40 で合計 1.1 倍、いちばん大きい北海道全体が 390KB。
    """
    med = float(np.median(np.sqrt(shapely.area(np.array(geoms, dtype=object)))))
    return min(max(med / SIMPLIFY_K, SIMPLIFY_MIN), SIMPLIFY)


ANCHORS = None  # 各市区町村の主な島（いちばん大きな部分と、その 1/4 以上の部分）の代表点（経緯度）。main() で入れる
MAIN_PART_RATIO = 0.25  # 小笠原村は硫黄島がいちばん大きく、父島（0.78）・母島（0.67）が続く。南鳥島は 0.05


def set_anchors(units):
    global ANCHORS
    pts = []
    for g in units.geometry:
        parts = shapely.get_parts(g)
        a = shapely.area(parts)
        pts += [p.representative_point() for p in parts[a >= MAIN_PART_RATIO * a.max()]]
    ANCHORS = shapely.MultiPoint(pts)


def frame_parts(deg, plane):
    """表示の枠（最初に見える範囲）を決める部分。地域ごとに、どこかの市区町村の主な島（ANCHORS）を含む部分と、地域のいちばん大きな部分。

    deg は経緯度の形（to_plane の範囲を決めたもの）、plane は平面に落とした形（小島を落としたあとでもよい）。
    遠くの小島（南鳥島・竹島など、市町村の一部）はデータに残って拡大すれば見えるが、枠を広げない。
    島だけの市町村（小笠原村、北方領土の村など）や、県・振興局にまとめた地域の中の島の市町村（宮古島市など）は枠に入る。
    地域を 1 つの塊として「いちばん大きな部分」だけを見ると、日本地図の沖縄県から先島が外れるので、市区町村ごとに見る。
    """
    pts = shapely.get_parts(shapely.transform(ANCHORS, plane_fn(list(deg))))
    out = []
    for g in plane:
        parts = shapely.get_parts(g)
        big = np.arange(len(parts)) == np.argmax(shapely.area(parts))
        hit = np.zeros(len(parts), bool)
        hit[STRtree(parts).query(pts, predicate="within")[1]] = True
        out.append(shapely.multipolygons(parts[big | hit]))
    return out


def drop_tiny(g, min_area):
    """面積（画面座標）が min_area より小さい部分を落とす（最大の部分は必ず残す）。サムネイル用。"""
    parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    big = max(parts, key=lambda p: p.area)
    keep = [p for p in parts if p.area >= min_area or p is big]
    return keep[0] if len(keep) == 1 else MultiPolygon(keep)


def path_of_polygons(g):
    parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    out = []
    for p in parts:
        p = orient(p, 1.0)
        for ring in [p.exterior, *p.interiors]:
            c = np.round(np.asarray(ring.coords)[:-1], 1)
            out.append("M" + "L".join(f"{x:g} {y:g}" for x, y in c) + "Z")
    return "".join(out)


def path_of_lines(g):
    if g.is_empty:
        return ""
    lines = [x for x in shapely.get_parts(shapely.get_parts(g)) if x.geom_type in ("LineString", "LinearRing")]
    out = []
    for ln in lines:
        c = np.round(np.asarray(ln.coords), 1)
        out.append("M" + "L".join(f"{x:g} {y:g}" for x, y in c))
    return "".join(out)


def four_colorable(n, pairs):
    """DSATUR 順のバックトラックで 4 色の塗り分けを 1 つ探す。見つからなければ None。"""
    adj = [set() for _ in range(n)]
    for a, b in pairs:
        adj[a].add(b)
        adj[b].add(a)
    col = [-1] * n
    sys.setrecursionlimit(10000)

    def pick():
        best, bk = -1, None
        for v in range(n):
            if col[v] < 0:
                k = (len({col[u] for u in adj[v] if col[u] >= 0}), len(adj[v]))
                if bk is None or k > bk:
                    best, bk = v, k
        return best

    def go(left):
        if left == 0:
            return True
        v = pick()
        used = {col[u] for u in adj[v]}
        for c in range(4):
            if c not in used:
                col[v] = c
                if go(left - 1):
                    return True
                col[v] = -1
        return False

    return col if go(n) else None


CACHE_DIR = ROOT / "data-raw/cache"
BUILD_VERSION = 8  # ステージを作る処理を変えたら上げる（キャッシュを無効にする）
ADJ_VERSION = 1  # 隣接の求め方を変えたら上げる


def build_stage(name, geoms, names=None):
    """build_stage_raw の結果を、入力の形と設定が同じならキャッシュから返す。"""
    geoms = list(geoms)
    gh = hashlib.sha1(f"{ADJ_VERSION}|{SIZE}".encode())
    for g in geoms:
        gh.update(shapely.to_wkb(g))
    h = hashlib.sha1(f"{BUILD_VERSION}|{name}|{SIMPLIFY}|{SIMPLIFY_K}|{SIMPLIFY_MIN}|{MIN_ISLAND_KM2}|{names}|{gh.hexdigest()}".encode())
    f = CACHE_DIR / f"{h.hexdigest()}.json"
    if f.exists():
        st = json.loads(f.read_text(encoding="utf-8"))
        print(f"  {name}: 地域 {st['n']}（キャッシュ）", flush=True)
        return st
    t = time.time()
    # 隣接は形だけで決まるので、簡略化の設定とは別にキャッシュする（全国の隣接計算は数分かかる）
    fa = CACHE_DIR / f"adj-{gh.hexdigest()}.json"
    pairs = [tuple(x) for x in json.loads(fa.read_text())] if fa.exists() else None
    st, pairs = build_stage_raw(name, geoms, names, pairs)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(fa, json.dumps(pairs))
    print(f"    {name}: ({time.time() - t:.0f} 秒)", flush=True)
    write_atomic(f, json.dumps(st, ensure_ascii=False))
    return st


def write_atomic(f, text):
    """別のプロセスが同じキャッシュを読み書きしても書きかけを読まないように、一時ファイルに書いてから置き換える。"""
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, f)


# ---------- 並列に作る ----------
# ステージとサムネイルは互いに独立なので、別のプロセスで作る。
# fork で起動するので、set_anchors の結果は子プロセスにそのまま引き継がれる（N03 全体を子で読み直さない）。
POOL = None


def later(fn, *args):
    """fn(*args) を子プロセスに投げる。結果は resolve で取り出す。"""
    return POOL.submit(fn, *args)


def resolve(x):
    """入れ子の dict と list の中の Future を、結果に置き換える。"""
    if isinstance(x, Future):
        return x.result()
    if isinstance(x, dict):
        return {k: resolve(v) for k, v in x.items()}
    if isinstance(x, list):
        return [resolve(v) for v in x]
    return x


def build_stage_raw(name, geoms, names=None, pairs=None):
    deg = geoms
    geoms = to_plane(geoms)
    if pairs is None:
        pairs = adjacency(geoms)
    orig = geoms
    geoms = [drop_specks(d, g) for d, g in zip(deg, geoms)]
    tol = simplify_tol(geoms)
    simp = list(shapely.coverage_simplify(np.array(geoms, dtype=object), tol))
    simp = [g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(0) for g in simp]
    xs0, ys0, xs1, ys1 = shapely.total_bounds(frame_parts(deg, geoms))
    regions = []
    for g in simp:
        rp = g.representative_point()
        regions.append({"d": path_of_polygons(g), "c": [round(rp.x, 1), round(rp.y, 1)]})
    pair_out, empty = [], 0
    for a, b in pairs:
        sh = simp[a].boundary.intersection(simp[b].buffer(0.15 * tol))  # 0.15 * tol は、tol = 2 のとき今までの 0.3
        d = path_of_lines(sh)
        if d == "":  # 簡略化や小島の除去で接する線が消えたときは、元の形から取る
            d = path_of_lines(orig[a].boundary.intersection(orig[b].buffer(0.004)).simplify(tol))
        empty += d == ""
        pair_out.append([a, b, d])
    border = path_of_lines(unary_union([g.boundary for g in simp]))
    sol = four_colorable(len(simp), pairs)
    print(f"  {name}: 地域 {len(simp)} / 隣接 {len(pairs)} / 4色 {'OK' if sol else '見つからず'} / 許容誤差 {tol:.2f} / 線なし {empty} / {len(border) // 1000}KB", flush=True)
    return {
        "name": name,
        "n": len(simp),
        "box": [round(xs0, 1), round(ys0, 1), round(xs1 - xs0, 1), round(ys1 - ys0, 1)],
        "regions": regions,
        "pairs": pair_out,
        "border": border,
        "colorable": bool(sol),
        **({"names": names} if names else {}),
    }, pairs


# ---------- ステージの定義 ----------
# 地方: 学校で習う 8 地方区分。選択画面の見出しにも使う。
# 北海道は 1 道だけなので地方のステージは無し。沖縄は離島の扱いが未決なので九州のステージには入れない
BLOCKS = {
    "北海道": ["北海道"],
    "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"],
    "中部": ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"],
    "近畿": ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州・沖縄": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"],
}
# 地方のステージに入れる県（BLOCKS と違う場合だけ書く）
BLOCK_STAGE_NAME = {"九州・沖縄": "九州"}  # 沖縄を入れないので
BLOCK_STAGE = {"九州・沖縄": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県"]}


def honpen(ward, city, pref_name, spec):
    """対応表から本編ステージを作る。全市町村がちょうど 1 地域に入っているかも確かめる。"""
    cu = city[(city.N03_001 == pref_name) & (city.N03_004 != "所属未定地")]
    listed = [m for a in spec["areas"] for m in a["munis"]]
    missing = set(cu.N03_004) - set(listed)
    unknown = set(listed) - set(cu.N03_004)
    dup = {m for m in listed if listed.count(m) > 1}
    if missing or unknown or dup:
        raise SystemExit(f"{pref_name} の対応表が合わない: 未割当 {missing} / データに無い {unknown} / 重複 {dup}")

    def units(a):
        src = ward if a.get("wards") else city
        return src[(src.N03_001 == pref_name) & src.N03_004.isin(a["munis"])]

    stages = []
    for a in spec["areas"]:
        u = units(a)
        stages.append(later(build_stage, f"{pref_name} {a['name']}", list(u.geometry), list(u.N03_005.fillna(u.N03_004)) if a.get("wards") else list(u.N03_004)))
    upper = []
    byname = {a["name"]: a for a in spec["areas"]}
    for up in spec.get("upper", []):
        munis = [m for nm in up["of"] for m in byname[nm]["munis"]]
        u = city[(city.N03_001 == pref_name) & city.N03_004.isin(munis)]
        upper.append(later(build_stage, f"{pref_name} {up['name']}（上の階層）", list(u.geometry), list(u.N03_004)))
    whole = later(build_stage, pref_name, list(cu.geometry), list(cu.N03_004))
    return stages, upper, whole


# ---------- サムネイル（選択画面の小さな地図。塗らずに輪郭だけ） ----------
THUMB_DIR = ROOT / "public/thumbs"  # 県ごとのサムネイル（県のページを開いたときに読む）


def ipath_polys(g):
    """整数に丸めた多角形のパス（サムネイル用）。"""
    out = []
    for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        for ring in [poly.exterior, *poly.interiors]:
            c = np.round(np.asarray(ring.coords)[:-1]).astype(int)
            if len(c) >= 3:
                out.append("M" + "L".join(f"{x} {y}" for x, y in c) + "Z")
    return "".join(out)


def ipath_lines(g):
    out = []
    for ln in shapely.get_parts(shapely.get_parts(g)):
        if ln.geom_type in ("LineString", "LinearRing"):
            c = np.round(np.asarray(ln.coords)).astype(int)
            if len(c) >= 2:
                out.append("M" + "L".join(f"{x} {y}" for x, y in c))
    return "".join(out)


def main_box(frames, pad=0.04):
    """サムネイルの表示範囲。ゲーム画面の最初の枠と同じ決め方（frame_parts）。frames は thumb_geoms が返す枠の部分。"""
    return box_list(*shapely.total_bounds(frames), pad)


def box_list(x0, y0, x1, y1, pad=0.04):
    pw, ph = (x1 - x0) * pad, (y1 - y0) * pad
    return [round(x0 - pw), round(y0 - ph), round(x1 - x0 + 2 * pw), round(y1 - y0 + 2 * ph)]


def thumb_geoms(geoms, rel):
    """サムネイルの形と、表示範囲を決める部分（ゲーム画面と同じく、小島を落としたあとの frame_parts）。

    簡略化の強さは、表示範囲の大きさに対する割合（rel）で決める。範囲を拡大しても角ばらないように。
    """
    deg = list(geoms)
    P = [drop_specks(d, g) for d, g in zip(deg, to_plane(deg))]
    F = frame_parts(deg, P)
    mb = main_box(F)
    tol = rel * max(mb[2], mb[3])
    P = [drop_tiny(g, tol * tol) for g in P]  # サムネイルは拡大しないので、画面で見えない島は落とす
    return list(shapely.coverage_simplify(np.array(P, dtype=object), tol)), F


def thumb(geoms, rel=0.004):
    """地図の輪郭（陸と境界線）と、ゲーム画面の最初の枠と同じ表示範囲。"""
    S, F = thumb_geoms(geoms, rel)
    return {"vb": main_box(F), "land": "".join(ipath_polys(g) for g in S), "lines": ipath_lines(unary_union([g.boundary for g in S]))}


def thumb_pref(geoms, masks, rel=0.004):
    """県全体の輪郭と、ステージごとに強調する部分。masks はステージごとの「どの市町村が入るか」。"""
    S, F = thumb_geoms(geoms, rel)
    t = {"vb": main_box(F), "land": "".join(ipath_polys(g) for g in S), "lines": ipath_lines(unary_union([g.boundary for g in S])), "parts": []}
    mb = t["vb"]
    for m in masks:
        sel = [g for g, on in zip(S, m) if on]
        x0, y0, x1, y1 = shapely.total_bounds([f for f, on in zip(F, m) if on])
        # 強調する部分が県の範囲の外（離島）にあるときは、範囲を広げて見えるようにする
        x0, y0 = min(x0, mb[0]), min(y0, mb[1])
        x1, y1 = max(x1, mb[0] + mb[2]), max(y1, mb[1] + mb[3])
        t["parts"].append({"d": "".join(ipath_polys(g) for g in sel), "vb": box_list(x0, y0, x1, y1, 0.02)})
    return t


MAX_UNSPLIT = 25  # これ以下の県は分けずに 1 ステージ（仕様書の目安の上限）


def main():
    global POOL
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else min(os.cpu_count() or 1, 8)
    sys.path.insert(0, str(Path(__file__).parent))
    from areas import AREAS

    ward = load_units()  # 区ごと（コード単位）
    set_anchors(ward[ward.N03_004 != "所属未定地"])  # 表示の枠を決める点（frame_parts）
    POOL = ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("fork"))  # set_anchors のあとに作る（子に引き継ぐ）
    city = merge_by(ward, ["N03_001", "N03_003", "N03_004"])  # 政令市は市でまとめる
    is_undetermined = lambda d: d["N03_004"] == "所属未定地"
    pref = merge_by(ward[~is_undetermined(ward)], ["N03_001"])
    print(f"地域: 区ごと {len(ward)} / 市でまとめ {len(city)} / 都道府県 {len(pref)} / {jobs} プロセスで作る", flush=True)
    # 時間のかかる全国は最初に投げる（最後に投げると、それだけが残って待つ）
    zen = later(build_stage, "日本地図", list(pref.geometry), list(pref.N03_001))
    zen_thumb = later(thumb, list(pref.geometry), 0.004)

    def pref_stages(pref_name):
        """1 県ぶんのステージ。分けた県は最後に県全体（まるごと）を付ける。"""
        if pref_name in AREAS:
            stages, _upper, whole = honpen(ward, city, pref_name, AREAS[pref_name])
            cu = city[(city.N03_001 == pref_name) & ~is_undetermined(city)]
            masks = [list(cu.N03_004.isin(a["munis"])) for a in AREAS[pref_name]["areas"]]
            return {"name": pref_name, "stages": stages, "whole": whole, "thumb": later(thumb_pref, list(cu.geometry), masks)}
        if pref_name == "北海道":
            # 案: 振興局ごと（データの N03_002）。政令市（札幌）は他と同じ振興局に入るので市で 1 つ
            hc = city[(city.N03_001 == "北海道") & ~is_undetermined(city)]
            groups = list(hc.groupby("N03_002", sort=False))
            stages = [later(build_stage, f"北海道 {k}", list(g.geometry), list(g.N03_004)) for k, g in groups]
            masks = [list(hc.N03_002 == k) for k, _ in groups]
            return {"name": pref_name, "stages": stages, "whole": later(build_stage, "北海道", list(hc.geometry), list(hc.N03_004)), "thumb": later(thumb_pref, list(hc.geometry), masks)}
        cu = city[(city.N03_001 == pref_name) & ~is_undetermined(city)]
        if len(cu) > MAX_UNSPLIT:
            raise SystemExit(f"{pref_name}: {len(cu)} 市区町村あるのに対応表（scripts/areas.py）が無い")
        return {"name": pref_name, "stages": [later(build_stage, pref_name, list(cu.geometry), list(cu.N03_004))], "whole": None, "thumb": later(thumb_pref, list(cu.geometry), [[True] * len(cu)])}

    blocks = []
    for bname, prefs in BLOCKS.items():
        members = BLOCK_STAGE.get(bname, prefs)
        stage, stage_thumb = None, None
        if bname == "北海道":
            # 北海道は 1 道だけなので、地方の入口は振興局で分けた北海道全体にする
            hk = merge_by(ward[(ward.N03_001 == "北海道") & ~is_undetermined(ward)], ["N03_002"])
            stage = later(build_stage, "北海道（振興局）", list(hk.geometry), list(hk.N03_002))
            stage_thumb = later(thumb, list(hk.geometry), 0.012)
        elif len(members) > 1:
            sel = pref[pref.N03_001.isin(members)]
            stage = later(build_stage, f"{BLOCK_STAGE_NAME.get(bname, bname)}地方", list(sel.geometry), list(sel.N03_001))
            stage_thumb = later(thumb, list(sel.geometry), 0.012)
        codes = {r.N03_001: r.N03_007[:2] for r in pref.itertuples()}
        bp = []
        for pn in prefs:
            ps = pref_stages(pn)
            ps["code"] = codes[pn]
            bp.append(ps)
        blocks.append({"name": bname, "stage": stage, "thumb": stage_thumb, "prefs": bp})

    data = resolve({"zenkoku": zen, "zen_thumb": zen_thumb, "blocks": blocks})
    POOL.shutdown()
    write_split(data)


def write_split(data):
    """ステージごとのファイル（public/maps/）と、一覧（src/data/stages.json）に分けて書く。

    一覧には名前と地域数だけを入れ、ゲームはステージを選んだときにそのファイルを読む。
    """
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    for old in MAPS_DIR.glob("*.json"):
        old.unlink()  # 生成物。消してもこのスクリプトで作り直せる
    total, count = 0, 0

    def put(st):
        nonlocal total, count
        if st is None:
            return None
        f = MAPS_DIR / f"{count:03d}.json"
        f.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total += f.stat().st_size
        count += 1
        return {"name": st["name"], "n": st["n"], "file": f.name}

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    tsize = 0

    def put_thumb(p):
        nonlocal tsize
        f = THUMB_DIR / f"{p['code']}.json"
        f.write_text(json.dumps(p["thumb"], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tsize += f.stat().st_size
        return f.name

    index = {
        "zenkoku": {**put(data["zenkoku"]), "thumb": data["zen_thumb"]},
        "blocks": [
            {
                "name": b["name"],
                "stage": put(b["stage"]),
                "thumb": b["thumb"],
                "prefs": [{"name": p["name"], "stages": [put(s) for s in p["stages"]], "whole": put(p["whole"]), "thumb": put_thumb(p)} for p in b["prefs"]],
            }
            for b in data["blocks"]
        ],
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"サムネイル: 一覧に {INDEX.stat().st_size // 1000}KB、県ごと {THUMB_DIR}/ に計 {tsize // 1000}KB")
    print(f"書き出し: {INDEX} と {MAPS_DIR}/ に {count} ステージ（計 {total // 1000}KB）")


if __name__ == "__main__":
    main()

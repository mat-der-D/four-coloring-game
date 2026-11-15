"""国土数値情報 N03 から、ゲームが読む地図データ（src/data/real-maps.json）を作る。

手順: 地域に束ねる -> 隣接を求める（簡略化の前） -> 座標を平面に落とす -> 簡略化 -> SVG のパスにする
          -> 4 色で塗り分けられるか確認する

使い方: uv run python scripts/build_maps.py
入力  : data-raw/n03-2025/N03-20250101.shp（docs/DATA.md 参照）
"""
import json
import math
import sys
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
OUT = ROOT / "src/data/real-maps.json"
SIZE = 1000.0  # 1 ステージの長辺（画面座標）
SIMPLIFY = 0.8  # 簡略化の許容誤差（画面座標）


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
    return u.fillna({"N03_002": "", "N03_003": ""}).dissolve(by=keys, aggfunc="first").reset_index()


# ---------- ステージを作る ----------
def to_plane(geoms):
    """経緯度 -> 平面（緯度で経度を縮める）。長辺が SIZE になるように拡大する。"""
    allb = shapely.total_bounds(geoms)
    lat0 = (allb[1] + allb[3]) / 2
    cx = math.cos(math.radians(lat0))
    w, h = (allb[2] - allb[0]) * cx, allb[3] - allb[1]
    s = SIZE / max(w, h)

    def f(xy):
        return np.column_stack([(xy[:, 0] - allb[0]) * cx * s, (allb[3] - xy[:, 1]) * s])

    return [shapely.transform(g, f) for g in geoms]


def adjacency(geoms):
    """境界線を共有している組（点だけの接触は除く）。簡略化の前の形で求める。"""
    eps, minlen = 0.004, 0.02
    tree = STRtree(geoms)
    pairs = []
    for i, g in enumerate(geoms):
        gb = g.boundary
        for j in tree.query(g.buffer(eps)):
            if j <= i:
                continue
            shared = gb.intersection(geoms[j].buffer(eps))
            if shared.length > minlen:
                pairs.append((i, int(j)))
    return pairs


def drop_specks(g, min_area=1.5):
    """画面で見えないほど小さい島を落とす（最大の部分は必ず残す）。"""
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
    lines = [g] if g.geom_type == "LineString" else [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]
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


def build_stage(name, geoms, names=None):
    geoms = to_plane(list(geoms))
    pairs = adjacency(geoms)
    geoms = [drop_specks(g) for g in geoms]
    simp = list(shapely.coverage_simplify(np.array(geoms, dtype=object), SIMPLIFY))
    simp = [g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(0) for g in simp]
    xs0, ys0, xs1, ys1 = shapely.total_bounds(simp)
    regions = []
    for g in simp:
        rp = g.representative_point()
        regions.append({"d": path_of_polygons(g), "c": [round(rp.x, 1), round(rp.y, 1)]})
    pair_out, empty = [], 0
    for a, b in pairs:
        sh = simp[a].boundary.intersection(simp[b].buffer(0.3))
        d = path_of_lines(sh)
        empty += d == ""
        pair_out.append([a, b, d])
    border = path_of_lines(unary_union([g.boundary for g in simp]))
    sol = four_colorable(len(simp), pairs)
    print(f"  {name}: 地域 {len(simp)} / 隣接 {len(pairs)} / 4色 {'OK' if sol else '見つからず'} / 線なし {empty} / {len(border) // 1000}KB", flush=True)
    return {
        "name": name,
        "n": len(simp),
        "box": [round(xs0, 1), round(ys0, 1), round(xs1 - xs0, 1), round(ys1 - ys0, 1)],
        "regions": regions,
        "pairs": pair_out,
        "border": border,
        "colorable": bool(sol),
        **({"names": names} if names else {}),
    }


# ---------- ステージの定義 ----------
CHIHO = {
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "近畿（三重を除く）": ["滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "近畿（三重を含む）": ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
}


def main():
    ward = load_units()  # 区ごと（コード単位）
    city = merge_by(ward, ["N03_001", "N03_003", "N03_004"])  # 政令市は市でまとめる
    is_undetermined = lambda d: d["N03_004"] == "所属未定地"
    pref = merge_by(ward[~is_undetermined(ward)], ["N03_001"])
    print(f"地域: 区ごと {len(ward)} / 市でまとめ {len(city)} / 都道府県 {len(pref)}")

    chiho = []
    for nm, prefs in CHIHO.items():
        sel = pref[pref.N03_001.isin(prefs)]
        chiho.append(build_stage(nm, sel.geometry))

    def of(df, p, excl_undetermined=True):
        d = df[df.N03_001 == p]
        return d[~is_undetermined(d)] if excl_undetermined else d

    chiiki = []
    one = lambda pref_name, stage: chiiki.append({"pref": pref_name, "stages": [stage]})
    one("香川県", build_stage("香川県（市町）", of(city, "香川県").geometry))
    one("神奈川県", build_stage("神奈川県（区ごと）", of(ward, "神奈川県").geometry))
    one("神奈川県", build_stage("神奈川県（政令市はまとめる）", of(city, "神奈川県").geometry))
    one("愛知県", build_stage("愛知県（所属未定地なし）", of(city, "愛知県").geometry))
    one("愛知県", build_stage("愛知県（所属未定地あり）", of(city, "愛知県", False).geometry))
    hk = ward[ward.N03_001 == "北海道"]
    one("北海道", build_stage("北海道（振興局）", merge_by(hk, ["N03_002"]).geometry))
    one("北海道", build_stage("北海道（市区町村）", merge_by(hk, ["N03_001", "N03_002", "N03_003", "N03_004"]).geometry))

    zen = build_stage("日本地図（47都道府県）", pref.geometry)
    data = {"chiho": chiho, "chiiki": chiiki, "ken": [], "zenkoku": zen}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"書き出し: {OUT} ({OUT.stat().st_size // 1000}KB)")


if __name__ == "__main__":
    main()

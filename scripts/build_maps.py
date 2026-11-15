"""国土数値情報 N03 から、ゲームが読む地図データ（src/data/real-maps.json）を作る。

手順: 地域に束ねる -> 隣接を求める（簡略化の前） -> 座標を平面に落とす -> 簡略化 -> SVG のパスにする
          -> 4 色で塗り分けられるか確認する

使い方: uv run python scripts/build_maps.py
入力  : data-raw/n03-2025/N03-20250101.shp（docs/DATA.md 参照）
出力  : src/data/stages.json（一覧）と public/maps/NNN.json（ステージごと）
"""
import hashlib
import json
import math
import sys
import time
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
SIMPLIFY = 2.0  # 簡略化の許容誤差（画面座標）。初期表示で 1px 未満
SPECK = 6.0  # これより小さい島（面積、画面座標）は落とす


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


def drop_specks(g, min_area=SPECK):
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
BUILD_VERSION = 3
ADJ_VERSION = 1  # 隣接の求め方を変えたら上げる  # ステージを作る処理を変えたら上げる（キャッシュを無効にする）


def build_stage(name, geoms, names=None):
    """build_stage_raw の結果を、入力の形と設定が同じならキャッシュから返す。"""
    geoms = list(geoms)
    gh = hashlib.sha1(f"{ADJ_VERSION}|{SIZE}".encode())
    for g in geoms:
        gh.update(shapely.to_wkb(g))
    h = hashlib.sha1(f"{BUILD_VERSION}|{name}|{SIMPLIFY}|{SPECK}|{names}|{gh.hexdigest()}".encode())
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
    fa.write_text(json.dumps(pairs))
    print(f"    ({time.time() - t:.0f} 秒)", flush=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return st


def build_stage_raw(name, geoms, names=None, pairs=None):
    geoms = to_plane(geoms)
    if pairs is None:
        pairs = adjacency(geoms)
    orig = geoms
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
        if d == "":  # 簡略化や小島の除去で接する線が消えたときは、元の形から取る
            d = path_of_lines(orig[a].boundary.intersection(orig[b].buffer(0.004)).simplify(SIMPLIFY))
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
        stages.append(build_stage(f"{pref_name} {a['name']}", u.geometry, list(u.N03_005.fillna(u.N03_004)) if a.get("wards") else list(u.N03_004)))
    upper = []
    byname = {a["name"]: a for a in spec["areas"]}
    for up in spec.get("upper", []):
        munis = [m for nm in up["of"] for m in byname[nm]["munis"]]
        u = city[(city.N03_001 == pref_name) & city.N03_004.isin(munis)]
        upper.append(build_stage(f"{pref_name} {up['name']}（上の階層）", u.geometry, list(u.N03_004)))
    whole = build_stage(pref_name, cu.geometry, list(cu.N03_004))
    return stages, upper, whole


MAX_UNSPLIT = 25  # これ以下の県は分けずに 1 ステージ（仕様書の目安の上限）


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    from areas import AREAS

    ward = load_units()  # 区ごと（コード単位）
    city = merge_by(ward, ["N03_001", "N03_003", "N03_004"])  # 政令市は市でまとめる
    is_undetermined = lambda d: d["N03_004"] == "所属未定地"
    pref = merge_by(ward[~is_undetermined(ward)], ["N03_001"])
    print(f"地域: 区ごと {len(ward)} / 市でまとめ {len(city)} / 都道府県 {len(pref)}")

    def pref_stages(pref_name):
        """1 県ぶんのステージ。分けた県は最後に県全体（まるごと）を付ける。"""
        if pref_name in AREAS:
            stages, _upper, whole = honpen(ward, city, pref_name, AREAS[pref_name])
            return {"name": pref_name, "stages": stages, "whole": whole}
        if pref_name == "北海道":
            # 案: 振興局ごと（データの N03_002）。政令市（札幌）は他と同じ振興局に入るので市で 1 つ
            hc = city[(city.N03_001 == "北海道") & ~is_undetermined(city)]
            stages = [build_stage(f"北海道 {k}", g.geometry, list(g.N03_004)) for k, g in hc.groupby("N03_002", sort=False)]
            return {"name": pref_name, "stages": stages, "whole": None}
        cu = city[(city.N03_001 == pref_name) & ~is_undetermined(city)]
        if len(cu) > MAX_UNSPLIT:
            raise SystemExit(f"{pref_name}: {len(cu)} 市区町村あるのに対応表（scripts/areas.py）が無い")
        return {"name": pref_name, "stages": [build_stage(pref_name, cu.geometry, list(cu.N03_004))], "whole": None}

    blocks = []
    for bname, prefs in BLOCKS.items():
        members = BLOCK_STAGE.get(bname, prefs)
        stage = None
        if len(members) > 1:
            sel = pref[pref.N03_001.isin(members)]
            stage = build_stage(f"{BLOCK_STAGE_NAME.get(bname, bname)}地方", sel.geometry, list(sel.N03_001))
        blocks.append({"name": bname, "stage": stage, "prefs": [pref_stages(p) for p in prefs]})

    zen = build_stage("日本地図", pref.geometry, list(pref.N03_001))
    write_split({"zenkoku": zen, "blocks": blocks})


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

    index = {
        "zenkoku": put(data["zenkoku"]),
        "blocks": [
            {
                "name": b["name"],
                "stage": put(b["stage"]),
                "prefs": [{"name": p["name"], "stages": [put(s) for s in p["stages"]], "whole": put(p["whole"])} for p in b["prefs"]],
            }
            for b in data["blocks"]
        ],
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"書き出し: {INDEX} と {MAPS_DIR}/ に {count} ステージ（計 {total // 1000}KB）")


if __name__ == "__main__":
    main()

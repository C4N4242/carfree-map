"""起点（ハブ）から歩いて届く施設の数を、3通りの方法で比べる。

  straight   直線距離 ÷ 歩く速さ（従来の簡易な方法）
  road_flat  道路網上の最短経路、坂は無視
  road_slope 道路網上の最短経路、坂を考慮（Tobler の式）

出力（results/<地域id>/）:
  walk_summary.md   道路網・標高・施設データの概要と、起点ごとの比較表
  hub_walk.csv      起点 × 分 × 方法 × 分類 の施設数
  poi_list.csv      取得した施設の一覧（登録状況の確認用）
処理途中のデータ（data/processed/<地域id>/）:
  walk.graphml      徒歩時間つきの道路網（公共交通の計算で再利用）

使い方:
    python pipeline/hub_walk.py --region <地域id>
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import date

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree

from pois import fetch_pois, load_categories
from region import load_region
from walk_network import build_walk_graph

METHODS = {"straight": "直線距離", "road_flat": "道路（坂なし）", "road_slope": "道路（坂あり）"}
ATTRIBUTION = "地図データ © OpenStreetMap contributors (ODbL) / 標高: 国土地理院 標高タイル"


def hub_stops(region, hub: str) -> pd.DataFrame:
    frames = []
    for f in region.feeds:
        with zipfile.ZipFile(f.zip_path) as z, z.open("stops.txt") as fp:
            s = pd.read_csv(fp, dtype=str, encoding="utf-8-sig")
        frames.append(s[s["stop_name"] == hub])
    stops = pd.concat(frames)
    if stops.empty:
        raise SystemExit(f"起点 '{hub}' が時刻表データの停留所名に見つかりません。")
    return stops.astype({"stop_lat": float, "stop_lon": float})


def project_points(lon, lat, crs) -> np.ndarray:
    import geopandas as gpd

    g = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs="EPSG:4326").to_crs(crs)
    return np.column_stack([g.x.values, g.y.values])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    args = ap.parse_args()
    region = load_region(args.region)
    if not region.hubs:
        raise SystemExit(f"地域設定 {region.id} に hubs（起点の停留所名）がありません。")
    w = region.walk
    v0 = w.speed_m_per_min * w.weather_factor / 60.0
    max_s = max(w.minutes) * 60

    print("道路網を取得して標高を付けています…")
    G, gstats = build_walk_graph(region)
    region.processed_dir.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, region.processed_dir / "walk.graphml")

    print("施設を取得しています…")
    pois = fetch_pois(region)

    # 位置合わせは平面直角座標（メートル）で行う
    Gp = ox.project_graph(G)
    crs = Gp.graph["crs"]
    node_ids = np.array(list(Gp.nodes))
    node_xy = np.array([[Gp.nodes[n]["x"], Gp.nodes[n]["y"]] for n in node_ids])
    tree = cKDTree(node_xy)
    poi_xy = project_points(pois["lon"].values, pois["lat"].values, crs)
    snap_d, snap_i = tree.query(poi_xy)
    pois["node"] = node_ids[snap_i]
    pois["snap_m"] = snap_d

    rows = []
    for hub in region.hubs:
        stops = hub_stops(region, hub)
        stop_xy = project_points(stops["stop_lon"].values, stops["stop_lat"].values, crs)
        src_d, src_i = tree.query(stop_xy)
        sources = set(node_ids[src_i].tolist())
        start_s = float(src_d.min()) / v0  # 停留所から最寄りの道路までの徒歩

        straight_m = cKDTree(stop_xy).query(poi_xy)[0]
        t = {"straight": straight_m / v0}
        for method, weight in (("road_flat", "walk_flat_s"), ("road_slope", "walk_s")):
            dist = nx.multi_source_dijkstra_path_length(G, sources, cutoff=max_s, weight=weight)
            node_t = pois["node"].map(dist).astype(float).values
            t[method] = start_s + node_t + pois["snap_m"].values / v0  # 道路から施設までの徒歩を足す
        for minutes in w.minutes:
            for method, secs in t.items():
                within = pois[np.nan_to_num(secs, nan=np.inf) <= minutes * 60]
                counts = within["category"].value_counts()
                for c in load_categories():
                    rows.append(dict(hub=hub, minutes=minutes, method=method, category=c["id"], count=int(counts.get(c["id"], 0))))

    out = pd.DataFrame(rows)
    rd = region.results_dir
    rd.mkdir(parents=True, exist_ok=True)
    out.to_csv(rd / "hub_walk.csv", index=False, encoding="utf-8-sig")
    pois.drop(columns=["node"]).sort_values(["category", "name"]).to_csv(rd / "poi_list.csv", index=False, encoding="utf-8-sig")
    (rd / "walk_summary.md").write_text(summary_md(region, gstats, pois, out), encoding="utf-8")
    print((rd / "walk_summary.md").read_text(encoding="utf-8"))


def summary_md(region, gstats: dict, pois: pd.DataFrame, out: pd.DataFrame) -> str:
    cats = load_categories()
    names = {c["id"]: c["name"] for c in cats}
    w = region.walk
    lines = [
        f"# 徒歩圏の集計（{region.name}）",
        "",
        f"集計日: {date.today()}　{ATTRIBUTION}",
        "",
        "## 道路網と標高",
        "",
        "| 項目 | 値 |",
        "|---|---|",
        f"| 範囲（南, 西, 北, 東） | {', '.join(map(str, region.bbox))} |",
        f"| 交差点などの点 / 道路の区間 | {gstats['nodes']:,} / {gstats['edges']:,} |",
        f"| 歩ける道路の総延長 | {gstats['length_km']:,.0f} km |",
        f"| 標高の範囲 | {gstats['elev_min']:.1f}〜{gstats['elev_max']:.1f} m（欠測 {gstats['elev_missing']} 点） |",
        f"| 勾配5%を超える道路の割合 | {gstats['share_grade_over_5pct']:.1%} |",
        f"| 勾配0とした橋・トンネルの区間 | {gstats['edges_structure_flat']:,} |",
        f"| 平坦な道の歩く速さ | {w.speed_m_per_min:g} m/分（天候係数 {w.weather_factor:g}） |",
        "",
        "## 施設データ（OpenStreetMap）の登録状況",
        "",
        "| 分類 | 件数 | 名前あり | 道路から100m超 |",
        "|---|---|---|---|",
    ]
    for c in cats:
        p = pois[pois["category"] == c["id"]]
        named = p["name"].notna().mean() if len(p) else 0
        far = (p["snap_m"] > 100).sum()
        lines.append(f"| {c['name']} | {len(p):,} | {named:.0%} | {far} |")
    for minutes in w.minutes:
        lines += ["", f"## 起点から徒歩{minutes}分で届く施設の数", "", "| 起点 | 方法 | " + " | ".join(names[c["id"]] for c in cats) + " |",
                  "|---|---|" + "---|" * len(cats)]
        sub = out[out["minutes"] == minutes]
        for hub in region.hubs:
            for method, label in METHODS.items():
                s = sub[(sub["hub"] == hub) & (sub["method"] == method)].set_index("category")["count"]
                lines.append(f"| {hub} | {label} | " + " | ".join(str(s.get(c["id"], 0)) for c in cats) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

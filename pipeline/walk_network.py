"""歩行者の道路網を作り、坂を考慮した徒歩時間を各辺に付ける。

- 道路網: OpenStreetMap（osmnx の network_type="walk"）
- 標高: 国土地理院 DEM（elevation.py）
- 歩く速さ: Tobler の式を、平坦な道で設定値（既定 80 m/分）になるよう正規化したもの
      v = v0 * exp(-3.5 * (|s + 0.05| - 0.05))   s: 勾配（上りが正）
  下り 5% で最も速く（v0 の約1.19倍）、上りも急な下りも遅くなる。
- 橋とトンネルは、下の地面や山の標高を拾ってしまうため勾配 0 とする。

各辺に付く属性:
  grade        勾配（向きつき）
  walk_s       坂を考慮した徒歩時間 [秒]
  walk_flat_s  坂を無視した徒歩時間 [秒]
"""

from __future__ import annotations

import math
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox

from elevation import DemSampler
from region import RAW_DIR, Region

ox.settings.use_cache = True
ox.settings.cache_folder = str(RAW_DIR / "osm_cache")
ox.settings.requests_timeout = 300
ox.settings.http_user_agent = "carfree-map"


def tobler_factor(grade: float) -> float:
    """平坦を 1 としたときの歩く速さの倍率。"""
    return math.exp(-3.5 * (abs(grade + 0.05) - 0.05))


def _is_structure(value) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    values = value if isinstance(value, list) else [value]
    return any(str(v).lower() not in ("no", "none", "") for v in values)


def add_walk_times(G: nx.MultiDiGraph, speed_m_per_min: float, weather_factor: float = 1.0, max_grade: float = 0.3) -> dict:
    """ノード属性 elev をもとに、各辺へ grade, walk_s, walk_flat_s を付ける。集計値を返す。"""
    v0 = speed_m_per_min * weather_factor / 60.0  # m/秒
    n_struct = n_noelev = 0
    for u, v, d in G.edges(data=True):
        length = float(d.get("length", 0.0))
        eu, ev = G.nodes[u].get("elev", np.nan), G.nodes[v].get("elev", np.nan)
        if _is_structure(d.get("bridge")) or _is_structure(d.get("tunnel")):
            grade = 0.0
            n_struct += 1
        elif np.isnan(eu) or np.isnan(ev) or length < 1.0:
            grade = 0.0
            n_noelev += 1
        else:
            grade = float(np.clip((ev - eu) / length, -max_grade, max_grade))
        d["grade"] = grade
        d["walk_flat_s"] = length / v0
        d["walk_s"] = length / (v0 * tobler_factor(grade))
    return {"edges_structure_flat": n_struct, "edges_without_elevation": n_noelev}


def build_walk_graph(region: Region, dem_cache: Path | None = None) -> tuple[nx.MultiDiGraph, dict]:
    if region.bbox is None:
        raise SystemExit(f"地域設定 {region.id} に bbox（[南, 西, 北, 東]）がありません。")
    south, west, north, east = region.bbox
    G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type="walk", simplify=True, retain_all=False)

    nodes = list(G.nodes)
    lon = np.array([G.nodes[n]["x"] for n in nodes])
    lat = np.array([G.nodes[n]["y"] for n in nodes])
    elev = DemSampler(dem_cache or RAW_DIR / "dem").sample(lon, lat)
    nx.set_node_attributes(G, dict(zip(nodes, elev.tolist())), "elev")

    w = region.walk
    stats = add_walk_times(G, w.speed_m_per_min, w.weather_factor, w.max_grade)
    lengths = np.array([d["length"] for _, _, d in G.edges(data=True)])
    grades = np.abs(np.array([d["grade"] for _, _, d in G.edges(data=True)]))
    stats.update(
        nodes=G.number_of_nodes(),
        edges=G.number_of_edges(),
        length_km=float(lengths.sum() / 1000 / 2),  # 双方向に1本ずつあるため半分にする
        elev_min=float(np.nanmin(elev)),
        elev_max=float(np.nanmax(elev)),
        elev_missing=int(np.isnan(elev).sum()),
        share_grade_over_5pct=float((lengths[grades > 0.05]).sum() / lengths.sum()),
    )
    return G, stats

"""ネットワークに接続しない単体テスト。  python -m pytest tests"""

import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from elevation import decode_dem_png, lonlat_to_global_pixel  # noqa: E402
from walk_network import add_walk_times, tobler_factor  # noqa: E402


def test_decode_dem_png():
    def enc(x):
        return [(x >> 16) & 255, (x >> 8) & 255, x & 255]
    rgb = np.array([[enc(1234), enc(2**23), enc(2**24 - 500)]], dtype=np.uint8)
    h = decode_dem_png(rgb)
    assert h[0, 0] == pytest.approx(12.34)
    assert np.isnan(h[0, 1])
    assert h[0, 2] == pytest.approx(-5.0)


def test_pixel_of_known_tile():
    # 東京駅付近は z14 のタイル (14552, 6451) に入る
    px, py = lonlat_to_global_pixel(np.array([139.7671]), np.array([35.6812]), 14)
    assert int(px[0] // 256) == 14552 and int(py[0] // 256) == 6451


def test_tobler_factor():
    assert tobler_factor(0.0) == pytest.approx(1.0)
    assert tobler_factor(-0.05) == pytest.approx(np.exp(0.175))  # 下り5%が最速
    assert tobler_factor(0.10) < tobler_factor(0.0) < tobler_factor(-0.05)
    assert tobler_factor(-0.30) < 1.0  # 急な下りは平坦より遅い


def _graph():
    G = nx.MultiDiGraph()
    for n, e in [(1, 0.0), (2, 10.0), (3, 10.0), (4, 50.0)]:
        G.add_node(n, elev=e)
    G.add_edge(1, 2, length=100.0)                 # 上り 10%
    G.add_edge(2, 1, length=100.0)                 # 下り 10%
    G.add_edge(2, 3, length=50.0)                  # 平坦
    G.add_edge(3, 4, length=100.0, bridge="yes")   # 橋: 標高差があっても平坦扱い
    G.add_edge(4, 1, length=0.5)                   # 短すぎる区間
    return G


def test_add_walk_times():
    G = _graph()
    stats = add_walk_times(G, speed_m_per_min=60.0)  # 1 m/秒
    up, down = G[1][2][0], G[2][1][0]
    assert up["grade"] == pytest.approx(0.10) and down["grade"] == pytest.approx(-0.10)
    assert up["walk_flat_s"] == pytest.approx(100.0)
    assert up["walk_s"] > down["walk_s"] > 100.0 * 0.85
    assert G[2][3][0]["walk_s"] == pytest.approx(50.0)
    assert G[3][4][0]["grade"] == 0.0 and stats["edges_structure_flat"] == 1
    assert G[4][1][0]["grade"] == 0.0 and stats["edges_without_elevation"] == 1


def test_weather_factor_slows_walk():
    G = _graph()
    add_walk_times(G, speed_m_per_min=60.0, weather_factor=0.8)
    assert G[2][3][0]["walk_s"] == pytest.approx(50.0 / 0.8)

"""OpenStreetMap から施設を取得し、poi_categories.toml の分類を付ける。"""

from __future__ import annotations

import tomllib
from pathlib import Path

import osmnx as ox
import pandas as pd

import walk_network  # noqa: F401  osmnx のキャッシュ設定を共有する
from region import Region

CATEGORIES_FILE = Path(__file__).resolve().parent / "poi_categories.toml"


def load_categories() -> list[dict]:
    return tomllib.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))["category"]


def _merged_tags(categories: list[dict]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for c in categories:
        for k, vs in c["tags"].items():
            merged.setdefault(k, set()).update(vs)
    return {k: sorted(v) for k, v in merged.items()}


def classify(row: pd.Series, categories: list[dict]) -> str | None:
    for c in categories:
        for k, vs in c["tags"].items():
            if k in row.index and isinstance(row[k], str) and row[k] in vs:
                return c["id"]
    return None


def fetch_pois(region: Region) -> pd.DataFrame:
    """列: category, name, lat, lon, osm_type, osm_id"""
    categories = load_categories()
    south, west, north, east = region.bbox
    gdf = ox.features_from_bbox(bbox=(west, south, east, north), tags=_merged_tags(categories))
    gdf = gdf.reset_index()
    pts = gdf.geometry.representative_point()
    df = pd.DataFrame(
        {
            "category": gdf.apply(lambda r: classify(r, categories), axis=1),
            "name": gdf["name"] if "name" in gdf.columns else None,
            "lat": pts.y,
            "lon": pts.x,
            "osm_type": gdf["element"] if "element" in gdf.columns else gdf["element_type"],
            "osm_id": gdf["id"] if "id" in gdf.columns else gdf["osmid"],
        }
    )
    return df.dropna(subset=["category"]).reset_index(drop=True)

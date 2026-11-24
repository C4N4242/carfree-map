"""国土地理院の標高タイル（DEM, PNG形式）から地点の標高を求める。

標高タイルの仕様: https://maps.gsi.go.jp/development/demtile.html
RGB 値 x = R*2^16 + G*2^8 + B について、x < 2^23 なら h = x*0.01 m、
x = 2^23 は欠測、x > 2^23 なら h = (x - 2^24)*0.01 m。
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
import requests
from PIL import Image

TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png"  # DEM10B, 最大ズーム14
HEADERS = {"User-Agent": "carfree-map"}
TILE = 256


def decode_dem_png(rgb: np.ndarray) -> np.ndarray:
    """(H, W, 3) の uint8 配列を標高 [m] に変換する。欠測は NaN。"""
    v = rgb.astype(np.int64)
    x = (v[..., 0] << 16) + (v[..., 1] << 8) + v[..., 2]
    h = np.where(x < 2**23, x * 0.01, (x - 2**24) * 0.01).astype(float)
    h[x == 2**23] = np.nan
    return h


def lonlat_to_global_pixel(lon: np.ndarray, lat: np.ndarray, z: int) -> tuple[np.ndarray, np.ndarray]:
    n = TILE * 2**z
    px = (np.asarray(lon) + 180.0) / 360.0 * n
    lat_r = np.radians(np.asarray(lat))
    py = (1.0 - np.arcsinh(np.tan(lat_r)) / math.pi) / 2.0 * n
    return px, py


class DemSampler:
    def __init__(self, cache_dir: Path, z: int = 14, url: str = TILE_URL):
        self.z, self.url, self.cache_dir = z, url, Path(cache_dir)
        self._tiles: dict[tuple[int, int], np.ndarray] = {}

    def _tile(self, tx: int, ty: int) -> np.ndarray:
        key = (tx, ty)
        if key in self._tiles:
            return self._tiles[key]
        path = self.cache_dir / str(self.z) / str(tx) / f"{ty}.png"
        if path.exists():
            data = path.read_bytes()
        else:
            r = requests.get(self.url.format(z=self.z, x=tx, y=ty), headers=HEADERS, timeout=30)
            data = r.content if r.status_code == 200 else b""
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)  # 404（海など）も空ファイルとして記録し、再取得しない
        if data:
            arr = decode_dem_png(np.asarray(Image.open(io.BytesIO(data)).convert("RGB")))
        else:
            arr = np.full((TILE, TILE), np.nan)
        self._tiles[key] = arr
        return arr

    def sample(self, lon, lat) -> np.ndarray:
        """地点ごとの標高 [m]（最も近い画素の値）。"""
        px, py = lonlat_to_global_pixel(lon, lat, self.z)
        ix, iy = np.floor(px).astype(int), np.floor(py).astype(int)
        tx, ty = ix // TILE, iy // TILE
        out = np.full(len(ix), np.nan)
        for key in set(zip(tx.tolist(), ty.tolist())):
            m = (tx == key[0]) & (ty == key[1])
            out[m] = self._tile(*key)[iy[m] % TILE, ix[m] % TILE]
        return out

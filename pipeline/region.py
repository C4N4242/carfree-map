"""地域設定ファイル（regions/<id>.toml）の読み込み。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS_DIR = ROOT / "regions"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


@dataclass
class Feed:
    id: str
    name: str = ""
    url: str | None = None   # zip を直接指す URL
    page: str | None = None  # zip へのリンクが載っている配布ページ（先頭のリンクを使う）

    @property
    def zip_path(self) -> Path:
        return RAW_DIR / f"{self.id}.zip"


@dataclass
class Walk:
    speed_m_per_min: float = 80.0      # 平坦な道での歩く速さ（不動産の表示基準 80 m/分）
    weather_factor: float = 1.0        # 天候による速さの係数（晴れ=1.0）
    max_grade: float = 0.3             # 標高誤差による極端な勾配を抑える上限
    minutes: list[int] = field(default_factory=lambda: [5, 10, 15])


@dataclass
class Region:
    id: str
    name: str
    timezone: str = "Asia/Tokyo"
    bbox: tuple[float, float, float, float] | None = None  # (南, 西, 北, 東) の緯度経度
    hubs: list[str] = field(default_factory=list)          # 起点にする停留所名（GTFS の stop_name）
    feeds: list[Feed] = field(default_factory=list)
    walk: Walk = field(default_factory=Walk)

    @property
    def results_dir(self) -> Path:
        return ROOT / "results" / self.id

    @property
    def processed_dir(self) -> Path:
        return PROCESSED_DIR / self.id


def load_region(region_id: str) -> Region:
    path = REGIONS_DIR / f"{region_id}.toml"
    if not path.exists():
        found = ", ".join(p.stem for p in sorted(REGIONS_DIR.glob("*.toml")) if p.stem != "example")
        raise SystemExit(f"地域設定 {path} がありません。利用できる地域: {found or '(なし)'}")
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    feeds = [Feed(**f) for f in cfg.get("gtfs", [])]
    for f in feeds:
        if not (f.url or f.page):
            raise SystemExit(f"{path}: gtfs '{f.id}' に url か page を指定してください。")
    r = cfg.get("region", {})
    bbox = tuple(r["bbox"]) if "bbox" in r else None
    if bbox is not None and (len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3])):
        raise SystemExit(f"{path}: bbox は [南, 西, 北, 東] の順で指定してください。")
    return Region(
        id=region_id,
        name=r.get("name", region_id),
        timezone=r.get("timezone", "Asia/Tokyo"),
        bbox=bbox,
        hubs=list(r.get("hubs", [])),
        feeds=feeds,
        walk=Walk(**cfg.get("walk", {})),
    )

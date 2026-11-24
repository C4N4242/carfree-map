"""地域設定ファイル（regions/<id>.toml）の読み込み。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS_DIR = ROOT / "regions"
RAW_DIR = ROOT / "data" / "raw"


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
class Region:
    id: str
    name: str
    timezone: str = "Asia/Tokyo"
    feeds: list[Feed] = field(default_factory=list)

    @property
    def results_dir(self) -> Path:
        return ROOT / "results" / self.id


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
    return Region(id=region_id, name=r.get("name", region_id), timezone=r.get("timezone", "Asia/Tokyo"), feeds=feeds)

"""地域設定に書かれた GTFS をダウンロードする。

各フィードについて、url があればそれを、page があればそのページで最初に見つかった
.zip へのリンクを取得し、data/raw/<フィードid>.zip に保存する。

使い方:
    python pipeline/fetch_data.py --region <地域id>
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from urllib.parse import urljoin

import requests

from region import RAW_DIR, Feed, load_region

HEADERS = {"User-Agent": "carfree-map"}


def resolve_url(feed: Feed) -> str:
    if feed.url:
        return feed.url
    html = requests.get(feed.page, headers=HEADERS, timeout=30).text
    links = re.findall(r'href=["\']([^"\']+\.zip)["\']', html, flags=re.IGNORECASE)
    if not links:
        sys.exit(f"{feed.page} に .zip へのリンクが見つかりません。地域設定で url を直接指定してください。")
    return urljoin(feed.page, links[0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="regions/<id>.toml の id")
    args = ap.parse_args()

    region = load_region(args.region)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    region.results_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for feed in region.feeds:
        url = resolve_url(feed)
        print(f"[{feed.id}] download: {url}")
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        feed.zip_path.write_bytes(r.content)
        with zipfile.ZipFile(feed.zip_path) as z:
            print(f"[{feed.id}] saved {feed.zip_path.name} ({feed.zip_path.stat().st_size:,} bytes):", ", ".join(sorted(z.namelist())))
        sources.append(f"{feed.id}\t{url}")
    (region.results_dir / "gtfs_sources.tsv").write_text("\n".join(sources) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

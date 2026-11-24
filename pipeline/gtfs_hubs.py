"""起点候補（ハブ）を選ぶため、停留所ごとの1日の発車本数を数える。

- 地域設定に書かれたすべての GTFS フィードを合算する
- 指定日に運行している便だけを数える（calendar.txt と calendar_dates.txt を反映）
- 便の終点では発車しないので数えない
- 同じ名前の停留所（のりば違い）は1つにまとめる
- 結果は results/<地域id>/hub_ranking_<日付>.csv に保存する

使い方:
    python pipeline/gtfs_hubs.py --region <地域id> --date 2026-12-01
    python pipeline/gtfs_hubs.py --gtfs path/to/feed.zip --date 2026-12-01   # 地域設定なしで1フィードだけ
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from region import load_region

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def read(z: zipfile.ZipFile, name: str) -> pd.DataFrame | None:
    if name not in z.namelist():
        return None
    with z.open(name) as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig")


def active_services(cal: pd.DataFrame | None, cal_dates: pd.DataFrame | None, d: date) -> set[str]:
    ymd = d.strftime("%Y%m%d")
    services: set[str] = set()
    if cal is not None:
        on = cal[(cal["start_date"] <= ymd) & (cal["end_date"] >= ymd) & (cal[WEEKDAYS[d.weekday()]] == "1")]
        services |= set(on["service_id"])
    if cal_dates is not None:
        today = cal_dates[cal_dates["date"] == ymd]
        services |= set(today.loc[today["exception_type"] == "1", "service_id"])
        services -= set(today.loc[today["exception_type"] == "2", "service_id"])
    return services


def departures(gtfs_path: Path, d: date, feed_id: str) -> pd.DataFrame:
    """指定日の発車（停留所×便）を1行ずつ返す。"""
    with zipfile.ZipFile(gtfs_path) as z:
        stops = read(z, "stops.txt")
        trips = read(z, "trips.txt")
        st = read(z, "stop_times.txt")
        routes = read(z, "routes.txt")
        services = active_services(read(z, "calendar.txt"), read(z, "calendar_dates.txt"), d)

    trips = trips[trips["service_id"].isin(services)]
    st = st[st["trip_id"].isin(trips["trip_id"])].copy()
    if st.empty:
        return st
    st["stop_sequence"] = st["stop_sequence"].astype(int)
    last = st.groupby("trip_id")["stop_sequence"].transform("max")
    dep = st[st["stop_sequence"] < last]

    dep = dep.merge(trips[["trip_id", "route_id"]], on="trip_id").merge(
        stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]], on="stop_id"
    )
    if routes is not None and "agency_id" in routes.columns:
        dep = dep.merge(routes[["route_id", "agency_id"]], on="route_id", how="left")
    else:
        dep["agency_id"] = ""
    dep["feed"] = feed_id
    dep["route_key"] = feed_id + ":" + dep["route_id"]
    dep["trip_key"] = feed_id + ":" + dep["trip_id"]
    return dep


def rank_hubs(feeds: list[tuple[str, Path]], d: date) -> pd.DataFrame:
    parts = [departures(path, d, fid) for fid, path in feeds]
    dep = pd.concat([p for p in parts if not p.empty], ignore_index=True) if any(not p.empty for p in parts) else None
    if dep is None:
        raise SystemExit(f"{d} に運行している便がありません。データの有効期間を確認してください。")

    dep["stop_lat"] = dep["stop_lat"].astype(float)
    dep["stop_lon"] = dep["stop_lon"].astype(float)
    out = (
        dep.groupby("stop_name")
        .agg(
            departures=("trip_key", "size"),
            routes=("route_key", "nunique"),
            feeds=("feed", lambda s: " ".join(sorted(set(s)))),
            agencies=("agency_id", lambda s: " ".join(sorted(set(s.dropna())))),
            lat=("stop_lat", "mean"),
            lon=("stop_lon", "mean"),
        )
        .sort_values(["departures", "routes"], ascending=False)
        .reset_index()
    )
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--region", help="regions/<id>.toml の id")
    src.add_argument("--gtfs", type=Path, help="GTFS zip を1つだけ直接指定")
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out", type=Path, help="出力先 CSV（省略時は results/<地域id>/ または data/processed/）")
    args = ap.parse_args()

    if args.region:
        region = load_region(args.region)
        feeds = [(f.id, f.zip_path) for f in region.feeds]
        out = args.out or region.results_dir / f"hub_ranking_{args.date}.csv"
    else:
        feeds = [(args.gtfs.stem, args.gtfs)]
        out = args.out or Path("data/processed") / f"hub_ranking_{args.date}.csv"

    ranking = rank_hubs(feeds, args.date)
    out.parent.mkdir(parents=True, exist_ok=True)
    ranking.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{args.date}（{'月火水木金土日'[args.date.weekday()]}）の発車本数ランキング → {out}")
    print(ranking.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()

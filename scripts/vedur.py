"""Veðurstofa Íslands (Icelandic Met Office) — api.vedur.is (modern JSON API).

No authentication; both services are OpenAPI-described. The OpenAPI spec is
authoritative — e.g. GET /quakes/events is summarised as GeoJSON-or-CSV but
`format` only accepts csv|json, and `json` returns GeoJSON anyway. There is NO
`limit` parameter on quake queries (it 422s) — bound with start_time instead.

Datasets covered by this script:

  stations       GET /weather/stations                          -> data/processed/vedur_stations.csv
  observations   GET /weather/observations/aws/{agg}/latest     -> data/processed/vedur_obs_latest.csv
  quakes         GET /quakes/events?start_time=...&size_min=... -> data/processed/vedur_quakes.csv

Documented in .agents/skills/vedur/SKILL.md but NOT scripted here: forecasts
(legacy xmlweather.vedur.is XML — still the simplest source), historical
climatology (no API, form-based web downloads only), the OGC EDR interface
under /weather/rodeo/, per-station time series via /weather/observations/aws/
{aggregation}, and /weather/parameters (field descriptions).

Usage:
    uv run python scripts/vedur.py list
    uv run python scripts/vedur.py fetch                          # all datasets
    uv run python scripts/vedur.py fetch --dataset quakes --days 14 --min-magnitude 2
    uv run python scripts/vedur.py fetch --dataset observations --aggregation hour
    uv run python scripts/vedur.py fetch --force                  # ignore the 24h raw cache
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "vedur"
PROCESSED_DIR = ROOT / "data" / "processed"

WEATHER = "https://api.vedur.is/weather"
QUAKES = "https://api.vedur.is/quakes"
USER_AGENT = "icelandic-data/vedur (+https://github.com/jokull/icelandic-data)"
CACHE_TTL = timedelta(hours=24)  # live source: raw snapshot is fresh for a day

# Datasets: name -> (endpoint, tidy output filename, one-line description)
DATASETS = {
    "stations": ("/weather/stations", "vedur_stations.csv", "all weather stations (776, live/historical)"),
    "observations": (
        "/weather/observations/aws/{agg}/latest",
        "vedur_obs_latest.csv",
        "latest automatic-weather-station observations (~293 stations, 10-min or hourly)",
    ),
    "quakes": ("/quakes/events?start_time=...&size_min=...", "vedur_quakes.csv", "earthquake events as GeoJSON, magnitude-filtered"),
}


def get(url: str, params: dict | None = None) -> httpx.Response:
    response = httpx.get(url, params=params, timeout=60, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response


def raw_cache(path: Path, args: argparse.Namespace) -> httpx.Response | None:
    """Reuse a fresh cached raw file (24h TTL) unless --force."""
    if args.force or not path.exists():
        return None
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    if age > CACHE_TTL:
        print(f"  cached {path.name} is {age.days}d old — re-fetching")
        return None
    print(f"  using cached {path.name}")
    return httpx.Response(200, content=path.read_bytes())


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------


def fetch_stations(args: argparse.Namespace) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / "stations.json"
    response = raw_cache(raw, args) or get(f"{WEATHER}/stations")
    if not raw.exists() or args.force:
        raw.write_text(response.text, encoding="utf-8")

    rows = response.json()
    df = (
        pl.DataFrame(rows, infer_schema_length=None)
        .unique(subset=["station"], keep="last")
        .sort("station")
    )
    out = PROCESSED_DIR / "vedur_stations.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(out)
    print(f"  {len(df):,} stations -> {out}")


# ---------------------------------------------------------------------------
# Latest AWS observations
# ---------------------------------------------------------------------------


def fetch_observations(args: argparse.Namespace) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"obs_aws_{args.aggregation}_latest.json"
    response = raw_cache(raw, args) or get(f"{WEATHER}/observations/aws/{args.aggregation}/latest")
    if not raw.exists() or args.force:
        raw.write_text(response.text, encoding="utf-8")

    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"unexpected payload from {WEATHER}/observations/aws/{args.aggregation}/latest: {rows!r}")

    columns = set(rows[0])  # aggregation-dependent: hourly has no 'minute', 10min no 'fx'
    df = (
        pl.DataFrame(rows, infer_schema_length=None)
        .unique(subset=["station", "time"], keep="last")
        .sort("time", "station")
        .with_columns(pl.col("time").str.to_datetime("%Y-%m-%dT%H:%M:%S"))
        .drop([c for c in ("year", "month", "day", "hour", "minute") if c in columns])  # redundant — encoded in time
    )
    out = PROCESSED_DIR / "vedur_obs_latest.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(out)
    print(f"  {len(df):,} stations, latest {args.aggregation} observations -> {out}")


# ---------------------------------------------------------------------------
# Earthquakes
# ---------------------------------------------------------------------------


def fetch_quakes(args: argparse.Namespace) -> None:
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {"start_time": start, "size_min": args.min_magnitude}

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"quakes_events_{args.days}d_m{args.min_magnitude}.json"
    response = raw_cache(raw, args) or get(f"{QUAKES}/events", params=params)
    if not raw.exists() or args.force:
        raw.write_text(response.text, encoding="utf-8")

    payload = response.json()
    features = payload.get("features") or []
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        rows.append({**props, "lon": coordinates[0] if len(coordinates) > 0 else None, "lat": coordinates[1] if len(coordinates) > 1 else None})

    df = (
        pl.DataFrame(rows, infer_schema_length=None)
        .unique(subset=["event_id"], keep="last")
        .sort("time")
        .with_columns(
            pl.col("time").str.to_datetime("%Y-%m-%dT%H:%M:%S%.fZ"),
            pl.col("updated_time").str.to_datetime("%Y-%m-%dT%H:%M:%S%.fZ"),
        )
    )
    out = PROCESSED_DIR / "vedur_quakes.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(out)
    print(f"  {len(df):,} quakes (>=M{args.min_magnitude}, last {args.days}d) -> {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_list(_: argparse.Namespace) -> None:
    print("Datasets covered by scripts/vedur.py (api.vedur.is, no auth):")
    for name, (endpoint, output, description) in DATASETS.items():
        print(f"  {name:<14} {endpoint:<48} -> data/processed/{output}")
        print(f"                  {description}")
    print()
    print("Documented in .agents/skills/vedur/SKILL.md but NOT scripted:")
    print("  forecasts      legacy xmlweather.vedur.is XML (still the simplest source)")
    print("  climatology    historical data — no API, form-based web downloads")
    print("  EDR            OGC interface under /weather/rodeo/collections/")
    print("  parameters     field descriptions via /weather/parameters?url=...")


def cmd_fetch(args: argparse.Namespace) -> None:
    for name in args.dataset:
        print(f"[{name}]")
        if name == "stations":
            fetch_stations(args)
        elif name == "observations":
            fetch_observations(args)
        elif name == "quakes":
            fetch_quakes(args)
        else:
            raise SystemExit(f"unknown dataset '{name}'; choose from {', '.join(DATASETS)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)

    p_list = sub.add_parser("list", help="enumerate the datasets this script covers")
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="download datasets to data/processed/")
    p_fetch.add_argument(
        "--dataset",
        action="append",
        choices=list(DATASETS),
        default=[],
        help="dataset(s) to fetch; repeatable, default: all",
    )
    p_fetch.add_argument("--aggregation", choices=["10min", "hour"], default="10min", help="observations: AWS aggregation (default 10min)")
    p_fetch.add_argument("--days", type=int, default=7, help="quakes: look-back window in days (default 7)")
    p_fetch.add_argument("--min-magnitude", type=float, default=1, help="quakes: minimum magnitude (default 1)")
    p_fetch.add_argument("--force", action="store_true", help="re-fetch even if a fresh raw cache exists")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    if not getattr(args, "dataset", None):
        args.dataset = list(DATASETS)
    args.func(args)


if __name__ == "__main__":
    main()

"""Environment Agency of Iceland public GeoServer layers.

Usage:
    uv run python scripts/ust_gis.py list
    uv run python scripts/ust_gis.py fetch
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import httpx
import polars as pl

WFS = "https://gis.ust.is/geoserver/ows"
CONTAMINATED_LAND = "INSPIRE:mengadur_jardvegur"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "ust_gis"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "ust_contaminated_land.parquet"


def get(params: dict) -> httpx.Response:
    response = httpx.get(WFS, params={"service": "WFS", "version": "2.0.0", **params}, timeout=90)
    response.raise_for_status()
    return response


def cmd_list(_: argparse.Namespace) -> None:
    text = get({"request": "GetCapabilities"}).text
    for name in re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", text):
        print(name)


def cmd_fetch(_: argparse.Namespace) -> None:
    payload = get({"request": "GetFeature", "typeNames": CONTAMINATED_LAND, "outputFormat": "application/json", "srsName": "EPSG:4326"}).json()
    features = payload.get("features") or []
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / "contaminated_land.geojson"
    raw.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rows = [{**(f.get("properties") or {}), "geometry_type": (f.get("geometry") or {}).get("type")} for f in features]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Registry attributes mix integers, floats and nulls across historic rows;
    # inspect the complete small layer before fixing the schema.
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(OUT)
    print(f"  {len(rows):,} contaminated-land records")
    print(f"  Wrote {raw} and {OUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("fetch").set_defaults(func=cmd_fetch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

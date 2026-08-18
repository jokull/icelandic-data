"""Fiskistofa public fishing-regulation geodata (open WFS only).

Usage:
    uv run python scripts/fiskistofa.py list
    uv run python scripts/fiskistofa.py fetch
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import httpx
import polars as pl

WFS = "https://gis.is/geoserver/fiskistofa/wfs"
ACTIVE_CLOSURES = "virkar_skyndilokanir"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "fiskistofa"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "fiskistofa_active_closures.parquet"


def get(params: dict) -> httpx.Response:
    response = httpx.get(WFS, params={"service": "WFS", "version": "2.0.0", **params}, timeout=60)
    response.raise_for_status()
    return response


def cmd_list(_: argparse.Namespace) -> None:
    text = get({"request": "GetCapabilities"}).text
    names = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", text)
    for name in names:
        if name.startswith(("virk_", "virkar_")):
            print(name)


def cmd_fetch(_: argparse.Namespace) -> None:
    payload = get({"request": "GetFeature", "typeNames": ACTIVE_CLOSURES, "outputFormat": "application/json", "srsName": "EPSG:4326"}).json()
    features = payload.get("features") or []
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / "active_closures.geojson"
    raw.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rows = [{**(f.get("properties") or {}), "geometry_type": (f.get("geometry") or {}).get("type")} for f in features]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(OUT)
    print(f"  {len(rows):,} active rapid closures")
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

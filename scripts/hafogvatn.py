"""Marine and Freshwater Research Institute stock-assessment tables.

Usage:
    uv run python scripts/hafogvatn.py list
    uv run python scripts/hafogvatn.py fetch --stock cod --year 2026
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import polars as pl
from bs4 import BeautifulSoup

BASE = "https://www.hafogvatn.is"
CATALOGUE = f"{BASE}/en/moya/extras/categories/radgjof"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "hafogvatn"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def tables_url(stock: str, year: int) -> str:
    # Current MFRI publication convention: stock number is immaterial to the
    # table endpoint for cod; other stocks can pass an explicit URL later.
    if stock != "cod":
        raise ValueError("currently supported stock is cod; use list for the catalogue URL")
    return f"{BASE}/static/extras/images/1_cod_{year}_1_tables_en.html"


def assessment_table(html: str) -> pl.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h3", string="Assessment summary")
    if heading:
        widget = heading.find_next("div", class_="datatables")
        script = widget.find_next_sibling("script") if widget else None
        if script:
            data = json.loads(script.string or "")
            payload = data["x"]
            names = {
                definition["targets"]: definition["name"]
                for definition in payload["options"]["columnDefs"]
                if "name" in definition and isinstance(definition["targets"], int)
            }
            columns = {
                names[index]: values for index, values in enumerate(payload["data"]) if index in names
            }
            if "Year" in columns:
                return pl.DataFrame(columns)
    raise ValueError("no embedded Assessment summary DataTables JSON found")


def cmd_list(_: argparse.Namespace) -> None:
    print("MFRI annual advice catalogue\t" + CATALOGUE)
    print("cod assessment tables\t" + tables_url("cod", 2026))


def cmd_fetch(args: argparse.Namespace) -> None:
    url = tables_url(args.stock, args.year)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{args.stock}_{args.year}_tables.html"
    raw.write_text(response.text, encoding="utf-8")
    df = assessment_table(response.text).with_columns(
        pl.lit(args.stock).alias("stock"), pl.lit(args.year).alias("assessment_year")
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"hafogvatn_{args.stock}_assessment.parquet"
    df.write_parquet(out)
    print(f"  {len(df):,} {args.stock} assessment rows")
    print(f"  Wrote {raw} and {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--stock", default="cod")
    fetch.add_argument("--year", type=int, default=2026)
    fetch.set_defaults(func=cmd_fetch)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

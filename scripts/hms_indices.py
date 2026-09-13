"""Process HMS house price (kaupvisitala) and rental price (leiguvisitala) indices.

Source: https://hms.is/gogn-og-maelabord/visitolur

Raw files:
    data/raw/hms/indices/kaupvisitala.csv   (house price index, monthly 2020-01+)
    data/raw/hms/indices/leiguvisitala.csv  (rental index, monthly 2023-05+)

Output:
    data/processed/hms_rent_vs_price_index.csv
        columns: date, region, price_index, rent_index, yoy_price_pct, yoy_rent_pct,
                 price_published, rent_published
    data/raw/hms/indices/indices.meta.json   (HTTP Last-Modified / ETag per file, fetched_at)
    data/raw/hms/indices/releases/{name}.{last-modified date}.csv  (one snapshot per release)

Vintage matters here: HMS restamps and revises the ENTIRE leiguvísitala
back-series on every release (every row carries the same UTGAFUDAGUR), so a
rent-index value quoted last month can differ from the same month today.
The per-row publication date is carried through as `rent_published` /
`price_published`, and each release is snapshotted so revisions can be diffed.

The kaupvisitala file has regional breakdowns (national, capital area, landsbyggð,
and sérbýli/fjölbýli by region). The leiguvisitala CSV is NATIONAL ONLY — no
regional disaggregation is published (HMS has an interactive dashboard
'Leiguverðsja' for region filters, but the static CSV is national only).

We produce a long format with region ∈ {national, capital_area, rest_of_country}.
The rental index is populated only for 'national' (rebased so national price and
national rent both = 100 at 2023-05, the first rent observation).
"""
from __future__ import annotations

import argparse
import io
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from tempfile import TemporaryDirectory
import sys
from pathlib import Path

import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "hms" / "indices"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "hms_rent_vs_price_index.csv"

# The visitala page (hms.is/gogn-og-maelabord/visitolur) is behind a Vercel
# checkpoint, but the CSVs it links live on public object storage and fetch
# directly. Imported by tests/health/test_hms.py to probe freshness.
OCI = "https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com/n/frs3o1zldvgn/b/public_data_for_download/o"
KAUPVISITALA_URL = f"{OCI}/kaupvisitala.csv"
LEIGUVISITALA_URL = f"{OCI}/leiguvisitala.csv"
HEADERS = {"User-Agent": "icelandic-data/1.0 (data toolkit fetcher)"}


def published_col() -> pl.Expr:
    """UTGAFUDAGUR as a Date; blank on old kaupvísitala rows → null."""
    return (
        pl.col("UTGAFUDAGUR").cast(pl.Utf8).str.strip_chars()
        .replace("", None).str.to_date("%Y-%m-%d", strict=False).alias("published")
    )


def load_kaup() -> pl.DataFrame:
    df = pl.read_csv(
        RAW / "kaupvisitala.csv",
        schema_overrides={"AR": pl.Int32, "MANUDUR": pl.Utf8},
    )
    df = df.with_columns(
        pl.date(
            pl.col("AR"),
            pl.col("MANUDUR").str.strip_chars().cast(pl.Int32),
            1,
        ).alias("date"),
        published_col(),
    ).select(
        "date",
        "published",
        pl.col("VISITALA").alias("national"),
        pl.col("VISITALA_HOFUDBORGARSVAEDI").alias("capital_area"),
        pl.col("VISITALA_LANDSBYGGD").alias("rest_of_country"),
    )
    return df.sort("date")


def load_leigu() -> pl.DataFrame:
    df = pl.read_csv(
        RAW / "leiguvisitala.csv",
        schema_overrides={"AR": pl.Int32, "MANUDUR": pl.Utf8},
    )
    df = df.with_columns(
        pl.date(
            pl.col("AR"),
            pl.col("MANUDUR").str.strip_chars().cast(pl.Int32),
            1,
        ).alias("date"),
        published_col(),
    ).select("date", pl.col("published").alias("rent_published"), pl.col("VISITALA").alias("rent_national"))
    return df.sort("date")


def rebase_to(df: pl.DataFrame, col: str, anchor_date) -> pl.DataFrame:
    """Rebase so that df[col] == 100 at anchor_date."""
    base = df.filter(pl.col("date") == anchor_date)[col].item()
    return df.with_columns((pl.col(col) / base * 100.0).alias(col))


def cmd_fetch(args: argparse.Namespace) -> None:
    """Download kaup-/leiguvísitala CSVs from public object storage.

    The hms.is visitala page is behind a Vercel checkpoint, but the CSVs it
    links live on OCI object storage and fetch directly. Both are small (a few
    KB), so this downloads them in full rather than streaming.
    """
    import httpx

    RAW.mkdir(parents=True, exist_ok=True)
    meta = {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": {}}
    with TemporaryDirectory(dir=RAW, prefix="indices-") as staging:
        for url, name in ((KAUPVISITALA_URL, "kaupvisitala.csv"),
                          (LEIGUVISITALA_URL, "leiguvisitala.csv")):
            r = httpx.get(url, timeout=60, headers=HEADERS, follow_redirects=True)
            r.raise_for_status()
            df = pl.read_csv(io.BytesIO(r.content))
            required = {"AR", "MANUDUR", "VISITALA"}
            if name == "kaupvisitala.csv":
                required |= {"VISITALA_HOFUDBORGARSVAEDI", "VISITALA_LANDSBYGGD"}
            if not required <= set(df.columns) or not df.height:
                raise ValueError(f"Invalid index schema: {name}")
            (Path(staging) / name).write_bytes(r.content)
            last_modified = r.headers.get("last-modified")
            newest = df["UTGAFUDAGUR"].cast(pl.Utf8).str.strip_chars().max() if "UTGAFUDAGUR" in df.columns else None
            meta["files"][name] = {"url": url, "last_modified": last_modified, "etag": r.headers.get("etag"),
                                   "newest_utgafudagur": newest, "rows": df.height}
        # Both responses have been fetched and checked before replacing either.
        for name in ("kaupvisitala.csv", "leiguvisitala.csv"):
            (Path(staging) / name).replace(RAW / name)
            print(f"  saved: {RAW / name}")
    # One snapshot per upstream release: the leiguvísitala back-series is
    # revised wholesale each month, so the previous release must survive.
    for name, info in meta["files"].items():
        stamp = (parsedate_to_datetime(info["last_modified"]).strftime("%Y-%m-%d") if info["last_modified"]
                 else meta["fetched_at"][:10])
        snap = RAW / "releases" / f"{Path(name).stem}.{stamp}.csv"
        if not snap.exists():
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_bytes((RAW / name).read_bytes())
            print(f"  release snapshot: {snap}")
        print(f"  {name}: last-modified {info['last_modified']}, newest UTGAFUDAGUR {info['newest_utgafudagur']}")
    (RAW / "indices.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\nNow run the processor (bare `python scripts/hms_indices.py`) to build the merged index.")


def cmd_process(args: argparse.Namespace) -> None:
    for name in ("kaupvisitala.csv", "leiguvisitala.csv"):
        if not (RAW / name).exists():
            sys.exit(
                f"Missing raw file {RAW / name}. Run `fetch` first — the visitala CSVs "
                f"are downloaded from public object storage, not the Vercel-guarded page."
            )

    kaup = load_kaup()
    leigu = load_leigu()

    # Rent index is 100 in 2023-05. Rebase price indices so national price = 100 in 2023-05
    # to make cumulative divergence directly comparable.
    from datetime import date

    anchor = date(2023, 5, 1)
    kaup_rebased = kaup
    for col in ("national", "capital_area", "rest_of_country"):
        kaup_rebased = rebase_to(kaup_rebased, col, anchor)

    # Long format
    price_long = kaup_rebased.unpivot(
        index=["date", "published"],
        on=["national", "capital_area", "rest_of_country"],
        variable_name="region",
        value_name="price_index",
    )

    rent_long = leigu.rename({"rent_national": "rent_index"}).with_columns(
        pl.lit("national").alias("region"),
    )

    merged = price_long.join(rent_long, on=["date", "region"], how="left")

    # YoY % change
    merged = merged.sort(["region", "date"]).with_columns(
        (
            (pl.col("price_index") / pl.col("price_index").shift(12).over("region") - 1)
            * 100
        )
        .round(2)
        .alias("yoy_price_pct"),
        (
            (pl.col("rent_index") / pl.col("rent_index").shift(12).over("region") - 1)
            * 100
        )
        .round(2)
        .alias("yoy_rent_pct"),
    )

    merged = merged.select(
        "date", "region", "price_index", "rent_index", "yoy_price_pct", "yoy_rent_pct",
        pl.col("published").alias("price_published"), "rent_published",
    )
    merged = merged.with_columns(
        pl.col("price_index").round(2),
        pl.col("rent_index").round(2),
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged.write_csv(OUT)

    print(f"Wrote {OUT}  ({len(merged)} rows)")
    print(f"Date range: {merged['date'].min()} .. {merged['date'].max()}")
    print("\nLatest YoY (national):")
    latest_nat = (
        merged.filter(pl.col("region") == "national").sort("date").tail(1)
    )
    print(latest_nat)

    print("\nLatest YoY (capital_area):")
    latest_cap = (
        merged.filter(pl.col("region") == "capital_area").sort("date").tail(1)
    )
    print(latest_cap)

    # Cumulative divergence since 2023-05 (anchor for both = 100)
    print("\nCumulative change since 2023-05 (both anchored at 100):")
    latest_national_row = (
        merged.filter(pl.col("region") == "national")
        .filter(pl.col("rent_index").is_not_null())
        .sort("date")
        .tail(1)
    )
    p = latest_national_row["price_index"].item()
    r = latest_national_row["rent_index"].item()
    d = latest_national_row["date"].item()
    print(f"  As of {d}: national price_index={p:.1f}, rent_index={r:.1f}")
    print(f"  Price cum Δ = {p - 100:+.1f} pts, Rent cum Δ = {r - 100:+.1f} pts")
    print(f"  Divergence (price − rent) = {p - r:+.1f} pts")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fetch", help="download kaup-/leiguvísitala CSVs from object storage")
    f.set_defaults(func=cmd_fetch)
    p = sub.add_parser("process", help="build the merged rent-vs-price index from raw CSVs")
    p.set_defaults(func=cmd_process)
    # Bare run == process (AGENTS.md quick command, and the pre-existing behaviour).
    ap.set_defaults(func=cmd_process)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

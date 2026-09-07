"""Process HMS house price (kaupvisitala) and rental price (leiguvisitala) indices.

Source: https://hms.is/gogn-og-maelabord/visitolur

Raw files:
    data/raw/hms/indices/kaupvisitala.csv   (house price index, monthly 2020-01+)
    data/raw/hms/indices/leiguvisitala.csv  (rental index, monthly 2023-05+)

Output:
    data/processed/hms_rent_vs_price_index.csv
        columns: date, region, price_index, rent_index, yoy_price_pct, yoy_rent_pct

The purchase index has national and regional breakdowns. The public rent
index covers capital-area market rents in recent contracts, not all Iceland.
Rent is attached only to capital_area; comparisons use matching geography.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "hms" / "indices"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "hms_rent_vs_price_index.csv"


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
    ).select(
        "date",
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
    ).select("date", pl.col("VISITALA").alias("rent_capital_area"))
    return df.sort("date")


def rebase_to(df: pl.DataFrame, col: str, anchor_date) -> pl.DataFrame:
    """Rebase so that df[col] == 100 at anchor_date."""
    base = df.filter(pl.col("date") == anchor_date)[col].item()
    return df.with_columns((pl.col(col) / base * 100.0).alias(col))


def main() -> None:
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
        index=["date"],
        on=["national", "capital_area", "rest_of_country"],
        variable_name="region",
        value_name="price_index",
    )

    rent_long = leigu.rename({"rent_capital_area": "rent_index"}).with_columns(
        pl.lit("capital_area").alias("region"),
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
        "date", "region", "price_index", "rent_index", "yoy_price_pct", "yoy_rent_pct"
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
    latest_capital_row = (
        merged.filter(pl.col("region") == "capital_area")
        .filter(pl.col("rent_index").is_not_null())
        .sort("date")
        .tail(1)
    )
    p = latest_capital_row["price_index"].item()
    r = latest_capital_row["rent_index"].item()
    d = latest_capital_row["date"].item()
    print(f"  As of {d}: capital-area price_index={p:.1f}, rent_index={r:.1f}")
    print(f"  Price cum Δ = {p - 100:+.1f} pts, Rent cum Δ = {r - 100:+.1f} pts")
    print(f"  Divergence (price − rent) = {p - r:+.1f} pts")


if __name__ == "__main__":
    main()

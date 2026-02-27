"""
Process Gasvaktin fuel price data into tidy CSVs for analysis.
Combines with Brent crude prices to compute implied retail margins.
"""

import json
from pathlib import Path
from datetime import datetime

import polars as pl

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "gasvaktin"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

COMPANY_NAMES = {
    "ao": "Atlantsolía",
    "co": "Costco",
    "dn": "Dælan",
    "n1": "N1",
    "ob": "ÓB",
    "ol": "Olís",
    "or": "Orkan",
    "ox": "Orkan X",
    "sk": "Skeljungur",
}

# Major retailers only (exclude Costco single station, Dælan small)
MAJOR_RETAILERS = {"ao", "n1", "ol", "or"}


def load_trends() -> pl.DataFrame:
    """Load Gasvaktin trends.json into a flat DataFrame."""
    with open(RAW_DIR / "vaktin" / "trends.json") as f:
        data = json.load(f)

    rows = []
    for code, entries in data.items():
        name = COMPANY_NAMES.get(code, code)
        for entry in entries:
            ts = entry.get("timestamp", "")
            if not ts:
                continue
            rows.append(
                {
                    "company_code": code,
                    "company": name,
                    "date": ts[:10],
                    "bensin95": entry.get("mean_bensin95"),
                    "bensin95_discount": entry.get("mean_bensin95_discount"),
                    "diesel": entry.get("mean_diesel"),
                    "diesel_discount": entry.get("mean_diesel_discount"),
                    "stations": entry.get("stations_count"),
                }
            )

    df = pl.DataFrame(rows)
    df = df.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
    return df.sort(["company_code", "date"])


def compute_daily_averages(df: pl.DataFrame) -> pl.DataFrame:
    """Compute market-wide daily averages (major retailers only)."""
    major = df.filter(pl.col("company_code").is_in(MAJOR_RETAILERS))
    daily = (
        major.group_by("date")
        .agg(
            pl.col("bensin95").mean().alias("avg_bensin95"),
            pl.col("diesel").mean().alias("avg_diesel"),
            pl.col("bensin95").min().alias("min_bensin95"),
            pl.col("bensin95").max().alias("max_bensin95"),
            pl.col("diesel").min().alias("min_diesel"),
            pl.col("diesel").max().alias("max_diesel"),
            pl.col("company").n_unique().alias("n_companies"),
        )
        .sort("date")
    )
    return daily


def compute_monthly_averages(df: pl.DataFrame) -> pl.DataFrame:
    """Monthly averages by company."""
    return (
        df.with_columns(
            pl.col("date").dt.year().alias("year"),
            pl.col("date").dt.month().alias("month"),
        )
        .group_by(["company_code", "company", "year", "month"])
        .agg(
            pl.col("bensin95").mean().round(1).alias("avg_bensin95"),
            pl.col("diesel").mean().round(1).alias("avg_diesel"),
            pl.col("stations").max().alias("max_stations"),
        )
        .sort(["company_code", "year", "month"])
    )


def compute_spread(df: pl.DataFrame) -> pl.DataFrame:
    """Compute price spread between companies on each date."""
    major = df.filter(pl.col("company_code").is_in(MAJOR_RETAILERS))
    spread = (
        major.group_by("date")
        .agg(
            (pl.col("bensin95").max() - pl.col("bensin95").min())
            .alias("bensin95_spread"),
            (pl.col("diesel").max() - pl.col("diesel").min()).alias("diesel_spread"),
        )
        .sort("date")
    )
    return spread


def main():
    print("Loading Gasvaktin trends data...")
    df = load_trends()
    print(f"  {len(df)} price observations, {df['company'].n_unique()} companies")
    print(
        f"  Date range: {df['date'].min()} to {df['date'].max()}"
    )

    # Save full dataset
    out = PROCESSED_DIR / "fuel_prices_daily.csv"
    df.write_csv(out)
    print(f"  Wrote {out}")

    # Daily market averages
    daily = compute_daily_averages(df)
    out2 = PROCESSED_DIR / "fuel_market_daily.csv"
    daily.write_csv(out2)
    print(f"  Wrote {out2}")

    # Monthly by company
    monthly = compute_monthly_averages(df)
    out3 = PROCESSED_DIR / "fuel_prices_monthly.csv"
    monthly.write_csv(out3)
    print(f"  Wrote {out3}")

    # Price spread
    spread = compute_spread(df)
    out4 = PROCESSED_DIR / "fuel_price_spread.csv"
    spread.write_csv(out4)
    print(f"  Wrote {out4}")

    # Summary stats
    for code in MAJOR_RETAILERS:
        co = df.filter(pl.col("company_code") == code)
        latest = co.sort("date").tail(1)
        if len(latest) > 0:
            row = latest.row(0, named=True)
            print(
                f"  {row['company']:15s} latest: bensin95={row['bensin95']:.1f} diesel={row['diesel']:.1f} ({row['date']})"
            )


if __name__ == "__main__":
    main()

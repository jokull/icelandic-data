"""
Process data for Play Airlines bankruptcy impact analysis.
Combines Hagstofan passenger data with Nasdaq announcements.
"""

import polars as pl
from pathlib import Path
import json

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

def process_passenger_data():
    """Transform wide-format Hagstofan passenger data to tidy format."""

    # Read CSV - it's in wide format with months as columns
    df = pl.read_csv(
        RAW_DIR / "hagstofan_passengers.csv",
        encoding="utf-8"
    )

    # Get column names (first is category, rest are months)
    cols = df.columns
    month_cols = [c for c in cols if c != "Ríkisfang"]

    # Unpivot to long format
    df_long = df.unpivot(
        index="Ríkisfang",
        on=month_cols,
        variable_name="month",
        value_name="passengers"
    )

    # Parse month column (format: 2024M01)
    df_long = df_long.with_columns([
        pl.col("month").str.slice(0, 4).cast(pl.Int32).alias("year"),
        pl.col("month").str.slice(5, 2).cast(pl.Int32).alias("month_num"),
        pl.col("Ríkisfang").alias("category")
    ])

    # Create date column
    df_long = df_long.with_columns(
        pl.date(pl.col("year"), pl.col("month_num"), 1).alias("date")
    )

    # Select and rename columns
    df_tidy = df_long.select([
        "date",
        "year",
        "month_num",
        "category",
        "passengers"
    ]).sort(["category", "date"])

    return df_tidy

def extract_play_timeline():
    """Extract key events from Play announcements."""

    with open(RAW_DIR / "nasdaq" / "play_announcements.json") as f:
        announcements = json.load(f)

    key_events = []
    for ann in announcements:
        headline = ann["headline"].lower()
        # Filter for significant events
        if any(kw in headline for kw in [
            "gjaldþrot", "hættir starfsemi", "afkomuviðvörun",
            "yfirtöku", "aðalmarkaði", "breytingar á viðskiptalíkani"
        ]):
            key_events.append({
                "date": ann["date"][:10],
                "event": ann["headline"],
                "category": ann["category"]
            })

    return pl.DataFrame(key_events)

def extract_icelandair_passenger_growth():
    """Extract monthly passenger growth from Icelandair announcements."""

    with open(RAW_DIR / "nasdaq" / "icelandair_announcements.json") as f:
        announcements = json.load(f)

    growth_data = []
    for ann in announcements:
        headline = ann["headline"]
        # Look for passenger growth announcements
        if "farþeg" in headline.lower() and "%" in headline:
            growth_data.append({
                "date": ann["date"][:10],
                "headline": headline
            })

    return pl.DataFrame(growth_data) if growth_data else None

def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Process passenger data
    print("Processing Keflavik passenger data...")
    passengers = process_passenger_data()
    passengers.write_csv(PROCESSED_DIR / "keflavik_passengers.csv")
    print(f"  Wrote {len(passengers)} rows")

    # Recent data summary (2024-2025)
    recent = passengers.filter(pl.col("year") >= 2024)
    recent_summary = recent.filter(
        pl.col("category") == "Farþegar alls"
    ).select(["date", "year", "month_num", "passengers"])
    recent_summary.write_csv(PROCESSED_DIR / "keflavik_passengers_recent.csv")
    print(f"  Recent summary: {len(recent_summary)} months")

    # Play timeline
    print("Extracting Play timeline...")
    play_events = extract_play_timeline()
    play_events.write_csv(PROCESSED_DIR / "play_key_events.csv")
    print(f"  Found {len(play_events)} key events")

    # Icelandair growth
    print("Extracting Icelandair passenger updates...")
    ice_growth = extract_icelandair_passenger_growth()
    if ice_growth is not None:
        ice_growth.write_csv(PROCESSED_DIR / "icelandair_passenger_growth.csv")
        print(f"  Found {len(ice_growth)} updates")

    print("\nDone! Files in data/processed/")

if __name__ == "__main__":
    main()

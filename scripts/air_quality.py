"""
Fetch PM10 air quality data from UST (Umhverfisstofnun) bulk CSVs and wind data from Open-Meteo.
Produces daily aggregated CSV for Reykjavik Grensásvegur station.

Uses annual bulk CSV downloads from api.ust.is (~70-100MB each) instead of per-day API.
"""

import io
from datetime import date, timedelta
from pathlib import Path

import httpx
import polars as pl

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "air_quality"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

STATION_ID = "STA-IS0005A"  # Grensásvegur (traffic)
BG_STATION_ID = "STA-IS0006A"  # Húsdýragarðurinn (background)
START_YEAR = 2016

UST_CSV_BASE = "https://api.ust.is/static/aq"
UST_API_BASE = "https://api.ust.is/aq/a"
OPEN_METEO_BASE = "https://archive-api.open-meteo.com/v1/archive"


def download_annual_csv(year: int) -> Path:
    """Download annual UST CSV if not cached."""
    cache_file = RAW_DIR / f"ust_aq_timeseries_{year}.csv"
    if cache_file.exists():
        size_mb = cache_file.stat().st_size / 1_000_000
        print(f"  Cached: {cache_file.name} ({size_mb:.0f} MB)")
        return cache_file

    url = f"{UST_CSV_BASE}/ust_aq_timeseries_{year}.csv"
    print(f"  Downloading {url}...")
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = 0
        with open(cache_file, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                total += len(chunk)
    size_mb = total / 1_000_000
    print(f"  Downloaded: {cache_file.name} ({size_mb:.0f} MB)")
    return cache_file


def load_pm10_from_csv(csv_path: Path, station_id: str) -> pl.DataFrame:
    """Extract PM10 hourly readings for a station from annual CSV."""
    # CSV columns: station_name, pollutantnotation, local_id, endtime, the_value,
    #              resolution, verification, validity, station_local_id, concentration
    df = pl.scan_csv(
        csv_path,
        infer_schema_length=1000,
        ignore_errors=True,
    ).filter(
        (pl.col("station_local_id") == station_id)
        & (pl.col("pollutantnotation") == "PM10")
    ).select(
        pl.col("endtime"),
        pl.col("the_value").cast(pl.Float64, strict=False).alias("pm10"),
    ).collect()

    if df.is_empty():
        return df

    # CSVs use two date formats: "2016-01-01 00:00:00" (older) and "31/12/2024 23:00:00" (newer)
    # Try DD/MM/YYYY first, fall back to YYYY-MM-DD
    sample = df["endtime"][0]
    if "/" in sample:
        fmt = "%d/%m/%Y %H:%M:%S"
    else:
        fmt = "%Y-%m-%d %H:%M:%S"

    df = df.with_columns(
        pl.col("endtime").str.to_datetime(fmt, strict=False).alias("datetime")
    ).drop("endtime").drop_nulls(["pm10", "datetime"])

    # Filter obvious sensor errors
    df = df.filter(pl.col("pm10") < 2000)

    return df.sort("datetime")


def fetch_recent_from_api(start: date, end: date, station_id: str) -> pl.DataFrame:
    """Fetch recent data from per-day API (for current year not yet in bulk CSV)."""
    import json
    import time

    rows = []
    client = httpx.Client()
    try:
        d = start
        total_days = (end - start).days + 1
        fetched = 0
        while d <= end:
            try:
                url = f"{UST_API_BASE}/getDate/date/{d.isoformat()}"
                resp = client.get(url, timeout=30)
                data = resp.json()
                station_data = data.get(station_id, {})
                if isinstance(station_data, dict):
                    pm10 = station_data.get("parameters", {}).get("PM10", {})
                    for k, v in pm10.items():
                        if isinstance(v, dict) and "value" in v:
                            try:
                                rows.append({
                                    "datetime": v["endtime"],
                                    "pm10": float(v["value"]),
                                })
                            except (ValueError, TypeError):
                                continue
            except Exception as e:
                print(f"    Warning: failed {d}: {e}")
            fetched += 1
            if fetched % 30 == 0:
                print(f"    API: {fetched}/{total_days} days...")
            d += timedelta(days=1)
            time.sleep(0.15)
    finally:
        client.close()

    if not rows:
        return pl.DataFrame(schema={"datetime": pl.Datetime, "pm10": pl.Float64})

    df = pl.DataFrame(rows)
    df = df.with_columns(pl.col("datetime").str.to_datetime("%Y-%m-%d %H:%M:%S"))
    # Filter obvious sensor errors (PM10 > 2000 µg/m³ is not physically plausible)
    df = df.filter(pl.col("pm10") < 2000)
    return df.select("datetime", "pm10").sort("datetime")


def fetch_all_pm10() -> pl.DataFrame:
    """Fetch PM10 data: bulk CSVs for past years + API for current year."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    current_year = date.today().year
    all_dfs = []

    # Bulk CSVs for complete years
    for year in range(START_YEAR, current_year):
        try:
            csv_path = download_annual_csv(year)
            traffic = load_pm10_from_csv(csv_path, STATION_ID)
            bg = load_pm10_from_csv(csv_path, BG_STATION_ID)

            if not traffic.is_empty():
                if not bg.is_empty():
                    bg = bg.rename({"pm10": "pm10_background"})
                    traffic = traffic.join(bg, on="datetime", how="left")
                else:
                    traffic = traffic.with_columns(pl.lit(None).cast(pl.Float64).alias("pm10_background"))
                all_dfs.append(traffic)
                print(f"    {year}: {len(traffic)} hourly PM10 readings")
        except Exception as e:
            print(f"    Warning: failed to load {year}: {e}")

    # Check which years actually produced data from CSV
    years_with_data = set()
    for df in all_dfs:
        if not df.is_empty():
            years = df["datetime"].dt.year().unique().to_list()
            years_with_data.update(years)

    for api_year in range(START_YEAR, current_year + 1):
        if api_year in years_with_data:
            continue
        start_of_year = date(api_year, 1, 1)
        end_of_year = min(date(api_year, 12, 31), date.today() - timedelta(days=1))
        if start_of_year > end_of_year:
            continue
        print(f"  Fetching {api_year} from daily API ({start_of_year} to {end_of_year})...")

        traffic = fetch_recent_from_api(start_of_year, end_of_year, STATION_ID)
        if not traffic.is_empty():
            bg = fetch_recent_from_api(start_of_year, end_of_year, BG_STATION_ID)
            if not bg.is_empty():
                bg = bg.rename({"pm10": "pm10_background"})
                traffic = traffic.join(bg, on="datetime", how="left")
            else:
                traffic = traffic.with_columns(pl.lit(None).cast(pl.Float64).alias("pm10_background"))
            all_dfs.append(traffic)
            print(f"    {api_year}: {len(traffic)} hourly PM10 readings")

    if not all_dfs:
        return pl.DataFrame(
            schema={"datetime": pl.Datetime, "pm10": pl.Float64, "pm10_background": pl.Float64}
        )

    # Ensure consistent column order before concat
    standardized = []
    for df in all_dfs:
        if "pm10_background" not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("pm10_background"))
        standardized.append(df.select("datetime", "pm10", "pm10_background"))

    return pl.concat(standardized).sort("datetime")


def aggregate_daily(hourly: pl.DataFrame) -> pl.DataFrame:
    """Aggregate hourly PM10 to daily stats."""
    return (
        hourly.with_columns(pl.col("datetime").dt.date().alias("date"))
        .group_by("date")
        .agg(
            pl.col("pm10").mean().round(1).alias("pm10_avg"),
            pl.col("pm10").max().alias("pm10_max"),
            pl.col("pm10").min().alias("pm10_min"),
            pl.col("pm10").count().alias("pm10_hours"),
            pl.col("pm10_background").mean().round(1).alias("pm10_bg_avg"),
        )
        .filter(pl.col("pm10_hours") >= 12)  # Require 12+ hours for valid daily avg
        .sort("date")
    )


def fetch_wind_data(start: date, end: date) -> pl.DataFrame:
    """Fetch daily wind speed and precipitation from Open-Meteo."""
    all_dfs = []
    chunk_start = start

    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=365), end)
        url = (
            f"{OPEN_METEO_BASE}?latitude=64.13&longitude=-21.90"
            f"&start_date={chunk_start.isoformat()}&end_date={chunk_end.isoformat()}"
            f"&daily=wind_speed_10m_max,wind_speed_10m_mean,precipitation_sum,temperature_2m_mean"
            f"&timezone=Atlantic/Reykjavik"
        )
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        if daily and daily.get("time"):
            df = pl.DataFrame(
                {
                    "date": daily["time"],
                    "wind_max": daily.get("wind_speed_10m_max"),
                    "wind_mean": daily.get("wind_speed_10m_mean"),
                    "precip_mm": daily.get("precipitation_sum"),
                    "temp_mean": daily.get("temperature_2m_mean"),
                }
            )
            df = df.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
            all_dfs.append(df)

        chunk_start = chunk_end + timedelta(days=1)

    if not all_dfs:
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "wind_max": pl.Float64,
                "wind_mean": pl.Float64,
                "precip_mm": pl.Float64,
                "temp_mean": pl.Float64,
            }
        )
    return pl.concat(all_dfs).sort("date")


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching PM10 data from UST...")
    hourly = fetch_all_pm10()
    print(f"  Total: {len(hourly)} hourly readings")

    if len(hourly) == 0:
        print("  No data retrieved. Exiting.")
        return

    daily = aggregate_daily(hourly)
    print(f"  {len(daily)} valid daily records")

    end = date.today() - timedelta(days=1)
    start = date(START_YEAR, 1, 1)

    print("Fetching wind/weather data from Open-Meteo...")
    wind = fetch_wind_data(start, end)
    print(f"  {len(wind)} daily weather records")

    # Join PM10 + weather
    combined = daily.join(wind, on="date", how="left")

    # Add derived columns
    combined = combined.with_columns(
        pl.col("date").dt.year().alias("year"),
        pl.col("date").dt.month().alias("month"),
        (pl.col("pm10_avg") > 50).alias("exceeds_eu_limit"),
    )

    out = PROCESSED_DIR / "reykjavik_pm10_daily.csv"
    combined.write_csv(out)
    print(f"  Wrote {out}")

    # Summary stats
    for year in sorted(combined["year"].unique().to_list()):
        yr = combined.filter(pl.col("year") == year)
        exceed = yr.filter(pl.col("exceeds_eu_limit")).height
        max_val = yr["pm10_max"].max()
        print(f"  {year}: {len(yr)} days, {exceed} days >50µg/m³, max={max_val}µg/m³")


if __name__ == "__main__":
    main()

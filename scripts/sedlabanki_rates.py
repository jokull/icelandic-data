"""
Fetch Central Bank of Iceland (Seðlabanki) interest rate history from gagnabanki.is.

Uses Playwright to load the Power BI embedded report and intercept query responses.
The gagnabanki.is portal wraps Power BI reports; data is extracted from the DSR
(DataShapeResult) format returned by Power BI's internal querydata endpoint.

Usage:
    uv run python scripts/sedlabanki_rates.py              # Fetch & save to CSV
    uv run python scripts/sedlabanki_rates.py --json        # Output JSON to stdout
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

EMBED_URL = "https://gagnabanki.is/report/interests"


def parse_pbi_timeseries(responses: list[dict]) -> list[dict]:
    """Parse Power BI DSR responses into flat records.

    gagnabanki.is wraps Power BI reports. The interest rate report returns
    two key query responses:
    1. A "legend" query: series names in ValueDicts.D0
    2. A "data" query: dates (G0 as ms epoch) + values in X[].C[]

    Data query DM0 structure:
      { G0: epoch_ms, X: [ {C: [value, format], I: slot_idx}, ... ] }
      R bitmask: bit 1 = G0 repeats from previous row
      Ø field: null/skip marker for a slot
    """
    series_names = []
    data_response = None

    for resp in responses:
        if "results" not in resp:
            continue
        for r in resp["results"]:
            data = r.get("result", {}).get("data", {})
            dsr = data.get("dsr", {})
            desc = data.get("descriptor", {})

            for ds in dsr.get("DS", []):
                vd = ds.get("ValueDicts", {})

                if "D0" in vd and len(vd["D0"]) > 2:
                    series_names = vd["D0"]

                select = desc.get("Select", [])
                has_calendar = any(
                    s.get("GroupKeys", [{}])[0]
                    .get("Source", {})
                    .get("Entity")
                    == "Calendar"
                    for s in select
                    if s.get("GroupKeys")
                )
                ph_list = ds.get("PH", [])
                for ph in ph_list:
                    dm0 = ph.get("DM0", [])
                    if has_calendar and len(dm0) > 50:
                        data_response = (ds, dm0, desc)

    if not series_names:
        print("ERROR: Could not find series names in responses", file=sys.stderr)
        return []

    if not data_response:
        print("ERROR: Could not find data query response", file=sys.stderr)
        return []

    ds, dm0_list, desc = data_response

    # Determine series-to-slot mapping via SH (secondary hierarchy)
    sh = ds.get("SH", [])
    slot_series = []
    if sh:
        for sh_entry in sh:
            dm1 = sh_entry.get("DM1", [])
            for item in dm1:
                c = item.get("C", [])
                if c and isinstance(c[0], int) and c[0] < len(series_names):
                    slot_series.append(series_names[c[0]])
                elif "G0" in item and isinstance(item["G0"], int) and item["G0"] < len(series_names):
                    slot_series.append(series_names[item["G0"]])

    if not slot_series:
        # Default: first 3 series (Meginvextir, daglánum, viðskiptareikningum)
        slot_series = series_names[:3]

    print(f"  Series: {slot_series}", file=sys.stderr)

    # Parse DM0 rows
    rows = []
    prev_date = None

    for dm in dm0_list:
        if "G0" in dm:
            try:
                dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                    milliseconds=dm["G0"]
                )
                prev_date = dt.strftime("%Y-%m-%d")
            except (OverflowError, ValueError, OSError):
                continue
        elif not (dm.get("R", 0) & 1):
            continue

        if prev_date is None:
            continue

        slot_idx = 0
        for x_entry in dm.get("X", []):
            if "I" in x_entry:
                slot_idx = x_entry["I"]

            if "\u00d8" in x_entry:
                slot_idx += 1
                continue

            c = x_entry.get("C", [])
            value = None
            if c:
                val_str = str(c[0]).rstrip("Dd")
                try:
                    value = float(val_str)
                except ValueError:
                    pass
            elif "M0" in x_entry:
                value = x_entry["M0"]

            if value is not None:
                series_name = (
                    slot_series[slot_idx]
                    if slot_idx < len(slot_series)
                    else f"Unknown_{slot_idx}"
                )
                rows.append({"date": prev_date, "series": series_name, "value": value})

            slot_idx += 1

    return rows


async def fetch_interest_rates() -> list[dict]:
    """Load gagnabanki.is interest rates page and intercept Power BI data."""
    from playwright.async_api import async_playwright

    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def handle_response(response):
            url = response.url
            if (
                "wabi" in url.lower()
                or "analysis.windows.net" in url.lower()
                or "pbidedicated" in url.lower()
            ):
                try:
                    body = await response.json()
                    captured.append(body)
                except Exception:
                    pass

        page.on("response", handle_response)

        print("Loading gagnabanki.is interest rates...", file=sys.stderr)
        await page.goto(EMBED_URL, wait_until="domcontentloaded", timeout=60000)

        # Poll until data-bearing responses arrive or timeout (90s)
        for i in range(45):
            await page.wait_for_timeout(2000)
            has_data = any(
                r.get("results", [{}])[0]
                .get("result", {})
                .get("data", {})
                .get("dsr", {})
                .get("DS", [{}])[0]
                .get("PH", [{}])[0]
                .get("DM0", [])
                for r in captured
                if "results" in r
            )
            if has_data:
                # Wait for any remaining queries
                await page.wait_for_timeout(5000)
                break
        else:
            print("WARNING: Timed out waiting for data (90s)", file=sys.stderr)

        await browser.close()

    if not captured:
        print("ERROR: No Power BI responses captured.", file=sys.stderr)
        return []

    rows = parse_pbi_timeseries(captured)
    print(f"Fetched {len(rows)} data points", file=sys.stderr)
    return rows


def save_csv(rows: list[dict], path: Path):
    """Save rows to CSV using polars."""
    import polars as pl

    df = pl.DataFrame(rows)
    df = df.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
    df = df.sort(["series", "date"])

    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(path)
    print(f"Wrote {len(df)} rows to {path}", file=sys.stderr)

    for series in df["series"].unique().sort().to_list():
        subset = df.filter(pl.col("series") == series)
        latest = subset.sort("date").tail(1)
        print(
            f"  {series}: {len(subset)} pts, latest {latest['date'][0]} = {latest['value'][0]}%",
            file=sys.stderr,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write fetched rows as JSON to stdout instead of saving CSV.",
    )
    args = parser.parse_args()

    rows = asyncio.run(fetch_interest_rates())
    if not rows:
        sys.exit(1)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        out_path = PROCESSED_DIR / "sedlabanki_rates.csv"
        save_csv(rows, out_path)


if __name__ == "__main__":
    main()

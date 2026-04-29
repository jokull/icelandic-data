"""
Ferðamálastofa — Tourism dashboard data extraction via Power BI scraping.

Intercepts Power BI executeQueries responses from the embedded dashboards
at maelabordferdathjonustunnar.is using Playwright.

Usage:
    uv run python scripts/ferdamalastofa.py passengers   # Keflavík passenger data
    uv run python scripts/ferdamalastofa.py hotels        # Hotel occupancy
    uv run python scripts/ferdamalastofa.py stays         # Length of stay
    uv run python scripts/ferdamalastofa.py list          # Show available dashboards
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

import polars as pl

BASE_URL = "https://www.maelabordferdathjonustunnar.is"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "ferdamalastofa"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

DASHBOARDS = {
    "passengers": {
        "path": "/fjoldi-farthega-um-keflavik",
        "report_id": "1fa56a04-3340-46c5-a36b-f9dde4ce0b92",
        "description": "Passenger counts by nationality through Keflavík",
    },
    "hotels": {
        "path": "/hotel",
        "report_id": "34af65b4-b68d-4309-a17a-5e9d4632b55c",
        "description": "Hotel guest nights and occupancy",
    },
    "accommodation": {
        "path": "/allir-gististadir",
        "report_id": "7cf5f866-459c-4873-947c-082d8a216ea9",
        "description": "All accommodation types",
    },
    "stays": {
        "path": "/dvalarlengd-og-gistimati",
        "report_id": "ae74ab2c-4b1a-4a5c-bf4f-a8ffdda1801f",
        "description": "Length of stay and accommodation type",
    },
}


# ---------------------------------------------------------------------------
# Power BI DSR decompression
# ---------------------------------------------------------------------------

def decompress_dsr(dsr_data: dict) -> list[dict]:
    """Decompress Power BI DSR format with ValueDicts and repeat flags.

    Power BI compresses data by:
    1. ValueDicts: shared string arrays referenced by index (C field)
    2. R (repeat): bitmask indicating which G values repeat from previous row
    3. Ø (null): marks null/missing values
    """
    value_dicts = dsr_data.get("ValueDicts", {})
    all_rows = []

    for ds in dsr_data.get("DS", []):
        # Column metadata
        col_info = []
        for sh in ds.get("SH", []):
            for dm_def in sh.get("DM1", sh.get("DM0", [])):
                s_items = dm_def.get("S", [])
                for s in s_items:
                    col_info.append(s)

        for ph in ds.get("PH", []):
            dm = ph.get("DM0", ph.get("DM1", []))
            prev_values = {}

            for row in dm:
                current = {}
                repeat_mask = row.get("R", 0)

                # Resolve G (group/dimension) values
                for i in range(10):
                    key = f"G{i}"
                    if key in row:
                        current[key] = row[key]
                        prev_values[key] = row[key]
                    elif repeat_mask & (1 << i) and key in prev_values:
                        current[key] = prev_values[key]

                # Resolve C (compressed dict reference) values
                if "C" in row:
                    for idx, val in enumerate(row["C"]):
                        dict_key = f"D{idx}"
                        if dict_key in value_dicts and isinstance(val, int):
                            try:
                                current[f"C{idx}"] = value_dicts[dict_key][val]
                            except IndexError:
                                current[f"C{idx}"] = val
                        else:
                            current[f"C{idx}"] = val

                # Extract X (measure) values
                for xi, x in enumerate(row.get("X", [])):
                    if isinstance(x, dict):
                        for mk, mv in x.items():
                            current[f"X{xi}_{mk}"] = mv
                    else:
                        current[f"X{xi}"] = x

                # Extract Ø (null markers)
                if "Ø" in row:
                    current["_null_mask"] = row["Ø"]

                all_rows.append(current)

    return all_rows


def extract_queries_from_results(raw_results: list[dict]) -> list[dict]:
    """Parse Power BI query responses and decompress DSR data."""
    all_tables = []

    for result in raw_results:
        data = result.get("data", {})

        # Handle top-level results array
        results_list = data.get("results", [])
        if not results_list and "result" in data:
            results_list = [data]

        for res in results_list:
            dsr = res.get("result", {}).get("data", {}).get("dsr", {})
            if not dsr:
                continue

            rows = decompress_dsr(dsr)
            if rows:
                all_tables.append({
                    "url": result.get("url", ""),
                    "rows": rows,
                    "dsr": dsr,  # Keep for debugging
                })

    return all_tables


# ---------------------------------------------------------------------------
# Playwright scraping
# ---------------------------------------------------------------------------

async def scrape_dashboard(page_path: str, wait_seconds: int = 15) -> list[dict]:
    """Load a dashboard page and intercept Power BI data responses."""
    from playwright.async_api import async_playwright

    query_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            # Power BI data goes through querydata or public/reports endpoints
            if any(kw in url.lower() for kw in ["querydata", "public/reports", "executeQueries"]):
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            query_results.append({"url": url, "data": body})
                except Exception:
                    pass

        page.on("response", handle_response)

        url = f"{BASE_URL}{page_path}"
        print(f"  Loading {url} ...")
        await page.goto(url, wait_until="networkidle", timeout=60000)

        # Power BI reports load async — wait for data queries to complete
        print(f"  Waiting {wait_seconds}s for Power BI data...")
        await asyncio.sleep(wait_seconds)

        await browser.close()

    return query_results


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list():
    """Show available dashboards."""
    print("Available dashboards:\n")
    for key, info in DASHBOARDS.items():
        print(f"  {key:15s}  {info['description']}")
        print(f"  {'':15s}  {BASE_URL}{info['path']}")
        print()


def cmd_scrape(dashboard_key: str):
    """Scrape a specific dashboard."""
    if dashboard_key not in DASHBOARDS:
        print(f"Unknown dashboard: {dashboard_key}")
        print(f"Available: {', '.join(DASHBOARDS.keys())}")
        return

    info = DASHBOARDS[dashboard_key]
    print(f"Scraping: {info['description']}")

    # Run Playwright
    raw_results = asyncio.run(scrape_dashboard(info["path"]))

    if not raw_results:
        print("  No Power BI data intercepted.")
        print("  This may mean the page structure changed or the report didn't load.")
        print("  Try increasing wait time or check the URL manually.")
        return

    print(f"  Intercepted {len(raw_results)} API responses")

    # Save raw responses
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    raw_path = RAW_DIR / f"{dashboard_key}_{ts}.json"
    raw_path.write_text(
        json.dumps(raw_results, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"  Raw JSON: {raw_path}")

    # Parse and decompress
    tables = extract_queries_from_results(raw_results)
    print(f"  Extracted {len(tables)} data tables")

    for i, table in enumerate(tables):
        rows = table["rows"]
        if not rows:
            continue

        df = pl.DataFrame(rows, infer_schema_length=len(rows))
        print(f"\n  Table {i}: {len(df)} rows, {len(df.columns)} columns")
        print(f"    Columns: {df.columns}")

        # Save each table
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        out = PROCESSED_DIR / f"ferdamalastofa_{dashboard_key}_t{i}.csv"
        df.write_csv(out)
        print(f"    Saved: {out}")

    # Summary
    total_rows = sum(len(t["rows"]) for t in tables)
    print(f"\n  Total: {total_rows} rows across {len(tables)} tables")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ferðamálastofa tourism dashboard data extraction"
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="Show available dashboards")
    sub.add_parser("passengers", help="Scrape passenger data")
    sub.add_parser("hotels", help="Scrape hotel data")
    sub.add_parser("accommodation", help="Scrape accommodation data")
    sub.add_parser("stays", help="Scrape length-of-stay data")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "passengers": lambda: cmd_scrape("passengers"),
        "hotels": lambda: cmd_scrape("hotels"),
        "accommodation": lambda: cmd_scrape("accommodation"),
        "stays": lambda: cmd_scrape("stays"),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

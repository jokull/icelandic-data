"""
Lánamál ríkisins — Icelandic government bond market data (lanamal.is).

RIKB (non-indexed) and RIKS (indexed) government bond yields, prices and the
daily-fixing history from the public JSON API documented in
.agents/skills/lanamal/SKILL.md. No auth; a browser-like User-Agent plus a
Referer pointing at the matching /markadsyfirlit page are required; responses
are UTF-16 JSON (httpx decodes from the BOM automatically).

Read the daily chartData fixing, not the top-level closingYield: these bonds
trade thinly (tradeCount can be 0 for the whole lookback) and closingYield
reflects the last actual trade, which can be stale — chartData's last point is
the market-maker's end-of-day fixing, updated every business day.

Usage:
    uv run python scripts/lanamal.py list
    uv run python scripts/lanamal.py fetch                # all catalog bonds
    uv run python scripts/lanamal.py fetch --orderbook RIKB_31_0124
"""

import argparse
import re
from datetime import datetime
from pathlib import Path

import httpx
import polars as pl

BASE = "https://www.lanamal.is"
DETAIL_URL = f"{BASE}/api/market/LoadIndexedDetail"
MARKET_URL = f"{BASE}/markadsyfirlit/?type=bond"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "lanamal"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
OUT_FILE = PROCESSED_DIR / "lanamal.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; icelandic-data-lanamal/1.0)",
    "Accept": "application/json",
}

# Known outstanding series as of 2026-08 — see the bond catalog in SKILL.md.
# Drifts as bonds mature and new ones auction; `list` rescans the market page
# for the live catalog, and this table is only the offline fallback.
CATALOG = [
    "RIKB_26_1015", "RIKB_27_0415", "RIKB_28_1115", "RIKB_29_0416",
    "RIKB_31_0124", "RIKB_35_0917", "RIKB_38_0215", "RIKB_42_0217",
    "RIKS_29_0917", "RIKS_30_0701", "RIKS_33_0321", "RIKS_37_0115", "RIKS_50_0915",
]


def list_orderbooks(client: httpx.Client) -> list[str]:
    """Rescan the /markadsyfirlit page for live orderbook ids (fallback: CATALOG).

    The page lists a bond link per outstanding series
    (href="/markadsyfirlit/?type=bond&orderbookid=...").
    """
    r = client.get(MARKET_URL, headers=HEADERS)
    r.raise_for_status()
    ids = re.findall(r"orderbookid=([a-z0-9_]+)", r.text, re.IGNORECASE)
    ids = list(dict.fromkeys(i.upper() for i in ids))  # dedupe, preserve order
    return ids or list(CATALOG)


def fetch_bond(client: httpx.Client, orderbook_id: str) -> tuple[pl.DataFrame, bytes]:
    """One bond's daily-fixing series as long rows (orderbook, date, yield).

    Returns (df, raw_response_bytes) — the raw bytes are UTF-16 JSON, saved
    verbatim to data/raw/ as received.
    """
    r = client.get(
        DETAIL_URL,
        params={"orderbookId": orderbook_id, "lang": "is"},
        headers={**HEADERS, "Referer": f"{MARKET_URL}&orderbookid={orderbook_id.lower()}"},
    )
    r.raise_for_status()
    record = r.json()[0]
    chart = record["chartData"]["chartData"]  # [[iso_datetime, yield_pct], ...] ascending
    if not chart:
        return (
            pl.DataFrame(
                schema={"orderbook_id": pl.Utf8, "short_name": pl.Utf8, "isin": pl.Utf8,
                        "date": pl.Date, "yield_pct": pl.Float64}
            ),
            r.content,
        )
    isin = next(
        (a["value"] for a in record.get("attributes", []) if a.get("name") == "ISIN númer"),
        None,
    )
    rows = [
        {
            "orderbook_id": record["orderbookId"],
            "short_name": record.get("shortName"),
            "isin": isin,
            "date": datetime.fromisoformat(pt[0]).date(),
            "yield_pct": float(pt[1]),
        }
        for pt in chart
    ]
    return pl.DataFrame(rows), r.content


def cmd_list(args) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        ids = list_orderbooks(client)
    print(f"{len(ids)} orderbooks found on {MARKET_URL}:")
    for i in ids:
        print(f"  {i}")
    print("\n(Catalog drifts — bonds mature and new ones auction. Re-run `list` if a fetch 404s.)")


def cmd_fetch(args) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        orderbooks = args.orderbook or list_orderbooks(client)
        frames = []
        for i, orderbook_id in enumerate(orderbooks, 1):
            print(f"  [{i}/{len(orderbooks)}] {orderbook_id} ...")
            try:
                df, raw = fetch_bond(client, orderbook_id)
            except Exception as exc:
                print(f"    failed: {exc}")
                continue
            (RAW_DIR / f"{orderbook_id.lower()}.json").write_bytes(raw)
            frames.append(df)
            if not df.is_empty():
                last = df.sort("date").tail(1).row(0, named=True)
                print(f"    {len(df)} daily fixings, latest {last['date']}: {last['yield_pct']}%")

    if not frames:
        print("No bond data fetched.")
        return
    df = pl.concat(frames, how="diagonal_relaxed").unique(
        subset=["orderbook_id", "date"], keep="last"
    ).sort(["orderbook_id", "date"])
    df.write_csv(OUT_FILE)
    print(f"{len(df)} rows written -> {OUT_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List outstanding bond orderbooks (live scan of /markadsyfirlit)")
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="Fetch daily-fixing yield series for bond orderbooks -> data/processed/lanamal.csv")
    p_fetch.add_argument(
        "--orderbook", action="append", default=[],
        help="Orderbook id(s) to fetch (repeatable); default: every catalog bond",
    )
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

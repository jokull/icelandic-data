"""Long-run Iceland housing completions series, combining:

- Hagstofan IDN03001 (1970–2021) — annual completions via PX-Web API
- HMS húsnæðisáætlanir report (2020–2025) — annual completions from sheet 2.1

Hagstofan stopped updating IDN03001 after 2021; HMS now runs quarterly
íbúðatalningar (field counts of housing under construction) and publishes
the annual figures in the yearly húsnæðisáætlanir report.

The 2020–2021 overlap matches within ~30 units, so the two series are the
same measurement with minor revision.

Output: data/processed/iceland_housing_completions.csv

Usage:
    uv run python scripts/housing_completions.py                        # fetch Hagstofan + build
    uv run python scripts/housing_completions.py fetch --use-cached     # reuse cached raw fetch

HMS 2020–2025 figures are HARDCODED in HMS_COMPLETIONS (see --help); update
them annually when HMS publishes the next housing plan report.
"""

import argparse
import sys
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / "data" / "processed" / "iceland_housing_completions.csv"
RAW_HAG = ROOT / "data" / "raw" / "hagstofan" / "IDN03001_housing_completions.csv"
HEADERS = {"User-Agent": "icelandic-data/1.0 (data toolkit fetcher)"}

HAGSTOFAN_URL = (
    "https://px.hagstofa.is/pxis/api/v1/is/"
    "Atvinnuvegir/idnadur/byggingar/IDN03001.px"
)

# Query: byggingarstaða=2 (Fullgert á árinu), eining=0 (Fjöldi íbúða)
HAGSTOFAN_QUERY = {
    "query": [
        {"code": "Byggingarstaða", "selection": {"filter": "item", "values": ["2"]}},
        {"code": "Eining", "selection": {"filter": "item", "values": ["0"]}},
    ],
    "response": {"format": "csv"},
}

# HMS annual completions from húsnæðisáætlanir 2026/1 (sheet 2.1)
# These should be updated annually when HMS publishes the next housing plan report.
# Source: data/raw/hms/husnaedisaaetlanir_2025_skyrsla.md (April 2026 publication)
HMS_COMPLETIONS = {
    2020: 3816,
    2021: 3220,
    2022: 2885,
    2023: 3458,
    2024: 3637,
    2025: 3371,
}


def _parse_completions(text: str) -> dict[int, int]:
    """Parse the ISO-8859-1 'YYYY',count CSV body into {year: count}."""
    out = {}
    for line in text.splitlines()[1:]:
        parts = line.replace('"', "").split(",")
        if len(parts) >= 2 and parts[0].isdigit():
            out[int(parts[0])] = int(parts[1])
    return out


def fetch_hagstofan() -> dict[int, int]:
    """Fetch Hagstofan completions 1970–2021 and cache the raw response."""
    resp = httpx.post(HAGSTOFAN_URL, json=HAGSTOFAN_QUERY, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    # CSV uses ISO-8859-1; decode from bytes
    text = resp.content.decode("iso-8859-1")
    RAW_HAG.parent.mkdir(parents=True, exist_ok=True)
    RAW_HAG.write_text(text, encoding="utf-8")
    return _parse_completions(text)


def load_cached_hagstofan() -> dict[int, int]:
    """Read the raw response cached by a previous run."""
    if not RAW_HAG.exists():
        raise FileNotFoundError(
            f"no cached Hagstofan data at {RAW_HAG} — run without --use-cached first"
        )
    return _parse_completions(RAW_HAG.read_text(encoding="utf-8"))


def cmd_fetch(args) -> int:
    if args.use_cached:
        hag = load_cached_hagstofan()
        print(f"Cached Hagstofan IDN03001: {len(hag)} years ({min(hag)}–{max(hag)})")
    else:
        hag = fetch_hagstofan()
        print(f"Hagstofan IDN03001: {len(hag)} years ({min(hag)}–{max(hag)})")

    if not hag:
        print("ERROR: no Hagstofan completions data — nothing written", file=sys.stderr)
        return 1

    # Combine: Hagstofan 1970–2019, HMS 2020–2025 (prefer HMS where overlapping)
    combined = {y: v for y, v in hag.items() if y <= 2019}
    for y, v in HMS_COMPLETIONS.items():
        combined[y] = v

    # Report overlap for sanity
    print("\nOverlap check:")
    for y in [2020, 2021]:
        h, m = hag.get(y), HMS_COMPLETIONS.get(y)
        print(f"  {y}: Hagstofan={h}, HMS={m}, Δ={(m - h) if h and m else 'N/A'}")

    df = pl.DataFrame(
        [
            {
                "year": y,
                "completions": combined[y],
                "source": "Hagstofan IDN03001" if y <= 2019 else "HMS húsnæðisáætlanir",
            }
            for y in sorted(combined)
        ]
    )

    DST.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(DST)
    print(f"\nWrote {len(df)} years to {DST}")

    # Recent summary
    print("\nRecent completions:")
    for row in df.filter(pl.col("year") >= 2015).iter_rows(named=True):
        print(f"  {row['year']}: {row['completions']}  [{row['source']}]")

    total_15_24 = sum(combined[y] for y in range(2015, 2025))
    print(f"\n2015–2024 total: {total_15_24}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        epilog=("NOTE: HMS completions for 2020–2025 are HARDCODED in HMS_COMPLETIONS "
                "from sheet 2.1 of the annual húsnæðisáætlanir report — update them by "
                "hand whenever HMS publishes the next housing plan, or the tail of the "
                "series silently stops moving. Hagstofan IDN03001 froze after 2021."),
    )
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser(
        "fetch",
        help="fetch Hagstofan IDN03001 + HMS → data/processed/iceland_housing_completions.csv",
    )
    f.add_argument(
        "--use-cached",
        action="store_true",
        help="skip the Hagstofan fetch and reuse the raw response cached by a "
             "previous run (data/raw/hagstofan/IDN03001_housing_completions.csv)",
    )
    f.set_defaults(func=cmd_fetch)
    ap.set_defaults(func=cmd_fetch, use_cached=False)  # bare run == fetch (AGENTS.md quick command)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

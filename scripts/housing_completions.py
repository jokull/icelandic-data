"""Long-run Iceland housing completions series, combining:

- Hagstofan IDN03001 (1970–2021) — annual completions via PX-Web API
- HMS húsnæðisáætlanir report (2020–2025) — annual completions from sheet 2.1

Hagstofan stopped updating IDN03001 after 2021; HMS now runs quarterly
íbúðatalningar (field counts of housing under construction) and publishes
the annual figures in the yearly húsnæðisáætlanir report.

The 2020–2021 overlap matches within ~30 units, so the two series are the
same measurement with minor revision.

Output: data/processed/iceland_housing_completions.csv

Usage: uv run python scripts/housing_completions.py
"""

from io import StringIO
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / "data" / "processed" / "iceland_housing_completions.csv"

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


def fetch_hagstofan() -> dict[int, int]:
    """Fetch Hagstofan completions 1970–2021."""
    resp = httpx.post(HAGSTOFAN_URL, json=HAGSTOFAN_QUERY, timeout=30)
    resp.raise_for_status()
    # CSV uses ISO-8859-1; decode from bytes
    text = resp.content.decode("iso-8859-1")
    # First line is header, each row: "YYYY",count
    out = {}
    for line in text.splitlines()[1:]:
        parts = line.replace('"', "").split(",")
        if len(parts) >= 2 and parts[0].isdigit():
            out[int(parts[0])] = int(parts[1])
    return out


def main():
    hag = fetch_hagstofan()
    print(f"Hagstofan IDN03001: {len(hag)} years ({min(hag)}–{max(hag)})")

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


if __name__ == "__main__":
    main()

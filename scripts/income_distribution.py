"""Fetch income distribution data from Hagstofa PX-Web API.

Usage:
    uv run python scripts/income_distribution.py                          # fetch all datasets
    uv run python scripts/income_distribution.py fetch                    # fetch all datasets
    uv run python scripts/income_distribution.py fetch --tables tax_burden income_by_age
"""

import argparse
import hashlib
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hagstofan_query import BASE as PX_BASE  # noqa: E402
from hagstofan_query import document_table, query_filters, record_fetch, write_sidecar  # noqa: E402

BASE = "https://px.hagstofa.is/pxis/api/v1/is/Samfelag/launogtekjur"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
# One sidecar per script, next to the primary output; keyed by table code.
# TEK01001 is fetched four times with different selections — value notes merge.
SIDECAR = OUT / "income_by_source.meta.json"
CLIENT = httpx.Client(timeout=60, headers={"User-Agent": "icelandic-data/1.0"})
TABLE_DOCS: dict = {}


def fetch_table(path: str, query: list[dict] | None = None) -> str:
    """Fetch CSV data from PX-Web API."""
    url = f"{BASE}/{path}"
    body = {"query": query or [], "response": {"format": "csv"}}
    r = CLIENT.post(url, json=body)
    r.raise_for_status()
    # Table documentation (LAST-UPDATED, notes) with the same selection, plus
    # the vintage line in the shared index. A header failure is reported and
    # skipped; it never breaks the data pipeline.
    px_path = url.removeprefix(PX_BASE)
    doc = document_table(CLIENT, px_path, query or [], TABLE_DOCS)
    record_fetch(px_path, query_filters(query or []), "", doc["last_updated"] if doc else None,
                 hashlib.sha256(r.content).hexdigest())
    # API returns UTF-8-BOM; decode properly and strip BOM
    text = r.content.decode("utf-8-sig")
    return text


def fetch_income_by_source():
    """TEK01001: Income by source, age, gender 1990-2024."""
    print("Fetching TEK01001 (income by source)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01001.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": ["0", "Y16-64", "Y25-54"],
                },
            },
            {
                "code": "Eining",
                "selection": {
                    "filter": "item",
                    "values": ["0", "2"],  # Mean-all, Median-all
                },
            },
        ],
    )
    path = OUT / "income_by_source.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


def fetch_income_by_source_gender():
    """TEK01001: Income by source and gender for latest years."""
    print("Fetching TEK01001 (income by source, by gender)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01001.px",
        query=[
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": ["Y25-54"],
                },
            },
            {
                "code": "Eining",
                "selection": {
                    "filter": "item",
                    "values": ["0", "2"],  # Mean-all, Median-all
                },
            },
        ],
    )
    path = OUT / "income_by_source_gender.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


def fetch_income_by_age():
    """TEK01001: Income by source for 5-year age bands."""
    print("Fetching TEK01001 (income by age bands)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01001.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": [
                        "16", "20", "25", "30", "35", "40",
                        "45", "50", "55", "60", "65", "70", "75",
                    ],
                },
            },
            {
                "code": "Eining",
                "selection": {
                    "filter": "item",
                    "values": ["0"],  # Mean-all
                },
            },
        ],
    )
    path = OUT / "income_by_age.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


def fetch_total_income_distribution():
    """TEK01006: Distribution of total income (percentiles) 1990-2024."""
    print("Fetching TEK01006 (total income distribution)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01006.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": ["0", "Y25-54"],
                },
            },
        ],
    )
    path = OUT / "total_income_distribution.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


def fetch_employment_income_distribution():
    """TEK01007: Distribution of employment income (percentiles) 1990-2024."""
    print("Fetching TEK01007 (employment income distribution)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01007.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": ["Total", "Y25-54"],
                },
            },
        ],
    )
    path = OUT / "employment_income_distribution.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


def fetch_tax_burden():
    """TEK01001: All income types + taxes for tax burden analysis."""
    print("Fetching TEK01001 (full tax burden data)...")
    csv = fetch_table(
        "3_tekjur/1_tekjur_skattframtol/TEK01001.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {
                    "filter": "item",
                    "values": [
                        "0", "16", "20", "25", "30", "35", "40",
                        "45", "50", "55", "60", "65", "70", "75",
                        "Y16-64", "Y25-54",
                    ],
                },
            },
            {
                "code": "Eining",
                "selection": {
                    "filter": "item",
                    "values": ["0", "2"],  # Mean-all, Median-all
                },
            },
            # All income types including taxes and disposable
        ],
    )
    path = OUT / "tax_burden.csv"
    path.write_text(csv, encoding="utf-8")
    print(f"  Saved {path}")


# Discoverable dataset catalog (fetch --tables selects from these)
DATASETS = [
    ("income_by_source", fetch_income_by_source, "TEK01001 income by source, age, gender (mean+median)"),
    ("income_by_source_gender", fetch_income_by_source_gender, "TEK01001 income by source × gender"),
    ("income_by_age", fetch_income_by_age, "TEK01001 income by 5-year age bands"),
    ("total_income_distribution", fetch_total_income_distribution, "TEK01006 total income distribution (percentiles)"),
    ("employment_income_distribution", fetch_employment_income_distribution, "TEK01007 employment income distribution (percentiles)"),
    ("tax_burden", fetch_tax_burden, "TEK01001 all income types + taxes"),
]
DATASET_NAMES = [name for name, _, _ in DATASETS]


def cmd_fetch(args) -> int:
    fns = {name: fn for name, fn, _ in DATASETS}
    for name in args.tables:
        fns[name]()
    # merge=True: a --tables subset must not erase the other tables' entries
    write_sidecar(SIDECAR, TABLE_DOCS, merge=True)
    print(f"  Saved {SIDECAR} ({len(TABLE_DOCS)} tables documented this run)")
    print("Done!")
    return 0


def cmd_list(args) -> int:
    """Print the datasets this script can fetch."""
    print("Hagstofan income-distribution datasets:")
    for name, _, desc in DATASETS:
        print(f"  {name:<32} {desc}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    l = sub.add_parser("list", help="list the datasets this script can fetch")
    l.set_defaults(func=cmd_list)
    f = sub.add_parser(
        "fetch",
        help="fetch income-distribution CSVs → data/processed/ (default: all datasets)",
    )
    f.add_argument(
        "--tables",
        nargs="*",
        choices=DATASET_NAMES,
        default=DATASET_NAMES,
        metavar="TABLE",
        help="datasets to fetch (default: all six)",
    )
    f.set_defaults(func=cmd_fetch)
    ap.set_defaults(func=cmd_fetch, tables=DATASET_NAMES)  # bare run == fetch all (AGENTS.md quick command)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

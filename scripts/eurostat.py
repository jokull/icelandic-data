"""Eurostat (Statistical Office of the EU) — official REST dissemination API.

Fetches any public Eurostat dataset to tidy CSV. This is the canonical way to
get euro-area / EU statistics (wages, HICP inflation, GDP, unemployment...)
and it needs no authentication and no third-party package — the pypi
`eurostat` wrapper is a thin, low-activity shim over the same API and `dlt` is
overkill for a couple of datasets.

Endpoint:
    https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{code}

Responses are json-stat2. This script flattens them to long-format rows
(dimension labels + value). Filters are passed as repeatable `--filter KEY=VALUE` arguments. The API
accepts single code values per dimension (codes are case-insensitive); the
`time` dimension cannot be range-filtered server-side — fetch the series and
slice locally (duckdb/polars) when you need a window. `list` shows the curated
datasets this repo cares about.

Usage:
    uv run python scripts/eurostat.py list
    uv run python scripts/eurostat.py fetch prc_hicp_midx --filter geo=EA20 --filter coicop=CP00 --filter unit=I15
    uv run python scripts/eurostat.py fetch lc_lci_lev --filter geo=EA20 --filter nace_r2=B-S --filter lcstruct=D11 --filter unit=EUR
    uv run python scripts/eurostat.py fetch lc_lci_lev --filter geo=EA20 --filter nace_r2=B-S --filter lcstruct=D11 --filter unit=EUR --filter time=2015-2025 --out /tmp/lci.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "eurostat"

# Curated catalog: datasets this repo actually uses, with their key dimensions.
# Codes/labels below are verified against the live API.
DATASETS = {
    "prc_hicp_midx": {
        "title": "HICP — monthly index (unit I15 = 2015=100, I05 = 2005=100, I96 = 1996=100)",
        "dims": "coicop (CP00 = all items), geo, unit, time (monthly)",
    },
    "prc_hicp_manr": {
        "title": "HICP — monthly rate of change (unit RCH_A = annual rate, RCH_M = monthly rate)",
        "dims": "coicop (CP00 = all items), geo, unit, time (monthly)",
    },
    "lc_lci_lev": {
        "title": "Labour cost levels, annual (lcstruct D11 = wages & salaries, D12 = employer social contributions; € per hour)",
        "dims": "nace_r2 (B-S = industry, construction & services), lcstruct, unit (EUR), time (annual)",
    },
    "earn_gr_nace": {
        "title": "Earnings — quarterly index by NACE (worktime FT/PT/TOT_FTE)",
        "dims": "nace_r1, sex, worktime, currency, time (quarterly)",
    },
    "namq_10_lp_ulc": {
        "title": "Labour productivity & unit labour costs, quarterly (na_item RLPR_*, NULC_*)",
        "dims": "na_item, s_adj, unit, time (quarterly)",
    },
}


def get_json(code: str, filters: dict[str, str], retries: int = 3) -> dict:
    params = {"format": "JSON", **{k: v for k, v in filters.items() if v}}
    url = f"{BASE}/{code}"
    for attempt in range(retries):
        try:
            r = httpx.get(url, params=params, timeout=60, follow_redirects=True)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def json_stat_to_long(js: dict) -> pl.DataFrame:
    """Flatten a json-stat2 response to long-format rows.

    `.dimension.<d>.category.index` maps code -> position; `.label` maps
    position -> human label. `.value` keys are row-major composite indices
    over the dimensions in object order (first dimension varies fastest).
    Absent keys are missing values.
    """
    dims = list(js["dimension"].keys())
    sizes = js.get("size") or [len(js["dimension"][d]["category"]["index"]) for d in dims]
    cat = js["dimension"]
    # position -> code, for reconstructing codes from the composite index
    pos_to_code: dict[str, dict[int, str]] = {}
    code_to_label: dict[str, dict[str, str]] = {}
    for d in dims:
        idx = cat[d]["category"]["index"]
        pos_to_code[d] = {int(v): k for k, v in idx.items()}
        code_to_label[d] = {k: cat[d]["category"]["label"].get(str(v), k)
                            for k, v in idx.items()}
    label = {d: cat[d]["category"]["label"] for d in dims}

    rows: list[dict] = []
    for key, val in js.get("value", {}).items():
        p = int(key)
        rec: dict = {}
        for d in dims:
            i = p % sizes[dims.index(d)] if sizes else 0
            p //= sizes[dims.index(d)] if sizes else 1
            lbl = label[d].get(str(i))
            rec[d] = lbl if lbl is not None else pos_to_code[d].get(i, "")
        rec["value"] = val
        rows.append(rec)
    return pl.DataFrame(rows)


def cmd_list(_args=None):
    for code, meta in DATASETS.items():
        print(f"{code}\n    {meta['title']}\n    dims: {meta['dims']}")
    print("\nAny other public dataset code also works: fetch CODE --filter KEY=VALUE ...")
    print("Codes are case-insensitive; slice the time window client-side.")


def cmd_fetch(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filters = {}
    for kv in args.filter or []:
        k, sep, v = kv.partition("=")
        if not sep:
            raise SystemExit(f"--filter must be KEY=VALUE, got {kv!r}")
        filters[k.strip()] = v.strip()
    print(f"Fetching {args.dataset} {filters}", file=sys.stderr)
    js = get_json(args.dataset, filters)
    df = json_stat_to_long(js)
    out = Path(args.out) if args.out else RAW_DIR / f"{args.dataset}.csv"
    df.write_csv(out)
    print(f"→ {out} ({df.height} rows × {df.width} cols)", file=sys.stderr)
    print(df.head(3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl_ = sub.add_parser("list", help="curated Eurostat datasets used in this repo")
    pl_.set_defaults(func=cmd_list)

    pf = sub.add_parser("fetch", help="fetch a dataset to tidy CSV")
    pf.add_argument("dataset", help="dataset code, e.g. prc_hicp_midx")
    pf.add_argument("--filter", action="append", metavar="KEY=VALUE",
                    help="dimension filter, repeatable, e.g. --filter geo=EA20 --filter unit=I15")
    pf.add_argument("--out", help="output CSV path (default data/raw/eurostat/{dataset}.csv)")
    pf.set_defaults(func=cmd_fetch)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

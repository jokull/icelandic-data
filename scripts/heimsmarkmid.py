"""Heimsmarkmið — Iceland's UN Sustainable Development Goal statistics.

heimsmarkmidin.hagstofa.is is an open-sdg instance; the underlying data repo
is a GitHub Pages site serving per-indicator CSV + JSON files plus one
`all_indicators.zip` bundle. We download the ZIP once and query it locally.

Usage:
    uv run python scripts/heimsmarkmid.py fetch                 # download + build catalog
    uv run python scripts/heimsmarkmid.py list                  # print catalog
    uv run python scripts/heimsmarkmid.py list --goal 4         # filter to goal 4 indicators
    uv run python scripts/heimsmarkmid.py get 1-1-1             # print data + meta for one indicator
"""
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "heimsmarkmid"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

DATA_BASE = "https://hagstofan.github.io/heimsmarkmid-data-prod"
ZIP_URL = f"{DATA_BASE}/is/zip/all_indicators.zip"

# Each indicator code looks like `1-1-1` or `16-b-1`. Goal is the leading
# integer before the first dash; target/indicator components follow.
_CODE_RE = re.compile(r"^(\d+)-([0-9a-z]+)(?:-(.+))?$")


def fetch_zip(*, force: bool = False) -> Path:
    """Download all_indicators.zip and extract into RAW_DIR. Idempotent."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "all_indicators.zip"
    if zip_path.exists() and not force:
        print(f"  zip already present: {zip_path}", file=sys.stderr)
    else:
        print(f"  downloading {ZIP_URL}", file=sys.stderr)
        with httpx.Client(timeout=60, follow_redirects=True) as c:
            r = c.get(ZIP_URL)
            r.raise_for_status()
            zip_path.write_bytes(r.content)
        print(f"  {len(r.content) // 1024} KB → {zip_path}", file=sys.stderr)

    # Extract into RAW_DIR/is/{data,meta,comb,headline}/*.csv / *.json
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(RAW_DIR)
    return zip_path


def _indicator_csvs() -> list[Path]:
    """Return the list of per-indicator data CSV files inside RAW_DIR."""
    data_dir = RAW_DIR / "data"
    if not data_dir.exists():
        # The ZIP extracts flat — data CSVs sit at RAW_DIR root.
        return sorted(RAW_DIR.glob("*.csv"))
    return sorted(data_dir.glob("*.csv"))


def _load_meta(code: str) -> dict:
    """Fetch the meta JSON for an indicator over HTTP.

    The ZIP bundle does not include meta files — only CSVs. This is by design
    in open-sdg; meta is always live from the data-repo web root.
    """
    url = f"{DATA_BASE}/is/meta/{code}.json"
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = c.get(url)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        return r.json()


def _parse_code(code: str) -> tuple[str, str, str]:
    """Split '16-b-1' → ('16', 'b', '1'). Returns '' for missing parts."""
    m = _CODE_RE.match(code)
    if not m:
        return (code, "", "")
    goal, target, indicator = m.groups()
    return goal, target, indicator or ""


def build_catalog() -> list[dict]:
    """Walk the extracted CSVs and build a catalog row per indicator.

    For each CSV we record:
      - code, goal, target, indicator (parsed)
      - n_rows, first_year, last_year (from the CSV)
      - columns (the non-Year/Value disaggregation columns)
    """
    rows: list[dict] = []
    for csv_path in _indicator_csvs():
        code = csv_path.stem
        goal, target, indicator = _parse_code(code)
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            data_rows = list(reader)
            header = reader.fieldnames or []
        dis_cols = [c for c in header if c not in {"Year", "Value"}]
        years = [int(r["Year"]) for r in data_rows if r.get("Year", "").isdigit()]
        rows.append(
            {
                "code": code,
                "goal": goal,
                "target": target,
                "indicator": indicator,
                "columns": "|".join(dis_cols),
                "n_rows": len(data_rows),
                "first_year": min(years) if years else "",
                "last_year": max(years) if years else "",
            }
        )
    return rows


def cmd_fetch(args):
    fetch_zip(force=args.force)
    catalog = build_catalog()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "heimsmarkmid_catalog.csv"
    cols = ["code", "goal", "target", "indicator", "columns",
            "n_rows", "first_year", "last_year"]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(catalog)
    print(f"wrote {len(catalog)} indicators → {out}", file=sys.stderr)


def _load_catalog() -> list[dict]:
    path = PROCESSED_DIR / "heimsmarkmid_catalog.csv"
    if not path.exists():
        raise SystemExit(f"catalog missing: {path}. Run `fetch` first.")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_list(args):
    rows = _load_catalog()
    if args.goal:
        rows = [r for r in rows if r["goal"] == str(args.goal)]
    for r in rows:
        yr = f"{r['first_year']}-{r['last_year']}" if r["first_year"] else "(no data)"
        cols = r["columns"] or "-"
        print(f"  {r['code']:10} · {r['n_rows']:>4} rows · {yr:11} · {cols}")
    print(f"\n{len(rows)} indicators", file=sys.stderr)


def cmd_get(args):
    code = args.code
    csvs = _indicator_csvs()
    target = next((p for p in csvs if p.stem == code), None)
    if not target:
        raise SystemExit(f"indicator CSV not found: {code}. Run `fetch` first or check the code.")
    print(f"=== {code} ===")
    meta = _load_meta(code)
    if meta:
        print(f"  name       : {meta.get('indicator_name', '').strip()}")
        print(f"  title      : {meta.get('graph_title', '').strip()}")
        print(f"  units      : {meta.get('computation_units', '').strip()}")
        print(f"  coverage   : {meta.get('national_geographical_coverage', '').strip()}")
        print(f"  graph type : {meta.get('graph_type', '').strip()}")
    print(f"\n--- data ({target.name}) ---")
    print(target.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_f = sub.add_parser("fetch", help="Download the ZIP + build catalog.")
    p_f.add_argument("--force", action="store_true", help="Re-download even if ZIP present")
    p_f.set_defaults(func=cmd_fetch)

    p_l = sub.add_parser("list", help="Print the cached catalog.")
    p_l.add_argument("--goal", type=int, help="Filter to one SDG goal (1-17)")
    p_l.set_defaults(func=cmd_list)

    p_g = sub.add_parser("get", help="Print data + meta for one indicator code.")
    p_g.add_argument("code", help="Indicator code, e.g. 1-1-1 or 16-b-1")
    p_g.set_defaults(func=cmd_get)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

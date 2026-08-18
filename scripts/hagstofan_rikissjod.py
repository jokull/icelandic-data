"""Ríkissjóður state-treasury balance — Hagstofan THJ05211 (1980–2025).

Fills the pre-2015 gap in `rikisreikningur.py`: the Fjársýsla API only
publishes state-accounts actuals from 2015, but Hagstofan's one-stop
"Helstu hagstærðir ríkissjóðs" table (THJ05211) carries tekjur / gjöld /
tekjuafgangur / %-of-GDP back to 1980 on the same accounts basis.

Worked example — the financial-crisis deficits (THJ05211, m.kr):

| Year | Tekjur   | Gjöld    | Afkoma     | % af VLF |
|------|---------:|---------:|-----------:|---------:|
| 2008 |  637,571 |  822,128 | **-184,556** | -11.5 |
| 2009 |  564,394 |  678,626 | **-114,232** |  -7.0 |
| 2010 |  541,554 |  642,474 | **-100,920** |  -5.9 |
| 2011 |  591,297 |  708,189 | **-116,892** |  -6.5 |

The 2008 gjöld jump (471 → 822 bn) is ~212 bn of one-off bank-rescue capital
transfers. Basis caveats live in skills/rikisreikningur/SKILL.md.

Sibling tables (see `list`): THJ05221 full ESA accounts 1998–2025;
THJ95200 cash-basis monthly 2004–2014 (month code "0" = annual total).

Usage:
    uv run python scripts/hagstofan_rikissjod.py list
    uv run python scripts/hagstofan_rikissjod.py fetch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://px.hagstofa.is/pxis/api/v1/is"
TABLE = "Efnahagur/fjaropinber/fjarmal_rikissjods/THJ05211.px"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/hagstofan"
PROC = ROOT / "data/processed"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

OUT_CSV = PROC / "rikissjod_balance.csv"

# code -> English column name for the 14 THJ05211 rows (codes are stable;
# labels are only used as a fallback if a row is missing/renamed).
COLUMNS = {
    "0": "tekjur_mkr",
    "1": "gjold_mkr",
    "2": "afkoma_mkr",
    "3": "tekjur_pct_vlf",
    "4": "gjold_pct_vlf",
    "5": "afkoma_pct_vlf",
    "6": "vlf_mkr",
    "7": "medalmannfjoldi",
    "8": "tekjur_real2025_mkr",
    "9": "gjold_real2025_mkr",
    "10": "tekjur_per_capita_real2025_thus_kr",
    "11": "gjold_per_capita_real2025_thus_kr",
    "12": "gjold_real_growth_pct",
    "13": "tekjur_real_growth_pct",
}

SIBLINGS = [
    ("THJ05221.px", "Tekju-, gjalda og fjárstreymisreikningar ríkissjóðs 1998-2025 — full ESA accounts (rekstrartekjur, rekstrarútgjöld, tekjuafgangur)"),
    ("THJ05222.px", "Rekstrarreikningur ríkissjóðs 1998-2025"),
    ("THJ95200.px", "Fjármál ríkissjóðs á greiðslugrunni (cash basis) eftir mánuðum 2004-2014 — month code \"0\" = annual total"),
    ("THJ05281.px", "Peningalegar eignir og skuldir ríkissjóðs 1998-2025"),
]


def post_json(path: str, query: list[dict]) -> dict:
    """POST to PX-Web and return json-stat2 response."""
    url = f"{BASE}/{path}"
    body = {"query": query, "response": {"format": "json-stat2"}}
    for attempt in range(5):
        r = httpx.post(url, json=body, timeout=120)
        if r.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  429, sleeping {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("exhausted retries")


def jsonstat_to_df(js: dict) -> pl.DataFrame:
    """Flatten a json-stat2 response to long-format polars DataFrame."""
    dim_ids = js["id"]
    sizes = js["size"]
    values = js["value"]
    dims = js["dimension"]

    dim_labels: list[list[str]] = []
    for d in dim_ids:
        cat = dims[d]["category"]
        idx = cat["index"]
        if isinstance(idx, dict):
            inv = [None] * len(idx)
            for code, pos in idx.items():
                inv[pos] = code
        else:
            inv = list(idx)
        labels = cat.get("label", {})
        dim_labels.append([labels.get(c, c) for c in inv])

    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    rows = []
    for flat in range(len(values)):
        v = values[flat]
        if v is None:
            continue
        row = {}
        for d, lab in zip(dim_ids, dim_labels):
            pos = (flat // strides[len(row)]) % sizes[len(row)]
            row[d] = lab[pos]
        row["value"] = float(v)
        rows.append(row)
    return pl.DataFrame(rows)


def fetch_balance() -> pl.DataFrame:
    print(f"[1/1] THJ05211 — Helstu hagstærðir ríkissjóðs 1980-2025...")
    meta = httpx.get(f"{BASE}/{TABLE}", timeout=60).json()
    sk = next(v for v in meta["variables"] if v["code"] == "Skipting")
    ar = next(v for v in meta["variables"] if v["code"] == "Ár")
    codes = sk["values"]
    years = ar["values"]  # e.g. "1980".."2025" — enumerate from metadata, not hardcoded

    js = post_json(
        TABLE,
        [
            {"code": "Skipting", "selection": {"filter": "item", "values": codes}},
            {"code": "Ár", "selection": {"filter": "item", "values": years}},
        ],
    )
    # Keep the raw payload as a fetch artifact (repo convention)
    raw_out = RAW / "rikissjod_thj05211.json"
    raw_out.write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")

    df = jsonstat_to_df(js)
    # Skipting labels come back in the response; map codes via metadata order
    code_to_label = dict(zip(sk["values"], sk["valueTexts"]))
    df = df.with_columns(
        pl.col("Skipting").replace_strict(code_to_label, default=pl.col("Skipting"))
    )
    wide = df.pivot(
        on="Skipting", index="Ár", values="value", aggregate_function="first"
    )
    # Rename to English columns; keep any unknown label as-is
    rename = {code_to_label.get(c, c): c for c in COLUMNS} | {
        label: en for label, en in zip(sk["valueTexts"], COLUMNS.values())
    }
    wide = wide.rename({label: rename.get(label, label) for label in wide.columns if label != "Ár"})
    return wide.select(["Ár", *COLUMNS.values()]).sort("Ár")


def cmd_list(args):
    print(f"THJ05211.px — Helstu hagstærðir ríkissjóðs 1980-2025 (one-stop balance: tekjur, gjöld, tekjuafgangur, % af VLF)")
    print(f"  {BASE}/{TABLE}")
    for name, desc in SIBLINGS:
        print(f"{name} — {desc}")
        print(f"  {BASE}/Efnahagur/fjaropinber/fjarmal_rikissjods/{name}")


def cmd_fetch(args):
    df = fetch_balance()
    df.write_csv(OUT_CSV)
    print(f"\n→ {OUT_CSV}  ({df.height} rows × {df.width - 1} indicators)")
    # Sanity: the crisis years the table exists for
    crisis = df.filter(pl.col("Ár").is_in(["2008", "2009", "2010", "2011"]))
    for row in crisis.iter_rows(named=True):
        print(f"  {row['Ár']}  afkoma={row['afkoma_mkr']:>12,.0f} m.kr  ({row['afkoma_pct_vlf']}% af VLF)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list the ríkissjóður PX tables and coverage")
    sub.add_parser("fetch", help="fetch THJ05211 → data/processed/rikissjod_balance.csv")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    else:
        cmd_fetch(args)


if __name__ == "__main__":
    main()

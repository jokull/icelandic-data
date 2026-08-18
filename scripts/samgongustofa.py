"""Samgöngustofa bifreiðatölur — vehicle-registration statistics.

Vehicle registrations from the Power BI dashboard at
https://bifreidatolur.samgongustofa.is/. The generic Power BI reverse-
engineering (embed token, in-iframe query replay, DSR decompression) lives in
`scripts/powerbi.py`; this file supplies only what is Samgöngustofa-specific:
which sections to open, the slicer/column names, and a small CLI.

Two reports:

  * nyskraningar  ("Nýskráningar", #nyskraningar) — NEW registrations =
        nyskraningar = first Icelandic registration, i.e. imports (brand-new
        AND imported-used). The FLOW into the fleet. Year / month / new-used.
  * onroad        ("Tölfræði ökutækja", #tolfraedi) — the CURRENT fleet on the
        road ("í umferð"). The STOCK. A snapshot, no year filter.

Both break down by make (Tegund), fuel (Orkugjafi — the EV-transition read),
class (Ökutækisflokkur) and model (Undirtegund).

GEO-FENCE: the host answers Icelandic IPs in ~50 ms and times out from
datacenter address space. Run this from an Icelandic connection.

Usage:
    uv run python scripts/samgongustofa.py list
    uv run python scripts/samgongustofa.py fetch --report onroad --dimension fuel
    uv run python scripts/samgongustofa.py fetch --dimension make --years 2020-2026
    uv run python scripts/samgongustofa.py fetch --dimension make --years 2025,2026 --monthly
    uv run python scripts/samgongustofa.py fetch --dimension make --years 2026 --where 'Orkugjafi=Rafmagn'
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import csv
import sys
from pathlib import Path

import powerbi as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_SPA = "https://bifreidatolur.samgongustofa.is/"
OUT_DIR = Path(__file__).parent.parent / "data" / "processed" / "samgongustofa"

YEAR_COL = "Ár - ísl."
MONTH_COL = "Mánuður - ísl."
IMPORT_COL = "Innflutningsástand"

MONTHS = [
    "01-janúar", "02-febrúar", "03-mars", "04-apríl", "05-maí", "06-júní",
    "07-júlí", "08-ágúst", "09-september", "10-október", "11-nóvember", "12-desember",
]

# `dims` maps a friendly name -> the Power BI column that visual groups by (the
# brand column is confusingly named "Tegund" = kind). `temporal` reports carry
# the year/month slicers; the snapshot report does not.
REPORTS = {
    "nyskraningar": {
        "anchor": "#nyskraningar",
        "temporal": True,
        "blurb": "new registrations / imports (flow) — year, month, new/used",
        "dims": {"make": "Tegund", "class": "Ökutækisflokkur",
                 "fuel": "Orkugjafi", "model": "Undirtegund"},
    },
    "onroad": {
        "anchor": "#tolfraedi",
        "temporal": False,
        "blurb": "current fleet on the road / í umferð (snapshot)",
        "dims": {"make": "Tegund", "class": "Ökutækjaflokkur",
                 "fuel": "Orkugjafi (groups)", "model": "Undirtegund"},
    },
}


# ---------------------------------------------------------------------------
# query building (thin wrappers over powerbi.py)
# ---------------------------------------------------------------------------
def _slicer_payload(template, *, year=None, month=None, import_state="all"):
    """Set the year / month / new-used slicers on a captured visual template."""
    b = pb.where_drop(template, MONTH_COL, IMPORT_COL)
    if year is not None:
        b = pb.where_in(b, YEAR_COL, [f"{year}L"], text=False)   # integer literal 2023L
    if month:
        b = pb.where_in(b, MONTH_COL, [month])                   # text literal '08-ágúst'
    if import_state == "new":
        b = pb.where_in(b, IMPORT_COL, ["Nýtt"])
    elif import_state == "used":
        b = pb.where_in(b, IMPORT_COL, ["Notað"])
    return b


def _apply_cross(payload, wheres):
    for col, vals in wheres:
        payload = pb.where_in(payload, col, vals, replace=False)
    return payload


def _parse_years(spec):
    years = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            years.update(range(int(a), int(b) + 1))
        elif part:
            years.add(int(part))
    return sorted(years)


def _parse_where(specs):
    """['Orkugjafi=Rafmagn', 'Klass=A;B'] -> [(col, [vals])]; ';' = OR."""
    out = []
    for spec in specs or []:
        col, sep, val = spec.partition("=")
        if not sep:
            raise SystemExit(f"--where must be COL=VALUE, got {spec!r}")
        out.append((col.strip(), [v.strip() for v in val.split(";") if v.strip()]))
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
async def _run_fetch(args):
    from playwright.async_api import async_playwright

    cfg = REPORTS[args.report]
    dim_col = cfg["dims"][args.dimension]
    wheres = _parse_where(args.where)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1200})
        disc = await pb.discover(page, BASE_SPA, anchor=cfg["anchor"])
        if dim_col not in disc.templates:
            raise SystemExit(f"dimension '{args.dimension}' ({dim_col}) not among "
                             f"{args.report} visuals: {sorted(disc.templates)}")
        template = disc.templates[dim_col]
        records, header = [], [args.dimension]

        async def pull(payload):
            return pb.group_counts(await pb.replay(disc.frame, disc.key, payload, retries=1))

        if cfg["temporal"]:
            years = _parse_years(args.years)
            months = MONTHS[: args.through] if args.monthly else [None]
            header += ["year"] + (["month"] if args.monthly else []) + ["count"]
            print(f"report={args.report} key={disc.key} dim={dim_col} years={years} "
                  f"months={'Jan..' + months[-1] if args.monthly else 'all'}", file=sys.stderr)
            for year in years:
                for month in months:
                    rows = await pull(_apply_cross(
                        _slicer_payload(template, year=year, month=month, import_state=args.import_state), wheres))
                    for name, cnt in sorted(rows.items(), key=lambda kv: -kv[1]):
                        rec = {args.dimension: name, "year": year, "count": int(cnt)}
                        if args.monthly:
                            rec["month"] = int(month[:2])
                        records.append(rec)
                    print(f"  {year}{' ' + month if month else ''}: {len(rows)} "
                          f"{args.dimension}s, {int(sum(rows.values())):,}", file=sys.stderr)
                    await asyncio.sleep(2.5)
        else:
            header += ["count"]
            print(f"report={args.report} key={disc.key} dim={dim_col} (current fleet snapshot)", file=sys.stderr)
            rows = await pull(_apply_cross(_slicer_payload(template, import_state=args.import_state), wheres))
            for name, cnt in sorted(rows.items(), key=lambda kv: -kv[1]):
                records.append({args.dimension: name, "count": int(cnt)})
            print(f"  {len(rows)} {args.dimension}s on road, {int(sum(rows.values())):,} total", file=sys.stderr)

        await browser.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parts = [args.report, args.dimension]
    if cfg["temporal"]:
        parts.append("by_year_month" if args.monthly else "by_year")
    if args.import_state != "all":
        parts.append(args.import_state)
    for col, vals in wheres:
        tag = col.split(" ")[0].split("-")[0][:6] + "-" + "+".join(vals)
        parts.append("".join(ch for ch in tag if ch.isalnum() or ch in "-+"))
    out = Path(args.out) if args.out else OUT_DIR / ("_".join(parts) + ".csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(records)
    print(f"→ {out} ({len(records)} rows)", file=sys.stderr)


async def _run_list(args):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1200})
        for name, cfg in REPORTS.items():
            disc = await pb.discover(page, BASE_SPA, anchor=cfg["anchor"])
            inv = {v: k for k, v in cfg["dims"].items()}
            print(f"\n=== {name}  ({cfg['anchor']}) — {cfg['blurb']}")
            print(f"    resource key: {disc.key}")
            print("    dimensions (all groupable columns the report exposes):")
            for col in sorted(disc.templates):
                alias = inv.get(col)
                print(f"      {col:<26} {'--dimension ' + alias if alias else '(bonus column, no alias)'}")
        print("\nSlicers (nyskraningar): --years / --monthly (" + MONTH_COL + ") / --import-state new|used")
        print("Cross-filter any report by any column: --where 'COL=VALUE' (repeatable; ';' = OR)")
        print("Months:", ", ".join(MONTHS))
        print("\nExamples:")
        print("  fetch --report onroad --dimension fuel               # current EV/petrol/diesel fleet split")
        print("  fetch --dimension make --years 2020-2026             # imports by brand per year")
        print("  fetch --dimension fuel --years 2025,2026 --monthly")
        print("  fetch --dimension make --years 2026 --where 'Orkugjafi=Rafmagn'   # BEV imports by brand")
        await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="discover both reports, their keys and dimensions")
    pl.set_defaults(func=lambda a: asyncio.run(_run_list(a)))

    pf = sub.add_parser("fetch", help="pull registration counts to a tidy CSV")
    pf.add_argument("--report", choices=list(REPORTS), default="nyskraningar",
                    help="nyskraningar = new registrations/imports (flow); onroad = current fleet (snapshot)")
    pf.add_argument("--dimension", choices=["make", "class", "fuel", "model"], default="make")
    pf.add_argument("--years", default=f"2020-{dt.date.today().year}",
                    help="temporal reports only, e.g. '2020-2026' or '2025,2026'")
    pf.add_argument("--monthly", action="store_true", help="break each year down by month")
    pf.add_argument("--through", type=int, default=12, metavar="N",
                    help="with --monthly, only months 1..N (default 12)")
    pf.add_argument("--import-state", choices=["all", "new", "used"], default="all")
    pf.add_argument("--where", action="append", metavar="COL=VALUE",
                    help="cross-filter by any model column, repeatable; ';' OR-joins values, "
                         "e.g. --where 'Orkugjafi=Rafmagn' (see column names in `list`)")
    pf.add_argument("--out", help="output CSV path (default data/processed/samgongustofa/)")
    pf.set_defaults(func=lambda a: asyncio.run(_run_fetch(a)))

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

"""Tekjusagan — income history dashboard (Forsætisráðuneytið).

Since an October 2026 redeploy the Angular SPA no longer embeds Power BI: it
charts JSON from its own backend, `POST /api/sqlseries/<queryId>`, with the
group filters as the request body. No token, no browser.

Usage:
    uv run python scripts/tekjusagan.py                 # same as fetch
    uv run python scripts/tekjusagan.py list            # series + default filters
    uv run python scripts/tekjusagan.py fetch           # all series, SPA defaults
    uv run python scripts/tekjusagan.py fetch --series radstofun --set "Tekjubil=Tekjubil 10"
    uv run python scripts/tekjusagan.py fetch --series radstofun --set "Breyta=Atvinnutekjur|Tekjuskattur"
"""
import argparse
import json
import sys
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "tekjusagan"
PROCESSED_DIR = ROOT / "data" / "processed"

SPA_URL = "https://tekjusagan.is/"
SERIES_URL = SPA_URL + "api/sqlseries/{query_id}"
USER_AGENT = "icelandic-data (+https://github.com/jokull/icelandic-data)"

# The SPA hardcodes both ends (firstTaxYear, page.selectedTaxYear); asking for a
# later `to` just returns through the last loaded year.
FIRST_TAX_YEAR = 1991
LAST_TAX_YEAR = 2024

# Breyta (which variables to return) for homeowners without capital income —
# the SPA's default Fasteign/Fjármagnstekjur selection on /skyrslur/radstofun.
# Renters and capital-income variants swap this list; see the skill.
_RADSTOFUN_BREYTA = [
    "Atvinnutekjur",
    "Lífeyrissjóðstekjur",
    "Bætur frá ríki og sveitarfélögum",
    "Barnabætur",
    "Vaxtabætur",
    "Tekjuskattur",
    "Fasteignaskattur",
    "Ráðstöfunartekjur fasteignaeigenda",
    "Tímabil 1991 - 2007",
    "Tímabil 2007 - 2012",
    "Ráðstöfunartekjur fasteignaeiganda án fjármagnstekna vöxtur frá 2012",
]

# slug -> SPA route, stored-procedure queryId, and the exact body the SPA sends
# with its default filter selection. Every key is a required procedure
# parameter: omit one and the backend answers 400 "expects parameter '@X'";
# add one it doesn't take (Breyta outside radstofun) and it answers 400 "too
# many arguments".
SERIES = {
    "radstofun": {
        "route": "/skyrslur/radstofun",
        "query_id": "IncomeVariables",
        "title": "Þróun ráðstöfunartekna — disposable income by component",
        "body": {
            "Aldurshópur": "25 - 64 ára",
            "Tekjubil": "Tekjubil 1-10",
            "Börn": "1 - 2 börn",
            "Búseta": "Landið allt",
            "Hjúskaparstaða": "Hjón",
            "Líkan": "T3 - Tíundir eftir atvinnutekjum og bótum",
            "Breyta": _RADSTOFUN_BREYTA,
            "Hópur": "Allir í aldursbili",
        },
    },
    "eignirskuldir": {
        "route": "/skyrslur/eignirskuldir",
        "query_id": "AssetVariables",
        "title": "Eignir og skuldir — assets and debt",
        "body": {
            "Aldurshópur": "25 - 64 ára",
            "Börn": "1 - 2 börn",
            "Búseta": "Landið allt",
            "Hjúskaparstaða": "Hjón",
            "Líkan": "T3 - Tíundir eftir atvinnutekjum og bótum",
            "Tekjubil": "Tekjubil 1-10",
            "Hópur": "Allir í aldursbili",
        },
    },
    "kynmenntun": {
        "route": "/skyrslur/kynmenntun",
        "query_id": "GenderEducationVariables",
        "title": "Kyn og menntun — pre-tax income by gender × education",
        "body": {
            "Aldurshópur": "25 - 64 ára",
            "Hjúskaparstaða": "Öll kyn óháð hjúskap",
            "Líkan": "Raðað í tekjutíundir eftir heildartekjum með fjármagnstekjum",
            "Búseta": "Landið allt",
            "Tekjubil": "Tekjubil 1-10",
            "Menntunarstig": "Óháð menntun",
        },
    },
}


def parse_overrides(pairs: list[str]) -> dict:
    """`KEY=VALUE` pairs -> body overrides; `|` in VALUE makes a list."""
    out = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise SystemExit(f"--set expects KEY=VALUE, got {pair!r}")
        out[key] = value.split("|") if "|" in value else value
    return out


def fetch_series(
    query_id: str, body: dict, year_from: int = FIRST_TAX_YEAR, year_to: int = LAST_TAX_YEAR
) -> list[dict]:
    r = httpx.post(
        SERIES_URL.format(query_id=query_id),
        params={"from": year_from, "to": year_to},
        json=body,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    if r.status_code == 400:
        # The backend relays the SQL Server error, which names the bad parameter.
        raise SystemExit(f"{r.request.url} -> 400: {r.json().get('message', r.text)}")
    r.raise_for_status()
    return r.json()["items"]


def tidy(items: list[dict], series: str, body: dict) -> pl.DataFrame:
    """One row per (tax year, variable). Section-header rows (both values
    null — e.g. the Ráðstöfunartekjur row the SPA sums itself) are dropped."""
    rows = [
        {
            "series": series,
            "tax_year": i["Skattár"],
            "variable": i["Breyta Heiti"],
            "label": i["Breyta Lýsing"],
            "sort_order": i["Breyta Röðun"],
            "value_isk": i["Breytugildi ISK"],
            "growth_rate": i["Breytugildi Prósenta"],
        }
        for i in items
        if i["Breytugildi ISK"] is not None or i["Breytugildi Prósenta"] is not None
    ]
    df = pl.DataFrame(
        rows,
        schema={
            "series": pl.Utf8,
            "tax_year": pl.Int32,
            "variable": pl.Utf8,
            "label": pl.Utf8,
            "sort_order": pl.Int32,
            "value_isk": pl.Float64,
            "growth_rate": pl.Float64,
        },
    )
    # Carry the group definition on every row so a CSV is self-describing.
    filters = {k: v for k, v in body.items() if k != "Breyta"}
    df = df.with_columns(pl.lit(v).alias(k) for k, v in filters.items())
    return df.unique(subset=["tax_year", "variable", "label"], keep="last").sort(
        "tax_year", "sort_order", "label"
    )


def cmd_list(args):
    for slug, s in SERIES.items():
        print(f"{slug:<14} {s['query_id']:<26} {SPA_URL.rstrip('/')}{s['route']}")
        print(f"  {s['title']}")
        for k, v in s["body"].items():
            shown = f"[{len(v)} variables]" if isinstance(v, list) else repr(v)
            print(f"    {k} = {shown}")


def cmd_fetch(args):
    overrides = parse_overrides(args.set or [])
    slugs = [args.series] if args.series else list(SERIES)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        s = SERIES[slug]
        body = {**s["body"], **overrides}
        items = fetch_series(s["query_id"], body, args.year_from, args.year_to)
        raw = RAW_DIR / f"{slug}.json"
        raw.write_text(
            json.dumps({"query_id": s["query_id"], "body": body, "items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        df = tidy(items, slug, body)
        if df.is_empty():
            # An unknown filter value is not an error to the backend — it just
            # matches nothing. Say so instead of writing an empty file silently.
            print(f"  {slug}: 0 rows — check the --set values against `list`/the skill", file=sys.stderr)
        out = PROCESSED_DIR / f"tekjusagan_{slug}.csv"
        df.write_csv(out)
        years = f"{df['tax_year'].min()}–{df['tax_year'].max()}" if len(df) else "-"
        print(f"  {slug}: {len(df)} rows, {df['label'].n_unique()} variables, {years} -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="series and their default filters").set_defaults(func=cmd_list)
    p = sub.add_parser("fetch", help="fetch series -> data/processed/tekjusagan_{series}.csv")
    p.add_argument("--series", choices=list(SERIES))
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a filter; '|' separates list values")
    p.add_argument("--from", dest="year_from", type=int, default=FIRST_TAX_YEAR)
    p.add_argument("--to", dest="year_to", type=int, default=LAST_TAX_YEAR)
    p.set_defaults(func=cmd_fetch)
    args = ap.parse_args()
    if args.cmd is None:
        args = ap.parse_args(["fetch"])
    args.func(args)


if __name__ == "__main__":
    main()

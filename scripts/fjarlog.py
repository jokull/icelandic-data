"""Fjárlög — Icelandic state budget (appropriations + plan), málaflokkur level.

The Ministry of Finance (Fjármála- og efnahagsráðuneytið) publishes the budget
bill (fjárlagafrumvarp), the enacted budget (fjárlög) and the 5-year fiscal
plan (fjármálaáætlun) on stjornarradid.is. Alongside the PDFs it publishes one
machine-readable CSV — "Talnagögn úr fjárlagafrumvarpi" — that contains the
whole budget at the level Alþingi appropriates it.

That CSV is the source this script targets. A single file spans four data
products in one tidy long table:

    Afurð              Year(s)   Meaning
    Ríkisreikningur    Y-2       Final state-accounts ACTUALS (outturn)
    Fjárlög            Y-1       Enacted budget for the prior year
    Frumvarp           Y         The budget BILL for the budget year
    Áætlun             Y+1..Y+2  Fiscal-plan projection

Each row is one (year × afurð × viðfang × TegundNota) cell, in m.kr with a
comma decimal. TegundNota is a *view* discriminator — the same money appears
under several views, so NEVER sum across TegundNota:

    Gjöld / Heildarútgjöld   gross expenditure  (use this for "spending")
    Tekjur / Rekstrartekjur  revenue / own-revenue (sértekjur)
    Greiðsla / Fjárhæð       net cash / net appropriation
    Rekstrarframlög          operating grant component  ┐ these three add up
    Rekstrartilfærslur       operating transfers        │ to Heildarútgjöld
    Fjárfestingarframlög     investment component       ┘
    Fjármagnstilfærslur      capital transfers

Hierarchy: Málefnasvið (01–36 policy area) → Málaflokkur (e.g. 04.30) →
Ráðuneyti → Liður (institution group) → Viðfang (appropriation item).

Defense lives in málaflokkur 04.30 "Samstarf um öryggis- og varnarmál"
(viðfang "101 Varnarmál" + "601 Tæki og búnaður"). This is the article's
"bein útgjöld til varnar- og öryggismála" definition — broader "varnar- og
öryggismál" aggregates (incl. Landhelgisgæslan 09.20, almannavarnir, etc.) are
bespoke ministry constructs not reproducible from a single málaflokkur.

Usage:
    uv run python scripts/fjarlog.py fetch                  # download + tidy parquet
    uv run python scripts/fjarlog.py fetch --year 2026      # pick budget-year page
    uv run python scripts/fjarlog.py products               # afurð × year coverage
    uv run python scripts/fjarlog.py mala 04.30             # one málaflokkur, all years
    uv run python scripts/fjarlog.py mala 04.30 --tegund Gjöld
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import quote, urljoin

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE = "https://www.stjornarradid.is"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "fjarlog"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
PROCESSED = PROCESSED_DIR / "fjarlog.parquet"

# The "skjöl og gögn" page for a budget year lists the numerical-data CSV.
def _gogn_url(year: int) -> str:
    return f"{BASE}/verkefni/opinber-fjarmal/fjarlog/fjarlog-fyrir-arid-{year}/skjol-og-gogn/"

# Link to the "Talnagögn úr fjárlagafrumvarpi … .csv" on that page. The filename
# carries a version suffix ("- 003.csv") that changes between revisions, so we
# discover it from the HTML rather than hard-coding.
_CSV_LINK_RE = re.compile(r'href="([^"]*[Tt]alnag[^"]*\.csv)"')

# Known-good fallback if the page layout changes (fjárlög 2026 bundle).
_FALLBACK_CSV = (
    f"{BASE}/library/02-Rit--skyrslur-og-skrar/"
    + quote("Talnagögn úr fjárlagafrumvarpi - 003.csv")
)

_RENAME = {
    "Ár": "ar",
    "Afurð": "afurd",
    "FlokkunNy": "flokkun_ny",
    "Málefnasvið": "malefnasvid",
    "Málaflokkur": "malaflokkur",
    "Ráðuneyti": "raduneyti",
    "Liður": "lidur",
    "Viðfang": "vidfang",
    "TegundNota": "tegund",
    "Upphæð": "mkr",
}


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=120,
        follow_redirects=True,
        headers={"User-Agent": "icelandic-data/1.0 (+fjarlog skill)"},
    )


def _discover_csv_url(client: httpx.Client, year: int) -> str:
    try:
        r = client.get(_gogn_url(year))
        r.raise_for_status()
        m = _CSV_LINK_RE.search(r.text)
        if m:
            return urljoin(BASE, m.group(1))
    except httpx.HTTPError as e:
        print(f"  (discovery failed: {e}; using fallback URL)", file=sys.stderr)
    return _FALLBACK_CSV


def fetch(year: int) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        url = _discover_csv_url(client, year)
        print(f"downloading {url}", file=sys.stderr)
        r = client.get(url)
        r.raise_for_status()
    raw = RAW_DIR / f"talnagogn_fjarlog{year}.csv"
    raw.write_bytes(r.content)
    print(f"wrote {len(r.content):,} bytes → {raw}", file=sys.stderr)

    df = (
        pl.read_csv(
            raw, separator=";", encoding="utf8-lossy",
            schema_overrides={"Upphæð": pl.String},
        )
        .rename(_RENAME)
        # Amount column m.kr. Revisions of this file ship in two number formats:
        #   dot-decimal, no grouping ("6381.1")          ← current canonical file
        #   comma-decimal, dot grouping ("6.381,1")      ← older revisions
        # Normalise both: if a comma is present it is the decimal sep (strip any
        # grouping dots first); otherwise the dot is already the decimal sep.
        .with_columns(
            pl.when(pl.col("mkr").str.contains(","))
            .then(pl.col("mkr").str.replace_all(r"\.", "").str.replace(",", "."))
            .otherwise(pl.col("mkr"))
            .str.replace_all(" ", "")
            .cast(pl.Float64, strict=False)
            .alias("mkr"),
            pl.col("ar").cast(pl.Int64),
        )
        # split "04 Utanríkismál" → nr + heiti for the two hierarchy columns
        .with_columns(
            pl.col("malefnasvid").str.extract(r"^(\d+)").alias("malefnasvid_nr"),
            pl.col("malaflokkur").str.extract(r"^(\d+\.\d+)").alias("malaflokkur_nr"),
        )
    )
    df.write_parquet(PROCESSED)
    print(
        f"wrote {df.height:,} rows → {PROCESSED}\n"
        f"  years {df['ar'].min()}–{df['ar'].max()} · "
        f"{df['afurd'].n_unique()} products · "
        f"{df['malaflokkur'].n_unique()} málaflokkar",
        file=sys.stderr,
    )


def _load() -> pl.DataFrame:
    if not PROCESSED.exists():
        sys.exit("no data — run: uv run python scripts/fjarlog.py fetch")
    return pl.read_parquet(PROCESSED)


def products() -> None:
    df = _load()
    out = (
        df.group_by("afurd")
        .agg(
            pl.col("ar").min().alias("y0"),
            pl.col("ar").max().alias("y1"),
            pl.len().alias("rows"),
        )
        .sort("y0")
    )
    print(out)


def mala(code: str, tegund: str | None) -> None:
    df = _load().filter(pl.col("malaflokkur").str.starts_with(code))
    if df.is_empty():
        sys.exit(f"no rows for málaflokkur {code!r}")
    name = df["malaflokkur"][0]
    print(f"# {name}\n")
    teg = tegund or "Gjöld"
    out = (
        df.filter(pl.col("tegund") == teg)
        .group_by("ar", "afurd")
        .agg(pl.col("mkr").sum().round(1).alias(f"{teg}_mkr"))
        .sort("ar")
    )
    print(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Icelandic state budget (fjárlög) — málaflokkur data")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download + tidy the budget CSV")
    f.add_argument("--year", type=int, default=2026, help="budget-year page to pull (default 2026)")

    sub.add_parser("products", help="afurð (Ríkisreikningur/Fjárlög/Frumvarp/Áætlun) × year coverage")

    m = sub.add_parser("mala", help="aggregate one málaflokkur across years")
    m.add_argument("code", help="málaflokkur prefix, e.g. 04.30")
    m.add_argument("--tegund", help="TegundNota view (default Gjöld)")

    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.year)
    elif args.cmd == "products":
        products()
    elif args.cmd == "mala":
        mala(args.code, args.tegund)


if __name__ == "__main__":
    main()

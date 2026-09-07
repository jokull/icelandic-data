"""Parse the annual HMS húsnæðisáætlanir (housing-plans) workbook.

The workbook is the authoritative annual update on Iceland's housing market:
completions vs the HMS "real need" forecast band, non-market rental waitlists
by category, and buildable-plot availability by region. It is published
annually by HMS (a PDF/XLSX under /skyrslur/húsnæðisáætlanir) and is the
natural home for the completions figures that `housing_completions.py`
previously hardcoded.

Three tidy outputs, into data/processed/:

  - hms_husnaedisaaetlanir_completions_vs_need.csv   sheet 2.1 + 3.1 + 3.2 (wide per year)
  - hms_husnaedisaaetlanir_nonmarket_rental_waitlist.csv  sheet 5.2 (long)
  - hms_husnaedisaaetlanir_plot_availability_by_region.csv sheet 4.2

Usage:
    uv run python scripts/hms_housing_plans.py            # parse the latest workbook in data/raw/hms/
    uv run python scripts/hms_housing_plans.py --year 2026
    uv run python scripts/hms_housing_plans.py --source /path/to/husnaedisaaetlanir_2026_gogn.xlsx
    uv run python scripts/hms_housing_plans.py list       # list available local workbooks
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "hms"
PROCESSED_DIR = ROOT / "data" / "processed"

OUT_COMPLETIONS = PROCESSED_DIR / "hms_husnaedisaaetlanir_completions_vs_need.csv"
OUT_WAITLIST = PROCESSED_DIR / "hms_husnaedisaaetlanir_nonmarket_rental_waitlist.csv"
OUT_PLOTS = PROCESSED_DIR / "hms_husnaedisaaetlanir_plot_availability_by_region.csv"

# The workbook is published under hms.is/skyrslur/húsnæðisáætlanir, but the page
# and the direct file link sit behind a Vercel checkpoint — so it is downloaded
# by hand (see .agents/skills/hms/SKILL.md) and parsed from data/raw/hms/.
FILENAME_RE = re.compile(r"husnaedisaaetlanir_(?P<year>\d{4})_gogn\.xlsx")


def resolve_workbook(year: int | None, source: str | None) -> Path:
    """Return the workbook path from --source, --year, or the latest local copy."""
    if source:
        return Path(source).expanduser().resolve()
    if year:
        p = RAW_DIR / f"husnaedisaaetlanir_{year}_gogn.xlsx"
        if not p.exists():
            sys.exit(f"Not found: {p}. Download the {year} workbook into data/raw/hms/ first.")
        return p
    candidates = {int(m["year"]): p for p in RAW_DIR.glob("husnaedisaaetlanir_*_gogn.xlsx")
                  if (m := FILENAME_RE.match(p.name))}
    if not candidates:
        sys.exit(
            f"No husnaedisaaetlanir workbook in {RAW_DIR}. Download one "
            f"(husnaedisaaetlanir_<year>_gogn.xlsx) or pass --source."
        )
    return candidates[max(candidates)]


def list_workbooks() -> int:
    for p in sorted(RAW_DIR.glob("husnaedisaaetlanir_*_gogn.xlsx")):
        m = FILENAME_RE.match(p.name)
        print(f"  {p.name}  (year {m['year'] if m else '?'})")
    return 0


def parse_completions_and_need(xlsx: Path) -> pl.DataFrame:
    """Sheet 2.1 (completions + forecast band) merged with sheets 3.1/3.2 (real need).

    One wide row per year: national + capital-area real-need bounds joined onto
    the completed-dwellings and forecast columns.
    """
    completions = pl.read_excel(xlsx, sheet_name="2.1").rename({
        "__UNNAMED__0": "year",
        "Fjöldi fullbúinna íbúða": "completed_national",
        "Miðspá": "forecast_mid_national",
        "Spábil neðri mörk": "forecast_low_national",
        "Spábil efri mörk": "forecast_high_national",
    }).with_columns(pl.col("year").cast(pl.Int64)).drop_nulls(["year"])

    national = pl.read_excel(xlsx, sheet_name="3.1").rename({
        "Allt landið": "year",
        "Raunveruleg þörf - neðri mörk": "real_need_low_national",
        "Raunveruleg þörf - efri mörk": "real_need_high_national",
    }).with_columns(pl.col("year").cast(pl.Int64))

    capital = pl.read_excel(xlsx, sheet_name="3.2").rename({
        "Höfuðborgarsvæðið": "year",
        "Raunveruleg þörf - neðri mörk": "real_need_low_capital",
        "Raunveruleg þörf - efri mörk": "real_need_high_capital",
    }).with_columns(pl.col("year").cast(pl.Int64))

    return (
        completions.join(national, on="year", how="full", coalesce=True, validate="1:1")
        .join(capital, on="year", how="full", coalesce=True, validate="1:1")
        .sort("year")
    )


WAITLIST_LABELS = {
    "Leiguíbúðir fyrir tekju- og eignalága": "Rental for low-income and low-asset households",
    "Búseturéttaríbúðir": "Cooperative (búseturéttur)",
    "Félagslegar íbúðir ": "Social apartments",
    "Leiguíbúðir fyrir eldri borgara": "Rental for elderly",
    "Námsmannaíbúðir": "Student housing",
    "Sértæk búsetuúrræði": "Specialised housing solutions",
    "Samtals": "Total",
}


def parse_waitlist(xlsx: Path) -> pl.DataFrame:
    """Sheet 5.2 — non-market rental waitlists by category, in long format.

    Row 0 is the sheet title, row 1 is the real header (Búsetuform + years), so
    read with an explicit header row.
    """
    raw = pl.read_excel(xlsx, sheet_name="5.2", read_options={"header_row": 1})
    year_cols = [c for c in raw.columns[1:] if c.isdigit()]
    long = (
        raw.rename({raw.columns[0]: "category"})
        .select(["category", *year_cols])
        .unpivot(index="category", on=year_cols, variable_name="year", value_name="waitlist")
        .with_columns(pl.col("year").cast(pl.Int64), pl.col("waitlist").cast(pl.Int64))
        .drop_nulls(["category"])
    )
    return long.with_columns(
        pl.col("category").replace_strict(WAITLIST_LABELS, default=pl.col("category"))
        .alias("category_en")
    )[["year", "category", "category_en", "waitlist"]]


def parse_plot_availability(xlsx: Path) -> pl.DataFrame:
    """Sheet 4.2 — ratio of buildable plots to 2025 housing need, by region."""
    df = pl.read_excel(xlsx, sheet_name="4.2")
    matches = [(c, re.fullmatch(r"Hlutfall byggingarhæfra lóða af íbúðaþörf (\d{4})", c)) for c in df.columns]
    matches = [(c, m) for c, m in matches if m]
    if len(matches) != 1 or df.columns[0] != "__UNNAMED__0":
        raise ValueError("Unexpected plot-availability sheet schema")
    column, match = matches[0]
    return df.rename({"__UNNAMED__0": "region", column: "plot_to_need_ratio"}).with_columns(
        pl.lit(int(match[1])).alias("need_year")
    )


def cmd_parse(args: argparse.Namespace) -> int:
    xlsx = resolve_workbook(args.year, args.source)
    print(f"Parsing {xlsx.name}…", file=sys.stderr)

    completions_need = parse_completions_and_need(xlsx)
    waitlist = parse_waitlist(xlsx)
    plots = parse_plot_availability(xlsx)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    completions_need.write_csv(OUT_COMPLETIONS)
    waitlist.write_csv(OUT_WAITLIST)
    plots.write_csv(OUT_PLOTS)

    print(f"Wrote {OUT_COMPLETIONS}  ({len(completions_need)} rows)")
    print(completions_need)
    print()
    print(f"Wrote {OUT_WAITLIST}  ({len(waitlist)} rows)")
    print(waitlist.pivot(index="category_en", on="year", values="waitlist"))
    print()
    print(f"Wrote {OUT_PLOTS}  ({len(plots)} rows)")
    print(plots)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, help="workbook year, e.g. 2026 (default: latest local)")
    ap.add_argument("--source", help="explicit path to the workbook .xlsx")
    sub = ap.add_subparsers(dest="cmd")
    ap.set_defaults(func=cmd_parse)
    l = sub.add_parser("list", help="list available local workbooks in data/raw/hms/")
    l.set_defaults(func=lambda args: list_workbooks())
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Fetch Hagstofa wage index + income distribution + PAYE by background.

Tidy long-format outputs with CPI-deflated real values. Complementary to
scripts/income_distribution.py (which dumps TEK01001 income-by-source tables
as raw CSV).

Pulls:
  1. LAU04000 — Launavísitala (headline wage index), monthly from 1989
  2. TEK01007 — Distribution of labor income (deciles + 95/99 pct, mean, count),
               annual, by sex and age
  3. TEK01006 — Distribution of total income (same shape)
  4. TEK02012 — Monthly PAYE payments by sex and background (Íslenskur bakgrunnur
               vs Innflytjendur) — direct citizenship/background breakdown

Outputs:
  - data/raw/hagstofan/wage_index_general/LAU04000.json  (raw POST JSON response)
  - data/raw/hagstofan/income/TEK01007.json
  - data/raw/hagstofan/income/TEK01006.json
  - data/raw/hagstofan/income/TEK02012.json
  - data/processed/hagstofan_income_distribution.csv
  - data/processed/hagstofan_wage_index_general.csv
  - data/processed/hagstofan_income_by_background.csv

Depends on data/raw/hagstofan/cpi_full.csv being present for CPI deflation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import polars as pl

BASE = "https://px.hagstofa.is/pxis/api/v1/is/Samfelag/launogtekjur"
ROOT = Path(__file__).resolve().parent.parent
RAW_WAGE = ROOT / "data/raw/hagstofan/wage_index_general"
RAW_INC = ROOT / "data/raw/hagstofan/income"
PROC = ROOT / "data/processed"
RAW_WAGE.mkdir(parents=True, exist_ok=True)
RAW_INC.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)


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

    # Build per-dim ordered label lists (by category index)
    dim_labels: list[list[str]] = []
    for d in dim_ids:
        cat = dims[d]["category"]
        # index maps code -> position; label maps code -> text
        idx = cat["index"]
        if isinstance(idx, dict):
            # invert to position -> code
            inv = [None] * len(idx)
            for code, pos in idx.items():
                inv[pos] = code
        else:
            inv = list(idx)
        labels = cat.get("label", {})
        dim_labels.append([labels.get(c, c) for c in inv])

    # Generate all combinations in row-major order matching `values`
    n = len(values)
    rows = []
    # position iterator via strides
    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    for flat in range(n):
        rem = flat
        row_labels = []
        for i, s in enumerate(strides):
            idx = rem // s
            rem = rem % s
            row_labels.append(dim_labels[i][idx])
        row = {d: lbl for d, lbl in zip(dim_ids, row_labels)}
        row["value"] = values[flat]
        rows.append(row)
    return pl.DataFrame(rows)


def fetch_wage_index() -> pl.DataFrame:
    print("[1/4] LAU04000 — Launavísitala monthly from 1989...")
    js = post_json(
        "2_lvt/1_manadartolur/LAU04000.px",
        query=[
            {"code": "Eining", "selection": {"filter": "item", "values": ["index"]}},
        ],
    )
    (RAW_WAGE / "LAU04000.json").write_text(
        json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    df = jsonstat_to_df(js)
    df = df.rename({"Mánuður": "month"}).drop("Eining")
    df = df.with_columns(
        pl.col("month").str.slice(0, 4).cast(pl.Int32).alias("year"),
        pl.col("month").str.slice(5, 2).cast(pl.Int32).alias("month_num"),
        pl.col("value").cast(pl.Float64).alias("wage_index"),
    ).drop("value")
    df.write_csv(PROC / "hagstofan_wage_index_general.csv")
    print(f"  {len(df)} rows, latest {df['month'].max()}")
    return df


def fetch_labor_income_dist() -> pl.DataFrame:
    print("[2/4] TEK01007 — Labor income distribution (deciles)...")
    js = post_json(
        "3_tekjur/1_tekjur_skattframtol/TEK01007.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},  # alls
            {
                "code": "Aldur",
                "selection": {"filter": "item", "values": ["Total", "Y25-54"]},
            },
        ],
    )
    (RAW_INC / "TEK01007.json").write_text(
        json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    df = jsonstat_to_df(js).rename({"Ár": "year"})
    df = df.with_columns(pl.col("year").cast(pl.Int32))
    print(f"  {len(df)} rows, years {df['year'].min()}-{df['year'].max()}")
    return df


def fetch_total_income_dist() -> pl.DataFrame:
    print("[3/4] TEK01006 — Total income distribution (deciles)...")
    js = post_json(
        "3_tekjur/1_tekjur_skattframtol/TEK01006.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            {
                "code": "Aldur",
                "selection": {"filter": "item", "values": ["0", "Y25-54"]},
            },
        ],
    )
    (RAW_INC / "TEK01006.json").write_text(
        json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    df = jsonstat_to_df(js).rename({"Ár": "year"})
    df = df.with_columns(pl.col("year").cast(pl.Int32))
    print(f"  {len(df)} rows")
    return df


def fetch_background_monthly() -> pl.DataFrame:
    print("[4/4] TEK02012 — PAYE by background (Íslenskur vs Innflytjendur)...")
    js = post_json(
        "3_tekjur/0_stadgreidsla/TEK02012.px",
        query=[
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
            # All Bakgrunnur categories
            # Tegund: wages only (Launagreiðslur)
            {
                "code": "Tegundir staðgreiðsluskyldra greiðslna",
                "selection": {"filter": "item", "values": ["1"]},
            },
        ],
    )
    (RAW_INC / "TEK02012.json").write_text(
        json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    df = jsonstat_to_df(js)
    df = df.rename({"Mánuður": "month", "Bakgrunnur": "background"})
    print(f"  {len(df)} rows, latest {df['month'].max()}")
    return df


def load_cpi() -> pl.DataFrame:
    """Load monthly CPI from existing cpi_full.csv, build annual average."""
    path = ROOT / "data/raw/hagstofan/cpi_full.csv"
    df = pl.read_csv(path)
    df = df.select(
        [
            pl.col("Mánuður").alias("month"),
            pl.col("Vísitala neysluverðs Vísitala").alias("cpi"),
        ]
    ).with_columns(
        pl.col("month").str.slice(0, 4).cast(pl.Int32).alias("year"),
        pl.col("cpi").cast(pl.Float64, strict=False),
    )
    annual = df.group_by("year").agg(pl.col("cpi").mean().alias("cpi_annual"))
    # base 2015 average
    base = annual.filter(pl.col("year") == 2015)["cpi_annual"][0]
    annual = annual.with_columns((pl.col("cpi_annual") / base * 100).alias("cpi_2015"))
    return annual.sort("year")


def build_processed_csv(df_labor: pl.DataFrame, df_total: pl.DataFrame) -> pl.DataFrame:
    """Build the tidy processed CSV with columns
    year, metric, group, age, value_isk, real_value_2015isk.
    """
    cpi = load_cpi()

    def tidy(df: pl.DataFrame, source: str) -> pl.DataFrame:
        return df.select(
            [
                pl.col("year"),
                pl.lit(source).alias("source"),
                pl.col("Kyn").alias("sex"),
                pl.col("Aldur").alias("age"),
                pl.col("Eining").alias("metric_raw"),
                pl.col("value").cast(pl.Float64, strict=False).alias("value_isk"),
            ]
        )

    out = pl.concat([tidy(df_labor, "labor_income"), tidy(df_total, "total_income")])

    # Canonicalise metric labels. Hagstofa labels are like "10%", "50%", "Meðaltal - skilyrt", "Fjöldi - skilyrtur"
    metric_map = {
        "10%": "decile_10",
        "20%": "decile_20",
        "30%": "decile_30",
        "40%": "decile_40",
        "50%": "median",
        "60%": "decile_60",
        "70%": "decile_70",
        "80%": "decile_80",
        "90%": "decile_90",
        "95%": "pct_95",
        "99%": "pct_99",
        "Meðaltal - skilyrt": "mean",
        "Fjöldi - skilyrtur": "count",
    }
    out = out.with_columns(
        pl.col("metric_raw").replace(metric_map).alias("metric")
    ).drop("metric_raw")

    out = out.with_columns(pl.lit("all").alias("group"))

    # Join CPI (annual) and compute real values in 2015 ISK
    out = out.join(cpi.select(["year", "cpi_2015"]), on="year", how="left")
    out = out.with_columns(
        pl.when(pl.col("metric") == "count")
        .then(pl.col("value_isk"))  # counts not deflated
        .otherwise(pl.col("value_isk") / pl.col("cpi_2015") * 100)
        .alias("real_value_2015isk")
    )

    out = out.select(
        [
            "year",
            "source",
            "metric",
            "group",
            "sex",
            "age",
            "value_isk",
            "real_value_2015isk",
        ]
    ).sort(["source", "age", "metric", "year"])

    out.write_csv(PROC / "hagstofan_income_distribution.csv")
    print(f"  wrote hagstofan_income_distribution.csv ({len(out)} rows)")
    return out


def build_background_csv(df_bg: pl.DataFrame) -> pl.DataFrame:
    """Monthly PAYE by background -> annual averages + person counts."""
    df = df_bg.with_columns(
        pl.col("month").str.slice(0, 4).cast(pl.Int32).alias("year"),
        pl.col("value").cast(pl.Float64, strict=False),
    )
    # Pivot Eining (Upphæð vs Fjöldi einstaklinga) to columns
    unit_col = "Eining"
    df_pivot = df.pivot(
        on=unit_col,
        index=["year", "month", "background"],
        values="value",
    )
    # column names will be "Upphæð", "Fjöldi einstaklinga"
    df_pivot = df_pivot.rename(
        {"Upphæð": "amount_isk_thousand", "Fjöldi einstaklinga": "persons"}
    )
    # Hagstofa upphæð in TEK02 series is in thousand ISK — confirm later. We keep raw.
    # Annual: sum amounts and average persons
    annual = df_pivot.group_by(["year", "background"]).agg(
        pl.col("amount_isk_thousand").sum().alias("annual_amount_thousand_isk"),
        pl.col("persons").mean().alias("avg_monthly_persons"),
    )
    # Mean per person per month = (annual_amount / 12) / avg_monthly_persons
    annual = annual.with_columns(
        (pl.col("annual_amount_thousand_isk") * 1000 / 12 / pl.col("avg_monthly_persons"))
        .alias("mean_monthly_wage_per_person_isk")
    )
    annual = annual.sort(["year", "background"])
    annual.write_csv(PROC / "hagstofan_income_by_background.csv")
    print(f"  wrote hagstofan_income_by_background.csv ({len(annual)} rows)")
    return annual


def compute_headline(
    wage_idx: pl.DataFrame,
    income: pl.DataFrame,
    bg: pl.DataFrame,
) -> None:
    print("\n=== HEADLINE COMPUTATION ===")
    # Annual wage index = mean of monthly
    wi_annual = wage_idx.group_by("year").agg(
        pl.col("wage_index").mean().alias("wage_index_avg")
    ).sort("year")
    # Median labor income (all ages)
    med = (
        income.filter(
            (pl.col("source") == "labor_income")
            & (pl.col("metric") == "median")
            & (pl.col("age") == "Allir")
        )
        .select(["year", "value_isk", "real_value_2015isk"])
        .sort("year")
    )
    if med.height == 0:
        # fall back — age label might differ; try Total match
        med = (
            income.filter(
                (pl.col("source") == "labor_income") & (pl.col("metric") == "median")
            )
            .group_by("year")
            .agg(
                pl.col("value_isk").first(),
                pl.col("real_value_2015isk").first(),
                pl.col("age").first(),
            )
            .sort("year")
        )
        print(f"  (fallback age group: {med['age'][0]})")

    wi_by_year = {r["year"]: r["wage_index_avg"] for r in wi_annual.iter_rows(named=True)}
    print("\nWage index annual averages (2015=100 or whatever base):")
    for y in sorted(wi_by_year):
        if y >= 2015:
            print(f"  {y}: {wi_by_year[y]:.1f}")

    print("\nMedian labor income (nominal ISK, real 2015 ISK):")
    for r in med.filter(pl.col("year") >= 2015).iter_rows(named=True):
        print(
            f"  {r['year']}: {r['value_isk']:>12,.0f}  real {r['real_value_2015isk']:>12,.0f}"
        )

    # Compute cumulative change 2015 → latest common year
    common_years = sorted(
        set(wi_by_year) & set(med["year"].to_list()) & {y for y in range(2015, 2100)}
    )
    if not common_years:
        print("no overlap 2015+")
        return
    y0 = 2015
    y1 = max(common_years)
    wi0 = wi_by_year[y0]
    wi1 = wi_by_year[y1]
    med0 = med.filter(pl.col("year") == y0)
    med1 = med.filter(pl.col("year") == y1)
    m0_nom = med0["value_isk"][0]
    m1_nom = med1["value_isk"][0]
    m0_real = med0["real_value_2015isk"][0]
    m1_real = med1["real_value_2015isk"][0]
    wi_g = (wi1 / wi0 - 1) * 100
    med_g_nom = (m1_nom / m0_nom - 1) * 100
    med_g_real = (m1_real / m0_real - 1) * 100
    gap_nom = wi_g - med_g_nom
    print(f"\n--- {y0} -> {y1} ---")
    print(f"Launavísitala cumulative:       {wi_g:+.1f}%  ({wi0:.1f} -> {wi1:.1f})")
    print(f"Median labor income nominal:    {med_g_nom:+.1f}%  ({m0_nom:,.0f} -> {m1_nom:,.0f})")
    print(f"Median labor income real (2015):{med_g_real:+.1f}%  ({m0_real:,.0f} -> {m1_real:,.0f})")
    print(f"GAP (wage index - median nom): {gap_nom:+.1f} pp")

    # Background comparison using TEK02012
    if bg is not None and bg.height > 0:
        isl = bg.filter(pl.col("background") == "Íslenskur bakgrunnur")
        imm = bg.filter(pl.col("background") == "Innflytjendur")
        allbg = bg.filter(pl.col("background") == "Alls")
        years_bg = sorted(set(bg["year"].to_list()))
        y0b = 2015 if 2015 in years_bg else min(years_bg)
        y1b = max(years_bg)

        def mean_pay(df, year):
            row = df.filter(pl.col("year") == year)
            if row.height == 0:
                return None
            return row["mean_monthly_wage_per_person_isk"][0]

        def persons(df, year):
            row = df.filter(pl.col("year") == year)
            if row.height == 0:
                return None
            return row["avg_monthly_persons"][0]

        print(f"\n--- Background (TEK02012, {y0b} -> {y1b}) ---")
        for name, df in [("Íslensk.", isl), ("Innflytj.", imm), ("Alls", allbg)]:
            p0 = mean_pay(df, y0b)
            p1 = mean_pay(df, y1b)
            if p0 and p1:
                g = (p1 / p0 - 1) * 100
                print(f"  {name}: {p0:>10,.0f} -> {p1:>10,.0f} ISK/mo  ({g:+.1f}%)")

        # Share of immigrants in PAYE workforce
        def share(df_imm, df_all, year):
            pi = persons(df_imm, year)
            pa = persons(df_all, year)
            if pi and pa:
                return pi / pa * 100
            return None

        s0 = share(imm, allbg, y0b)
        s1 = share(imm, allbg, y1b)
        if s0 and s1:
            print(
                f"  Immigrant share of paid workers: {s0:.1f}% ({y0b}) -> {s1:.1f}% ({y1b})"
            )

        # Wage ratio
        p0_isl = mean_pay(isl, y0b)
        p1_isl = mean_pay(isl, y1b)
        p0_imm = mean_pay(imm, y0b)
        p1_imm = mean_pay(imm, y1b)
        if all([p0_isl, p1_isl, p0_imm, p1_imm]):
            r0 = p0_imm / p0_isl * 100
            r1 = p1_imm / p1_isl * 100
            print(f"  Imm/Icel ratio: {r0:.1f}% -> {r1:.1f}% ({r1-r0:+.1f} pp)")


def main():
    wi = fetch_wage_index()
    time.sleep(3)
    lab = fetch_labor_income_dist()
    time.sleep(3)
    tot = fetch_total_income_dist()
    time.sleep(3)
    bg_raw = fetch_background_monthly()

    proc = build_processed_csv(lab, tot)
    bg = build_background_csv(bg_raw)
    compute_headline(wi, proc, bg)


if __name__ == "__main__":
    main()

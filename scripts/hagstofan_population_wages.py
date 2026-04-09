#!/usr/bin/env python3
"""
Fetch population by citizenship and wage index by sector from Hagstofan (Statistics Iceland).

Datasets used:
- MAN10001.px: Quarterly population by municipality, sex, citizenship (2010Q4-2025Q4)
- MAN04103.px: Annual population (Jan 1) by citizenship country, sex, age (1998-2025)
- LAU04007.px: Monthly wage index (private market) by economic activity (2015M01-)
- LAU04001.px: Monthly overall wage index (2015M01-)
- VIN10001.px: Monthly employed persons by background (Icelandic / Immigrants) 2005-

Outputs:
- data/raw/hagstofan/{population,wages,labor}/*.json
- data/processed/hagstofan_population_by_citizenship.csv
- data/processed/hagstofan_wages_by_sector.csv
- data/processed/hagstofan_foreign_labor_share.csv
"""

import json
from pathlib import Path

import httpx
import polars as pl

BASE = "https://px.hagstofa.is/pxis/api/v1/is"
ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw" / "hagstofan"
OUT = ROOT / "data" / "processed"

POPULATION_DIR = RAW / "population"
WAGES_DIR = RAW / "wages"
LABOR_DIR = RAW / "labor"

for d in (POPULATION_DIR, WAGES_DIR, LABOR_DIR, OUT):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Country → citizenship group mapping (ISO-style)
# ---------------------------------------------------------------------------

# EEA/EU countries (major labor-source countries get their own slot)
EEA_COUNTRIES = {
    "Austurríki", "Belgía", "Búlgaría", "Kýpur", "Tékkland", "Danmörk",
    "Eistland", "Finnland", "Frakkland", "Þýskaland", "Grikkland",
    "Ungverjaland", "Írland", "Ítalía", "Lettland", "Litháen",
    "Lúxemborg", "Malta", "Holland", "Pólland", "Portúgal",
    "Rúmenía", "Slóvakía", "Slóvenía", "Spánn", "Svíþjóð",
    "Ísland",  # handled separately
    "Noregur", "Liechtenstein",
    "Króatía",
}

# Countries of particular interest for labor-import narrative
FOCUS_COUNTRIES = {
    "Pólland": "PL",
    "Rúmenía": "RO",
    "Litháen": "LT",
    "Lettland": "LV",
    "Portúgal": "PT",
    "Úkraína": "UA",
    "Búlgaría": "BG",
    "Þýskaland": "DE",
    "Danmörk": "DK",
    "Svíþjóð": "SE",
    "Noregur": "NO",
    "Filippseyjar": "PH",
    "Taíland": "TH",
    "Víetnam": "VN",
    "Bandaríkin": "US",
    "Bretland": "GB",
    "Spánn": "ES",
    "Ítalía": "IT",
}


def post_json(path: str, query: list[dict]) -> dict:
    """Post a PX-Web query and return JSON-stat-like dict."""
    url = f"{BASE}/{path}"
    body = {"query": query, "response": {"format": "json-stat2"}}
    r = httpx.post(url, json=body, timeout=120)
    r.raise_for_status()
    return r.json()


def fetch_metadata(path: str) -> dict:
    r = httpx.get(f"{BASE}/{path}", timeout=60)
    r.raise_for_status()
    return r.json()


def jsonstat_to_records(data: dict) -> list[dict]:
    """Convert a json-stat2 response to a list of dict records."""
    dims = data["dimension"]
    dim_ids = data["id"]
    sizes = data["size"]
    values = data["value"]

    # For each dim, build an ordered list of (code, label)
    dim_codes: list[list[str]] = []
    dim_labels: list[list[str]] = []
    for did in dim_ids:
        dim = dims[did]
        cat = dim["category"]
        index_map = cat["index"]  # code -> position
        label_map = cat["label"]
        # Order by position
        ordered = sorted(index_map.items(), key=lambda kv: kv[1])
        codes = [c for c, _ in ordered]
        labels = [label_map.get(c, c) for c, _ in ordered]
        dim_codes.append(codes)
        dim_labels.append(labels)

    # values can be dict (sparse) or list (dense)
    total = 1
    for s in sizes:
        total *= s

    def idx_to_coords(idx: int) -> list[int]:
        coords = []
        for s in reversed(sizes):
            coords.append(idx % s)
            idx //= s
        return list(reversed(coords))

    if isinstance(values, list):
        iterator = enumerate(values)
    else:
        iterator = ((int(k), v) for k, v in values.items())

    records = []
    for idx, v in iterator:
        if v is None:
            continue
        coords = idx_to_coords(idx)
        rec = {}
        for i, c in enumerate(coords):
            rec[dim_ids[i] + "_code"] = dim_codes[i][c]
            rec[dim_ids[i] + "_label"] = dim_labels[i][c]
        rec["value"] = v
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# A. Population — quarterly total + annual by country
# ---------------------------------------------------------------------------

def fetch_population_quarterly():
    """MAN10001: quarterly, total country, Ísl. vs Erl. ríkisborgarar."""
    path = "Ibuar/mannfjoldi/1_yfirlit/arsfjordungstolur/MAN10001.px"
    meta = fetch_metadata(path)
    (POPULATION_DIR / "MAN10001_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    # Keep only Alls municipality, Alls/Íslenskir/Erlendir from Kyn og ríkisfang,
    # all quarters 2010Á4-present.
    query = [
        {"code": "Sveitarfélag", "selection": {"filter": "item", "values": ["0.0"]}},  # Alls
        {"code": "Kyn og ríkisfang", "selection": {"filter": "item",
                                                    "values": ["0", "4", "5"]}},  # Alls, Ísl., Erl.
    ]
    # We need to look up the actual code values from metadata for Sveitarfélag = Alls
    # and Kyn og ríkisfang codes.
    var_map = {v["code"]: v for v in meta["variables"]}

    svf = var_map["Sveitarfélag"]
    alls_sveit = svf["values"][svf["valueTexts"].index("Alls")]

    kyn = var_map["Kyn og ríkisfang"]
    wanted = {"Alls": None, "Ísl. ríkisborgarar": None, "Erl. ríkisborgarar": None}
    for code, text in zip(kyn["values"], kyn["valueTexts"]):
        if text in wanted:
            wanted[text] = code

    query = [
        {"code": "Sveitarfélag", "selection": {"filter": "item", "values": [alls_sveit]}},
        {"code": "Kyn og ríkisfang", "selection": {"filter": "item",
                                                    "values": [v for v in wanted.values() if v]}},
    ]
    data = post_json(path, query)
    (POPULATION_DIR / "MAN10001_quarterly.json").write_text(json.dumps(data, ensure_ascii=False))
    recs = jsonstat_to_records(data)
    return recs


def fetch_population_by_country():
    """MAN04103: annual Jan 1, population by citizenship (country), all ages/sex."""
    path = "Ibuar/mannfjoldi/3_bakgrunnur/Rikisfang/MAN04103.px"
    meta = fetch_metadata(path)
    (POPULATION_DIR / "MAN04103_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    var_map = {v["code"]: v for v in meta["variables"]}

    # Years 2010-latest
    year_var = var_map["Ár"]
    years = [c for c, t in zip(year_var["values"], year_var["valueTexts"]) if int(t) >= 2010]

    # Age = Alls
    aldur = var_map["Aldur"]
    alls_aldur = aldur["values"][aldur["valueTexts"].index("Alls")]

    # Sex = Alls
    kyn = var_map["Kyn"]
    alls_kyn = kyn["values"][kyn["valueTexts"].index("Alls")]

    # All citizenship countries
    rikisfang = var_map["Ríkisfang"]
    all_countries = rikisfang["values"]

    query = [
        {"code": "Ríkisfang", "selection": {"filter": "item", "values": all_countries}},
        {"code": "Aldur", "selection": {"filter": "item", "values": [alls_aldur]}},
        {"code": "Ár", "selection": {"filter": "item", "values": years}},
        {"code": "Kyn", "selection": {"filter": "item", "values": [alls_kyn]}},
    ]

    data = post_json(path, query)
    (POPULATION_DIR / "MAN04103_by_country.json").write_text(json.dumps(data, ensure_ascii=False))
    return jsonstat_to_records(data)


def build_population_csv(quarterly: list[dict], by_country: list[dict]) -> pl.DataFrame:
    """Build tidy long CSV: date, citizenship_group, country_code, count, pct_of_total."""
    rows = []

    # --- Quarterly (2010Q4+): Alls/Ísl./Erl. only, country_code=None ---
    group_map = {
        "Alls": "total",
        "Ísl. ríkisborgarar": "icelandic",
        "Erl. ríkisborgarar": "foreign",
    }
    # pivot quarterly by date
    qdf = pl.DataFrame(quarterly)
    if not qdf.is_empty():
        qdf = qdf.with_columns(
            pl.col("Ársfjórðungur_label").alias("date_raw"),
            pl.col("Kyn og ríkisfang_label").alias("group_label"),
            pl.col("value").cast(pl.Int64),
        )
        # Convert "2010Á4" -> "2010-Q4"
        qdf = qdf.with_columns(
            pl.col("date_raw").str.replace("Á", "-Q").alias("date"),
            pl.col("group_label").replace(group_map, default="other").alias("citizenship_group"),
        ).select(["date", "citizenship_group", "value"])

        # Compute pct_of_total per date
        totals = qdf.filter(pl.col("citizenship_group") == "total").select(
            ["date", pl.col("value").alias("total")]
        )
        qdf = qdf.join(totals, on="date", how="left").with_columns(
            (pl.col("value") / pl.col("total") * 100).round(3).alias("pct_of_total")
        )
        for r in qdf.iter_rows(named=True):
            rows.append({
                "date": r["date"],
                "citizenship_group": r["citizenship_group"],
                "country_code": None,
                "count": r["value"],
                "pct_of_total": r["pct_of_total"],
                "source": "MAN10001",
            })

    # --- Annual by country: date = YYYY-01-01, group = foreign|icelandic, country_code set ---
    cdf = pl.DataFrame(by_country)
    if not cdf.is_empty():
        cdf = cdf.with_columns(
            pl.col("Ríkisfang_label").alias("country"),
            pl.col("Ár_label").alias("year"),
            pl.col("value").cast(pl.Int64),
        ).select(["country", "year", "value"])

        # Total per year (Alls row)
        year_totals = (
            cdf.filter(pl.col("country") == "Alls")
            .select(["year", pl.col("value").alias("total")])
        )

        # Icelandic per year
        isl = cdf.filter(pl.col("country") == "Ísland").select([
            pl.col("year"),
            pl.lit("icelandic").alias("citizenship_group"),
            pl.lit(None, dtype=pl.Utf8).alias("country_code"),
            pl.col("value").alias("count"),
        ])

        alls = cdf.filter(pl.col("country") == "Alls").select([
            pl.col("year"),
            pl.lit("total").alias("citizenship_group"),
            pl.lit(None, dtype=pl.Utf8).alias("country_code"),
            pl.col("value").alias("count"),
        ])

        # Foreign: sum of all != Ísland, != Alls
        foreign = (
            cdf.filter((pl.col("country") != "Ísland") & (pl.col("country") != "Alls"))
            .group_by("year").agg(pl.col("value").sum().alias("count"))
            .with_columns(
                pl.lit("foreign").alias("citizenship_group"),
                pl.lit(None, dtype=pl.Utf8).alias("country_code"),
            )
            .select(["year", "citizenship_group", "country_code", "count"])
        )

        # EEA aggregate (excluding Ísland)
        eea_countries = EEA_COUNTRIES - {"Ísland"}
        eea = (
            cdf.filter(pl.col("country").is_in(list(eea_countries)))
            .group_by("year").agg(pl.col("value").sum().alias("count"))
            .with_columns(
                pl.lit("eea_ex_iceland").alias("citizenship_group"),
                pl.lit("EEA").alias("country_code"),
            )
            .select(["year", "citizenship_group", "country_code", "count"])
        )

        # Per-focus-country
        focus_rows = []
        for is_name, iso in FOCUS_COUNTRIES.items():
            sub = cdf.filter(pl.col("country") == is_name).select([
                pl.col("year"),
                pl.lit("country").alias("citizenship_group"),
                pl.lit(iso).alias("country_code"),
                pl.col("value").alias("count"),
            ])
            if not sub.is_empty():
                focus_rows.append(sub)

        stacked = pl.concat([alls, isl, foreign, eea] + focus_rows, how="vertical")
        stacked = stacked.join(year_totals, on="year", how="left").with_columns(
            (pl.col("count") / pl.col("total") * 100).round(3).alias("pct_of_total"),
            (pl.col("year") + "-01-01").alias("date"),
        )
        for r in stacked.iter_rows(named=True):
            rows.append({
                "date": r["date"],
                "citizenship_group": r["citizenship_group"],
                "country_code": r["country_code"],
                "count": r["count"],
                "pct_of_total": r["pct_of_total"],
                "source": "MAN04103",
            })

    schema = {
        "date": pl.Utf8,
        "citizenship_group": pl.Utf8,
        "country_code": pl.Utf8,
        "count": pl.Int64,
        "pct_of_total": pl.Float64,
        "source": pl.Utf8,
    }
    df = pl.DataFrame(rows, schema=schema).sort(
        ["source", "date", "citizenship_group", "country_code"]
    )
    return df


# ---------------------------------------------------------------------------
# B. Wages by sector
# ---------------------------------------------------------------------------

SECTOR_NAME_EN = {
    "TOTAL": "Total private market",
    "C": "Manufacturing",
    "D_E": "Utilities",
    "F": "Construction",
    "G": "Wholesale and retail trade",
    "H": "Transportation and storage",
    "I": "Accommodation and food service",
    "J": "Information and communication",
    "K": "Financial and insurance activities",
}

def fetch_wages_by_sector():
    path = "Samfelag/launogtekjur/2_lvt/1_manadartolur/LAU04007.px"
    meta = fetch_metadata(path)
    (WAGES_DIR / "LAU04007_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    var_map = {v["code"]: v for v in meta["variables"]}
    manuaur = var_map["Mánuður"]
    # Keep everything 2015M01 onward (all of it)
    months = [c for c in manuaur["values"]]
    sectors = var_map["Atvinnugrein"]["values"]  # all 9
    eining = var_map["Eining"]
    # Keep 'index' and 'change_A'
    eining_vals = [c for c, t in zip(eining["values"], eining["valueTexts"])
                   if c in ("index", "change_A")]
    visitala = var_map["Vísitala"]
    # Only launavísitala (LVT) — the headline
    lvt_code = visitala["values"][visitala["valueTexts"].index("Launavísitala")]

    query = [
        {"code": "Mánuður", "selection": {"filter": "item", "values": months}},
        {"code": "Vísitala", "selection": {"filter": "item", "values": [lvt_code]}},
        {"code": "Atvinnugrein", "selection": {"filter": "item", "values": sectors}},
        {"code": "Eining", "selection": {"filter": "item", "values": eining_vals}},
    ]
    data = post_json(path, query)
    (WAGES_DIR / "LAU04007_wages_by_sector.json").write_text(json.dumps(data, ensure_ascii=False))
    return jsonstat_to_records(data)


def fetch_wages_overall():
    """LAU04001: overall wage index, monthly from 2015."""
    path = "Samfelag/launogtekjur/2_lvt/1_manadartolur/LAU04001.px"
    meta = fetch_metadata(path)
    (WAGES_DIR / "LAU04001_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    var_map = {v["code"]: v for v in meta["variables"]}
    months = var_map["Mánuður"]["values"]
    visitala = var_map["Vísitala"]
    lvt = visitala["values"][visitala["valueTexts"].index("Launavísitala")]
    eining = var_map["Eining"]
    eining_vals = [c for c, t in zip(eining["values"], eining["valueTexts"])
                   if c in ("index", "change_A")]

    query = [
        {"code": "Mánuður", "selection": {"filter": "item", "values": months}},
        {"code": "Vísitala", "selection": {"filter": "item", "values": [lvt]}},
        {"code": "Eining", "selection": {"filter": "item", "values": eining_vals}},
    ]
    data = post_json(path, query)
    (WAGES_DIR / "LAU04001_wages_overall.json").write_text(json.dumps(data, ensure_ascii=False))
    return jsonstat_to_records(data)


def build_wages_csv(sector_recs: list[dict], overall_recs: list[dict]) -> pl.DataFrame:
    """Tidy CSV: date, sector_code, sector_name_is, sector_name_en, wage_index, yoy_pct."""
    df = pl.DataFrame(sector_recs)

    # Pivot: index + change_A side-by-side
    df = df.with_columns(
        pl.col("Mánuður_label").alias("month_raw"),
        pl.col("Atvinnugrein_code").alias("sector_code"),
        pl.col("Atvinnugrein_label").alias("sector_name_is"),
        pl.col("Eining_code").alias("metric"),
        pl.col("value").cast(pl.Float64),
    ).select(["month_raw", "sector_code", "sector_name_is", "metric", "value"])

    wide = df.pivot(on="metric", index=["month_raw", "sector_code", "sector_name_is"], values="value")
    wide = wide.rename({"index": "wage_index", "change_A": "yoy_pct"}) \
        .with_columns(
            # "2015M01" -> "2015-01"
            (pl.col("month_raw").str.slice(0, 4) + "-" + pl.col("month_raw").str.slice(5, 2)).alias("date"),
            pl.col("sector_code").replace(SECTOR_NAME_EN, default="Unknown").alias("sector_name_en"),
        )

    wide = wide.select([
        "date", "sector_code", "sector_name_is", "sector_name_en", "wage_index", "yoy_pct"
    ]).sort(["sector_code", "date"])

    # Append overall LAU04001 as sector_code='OVERALL_ALL'
    if overall_recs:
        odf = pl.DataFrame(overall_recs).with_columns(
            pl.col("Mánuður_label").alias("month_raw"),
            pl.col("Eining_code").alias("metric"),
            pl.col("value").cast(pl.Float64),
        ).select(["month_raw", "metric", "value"])

        owide = odf.pivot(on="metric", index="month_raw", values="value")
        owide = owide.rename({"index": "wage_index", "change_A": "yoy_pct"}).with_columns(
            (pl.col("month_raw").str.slice(0, 4) + "-" + pl.col("month_raw").str.slice(5, 2)).alias("date"),
            pl.lit("OVERALL_ALL").alias("sector_code"),
            pl.lit("Launavísitala (heild)").alias("sector_name_is"),
            pl.lit("General wage index (all labor market)").alias("sector_name_en"),
        ).select(["date", "sector_code", "sector_name_is", "sector_name_en", "wage_index", "yoy_pct"])

        wide = pl.concat([wide, owide], how="vertical").sort(["sector_code", "date"])

    return wide


# ---------------------------------------------------------------------------
# C. Foreign labor share (VIN10001)
# ---------------------------------------------------------------------------

def fetch_labor_by_background():
    path = "Samfelag/vinnumarkadur/vinnuaflskraargogn/VIN10001.px"
    meta = fetch_metadata(path)
    (LABOR_DIR / "VIN10001_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    var_map = {v["code"]: v for v in meta["variables"]}
    months = var_map["Mánuður"]["values"]
    kyn = var_map["Kyn"]["values"][0]  # Alls
    aldur = var_map["Aldursflokkar"]
    total_age = aldur["values"][aldur["valueTexts"].index("Alls")]
    uppruni = var_map["Uppruni"]["values"]  # Alls, Íslenskur bakgrunnur, Innflytjendur
    loghemili = var_map["Lögheimili"]
    loghemili_alls = loghemili["values"][0]  # Alls

    query = [
        {"code": "Mánuður", "selection": {"filter": "item", "values": months}},
        {"code": "Kyn", "selection": {"filter": "item", "values": [kyn]}},
        {"code": "Aldursflokkar", "selection": {"filter": "item", "values": [total_age]}},
        {"code": "Uppruni", "selection": {"filter": "item", "values": uppruni}},
        {"code": "Lögheimili", "selection": {"filter": "item", "values": [loghemili_alls]}},
    ]
    data = post_json(path, query)
    (LABOR_DIR / "VIN10001_labor_background.json").write_text(json.dumps(data, ensure_ascii=False))
    return jsonstat_to_records(data)


def build_labor_csv(recs: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(recs)
    df = df.with_columns(
        pl.col("Mánuður_label").alias("month_raw"),
        pl.col("Uppruni_label").alias("background"),
        pl.col("value").cast(pl.Int64),
    ).select(["month_raw", "background", "value"])

    wide = df.pivot(on="background", index="month_raw", values="value")

    # Rename columns safely
    rename_map = {}
    for col in wide.columns:
        if col == "Alls":
            rename_map[col] = "total_employed"
        elif col == "Íslenskur bakgrunnur":
            rename_map[col] = "icelandic_background"
        elif col == "Innflytjendur":
            rename_map[col] = "immigrants"
    wide = wide.rename(rename_map)

    wide = wide.with_columns(
        (pl.col("month_raw").str.slice(0, 4) + "-" + pl.col("month_raw").str.slice(5, 2)).alias("date"),
        (pl.col("immigrants") / pl.col("total_employed") * 100).round(3).alias("immigrant_share_pct"),
    ).select([
        "date", "total_employed", "icelandic_background", "immigrants", "immigrant_share_pct"
    ]).sort("date")

    return wide


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("A. Population")
    print("=" * 60)
    print("Fetching MAN10001 (quarterly)...")
    q = fetch_population_quarterly()
    print(f"  Got {len(q)} records")

    print("Fetching MAN04103 (annual by country)...")
    c = fetch_population_by_country()
    print(f"  Got {len(c)} records")

    pop_df = build_population_csv(q, c)
    pop_out = OUT / "hagstofan_population_by_citizenship.csv"
    pop_df.write_csv(pop_out)
    print(f"Saved population CSV: {pop_out} ({len(pop_df)} rows)")

    print()
    print("=" * 60)
    print("B. Wages")
    print("=" * 60)
    print("Fetching LAU04007 (wages by sector)...")
    wages = fetch_wages_by_sector()
    print(f"  Got {len(wages)} records")

    print("Fetching LAU04001 (overall)...")
    overall = fetch_wages_overall()
    print(f"  Got {len(overall)} records")

    wage_df = build_wages_csv(wages, overall)
    wage_out = OUT / "hagstofan_wages_by_sector.csv"
    wage_df.write_csv(wage_out)
    print(f"Saved wages CSV: {wage_out} ({len(wage_df)} rows)")

    print()
    print("=" * 60)
    print("C. Foreign labor share")
    print("=" * 60)
    print("Fetching VIN10001 (employed by background)...")
    labor = fetch_labor_by_background()
    print(f"  Got {len(labor)} records")

    lab_df = build_labor_csv(labor)
    lab_out = OUT / "hagstofan_foreign_labor_share.csv"
    lab_df.write_csv(lab_out)
    print(f"Saved labor CSV: {lab_out} ({len(lab_df)} rows)")

    # ---- Quick stats printout for the report ----
    print()
    print("=" * 60)
    print("KEY OBSERVATIONS")
    print("=" * 60)

    # Foreign citizen share (annual, from MAN04103)
    annual = pop_df.filter(pl.col("source") == "MAN04103")
    foreign_yr = annual.filter(pl.col("citizenship_group") == "foreign").select(
        [pl.col("date").str.slice(0, 4).alias("year"),
         pl.col("count").alias("foreign_count"),
         pl.col("pct_of_total").alias("foreign_pct")]
    )
    total_yr = annual.filter(pl.col("citizenship_group") == "total").select(
        [pl.col("date").str.slice(0, 4).alias("year"),
         pl.col("count").alias("total_pop")]
    )
    merged = foreign_yr.join(total_yr, on="year").sort("year")
    print("\nForeign citizen share of total population (annual, Jan 1):")
    print(merged)

    # Latest quarterly
    quart = pop_df.filter(pl.col("source") == "MAN10001")
    q_foreign = quart.filter(pl.col("citizenship_group") == "foreign").sort("date").tail(5)
    print("\nLatest quarterly foreign share:")
    print(q_foreign.select(["date", "count", "pct_of_total"]))

    # Wage growth 2020 -> latest (cumulative) for target sectors
    targets = ["C", "F", "G", "I", "TOTAL", "OVERALL_ALL"]
    wsub = wage_df.filter(pl.col("sector_code").is_in(targets))
    jan_2020 = wsub.filter(pl.col("date") == "2020-01")
    latest_date = wsub.sort("date").tail(1).item(0, "date")
    latest = wsub.filter(pl.col("date") == latest_date)
    print(f"\nWage index 2020-01 vs {latest_date} (target sectors):")
    print("sector_code | 2020-01 | latest | cum %")
    for sc in targets:
        v20 = jan_2020.filter(pl.col("sector_code") == sc).select("wage_index").to_series()
        vlast = latest.filter(pl.col("sector_code") == sc).select("wage_index").to_series()
        if len(v20) and len(vlast):
            pct = (vlast[0] / v20[0] - 1) * 100
            print(f"  {sc:12s} | {v20[0]:7.2f} | {vlast[0]:7.2f} | {pct:+.2f}%")

    # Immigrant share of employment
    print("\nImmigrant share of employment (latest 3 months):")
    print(lab_df.sort("date").tail(3).select(["date", "immigrant_share_pct"]))
    print("\nImmigrant share for Jan 2015, Jan 2020, latest:")
    for dt in ["2015-01", "2020-01"]:
        row = lab_df.filter(pl.col("date") == dt)
        if not row.is_empty():
            print(f"  {dt}: {row.item(0, 'immigrant_share_pct'):.2f}%")
    latest_lab = lab_df.sort("date").tail(1)
    print(f"  {latest_lab.item(0, 'date')}: {latest_lab.item(0, 'immigrant_share_pct'):.2f}%")


if __name__ == "__main__":
    main()

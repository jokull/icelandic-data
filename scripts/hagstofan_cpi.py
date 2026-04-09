#!/usr/bin/env python3
"""
Fetch CPI (vísitala neysluverðs) sub-component data from Hagstofan PX-Web API
for inflation decomposition analysis (tradables vs domestic vs services vs housing).

Sources (three tables, stitched together on overlapping months to handle the
June 2024 housing methodology change where possible):
  - VIS01000 (headline CPI, grunnur 1988=100, 1988-present)
  - VIS01300 (sub-indices CPXX, 2025M01-present)
  - VIS01304 (archive sub-indices ISXX, grunnur 2008=100, 2008-2025)
  - VIS01101 (nature/origin split CPI.., 2024M12-present)
  - VIS01102 (archive nature/origin split, 1997-2025, using index_B2008)

Because the archive tables end 2025M12 and the current tables only begin in
2024M12 / 2025M01, there is an overlap window we use to rebase the newer
series onto the Jan 2008 = 100 base (matching VIS01304 / VIS01102).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import polars as pl

BASE_URL = "https://px.hagstofa.is/pxis/api/v1/is"
ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "hagstofan" / "cpi"
PROCESSED = ROOT / "data" / "processed" / "hagstofan_cpi_components.csv"
RAW_DIR.mkdir(parents=True, exist_ok=True)

START = "2015M01"  # earliest month we want


# --- Series catalog ----------------------------------------------------------
# (series_code, series_name_is, series_name_en, coicop_level,
#  archive_table_path, archive_value, current_table_path, current_value)

SERIES = [
    # Headline CPI (use VIS01000 which spans 1988-present)
    ("CPI", "Vísitala neysluverðs", "Consumer price index (headline)", "headline",
     None, None,
     "Efnahagur/visitolur/1_vnv/1_vnv/VIS01000.px", "CPI"),

    # COICOP main groups (archive IS.. 2008-2025, current CP.. 2025M01+)
    ("CP01", "01 Matur og óáfengir drykkir", "01 Food and non-alcoholic beverages", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS01",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP01"),
    ("CP02", "02 Áfengir drykkir og tóbak", "02 Alcoholic beverages and tobacco", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS02",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP02"),
    ("CP03", "03 Fatnaður og skófatnaður", "03 Clothing and footwear", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS03",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP03"),
    ("CP04", "04 Húsnæði, hiti og rafmagn", "04 Housing, water, electricity, gas and other fuels", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS04",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP04"),
    ("CP05", "05 Húsgögn, heimilisbúnaður", "05 Furnishings, household equipment", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS05",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP05"),
    ("CP06", "06 Heilsa", "06 Health", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS06",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP06"),
    ("CP07", "07 Ferðir og flutningar", "07 Transport", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS07",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP07"),
    ("CP08", "08 Póstur og sími / Upplýsingar og fjarskipti", "08 Communication / Information and communication", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS08",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP08"),
    ("CP09", "09 Tómstundir og menning / Afþreying", "09 Recreation and culture", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS09",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP09"),
    ("CP10", "10 Menntun", "10 Education", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS10",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP10"),
    ("CP11", "11 Hótel og veitingastaðir", "11 Restaurants and accommodation", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS11",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP11"),
    ("CP12", "12 Aðrar vörur og þjónusta", "12 Miscellaneous goods and services", "COICOP-1",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS12",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP12"),

    # Housing sub-components
    ("CP041", "041 Greidd húsaleiga", "041 Actual rentals for housing", "COICOP-3",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS041",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP041"),
    ("CP042", "042 Reiknuð húsaleiga", "042 Imputed rentals for owner-occupied housing", "COICOP-3",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01304.px", "IS042",
     "Efnahagur/visitolur/1_vnv/2_undirvisitolur/VIS01300.px", "CP042"),

    # Nature/origin split (archive VIS01102, current VIS01101)
    ("CPI_imported", "Innfluttar vörur alls", "Imported goods (all)", "analytical",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01102.px", "5to9",
     "Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01101.px", "2ai"),
    ("CPI_domestic_ex_agri", "Innlendar vörur án búvöru og grænmetis", "Domestic goods excl. agri/veg", "analytical",
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01102.px", "3to4",
     "Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01101.px", "2c"),
    ("CPI_services", "Þjónusta", "Services (all)", "analytical",
     # archive VIS01102 only has '11 Opinber þjónusta' + '12 Önnur þjónusta' separately
     # we sum them into services below during fetch (special-case)
     "Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01102.px", "SERVICES_SUM",
     "Efnahagur/visitolur/1_vnv/3_greiningarvisitolur/VIS01101.px", "5"),
]


# --- Fetch helpers ------------------------------------------------------------

def _post(url: str, body: dict) -> dict:
    r = httpx.post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_json(table_path: str, query: list[dict], out_file: Path) -> dict:
    """POST to PX-Web; save raw JSON and return parsed body."""
    url = f"{BASE_URL}/{table_path}"
    body = {"query": query, "response": {"format": "json"}}
    data = _post(url, body)
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def px_to_df(payload: dict) -> pl.DataFrame:
    """
    PX-Web 'json' format returns a list of {key: [..], values: [..]} rows.
    Columns names come from payload['columns'].
    Convert to a tidy DataFrame with explicit schema.
    """
    columns = payload.get("columns", [])
    dim_cols = [c["code"] for c in columns if c.get("type") in ("t", "d")]
    val_cols = [c["code"] for c in columns if c.get("type") == "c"]

    # Build column-wise lists so polars doesn't have to infer from heterogeneous rows
    data: dict[str, list] = {k: [] for k in dim_cols}
    data["_metric"] = []
    data["_value"] = []

    for item in payload.get("data", []):
        key = item["key"]
        values = item["values"]
        key_map = dict(zip(dim_cols, key))
        for vc, v in zip(val_cols, values):
            for k in dim_cols:
                data[k].append(key_map[k])
            data["_metric"].append(vc)
            try:
                data["_value"].append(
                    float(v) if v not in ("", "..", ".", None) else None
                )
            except (ValueError, TypeError):
                data["_value"].append(None)

    schema = {k: pl.Utf8 for k in dim_cols}
    schema["_metric"] = pl.Utf8
    schema["_value"] = pl.Float64
    return pl.DataFrame(data, schema=schema)


def fetch_series_archive(table_path: str, value_code: str, value_var: str,
                         index_metric: str, out_file: Path) -> pl.DataFrame:
    """Fetch a single series from an archive/historical table using value list."""
    query = [
        {"code": value_var, "selection": {"filter": "item", "values": [value_code]}},
        {"code": "Liður", "selection": {"filter": "item", "values": [index_metric]}},
    ]
    data = fetch_json(table_path, query, out_file)
    df = px_to_df(data)
    return df


def fetch_services_archive_sum(out_file: Path) -> pl.DataFrame:
    """
    Archive VIS01102 has no single 'services' row. Sum items 11 (public services)
    and 12 (other services) using their weight-weighted average. Since we only
    have the indices (not weights) at row level here, we fetch index_B2008 for
    both items and the headline CPI, then reconstruct services as a simple
    weight-weighted index using VIS01102's 'breakdown' (vægi) field, or
    fall back to equal-weight chain-linking via the current series rebasing.

    Simpler: fetch both series, return long DF with both; we'll chain with
    current VIS01101 services '5' at the overlap month instead.
    """
    query = [
        {"code": "Útgjaldaflokkur", "selection": {"filter": "item", "values": ["11", "12"]}},
        {"code": "Liður", "selection": {"filter": "item", "values": ["index_B2008", "breakdown"]}},
    ]
    data = fetch_json("Efnahagur/visitolur/1_vnv/4_eldraefni/VIS01102.px", query, out_file)
    return px_to_df(data)


def month_to_date(m: str) -> str:
    # "2015M01" -> "2015-01-01"
    y = m[:4]
    mm = m[5:]
    return f"{y}-{mm}-01"


def tidy_long(df: pl.DataFrame, series_code: str, series_name_is: str,
              series_name_en: str, coicop_level: str,
              month_col: str, index_col_name: str) -> pl.DataFrame:
    """Filter to index metric, rename to canonical schema.

    `index_col_name` is matched against either the `_metric` column (which holds
    the PX value-column label) or the `Liður` column (when the table has a
    Liður dimension like 'index' / 'index_B2008').
    """
    if df.is_empty():
        return pl.DataFrame()
    if "Liður" in df.columns:
        out = df.filter(pl.col("Liður") == index_col_name)
    else:
        # tables without a Liður dim: take all rows (there's only one c-col)
        out = df
    out = out.select(
        pl.col(month_col).alias("_month"),
        pl.col("_value").alias("value_index"),
    ).drop_nulls("value_index")
    out = out.with_columns([
        pl.lit(series_code).alias("series_code"),
        pl.lit(series_name_is).alias("series_name_is"),
        pl.lit(series_name_en).alias("series_name_en"),
        pl.lit(coicop_level).alias("coicop_level"),
    ])
    out = out.with_columns(
        pl.col("_month").map_elements(month_to_date, return_dtype=pl.Utf8).alias("date")
    )
    return out.select(["date", "series_code", "series_name_is", "series_name_en",
                       "coicop_level", "value_index"])


def chain_link(archive: pl.DataFrame, current: pl.DataFrame) -> pl.DataFrame:
    """
    Chain-link current series onto archive base at the latest overlap month.
    If no overlap, append directly.
    """
    if archive.is_empty():
        return current
    if current.is_empty():
        return archive

    overlap = (archive.join(current, on="date", how="inner", suffix="_c")
               .select(["date", "value_index", "value_index_c"])
               .sort("date"))
    if overlap.is_empty():
        # no overlap - use archive only, print warning
        return archive

    # latest overlap month
    last = overlap.tail(1).to_dicts()[0]
    scale = last["value_index"] / last["value_index_c"] if last["value_index_c"] else 1.0

    # Split current into archive-only vs after-archive
    archive_last = archive["date"].max()
    after = current.filter(pl.col("date") > archive_last).with_columns(
        (pl.col("value_index") * scale).alias("value_index")
    )
    return pl.concat([archive, after]).sort("date")


def add_changes(df: pl.DataFrame) -> pl.DataFrame:
    """Compute MoM % and YoY % per series."""
    df = df.sort(["series_code", "date"])
    df = df.with_columns(
        pl.col("value_index").pct_change().over("series_code").alias("mom_pct"),
        ((pl.col("value_index") / pl.col("value_index").shift(12).over("series_code")) - 1)
            .alias("yoy_pct"),
    )
    # multiply by 100
    df = df.with_columns(
        (pl.col("mom_pct") * 100).round(3),
        (pl.col("yoy_pct") * 100).round(3),
    )
    return df


# --- Main ---------------------------------------------------------------------

def main():
    all_rows: list[pl.DataFrame] = []

    for spec in SERIES:
        (series_code, name_is, name_en, level,
         archive_path, archive_val, current_path, current_val) = spec

        print(f"\n[{series_code}] {name_is}")

        # ---- Fetch current data ----
        current_df = pl.DataFrame()
        if current_path:
            # Determine variable name and metric name for this table
            if "VIS01000" in current_path:
                var_name = "Vísitala"
                metric_name = "index"
            elif "VIS01300" in current_path:
                var_name = "Undirvísitala"
                metric_name = "index"
            elif "VIS01101" in current_path:
                var_name = "Útgjaldaflokkur"
                metric_name = "index"
            else:
                var_name = "Undirvísitala"
                metric_name = "index"

            out_file = RAW_DIR / f"{series_code}_current.json"
            try:
                query = [
                    {"code": var_name, "selection": {"filter": "item", "values": [current_val]}},
                    {"code": "Liður", "selection": {"filter": "item", "values": [metric_name]}},
                ]
                data = fetch_json(current_path, query, out_file)
                df = px_to_df(data)
                month_col = "Mánuður"
                current_df = tidy_long(df, series_code, name_is, name_en, level,
                                       month_col, metric_name)
                print(f"  current: {len(current_df)} rows "
                      f"({current_df['date'].min()}..{current_df['date'].max()})" if len(current_df) else "  current: empty")
            except Exception as e:
                print(f"  WARN current fetch failed: {e}")

        # ---- Fetch archive data ----
        archive_df = pl.DataFrame()
        if archive_path and archive_val:
            out_file = RAW_DIR / f"{series_code}_archive.json"
            try:
                if archive_val == "SERVICES_SUM":
                    # Special handling: fetch VIS01102 items 11+12, weight-sum
                    raw = fetch_services_archive_sum(out_file)
                    # Filter to index_B2008 vs breakdown via Liður dim
                    idx = raw.filter(pl.col("Liður") == "index_B2008")
                    wts = raw.filter(pl.col("Liður") == "breakdown")
                    # Need weights per month x item
                    idx_w = idx.select(["Útgjaldaflokkur", "Mánuður", "_value"]).rename({"_value": "idx"})
                    wts_w = wts.select(["Útgjaldaflokkur", "Mánuður", "_value"]).rename({"_value": "wt"})
                    merged = idx_w.join(wts_w,
                                        on=["Útgjaldaflokkur", "Mánuður"],
                                        how="inner")
                    # weight-average index per month
                    services = (merged
                                .group_by("Mánuður")
                                .agg(
                                    ((pl.col("idx") * pl.col("wt")).sum() /
                                     pl.col("wt").sum()).alias("value_index")
                                )
                                .sort("Mánuður"))
                    services = services.with_columns(
                        pl.col("Mánuður").map_elements(month_to_date, return_dtype=pl.Utf8).alias("date"),
                        pl.lit(series_code).alias("series_code"),
                        pl.lit(name_is).alias("series_name_is"),
                        pl.lit(name_en).alias("series_name_en"),
                        pl.lit(level).alias("coicop_level"),
                    ).select(["date", "series_code", "series_name_is", "series_name_en",
                              "coicop_level", "value_index"])
                    archive_df = services
                elif "VIS01304" in archive_path:
                    query = [
                        {"code": "Undirvísitala",
                         "selection": {"filter": "item", "values": [archive_val]}},
                    ]
                    data = fetch_json(archive_path, query, out_file)
                    df = px_to_df(data)
                    # VIS01304 has no Liður dim, single value col
                    archive_df = tidy_long(df, series_code, name_is, name_en, level,
                                           "Mánuður", "index")
                elif "VIS01102" in archive_path:
                    query = [
                        {"code": "Útgjaldaflokkur",
                         "selection": {"filter": "item", "values": [archive_val]}},
                        {"code": "Liður",
                         "selection": {"filter": "item", "values": ["index_B2008"]}},
                    ]
                    data = fetch_json(archive_path, query, out_file)
                    df = px_to_df(data)
                    archive_df = tidy_long(df, series_code, name_is, name_en, level,
                                           "Mánuður", "index_B2008")
                elif "VIS01000" in archive_path:
                    query = [
                        {"code": "Vísitala",
                         "selection": {"filter": "item", "values": [archive_val]}},
                        {"code": "Liður",
                         "selection": {"filter": "item", "values": ["index"]}},
                    ]
                    data = fetch_json(archive_path, query, out_file)
                    df = px_to_df(data)
                    archive_df = tidy_long(df, series_code, name_is, name_en, level,
                                           "Mánuður", "index")
                print(f"  archive: {len(archive_df)} rows "
                      f"({archive_df['date'].min()}..{archive_df['date'].max()})" if len(archive_df) else "  archive: empty")
            except Exception as e:
                print(f"  WARN archive fetch failed: {e}")

        # ---- Chain and trim ----
        if series_code == "CPI":
            # Headline CPI: VIS01000 already spans 1988-present, no chaining needed
            combined = current_df
        else:
            combined = chain_link(archive_df, current_df)

        # Trim to >=2015-01-01
        combined = combined.filter(pl.col("date") >= "2015-01-01")
        print(f"  combined: {len(combined)} rows "
              f"({combined['date'].min()}..{combined['date'].max()})" if len(combined) else "  combined: EMPTY")
        if not combined.is_empty():
            all_rows.append(combined)

    # ---- Merge everything ----
    if not all_rows:
        print("No data collected!")
        return
    master = pl.concat(all_rows)
    master = add_changes(master)

    # Reorder columns
    master = master.select([
        "date", "series_code", "series_name_is", "series_name_en",
        "coicop_level", "value_index", "mom_pct", "yoy_pct"
    ])
    master = master.sort(["series_code", "date"])

    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    master.write_csv(PROCESSED)
    print(f"\nWrote {len(master)} rows to {PROCESSED}")
    print(master.group_by("series_code").agg(
        pl.col("date").min().alias("from"),
        pl.col("date").max().alias("to"),
        pl.len().alias("n"),
    ).sort("series_code"))


if __name__ == "__main__":
    main()

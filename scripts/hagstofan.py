#!/usr/bin/env python3
"""
Fetch bike and e-bike import data from Hagstofan (Statistics Iceland).
Combines multiple tariff code tables across different periods.
"""

import httpx
import polars as pl
from pathlib import Path
import re

BASE_URL = "https://px.hagstofa.is/pxis/api/v1/is"

# Tariff code mappings - see .claude/skills/hagstofan.md
TARIFF_CATEGORIES = {
    "87116010": "ebikes",     # Pre-2020: E-bikes + e-scooters combined
    "87116011": "ebikes",     # E-bikes (pedal-assist ≤25 km/h)
    "87116012": "escooters",  # E-scooters
    "87116015": "ebikes",     # Other small EVs ≤25 km/h
    "87116090": "ebikes",     # Other electric motorcycles
    "87120000": "bikes",      # Regular bicycles
}

TABLES = [
    # Current data (2023-2025, monthly) - chapters 84-99
    ("Efnahagur/utanrikisverslun/1_voruvidskipti/03_inntollskra/UTA03803.px", "current"),
    # Archive 2017-2022 (annual)
    ("Efnahagur/utanrikisverslun/1_voruvidskipti/06_tollskrarnumereldra/UTA13813.px", "archive_2017"),
    # Archive 2012-2016 (annual)
    ("Efnahagur/utanrikisverslun/1_voruvidskipti/06_tollskrarnumereldra/UTA13823.px", "archive_2012"),
]


def fetch_table(path: str, tariff_codes: list[str]) -> str | None:
    """Fetch CSV data from PX-Web API for specific tariff codes."""
    url = f"{BASE_URL}/{path}"
    
    # First get metadata to find the correct variable code
    try:
        meta = httpx.get(url, timeout=30).json()
    except Exception as e:
        print(f"  Error getting metadata: {e}")
        return None
    
    # Find the tariff code variable
    tariff_var = None
    for var in meta.get("variables", []):
        code = var.get("code", "").lower()
        text = var.get("text", "").lower()
        if "tollskr" in code or "tollskr" in text:
            tariff_var = var["code"]
            # Get available values
            available = var.get("values", [])
            # Filter to only codes we want that exist in this table
            valid_codes = [c for c in tariff_codes if c in available]
            if not valid_codes:
                # Try matching with prefix
                valid_codes = [v for v in available if any(v.startswith(c) for c in tariff_codes)]
            break
    
    if not tariff_var:
        print(f"  Could not find tariff variable in {path}")
        return None
    
    if not valid_codes:
        print(f"  No matching tariff codes found in {path}")
        return None
    
    print(f"  Found {len(valid_codes)} matching codes: {valid_codes[:5]}...")
    
    # Request filtered data
    query = {
        "query": [
            {
                "code": tariff_var,
                "selection": {"filter": "item", "values": valid_codes}
            }
        ],
        "response": {"format": "csv"}
    }
    
    try:
        resp = httpx.post(url, json=query, timeout=60)
        if resp.status_code != 200:
            print(f"  Failed to fetch {path}: {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
            return None
        return resp.text
    except Exception as e:
        print(f"  Error fetching: {e}")
        return None


def parse_wide_csv(raw_file: Path) -> pl.DataFrame:
    """Parse Hagstofan's wide format CSV into tidy data."""
    # Read with encoding handling
    content = raw_file.read_bytes()
    # Try to decode as UTF-8, falling back to latin-1
    try:
        text = content.decode("utf-8-sig")  # Handle BOM
    except:
        text = content.decode("latin-1")
    
    # Parse CSV
    df = pl.read_csv(text.encode(), infer_schema_length=0, ignore_errors=True)
    
    cols = df.columns
    tariff_col = cols[0]  # First column is always tariff code
    
    # Extract year columns by pattern: "YYYY Something" or "YYYYMNN Something" (monthly)
    year_pattern = re.compile(r"^(\d{4})(?:M\d{2})?\s+(.+)$")
    
    records = []
    for row in df.iter_rows(named=True):
        tariff_full = row[tariff_col]
        # Extract 8-digit code from start
        match = re.match(r"^(\d{8})", str(tariff_full))
        if not match:
            continue
        tariff_code = match.group(1)
        category = TARIFF_CATEGORIES.get(tariff_code, "other")
        
        # Process each year column
        for col_name, value in row.items():
            if col_name == tariff_col:
                continue
            
            col_match = year_pattern.match(col_name)
            if not col_match:
                continue
            
            year = col_match.group(1)
            metric = col_match.group(2).lower()
            
            # Parse value
            try:
                val = float(str(value).replace(",", "").replace(" ", "")) if value else 0
            except:
                val = 0
            
            # Determine metric type
            if "cif" in metric:
                metric_type = "cif_isk"
            elif "magn" in metric or "ein" in metric:
                metric_type = "units"
            elif "kíl" in metric or "kg" in metric or "kil" in metric:
                metric_type = "kg"
            else:
                continue  # Skip fob, etc.
            
            records.append({
                "year": int(year),
                "tariff_code": tariff_code,
                "category": category,
                "metric": metric_type,
                "value": val
            })
    
    return pl.DataFrame(records)


def main():
    """Fetch and process all bike import data."""
    output_dir = Path(__file__).parent.parent / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    raw_dir = Path(__file__).parent.parent / "data" / "raw" / "hagstofan"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    tariff_codes = list(TARIFF_CATEGORIES.keys())
    all_data = []
    
    for table_path, source_name in TABLES:
        print(f"Fetching {source_name}...")
        csv_text = fetch_table(table_path, tariff_codes)
        
        if csv_text:
            # Save raw
            raw_file = raw_dir / f"{source_name}.csv"
            raw_file.write_text(csv_text, encoding="utf-8")
            print(f"  Saved raw to {raw_file}")
    
    # Parse all raw files
    print("\nParsing raw files...")
    for raw_file in raw_dir.glob("*.csv"):
        print(f"  Parsing {raw_file.name}...")
        df = parse_wide_csv(raw_file)
        if not df.is_empty():
            all_data.append(df)
            print(f"    Got {len(df)} records")
    
    if not all_data:
        print("No data found!")
        return
    
    # Combine all data
    combined = pl.concat(all_data)
    
    # Pivot to get cif and units as separate columns, then aggregate
    summary = (
        combined
        .filter(pl.col("value") > 0)
        .group_by(["year", "category", "metric"])
        .agg(pl.col("value").sum())
        .pivot(on="metric", index=["year", "category"], values="value")
        .fill_null(0)
        .sort(["year", "category"])
    )
    
    # Ensure expected columns exist
    if "cif_isk" not in summary.columns:
        summary = summary.with_columns(pl.lit(0).alias("cif_isk"))
    if "units" not in summary.columns:
        summary = summary.with_columns(pl.lit(0).alias("units"))
    
    # Select and rename for output
    output = summary.select([
        pl.col("year"),
        pl.col("category"),
        pl.col("cif_isk").alias("total_cif_isk"),
        pl.col("units").alias("total_units")
    ])
    
    # Save processed
    output_file = output_dir / "bike_imports_all.csv"
    output.write_csv(output_file)
    print(f"\nSaved {len(output)} rows to {output_file}")
    print(output)


if __name__ == "__main__":
    main()

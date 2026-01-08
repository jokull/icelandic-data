# Data Agent

Self-building data agent for Icelandic data. Extracts from official sources, builds Evidence reports with charts.

## Architecture

```
/.claude/skills/{source}.md   # Data source skills (fetching, API docs, series scope)
/scripts/{source}.py          # Python processing scripts (uv project)
/data/
  /raw/{source}/              # Raw downloads (Excel, CSV, JSON)
  /processed/                 # Cleaned, tidy datasets
/evidence-reports/
  /sources/{source}/          # SQL queries per data source
  /pages/{report}.md          # Evidence report pages
```

## Two Jobs

### 1. Data Skills (extraction)

Each skill in `/.claude/skills/` documents ONE data source:
- API endpoints and authentication
- Available series and their scope
- Tariff codes, variable mappings, classification changes
- Example fetch commands
- Known caveats (encoding, date ranges, schema changes)

**When asked about a new data source:** Research it thoroughly, then create a skill file.

### 2. Evidence Reports (visualization)

Reports live in `/evidence-reports/pages/`. Each report:
- Queries data via SQL in `/evidence-reports/sources/`
- Uses Evidence components: `<LineChart>`, `<BarChart>`, `<DataTable>`, `<BigValue>`
- Renders in browser with `npm run dev`

**When asked for a new report:** Create the SQL queries and Evidence page.

## Active Skills

| Skill | Source | Description |
|-------|--------|-------------|
| [hagstofan](/.claude/skills/hagstofan.md) | Statistics Iceland | PX-Web API for economic, demographic, trade data |
| [sedlabanki](/.claude/skills/sedlabanki.md) | Central Bank of Iceland | SDMX API for monetary, financial, external sector data |
| [reykjavik](/.claude/skills/reykjavik.md) | Reykjavík Municipality | CKAN + PX-Web APIs for municipal services, demographics, welfare, nationality data |
| [skatturinn](/.claude/skills/skatturinn.md) | Iceland Tax Authority | Annual reports (ársreikningar), company registry, ownership chain mapping via Playwright |
| [financials](/.claude/skills/financials.md) | PDF Extraction | Structured financial data from annual reports using Docling + Claude interpretation |
| [hms](/.claude/skills/hms.md) | HMS Property Registry | Kaupskrá fasteigna - 222k property transactions 2006-present, geocoded |
| [iceaddr](/.claude/skills/iceaddr.md) | Address Geocoding | Python library for Icelandic address lookup, reverse geocoding, postcodes |

## Adding a New Skill

1. Research the data source API
2. Create `/.claude/skills/{source}.md` with:
   - API base URL and auth
   - Available datasets and their codes
   - Example queries
   - Data caveats
3. Add SQL source in `/evidence-reports/sources/{source}/`
4. Update this file's "Active Skills" table

## Tools

Installed via `./setup.sh`:
- `jq` - JSON processing
- `miller` - CSV swiss army knife
- `duckdb` - SQL on local files
- `pandoc` - document conversion
- `uv` - Python package manager
- `xlsx2csv` - Excel to CSV conversion

Python (managed by `uv`):
- `polars` - Fast DataFrame library
- `openpyxl` - Excel file reading
- `httpx` - HTTP client
- `playwright` - Headless browser automation (for skatturinn.is)
- `pdfplumber` - PDF text/table extraction
- `docling` - AI-powered PDF extraction with 97.9% table accuracy (IBM)
- `iceaddr` - Icelandic address geocoding (bundled SQLite from Staðfangaskrá)

Evidence (in `/evidence-reports/`):
- Node.js project with DuckDB integration
- SQL queries → Parquet → Interactive charts

## Quick Commands

```bash
# Process raw data into tidy CSVs
uv run python scripts/sedlabanki.py

# Query processed data
duckdb -c "SELECT * FROM 'data/processed/*.csv' LIMIT 10"

# Start Evidence dev server
cd evidence-reports && npm run dev

# Get company info and annual reports list
uv run python scripts/skatturinn.py info <kennitala>

# Download annual report PDF
uv run python scripts/skatturinn.py download <kennitala> --year 2024

# Extract financials from PDF (full pipeline)
uv run python scripts/financials.py company <kennitala> --year 2024

# Extract from local PDF
uv run python scripts/financials.py extract /path/to/report.pdf

# Property price analysis
duckdb -c "SELECT YEAR(kaupsamningur_dags), median(kaupverd*1000/einflm_m2) FROM 'data/processed/kaupskra_geocoded.parquet' WHERE NOT onothaefur AND tegund='Fjölbýli' GROUP BY 1 ORDER BY 1"

# Geocode an Icelandic address
uv run python -c "from iceaddr import iceaddr_lookup; print(iceaddr_lookup('Laugavegur', number=22, postcode=101))"
```

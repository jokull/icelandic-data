# Icelandic Data Toolkit

Data toolkit for Icelandic public data. Each skill in `.claude/skills/` documents one data source — API endpoints, series codes, encoding quirks, classification changes. Scripts in `scripts/` fetch, clean, and transform the data.

## Architecture

```
/.claude/skills/{source}.md   # Data source docs (API, endpoints, caveats)
/scripts/{source}.py          # Fetch + transform scripts (uv project)
/data/
  /raw/{source}/              # Raw downloads (Excel, CSV, JSON)
  /processed/                 # Cleaned datasets
```

## Skills

Each skill documents ONE data source:
- API endpoints and authentication
- Available series and their scope
- Tariff codes, variable mappings, classification changes
- Example fetch commands
- Known caveats (encoding, date ranges, schema changes)

**When asked about a new data source:** Research it thoroughly, then create a skill file.

## HTML Reports

When asked for a report, produce a **single self-contained `.html` file** in `/reports/`:
- Embed data as JSON in `<script>` tags
- Use Chart.js (CDN) — `<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>`
- No build step, no dependencies

Style: system fonts, max-width `960px`, cards with `border-radius: 12px`, Chart.js in `.chart-wrap` at `height: 360px`.

## Active Skills

| Skill | Source | Description |
|-------|--------|-------------|
| [hagstofan](/.claude/skills/hagstofan.md) | Statistics Iceland | PX-Web API for economic, demographic, trade data |
| [sedlabanki](/.claude/skills/sedlabanki.md) | Central Bank of Iceland | SDMX API for monetary, financial, external sector data |
| [reykjavik](/.claude/skills/reykjavik.md) | Reykjavík Municipality | CKAN + PX-Web APIs for municipal services, demographics, welfare, nationality data. **Opin Fjármál**: vendor-level spending by division/unit (2014–2025, ~94k rows/yr) — use for "what does Reykjavík buy/spend/pay" |
| [skatturinn](/.claude/skills/skatturinn.md) | Iceland Tax Authority | Annual reports (ársreikningar), company registry, ownership chain mapping via Playwright |
| [financials](/.claude/skills/financials.md) | PDF Extraction | Structured financial data from annual reports using Docling + Claude interpretation |
| [hms](/.claude/skills/hms.md) | HMS Property Registry | Kaupskrá fasteigna - 222k property transactions 2006-present, geocoded |
| [iceaddr](/.claude/skills/iceaddr.md) | Address Geocoding | Python library for Icelandic address lookup, reverse geocoding, postcodes |
| [nasdaq](/.claude/skills/nasdaq.md) | Nasdaq Iceland | Exchange notices, annual reports, insider trading for listed companies |
| [samgongustofa](/.claude/skills/samgongustofa.md) | Transport Authority | Vehicle registrations by make, fuel type, location via Power BI scraping |
| [insurance](/.claude/skills/insurance.md) | Insurance Market | 4 insurers (Sjóvá, Skagi/VÍS, TM, Vörður), combined ratios, Nordic comparison |
| [fuel](/.claude/skills/fuel.md) | Fuel Market | Gasvaktin prices, N1/Olís/Orkan/Atlantsolía, conglomerate financials |
| [vedur](/.claude/skills/vedur.md) | Meteorological Office | XML weather API for observations/forecasts, climatological data |
| [loftgaedi](/.claude/skills/loftgaedi.md) | Air Quality (UST) | PM10/PM2.5/NO2/H2S monitoring, 57 stations, hourly data via UST API |
| [tenders](/.claude/skills/tenders.md) | Public Procurement | TED API + OCDS bulk data for 3,494+ Icelandic tenders, award tracking, CPV search |
| [opnirreikningar](/.claude/skills/opnirreikningar.md) | Open Accounts | Government invoice data — paid invoices by org/vendor/type, 2017–present |
| [ferdamalastofa](/.claude/skills/ferdamalastofa.md) | Icelandic Tourist Board | Keflavík passenger counts by nationality/month, flights, accommodation, tourism stats via Power BI scraping |
| [domstolar](/.claude/skills/domstolar.md) | Icelandic Courts | Héraðsdómstólar, Landsréttur, Hæstiréttur — ruling search, RSS feeds, PDF download, HTML scraping |
| [skipulagsmal](/.claude/skills/skipulagsmal.md) | Planitor | Planning & building permits — cases, minutes, entities, nearby search across 5 municipalities |

## Adding a New Skill

1. Research the data source API
2. Create `/.claude/skills/{source}.md` with:
   - API base URL and auth
   - Available datasets and their codes
   - Example queries
   - Data caveats
3. Update this file's "Active Skills" table

## Tools

Installed via `./setup.sh`:
- `jq` - JSON processing
- `duckdb` - SQL on local files
- `uv` - Python package manager

Python (managed by `uv`):
- `polars` - Fast DataFrame library
- `openpyxl` - Excel file reading
- `httpx` - HTTP client
- `playwright` - Headless browser automation (for skatturinn.is)
- `pdfplumber` - PDF text/table extraction
- `docling` - AI-powered PDF extraction with 97.9% table accuracy (IBM)
- `iceaddr` - Icelandic address geocoding (bundled SQLite from Staðfangaskrá)

## Quick Commands

```bash
# Process raw data into tidy CSVs
uv run python scripts/sedlabanki.py

# Query processed data
duckdb -c "SELECT * FROM 'data/processed/*.csv' LIMIT 10"

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

# List Nasdaq Iceland companies
uv run python scripts/nasdaq.py companies

# Search company announcements (handles Icelandic encoding)
uv run python scripts/nasdaq.py search --company "Arion banki hf." --category "Ársreikningur"

# Process Gasvaktin fuel prices
uv run python scripts/fuel_prices.py
```

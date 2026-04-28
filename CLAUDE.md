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
| [sectoral_balances](/.claude/skills/sectoral_balances.md) | Analytical (Hagstofan + FSR) | Current account decomposition, NIIP attribution, pension fund foreign assets, Godley/MMT sectoral balances identity |
| [sedlabanki](/.claude/skills/sedlabanki.md) | Central Bank of Iceland | SDMX API (balance sheets, new credit) + gagnabanki.is Power BI for daily key interest rates 2007+ |
| [reykjavik](/.claude/skills/reykjavik.md) | Reykjavík Municipality | CKAN + PX-Web APIs for municipal services, demographics, welfare, nationality data. **Opin Fjármál**: vendor-level spending by division/unit (2014–2025, ~94k rows/yr) — use for "what does Reykjavík buy/spend/pay" |
| [skatturinn](/.claude/skills/skatturinn.md) | Iceland Tax Authority | Annual reports (ársreikningar), company registry, ownership chain mapping via Playwright |
| [financials](/.claude/skills/financials.md) | PDF Extraction | Structured financial data from annual reports using Docling + Claude interpretation |
| [hms](/.claude/skills/hms.md) | HMS Property Registry | Kaupskrá fasteigna (222k property transactions, geocoded) + Landeignaskrá (89k land parcels with polygons, ESRI shapefile via Azure blob) |
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
| [car](/.claude/skills/car.md) | island.is | Vehicle lookup by plate/VIN via public GraphQL API |
| [gengi](/.claude/skills/gengi.md) | Borgun | Currency exchange rates (card rates, not interbank) |
| [laun](/.claude/skills/laun.md) | payday.is | Take-home salary calculator with tax/pension breakdown |
| [maskina](/.claude/skills/maskina.md) | Maskína | Public opinion polls — structured data via Tableau Public VizQL + articles via WordPress API |
| [liteparse](/.claude/skills/liteparse.md) | PDF Parsing | LlamaIndex local PDF parser — text with bounding box coordinates, page screenshots, visual element detection |
| [umferd](/.claude/skills/umferd.md) | Vegagerðin | Traffic counters — real-time 15-min counts, 7-day rolling daily totals, 168+ stations via GeoServer WFS |

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

# Hagstofan: CPI sub-components (headline + 12 COICOP groups + imported/domestic/services)
# Chain-links VIS01304/01102 archive onto VIS01300/01101 current across the June 2024 break
uv run python scripts/hagstofan_cpi.py

# Hagstofan: population by citizenship (quarterly + annual by country), wages by private sector, immigrant labor share
uv run python scripts/hagstofan_population_wages.py

# Hagstofan: wage index (LAU04000) + labor/total income deciles (TEK01006/07) + PAYE by background (TEK02012)
# Tidy long format with CPI-deflated real values
uv run python scripts/hagstofan_income.py

# HMS: house-price (kaupvísitala) vs rental-price (leiguvísitala) indices, rebased to 2023-05=100
# Requires data/raw/hms/indices/{kaup,leigu}visitala.csv — manual downloads from hms.is
uv run python scripts/hms_indices.py

# HMS Landeignaskrá — download shapefile, build landsnr → lon/lat CSV
uv run python scripts/landeignaskra.py download    # 25 MB Azure blob
uv run python scripts/landeignaskra.py extract
uv run python scripts/landeignaskra.py build       # data/processed/landeignaskra.csv
uv run python scripts/landeignaskra.py lookup 0174540

# Seðlabanki interest rates — Power BI scrape via gagnabanki.is
uv run python scripts/sedlabanki_rates.py

# Traffic counters (Vegagerðin) — list, snapshot, accumulate, render
uv run python scripts/umferd.py stations
uv run python scripts/umferd.py snapshot
uv run python scripts/umferd.py collect
uv run python scripts/umferd.py report
uv run python scripts/umferd_map.py    # Iceland-wide traffic map (depends on LMI cache from PR 1)
```

## Scripts layout

- `scripts/*.py` — fetchers/cleaners: hit an API or read raw files, write tidy CSVs to `data/processed/`
- `reports/*.py` — one-off report scripts (gitignored, local-only, sit next to the `.html` they emit)

Inflation-specific analysis (derivation scripts, research reports, the whodunit blog post) lives in [`~/Code/inflation-whodunit`](../inflation-whodunit). That repo reads processed data from here.

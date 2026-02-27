# Icelandic Data

AI-assisted data agent for Icelandic public data. Fetches from official APIs, processes into tidy datasets, and builds self-contained HTML reports with Chart.js.

Built with [Claude Code](https://claude.com/claude-code) — each data source is a skill file that teaches the agent how to fetch and interpret the data.

## How it works

```
.claude/skills/{source}.md   → Data source documentation (API docs, endpoints, caveats)
scripts/{source}.py           → Python processing scripts
data/raw/{source}/            → Raw downloads (Excel, CSV, JSON)
data/processed/               → Cleaned datasets
{report}.html                 → Self-contained HTML reports
```

Ask the agent about an Icelandic data source and it will research the API, create a skill file, write a processing script, and build an HTML report — or any subset of those steps.

## Data sources

| Source | Description |
|--------|-------------|
| Statistics Iceland | PX-Web API — economic, demographic, trade data |
| Central Bank | SDMX API — monetary policy, financial stability, external sector |
| Reykjavík Municipality | CKAN + PX-Web — municipal services, spending (Opin Fjármál) |
| Tax Authority | Annual reports, company registry, ownership chains |
| HMS Property Registry | 222k property transactions since 2006, geocoded |
| Nasdaq Iceland | Exchange notices, annual reports, insider trading |
| Transport Authority | Vehicle registrations by make, fuel type, location |
| Planitor | Planning & building permits across 5 municipalities |
| Meteorological Office | Weather observations, forecasts, climatological data |
| Air Quality (UST) | PM10/PM2.5/NO2/H2S from 57 monitoring stations |
| Tourist Board | Keflavík passenger counts, flights, accommodation stats |
| Public Procurement | 3,494+ tenders via TED API and OCDS bulk data |
| Open Accounts | Government invoices by org/vendor/type, 2017–present |
| Icelandic Courts | Ruling search across all three court levels |

## Setup

```bash
./setup.sh          # Install CLI tools (jq, miller, duckdb, uv, etc.)
uv sync             # Install Python dependencies
```

## Usage

```bash
# Process data
uv run python scripts/sedlabanki.py
uv run python scripts/fuel_prices.py

# Query with DuckDB
duckdb -c "SELECT * FROM 'data/processed/*.csv' LIMIT 10"

# Company financials pipeline
uv run python scripts/financials.py company <kennitala> --year 2024

# Serve reports locally
npx serve .
```

## Reports

Reports are single `.html` files — no build step, no dependencies beyond a CDN link to Chart.js. Open directly in a browser or serve locally.

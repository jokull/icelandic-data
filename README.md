# Icelandic Data

Data toolkit for Icelandic public data, built around [Claude Code](https://claude.com/claude-code). The `.claude/skills/` files document each data source — API endpoints, series codes, encoding quirks, classification changes — and the `scripts/` directory has Python scripts that fetch, clean, and transform the data.

Not a portable skill library. The skills reference co-located scripts, assume local tooling (`uv`, `duckdb`, `playwright`), and work as a unit. Clone the repo, run setup, and use Claude Code to research questions, join data sources, or produce outputs — a gist, a CSV, an HTML report, whatever fits.

## Structure

```
.claude/skills/{source}.md   → Data source docs (API, endpoints, caveats)
scripts/{source}.py           → Fetch + transform scripts
data/raw/{source}/            → Raw downloads
data/processed/               → Cleaned datasets
```

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
| Fuel Market | Gasvaktin prices, conglomerate financials |
| Insurance Market | Combined ratios, Nordic comparison |

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
```

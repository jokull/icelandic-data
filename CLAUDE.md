# Data Agent

Self-building data agent for Icelandic data. Extracts from official sources, builds Evidence reports with charts.

## Architecture

```
/.claude/skills/{source}.md   # Data source skills (fetching, API docs, series scope)
/data/
  /raw/{source}/              # Raw downloads (CSV, JSON)
  /processed/                 # Cleaned, joined datasets
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

## Quick Reference

### Data fetching
```bash
# Fetch from Hagstofan
curl -X POST "https://px.hagstofa.is/pxis/api/v1/is/{path}/{TABLE}.px" \
  -H "Content-Type: application/json" \
  -d '{"query": [], "response": {"format": "csv"}}'
```

### Evidence commands
```bash
cd evidence-reports
npm run sources    # Regenerate data from SQL queries
npm run dev        # Start dev server at localhost:3000
npm run build      # Build static site
```

### DuckDB queries
```bash
# Query CSVs directly
duckdb -c "SELECT * FROM 'data/processed/*.csv' LIMIT 10"
```

## Active Skills

| Skill | Source | Description |
|-------|--------|-------------|
| [hagstofan](/.claude/skills/hagstofan.md) | Statistics Iceland | PX-Web API for economic, demographic, trade data |

## Active Reports

| Report | Path | Description |
|--------|------|-------------|
| E-bike Imports | `/evidence-reports/pages/index.md` | E-bike, e-scooter, bike import trends 2017-2025 |

## Adding a New Skill

1. Research the data source API
2. Create `/.claude/skills/{source}.md` with:
   - API base URL and auth
   - Available datasets and their codes
   - Example queries
   - Data caveats
3. Add SQL source in `/evidence-reports/sources/{source}/`
4. Update this file's "Active Skills" table

## Adding a New Report

1. Ensure data source skill exists
2. Create SQL queries in `/evidence-reports/sources/{source}/`
3. Run `npm run sources` to generate data
4. Create `/evidence-reports/pages/{report}.md` with Evidence components
5. Test with `npm run dev`
6. Update this file's "Active Reports" table

## Tools

Installed via `./setup.sh`:
- `jq` - JSON processing
- `miller` - CSV swiss army knife
- `duckdb` - SQL on local files
- `pandoc` - document conversion

Evidence (in `/evidence-reports/`):
- Node.js project with DuckDB integration
- SQL queries → Parquet → Interactive charts

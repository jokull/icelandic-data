# Icelandic Data

Data toolkit for Icelandic public data, built around [Claude Code](https://claude.com/claude-code) and [Codex](https://developers.openai.com/codex). The `.agents/skills/` files document each data source — API endpoints, series codes, encoding quirks, classification changes — and the `scripts/` directory has Python scripts that fetch, clean, and transform the data.

Not a portable skill library. The skills reference co-located scripts, assume local tooling (`uv`, `duckdb`, `playwright`), and work as a unit. Clone the repo, run setup, and use an agent to research questions, join data sources, or produce outputs — a gist, a CSV, an HTML report, whatever fits.

## Structure

```
.agents/skills/{source}/SKILL.md → Data source docs (API, endpoints, caveats)
scripts/{source}.py              → Fetch + transform scripts
tests/health/test_{source}.py    → Upstream health probes (marker: health)
data/raw/{source}/               → Raw downloads
data/processed/                  → Cleaned datasets
```

Skills follow the [agentskills.io](https://agentskills.io) open standard. `.agents/skills/`
is the real location (read natively by Codex); `.claude/skills` symlinks to it for Claude
Code, and `CLAUDE.md` symlinks to `AGENTS.md`. One set of files, both agents.

## Data sources

Currently 45 skills covering national statistics, government dashboards
(_mælaborð_), regulatory filings, and utility APIs. Each skill's frontmatter
`description` is its index entry — run `ls .agents/skills/` to enumerate them, and see
[`AGENTS.md`](AGENTS.md) for the quick-commands reference.

### Statistics & macroeconomic

| Source | Description |
|--------|-------------|
| Hagstofa Íslands | PX-Web API — economic, demographic, trade, income series |
| Seðlabanki | SDMX API — monetary policy, financial stability, FX history via ECB |
| Tekjusagan | Income-history dashboard — 5 Power BI report routes (Forsætisráðuneytið) |
| Velsældarvísar | Hagstofa indicator catalogs — well-being + social + cultural (88 indicators → 77 PX tables) |
| Heimsmarkmið | UN SDG national statistics — 137 indicators across all 17 goals (open-sdg ZIP bundle) |
| Ríkisreikningur | State accounts — yearly afkoma 2015+, málefnasvið breakdowns, 35 published files (Azure Functions API) |

### Government dashboards (_mælaborð_)

Systematic coverage of public dashboards published under Iceland's data-access law.

| Source | Description |
|--------|-------------|
| Landlæknir | 33 Directorate-of-Health Power BI dashboards + Talnabrunnur PDFs |
| Vinnumálastofnun | Registered unemployment — Power BI + monthly Excel |
| Farsæld barna | Child-wellbeing dashboard (static-data Power BI) |
| Mælaborð landbúnaðarins | 3 Power BI dashboards — subsidies, livestock, markets |
| Ferðamálastofa | Keflavík passengers, flights, accommodation — Power BI scraping |
| Umferð (Vegagerðin) | 168+ traffic counters — real-time 15-min + 7-day rolling daily |
| Byggðastofnun | Regional-development dashboards — 11 Tableau Public embeds (population, income, energy, grants) |
| Vernd (Ríkislögreglustjóri) | Asylum / international-protection monthly stats — Power BI |

### Business & markets

| Source | Description |
|--------|-------------|
| Skatturinn | Annual reports (ársreikningar), company registry, ownership chains |
| Financials | PDF-to-structured extraction via `pdfplumber` + Claude interpretation |
| Nasdaq Iceland | Exchange notices, annual reports, insider trading |
| Insurance | 4 insurers (Sjóvá, Skagi/VÍS, TM, Vörður), combined ratios, Nordic comparison |
| Fuel | Gasvaktin prices + conglomerate financials for N1/Olís/Orkan/Atlantsolía |
| Maskína | Public-opinion polls via Tableau Public VizQL + WordPress API |
| Opnir reikningar | Government invoices by org/vendor/type, 2017–present |
| Tenders | 3,494+ public tenders via TED API + OCDS bulk data |

### Property, planning, addresses

| Source | Description |
|--------|-------------|
| HMS | Kaupskrá fasteigna (222k transactions, geocoded) + Landeignaskrá (89k parcel polygons) |
| Skipulagsmál (Planitor) | Planning & building permits — cases, minutes, entities, nearby search across 5 municipalities |
| iceaddr | Icelandic address geocoding (bundled SQLite from Staðfangaskrá) |

### Transport & mobility

| Source | Description |
|--------|-------------|
| Samgöngustofa | Vehicle registrations by make, fuel type, location — Power BI |
| car (island.is) | Per-vehicle lookup by plate/VIN via public GraphQL API |

### Environment & geography

| Source | Description |
|--------|-------------|
| Veður | Met-Office XML API — observations, forecasts, climatology |
| Loftgæði | UST air quality — PM10/PM2.5/NO2/H2S, 57 stations, hourly |
| CO2 (co2.is) | Climate action plan — 106 numbered actions across 4 kerfi, status + ministry + year tracking |
| LMI | Vector geodata via GeoServer WFS — coastline, roads, rivers, glaciers |
| Kortagerð | Iceland map generation — matplotlib (static) + Leaflet (interactive) |

### Personal finance & rates

| Source | Description |
|--------|-------------|
| Laun (payday.is) | Take-home salary calculator with tax/pension breakdown |
| Gengi (Borgun) | Currency exchange rates (card rates, not interbank) |

### Legal & civic

| Source | Description |
|--------|-------------|
| Dómstólar | Court rulings — Héraðsdómstólar, Landsréttur, Hæstiréttur via RSS + scraping |
| Reykjavíkurborg | CKAN + PX-Web APIs for municipal services, demographics, welfare, Opin Fjármál |

## Setup

```bash
./setup.sh          # Install CLI tools (jq, duckdb, uv, etc.)
uv sync             # Install Python dependencies
uv run playwright install chromium   # Only if you plan to use Power BI / SPA scrapers
```

## Usage

```bash
# Process data
uv run python scripts/sedlabanki.py
uv run python scripts/fuel.py

# Query with DuckDB
duckdb -c "SELECT * FROM 'data/processed/*.csv' LIMIT 10"

# Company financials pipeline
uv run python scripts/financials.py company <kennitala> --year 2024

# Scrape a government dashboard
uv run python scripts/landlaeknir.py list
uv run python scripts/landlaeknir.py fetch --slug mortis

# Build the indicator catalog for visar.hagstofa.is
uv run python scripts/velsaeldarvisar.py fetch
```

See [AGENTS.md](AGENTS.md) for the full command catalog across every skill.

## Tests

```bash
uv run pytest -m "not slow"   # fast unit tests (~0.5s) — what PR CI runs
uv run pytest -m slow         # network + Playwright tests (several minutes)
uv run pytest -m health       # upstream health probes
uv run pytest -m health -k hagstofan   # probe one source
```

Health probes check that each upstream source still serves the smallest contract
its script depends on. They run daily in CI; browser-based probes are
manual-dispatch only. See [`.github/workflows/source-health.yml`](.github/workflows/source-health.yml).

## Adding a new data source

See the [`new-data-source` skill](.agents/skills/new-data-source/SKILL.md) for
the methodology — discovery, probing, skill authoring, script conventions,
testing, and visualization.

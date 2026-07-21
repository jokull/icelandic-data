# Icelandic Data

[![data sources](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjokull%2Ficelandic-data%2Fhealth-history%2Fbadge.json)](https://github.com/jokull/icelandic-data/actions/workflows/source-health.yml)
[![CI](https://github.com/jokull/icelandic-data/actions/workflows/ci.yml/badge.svg)](https://github.com/jokull/icelandic-data/actions/workflows/ci.yml)

Data toolkit for Icelandic public data, built around [Claude Code](https://claude.com/claude-code) and [Codex](https://developers.openai.com/codex). The `.agents/skills/` files document each data source — API endpoints, series codes, encoding quirks, classification changes — and the `scripts/` directory has Python scripts that fetch, clean, and transform the data.

The **data sources** badge reports upstream health, not this repo's code: a source only turns it
red after **7 straight days** down or returning the wrong shape. Anything shorter is weather —
these are public APIs and they blink. Details in
[`AGENTS.md`](AGENTS.md#flake-vs-dead); raw history is on the
[`health-history`](https://github.com/jokull/icelandic-data/tree/health-history) branch.

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

Currently 49 skills covering national statistics, government dashboards
(_mælaborð_), regulatory filings, and utility APIs. Each skill's frontmatter
`description` is its index entry — run `ls .agents/skills/` to enumerate them, and see
[`AGENTS.md`](AGENTS.md) for the quick-commands reference.

The light in each row is that source's current verdict, refreshed daily and finer-grained
than the badge above (which waits a full week before going red):
<img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/_legend_healthy.svg" width="10"> healthy ·
<img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/_legend_flaky.svg" width="10"> flaky (failed but recovered — these APIs blink) ·
<img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/_legend_dead.svg" width="10"> dead, or the skill no longer matches the source ·
<img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/_legend_unknown.svg" width="10"> not enough observations yet.
A `·` means there is [nothing upstream to probe](tests/health/README.md#skills-with-no-upstream-to-probe).
Per-source uptime and last error are in the
[workflow summary](https://github.com/jokull/icelandic-data/actions/workflows/source-health.yml).

### Statistics & macroeconomic

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/hagstofan.svg" width="12"> | Hagstofa Íslands | PX-Web API — economic, demographic, trade, income series |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/sedlabanki.svg" width="12"> | Seðlabanki | SDMX API — monetary policy, financial stability, FX history via ECB |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/tekjusagan.svg" width="12"> | Tekjusagan | Income-history dashboard — 5 Power BI report routes (Forsætisráðuneytið) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/velsaeldarvisar.svg" width="12"> | Velsældarvísar | Hagstofa indicator catalogs — well-being + social + cultural (88 indicators → 77 PX tables) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/heimsmarkmid.svg" width="12"> | Heimsmarkmið | UN SDG national statistics — 137 indicators across all 17 goals (open-sdg ZIP bundle) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/rikisreikningur.svg" width="12"> | Ríkisreikningur | State accounts — yearly afkoma 2015+, málefnasvið breakdowns, 35 published files (Azure Functions API) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/fjarlog.svg" width="12"> | Fjárlög | State budget appropriations + 5-year plan at málaflokkur level (actual / enacted / bill) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/energy.svg" width="12"> | Energy | Electricity generation by source, energy-system tables and fuel sales (Environment & Energy Agency) |

### Government dashboards (_mælaborð_)

Systematic coverage of public dashboards published under Iceland's data-access law.

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/landlaeknir.svg" width="12"> | Landlæknir | 33 Directorate-of-Health Power BI dashboards + Talnabrunnur PDFs |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/vinnumalastofnun.svg" width="12"> | Vinnumálastofnun | Registered unemployment — Power BI + monthly Excel |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/farsaeld_barna.svg" width="12"> | Farsæld barna | Child-wellbeing dashboard (static-data Power BI) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/maelabord_landbunadarins.svg" width="12"> | Mælaborð landbúnaðarins | 3 Power BI dashboards — subsidies, livestock, markets |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/ferdamalastofa.svg" width="12"> | Ferðamálastofa | Keflavík passengers, flights, accommodation — Power BI scraping |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/umferd.svg" width="12"> | Umferð (Vegagerðin) | 168+ traffic counters — real-time 15-min + 7-day rolling daily |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/byggdastofnun.svg" width="12"> | Byggðastofnun | Regional-development dashboards — 11 Tableau Public embeds (population, income, energy, grants) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/vernd.svg" width="12"> | Vernd (Ríkislögreglustjóri) | Asylum / international-protection monthly stats — Power BI |

### Business & markets

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/skatturinn.svg" width="12"> | Skatturinn | Annual reports (ársreikningar), company registry, ownership chains |
| · | Financials | PDF-to-structured extraction via `pdfplumber` + Claude interpretation |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/nasdaq.svg" width="12"> | Nasdaq Iceland | Exchange notices, annual reports, insider trading |
| · | Insurance | 4 insurers (Sjóvá, Skagi/VÍS, TM, Vörður), combined ratios, Nordic comparison |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/fuel.svg" width="12"> | Fuel | Gasvaktin prices + conglomerate financials for N1/Olís/Orkan/Atlantsolía |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/maskina.svg" width="12"> | Maskína | Public-opinion polls via Tableau Public VizQL + WordPress API |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/skodanakannanir.svg" width="12"> | Skoðanakannanir | RÚV opinion-poll aggregator — national + Reykjavík party support across pollsters |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/opnirreikningar.svg" width="12"> | Opnir reikningar | Government invoices by org/vendor/type, 2017–present |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/tenders.svg" width="12"> | Tenders | 3,494+ public tenders via TED API + OCDS bulk data |

### Property, planning, addresses

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/hms.svg" width="12"> | HMS | Kaupskrá fasteigna (222k transactions, geocoded) + Landeignaskrá (89k parcel polygons) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/skipulagsmal.svg" width="12"> | Skipulagsmál (Planitor) | Planning & building permits — cases, minutes, entities, nearby search across 5 municipalities |
| · | iceaddr | Icelandic address geocoding (bundled SQLite from Staðfangaskrá) |

### Transport & mobility

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/samgongustofa.svg" width="12"> | Samgöngustofa | Vehicle registrations by make, fuel type, location — Power BI |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/car.svg" width="12"> | car (island.is) | Per-vehicle lookup by plate/VIN via public GraphQL API |

### Environment & geography

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/vedur.svg" width="12"> | Veður | Met-Office JSON API — observations, stations, forecasts, earthquakes |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/loftgaedi.svg" width="12"> | Loftgæði | UST air quality — PM10/PM2.5/NO2/H2S, 57 stations, hourly |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/co2.svg" width="12"> | CO2 (co2.is) | Climate action plan — 106 numbered actions across 4 kerfi, status + ministry + year tracking |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/lmi.svg" width="12"> | LMI | Vector geodata via GeoServer WFS — coastline, roads, rivers, glaciers |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/lmi_hrl.svg" width="12"> | LMI HRL | Copernicus High Resolution Layers via LMI — grassland, imperviousness (20 m raster) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/natt.svg" width="12"> | Náttúrufræðistofnun | Habitat-type polygons (vistgerðir) via WFS |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/eea_sdi.svg" width="12"> | EEA SDI | European Environment Agency geospatial catalogue (GeoNetwork 4.4) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/ust_gis.svg" width="12"> | UST GIS | Environment Agency WFS — contaminated land, water, protected areas, noise and wastewater |
| · | Kortagerð | Iceland map generation — matplotlib (static) + Leaflet (interactive) |

### Energy & fisheries

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/hafogvatn.svg" width="12"> | Hafrannsóknastofnun | Annual fish-stock assessments, advice, landings and survey series (embedded table JSON) |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/fiskistofa.svg" width="12"> | Fiskistofa | Open WFS layers for active fishing closures, regulations and fishing areas (not paid catch/quota REST) |

### Personal finance & rates

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/laun.svg" width="12"> | Laun (payday.is) | Take-home salary calculator with tax/pension breakdown |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/gengi.svg" width="12"> | Gengi (Borgun) | Currency exchange rates (card rates, not interbank) |

### Legal & civic

| | Source | Description |
|---|--------|-------------|
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/domstolar.svg" width="12"> | Dómstólar | Court rulings — Héraðsdómstólar, Landsréttur, Hæstiréttur via RSS + scraping |
| <img src="https://raw.githubusercontent.com/jokull/icelandic-data/health-history/dots/reykjavik.svg" width="12"> | Reykjavíkurborg | CKAN + PX-Web APIs for municipal services, demographics, welfare, Opin Fjármál |

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

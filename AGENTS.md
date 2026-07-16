# Icelandic Data Toolkit

Data toolkit for Icelandic public data. Each skill in `.agents/skills/` documents one data source — API endpoints, series codes, encoding quirks, classification changes. Scripts in `scripts/` fetch, clean, and transform the data.

## Architecture

```
/.agents/skills/{source}/SKILL.md   # Data source docs (API, endpoints, caveats)
/scripts/{source}.py                # Fetch + transform scripts (uv project)
/tests/health/test_{source}.py      # Upstream health probe (marker: health)
/data/
  /raw/{source}/                    # Raw downloads (Excel, CSV, JSON)
  /processed/                       # Cleaned datasets
```

Skills follow the [agentskills.io](https://agentskills.io) open standard, so the same
`SKILL.md` files work in both Claude Code and Codex:

- `.agents/skills/` is the real location — read natively by Codex.
- `.claude/skills` is a symlink to it, so Claude Code discovers the same files.
- `CLAUDE.md` is a symlink to `AGENTS.md`, so both agents read these instructions.

Skill names must be lowercase, ASCII, hyphen-separated (no underscores, no `ð`/`æ`).

## Skills

Each skill documents ONE data source:
- API endpoints and authentication
- Available series and their scope
- Tariff codes, variable mappings, classification changes
- Example fetch commands
- Known caveats (encoding, date ranges, schema changes)

There is deliberately no index of skills here. Each `SKILL.md` carries a `description`
in its frontmatter, and that description is what both agents preload and match against —
a table in this file would be a second, staler copy that cannot trigger anything.
Run `ls .agents/skills/` to enumerate them.

Keep each `description` under ~160 characters: Codex truncates when all descriptions
combined exceed 8,000 characters, and with 45 skills that budget is the binding constraint.

**When asked about a new data source:** follow the `new-data-source` skill.

## HTML Reports

When asked for a report, produce a **single self-contained `.html` file** in `/reports/`:
- Embed data as JSON in `<script>` tags
- Use Chart.js (CDN) — `<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>`
- No build step, no dependencies

Style: system fonts, max-width `960px`, cards with `border-radius: 12px`, Chart.js in `.chart-wrap` at `height: 360px`.

## Adding a New Data Source

Follow the methodology in the `new-data-source` skill — covers discovery, probing, skill authoring, script conventions, health probes, testing, and visualization. Summary:

1. **Discover** — find the API type (REST, WFS, Power BI, scraping), probe endpoints, document schema
2. **Skill** — create `.agents/skills/{source}/SKILL.md` with frontmatter, API, schema, request examples, caveats
3. **Script** — create `scripts/{source}.py` with `list`/`fetch` subcommands (polars + httpx)
4. **Test** — verify output with DuckDB, check Icelandic encoding, spot-check values
5. **Health probe** — add `tests/health/test_{source}.py` so upstream breakage surfaces on its own
6. **Visualize** — HTML report (Chart.js/Leaflet) or static map (geopandas + cached LMI layers)
7. **Register** — add a Quick Command below (the skill's `description` is its own index entry)

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
uv run python scripts/fuel.py

# EEA geospatial catalogue (sdi.eea.europa.eu, GeoNetwork 4.4)
uv run python scripts/eea_sdi.py search "grassland" --iceland --size 10
uv run python scripts/eea_sdi.py record   35a036bb-c027-401c-8625-2ecf722e8461
uv run python scripts/eea_sdi.py links    35a036bb-c027-401c-8625-2ecf722e8461
uv run python scripts/eea_sdi.py xml      35a036bb-c027-401c-8625-2ecf722e8461 -o data/raw/eea_sdi/grassland_2015.xml

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

# Download LMI geodata layers (~50 MB)
uv run python scripts/lmi.py download

# Generate Iceland maps
uv run python scripts/kortagerð.py static -o reports/iceland-map.png
uv run python scripts/kortagerð.py html -o reports/iceland-map.html
uv run python scripts/kortagerð.py static --bounds capital --highlight "Reykjavíkurborg" -o reports/rvk.png

# Náttúrufræðistofnun: download habitat-type polygons via WFS
# (vistgerðir 1:25.000 3rd ed.; DN=95 = L14.2 Tún og akurlendi, ~1,800 km²)
uv run python scripts/natt.py habitat --dn 95
uv run python scripts/natt.py inventory          # list all DN→htxt codes

# Map of Iceland's agricultural land (PNG + single-file Leaflet HTML)
uv run python scripts/agricultural_land_map.py

# Iceland grassland map (Copernicus HRL via LMI, 20 m raster) — uses Tier 3 cache
uv run python scripts/lmi_hrl.py fetch grassland       # one-time, ~860 MB
uv run python scripts/build_cache.py rasters           # one-time, → 9 MB ISN93 GeoTIFF
uv run python scripts/grassland_map.py                 # ≈3 s warm

# GRAVPI heatmap (Copernicus EEA discomap WMS — no LMI Iceland clip exists)
uv run python scripts/grassland_probability_heatmap.py

# Directorate of Health — list all dashboards, scrape one (Playwright)
uv run python scripts/landlaeknir.py list
uv run python scripts/landlaeknir.py fetch --slug mortis

# Vinnumálastofnun — Excel + Power BI capture
uv run python scripts/vinnumalastofnun.py fetch

# Farsæld barna — child wellbeing Power BI capture
uv run python scripts/farsaeld_barna.py fetch

# Vernd — asylum / international-protection dashboard
uv run python scripts/vernd.py info
uv run python scripts/vernd.py fetch

# Byggðastofnun — regional-development dashboard catalog (Tableau Public)
uv run python scripts/byggdastofnun.py list
uv run python scripts/byggdastofnun.py url tekjur

# Tekjusagan — income history (token + Playwright drive)
uv run python scripts/tekjusagan.py token
uv run python scripts/tekjusagan.py fetch

# Ferðamálastofa — Keflavík tourism Power BI
uv run python scripts/ferdamalastofa.py --help

# Velsældarvísar + Félagsvísar + Menningarvísar — Hagstofa indicator catalog
uv run python scripts/velsaeldarvisar.py fetch
uv run python scripts/velsaeldarvisar.py list --section velsaeldarvisar
uv run python scripts/velsaeldarvisar.py pxtables

# Heimsmarkmið — UN SDG national statistics (open-sdg)
uv run python scripts/heimsmarkmid.py fetch
uv run python scripts/heimsmarkmid.py list --goal 4
uv run python scripts/heimsmarkmid.py get 1-1-1

# Ríkisreikningur — state accounts ACTUALS (Fjársýsla)
uv run python scripts/rikisreikningur.py summary
uv run python scripts/rikisreikningur.py malefni
uv run python scripts/rikisreikningur.py files

# Fjárlög — state budget APPROPRIATIONS + 5-yr plan (málaflokkur level)
uv run python scripts/fjarlog.py fetch                 # → data/processed/fjarlog.parquet
uv run python scripts/fjarlog.py products              # afurð × year coverage
uv run python scripts/fjarlog.py mala 04.30            # defense across actual/enacted/bill

# CO2.is — climate action plan
uv run python scripts/co2.py fetch
uv run python scripts/co2.py list --kerfi S
uv run python scripts/co2.py list --status "Í framkvæmd"

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

# Mælaborð landbúnaðarins — cattle-subsidy recipients (Playwright scrape of "Eftir búi" matrix)
uv run python scripts/maelabord_nautgripa.py fetch

# Render cattle-subsidy farms on an Iceland map (depends on PR 1 LMI cache + PR 4 landeignaskra)
uv run python scripts/nautgripa_map.py

# Map-construction caching (Tier 3+4; ISN93-reprojected raster + Iceland constants)
uv run python scripts/build_cache.py all                 # build all derived caches
uv run python scripts/build_cache.py status              # what is cached / stale / missing
uv run python scripts/build_cache.py rasters --only grassland_isn93

# Benchmark map-construction speed (cold|warm-raw|warm), JSON history
uv run python scripts/bench_maps.py run --mode warm
uv run python scripts/bench_maps.py history

# Cache + render integration tests
uv run pytest tests/test_cache_consistency.py tests/test_maps_render.py -v
```

## Tests and source health

```bash
uv run pytest -m "not slow"            # fast, offline — what PR CI runs
uv run pytest -m slow                  # network + Playwright integration tests

# Upstream health probes (tests/health/) — smallest stable contract per source
uv run pytest -m health                        # every probe
uv run pytest -m health -k hagstofan           # one source by name
uv run pytest -m "health and not browser and not degraded_ok"   # required lane
uv run pytest -m "health and degraded_ok"      # staleness / known-soft lane
uv run pytest -m browser                       # Playwright probes (manual only)

# Render a health report from both lanes (exits non-zero only on a required failure)
uv run python scripts/health_summary.py --required health-required.xml \
  --degraded health-degraded.xml --json health-results.json
```

Health probes run daily in `.github/workflows/source-health.yml`. Browser probes
are manual-dispatch only — from a datacenter IP, Power BI/Tableau failures say
more about bot detection than about the source being down.

To add a probe for a new source, see the `new-data-source` skill.

## Scripts layout

- `scripts/*.py` — fetchers/cleaners: hit an API or read raw files, write tidy CSVs to `data/processed/`
- `scripts/health_summary.py` — renders health results from pytest JUnit XML (not a fetcher)
- `tests/health/test_{source}.py` — upstream health probes, auto-marked `slow` + `health`
- `reports/*.py` — one-off report scripts (gitignored, local-only, sit next to the `.html` they emit)

Inflation-specific analysis (derivation scripts, research reports, the whodunit blog post) lives in [`~/Code/inflation-whodunit`](../inflation-whodunit). That repo reads processed data from here.

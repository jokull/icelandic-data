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
| [lmi](/.claude/skills/lmi.md) | Landmælingar Íslands | Vector geodata via GeoServer WFS — landmask, coastline, roads, rivers, lakes, glaciers, municipalities, settlements |
| [lmi_hrl](/.claude/skills/lmi_hrl.md) | LMI / Copernicus HRL | High Resolution Layer rasters (Grassland, Tree Cover, Imperviousness, Water & Wetness, Dominant Leaf Type) for Iceland 2015 at 20 m, EPSG:5325 |
| [kortagerð](/.claude/skills/kortagerð.md) | Mapmaking | Iceland map generation from cached LMI data — static (matplotlib) and interactive (Leaflet); now includes Tier 3+4 derived-cache (ISN93-reprojected GeoTIFF + Iceland-constants JSON) for sub-10s warm renders |
| [natt](/.claude/skills/natt.md) | Náttúrufræðistofnun | Habitat-type / species / geology open data via GeoServer WFS+WMS at gis.natt.is. Vistgerðir 25k 3rd-edition vector polygons (incl. L14.2 Tún og akurlendi cultivated land). |
| [new_data_source](/.claude/skills/new_data_source.md) | Methodology | How to learn and integrate a new data source — discovery, probing, skill authoring, script conventions, testing |
| [landlaeknir](/.claude/skills/landlaeknir.md) | Directorate of Health | ~30 Power BI dashboards — mortality, medication, healthcare services, infectious disease; Talnabrunnur PDF archive |
| [vinnumalastofnun](/.claude/skills/vinnumalastofnun.md) | Directorate of Labour | Registered unemployment, job seekers, work permits — Power BI mælaborð + monthly Excel |
| [farsaeld_barna](/.claude/skills/farsaeld_barna.md) | Barna- og fjölskyldustofa | Child wellbeing dashboard (farsaeldbarna.is) — static-data Power BI scraped via modelsAndExploration |
| [vernd](/.claude/skills/vernd.md) | Ríkislögreglustjóri | International-protection (asylum) monthly stats — Power BI dashboard, applicants by year/week/nationality/gender/age |
| [byggdastofnun](/.claude/skills/byggdastofnun.md) | Byggðastofnun | Regional-development dashboards — 11 Tableau Public embeds (population, income, property tax, energy, grants, state employment) |
| [tekjusagan](/.claude/skills/tekjusagan.md) | Forsætisráðuneytið | Income history dashboard (tekjusagan.is) — token-gated Power BI, 5 report routes, driven via Playwright |
| [velsaeldarvisar](/.claude/skills/velsaeldarvisar.md) | Hagstofa Íslands | Indicator catalogs on visar.hagstofa.is — well-being + social + cultural (88 indicators → ~77 PX-Web tables) |
| [heimsmarkmid](/.claude/skills/heimsmarkmid.md) | Hagstofa Íslands | UN SDG national statistics (open-sdg) — 137 indicators across all 17 goals, ~10k rows, ZIP bundle from GitHub Pages |
| [rikisreikningur](/.claude/skills/rikisreikningur.md) | Fjársýsla ríkisins | State accounts — yearly revenue/expense (2015+), málefnasvið breakdown (36 policy areas), 35 downloadable XLSX/CSV files via Azure Functions API |
| [co2](/.claude/skills/co2.md) | Umhverfis-, orku- og loftslagsráðuneytið | Climate action plan (co2.is) — 106 numbered actions across 4 kerfi, status / ministry / start–end years, Webflow scrape |
| [umferd](/.claude/skills/umferd.md) | Vegagerðin | Traffic counters — real-time 15-min counts, 7-day rolling daily totals, 168+ stations via GeoServer WFS |
| [maelabord_landbunadarins](/.claude/skills/maelabord_landbunadarins.md) | Ministry of Agriculture | Agricultural subsidies (búvörusamningar), market data, farm/livestock stats via 3 Power BI dashboards. Includes per-farm subsidy recipients and busnr→landsnr crosswalk. |
| [eea_sdi](/.claude/skills/eea_sdi.md) | European Environment Agency | Geospatial-data catalogue (GeoNetwork 4.4) — Elasticsearch + CSW search, ISO 19115 records, OGC WMS/WFS/WCS + ArcGIS REST link discovery for ~10k Pan-European datasets (CORINE, HRL series, Natura 2000, …) |

## Adding a New Data Source

Follow the methodology in [new_data_source](/.claude/skills/new_data_source.md) — covers discovery, probing, skill authoring, script conventions, testing, and visualization. Summary:

1. **Discover** — find the API type (REST, WFS, Power BI, scraping), probe endpoints, document schema
2. **Skill file** — create `/.claude/skills/{source}.md` with API, schema, request examples, caveats
3. **Script** — create `scripts/{source}.py` with `list`/`fetch` subcommands (polars + httpx)
4. **Test** — verify output with DuckDB, check Icelandic encoding, spot-check values
5. **Visualize** — HTML report (Chart.js/Leaflet) or static map (geopandas + cached LMI layers)
6. **Register** — update this file's Active Skills table and Quick Commands

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

# Ríkisreikningur — state accounts (Fjársýsla)
uv run python scripts/rikisreikningur.py summary
uv run python scripts/rikisreikningur.py malefni
uv run python scripts/rikisreikningur.py files

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

## Scripts layout

- `scripts/*.py` — fetchers/cleaners: hit an API or read raw files, write tidy CSVs to `data/processed/`
- `reports/*.py` — one-off report scripts (gitignored, local-only, sit next to the `.html` they emit)

Inflation-specific analysis (derivation scripts, research reports, the whodunit blog post) lives in [`~/Code/inflation-whodunit`](../inflation-whodunit). That repo reads processed data from here.

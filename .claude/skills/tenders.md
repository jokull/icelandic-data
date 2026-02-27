# Public Procurement (Útboð)

Icelandic public tender data from three sources: TED API (EU-threshold, real-time), OCDS bulk data (historical), and utbodsvefur.is (domestic, web-only).

## Data Sources

| Source | Coverage | Access | Tenders |
|--------|----------|--------|---------|
| TED API | EEA-threshold (>€215k services) | REST API, no auth | ~1,481 ISL |
| OCDS (OpenTender) | 2006–2023, all published | Bulk download (JSONL/CSV) | ~3,494 |
| utbodsvefur.is | Current/active domestic | Web UI only (WordPress) | varies |
| reykjavik.is | 2018–2024 result PDFs | Web scraping | Reykjavík only |

## TED Search API

**Base URL:** `https://api.ted.europa.eu/v3/notices/search`

No authentication required. POST with JSON body, returns paginated results.

### Search all Icelandic tenders
```bash
curl -s -X POST "https://api.ted.europa.eu/v3/notices/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "organisation-country-buyer=ISL",
    "fields": ["notice-title","publication-date","buyer-city","classification-cpv","tender-value","tender-value-cur","organisation-name-buyer","description-lot","title-proc","deadline-receipt-tender-date-lot"],
    "limit": 20,
    "page": 1
  }'
```

### Search by buyer city
```bash
curl -s -X POST "https://api.ted.europa.eu/v3/notices/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "organisation-country-buyer=ISL AND buyer-city=\"Reykjav*\"",
    "fields": ["notice-title","publication-date","organisation-name-buyer","tender-value","classification-cpv"],
    "limit": 50, "page": 1
  }'
```

### Search by CPV code
```bash
curl -s -X POST "https://api.ted.europa.eu/v3/notices/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "organisation-country-buyer=ISL AND classification-cpv=90610000",
    "fields": ["notice-title","publication-date","organisation-name-buyer","tender-value"],
    "limit": 50, "page": 1
  }'
```

### Available query fields

| Field | Description |
|-------|-------------|
| `organisation-country-buyer` | ISO3 country code (`ISL`) |
| `organisation-name-buyer` | Buyer org name (supports wildcards) |
| `buyer-city` | City of buyer |
| `classification-cpv` | CPV code (8-digit) |
| `notice-title` | Title text search |
| `publication-date` | Format: `YYYYMMDD`, supports ranges |
| `estimated-value-lot` | Estimated value |
| `tender-value` | Award value |
| `tender-value-cur` | Currency (EUR/ISK) |
| `description-lot` | Lot description text |
| `title-proc` / `title-glo` | Procedure/global title |
| `deadline-receipt-tender-date-lot` | Submission deadline |
| `description-glo` | Global description |

Pagination: `page` (1-indexed) + `limit` (max 100). Country code must be ISO3 (`ISL`, not `IS`).

## OCDS Bulk Data (OpenTender)

**Download URL:** `https://data.open-contracting.org/en/publication/57/download?name=full.jsonl.gz`

License: CC BY-NC-SA 4.0. Coverage: Jan 2006 – Nov 2023 (updated ~every 6 months).

### Formats
| Format | URL param | Size |
|--------|-----------|------|
| JSONL (gzipped) | `?name=full.jsonl.gz` | ~1.6MB |
| CSV | `?name=full.csv.gz` | ~1.9MB |
| Excel | `?name=full.xlsx` | ~2.7MB |
| Year-specific | `?name=2023.jsonl.gz` | varies |

### OCDS Schema (key fields)

```json
{
  "ocid": "ocds-...",
  "buyer": {"name": "Reykjavíkurborg"},
  "tender": {
    "title": "...",
    "value": {"amount": 50000000, "currency": "ISK"},
    "items": [{"classification": {"id": "90610000", "scheme": "CPV"}}]
  },
  "awards": [{
    "value": {"amount": 48000000, "currency": "ISK"},
    "suppliers": [{"name": "Hreinsitækni ehf", "id": "..."}]
  }],
  "parties": [
    {"name": "...", "roles": ["buyer"], "address": {"locality": "Reykjavík"}}
  ]
}
```

Of ~3,494 tenders, ~1,759 have award + supplier data. 659 from Reykjavík.

## utbodsvefur.is (Web Scraping)

National tender portal. WordPress site, no API.

- Search by: buyer dropdown (79+ orgs), tender type (Framkvæmd/Vörukaup/Þjónusta/Leiguhúsnæði), free text
- Active tenders only — no historical archive
- Use Playwright if scraping needed (follow skatturinn.md pattern)
- For historical data, prefer TED/OCDS instead

## Reykjavík Tender Results (reykjavik.is)

Annual result pages with linked PDFs showing winner, bidders, amounts:

| Year | URL |
|------|-----|
| 2018 | `https://reykjavik.is/en/nidurstodur-utboda-2018` |
| 2019 | `https://reykjavik.is/en/tender-results-2019` |
| 2020 | `https://reykjavik.is/en/tender-results-2020` |
| 2021 | `https://reykjavik.is/en/tender-results-2021` |
| 2022 | `https://reykjavik.is/en/tender-results-2022` |
| 2023 | `https://reykjavik.is/en/tender-results-2023` |
| 2024 | `https://reykjavik.is/en/economy-tenders-procurement-results-tenders/nidurstodur-utboda-og-verdfyrirspurna-2024` |

Scraped by `scripts/reykjavik_tenders.py` → `data/processed/reykjavik_winter_tenders.csv`.
Result PDFs have winner/bidder/amount detail not available in TED or OCDS.

## Key Buyers

Major Icelandic public buyers (OCDS counts):

| Buyer | OCDS tenders |
|-------|-------------|
| Ríkiskaup / Fjársýslan | ~1,655 combined |
| Reykjavíkurborg | ~522 |
| Vegagerðin | ~147 |
| Landsvirkjun | ~96 |
| Landsnet | ~89 |
| OR (Orkuveita Reykjavíkur) | ~54 |
| Isavia | ~52 |
| Kópavogsbær | ~32 |

## CPV Code Reference

Common CPV codes for municipal services:

| CPV | Description |
|-----|-------------|
| 90610000 | Street cleaning |
| 90620000 | Snow clearing |
| 90630000 | Ice clearing |
| 44113600 | Bitumen |
| 34350000 | Tires |
| 45233141 | Road maintenance |

## CLI Usage

```bash
# Download OCDS bulk data
uv run python scripts/procurement.py download-ocds

# Search TED for Reykjavik tenders
uv run python scripts/procurement.py search --buyer "Reykjav" --limit 20

# Search by CPV code (street cleaning)
uv run python scripts/procurement.py search --cpv 90610000

# Export awards with suppliers to CSV
uv run python scripts/procurement.py awards --buyer "Reykjav" -o data/processed/reykjavik_awards.csv

# List top buyers from OCDS data
uv run python scripts/procurement.py buyers

# Scrape reykjavik.is tender results (existing script)
uv run python scripts/reykjavik_tenders.py
```

## Data Caveats

- TED only has above-EEA-threshold tenders (~€215k for services)
- OCDS updated every ~6 months, not real-time
- utbodsvefur.is covers domestic below-threshold tenders but no API
- Supplier names inconsistent between sources (e.g. "Hreinsitækni ehf" vs "Hreinsitækni ehf.")
- Award values sometimes EUR, sometimes ISK — check currency field
- Reykjavík appears under 3+ different buyer names in OCDS

## Related Skills

- [skatturinn](./skatturinn.md) — contractor financials/ownership
- [reykjavik](./reykjavik.md) — municipal CKAN data
- [financials](./financials.md) — extract contractor annual reports

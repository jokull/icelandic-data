# Hagstofan (Statistics Iceland)

Official statistics for Iceland via PX-Web API.

## API

**Base URL:** `https://px.hagstofa.is/pxis/api/v1/is/`

No authentication required. Returns JSON metadata (GET) or CSV/JSON data (POST).

## Fetching Data

### Browse categories
```bash
curl -s "https://px.hagstofa.is/pxis/api/v1/is/" | jq
curl -s "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/" | jq
```

### Get table metadata
```bash
curl -s "https://px.hagstofa.is/pxis/api/v1/is/{path}/{TABLE}.px" | jq
```

### Fetch all data as CSV
```bash
curl -X POST "https://px.hagstofa.is/pxis/api/v1/is/{path}/{TABLE}.px" \
  -H "Content-Type: application/json" \
  -d '{"query": [], "response": {"format": "csv"}}'
```

### Fetch filtered data
```bash
curl -X POST "https://px.hagstofa.is/pxis/api/v1/is/{path}/{TABLE}.px" \
  -H "Content-Type: application/json" \
  -d '{
    "query": [
      {"code": "Tollskrárnúmer", "selection": {"filter": "item", "values": ["87116011", "87120000"]}}
    ],
    "response": {"format": "csv"}
  }'
```

## API Categories

| Category | Path | Description |
|----------|------|-------------|
| Population | `Ibuar/` | Demographics, migration, families |
| Economy | `Efnahagur/` | GDP, national accounts, trade |
| Prices | `Verdlag/` | CPI, price indices |
| Industries | `Atvinnuvegir/` | Fishing, agriculture, tourism |
| Society | `Samfelag/` | Education, health, crime |
| Environment | `Umhverfi/` | Climate, waste, energy |
| Historical | `Sogulegar/` | Long-term historical series |

## Key Datasets

### Foreign Trade (Tollskrá)
**Path:** `Efnahagur/utanrikisverslun/1_voruvidskipti/`

| Table | Period | Description |
|-------|--------|-------------|
| `03_inntollskra/UTA03803.px` | 2023-2025 | Imports by tariff, chapters 84-99 (monthly) |
| `06_tollskrarnumereldra/UTA13813.px` | 2017-2022 | Imports by tariff, chapters 84-99 (annual) |
| `06_tollskrarnumereldra/UTA13823.px` | 2012-2016 | Imports by tariff, chapters 84-99 (annual) |

**Units available:** `kg` (weight), `cif` (value ISK), `vEin` (units)

### GDP / National Accounts
**Path:** `Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/`

| Table | Description |
|-------|-------------|
| `THJ01103.px` | GDP at constant prices 1980-2024 |
| `THJ01000.px` | Key GDP figures 1945-2024 |
| `THJ01401.px` | GDP per capita 1980-2024 |

### Population
**Path:** `Ibuar/mannfjoldi/`

| Table | Description |
|-------|-------------|
| `1_yfirlit/Yfirlit_mannfjolda/MAN00000.px` | Key population figures 1703-2025 |
| `1_yfirlit/Yfirlit_mannfjolda/MAN00101.px` | Population by sex and age |

## Tariff Codes (Bikes/E-bikes)

Classification changed in 2020:

| Code | Category | Description |
|------|----------|-------------|
| 87116010 | ebikes* | Pre-2020: E-bikes + e-scooters combined |
| 87116011 | ebikes | E-bikes (pedal-assist ≤25 km/h) |
| 87116012 | escooters | E-scooters (kick scooters with motor) |
| 87116015 | ebikes | Other small EVs ≤25 km/h |
| 87116090 | ebikes | Other electric motorcycles |
| 87120000 | bikes | Regular bicycles (no motor) |

*Discontinued 2020, split into 87116011/12/15

## Data Caveats

1. **Encoding:** CSV output uses UTF-8 with BOM. DuckDB may need `ignore_errors=true`

2. **Archive vs Current:**
   - Archive tables (`eldra efni`) have annual aggregates
   - Current tables have monthly data by country

3. **Classification changes:** Tariff codes change over time. Always check when series definitions shifted.

4. **Wide format:** PX tables often return years as columns. Use `mlr reshape` or DuckDB UNPIVOT to normalize.

5. **Icelandic headers:** Column names are in Icelandic. Common terms:
   - `Ár` = Year
   - `Mánuður` = Month
   - `Tollskrárnúmer` = Tariff code
   - `Cif verð krónur` = CIF value in ISK
   - `Viðbótar magneining` = Additional unit (count)

## Evidence Integration

SQL queries go in `/evidence-reports/sources/hagstofan/`:

```sql
-- bike_imports.sql
SELECT year, category, total_units
FROM read_csv('../data/processed/bike_imports_all.csv')
```

Run `npm run sources` to regenerate parquet files after updating CSVs.

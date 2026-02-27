# Reykjavíkurborg (Reykjavík Municipality)

Open data from Reykjavík City via two APIs:
1. **CKAN API** at gagnagatt.reykjavik.is - downloadable CSV files
2. **PX-Web API** at velstat.reykjavik.is - welfare statistics (requires POST queries)

## Data Scope

589 CKAN datasets + 293 PX-Web tables covering municipal operations, social services, demographics, and infrastructure.

**Full catalog:** [`data/reykjavik_catalog.md`](/data/reykjavik_catalog.md) — browse this first to find the right dataset before querying APIs.

- **Financial:** Annual accounts by department and fund (Ársuppgjör)
- **Education:** School enrollment, music schools, after-school programs
- **Welfare:** Home support services, elderly care, disability services
- **Infrastructure:** Water quality, waste management, energy consumption
- **Demographics:** Population by district, housing, families
- **Civic:** Election data, website analytics, service usage

## APIs

### CKAN API (gagnagatt.reykjavik.is)

**Base URL:** `https://gagnagatt.reykjavik.is/api/3/action/`

No authentication required. Returns CSV files directly.

### PX-Web API (velstat.reykjavik.is)

**Base URL:** `https://velstat.reykjavik.is/PxWeb/api/v1/is/VELSTAT/`

No authentication required. Returns JSON metadata (GET) or CSV data (POST).

**Categories:**
| Path | Description |
|------|-------------|
| `000. Lykiltölur/` | Key statistics |
| `100. Manadarleg tolfraedi/` | Monthly statistics |
| `200. Arsskyrsla/` | Annual reports |

**Subcategories (e.g., in 200. Arsskyrsla/):**
- `02 Fjarhagsadstod/` - Financial assistance
- `07 Barnavernd Reykjavikur/` - Child protection
- `10. Heimilisofbeldi/` - Domestic violence
- `11 Mannfjoldi/` - Population

**Fetch all data from a table:**
```bash
curl -X POST "https://velstat.reykjavik.is/PxWeb/api/v1/is/VELSTAT/200.%20Arsskyrsla/11%20Mannfjoldi/VEL11008.px" \
  -H "Content-Type: application/json" \
  -d '{"query": [], "response": {"format": "csv"}}' \
  -o output.csv

# Convert encoding (output is Windows-1252)
iconv -f WINDOWS-1252 -t UTF-8 output.csv > output_utf8.csv
```

## Fetching Data (CKAN)

### List all datasets
```bash
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_list" | jq '.result[:10]'
```

### Search datasets
```bash
# Search by keyword
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_search?q=mannfjoldi&rows=5" | jq

# Filter by organization
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_search?fq=organization:velferdarsvid&rows=10" | jq

# Filter by group (category)
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_search?fq=groups:ibuar&rows=10" | jq
```

### Get dataset details
```bash
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_show?id=arsuppgjor-a-hluta-reykjavikurborgar" | jq
```

### Download CSV resource
```bash
# Get resource URL from package_show, then download
curl -s "https://gagnagatt.reykjavik.is/api/3/action/package_show?id=arsuppgjor-a-hluta-reykjavikurborgar" | \
  jq -r '.result.resources[0].url' | \
  xargs curl -o data/raw/reykjavik/arsuppgjor.csv
```

## Organizations (Departments)

| ID | Name | Description |
|----|------|-------------|
| `thjonustu-og-nyskopunarsvid` | Þjónustu- og nýsköpunarsviðið | Service & Innovation (111 datasets) |
| `velferdarsvid` | Velferðarsviðið | Welfare Services (85 datasets) |
| `skola-og-fristundasvid` | Skóla- og frístundasviðið | Education & Recreation (44 datasets) |
| `umhverfis-og-skipulagssvid` | Umhverfis- og skipulagssviðið | Environment & Planning |
| `fjarmala-og-ahettusjornunarsvid` | Fjármála- og áhættustjórnarsviðið | Finance & Risk Management |
| `menningar-og-ithrottasvid` | Menningar- og íþróttasviðið | Culture & Sports |
| `mannauds-og-starfsumhverfissvid` | Mannauðs- og starfsumhverfissviðið | HR & Work Environment |

## Groups (Categories)

| ID | Name |
|----|------|
| `ibuar` | Íbúar (Residents) |
| `lydheilsa_oryggi_lydraedi` | Lýðheilsa, öryggi, lýðræði |
| `velferdarmal` | Velferðarmál (Welfare) |
| `skolar-menntun-fraedsla` | Skólar, menntun, fræðsla |
| `fjolskyldan` | Fjölskyldan (Family) |
| `husnaedismarkadur_og_skipulagsmal` | Húsnæðismarkaður og skipulagsmál |
| `umhverfi_og_audlindir` | Umhverfi og auðlindir |
| `samgongur` | Samgöngur (Transport) |
| `menning_ferdamal_og_tomstundir` | Menning, ferðamál, tómstundir |
| `vinnumarkadur` | Vinnumarkaður (Labor market) |
| `starfsemi_reykjavikurborgar` | Starfsemi Reykjavíkurborgar |

## Key Datasets

### Financial — Opin Fjármál (Annual Accounts with Vendor Detail)

**Use this for:** "What does Reykjavík spend on X?", "Who are Reykjavík's biggest vendors?", "How much does Reykjavík pay Strætó/SORPA/etc?"

**Dataset:** `arsuppgjor` on gagnagatt — CSV files per year, semicolon-delimited, 2014–2025.

**Coverage:** A-part only (tax-funded). Three funds: Reykjavíkurborg (Aðalsjóður), Eignasjóður fasteignastofa, Bílastæðasjóður. B-part entities (OR, Strætó, Félagsbústaðir, SORPA, etc.) are **not** included as buyers — but they appear as vendors when the A-part pays them.

**Download URLs (latest years):**
```bash
# 2024 full year (~94k rows)
curl -sL 'https://gagnagatt.reykjavik.is/dataset/75521327-9d99-47d1-b1fd-a273057cbb4b/resource/54bb63af-1037-47e9-9a00-165b758f09a9/download/uppg202412_island.csv' \
  -o data/raw/reykjavik_accounts/uppg202412.csv

# 2025 Q1-Q3
curl -sL 'https://gagnagatt.reykjavik.is/dataset/75521327-9d99-47d1-b1fd-a273057cbb4b/resource/ccc2422a-63c1-4145-8579-7f4e383afbc6/download/uppg202509_island.csv' \
  -o data/raw/reykjavik_accounts/uppg202509.csv

# For other years, use CKAN API:
curl -s 'https://gagnagatt.reykjavik.is/api/3/action/package_show?id=arsuppgjor' | jq '.result.resources[] | {name, url}'
```

**CSV Schema (semicolon-delimited, UTF-8):**

| Column | Description | Example |
|--------|-------------|---------|
| `uttak` | Extract ID | `UPPG202412` |
| `fyrirtaeki` | Fund name | `Reykjavíkurborg`, `Eignasjóður fasteignastofa` |
| `samtala1` | Division (svið) | `Skóla- og frístundasvið` |
| `samtala2` | Department | `Grunnskólar` |
| `samtala3` | Sub-department | `Grunnskólar` |
| `samtala4` | Category | (often empty) |
| `samtala0` | Unit/school/office | `Grandaskóli` |
| `tegund1` | Expense type L1 | `Rekstrargjöld` |
| `tegund2` | Expense type L2 | `Skrifstofu- og stjórnunarkostnaður` |
| `tegund3` | Expense type L3 | `Fjarskiptakostnaður` |
| `tegund4` | Expense type L4 | (often empty) |
| `tegund0` | Expense type detail | `Fjarskipti` |
| `vm_numer` | Vendor ID (internal) | `60829` |
| `vm_nafn` | Vendor name | `Sýn hf.` |
| `ar` | Year | `2024` |
| `arsfjordungur` | Quarter (1-4) | `3` |
| `raun` | Amount ISK | `8262` (positive=expense, negative=revenue) |

**Key divisions (samtala1) in 2024:**
- Skóla- og frístundasvið — 80 bn (schools, kindergartens, recreation)
- Velferðarsvið — 46 bn (welfare services)
- Menningar- og íþróttasvið — 20 bn (culture, sports)
- Umhverfis- og skipulagssvið — 12 bn (environment, planning)
- Framlög til B-hluta — 5.5 bn (transfers to subsidiaries)

**Top external vendors (2024):** Strætó (5.6 bn), SORPA (2 bn), Veitur/OR (1.5 bn), Slökkvilið (1.5 bn), Skólamatur (817 m).

**Note:** Salary rows have empty `vm_numer`/`vm_nafn` (personal data excluded). Internal transfers (Reykjavíkurborg ↔ Eignasjóður) are the largest "vendor" entries.

**DuckDB queries:**
```sql
-- Top vendors for a division
SELECT vm_nafn, sum(raun) as total
FROM read_csv('data/raw/reykjavik_accounts/uppg202412.csv', delim=';', header=true)
WHERE samtala1 = 'Velferðarsvið' AND raun > 0 AND vm_nafn IS NOT NULL AND vm_nafn != ''
GROUP BY 1 ORDER BY 2 DESC LIMIT 20

-- Spending by division over time (load multiple years)
SELECT ar, samtala1, sum(raun) as total
FROM read_csv('data/raw/reykjavik_accounts/uppg*.csv', delim=';', header=true, union_by_name=true)
WHERE raun > 0
GROUP BY 1, 2 ORDER BY 1, 3 DESC

-- All payments to a specific vendor
SELECT ar, arsfjordungur, samtala1, samtala0, tegund1, tegund2, raun
FROM read_csv('data/raw/reykjavik_accounts/uppg202412.csv', delim=';', header=true)
WHERE vm_nafn ILIKE '%strætó%'
ORDER BY raun DESC
```

| Dataset ID | Description |
|------------|-------------|
| `arsuppgjor` | Annual accounts A-part with vendor detail (2014-2025) |
| `arsuppgjor-b-hluta-reykjavikurborgar` | Annual accounts section B (enterprises, no vendor detail) |

### Population & Demographics
| Dataset ID | Description | Verified |
|------------|-------------|----------|
| `mannfjoldi_i_reykjavik_eftir_aldursbilum` | Population by age group (1998-2018) | ✓ |
| `mannfjoldi_i_reykjavik_eftir_hverfum_og_kyni` | Population by district and gender | |
| `mannfjoldi_og_ibudir_i_reykjavik` | Population and housing | |
| `midborgin-okkar` | Central district housing and population | |
| `fjoldi-ibua-eftir-hverfi-og-aldri` | Population by district and age | |

### Education
| Dataset ID | Description |
|------------|-------------|
| `nemendur-i-tonlistarskola-*` | Music school enrollment |
| `nemendafjoldi-i-fristundaheidmilum` | After-school program enrollment |
| `grunnskolanemendur-*` | Primary school students |

### Welfare Services
| Dataset ID | Description |
|------------|-------------|
| `heimastudningur-*` | Home support services |
| `fjoldi-*-fatlads-folks` | Disability services |
| `felags-og-fjolskylduthjonusta-*` | Social and family services |

### Infrastructure
| Dataset ID | Description |
|------------|-------------|
| `neysluvatn-veitufra-rvk-efnamaelingar` | Drinking water quality |
| `efnamaelingar-a-strondumog-i-sjorum` | Coastal water quality |
| `rafmagn-og-heitavatn-og-kalt-vatn` | Energy and water consumption |
| `sorphirda-*` | Waste collection statistics |

### Elections
| Dataset ID | Description |
|------------|-------------|
| `sveitarstjornarkosningar-*` | Municipal election results (1986-present) |
| `kjorsokn-*` | Voter turnout data |

### Nationality/Citizenship (ríkisfang)
**CKAN datasets:**
| Dataset ID | Description |
|------------|-------------|
| `erlendir_rikisborgarar_i_reykjavik_eftir_rikisfangi_med_ar_rikisfang_og_kyni_i_stafrofsrod` | Foreign citizens by country, year, gender (1998-present) |
| `erlendir_rikisborgarar_i_reykjavik_eftir_hverfum` | Foreign citizens by district |
| `erlendir_rikisborgarar_i_reykjavik_eftir_heimsalfum` | Foreign citizens by continent |
| `atvinnuleysi_i_reykjavik_eftir_manudum_rikisfangi_og_kyni` | Unemployment by nationality and gender |
| `algengustu_thjoderni_barna_af_erlendum_uppruna_i_leikskolum_borgarinnar` | Most common nationalities in kindergartens |
| `algengustu_thjoderni_nemenda_i_grunnskolum_sem_fengu_kennslu_i_islensku_sem_odru_tungumali` | Nationalities of students learning Icelandic as 2nd language |
| `fjoldi_barna_af_erlendum_uppruna_i_leikskolum_reykjavikur_eftir_thjonustumidstodvum` | Foreign-origin children in kindergartens by district |
| `thjoderni_og_fjoldi_farthega_skemmtiferdaskipa_sem_fara_um_hafnir_faxafloahafna` | Cruise passenger nationalities |

**PX-Web tables (velstat.reykjavik.is):**
| Table | Path | Description |
|-------|------|-------------|
| `VEL11008.px` | `200. Arsskyrsla/11 Mannfjoldi/` | Population by district and nationality (2010-2022) |
| `VEL11006.px` | `200. Arsskyrsla/11 Mannfjoldi/` | Population by service center, age, nationality |
| `VEL02009.px` | `200. Arsskyrsla/02 Fjarhagsadstod/` | Financial assistance recipients by nationality |
| `VST10006.px` | `100. Manadarleg tolfraedi/10. Heimilisofbeldi/` | Domestic violence reports by nationality |

## Response Structure

```json
{
  "success": true,
  "result": {
    "id": "6e0aca8d-4690-4209-a0e9-a87ebd2c412b",
    "name": "arsuppgjor-a-hluta-reykjavikurborgar",
    "title": "Ársuppgjör A-hluta Reykjávíkurborgar",
    "notes": "Dataset description...",
    "resources": [
      {
        "id": "60ab64ee-866a-4cd0-9b08-0d6ecda1b254",
        "name": "uppg202509_island.csv",
        "format": "CSV",
        "url": "https://gagnagatt.reykjavik.is/dataset/.../download/uppg202509_island.csv"
      }
    ],
    "organization": {...},
    "tags": [...]
  }
}
```

## CSV Format

Reykjavík CSVs use **Icelandic locale formatting**:

| Setting | Value |
|---------|-------|
| Delimiter | `;` (semicolon) |
| Decimal | `,` (comma) |
| Encoding | UTF-8 |

### DuckDB
```sql
SELECT *
FROM read_csv('data/raw/reykjavik/file.csv',
  delim=';',
  decimal_separator=','
)
```

### Python (polars)
```python
import polars as pl
df = pl.read_csv('data/raw/reykjavik/file.csv',
  separator=';',
  decimal_comma=True
)
```

### miller
```bash
mlr --icsv --ifs ';' --ocsv cat data/raw/reykjavik/file.csv
```

## Data Caveats

1. **Icelandic CSV format:** Semicolon delimiter, comma decimal separator (see CSV Format above).

2. **Naming conventions:** Dataset IDs use Icelandic with hyphens or underscores. Years often appear at end (e.g., `2011-2022`).

3. **Multiple resources:** Datasets often contain multiple CSV files for different time periods. Check `resources` array for all files.

4. **License:** Most datasets use "other-open" license allowing reuse.

5. **Time series:** Historical data is often split across multiple dataset IDs by year range.

6. **Updates:** Datasets are updated at varying frequencies. Check `metadata_modified` for last update.

## Icelandic Terms

### Common Column Headers
| Icelandic | English |
|-----------|---------|
| Ár | Year |
| Aldur | Age |
| Kyn | Gender |
| Fjöldi | Count/number |
| Hlutfall | Share/proportion |
| Heild / Alls | Total |

### Domain Terms
| Icelandic | English |
|-----------|---------|
| Ársuppgjör | Annual accounts |
| Íbúar | Residents |
| Hverfi | District/neighborhood |
| Þjónusta | Service |
| Velferð | Welfare |
| Skólar | Schools |
| Fjölskylda | Family |
| Heimastudningur | Home support |
| Sorphirða | Waste collection |
| Neysluvatn | Drinking water |
| Kosningar | Elections |
| Mannfjöldi | Population |
| Ríkisfang | Citizenship/nationality |
| Erlendur/Erlendir | Foreign |
| Íslenskur/Íslenskt | Icelandic |
| Þjóðerni | Nationality/ethnicity |
| Uppruni | Origin |
| Atvinnuleysi | Unemployment |
| Fjárhagsaðstoð | Financial assistance |
| Heimilisofbeldi | Domestic violence |
| Gerandi | Perpetrator |
| Þolandi | Victim |
| Þjónustumiðstöð | Service center |

## Evidence Integration

SQL queries go in `/evidence-reports/sources/reykjavik/`:

```sql
-- Example: Population time series from raw data
SELECT
  Ár as year,
  Fjöldi as population
FROM read_csv('../data/raw/reykjavik/mannfjoldi_aldursbil.csv',
  delim=';',
  decimal_separator=','
)
WHERE Aldur = 'Alls'
ORDER BY year

-- Example: From processed data (standard CSV format)
SELECT *
FROM read_csv('../data/processed/reykjavik_population.csv')
ORDER BY year
```

Run `npm run sources` to regenerate parquet files after updating CSVs.

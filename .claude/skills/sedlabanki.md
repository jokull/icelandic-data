# Seðlabanki Íslands (Central Bank of Iceland)

Monetary and financial statistics: interest rates, balance sheets, and new credit.

**Important:** Both sedlabanki.is and gagnabanki.is are JavaScript SPAs (Blazor / Angular).
Simple HTTP fetches return empty HTML shells. Use Playwright for data extraction.

## Data Scope

Three core datasets covering Iceland's monetary system:

### 0. Key Interest Rates (Meginvextir Seðlabankans)
**Type:** Daily observations
**Period:** Jan 2007 - present (18+ years)
**Frequency:** Daily (business days)

Central Bank policy rates:
- **Meginvextir / Key rate** (7-day term deposit rate) — the main policy rate since 2014
- **Vextir á daglánum / Overnight lending rate**
- **Vextir á viðskiptareikningum / Current account rate**
- Also: 7-day collateralised lending, 28-day CBI CDs, REIBOR rates

**Source:** gagnabanki.is Power BI embed (report key: `interests`)

### Data Portal: gagnabanki.is

The Central Bank's data portal at `gagnabanki.is` is an Angular SPA wrapping Power BI reports.

**Architecture:**
- Config API: `GET https://gagnabanki.is/api/config` — returns all report IDs, time series keys, filters
- Embed token: `GET https://gagnabanki.is/api/embed/{groupId}/{reportId}`
- Group ID: `05060786-7f48-4442-8981-314b262d68a7`
- Data flows through Power BI's WABI backend (`*.pbidedicated.windows.net`)

**Interest Rate Report:**
- Config key: `interests`
- Report ID (live): `2b28c90f-7da7-4fd0-bd9b-f87ffeddbb07`
- Dataset: `e75e5a3b-6118-4899-a266-62550d1b32e4`
- Default series: keys 24, 28, 17923
- All series keys: `[17923, 28, 75, 55, 24, 3459, 17922, 4125, 289, 3460, 3461, 3458]`

**Extraction method:** Playwright intercepts Power BI `querydata` responses from `*.pbidedicated.windows.net`. Data arrives in DSR (DataShapeResult) format with compressed values.

```bash
# Fetch interest rates to CSV
uv run python scripts/sedlabanki_rates.py

# Output as JSON
uv run python scripts/sedlabanki_rates.py --json
```

**Output:** `data/processed/sedlabanki_rates.csv` with columns: date, series, value

### 1. Balance Sheets (Efnahagur innlánsstofnana) — via SDMX
**Type:** Stock (end-of-month positions)
**Period:** Sept 1993 - present (387+ months, 32 years)
**Frequency:** Monthly

Full balance sheet of deposit-taking institutions:
- **Assets** (Eignir)
  - Domestic: Loans (indexed/non-indexed), deposits, securities, derivatives
  - Foreign: Same breakdown for foreign-held assets
- **Liabilities** (Skuldir)
  - Deposits (demand/term), debt securities, borrowing, equity

### 2. New Credit (Ný útlán) — via Library Download
**Type:** Flow (net new lending minus prepayments)
**Period:** Jan 2013 - present (155+ months, 13 years)
**Frequency:** Monthly

New lending by sector and index type:
- **Sectors:** Non-financial corps (by industry), Financial corps, Government, Households
- **Household detail:** Mortgages (fixed/floating rate), car loans
- **Index types:** Indexed (verðtryggð), Non-indexed, Foreign currency

## API

**Portal:** `https://gagnabanki.is/report/monetary`
**Download Proxy:** `https://gagnabanki.is/api/download` (POST)

## Download URLs

| Dataset | URL Type | Download URL |
|---------|----------|--------------|
| Balance Sheets | SDMX | `https://fr.sedlabanki.is/sdmx/v2/table/IS2_EXT/INN_BALANCE_SHEETS_TOTAL/1.0?format=xlsx` |
| New Credit | Library | `https://sedlabanki.is/library?itemid=b73e42d6-ba32-4eb3-b39e-1c70d2e45aec` |

## Fetching Data

```bash
# Balance Sheets (32 years of monthly stock data)
curl 'https://gagnabanki.is/api/download' \
  -X POST -H 'Content-Type: application/json' \
  --data-raw '{"url":"https://fr.sedlabanki.is/sdmx/v2/table/IS2_EXT/INN_BALANCE_SHEETS_TOTAL/1.0?format=xlsx"}' \
  -o data/raw/sedlabanki/balance_sheets.xlsx

# New Credit (13 years of monthly flow data)
curl 'https://gagnabanki.is/api/download' \
  -X POST -H 'Content-Type: application/json' \
  --data-raw '{"url":"https://sedlabanki.is/library?itemid=b73e42d6-ba32-4eb3-b39e-1c70d2e45aec"}' \
  -o data/raw/sedlabanki/newcredit.xlsx
```

## Data Structure

### Balance Sheets Excel Layout
- Sheet: `INN_BALANCE_SHEETS_TOTAL`
- Row 3: Date headers (1993-09, 1993-10, ...)
- Row 4+: Balance sheet line items with hierarchy (indented)
- Column B: Row labels (Icelandic / English)
- Column C+: Monthly values in M.kr.

**Key line items:**
```
Eignir samtals / Assets, total
  Innlendar eignir / Domestic assets
    Lán / Loans
      Útlán / Loans outstanding
      Niðurfærslur / Provisions (negative)
  Erlendar eignir / Foreign assets
Skuldir samtals / Liabilities, total
  Innlán / Deposits
  Markaðsskuldabréf / Debt securities issued
  Eigið fé / Equity
```

### New Credit Excel Layout
- Sheet: `I`
- Row 10: Header with "M.kr." and dates
- Row 11+: Sector rows
- Repeating blocks for: Total, Non-indexed, Indexed, Foreign currency

**Sector hierarchy:**
```
Ný útlán / New credit (total)
├── Atvinnufyrirtæki / Non-financial corporations
│   ├── Landbúnaður / Agriculture
│   ├── Fiskveiðar / Fisheries
│   ├── Iðnaður / Manufacturing
│   └── ...
├── Fjármálageiri / Financial corporations
├── Hið opinbera / Government
├── Heimili / Households
│   ├── Lán með veði í íbúð / Mortgage loans
│   │   ├── Breytilegir vextir / Floating rate
│   │   └── Fastir vextir / Fixed rate
│   └── Bílalán / Car loans
└── Erlendur aðili / Non-residents
```

## Processing Pipeline

```bash
# Process both datasets to tidy CSVs
uv run python scripts/sedlabanki.py
```

**Outputs:**
- `data/processed/sedlabanki_newcredit.csv` - New credit by sector
- `data/processed/sedlabanki_balance_sheets.csv` - Balance sheet items

## Icelandic Terms

| Icelandic | English |
|-----------|---------|
| Innlánsstofnanir | Deposit institutions (banks) |
| Efnahagur | Balance sheet |
| Eignir | Assets |
| Skuldir | Liabilities |
| Útlán | Loans (outstanding) |
| Ný útlán | New credit (flow) |
| Innlán | Deposits |
| Verðtryggð | Indexed (to inflation) |
| Óverðtryggð | Non-indexed |
| Heimili | Households |
| Atvinnufyrirtæki | Non-financial corporations |

## Data Notes

1. **Stock vs Flow:** Balance sheets are end-of-month stocks; New credit is monthly flow (new loans minus prepayments)

2. **Indexation:** Icelandic loans are either indexed to CPI (verðtryggð) or non-indexed. This distinction is critical for analyzing credit conditions.

3. **Provisional data:** Latest months are provisional, revised when annual accounts published

4. **Units:** All values in M.kr. (million ISK)

5. **Source:** Data collection per Act 92/2019 on the Central Bank of Iceland

6. **Encoding.** Icelandic chars (þ, ð, æ, ö) appear in sector names (Heimili, Atvinnufyrirtæki, verðtryggð) across both SDMX exports and the gagnabanki Power BI payload. Read CSV with `encoding="utf-8"` (the Excel-derived files are `utf-8-sig`); write JSON with `ensure_ascii=False`.

## Evidence Integration

```sql
-- Example: Household mortgage trends
SELECT date, sector_en, value_mkr
FROM read_csv('../data/processed/sedlabanki_newcredit.csv')
WHERE sector_en LIKE 'Housholds%mortgage%'
ORDER BY date

-- Example: Total bank assets over time
SELECT date, value_mkr as assets_mkr
FROM read_csv('../data/processed/sedlabanki_balance_sheets.csv')
WHERE item_en = 'Assets, total'
ORDER BY date
```

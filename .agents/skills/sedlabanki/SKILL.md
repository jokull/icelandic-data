---
name: sedlabanki
description: Central Bank of Iceland — SDMX balance sheets + new credit, key interest rates via gagnabanki, and FX intervention (kaup/sala, turnover, reserves, ISK/EUR).
---

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

### 3. FX Intervention (Gjaldeyriskaup/-sala) — via XML Time Series
**Type:** Flow (daily CBI FX purchases/sales, market turnover) + stock (reserves)
**Period:** Daily series since Jan 2009; reserves monthly since Jan 1994
**Frequency:** Daily (business days), aggregated monthly downstream

CBI foreign-exchange intervention — the answer to "did the CBI defend the
króna?" questions (e.g. the COVID 2020-21 period and the 2025 carry-trade era):
- **TS 285** Gjaldeyrissala SÍ í ISK — CBI *sales* of foreign currency, M.kr. (positive = CBI sells FX)
- **TS 287** Gjaldeyriskaup SÍ í ISK — CBI *purchases* of foreign currency, M.kr.
- **TS 284** Heildarvelta á innlendum gjaldeyrismarkaði — total interbank FX market turnover, M.kr.
- **TS 282** Same turnover, M.eur
- **TS 4064** Evra, skráð miðgengi — official EUR mid rate (ISK per EUR), daily
- **FX reserves** (Gjaldeyrisforði) — from the CBI's own balance sheet workbook ("Sedlabanki" sheet, row "Liðir til skýringar: Gjaldeyrisforði"), monthly M.kr.

**Source:** `https://sedlabanki.is/xmltimeseries/Default.aspx` — plain HTTP,
**directly fetchable** (no Playwright, no gagnabanki proxy) for the daily series.
The reserves workbook is a `sedlabanki.is/library` item fetched through the
gagnabanki proxy (see Download URLs).

**Fetch:** `uv run python scripts/sedlabanki_fx.py fetch`
**Output:** `data/processed/sedlabanki_fx_intervention.csv` — monthly rows with
`date, net_purchases_mkr, turnover_mkr, reserves_mkr, isk_per_eur, item_en`.
`net_purchases_mkr` = kaup − sala (negative = CBI net seller, defending the
króna; positive = accumulating reserves). Reserves and ISK/EUR are month-end;
the daily flow series are summed per month.

**Known COVID-era pattern (verified against this data):** the CBI was a heavy
net SELLER of FX from March 2020 through spring 2021 (net −132.7 bn kr in 2020,
−22.7 bn kr in 2021; monthly peaks Oct 2020 −38.3 bn kr), selling reserves to
support the króna as ISK/EUR rose from ~135 (Dec 2019) to a trough ~164 (Oct
2020), then recovered to ~146-150 through 2021. It flipped to a net BUYER from
2025 (67.9 bn kr bought in 2025, matching the 67.9 ma.kr. stated in
Peningamál 2026/1).

## API

**Portal:** `https://gagnabanki.is/report/monetary`
**Download Proxy:** `https://gagnabanki.is/api/download` (POST)

> ### ⚠️ `fr.sedlabanki.is` is not fetchable directly — the proxy is mandatory
>
> The SDMX host resolves (`217.151.180.10`, a Vodafone Iceland xDSL pool address)
> but **black-holes on both 80 and 443** from the public internet: connections
> hang until timeout rather than being refused. It has never been publicly
> reachable — archive.org has zero captures of it, ever.
>
> The server itself is alive and serving current data. Seðlabanki's own backend
> reaches it, so **every SDMX fetch must go through
> `POST https://gagnabanki.is/api/download`**, which performs the GET from inside
> their network. This is a hard requirement, not a convenience wrapper.
>
> The SDMX URL below is therefore a **proxy payload, not a URL you can curl**.
> If you `curl` it directly you will get a `ConnectTimeout` and conclude the
> service is dead. It isn't.
>
> The block mechanism (geo-restriction, source-IP allowlist, or a public A record
> fronting a firewalled host) is **unverified** — only the effect is established.

## Download URLs

| Dataset | URL Type | Direct? | URL |
|---------|----------|---------|-----|
| Balance Sheets | SDMX | ❌ **proxy only** | `https://fr.sedlabanki.is/sdmx/v2/table/IS2_EXT/INN_BALANCE_SHEETS_TOTAL/1.0?format=xlsx` |
| New Credit | Library | ✅ direct | `https://sedlabanki.is/library?itemid=b73e42d6-ba32-4eb3-b39e-1c70d2e45aec` |
| FX market (daily) | XML time series | ✅ **direct** | `https://sedlabanki.is/xmltimeseries/Default.aspx?DagsFra=2009-01-01&GroupID=8&Type=csv` |
| EUR mid rate (daily) | XML time series | ✅ **direct** | `https://sedlabanki.is/xmltimeseries/Default.aspx?DagsFra=2009-01-01&TimeSeriesID=4064&Type=csv` |
| CBI balance sheet (reserves) | Library | ❌ **proxy only** | `https://sedlabanki.is/library?itemid=c0126d81-fd88-42bd-aee3-449e09b9089f` |

### XML Time Series endpoint (`xmltimeseries`)

Separate from the SDMX service: a simple public GET at `sedlabanki.is` (NOT
`www.` — that host 301s), returning `Type=csv` as a **headerless semicolon
CSV**: `group;group_name;series_id;;series_name;description;date;value`.
Dates are `M/D/YYYY h:mm:ss AM` — parse with `%m/%d/%Y %I:%M:%S %p`. Parameters:
`DagsFra`/`DagsTil` (`YYYY-MM-DD`, or `LATEST`/`TODAY`), `GroupID` or
`TimeSeriesID`, `Type=xml|csv`. See the full catalog at
`https://sedlabanki.is/gagnatorg/xml-gogn/` (GroupID 8 = "Velta á
gjaldeyrismarkaði", the FX market group; the official mid rates are GroupID 9).

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

### FX Intervention CSV Layout

`data/processed/sedlabanki_fx_intervention.csv` — one row per month:

| Column | Type | Meaning |
|--------|------|---------|
| date | date (YYYY-MM-01) | month (flows are monthly sums; stocks are month-end) |
| net_purchases_mkr | float | CBI kaup − sala, M.kr. **negative = CBI net seller of FX** |
| turnover_mkr | float | interbank FX market total turnover, M.kr. |
| reserves_mkr | float | month-end FX reserves (Gjaldeyrisforði), M.kr. |
| isk_per_eur | float | month-end official EUR mid rate |
| item_en | str | descriptive label of the row |

### CBI Balance Sheet Excel Layout (for reserves)
- Sheets: `FAME Persistence2`, `Sedlabanki`
- `Sedlabanki` sheet: row 9 = date headers (`1994-01-31 00:00:00`, …), row 60 = `Liðir til skýringar: Gjaldeyrisforði (erlendar eignir, a-f)` — the FX reserves memo line, M.kr.

## Processing Pipeline

```bash
# Process balance sheets + new credit to tidy CSVs
uv run python scripts/sedlabanki.py

# Fetch FX intervention data (raw + processed monthly CSV)
uv run python scripts/sedlabanki_fx.py fetch

# List the daily FX series available upstream
uv run python scripts/sedlabanki_fx.py list
```

**Outputs:**
- `data/processed/sedlabanki_newcredit.csv` - New credit by sector
- `data/processed/sedlabanki_balance_sheets.csv` - Balance sheet items
- `data/processed/sedlabanki_fx_intervention.csv` - FX intervention (monthly)

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
| Gjaldeyriskaup | FX purchases (CBI buys foreign currency) |
| Gjaldeyrissala | FX sales (CBI sells foreign currency) |
| Gjaldeyrisforði | FX reserves |
| Velta á gjaldeyrismarkaði | FX market turnover |
| Skráð miðgengi | Official mid rate |

## Data Notes

1. **Stock vs Flow:** Balance sheets are end-of-month stocks; New credit is monthly flow (new loans minus prepayments)

2. **Indexation:** Icelandic loans are either indexed to CPI (verðtryggð) or non-indexed. This distinction is critical for analyzing credit conditions.

3. **Provisional data:** Latest months are provisional, revised when annual accounts published

4. **Units:** All values in M.kr. (million ISK)

5. **Source:** Data collection per Act 92/2019 on the Central Bank of Iceland

6. **Encoding.** Icelandic chars (þ, ð, æ, ö) appear in sector names (Heimili, Atvinnufyrirtæki, verðtryggð) across both SDMX exports and the gagnabanki Power BI payload. Read CSV with `encoding="utf-8"` (the Excel-derived files are `utf-8-sig`); write JSON with `ensure_ascii=False`.

7. **FX sign convention.** In `sedlabanki_fx_intervention.csv`, `net_purchases_mkr` = kaup − sala, so a **negative** value means the CBI *sold* FX that month (net) — the direction that defends/dampens the króna. Series 285 (sala) and 287 (kaup) are both reported as positive numbers upstream; the sign appears only in the net column.

8. **FX provisional data.** The daily FX market numbers are provisional ("nýjustu tölur eru bráðabirgðatölur") and revised; the daily series update each business day at 16:00 with a two-day lag.

9. **Reserves workbook layout is positional.** The `Sedlabanki` sheet reserves row (60) and date row (9) are assumed by row number in `scripts/sedlabanki_fx.py`. If the CBI reorders the workbook, the reserves column breaks — the health test only catches reachability, not the row numbers.

10. **XML endpoint quirks.** Use `sedlabanki.is` (the `www.` host 301s). The CSV is headerless and semicolon-delimited with an empty 4th field, and dates are US-format `M/D/YYYY h:mm:ss AM`. The `LATEST` keyword returns only the most recent observation — use explicit `DagsFra`/`DagsTil` for ranges.

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

-- Example: CBI FX intervention through COVID (net seller = negative)
SELECT date, net_purchases_mkr, turnover_mkr, reserves_mkr, isk_per_eur
FROM read_csv('../data/processed/sedlabanki_fx_intervention.csv')
WHERE date BETWEEN DATE '2020-01-01' AND DATE '2021-12-31'
ORDER BY date
```

# Opnir Reikningar — Government Invoice Data

## Overview

[opnirreikningar.is](https://opnirreikningar.is) publishes paid invoices from Icelandic government agencies (ministries, directorates). No auth required.

**Scope:** Paid invoices with org, vendor, amount, date, invoice number. Monthly updates (~10th of following month). Coverage: 2017–present.

**Excludes:** Salaries, foreign currency transactions, benefits, healthcare provider payments, prisoner payments, security operations. No municipality data — central government only.

## API Endpoints

Base URL: `https://opnirreikningar.is`

### 1. Invoice Search (DataTables pagination)

```
GET /data_pagination_search?vendor_id=&type_id=&org_id=14412&timabil_fra=01.01.2025&timabil_til=31.01.2025&draw=1&columns[0][data]=org_name&columns[1][data]=check_date&columns[2][data]=vendor_name&columns[3][data]=invoice_amount&columns[4][data]=check_amount&start=0&length=500&order[0][column]=1&order[0][dir]=desc
```

**Required headers:** `X-Requested-With: XMLHttpRequest`, `Accept: application/json`

**Optional:** `org_text=<id> - <name>` (URL-encoded) when filtering by org

**Key:** Only abbreviated column spec needed (`columns[N][data]=<name>`) — full DataTables sub-params are not required. The `draw`, `order`, and 5-column layout are required.

**Response:**
```json
{
  "draw": 1,
  "data": [
    {
      "org_name": "Veðurstofa Íslands",
      "check_date": "2025-01-31",
      "check_amount": 507706,
      "vendor_name": "Síminn hf.",
      "invoice_num": "12345",
      "invoice_date": "2025-01-15",
      "invoice_description": "",
      "invoice_amount": 507706,
      "check_id": 18048834,
      "invoice_id": 22050869,
      "unique_id": "18048834_22050869",
      "attachments": 0
    }
  ]
}
```

**Pagination:** No `recordsTotal` — paginate with `start` param (increment by `length`) until `data: []`.

**Date params:** `DD.MM.YYYY` (input), but response dates are ISO `YYYY-MM-DD`. Amounts are integers (ISK).

### 2. Autocomplete

```bash
# Organizations
curl 'https://opnirreikningar.is/rest/org?term=veg'
# → {"data": [{"id": "10211", "text": "Vegagerðin, rekstur"}]}

# Vendors (id = kennitala)
curl 'https://opnirreikningar.is/rest/vendor?term=Síminn'
# → {"data": [{"id": "4602070880", "text": "Síminn hf."}]}

# Expense types
curl 'https://opnirreikningar.is/rest/type?term=ferð'
# → {"data": [{"id": "...", "text": "... - Ferðakostnaður"}]}
```

### 3. Date Range

```bash
curl 'https://opnirreikningar.is/rest/max_time_period'
# → "2025-11-30" (plain text, last available month)
```

### 4. Invoice Line Items

```
GET /data_pagination_line?invoice_id=<id>&start=0&length=10&...columns...
```

Returns `type_text`, `line_description`, `line_amount`. May require session cookie — lower priority.

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `org_name` | string | Government agency name |
| `check_date` | string | Payment date (YYYY-MM-DD) |
| `check_amount` | int | Payment amount in ISK |
| `vendor_name` | string | Vendor/supplier name |
| `invoice_num` | string | Invoice number |
| `invoice_date` | string | Invoice date (YYYY-MM-DD) |
| `invoice_description` | string | Free-text description |
| `invoice_amount` | int | Invoice amount in ISK |
| `check_id` | int | Internal payment ID |
| `invoice_id` | int | Internal invoice ID |
| `unique_id` | string | Unique row ID (`check_id_invoice_id`) |
| `attachments` | int | Attachment count (usually 0) |

## Key Organizations

| Org ID | Name |
|--------|------|
| 10211 | Vegagerðin, rekstur (Road Administration) |
| 14400 | Landspítali (National Hospital) |
| 14418 | Ríkiskaup (State Procurement) |
| 14412 | Veðurstofa Íslands (Met Office) |
| 14401 | Háskóli Íslands (University of Iceland) |

Use `search-org` subcommand to look up IDs.

## CLI Usage

```bash
# Lookup org ID
uv run python scripts/opnirreikningar.py search-org "veg"

# Lookup vendor kennitala
uv run python scripts/opnirreikningar.py search-vendor "siminn"

# Fetch invoices to CSV
uv run python scripts/opnirreikningar.py fetch --org 14412 --from 2025-01-01 --to 2025-01-31 -o data/processed/vedurstofa_jan2025.csv

# Top vendors for an org in a year
uv run python scripts/opnirreikningar.py top-vendors --org 14412 --year 2024
```

## Caveats

- **51-row first-page cap** — the server silently truncates the first page to ~51 rows regardless of `length`. Use `length=50` and paginate with `start` to get all results. Dedup by `unique_id`.
- **No recordsTotal** — must paginate until empty response
- **Full dump requires iterating all orgs** — without `org_id` or `vendor_id`, pagination may not work. Must enumerate orgs via autocomplete, then paginate each.
- **Date params** — API accepts DD.MM.YYYY for `timabil_fra`/`timabil_til`, but returns ISO dates and integer amounts
- **Vendor search is accent-sensitive** — use `Síminn` not `siminn`
- **Monthly lag** — data appears ~10th of following month. Use `/rest/max_time_period` to check latest available date (returns `YYYY-MM-DD`). As of 2026-02-21, latest data is 2026-01-30.
- **Central government only** — no municipalities, no SOEs
- **Amounts** — integers in ISK (no decimals)

## Related Skills

- **skatturinn** — look up vendor kennitala → company info, annual reports
- **tenders** — cross-reference procurement contracts with actual payments

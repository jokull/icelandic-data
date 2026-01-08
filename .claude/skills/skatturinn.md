# Skatturinn (Iceland Tax Authority)

Company registry and annual reports (ársreikningar) from the Icelandic tax authority.

## Overview

Skatturinn operates the Company Registry (Fyrirtækjaskrá) and Annual Reports Registry (Ársreikningaskrá). Annual reports are available free of charge since January 1, 2021, but require browser automation to download due to a shopping cart workflow with anti-bot measures.

**Use case:** Map company ownership chains by extracting beneficial owners from annual reports, then recursively looking up parent company reports.

## URLs

| Resource | URL Pattern |
|----------|-------------|
| Company lookup | `https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}` |
| Search by name | `https://www.skatturinn.is/fyrirtaekjaskra/leit?nafn={company_name}` |
| Search page | `https://www.skatturinn.is/fyrirtaekjaskra/leit` |
| Annual reports info | `https://www.skatturinn.is/fyrirtaekjaskra/arsreikningaskra/` |
| API Portal | `https://api.skatturinn.is/` (requires registration, limited endpoints) |

## Finding a Company's Kennitala

To find a company's kennitala by name, use WebFetch on the search URL:

```
https://www.skatturinn.is/fyrirtaekjaskra/leit?nafn={company_name}
```

Example: `?nafn=dansport` returns the company page with kennitala `4807032350`.

This is more reliable than Google searches. The page shows matching companies with their kennitala prominently displayed.

## Data Available

### Company Lookup Page

Each company page at `/fyrirtaekjaskra/leit/kennitala/{kt}` shows:

- **Basic info:** Name, kennitala, address, registration date, legal form
- **Management:** Directors, beneficial owners with ownership percentages
- **Activity:** ÍSAT codes (business classification)
- **Annual reports table:** List of submitted reports with:
  - Operating year (Rek. ár)
  - Submission date (Skiladagsetning)
  - Report number (Nr. ársreiknings)
  - Report type (Tegund ársreiknings)

### Annual Report PDFs

Reports contain:
- Balance sheet, income statement, cash flow
- **Beneficial ownership (Raunverulegir eigendur):** Name, kennitala, ownership %
- **Shareholders (Hluthafar):** For smaller companies
- Notes on related party transactions

## Access Method: Playwright

No public API exists for downloading annual reports. The website uses a shopping cart system that requires JavaScript interaction.

### Setup

```bash
# Install dependencies (already in pyproject.toml)
uv sync

# Install Chromium browser
uv run playwright install chromium
```

### Page Structure (Verified)

**Beneficial Owners** - in `.collapsebox` elements:
```html
<div class="collapsebox">
  <span><h4>Viktor Ólason</h4></span>
  <div class="tablewrap">
    <table class="annualTable">
      <thead>
        <tr><th>Fæðingarár/mán</th><th>Búsetuland</th><th>Ríkisfang</th><th>Eignarhlutur</th><th>Tegund eignahalds</th></tr>
      </thead>
      <tbody>
        <tr><td>1964-JÚNÍ</td><td>Ísland</td><td>Ísland</td><td>100%</td><td>Beint eignarhald</td></tr>
      </tbody>
    </table>
  </div>
</div>
```

**Annual Reports** - table with `td[data-itemid]`:
```html
<td data-itemid="808877" data-typeid="1">Ársreikningur<a href="#" class="tocart">Kaupa</a></td>
```

**Report Type IDs:**
| typeid | Type | Download |
|--------|------|----------|
| 1 | Ársreikningur (PDF) | Works |
| 4 | Rafrænn ársreikningur (XBRL?) | Different flow, may fail |

Some years have `typeid=4` instead of `1`. The current script only handles `typeid=1` reliably.

### Download Flow (Verified)

1. **Add to cart** via API:
   ```
   GET /da/CartService/addToCart?itemid={itemid}&typeid={typeid}
   ```
   Returns: `{"addCartItemResult": true, "shoppingCartUrl": "https://vefur.rsk.is/Vefverslun/Default.aspx?kid=XXXX"}`

2. **Navigate to cart URL** from response

3. **Click "Áfram"** button to proceed

4. **Download triggers** - clicking download button returns PDF

### CLI Usage

```bash
# Get company info with beneficial owners
uv run python scripts/skatturinn.py info 5012043070

# Download specific year
uv run python scripts/skatturinn.py download 5012043070 --year 2024

# Download all available reports
uv run python scripts/skatturinn.py download 5012043070

# Map ownership chain (recursive)
uv run python scripts/skatturinn.py chain 5012043070 --depth 3
```

### Anti-Bot Measures

Observed behavior:
1. **Session cookies required** - JSESSIONID must persist across requests
2. **Rate limiting** - 3 second delay recommended between requests
3. **Cross-domain flow** - Cart redirects from skatturinn.is to vefur.rsk.is

## PDF Extraction

### Report Types

1. **Hnappurinn (Micro-company)** - Simplified 4-page format without ownership section. Only financial statements.
2. **Full ársreikningur** - Complete reports with ownership tables, auditor statements, detailed notes.

For ownership chain mapping, the **web page scraping** is more reliable since it shows current beneficial owners directly. PDF extraction is useful for historical ownership or additional shareholder detail in full reports.

### Extract Command

```bash
# Test extraction from any PDF
uv run python scripts/skatturinn.py extract /path/to/report.pdf
```

The script looks for:
- Kennitala patterns: `\d{6}-?\d{4}`
- Ownership percentages: `\d+%`
- Section keywords: "eigend", "hluthaf", "eignarhald"

## Ownership Chain Mapping

The main use case: follow ownership through multiple levels.

```python
async def map_ownership_chain(
    root_kennitala: str,
    max_depth: int = 5,
    visited: set[str] | None = None
) -> dict:
    """
    Recursively map ownership chain starting from a company.

    Returns nested structure:
    {
        "kennitala": "5012043070",
        "name": "Example ehf.",
        "owners": [
            {
                "kennitala": "1234567890",
                "name": "Parent Company hf.",
                "ownership_pct": 100.0,
                "type": "company",
                "owners": [...]  # Recursive
            },
            {
                "kennitala": "0101801234",
                "name": "Jón Jónsson",
                "ownership_pct": 50.0,
                "type": "person"  # No recursion for individuals
            }
        ]
    }
    """
    if visited is None:
        visited = set()

    if root_kennitala in visited or max_depth <= 0:
        return {"kennitala": root_kennitala, "circular_ref": True}

    visited.add(root_kennitala)

    # Get company info from skatturinn
    info = await get_company_info(root_kennitala)

    # Download latest annual report and extract ownership
    # (page info may be stale - PDF has authoritative ownership)

    result = {
        "kennitala": root_kennitala,
        "name": info["name"],
        "owners": []
    }

    for owner in info["beneficial_owners"]:
        owner_kt = owner["kennitala"]

        # Determine if owner is company or person
        # Companies: first 2 digits are month (01-12), not day
        # Actually: company kennitalas start with 4-7 in first digit
        is_company = owner_kt[0] in "4567"

        owner_data = {
            "kennitala": owner_kt,
            "name": owner["name"],
            "ownership_pct": owner["ownership_pct"],
            "type": "company" if is_company else "person"
        }

        if is_company:
            # Recurse into parent company
            owner_data["owners"] = (await map_ownership_chain(
                owner_kt, max_depth - 1, visited
            )).get("owners", [])

        result["owners"].append(owner_data)

    return result
```

## Kennitala Format

Icelandic identification numbers:

| Type | Format | First digit | Example |
|------|--------|-------------|---------|
| Person | DDMMYY-NNNN | 0-3 (day) | 0101801234 (Jan 1, 1980) |
| Company | DDMMYY-NNNN | 4-7 | 5012043070 (Dec 10, 2004) |

The first 6 digits encode the registration date. Century determined by 9th digit:
- 8 = 1800s, 9 = 1900s, 0 = 2000s

## Data Caveats

1. **PDF variability:** Report formats vary by year and preparer (accountant). Some are structured, some are scanned images.

2. **Ownership on page vs PDF:** The company lookup page shows current beneficial owners. The annual report PDF shows ownership as of fiscal year end - these may differ.

3. **Holding structures:** Beneficial owners may be foreign entities without Icelandic kennitala, making chain tracing incomplete.

4. **Rate limits:** Unknown but assume conservative limits. Add 2-5 second delays between requests.

5. **Terms of service:** No explicit prohibition on automated access, but bulk scraping may trigger blocks. Consider contacting fyrirtaekjaskra@skatturinn.is for data access agreements.

6. **Session cookies:** The shopping cart requires maintaining session state. Don't create new browser contexts between adding items and downloading.

## Evidence Integration

Store extracted data in `/data/processed/skatturinn/`:

```
/data/
  /raw/skatturinn/
    /{kennitala}_{year}.pdf     # Original PDFs
  /processed/skatturinn/
    /companies.csv              # Company metadata
    /ownership.csv              # Ownership relationships
    /ownership_chains.json      # Full chain mapping
```

SQL queries in `/evidence-reports/sources/skatturinn/`:

```sql
-- ownership_network.sql
SELECT
    parent_kt,
    child_kt,
    ownership_pct,
    depth
FROM read_csv('../data/processed/skatturinn/ownership.csv')
```

## Quick Commands

```bash
# Download single report
uv run python scripts/skatturinn.py download --kennitala 5012043070 --year 2023

# Map ownership chain
uv run python scripts/skatturinn.py chain --kennitala 5012043070 --depth 3

# Bulk download for list of companies
uv run python scripts/skatturinn.py bulk --input companies.txt --year 2023
```

## Related Skills

- [hagstofan](./hagstofan.md) - Statistics Iceland for economic context
- [sedlabanki](./sedlabanki.md) - Central Bank for financial sector data
- [National Registers API](https://gagnatorg.ja.is/docs/skra/v1/) - Basic company info (no annual reports)

# Financials (Annual Report Extraction)

Extract structured financial data from Icelandic annual reports (ársreikningar) using AI-powered PDF parsing.

## Overview

This skill combines:
1. **skatturinn** skill - Downloads annual report PDFs
2. **Docling** - IBM's PDF extraction with 97.9% table accuracy
3. **Claude interpretation** - Standardizes extracted data into structured format

## Pipeline

```
Company kennitala
    ↓
skatturinn.py download (PDF)
    ↓
Docling (markdown + tables)
    ↓
Claude (structured JSON)
    ↓
Standardized financial data
```

## Output Schema

```typescript
interface CompanyFinancials {
  // Identification
  company_name: string;
  kennitala: string;
  fiscal_year: number;
  report_type: "full" | "hnappurinn" | "consolidated";

  // Income Statement (Rekstraryfirlit)
  income: {
    revenue: number;              // Rekstrartekjur
    operating_expenses: number;   // Rekstrargjöld
    ebitda: number;               // Afkoma fyrir afskriftir
    depreciation: number;         // Afskriftir
    ebit: number;                 // Afkoma fyrir fjármagnsliði
    financial_income: number;     // Fjármunatekjur
    financial_expenses: number;   // Fjármagnsgjöld
    profit_before_tax: number;    // Afkoma fyrir skatt
    income_tax: number;           // Tekjuskattur
    net_profit: number;           // Hagnaður/Tap ársins
  };

  // Balance Sheet (Efnahagsyfirlit)
  balance: {
    // Assets (Eignir)
    fixed_assets: number;         // Fastafjármunir
    current_assets: number;       // Veltufjármunir
    total_assets: number;         // Eignir samtals

    // Equity & Liabilities
    share_capital: number;        // Hlutafé
    retained_earnings: number;    // Óráðstafað eigið fé
    total_equity: number;         // Eigið fé samtals
    long_term_debt: number;       // Langtímaskuldir
    short_term_debt: number;      // Skammtímaskuldir
    total_liabilities: number;    // Skuldir samtals
  };

  // Cash Flow (if available)
  cashflow?: {
    operating: number;            // Handbært fé frá rekstri
    investing: number;            // Fjárfestingarhreyfingar
    financing: number;            // Fjármögnunarhreyfingar
    net_change: number;           // Breyting á handbæru fé
  };

  // Ownership (from skatturinn page or PDF)
  ownership: Array<{
    name: string;
    kennitala?: string;           // If company owner
    birth_year_month?: string;    // If individual (privacy)
    percentage: number;
    type: "direct" | "indirect";
  }>;

  // Corporate Structure
  parent_company?: {
    name: string;
    kennitala: string;
    ownership_pct: number;
  };

  subsidiaries: Array<{
    name: string;
    kennitala: string;
    ownership_pct: number;        // How much THIS company owns
    book_value?: number;          // Bókfært virði
    equity_method: boolean;       // Hlutdeildaraðferð (20-50% ownership)
  }>;

  associates: Array<{             // Hlutdeildarfélög (20-50% ownership)
    name: string;
    kennitala: string;
    ownership_pct: number;
    book_value?: number;
  }>;

  // Key Metrics (calculated)
  metrics: {
    equity_ratio: number;         // Eiginfjárhlutfall
    current_ratio?: number;       // Veltufjárhlutfall
    debt_to_equity?: number;      // Skuldir/Eigið fé
    profit_margin?: number;       // Hagnaðarhlutfall
  };

  // Notable Events
  events: Array<{
    type: "acquisition" | "investment" | "dividend" | "restructuring" | "other";
    description: string;
    amount?: number;
  }>;

  // Data Quality
  extraction: {
    source_pdf: string;
    extracted_at: string;
    confidence: "high" | "medium" | "low";
    notes: string[];
  };
}
```

## Icelandic Financial Terms

| Icelandic | English | Schema Field |
|-----------|---------|--------------|
| Rekstrartekjur | Revenue | income.revenue |
| Rekstrargjöld | Operating expenses | income.operating_expenses |
| Afskriftir | Depreciation | income.depreciation |
| Fjármunatekjur | Financial income | income.financial_income |
| Fjármagnsgjöld | Financial expenses | income.financial_expenses |
| Tekjuskattur | Income tax | income.income_tax |
| Hagnaður ársins | Net profit | income.net_profit |
| Fastafjármunir | Fixed assets | balance.fixed_assets |
| Veltufjármunir | Current assets | balance.current_assets |
| Hlutafé | Share capital | balance.share_capital |
| Eigið fé | Equity | balance.total_equity |
| Langtímaskuldir | Long-term debt | balance.long_term_debt |
| Skammtímaskuldir | Short-term debt | balance.short_term_debt |
| Arðgreiðslur | Dividends | events (type: dividend) |
| Dótturfélög | Subsidiaries | subsidiaries[] |
| Hlutdeildarfélög | Associates (20-50%) | associates[] |
| Móðurfélag | Parent company | parent_company |
| Eignarhlutir í dótturfélögum | Shares in subsidiaries | subsidiaries[].book_value |
| Samstæða | Group/Consolidated | report_type: "consolidated" |

## CLI Usage

```bash
# Extract financials from a downloaded PDF
uv run python scripts/financials.py extract /path/to/report.pdf

# Full pipeline: download + extract for a company
uv run python scripts/financials.py company 5012043070 --year 2024

# Extract multiple years for comparison
uv run python scripts/financials.py company 5012043070 --years 2020-2024

# Output as JSON
uv run python scripts/financials.py company 5012043070 --year 2024 --format json

# Output as CSV (flattened)
uv run python scripts/financials.py company 5012043070 --year 2024 --format csv
```

## Docling Integration

### Setup

```bash
uv sync
# Docling downloads models on first run (~500MB)
```

### Basic Extraction

```python
from docling.document_converter import DocumentConverter

def extract_pdf(pdf_path: str) -> tuple[str, list[dict]]:
    """Extract markdown and tables from PDF."""
    converter = DocumentConverter()
    result = converter.convert(pdf_path)

    markdown = result.document.export_to_markdown()

    tables = []
    for table in result.document.tables:
        tables.append({
            "dataframe": table.export_to_dataframe().to_dict(),
        })

    return markdown, tables
```

### Table Detection

Docling's TableFormer model handles:
- Multi-row headers
- Merged cells
- Nested tables
- Currency formatting (ISK with dots: 1.234.567)

## Claude Interpretation

After Docling extracts the content, use Claude to interpret and standardize:

```python
EXTRACTION_PROMPT = '''
Extract structured financial data from this Icelandic annual report.

DOCUMENT:
{markdown}

TABLES:
{tables_json}

Return a JSON object matching this schema:
{schema}

Guidelines:
1. All amounts in ISK (Icelandic króna), no thousands separators
2. Negative values for expenses/losses (use actual signs from document)
3. Calculate metrics if raw data available
4. Note any unusual items in events[]
5. Set confidence based on data completeness
6. If "Hnappurinn" format, mark report_type accordingly

Return ONLY valid JSON, no markdown.
'''
```

## Report Types

### Hnappurinn (Micro-company)
- 4-page simplified format
- No detailed notes
- No ownership section in PDF
- Fields: revenue, expenses, profit, basic balance sheet

### Full Ársreikningur
- Complete financial statements
- Auditor's report
- Detailed notes
- Ownership/shareholder tables
- Cash flow statement

### Consolidated (Samstæðureikningur)
- Group financials
- Subsidiary breakdown
- Intercompany eliminations

## Data Quality Notes

1. **Currency**: All figures in ISK. Watch for thousands (þús.kr.) vs millions (m.kr.) notation.

2. **Fiscal Year**: Most companies use calendar year, but some differ. Check "Reikningsár" field.

3. **Comparatives**: Reports show current year + prior year. Extract both for trend analysis.

4. **Rounding**: Hnappurinn reports often round to thousands. Full reports may have exact figures.

5. **Negative Signs**: Expenses sometimes shown as positive numbers with context, sometimes with parentheses or minus signs.

## Integration with skatturinn

```python
from scripts.skatturinn import download_annual_report, get_company_info
from scripts.financials import extract_financials

async def get_company_financials(kennitala: str, year: int):
    """Full pipeline: fetch PDF, extract, standardize."""

    # Get company info (includes ownership from page)
    info = await get_company_info(kennitala)

    # Download the PDF
    pdf_path = await download_annual_report(kennitala, year)

    # Extract with Docling + Claude
    financials = extract_financials(pdf_path, info)

    return financials
```

## Evidence Integration

Store extracted financials in `/data/processed/financials/`:

```
/data/processed/financials/
  /{kennitala}/
    /2024.json          # Full extracted data
    /2023.json
    /summary.csv        # Multi-year comparison
```

SQL queries in `/evidence-reports/sources/financials/`:

```sql
-- company_trends.sql
SELECT
    fiscal_year,
    income_revenue,
    income_net_profit,
    balance_total_equity,
    metrics_equity_ratio
FROM read_json_auto('../data/processed/financials/5012043070/*.json')
ORDER BY fiscal_year
```

## Corporate Structure Mapping

### Data Sources

| Data | Source | Method |
|------|--------|--------|
| Parent company | skatturinn page | Beneficial owners with company kennitala |
| Subsidiaries | Annual report PDF | Notes section, "Eignarhlutir í dótturfélögum" |
| Associates | Annual report PDF | "Hlutdeildarfélög" section |
| Group structure | Recursive lookup | Follow kennitalas both directions |

### Deriving Parent Company

From skatturinn ownership scraping, if a beneficial owner has a company kennitala (starts with 4-7), that's a parent company:

```python
for owner in company.beneficial_owners:
    if owner.is_company:  # kennitala[0] in "4567"
        financials.parent_company = {
            "name": owner.name,
            "kennitala": owner.kennitala,
            "ownership_pct": owner.ownership_pct
        }
```

### Extracting Subsidiaries from PDF

Look for these patterns in annual report notes:

```
Eignarhlutir í dótturfélögum:
| Nafn | Kennitala | Eignarhlutur | Bókfært virði |
|------|-----------|--------------|---------------|
| ABC ehf. | 1234567890 | 100% | 50.000.000 |
```

Also check balance sheet line "Eignarhlutir í dóttur- og hlutdeildarfélögum" - if > 0, there are subsidiaries.

### Ownership Classifications

| Ownership % | Classification | Accounting |
|-------------|----------------|------------|
| >50% | Dótturfélag (Subsidiary) | Full consolidation |
| 20-50% | Hlutdeildarfélag (Associate) | Equity method |
| <20% | Fjárfesting (Investment) | Cost/fair value |

### Building Group Tree

```python
async def build_group_structure(root_kennitala: str) -> dict:
    """
    Build complete group structure:
    - Look UP: find parent companies
    - Look DOWN: find subsidiaries
    """
    company = await get_company_financials(root_kennitala)

    structure = {
        "company": company,
        "parents": [],
        "subsidiaries": []
    }

    # Look UP - parent from beneficial owners
    if company.parent_company:
        parent_structure = await build_group_structure(
            company.parent_company.kennitala
        )
        structure["parents"].append(parent_structure)

    # Look DOWN - subsidiaries from notes
    for sub in company.subsidiaries:
        sub_structure = await build_group_structure(sub.kennitala)
        structure["subsidiaries"].append(sub_structure)

    return structure
```

### CLI Commands

```bash
# Get company with parent/subsidiary info
uv run python scripts/financials.py company 5012043070 --include-structure

# Build full group tree
uv run python scripts/financials.py group 5012043070 --depth 3

# Find ultimate parent (top of chain)
uv run python scripts/financials.py ultimate-parent 5012043070
```

## Related Skills

- [skatturinn](./skatturinn.md) - PDF download and ownership scraping
- [sedlabanki](./sedlabanki.md) - Central Bank financial sector data
- [hagstofan](./hagstofan.md) - National economic statistics

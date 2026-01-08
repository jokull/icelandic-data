"""
Extract structured financial data from Icelandic annual reports (ársreikningar).

Uses Docling for PDF parsing and outputs standardized JSON for Claude interpretation.
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

import polars as pl

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "skatturinn"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed" / "financials"


@dataclass
class IncomeStatement:
    """Rekstraryfirlit - Income statement fields."""

    revenue: float | None = None  # Rekstrartekjur
    operating_expenses: float | None = None  # Rekstrargjöld
    ebitda: float | None = None  # Afkoma fyrir afskriftir
    depreciation: float | None = None  # Afskriftir
    ebit: float | None = None  # Afkoma fyrir fjármagnsliði
    financial_income: float | None = None  # Fjármunatekjur
    financial_expenses: float | None = None  # Fjármagnsgjöld
    profit_before_tax: float | None = None  # Afkoma fyrir skatt
    income_tax: float | None = None  # Tekjuskattur
    net_profit: float | None = None  # Hagnaður/Tap ársins


@dataclass
class BalanceSheet:
    """Efnahagsyfirlit - Balance sheet fields."""

    # Assets
    fixed_assets: float | None = None  # Fastafjármunir
    current_assets: float | None = None  # Veltufjármunir
    total_assets: float | None = None  # Eignir samtals

    # Equity & Liabilities
    share_capital: float | None = None  # Hlutafé
    retained_earnings: float | None = None  # Óráðstafað eigið fé
    total_equity: float | None = None  # Eigið fé samtals
    long_term_debt: float | None = None  # Langtímaskuldir
    short_term_debt: float | None = None  # Skammtímaskuldir
    total_liabilities: float | None = None  # Skuldir samtals


@dataclass
class CashFlow:
    """Sjóðstreymi - Cash flow statement fields."""

    operating: float | None = None  # Handbært fé frá rekstri
    investing: float | None = None  # Fjárfestingarhreyfingar
    financing: float | None = None  # Fjármögnunarhreyfingar
    net_change: float | None = None  # Breyting á handbæru fé


@dataclass
class Owner:
    """Beneficial owner or shareholder."""

    name: str
    kennitala: str | None = None
    birth_year_month: str | None = None
    percentage: float | None = None
    ownership_type: Literal["direct", "indirect"] = "direct"


@dataclass
class ParentCompany:
    """Parent company that owns this company."""

    name: str
    kennitala: str
    ownership_pct: float


@dataclass
class Subsidiary:
    """Company owned by this company (>50% ownership)."""

    name: str
    kennitala: str
    ownership_pct: float
    book_value: float | None = None  # Bókfært virði
    equity_method: bool = False  # True if 20-50% (hlutdeildarfélag)


@dataclass
class Associate:
    """Company with 20-50% ownership (hlutdeildarfélag)."""

    name: str
    kennitala: str
    ownership_pct: float
    book_value: float | None = None


@dataclass
class Event:
    """Notable event from the report."""

    event_type: Literal["acquisition", "investment", "dividend", "restructuring", "other"]
    description: str
    amount: float | None = None


@dataclass
class ExtractionMeta:
    """Metadata about the extraction process."""

    source_pdf: str
    extracted_at: str
    confidence: Literal["high", "medium", "low"] = "medium"
    notes: list[str] = field(default_factory=list)


@dataclass
class Metrics:
    """Calculated financial metrics."""

    equity_ratio: float | None = None  # Eiginfjárhlutfall
    current_ratio: float | None = None  # Veltufjárhlutfall
    debt_to_equity: float | None = None
    profit_margin: float | None = None


@dataclass
class CompanyFinancials:
    """Complete structured financial data for a company year."""

    # Identification
    company_name: str
    kennitala: str
    fiscal_year: int
    report_type: Literal["full", "hnappurinn", "consolidated"] = "hnappurinn"

    # Financial statements
    income: IncomeStatement = field(default_factory=IncomeStatement)
    balance: BalanceSheet = field(default_factory=BalanceSheet)
    cashflow: CashFlow | None = None

    # Ownership (who owns this company)
    ownership: list[Owner] = field(default_factory=list)

    # Corporate structure
    parent_company: ParentCompany | None = None
    subsidiaries: list[Subsidiary] = field(default_factory=list)
    associates: list[Associate] = field(default_factory=list)

    # Events
    events: list[Event] = field(default_factory=list)

    # Calculated metrics
    metrics: Metrics = field(default_factory=Metrics)

    # Extraction metadata
    extraction: ExtractionMeta = field(
        default_factory=lambda: ExtractionMeta(
            source_pdf="", extracted_at=datetime.now().isoformat()
        )
    )

    def calculate_metrics(self):
        """Calculate derived metrics from raw data."""
        # Equity ratio = Equity / Total Assets
        if self.balance.total_equity and self.balance.total_assets:
            self.metrics.equity_ratio = round(
                self.balance.total_equity / self.balance.total_assets * 100, 1
            )

        # Debt to equity
        if self.balance.total_liabilities and self.balance.total_equity:
            self.metrics.debt_to_equity = round(
                self.balance.total_liabilities / self.balance.total_equity, 2
            )

        # Profit margin
        if self.income.net_profit and self.income.revenue:
            self.metrics.profit_margin = round(
                self.income.net_profit / self.income.revenue * 100, 1
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def parse_icelandic_number(text: str) -> float | None:
    """
    Parse Icelandic number format to float.

    Icelandic uses:
    - Dots as thousands separators: 1.234.567
    - Commas as decimal separators: 1.234,56
    - Parentheses for negative: (1.234)
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    # Check for negative in parentheses
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    # Also check for minus sign
    if text.startswith("-"):
        negative = True
        text = text[1:]

    # Remove thousands separators (dots) but keep decimal comma
    # First, replace comma with placeholder
    text = text.replace(",", "DECIMAL")
    # Remove dots (thousands separators)
    text = text.replace(".", "")
    # Replace decimal placeholder with dot
    text = text.replace("DECIMAL", ".")

    # Remove any remaining non-numeric characters except dot and minus
    text = re.sub(r"[^\d.]", "", text)

    try:
        value = float(text)
        return -value if negative else value
    except ValueError:
        return None


def extract_with_docling(pdf_path: Path) -> tuple[str, list[dict]]:
    """
    Extract markdown and tables from PDF using Docling.

    Returns:
        Tuple of (markdown_content, list_of_tables)
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        print("Docling not installed. Run: uv sync")
        sys.exit(1)

    print(f"  Extracting with Docling: {pdf_path}")
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))

    # Get markdown representation
    markdown = result.document.export_to_markdown()

    # Extract tables as dictionaries
    tables = []
    for i, table in enumerate(result.document.tables):
        try:
            df = table.export_to_dataframe()
            tables.append({
                "index": i,
                "rows": len(df),
                "columns": list(df.columns),
                "data": df.to_dict(orient="records"),
            })
        except Exception as e:
            print(f"  Warning: Could not extract table {i}: {e}")

    print(f"  Extracted {len(tables)} tables, {len(markdown)} chars of text")
    return markdown, tables


def extract_basic_info(markdown: str, pdf_path: Path) -> CompanyFinancials:
    """
    Extract basic company info and financial data from markdown.

    This is a heuristic-based extraction. For best results, feed the
    markdown to Claude for interpretation.
    """
    financials = CompanyFinancials(
        company_name="Unknown",
        kennitala="",
        fiscal_year=0,
        extraction=ExtractionMeta(
            source_pdf=str(pdf_path),
            extracted_at=datetime.now().isoformat(),
        ),
    )

    # Try to extract kennitala from filename
    kt_match = re.search(r"(\d{10})", pdf_path.stem)
    if kt_match:
        financials.kennitala = kt_match.group(1)

    # Try to extract year from filename
    year_match = re.search(r"_(\d{4})", pdf_path.stem)
    if year_match:
        financials.fiscal_year = int(year_match.group(1))

    # Look for company name in first lines
    lines = markdown.split("\n")
    for line in lines[:20]:
        line = line.strip()
        # Skip headers and empty lines
        if line.startswith("#") or not line:
            continue
        # Look for "ehf." or "hf." in line
        if "ehf" in line.lower() or " hf" in line.lower():
            # Clean up the name
            name = re.sub(r"\s*\(?\d{6}-?\d{4}\)?", "", line)  # Remove kennitala
            name = re.sub(r"^#+\s*", "", name)  # Remove markdown headers
            financials.company_name = name.strip()
            break

    # Determine report type
    if "Hnappurinn" in markdown or "örfélaga" in markdown.lower():
        financials.report_type = "hnappurinn"
    elif "samstæð" in markdown.lower():
        financials.report_type = "consolidated"
    else:
        financials.report_type = "full"

    # Extract financial figures using patterns
    # Revenue patterns
    revenue_patterns = [
        r"Rekstrartekjur\s+([\d.,()]+)",
        r"Tekjur\s+([\d.,()]+)",
    ]
    for pattern in revenue_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            financials.income.revenue = parse_icelandic_number(match.group(1))
            break

    # Operating expenses
    expense_patterns = [
        r"Rekstrargjöld\s+\(?\s*([\d.,]+)\s*\)?",
    ]
    for pattern in expense_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            val = parse_icelandic_number(match.group(1))
            if val:
                financials.income.operating_expenses = -abs(val)  # Expenses are negative
            break

    # Net profit
    profit_patterns = [
        r"Hagnaður.*?ársins\s+([\d.,()]+)",
        r"Tap.*?ársins\s+\(?([\d.,]+)\)?",
    ]
    for pattern in profit_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            val = parse_icelandic_number(match.group(1))
            if "Tap" in pattern and val:
                val = -abs(val)
            financials.income.net_profit = val
            break

    # Total assets
    asset_patterns = [
        r"Eignir samtals\s+([\d.,()]+)",
    ]
    for pattern in asset_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            financials.balance.total_assets = parse_icelandic_number(match.group(1))
            break

    # Total equity
    equity_patterns = [
        r"Eigið fé samtals\s+([\d.,()]+)",
    ]
    for pattern in equity_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            financials.balance.total_equity = parse_icelandic_number(match.group(1))
            break

    # Calculate metrics
    financials.calculate_metrics()

    # Assess confidence
    filled_fields = sum([
        financials.income.revenue is not None,
        financials.income.net_profit is not None,
        financials.balance.total_assets is not None,
        financials.balance.total_equity is not None,
    ])
    if filled_fields >= 4:
        financials.extraction.confidence = "high"
    elif filled_fields >= 2:
        financials.extraction.confidence = "medium"
    else:
        financials.extraction.confidence = "low"
        financials.extraction.notes.append(
            "Low extraction confidence - consider Claude interpretation"
        )

    return financials


def generate_claude_prompt(markdown: str, tables: list[dict], schema: str) -> str:
    """Generate a prompt for Claude to interpret the extracted content."""
    tables_json = json.dumps(tables, indent=2, ensure_ascii=False)

    return f'''Extract structured financial data from this Icelandic annual report (ársreikningur).

## Document Content (Markdown)

{markdown}

## Extracted Tables (JSON)

{tables_json}

## Output Schema

Return a JSON object with this structure:
{schema}

## Guidelines

1. All amounts in ISK (Icelandic króna) as integers, no thousands separators
2. Use negative values for expenses, losses, and outflows
3. Parse Icelandic number format: dots are thousands separators, commas are decimals
4. If report is "Hnappurinn" (micro-company), mark report_type accordingly
5. Calculate metrics where possible (equity_ratio, profit_margin, etc.)
6. Include any notable events (dividends, acquisitions, investments)
7. Set confidence based on data completeness

Common Icelandic terms:
- Rekstrartekjur = Revenue
- Rekstrargjöld = Operating expenses
- Afskriftir = Depreciation
- Hagnaður = Profit, Tap = Loss
- Eigið fé = Equity
- Skuldir = Liabilities

Return ONLY valid JSON, no markdown code blocks.'''


def extract_command(pdf_path: str, output_format: str = "json") -> None:
    """Extract financials from a PDF file."""
    path = Path(pdf_path)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    # Extract with Docling
    markdown, tables = extract_with_docling(path)

    # Basic heuristic extraction
    financials = extract_basic_info(markdown, path)

    if output_format == "json":
        print(financials.to_json())
    elif output_format == "markdown":
        # Output markdown for Claude interpretation
        print(markdown)
    elif output_format == "prompt":
        # Generate Claude prompt
        schema = json.dumps(asdict(CompanyFinancials(
            company_name="", kennitala="", fiscal_year=0
        )), indent=2)
        print(generate_claude_prompt(markdown, tables, schema))
    elif output_format == "tables":
        # Just output tables
        print(json.dumps(tables, indent=2, ensure_ascii=False))
    else:
        # Summary
        print(f"Company: {financials.company_name}")
        print(f"Kennitala: {financials.kennitala}")
        print(f"Fiscal Year: {financials.fiscal_year}")
        print(f"Report Type: {financials.report_type}")
        print()
        print("Income Statement:")
        print(f"  Revenue: {financials.income.revenue:,.0f}" if financials.income.revenue else "  Revenue: -")
        print(f"  Net Profit: {financials.income.net_profit:,.0f}" if financials.income.net_profit else "  Net Profit: -")
        print()
        print("Balance Sheet:")
        print(f"  Total Assets: {financials.balance.total_assets:,.0f}" if financials.balance.total_assets else "  Total Assets: -")
        print(f"  Total Equity: {financials.balance.total_equity:,.0f}" if financials.balance.total_equity else "  Total Equity: -")
        print()
        print("Metrics:")
        print(f"  Equity Ratio: {financials.metrics.equity_ratio}%" if financials.metrics.equity_ratio else "  Equity Ratio: -")
        print()
        print(f"Confidence: {financials.extraction.confidence}")
        for note in financials.extraction.notes:
            print(f"  Note: {note}")


async def company_command(kennitala: str, year: int | None, output_format: str) -> None:
    """Full pipeline: download PDF from skatturinn and extract."""
    # Import skatturinn functions
    try:
        from scripts.skatturinn import get_company_info, download_annual_report
        from playwright.async_api import async_playwright
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure skatturinn.py and playwright are available")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Get company info
        print(f"Fetching company info for {kennitala}...")
        company = await get_company_info(page, kennitala)

        if not company:
            print(f"Company {kennitala} not found")
            await browser.close()
            return

        print(f"Company: {company.name}")

        # Determine which year to download
        if year:
            target_year = year
        elif company.available_reports:
            target_year = max(r.year for r in company.available_reports)
            print(f"Using latest available year: {target_year}")
        else:
            print("No reports available")
            await browser.close()
            return

        # Download PDF
        print(f"Downloading report for {target_year}...")
        pdf_path = await download_annual_report(page, kennitala, target_year, RAW_DIR)

        await browser.close()

        if not pdf_path:
            print("Download failed")
            return

    # Extract financials
    print("Extracting financials...")
    markdown, tables = extract_with_docling(pdf_path)
    financials = extract_basic_info(markdown, pdf_path)

    # Add ownership from page scraping
    for owner in company.beneficial_owners:
        financials.ownership.append(Owner(
            name=owner.name,
            kennitala=owner.kennitala if owner.is_company else None,
            birth_year_month=owner.kennitala if not owner.is_company else None,
            percentage=owner.ownership_pct,
        ))

        # If owner is a company, set as parent company
        if owner.is_company and owner.ownership_pct and owner.ownership_pct > 50:
            financials.parent_company = ParentCompany(
                name=owner.name,
                kennitala=owner.kennitala,
                ownership_pct=owner.ownership_pct,
            )

    # Check for subsidiaries indicator in balance sheet
    # Look for "Eignarhlutir í dóttur" pattern in markdown
    if "dóttur" in markdown.lower() or "hlutdeildar" in markdown.lower():
        financials.extraction.notes.append(
            "May have subsidiaries/associates - check PDF notes section"
        )

    # Save to processed directory
    output_dir = PROCESSED_DIR / kennitala
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{target_year}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(financials.to_json())

    print(f"Saved to {output_file}")

    # Output based on format
    if output_format == "json":
        print(financials.to_json())
    elif output_format == "summary":
        extract_command(str(pdf_path), "summary")


async def group_command(kennitala: str, depth: int = 3) -> None:
    """Build corporate group structure by following ownership chains."""
    try:
        from scripts.skatturinn import get_company_info
        from playwright.async_api import async_playwright
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)

    visited = set()

    async def build_structure(kt: str, current_depth: int, direction: str = "both") -> dict:
        """Recursively build group structure."""
        if kt in visited or current_depth <= 0:
            return {"kennitala": kt, "truncated": True}

        visited.add(kt)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            company = await get_company_info(page, kt)
            await browser.close()

            if not company:
                return {"kennitala": kt, "not_found": True}

        node = {
            "kennitala": kt,
            "name": company.name,
            "owners": [],
            "subsidiaries": [],
        }

        # Look UP - find parent companies
        if direction in ("both", "up"):
            for owner in company.beneficial_owners:
                if owner.is_company:
                    parent_node = await build_structure(
                        owner.kennitala, current_depth - 1, "up"
                    )
                    parent_node["ownership_pct"] = owner.ownership_pct
                    node["owners"].append(parent_node)

        # Note: Looking DOWN (subsidiaries) requires PDF parsing
        # which is expensive. For now, just note if there might be subsidiaries.

        return node

    print(f"Building group structure for {kennitala} (depth={depth})...")
    structure = await build_structure(kennitala, depth)

    # Save result
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / f"group_{kennitala}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)

    print(f"\nGroup structure saved to {output_path}")
    print(json.dumps(structure, ensure_ascii=False, indent=2))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract structured financial data from Icelandic annual reports"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # extract command
    extract_parser = subparsers.add_parser("extract", help="Extract from local PDF")
    extract_parser.add_argument("pdf_path", help="Path to PDF file")
    extract_parser.add_argument(
        "--format",
        choices=["json", "summary", "markdown", "prompt", "tables"],
        default="summary",
        help="Output format",
    )

    # company command
    company_parser = subparsers.add_parser(
        "company", help="Full pipeline: download + extract"
    )
    company_parser.add_argument("kennitala", help="Company kennitala")
    company_parser.add_argument("--year", type=int, help="Fiscal year (default: latest)")
    company_parser.add_argument(
        "--format",
        choices=["json", "summary"],
        default="summary",
        help="Output format",
    )

    # group command
    group_parser = subparsers.add_parser(
        "group", help="Build corporate group structure"
    )
    group_parser.add_argument("kennitala", help="Starting company kennitala")
    group_parser.add_argument("--depth", type=int, default=3, help="Max recursion depth")

    # schema command - output the JSON schema
    subparsers.add_parser("schema", help="Output the JSON schema")

    args = parser.parse_args()

    if args.command == "extract":
        extract_command(args.pdf_path, args.format)
    elif args.command == "company":
        asyncio.run(company_command(args.kennitala, args.year, args.format))
    elif args.command == "group":
        asyncio.run(group_command(args.kennitala, args.depth))
    elif args.command == "schema":
        schema = asdict(CompanyFinancials(
            company_name="Example Company ehf.",
            kennitala="1234567890",
            fiscal_year=2024,
        ))
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

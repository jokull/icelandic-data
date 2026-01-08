"""
Download annual reports (ársreikningar) from skatturinn.is and extract ownership data.

Uses Playwright for browser automation since there's no public API.
Maps ownership chains by following beneficial owner kennitalas recursively.
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from playwright.async_api import async_playwright, Page, Browser

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "skatturinn"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

# Request delay to avoid rate limiting
REQUEST_DELAY = 3.0

# Kennitala patterns
KT_PATTERN = re.compile(r"\b(\d{6}-?\d{4})\b")


@dataclass
class Owner:
    """Beneficial owner or shareholder."""

    name: str
    kennitala: str
    ownership_pct: float | None = None
    is_company: bool = False

    def __post_init__(self):
        # Clean kennitala (remove dash)
        self.kennitala = self.kennitala.replace("-", "")
        # Determine if company based on first digit (4-7 = company)
        if self.kennitala and len(self.kennitala) >= 1:
            self.is_company = self.kennitala[0] in "4567"


@dataclass
class AnnualReport:
    """Annual report metadata."""

    year: int
    report_number: str
    submission_date: str
    report_type: str = ""


@dataclass
class Company:
    """Company information from skatturinn.is."""

    kennitala: str
    name: str
    address: str = ""
    legal_form: str = ""
    registration_date: str = ""
    beneficial_owners: list[Owner] = field(default_factory=list)
    available_reports: list[AnnualReport] = field(default_factory=list)


async def get_company_info(page: Page, kennitala: str) -> Company | None:
    """
    Scrape company info from skatturinn.is company lookup page.

    Args:
        page: Playwright page object
        kennitala: Company kennitala (10 digits, no dash)

    Returns:
        Company object or None if not found
    """
    url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
    print(f"  Fetching {url}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"  Error loading page: {e}")
        return None

    # Check if company exists
    content = await page.content()
    if "Ekkert fyrirtæki fannst" in content or "ekki til" in content.lower():
        print(f"  Company {kennitala} not found")
        return None

    # Extract company name from h1
    try:
        name_el = await page.query_selector("h1")
        name = await name_el.inner_text() if name_el else "Unknown"
        name = name.strip()
    except Exception:
        name = "Unknown"

    company = Company(kennitala=kennitala, name=name)

    # Extract beneficial owners from .collapsebox elements
    # Structure: .collapsebox > span > h4 (name), then .annualTable with ownership %
    try:
        owner_boxes = await page.query_selector_all(".collapsebox")
        for box in owner_boxes:
            # Get owner name from h4
            name_el = await box.query_selector("h4")
            if not name_el:
                continue
            owner_name = (await name_el.inner_text()).strip()

            # Get ownership details from .annualTable
            table = await box.query_selector(".annualTable")
            if not table:
                continue

            # Check if this is an ownership table (has "Eignarhlutur" column)
            table_text = await table.inner_text()
            if "Eignarhlutur" not in table_text and "%" not in table_text:
                continue

            # Extract from table rows
            rows = await table.query_selector_all("tbody tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 4:
                    # Column order: Fæðingarár/mán, Búsetuland, Ríkisfang, Eignarhlutur, Tegund
                    birth_info = (await cells[0].inner_text()).strip()
                    pct_text = (await cells[3].inner_text()).strip()

                    # Parse percentage
                    pct = None
                    pct_match = re.search(r"(\d+(?:[,\.]\d+)?)\s*%?", pct_text)
                    if pct_match:
                        pct = float(pct_match.group(1).replace(",", "."))

                    # For individuals, we get birth year/month, not kennitala
                    # We'll store birth_info as a pseudo-identifier
                    # Note: Real kennitala not shown on page for privacy
                    company.beneficial_owners.append(
                        Owner(
                            name=owner_name,
                            kennitala=birth_info.replace(" ", ""),  # e.g., "1964-JÚNÍ"
                            ownership_pct=pct,
                        )
                    )
    except Exception as e:
        print(f"  Warning: Could not extract owners: {e}")

    # Extract available annual reports from "Gögn úr ársreikningaskrá" section
    try:
        # Find the annual reports table
        tables = await page.query_selector_all("table")
        for table in tables:
            header = await table.query_selector("th")
            if header:
                header_text = await header.inner_text()
                if "Rek. ár" in header_text or "ársreikn" in header_text.lower():
                    rows = await table.query_selector_all("tr")
                    for row in rows[1:]:  # Skip header
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 4:
                            year_text = await cells[0].inner_text()
                            # Name in cells[1]
                            date_text = await cells[2].inner_text()
                            report_num = await cells[3].inner_text()

                            try:
                                year = int(year_text.strip())
                                company.available_reports.append(
                                    AnnualReport(
                                        year=year,
                                        report_number=report_num.strip(),
                                        submission_date=date_text.strip(),
                                    )
                                )
                            except ValueError:
                                continue
                    break
    except Exception as e:
        print(f"  Warning: Could not extract reports list: {e}")

    return company


async def download_annual_report(
    page: Page, kennitala: str, year: int, output_dir: Path
) -> Path | None:
    """
    Download annual report PDF using the shopping cart mechanism.

    Flow:
    1. Find td[data-itemid] for the target year
    2. Click .tocart link (adds to cart via /da/CartService/addToCart)
    3. Navigate to cart page at vefur.rsk.is
    4. Click "Áfram" to proceed
    5. Click download button to get PDF

    Args:
        page: Playwright page object
        kennitala: Company kennitala
        year: Operating year to download
        output_dir: Directory to save PDF

    Returns:
        Path to downloaded PDF or None if failed
    """
    url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
    print(f"  Navigating to {url} for year {year}")

    await page.goto(url, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(1)  # Let JS initialize

    try:
        # Find the row for target year and get itemid
        # Reports are in table with td[data-itemid] containing .tocart link
        # Prefer PDF types (1, 2) over electronic (4, 5, 6) which require email
        item_id = None
        type_id = None
        report_cells = await page.query_selector_all("td[data-itemid]")

        # Collect all reports for target year
        year_reports = []
        for cell in report_cells:
            row = await cell.evaluate_handle("el => el.closest('tr')")
            row_text = await row.evaluate("el => el.textContent")

            if str(year) in row_text:
                cell_item_id = await cell.get_attribute("data-itemid")
                cell_type_id = await cell.get_attribute("data-typeid") or "1"
                year_reports.append((cell_item_id, cell_type_id))

        # Prefer PDF types (1, 2) over electronic (4, 5, 6)
        pdf_types = ["1", "2"]
        for item, typ in year_reports:
            if typ in pdf_types:
                item_id = item
                type_id = typ
                break

        # Fallback to first available if no PDF type found
        if not item_id and year_reports:
            item_id, type_id = year_reports[0]

        if not item_id:
            print(f"  Could not find report for year {year}")
            return None

        print(f"  Found report itemid={item_id}")

        # Add to cart - use the API directly (more reliable than clicking hidden link)
        add_cart_url = f"/da/CartService/addToCart?itemid={item_id}&typeid={type_id}"
        print(f"  Adding to cart: {add_cart_url}")

        response = await page.evaluate(f'''
            async () => {{
                const resp = await fetch("{add_cart_url}", {{
                    headers: {{ "X-Requested-With": "XMLHttpRequest" }}
                }});
                return await resp.json();
            }}
        ''')
        print(f"  Cart response: {response}")

        if not response or not response.get("addCartItemResult"):
            print("  Failed to add to cart")
            return None

        # Get the shopping cart URL from the response
        cart_page_url = response.get("shoppingCartUrl")
        if not cart_page_url:
            print("  No cart URL in response")
            return None

        # Ensure HTTPS
        cart_page_url = cart_page_url.replace("http://", "https://")
        print(f"  Navigating to cart: {cart_page_url}")

        await page.goto(cart_page_url, wait_until="networkidle")
        await asyncio.sleep(2)

        # Click "Áfram" button to proceed to download page
        afram_btn = await page.query_selector('input[value="Áfram"], button:has-text("Áfram"), a:has-text("Áfram")')
        if afram_btn:
            await afram_btn.click()
            await asyncio.sleep(2)

        # Now we should be on the download page
        # Set up download handler and click the download button
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{kennitala}_{year}.pdf"

        # Check if this is an electronic report requiring email
        email_field = await page.query_selector('input[name*="netfang" i], input[id*="netfang" i], input[type="email"]')
        page_content = await page.content()

        if email_field or "Skráning netfangs" in page_content:
            # Electronic report flow - requires email registration
            print(f"  Electronic report (typeid={type_id}) - requires email registration")
            print("  Note: Electronic reports are sent via email and cannot be downloaded directly.")
            print("  Try an older year with typeid=1 (PDF format) or manually request via skatturinn.is")
            await page.screenshot(path=output_dir / f"debug_{kennitala}_{year}.png")
            return None

        # Find download button - it's an input with class "download-button" or similar
        download_btn = await page.query_selector(
            'input.download-button, input[value="Sækja"], .btn.download-button, '
            'input[name*="Saekja"], input[id*="Saekja"]'
        )

        if not download_btn:
            # Try "Sækja öll skjöl" button
            download_btn = await page.query_selector('input[value*="Sækja öll"]')

        if not download_btn:
            print("  Could not find download button on cart page")
            # Take screenshot for debugging
            await page.screenshot(path=output_dir / f"debug_{kennitala}_{year}.png")
            return None

        async with page.expect_download(timeout=60000) as download_info:
            await download_btn.click()

        download = await download_info.value
        await download.save_as(output_path)

        print(f"  Downloaded to {output_path}")
        return output_path

    except Exception as e:
        print(f"  Download failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def extract_owners_from_pdf(pdf_path: Path) -> list[Owner]:
    """
    Extract ownership information from annual report PDF.

    Looks for sections containing:
    - "Raunverulegir eigendur" (Beneficial owners)
    - "Hluthafar" (Shareholders)
    - "Eigendur" (Owners)

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of Owner objects
    """
    owners = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                text_lower = text.lower()

                # Check if this page contains ownership info
                if not any(
                    kw in text_lower for kw in ["eigend", "hluthaf", "eignarhald"]
                ):
                    continue

                # Try to extract tables
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue

                    for row in table:
                        if not row or len(row) < 2:
                            continue

                        # Look for kennitala in any cell
                        row_text = " ".join(str(cell) for cell in row if cell)
                        kt_matches = KT_PATTERN.findall(row_text)

                        for kt in kt_matches:
                            # Try to find name (usually first column)
                            name = str(row[0]) if row[0] else "Unknown"

                            # Try to find percentage
                            pct = None
                            for cell in row:
                                if cell:
                                    pct_match = re.search(
                                        r"(\d+(?:[,\.]\d+)?)\s*%", str(cell)
                                    )
                                    if pct_match:
                                        pct = float(
                                            pct_match.group(1).replace(",", ".")
                                        )
                                        break

                            owners.append(
                                Owner(name=name.strip(), kennitala=kt, ownership_pct=pct)
                            )

                # Also try regex on plain text for less structured PDFs
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    kt_matches = KT_PATTERN.findall(line)
                    for kt in kt_matches:
                        # Check if we already have this kennitala
                        if any(o.kennitala.replace("-", "") == kt.replace("-", "") for o in owners):
                            continue

                        # Try to get name from same line or previous line
                        name = "Unknown"
                        # Look for name pattern before kennitala
                        name_match = re.search(r"([A-ZÁÉÍÓÚÝÞÆÖa-záéíóúýþæö\s]+)\s+" + kt, line)
                        if name_match:
                            name = name_match.group(1).strip()
                        elif i > 0:
                            # Try previous line
                            prev = lines[i - 1].strip()
                            if prev and not KT_PATTERN.search(prev):
                                name = prev

                        # Look for percentage
                        pct = None
                        pct_match = re.search(r"(\d+(?:[,\.]\d+)?)\s*%", line)
                        if pct_match:
                            pct = float(pct_match.group(1).replace(",", "."))

                        owners.append(Owner(name=name, kennitala=kt, ownership_pct=pct))

    except Exception as e:
        print(f"  Error extracting from PDF: {e}")

    # Deduplicate by kennitala
    seen = set()
    unique_owners = []
    for owner in owners:
        kt_clean = owner.kennitala.replace("-", "")
        if kt_clean not in seen:
            seen.add(kt_clean)
            unique_owners.append(owner)

    return unique_owners


async def map_ownership_chain(
    browser: Browser,
    root_kennitala: str,
    max_depth: int = 5,
    visited: set[str] | None = None,
    download_pdfs: bool = False,
) -> dict:
    """
    Recursively map ownership chain starting from a company.

    Args:
        browser: Playwright browser instance
        root_kennitala: Starting company kennitala
        max_depth: Maximum recursion depth
        visited: Set of already-visited kennitalas (to avoid cycles)
        download_pdfs: Whether to download PDFs for each company

    Returns:
        Nested dict structure representing ownership chain
    """
    if visited is None:
        visited = set()

    kt_clean = root_kennitala.replace("-", "")

    if kt_clean in visited:
        return {"kennitala": kt_clean, "circular_reference": True}

    if max_depth <= 0:
        return {"kennitala": kt_clean, "max_depth_reached": True}

    visited.add(kt_clean)

    # Create new page for this lookup
    page = await browser.new_page()

    try:
        company = await get_company_info(page, kt_clean)

        if company is None:
            return {"kennitala": kt_clean, "not_found": True}

        result = {
            "kennitala": kt_clean,
            "name": company.name,
            "owners": [],
        }

        # Optionally download latest annual report and extract more detailed ownership
        if download_pdfs and company.available_reports:
            latest = max(company.available_reports, key=lambda r: r.year)
            pdf_path = await download_annual_report(page, kt_clean, latest.year, RAW_DIR)
            if pdf_path:
                pdf_owners = extract_owners_from_pdf(pdf_path)
                # Merge with page owners, preferring PDF data
                for pdf_owner in pdf_owners:
                    existing = next(
                        (
                            o
                            for o in company.beneficial_owners
                            if o.kennitala == pdf_owner.kennitala
                        ),
                        None,
                    )
                    if existing:
                        # Update with PDF data
                        if pdf_owner.ownership_pct:
                            existing.ownership_pct = pdf_owner.ownership_pct
                    else:
                        company.beneficial_owners.append(pdf_owner)

        # Recurse into company owners
        for owner in company.beneficial_owners:
            owner_data = {
                "kennitala": owner.kennitala,
                "name": owner.name,
                "ownership_pct": owner.ownership_pct,
                "type": "company" if owner.is_company else "person",
            }

            if owner.is_company:
                # Recurse
                await asyncio.sleep(REQUEST_DELAY)  # Rate limiting
                child_chain = await map_ownership_chain(
                    browser, owner.kennitala, max_depth - 1, visited, download_pdfs
                )
                owner_data["owners"] = child_chain.get("owners", [])

            result["owners"].append(owner_data)

        return result

    finally:
        await page.close()


async def download_command(kennitala: str, year: int | None = None) -> None:
    """Download annual report(s) for a company."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        company = await get_company_info(page, kennitala)
        if company is None:
            print(f"Company {kennitala} not found")
            await browser.close()
            return

        print(f"Company: {company.name}")
        print(f"Available reports: {len(company.available_reports)}")

        if year:
            # Download specific year
            await download_annual_report(page, kennitala, year, RAW_DIR)
        else:
            # Download all available
            for report in company.available_reports:
                print(f"Downloading {report.year}...")
                await download_annual_report(page, kennitala, report.year, RAW_DIR)
                await asyncio.sleep(REQUEST_DELAY)

        await browser.close()


async def chain_command(kennitala: str, depth: int = 5, download: bool = False) -> None:
    """Map ownership chain for a company."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        print(f"Mapping ownership chain for {kennitala} (depth={depth})")
        chain = await map_ownership_chain(
            browser, kennitala, max_depth=depth, download_pdfs=download
        )

        await browser.close()

    # Save result
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / f"ownership_chain_{kennitala}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)

    print(f"\nOwnership chain saved to {output_path}")
    print(json.dumps(chain, ensure_ascii=False, indent=2))


async def info_command(kennitala: str) -> None:
    """Get company info without downloading."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        company = await get_company_info(page, kennitala)

        await browser.close()

    if company is None:
        print(f"Company {kennitala} not found")
        return

    print(f"Name: {company.name}")
    print(f"Kennitala: {company.kennitala}")
    print(f"\nBeneficial owners ({len(company.beneficial_owners)}):")
    for owner in company.beneficial_owners:
        pct = f"{owner.ownership_pct}%" if owner.ownership_pct else "?"
        type_str = "company" if owner.is_company else "person"
        print(f"  - {owner.name} ({owner.kennitala}) - {pct} [{type_str}]")

    print(f"\nAvailable reports ({len(company.available_reports)}):")
    for report in company.available_reports:
        print(f"  - {report.year}: #{report.report_number} ({report.submission_date})")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download annual reports and map ownership from skatturinn.is"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # info command
    info_parser = subparsers.add_parser("info", help="Get company info")
    info_parser.add_argument("kennitala", help="Company kennitala")

    # download command
    dl_parser = subparsers.add_parser("download", help="Download annual report PDFs")
    dl_parser.add_argument("kennitala", help="Company kennitala")
    dl_parser.add_argument("--year", type=int, help="Specific year (default: all)")

    # chain command
    chain_parser = subparsers.add_parser("chain", help="Map ownership chain")
    chain_parser.add_argument("kennitala", help="Company kennitala")
    chain_parser.add_argument("--depth", type=int, default=5, help="Max recursion depth")
    chain_parser.add_argument(
        "--download", action="store_true", help="Download PDFs for detailed ownership"
    )

    # extract command (for testing PDF extraction)
    extract_parser = subparsers.add_parser("extract", help="Extract owners from PDF")
    extract_parser.add_argument("pdf_path", help="Path to PDF file")

    args = parser.parse_args()

    if args.command == "info":
        asyncio.run(info_command(args.kennitala))
    elif args.command == "download":
        asyncio.run(download_command(args.kennitala, args.year))
    elif args.command == "chain":
        asyncio.run(chain_command(args.kennitala, args.depth, args.download))
    elif args.command == "extract":
        pdf_path = Path(args.pdf_path)
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            sys.exit(1)
        owners = extract_owners_from_pdf(pdf_path)
        print(f"Found {len(owners)} owners:")
        for owner in owners:
            pct = f"{owner.ownership_pct}%" if owner.ownership_pct else "?"
            print(f"  - {owner.name} ({owner.kennitala}) - {pct}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

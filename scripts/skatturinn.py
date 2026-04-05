"""
Download annual reports (ársreikningar) from skatturinn.is and extract ownership data.

Uses httpx for plain HTTP requests — no browser automation needed.
Maps ownership chains by following beneficial owner kennitalas recursively.
"""

import argparse
import asyncio
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pdfplumber

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "skatturinn"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

# Request delay to avoid rate limiting
REQUEST_DELAY = 3.0

# Kennitala patterns
KT_PATTERN = re.compile(r"\b(\d{6}-?\d{4})\b")

# Shared httpx client config
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
_HTTP_TIMEOUT = httpx.Timeout(60.0)


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


def _extract_hidden(html: str, name: str) -> str | None:
    """Extract value of a named hidden input from HTML."""
    esc = re.escape(name)
    m = re.search(rf'name="{esc}"[^>]*value="([^"]*)"', html, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(rf'value="([^"]*)"[^>]*name="{esc}"', html, re.IGNORECASE)
    return m.group(1) if m else None


def _strip_html(html: str) -> str:
    """Strip HTML tags, returning plain text."""
    return re.sub(r"<[^>]+>", "", html).strip()


async def get_company_info(kennitala: str) -> Company | None:
    """
    Scrape company info from skatturinn.is company lookup page using httpx.

    Args:
        kennitala: Company kennitala (10 digits, no dash)

    Returns:
        Company object or None if not found
    """
    print(f"  Searching for {kennitala}...")

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        headers=_HTTP_HEADERS,
        follow_redirects=True,
    ) as http:
        # Go directly to the company page by kennitala
        url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
        r = await http.get(url)
        r.raise_for_status()
        html = r.text

        # Check if not found
        if "engri niðurstöðu" in html or "Engin fyrirtæki fundust" in html:
            print(f"  Company {kennitala} not found")
            return None

        # Extract company name from h1 (format: "Name (kennitala)")
        name = "Unknown"
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        if h1_match:
            h1_text = _strip_html(h1_match.group(1))
            name = re.sub(r"\s*\(\d{6}-?\d{4}\)\s*$", "", h1_text).strip()
            if not name:
                name = "Unknown"

        print(f"  Found: {name}")
        company = Company(kennitala=kennitala, name=name)

        # Extract beneficial owners from .collapsebox elements
        # Each collapsebox has an h4 with the owner name and a table with ownership details
        try:
            # Find all collapsebox sections
            collapsebox_pattern = re.compile(
                r'<div[^>]*class="[^"]*collapsebox[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>',
                re.IGNORECASE,
            )
            # More robust: find sections between collapsebox markers
            # The HTML structure has .collapsebox containing h4 + table
            owner_sections = re.findall(
                r'<div[^>]*class="[^"]*collapsebox[^"]*"[^>]*>([\s\S]*?)(?=<div[^>]*class="[^"]*collapsebox|$)',
                html,
                re.IGNORECASE,
            )

            for section in owner_sections:
                # Get owner name from h4
                h4_match = re.search(r"<h4[^>]*>(.*?)</h4>", section, re.DOTALL)
                if not h4_match:
                    continue
                owner_name = _strip_html(h4_match.group(1)).strip()

                # Check if this section has ownership data
                if "Eignarhlutur" not in section and "%" not in section:
                    continue

                # Extract table rows
                rows = re.findall(
                    r"<tr[^>]*>([\s\S]*?)</tr>", section, re.IGNORECASE
                )
                for row_html in rows:
                    cells = re.findall(
                        r"<td[^>]*>([\s\S]*?)</td>", row_html, re.IGNORECASE
                    )
                    if len(cells) >= 4:
                        birth_info = _strip_html(cells[0]).strip()
                        pct_text = _strip_html(cells[3]).strip()

                        # Parse percentage
                        pct = None
                        pct_match = re.search(r"(\d+(?:[,\.]\d+)?)\s*%?", pct_text)
                        if pct_match:
                            pct = float(pct_match.group(1).replace(",", "."))

                        company.beneficial_owners.append(
                            Owner(
                                name=owner_name,
                                kennitala=birth_info.replace(" ", ""),
                                ownership_pct=pct,
                            )
                        )
        except Exception as e:
            print(f"  Warning: Could not extract owners: {e}")

        # Extract available annual reports from table rows with data-itemid
        try:
            # Find all table rows that have data-itemid (these are report rows)
            for row_match in re.finditer(
                r"<tr[^>]*>([\s\S]*?)</tr>", html, re.IGNORECASE
            ):
                row_html = row_match.group(1)
                # Check if this row has data-itemid (report download cell)
                if "data-itemid" not in row_html:
                    continue

                # Extract cells
                cells = re.findall(
                    r"<td[^>]*>([\s\S]*?)</td>", row_html, re.IGNORECASE
                )
                if len(cells) >= 4:
                    year_text = _strip_html(cells[0]).strip()
                    # cells[1] is typically company name
                    date_text = _strip_html(cells[2]).strip()
                    report_num = _strip_html(cells[3]).strip()

                    try:
                        year_val = int(year_text)
                        company.available_reports.append(
                            AnnualReport(
                                year=year_val,
                                report_number=report_num,
                                submission_date=date_text,
                            )
                        )
                    except ValueError:
                        continue

            # Fallback: try parsing from text between known markers
            if not company.available_reports:
                # Look for tab-separated text blocks with year patterns
                text = _strip_html(html)
                lines = text.split("\n")
                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 4 and parts[0].strip().isdigit():
                        year_text = parts[0].strip()
                        date_text = parts[2].strip() if len(parts) > 2 else ""
                        report_num = parts[3].strip() if len(parts) > 3 else ""
                        try:
                            year_val = int(year_text)
                            if 1990 <= year_val <= 2030:
                                company.available_reports.append(
                                    AnnualReport(
                                        year=year_val,
                                        report_number=report_num,
                                        submission_date=date_text,
                                    )
                                )
                        except ValueError:
                            continue
        except Exception as e:
            print(f"  Warning: Could not extract reports list: {e}")

    return company


async def download_annual_report(
    kennitala: str, year: int, output_dir: Path
) -> Path | None:
    """
    Download annual report PDF from skatturinn.is using plain HTTP.

    Flow:
      1. GET company page -> find td[data-itemid] for target year
      2. GET addToCart -> get cart kid
      3. GET cart page -> extract ASP.NET viewstate
      4. POST Afram (with hfKaupaMouseClicked=true) -> payment form fields
      5. POST ReturnPage.aspx with payment fields -> download page
      6. POST ReturnPage.aspx with Saekja oll -> ZIP containing PDF
      7. Extract PDF from ZIP to disk

    Args:
        kennitala: Company kennitala
        year: Operating year to download
        output_dir: Directory to save PDF

    Returns:
        Path to downloaded PDF or None if failed
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{kennitala}_{year}.pdf"

    print(f"  Downloading report for {kennitala} year {year}")

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        headers=_HTTP_HEADERS,
        follow_redirects=True,
    ) as http:
        cookies: dict[str, str] = {}

        try:
            # Step 1: GET company page, find report items for target year
            company_url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
            r1 = await http.get(company_url)
            r1.raise_for_status()
            cookies.update(dict(r1.cookies))
            html1 = r1.text

            # Find td[data-itemid] rows matching the target year
            year_items: list[tuple[str, str]] = []  # (itemId, typeId)
            for row_match in re.finditer(
                r"<tr[^>]*>([\s\S]*?)</tr>", html1, re.IGNORECASE
            ):
                row_html = row_match.group(1)
                row_text = re.sub(r"<[^>]+>", " ", row_html)
                if str(year) not in row_text:
                    continue
                item_match = re.search(
                    r'data-itemid="(\d+)"[^>]*data-typeid="(\d+)"', row_html
                )
                if item_match:
                    year_items.append((item_match.group(1), item_match.group(2)))

            if not year_items:
                print(f"  Could not find report for year {year}")
                return None

            # Prefer typeId 1 or 2 (PDF), warn about 4-7 (electronic/email-only)
            chosen_item, chosen_type = year_items[0]
            for item_id, type_id in year_items:
                if type_id in ("1", "2"):
                    chosen_item, chosen_type = item_id, type_id
                    break

            if chosen_type in ("4", "5", "6", "7"):
                print(
                    f"  Warning: Only electronic report available (typeId={chosen_type}). "
                    "These are sent via email and may not download as PDF. Attempting anyway..."
                )

            print(f"  Found report: itemId={chosen_item} typeId={chosen_type}")

            # Step 2: Add to cart
            cart_url = f"https://www.skatturinn.is/da/CartService/addToCart?itemid={chosen_item}&typeid={chosen_type}"
            r2 = await http.get(
                cart_url,
                headers={"X-Requested-With": "XMLHttpRequest"},
                cookies=cookies,
            )
            r2.raise_for_status()
            cookies.update(dict(r2.cookies))
            cart_json = r2.json()

            if not cart_json.get("addCartItemResult"):
                print(f"  Failed to add to cart: {cart_json}")
                return None

            cart_page_url = cart_json["shoppingCartUrl"].replace(
                "http://", "https://"
            )
            kid = cart_page_url.split("kid=")[1]
            print(f"  Added to cart: kid={kid}")

            # Step 3: GET cart page, extract viewstate
            r3 = await http.get(cart_page_url, cookies=cookies)
            r3.raise_for_status()
            cookies.update(dict(r3.cookies))
            html3 = r3.text

            vs3 = _extract_hidden(html3, "__VIEWSTATE")
            vsg3 = _extract_hidden(html3, "__VIEWSTATEGENERATOR")
            ev3 = _extract_hidden(html3, "__EVENTVALIDATION")
            if not vs3 or not ev3:
                print("  Failed to extract viewstate from cart page")
                return None

            # Step 4: POST Afram (hfKaupaMouseClicked=true is required)
            form4 = {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": vs3,
                "__VIEWSTATEGENERATOR": vsg3 or "",
                "__VIEWSTATEENCRYPTED": "",
                "__EVENTVALIDATION": ev3,
                "hfMouseClicked": "false",
                "hfKaupaMouseClicked": "true",
                "ctl00$MainContent$btnKaupa": "Áfram",
            }
            r4 = await http.post(
                cart_page_url,
                data=form4,
                cookies=cookies,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r4.raise_for_status()
            cookies.update(dict(r4.cookies))
            html4 = r4.text

            # Extract payment gateway hidden fields from the Afram response
            payment_fields: dict[str, str] = {}
            for m in re.finditer(
                r'<input[^>]*type="hidden"[^>]*>', html4, re.IGNORECASE
            ):
                tag = m.group(0)
                name_m = re.search(r'name="([^"]+)"', tag)
                value_m = re.search(r'value="([^"]*)"', tag)
                if name_m:
                    fname = name_m.group(1)
                    fvalue = value_m.group(1) if value_m else ""
                    if not fname.startswith("__") and not fname.startswith("hf"):
                        payment_fields[fname] = fvalue

            if not payment_fields:
                # Check if this is an electronic report requiring email
                if "Skráning netfangs" in html4 or "netfang" in html4.lower():
                    print(
                        f"  Electronic report (typeId={chosen_type}) requires email registration."
                    )
                    print(
                        "  These cannot be downloaded directly. Try an older year with PDF format."
                    )
                    return None
                print("  No payment form fields found after Afram")
                return None

            print(f"  Payment form: {len(payment_fields)} fields")

            # Step 5: POST payment fields to ReturnPage.aspx
            return_url = (
                f"https://vefur.rsk.is/Vefverslun/ReturnPage.aspx?kid={kid}"
            )
            r5 = await http.post(
                return_url,
                data=payment_fields,
                cookies=cookies,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": cart_page_url,
                },
            )
            r5.raise_for_status()
            cookies.update(dict(r5.cookies))
            html5 = r5.text

            if "download-button" not in html5:
                print("  Download page not reached — no download button found")
                return None

            vs5 = _extract_hidden(html5, "__VIEWSTATE")
            vsg5 = _extract_hidden(html5, "__VIEWSTATEGENERATOR")
            ev5 = _extract_hidden(html5, "__EVENTVALIDATION")
            if not vs5 or not ev5:
                print("  Failed to extract viewstate from download page")
                return None

            # Step 6: POST "Saekja oll skjol" to download ZIP
            form6 = {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": vs5,
                "__VIEWSTATEGENERATOR": vsg5 or "",
                "__VIEWSTATEENCRYPTED": "",
                "__EVENTVALIDATION": ev5,
                "hfMouseClicked": "true",
                "ctl00$MainContent$ucVoruGrid$btnSaekjaAllarVorur": "Sækja öll skjöl",
            }
            r6 = await http.post(
                return_url,
                data=form6,
                cookies=cookies,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": return_url,
                    "Origin": "https://vefur.rsk.is",
                },
            )
            r6.raise_for_status()

            content_type = r6.headers.get("content-type", "")
            if "zip" not in content_type and "octet-stream" not in content_type:
                # Check if it's a direct PDF
                if r6.content[:5] == b"%PDF-":
                    output_path.write_bytes(r6.content)
                    print(
                        f"  Downloaded PDF: {output_path} ({output_path.stat().st_size} bytes)"
                    )
                    return output_path
                print(
                    f"  Expected ZIP/PDF, got {content_type}: {r6.text[:300]}"
                )
                return None

            # Step 7: Extract PDF from ZIP
            print(f"  ZIP downloaded: {len(r6.content)} bytes")
            with zipfile.ZipFile(io.BytesIO(r6.content)) as zf:
                pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                if not pdf_names:
                    print(f"  No PDF in ZIP. Contents: {zf.namelist()}")
                    return None
                output_path.write_bytes(zf.read(pdf_names[0]))

            print(
                f"  Downloaded to {output_path} ({output_path.stat().st_size} bytes)"
            )
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
    root_kennitala: str,
    max_depth: int = 5,
    visited: set[str] | None = None,
    download_pdfs: bool = False,
) -> dict:
    """
    Recursively map ownership chain starting from a company.

    Args:
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

    company = await get_company_info(kt_clean)

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
        pdf_path = await download_annual_report(kt_clean, latest.year, RAW_DIR)
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
                owner.kennitala, max_depth - 1, visited, download_pdfs
            )
            owner_data["owners"] = child_chain.get("owners", [])

        result["owners"].append(owner_data)

    return result


async def download_command(kennitala: str, year: int | None = None) -> None:
    """Download annual report(s) for a company."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    company = await get_company_info(kennitala)
    if company is None:
        print(f"Company {kennitala} not found")
        return

    print(f"Company: {company.name}")
    print(f"Available reports: {len(company.available_reports)}")

    if year:
        # Download specific year
        await download_annual_report(kennitala, year, RAW_DIR)
    else:
        # Download all available
        for report in company.available_reports:
            print(f"Downloading {report.year}...")
            await download_annual_report(kennitala, report.year, RAW_DIR)
            await asyncio.sleep(REQUEST_DELAY)


async def chain_command(kennitala: str, depth: int = 5, download: bool = False) -> None:
    """Map ownership chain for a company."""
    print(f"Mapping ownership chain for {kennitala} (depth={depth})")
    chain = await map_ownership_chain(
        kennitala, max_depth=depth, download_pdfs=download
    )

    # Save result
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / f"ownership_chain_{kennitala}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)

    print(f"\nOwnership chain saved to {output_path}")
    print(json.dumps(chain, ensure_ascii=False, indent=2))


async def info_command(kennitala: str) -> None:
    """Get company info without downloading."""
    company = await get_company_info(kennitala)

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

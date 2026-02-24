"""
Reykjavík Byggingarfulltrúi (Building Permits) PDF Scraper

Scrapes building permit meeting minutes from PDF files on reykjavik.is

Usage:
    uv run python scripts/reykjavik_byggingarfulltrui.py list
    uv run python scripts/reykjavik_byggingarfulltrui.py fetch <pdf_url>
    uv run python scripts/reykjavik_byggingarfulltrui.py scrape --from YYYY-MM --to YYYY-MM
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
import pdfplumber
import typer
from bs4 import BeautifulSoup

app = typer.Typer()

BASE_URL = "https://reykjavik.is"
FUNDARGERDIR_URL = "https://reykjavik.is/byggingarmal/fundargerdir-byggingarfulltrua"

# Icelandic month names
MONTHS_IS = {
    "janúar": 1, "januar": 1,
    "febrúar": 2, "februar": 2,
    "mars": 3,
    "apríl": 4, "april": 4,
    "maí": 5, "mai": 5,
    "júní": 6, "juni": 6,
    "júlí": 7, "juli": 7,
    "ágúst": 8, "agust": 8,
    "september": 9,
    "október": 10, "oktober": 10,
    "nóvember": 11, "november": 11,
    "desember": 12,
}


@dataclass
class Minute:
    case_serial: Optional[str]
    headline: str
    address: Optional[str]
    inquiry: Optional[str]
    remarks: Optional[str]
    status: Optional[str] = None


@dataclass 
class Meeting:
    council: str
    municipality: str
    number: int
    date: datetime
    url: str
    attendees: list[str] = field(default_factory=list)
    minutes: list[Minute] = field(default_factory=list)


def parse_date_from_filename(filename: str) -> Optional[datetime]:
    """Parse date from PDF filename like 'afgreidslufundur-byggingarfulltrua-3.-februar-2026.pdf'"""
    # Try various patterns
    patterns = [
        r"(\d{1,2})[._-]\s*(\w+)[._-]\s*(\d{4})",  # 3. februar 2026
        r"(\d{1,2})[._\s]+(\w+)[._\s]+(\d{4})",    # 3 februar 2026
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename.lower())
        if match:
            day, month_name, year = match.groups()
            month_name = month_name.replace("_", "").replace("-", "")
            month = MONTHS_IS.get(month_name)
            if month:
                return datetime(int(year), month, int(day))
    return None


def parse_date_from_text(text: str) -> Optional[datetime]:
    """Parse date from PDF content like 'Árið 2026, þriðjudaginn 3. febrúar kl. 13:00'"""
    match = re.search(
        r"Árið\s+(\d{4}).*?(\d{1,2})\.\s+(\w+)\s+kl\.\s+(\d{1,2}):(\d{2})",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        year, day, month_name, hour, minute = match.groups()
        month = MONTHS_IS.get(month_name.lower())
        if month:
            return datetime(int(year), month, int(day), int(hour), int(minute))
    return None


def extract_meeting_number(text: str) -> Optional[int]:
    """Extract meeting number from text like '1242. fund'"""
    match = re.search(r"(\d+)\.\s*fund", text)
    if match:
        return int(match.group(1))
    return None


def extract_attendees(text: str) -> list[str]:
    """Extract attendees from 'Fundinn sátu: Name1, Name2 og Name3.'"""
    match = re.search(r"Fundinn sátu:\s*([^.]+)\.", text)
    if match:
        names_text = match.group(1)
        names = re.split(r",\s*|\s+og\s+", names_text)
        return [n.strip() for n in names if n.strip() and len(n.strip()) > 2]
    return []


def extract_status(text: str) -> Optional[str]:
    """Extract decision status from text"""
    text_lower = text.lower()
    
    if re.search(r"\bsamþykkt\b", text_lower):
        return "samþykkt"
    if re.search(r"\bfrestað\b", text_lower):
        return "frestað"
    if re.search(r"\bsynjað\b", text_lower):
        return "synjað"
    if re.search(r"\bvísað til\b", text_lower):
        return "vísað"
    return None


def parse_pdf(pdf_path: str, url: str) -> Meeting:
    """Parse a byggingarfulltrúi PDF into a Meeting object"""
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    
    # Extract metadata
    date = parse_date_from_text(full_text) or parse_date_from_filename(url)
    meeting_num = extract_meeting_number(full_text) or 0
    attendees = extract_attendees(full_text)
    
    meeting = Meeting(
        council="Byggingarfulltrúi",
        municipality="Reykjavík",
        number=meeting_num,
        date=date or datetime.now(),
        url=url,
        attendees=attendees,
    )
    
    # Parse agenda items
    # Pattern: number. Address - USKxxxxxxxx
    # Followed by description paragraphs
    # Ending with status (Samþykkt/Frestað/etc.)
    
    # Split into items by numbered headings
    item_pattern = re.compile(
        r"^(\d+)\.\s+(.+?)\s*-\s*(USK\d+)",
        re.MULTILINE
    )
    
    matches = list(item_pattern.finditer(full_text))
    
    for i, match in enumerate(matches):
        item_num = int(match.group(1))
        address_headline = match.group(2).strip()
        case_serial = match.group(3)
        
        # Get text until next item or end
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        item_text = full_text[start_pos:end_pos].strip()
        
        # Split into paragraphs
        paragraphs = [p.strip() for p in item_text.split("\n") if p.strip()]
        
        # Find the status line (usually last meaningful line before next item)
        remarks = None
        inquiry_parts = []
        
        for para in paragraphs:
            status = extract_status(para)
            if status:
                remarks = para
                break
            else:
                inquiry_parts.append(para)
        
        inquiry = "\n".join(inquiry_parts) if inquiry_parts else None
        
        # Clean address - remove "breytingaerindi" suffix
        address = re.sub(r"\s*–?\s*breytingaerindi\s*$", "", address_headline, flags=re.IGNORECASE)
        
        # Headline includes address and case serial
        headline = f"{address_headline} - {case_serial}"
        
        minute = Minute(
            case_serial=case_serial,
            headline=headline,
            address=address,
            inquiry=inquiry,
            remarks=remarks,
            status=extract_status(remarks) if remarks else None,
        )
        meeting.minutes.append(minute)
    
    return meeting


def meeting_to_dict(meeting: Meeting) -> dict:
    """Convert Meeting to JSON-serializable dict"""
    return {
        "meeting": {
            "council": meeting.council,
            "municipality": meeting.municipality,
            "number": meeting.number,
            "date": meeting.date.isoformat() if meeting.date else None,
            "url": meeting.url,
            "attendees": meeting.attendees,
        },
        "minutes": [
            {
                "case_serial": m.case_serial,
                "headline": m.headline,
                "address": m.address,
                "inquiry": m.inquiry,
                "remarks": m.remarks,
                "status": m.status,
                "entities": [],
                "attachments": [],
            }
            for m in meeting.minutes
        ]
    }


def fetch_pdf_list() -> list[dict]:
    """Fetch list of PDF URLs from the fundargerdir page"""
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(FUNDARGERDIR_URL)
        response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    pdfs = []
    
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if ".pdf" in href.lower() and "byggingarfulltr" in href.lower():
            full_url = urljoin(BASE_URL, href) if not href.startswith("http") else href
            date = parse_date_from_filename(href)
            pdfs.append({
                "url": full_url,
                "date": date,
                "filename": href.split("/")[-1],
            })
    
    # Sort by date descending
    pdfs.sort(key=lambda x: x["date"] or datetime.min, reverse=True)
    return pdfs


@app.command("list")
def list_pdfs(limit: int = typer.Option(20, help="Max PDFs to list")):
    """List available PDF meeting minutes"""
    pdfs = fetch_pdf_list()
    
    for pdf in pdfs[:limit]:
        date_str = pdf["date"].strftime("%Y-%m-%d") if pdf["date"] else "unknown"
        typer.echo(f"{date_str}: {pdf['filename']}")


@app.command()
def fetch(
    pdf_url: str,
    output: Optional[Path] = typer.Option(None, help="Output JSON file"),
):
    """Fetch and parse a single PDF"""
    import tempfile
    
    typer.echo(f"Downloading {pdf_url}...")
    
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(pdf_url)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(response.content)
            pdf_path = f.name
    
    meeting = parse_pdf(pdf_path, pdf_url)
    result = meeting_to_dict(meeting)
    
    Path(pdf_path).unlink()  # Cleanup
    
    if output:
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        typer.echo(f"Written to {output}")
    else:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def scrape(
    output_dir: Path = typer.Option(Path("data/raw/reykjavik-byggingarfulltrui"), help="Output directory"),
    limit: int = typer.Option(None, help="Max PDFs to scrape"),
    delay: float = typer.Option(1.0, help="Delay between requests"),
):
    """Scrape all available PDFs"""
    import tempfile
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pdfs = fetch_pdf_list()
    if limit:
        pdfs = pdfs[:limit]
    
    typer.echo(f"Found {len(pdfs)} PDFs to scrape")
    
    for pdf in pdfs:
        date_str = pdf["date"].strftime("%Y-%m-%d") if pdf["date"] else "unknown"
        output_file = output_dir / f"byggingarfulltrui_{date_str}.json"
        
        if output_file.exists():
            typer.echo(f"Skipping {date_str} (already exists)")
            continue
        
        typer.echo(f"Fetching {date_str}...", nl=False)
        
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(pdf["url"])
                response.raise_for_status()
                
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(response.content)
                    pdf_path = f.name
            
            meeting = parse_pdf(pdf_path, pdf["url"])
            result = meeting_to_dict(meeting)
            
            output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            typer.echo(f" ✓ {len(meeting.minutes)} items")
            
            Path(pdf_path).unlink()
            
        except Exception as e:
            typer.echo(f" ✗ {e}")
        
        time.sleep(delay)


if __name__ == "__main__":
    app()

"""
Reykjavík Fundargerðir (Meeting Minutes) Scraper

Scrapes planning and building permit meeting minutes from reykjavik.is
for import into planitor.io database.

Usage:
    uv run python scripts/reykjavik_fundargerdir.py list [--council COUNCIL]
    uv run python scripts/reykjavik_fundargerdir.py fetch <meeting_url>
    uv run python scripts/reykjavik_fundargerdir.py scrape --council COUNCIL --from N --to M
    uv run python scripts/reykjavik_fundargerdir.py extract-pdf <pdf_url>
"""

import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
import typer

app = typer.Typer()

BASE_URL = "https://reykjavik.is"
FUNDUR_BASE = "https://fundur.reykjavik.is"

# Council URL patterns
COUNCILS = {
    "skipulagsfulltrui": {
        "name": "Afgreiðslufundir skipulagsfulltrúa",
        "pattern": "/fundargerdir/afgreidslufundir-skipulagsfulltrua-fundur-nr-{n}",
        "municipality": "Reykjavík",
        "planitor_name": "Skipulagsfulltrúi",
    },
    "skipulags-og-samgongurad": {
        "name": "Skipulags- og samgönguráð",
        "pattern": "/fundargerdir/skipulags-og-samgongurad-starfadi-2018-2022-fundur-nr-{n}",
        "municipality": "Reykjavík",
        "planitor_name": "Skipulags- og samgönguráð",
    },
    "umhverfis-og-skipulagsrad": {
        "name": "Umhverfis- og skipulagsráð",
        "pattern": "/fundargerdir/umhverfis-og-skipulagsrad-fundur-nr-{n}",
        "municipality": "Reykjavík",
        "planitor_name": "Umhverfis- og skipulagsráð",
    },
}

# Icelandic month names
MONTHS_IS = {
    "janúar": 1, "febrúar": 2, "mars": 3, "apríl": 4,
    "maí": 5, "júní": 6, "júlí": 7, "ágúst": 8,
    "september": 9, "október": 10, "nóvember": 11, "desember": 12,
}


@dataclass
class Entity:
    name: str
    type: str  # "person" or "company"
    kennitala: Optional[str] = None


@dataclass
class Attachment:
    url: str
    label: str  # Name/title of the attachment
    type: str = "application/pdf"  # MIME type


@dataclass
class Minute:
    case_serial: Optional[str]
    headline: str
    address: Optional[str]
    inquiry: Optional[str]
    remarks: Optional[str]
    status: Optional[str] = None  # "samþykkt", "synjað", "frestað", etc.
    entities: list[Entity] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class Meeting:
    council: str
    municipality: str
    number: int
    date: datetime
    url: str
    attendees: list[str] = field(default_factory=list)
    minutes: list[Minute] = field(default_factory=list)


def parse_icelandic_date(text: str) -> Optional[datetime]:
    """Parse Icelandic date like 'Ár 2026, þriðjudaginn 17. febrúar kl. 09:10'"""
    # Try pattern: Ár YYYY, dagur DD. mánuður kl. HH:MM
    match = re.search(
        r"Ár (\d{4}),.*?(\d{1,2})\.\s+(\w+)\s+kl\.\s+(\d{1,2}):(\d{2})",
        text,
        re.IGNORECASE
    )
    if match:
        year, day, month_name, hour, minute = match.groups()
        month = MONTHS_IS.get(month_name.lower())
        if month:
            return datetime(int(year), month, int(day), int(hour), int(minute))
    
    # Fallback: try simpler patterns
    match = re.search(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})", text)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS_IS.get(month_name.lower())
        if month:
            return datetime(int(year), month, int(day))
    
    return None


def extract_case_serial(text: str) -> Optional[str]:
    """Extract case serial like USK26020145"""
    match = re.search(r"\b(USK\d+)\b", text)
    return match.group(1) if match else None


def extract_status(text: str) -> Optional[str]:
    """Extract decision status from text (samþykkt, synjað, etc.)"""
    # Look for status keywords, typically at end of a sentence
    status_patterns = [
        (r"\bsamþykkt\b", "samþykkt"),  # approved
        (r"\bsysjað\b", "synjað"),  # rejected (typo variant)
        (r"\bsynjað\b", "synjað"),  # rejected
        (r"\bfrestað\b", "frestað"),  # postponed
        (r"\bvísað\s+(?:til|frá)\b", "vísað"),  # referred
        (r"\bfellt\s+niður\b", "fellt niður"),  # dropped
        (r"\bafgreitt\b", "afgreitt"),  # processed
    ]
    
    text_lower = text.lower()
    for pattern, status in status_patterns:
        if re.search(pattern, text_lower):
            return status
    return None


def extract_address(text: str) -> Optional[str]:
    """Try to extract address from text (headline or inquiry)"""
    # Common Icelandic street suffixes
    street_suffixes = r"(?:götu|gata|veg|vegur|braut|stræti|torg|holt|mel|ás|brekku|hlíð|gerði|garði|sund|land|bakki|nes|eyri|staðir|höfði|teig|grund)"
    
    patterns = [
        # "Langagerði 24" at start of headline (before " - ")
        rf"^(\w*{street_suffixes})\s+(\d+[a-zA-Z]?)\s*[-–]",
        # "nr. X við Y" pattern
        rf"(?:nr\.|lóð(?:ar)?(?:innar)?)\s*(\d+[a-zA-Z]?)\s+við\s+(\w+{street_suffixes})",
        # "Streetname 24" in text
        rf"(\w*{street_suffixes})\s+(\d+[a-zA-Z]?)\b",
        # "að Streetname X"
        rf"að\s+(\w+{street_suffixes})\s+(\d+[a-zA-Z]?)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                # Normalize to "Street Number" format
                if groups[0].isdigit() or re.match(r"^\d+[a-zA-Z]?$", groups[0]):
                    return f"{groups[1]} {groups[0]}"
                return f"{groups[0]} {groups[1]}"
    return None


def extract_company_names(text: str) -> list[str]:
    """Extract Icelandic company names (ending in ehf., hf., ohf., etc.)"""
    pattern = r"([A-ZÁÉÍÓÚÝÞÆÖÐ][a-záéíóúýþæöð\s&-]+(?:ehf\.|hf\.|ohf\.|sf\.|slhf\.|bs\.))"
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]


def fetch_meeting_page(url: str) -> str:
    """Fetch meeting page HTML"""
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def parse_meeting_page(html: str, url: str, council_key: str) -> Meeting:
    """Parse meeting page HTML into Meeting object"""
    soup = BeautifulSoup(html, "html.parser")
    council_info = COUNCILS[council_key]
    
    # Extract meeting number from URL
    match = re.search(r"fundur-nr-(\d+)", url)
    meeting_number = int(match.group(1)) if match else 0
    
    # Find main content
    content = soup.find("article") or soup.find("main") or soup
    
    # Get all text for date parsing
    full_text = content.get_text()
    meeting_date = parse_icelandic_date(full_text)
    
    # Extract attendees (usually after "Fundinn sátu:")
    attendees = []
    attendee_match = re.search(r"Fundinn sátu:\s*([^.]+?)(?:\.|Eftirtaldir)", full_text)
    if attendee_match:
        attendee_text = attendee_match.group(1)
        # Split by "og" and commas
        attendees = [
            name.strip() 
            for name in re.split(r",|(?:\s+og\s+)", attendee_text)
            if name.strip() and len(name.strip()) > 2
        ]
    
    meeting = Meeting(
        council=council_info["name"],
        municipality=council_info["municipality"],
        number=meeting_number,
        date=meeting_date or datetime.now(),
        url=url,
        attendees=attendees,
    )
    
    # Parse agenda items
    # Real agenda items have id="agenda_XXXXX", skip attachment <li> items inside <ul>
    items = content.find_all("li", id=lambda x: x and x.startswith("agenda_"))
    
    # Fallback to all <li> if no agenda_ items found
    if not items:
        items = content.find_all("li")
    
    current_minute = None
    
    for item in items:
        # Skip items inside <ul> (attachment lists) - they don't have agenda_ id
        if item.parent and item.parent.name == "ul" and not item.get("id", "").startswith("agenda_"):
            continue
        
        # Get paragraphs separately to preserve structure
        paragraphs = item.find_all("p")
        
        # Get full text with line breaks for processing
        text = item.get_text(separator="\n", strip=True)
        
        # Skip navigation/footer items
        if len(text) < 50:
            continue
        
        # Extract case serial from full text
        case_serial = extract_case_serial(text)
        
        # Structure: first <p> = headline, middle <p>s = inquiry, last <p> = remarks/decision
        if paragraphs:
            headline = paragraphs[0].get_text(strip=True)[:200]
            
            # Filter out empty paragraphs and "Fylgigögn"
            content_paragraphs = [
                p.get_text(strip=True) for p in paragraphs[1:]
                if p.get_text(strip=True) and p.get_text(strip=True) != "Fylgigögn"
            ]
            
            if len(content_paragraphs) >= 2:
                # Last paragraph is the decision/remarks
                remarks_text = content_paragraphs[-1]
                # Middle paragraphs are the inquiry
                inquiry_text = "\n\n".join(content_paragraphs[:-1])
            elif len(content_paragraphs) == 1:
                # Only one paragraph after headline - treat as remarks if it looks like a decision
                para = content_paragraphs[0]
                if extract_status(para):
                    remarks_text = para
                    inquiry_text = None
                else:
                    remarks_text = None
                    inquiry_text = para
            else:
                remarks_text = None
                inquiry_text = None
        else:
            lines = text.split("\n")
            headline = lines[0][:200] if lines else text[:200]
            inquiry_text = text[:2000] if len(text) > 200 else None
            remarks_text = None
        
        # Clean headline - remove "Fylgigögn" suffix and trailing case serial
        headline = re.sub(r"\s*Fylgigögn\s*$", "", headline)
        headline = re.sub(r"\s*-?\s*USK\d+\s*$", "", headline)
        
        # Extract address
        address = extract_address(text)
        
        # Extract company names as entities
        companies = extract_company_names(text)
        entities = [Entity(name=c, type="company") for c in companies]
        
        # Extract PDF attachments
        attachments = []
        for link in item.find_all("a", href=True):
            href = link["href"]
            if ".pdf" in href.lower():
                full_url = urljoin(FUNDUR_BASE, href) if not href.startswith("http") else href
                attachments.append(Attachment(
                    url=full_url,
                    label=link.get_text(strip=True) or "Attachment",
                    type="application/pdf",
                ))
        
        # Extract status from remarks (the decision paragraph)
        status = extract_status(remarks_text) if remarks_text else None
        
        minute = Minute(
            case_serial=case_serial,
            headline=headline,
            address=address,
            inquiry=inquiry_text,
            remarks=remarks_text,
            status=status,
            entities=entities,
            attachments=attachments,
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
                "entities": [asdict(e) for e in m.entities],
                "attachments": [asdict(a) for a in m.attachments],
            }
            for m in meeting.minutes
        ]
    }


@app.command("list")
def list_meetings(
    council: str = typer.Option("skipulagsfulltrui", help="Council key"),
    limit: int = typer.Option(20, help="Max meetings to list"),
):
    """List recent meetings from fundargerdir page"""
    url = f"{BASE_URL}/fundargerdir"
    html = fetch_meeting_page(url)
    soup = BeautifulSoup(html, "html.parser")
    
    council_info = COUNCILS.get(council)
    if not council_info:
        typer.echo(f"Unknown council: {council}. Available: {list(COUNCILS.keys())}")
        raise typer.Exit(1)
    
    # Find links matching the council pattern
    pattern_base = council_info["pattern"].split("{n}")[0]
    meetings = []
    
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if pattern_base.replace("/fundargerdir/", "") in href:
            match = re.search(r"fundur-nr-(\d+)", href)
            if match:
                meetings.append({
                    "number": int(match.group(1)),
                    "url": urljoin(BASE_URL, href),
                    "title": link.get_text(strip=True),
                })
    
    # Deduplicate and sort
    seen = set()
    unique = []
    for m in meetings:
        if m["number"] not in seen:
            seen.add(m["number"])
            unique.append(m)
    
    unique.sort(key=lambda x: x["number"], reverse=True)
    
    for m in unique[:limit]:
        typer.echo(f"#{m['number']}: {m['url']}")


@app.command()
def fetch(
    meeting_url: str,
    council: str = typer.Option("skipulagsfulltrui", help="Council key"),
    output: Optional[Path] = typer.Option(None, help="Output JSON file"),
):
    """Fetch and parse a single meeting"""
    html = fetch_meeting_page(meeting_url)
    meeting = parse_meeting_page(html, meeting_url, council)
    
    result = meeting_to_dict(meeting)
    
    if output:
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        typer.echo(f"Written to {output}")
    else:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def scrape(
    council: str = typer.Option(..., help="Council key"),
    start: int = typer.Option(..., "--from", help="Starting meeting number"),
    end: int = typer.Option(..., "--to", help="Ending meeting number"),
    output_dir: Path = typer.Option(Path("data/raw/reykjavik-fundargerdir"), help="Output directory"),
    delay: float = typer.Option(1.0, help="Delay between requests in seconds"),
):
    """Scrape a range of meetings"""
    council_info = COUNCILS.get(council)
    if not council_info:
        typer.echo(f"Unknown council: {council}. Available: {list(COUNCILS.keys())}")
        raise typer.Exit(1)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for n in range(start, end + 1):
        url = BASE_URL + council_info["pattern"].format(n=n)
        output_file = output_dir / f"{council}_{n}.json"
        
        if output_file.exists():
            typer.echo(f"Skipping #{n} (already exists)")
            continue
        
        typer.echo(f"Fetching #{n}...")
        
        try:
            html = fetch_meeting_page(url)
            meeting = parse_meeting_page(html, url, council)
            result = meeting_to_dict(meeting)
            
            output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            typer.echo(f"  → {len(meeting.minutes)} items, saved to {output_file}")
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                typer.echo(f"  → Not found (404)")
            else:
                typer.echo(f"  → Error: {e}")
        except Exception as e:
            typer.echo(f"  → Error: {e}")
        
        time.sleep(delay)


@app.command()
def extract_pdf(
    pdf_url: str,
    check_kennitala: bool = typer.Option(True, help="Search for kennitalas in text"),
):
    """Download and extract text from a PDF attachment"""
    try:
        import pdfplumber
    except ImportError:
        typer.echo("pdfplumber not installed. Run: uv add pdfplumber")
        raise typer.Exit(1)
    
    import tempfile
    
    # Download PDF
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(pdf_url)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(response.content)
            pdf_path = f.name
    
    # Extract text
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    
    combined = "\n\n".join(full_text)
    
    if check_kennitala:
        # Look for kennitala patterns (6 digits - 4 digits)
        kennitalas = re.findall(r"\b(\d{6}-?\d{4})\b", combined)
        if kennitalas:
            typer.echo("Found kennitalas:")
            for kt in set(kennitalas):
                typer.echo(f"  {kt}")
            typer.echo()
    
    typer.echo(combined)
    
    # Cleanup
    Path(pdf_path).unlink()


if __name__ == "__main__":
    app()

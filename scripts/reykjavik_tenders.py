"""Scrape Reykjavík tender results for winter service contracts."""

import csv
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

TENDER_URLS = {
    2018: "https://reykjavik.is/en/nidurstodur-utboda-2018",
    2019: "https://reykjavik.is/en/tender-results-2019",
    2020: "https://reykjavik.is/en/tender-results-2020",
    2021: "https://reykjavik.is/en/tender-results-2021",
    2022: "https://reykjavik.is/en/tender-results-2022",
    2023: "https://reykjavik.is/en/tender-results-2023",
    2024: "https://reykjavik.is/en/economy-tenders-procurement-results-tenders/nidurstodur-utboda-og-verdfyrirspurna-2024",
}

# Keywords for winter/street service tenders (case-insensitive)
WINTER_KEYWORDS = [
    r"vetrar",
    r"snjó",
    r"salt",
    r"hálku",
    r"winter",
    r"snow",
]

STREET_KEYWORDS = [
    r"göngustíg",
    r"göngu",
    r"hjólastíg",
    r"hjóla",
    r"gangstétt",
    r"pedestrian",
    r"walking.?path",
    r"bike.?path",
]

CLEANING_KEYWORDS = [
    r"hreinsun",
    r"sópun",
    r"cleaning",
    r"sweeping",
    r"mowing",
    r"sláttur",
]


def classify_tender(text: str) -> str | None:
    """Classify a tender description. Returns category or None if not relevant."""
    t = text.lower()

    # Check winter keywords first
    for kw in WINTER_KEYWORDS:
        if re.search(kw, t):
            if any(re.search(sk, t) for sk in STREET_KEYWORDS):
                return "winter_paths"
            return "winter_streets"

    # Street/path cleaning
    for kw in CLEANING_KEYWORDS:
        if re.search(kw, t):
            if any(re.search(sk, t) for sk in STREET_KEYWORDS + [r"gat[na]", r"street"]):
                return "street_cleaning"

    return None


def scrape_year(year: int, url: str) -> list[dict]:
    """Scrape tender results for a given year."""
    print(f"Fetching {year}...", file=sys.stderr)
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tenders = []

    # Find all text content that looks like tender entries
    # Tender pages have varying HTML structure, so we look for patterns
    # Common pattern: "NNNNN Description" where NNNNN is tender number
    text_content = soup.get_text(separator="\n")

    for line in text_content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Try to extract tender number and description
        match = re.match(r"(\d{4,6})\s+(.+)", line)
        if match:
            tender_id = match.group(1)
            description = match.group(2).strip()
            category = classify_tender(description)
            if category:
                tenders.append({
                    "year": year,
                    "tender_id": tender_id,
                    "description": description,
                    "category": category,
                })

    # Also check for list items, table cells, etc. with tender-like content
    for el in soup.find_all(["li", "td", "p", "div"]):
        text = el.get_text(strip=True)
        match = re.match(r"(\d{4,6})\s+(.+)", text)
        if match:
            tender_id = match.group(1)
            description = match.group(2).strip()
            category = classify_tender(description)
            if category and not any(t["tender_id"] == tender_id for t in tenders):
                tenders.append({
                    "year": year,
                    "tender_id": tender_id,
                    "description": description,
                    "category": category,
                })

    return tenders


def main():
    output = Path("data/processed/reykjavik_winter_tenders.csv")
    output.parent.mkdir(parents=True, exist_ok=True)

    all_tenders = []
    for year, url in sorted(TENDER_URLS.items()):
        tenders = scrape_year(year, url)
        all_tenders.extend(tenders)
        print(f"  {year}: {len(tenders)} winter/street tenders found", file=sys.stderr)

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["year", "tender_id", "description", "category"])
        writer.writeheader()
        writer.writerows(all_tenders)

    print(f"\nWrote {len(all_tenders)} tenders to {output}", file=sys.stderr)

    # Print summary
    from collections import Counter
    by_year = Counter(t["year"] for t in all_tenders)
    for y in sorted(TENDER_URLS.keys()):
        print(f"  {y}: {by_year.get(y, 0)}")


if __name__ == "__main__":
    main()

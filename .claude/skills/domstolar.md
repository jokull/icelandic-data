# Icelandic Courts (dómstólar)

Three independent court sites — no unified API, all HTML scraping.

## Sites

| Court | Domain | Rulings from |
|-------|--------|-------------|
| Héraðsdómstólar (8 district courts) | `heradsdomstolar.is` | ~2015+ |
| Landsréttur (Court of Appeals) | `landsrettur.is` | 2018+ |
| Hæstiréttur (Supreme Court) | `haestirettur.is` | 1999+ |

Case number prefixes: `E-` = einkamál (civil), `S-` = sakamál (criminal).

## Héraðsdómstólar (District Courts)

### RSS Feeds (best entry point, no JS needed)

```
https://www.heradsdomstolar.is/heradsdomstolar/{slug}/domar/rss/
```

Courts: `reykjavik`, `reykjanes`, `vesturland`, `vestfirdir`, `nordurland-vestra`, `nordurland-eystra`, `austurland`, `sudurland`

Each RSS item has: `<title>` (case number), `<description>` (reifun/summary), `<link>`, `<guid>` (UUID), `<pubDate>`.

### PDF Download (direct, no JS)

```
https://www.heradsdomstolar.is/Cache/Verdicts/{guid}.pdf
```

### Search (GET params)

```
https://www.heradsdomstolar.is/default.aspx?SearchAction=Search&pageid=fd8e17eb-6e70-11e5-80c3-005056bc50d4&Verdict={text}&Court={court}&CaseNumber=&CaseType=&LawParagraphs=&Keywords=&Parties=&FromDate={DD.MM.YYYY}&ToDate={DD.MM.YYYY}
```

**Caveat**: Search results render client-side (JS required → Playwright). Use RSS + pagination for non-JS scraping.

### Pagination (AJAX, returns HTML fragments, no JS needed)

```
GET /default.aspx?pageitemid={pageitemid}&offset={n}&count={batch_size}
```

Reykjavík pageitemid: `98619c0d-86c7-11e5-80c6-005056bc6a40` (initial count=22, then batches of 6).

Returns `.verdict-box` divs with date, case number, judge, parties, reifun, link.

### Individual Ruling

```
https://www.heradsdomstolar.is/default.aspx?pageid=347c3bb1-8926-11e5-80c6-005056bc6a40&id={guid}
```

## Landsréttur (Court of Appeals)

### Search

```
https://www.landsrettur.is/search?Text={text}&CaseNumber=&LawCitations=&Keywords=&Parties=&CaseType=&FromDate={DD.MM.YYYY}&ToDate={DD.MM.YYYY}
```

### Pagination

```
GET /domar-og-urskurdir/$Verdicts/Index/?pageitemid=5cf6e850-20b6-11e9-85de-94b86df896cb&offset={n}&count={n}
```

Returns HTML fragments. Default count=12.

### Individual Ruling

```
https://www.landsrettur.is/domar-og-urskurdir/domur-urskurdur/?Id={case_uuid}&verdictid={verdict_uuid}
```

## Hæstiréttur (Supreme Court)

### Search

```
https://www.haestirettur.is/default.aspx?SearchAction=Search&pageid=fd8e17eb-6e70-11e5-80c3-005056bc50d4&tab=1&Verdict={text}&CaseNumber=&LawParagraphs=&Keywords=&Parties=&FromDate=&ToDate=
```

### Pagination

```
GET /default.aspx?pageitemid=a31e2c30-9510-11e5-80c6-005056bc6a40&offset={n}&count={n}
```

### Individual Ruling

```
https://www.haestirettur.is/default.aspx?pageid=0f2f6428-7b6a-11eb-947c-005056bc0bdb&id={guid}
```

## Metadata Per Ruling

- **Málsnúmer** (case number): e.g. `E-679/2023`, `36/2020`
- **Dagsetning** (date)
- **Dómari** (judge name + title)
- **Málsaðilar** (parties) with lawyers
- **Reifun** (summary/abstract)
- **Lykilorð** (keywords/tags)
- **Lagagreinar** (legal statutes cited)
- **Full text** (HTML on page, PDF for district courts)

## Scraping Strategy

1. **Discovery**: Poll RSS feeds (8 district courts) + paginate listing endpoints
2. **Full text**: Fetch PDFs from `/Cache/Verdicts/{guid}.pdf` (district) or scrape HTML (upper courts)
3. **Search**: Use Playwright for JS-rendered search results, or stick to pagination endpoints
4. **Cross-references**: Upper court rulings link to lower court decisions — useful for case tracking

## Relevant Search Terms for Launaþjófnaður

- `launaþjófnaður` (wage theft)
- `vangreidd laun` / `vangoldin laun` (unpaid wages)
- `vinnulaun` (work wages)
- `kjarasamningur` (collective agreement)
- `ólögmæt launakjör` (illegal wage conditions)
- `mansal` (human trafficking — severe cases)
- `vinnuréttindi` (labor rights)

## Example: Fetch + Parse Script

```python
"""Search Icelandic court rulings across all three court levels."""
import httpx
from bs4 import BeautifulSoup

COURTS = {
    "héraðsdómstólar": {
        "base": "https://www.heradsdomstolar.is",
        "search": "/default.aspx",
        "params": {
            "SearchAction": "Search",
            "pageid": "fd8e17eb-6e70-11e5-80c3-005056bc50d4",
        },
        "text_param": "Verdict",
        "pagination_pageitemid": "98619c0d-86c7-11e5-80c6-005056bc6a40",
    },
    "landsréttur": {
        "base": "https://www.landsrettur.is",
        "search": "/search",
        "params": {},
        "text_param": "Text",
        "pagination_pageitemid": "5cf6e850-20b6-11e9-85de-94b86df896cb",
    },
    "hæstiréttur": {
        "base": "https://www.haestirettur.is",
        "search": "/default.aspx",
        "params": {
            "SearchAction": "Search",
            "pageid": "fd8e17eb-6e70-11e5-80c3-005056bc50d4",
            "tab": "1",
        },
        "text_param": "Verdict",
        "pagination_pageitemid": "a31e2c30-9510-11e5-80c6-005056bc6a40",
    },
}

def paginate_results(court_key: str, offset: int = 0, count: int = 20):
    """Fetch a page of rulings via the AJAX pagination endpoint (no JS needed)."""
    court = COURTS[court_key]
    url = f"{court['base']}/default.aspx"
    params = {
        "pageitemid": court["pagination_pageitemid"],
        "offset": offset,
        "count": count,
    }
    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    return parse_verdict_boxes(r.text)

def parse_verdict_boxes(html: str) -> list[dict]:
    """Parse .verdict-box elements from HTML fragment."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for box in soup.select(".verdict-box, .row"):
        # Extract what we can — structure varies by court
        links = box.select("a[href]")
        title = box.get_text(strip=True)[:200]
        href = links[0]["href"] if links else None
        results.append({"title": title, "url": href})
    return results

def fetch_rss(court_slug: str) -> list[dict]:
    """Fetch RSS feed for a district court."""
    url = f"https://www.heradsdomstolar.is/heradsdomstolar/{court_slug}/domar/rss/"
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "xml")
    items = []
    for item in soup.find_all("item"):
        items.append({
            "case_number": item.title.text if item.title else "",
            "summary": item.description.text if item.description else "",
            "url": item.link.text if item.link else "",
            "guid": item.guid.text if item.guid else "",
            "date": item.pubDate.text if item.pubDate else "",
        })
    return items

def download_pdf(guid: str, output_path: str):
    """Download district court ruling PDF."""
    url = f"https://www.heradsdomstolar.is/Cache/Verdicts/{guid}.pdf"
    r = httpx.get(url, timeout=60)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(r.content)

# Usage:
# items = fetch_rss("reykjavik")
# download_pdf(items[0]["guid"], "ruling.pdf")
# results = paginate_results("hæstiréttur", offset=0, count=20)
```

## robots.txt Note

All three sites disallow `/domar*` in robots.txt. Search and pagination endpoints are not blocked. Use responsibly for personal/research purposes.

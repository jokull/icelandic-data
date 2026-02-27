# Ferðamálastofa (Icelandic Tourist Board)

Inbound tourism statistics via Power BI dashboard scraping. Passenger counts through Keflavík airport by nationality, month, and year.

## Data Source

**Dashboard URL:** `https://www.maelabordferdathjonustunnar.is/`
**Embed backend:** `ferdapbi.azurewebsites.net` (Azure web app generating Power BI embed tokens)

The dashboard embeds Power BI reports via `ferdapbi.azurewebsites.net/embed/{reportId}`. Data must be extracted by intercepting Power BI API calls within the iframe.

### Power BI Report IDs

| Report ID | Page | Description |
|-----------|------|-------------|
| `1fa56a04-3340-46c5-a36b-f9dde4ce0b92` | `/fjoldi-farthega-um-keflavik` | Passenger counts by nationality |
| `34af65b4-b68d-4309-a17a-5e9d4632b55c` | `/hotel` | Hotel guest nights and occupancy |
| `7cf5f866-459c-4873-947c-082d8a216ea9` | `/allir-gististadir` | All accommodation types |
| `ae74ab2c-4b1a-4a5c-bf4f-a8ffdda1801f` | `/dvalarlengd-og-gistimati` | Length of stay and accommodation type |

## Available Dashboards

### Samgöngur (Transport)

| Page | URL path | Description |
|------|----------|-------------|
| Þjóðernaskipting og fjöldi um Keflavík | `/fjoldi-farthega-um-keflavik` | **Primary** — passenger counts by nationality |
| Framboð á flugi frá Keflavík | `/frambod-a-flugi-fra-keflavik` | Flight supply from Keflavík |
| Verð á flugi | `/verd-a-flugi` | Flight prices |
| Tölfræðivísar norrænna flugfélaga | `/tolfraedivisar-norraenna-flugfelaga` | Nordic airline statistics |
| Skemmtiferðaskip | `/skemmtiferdaskip` | Cruise ships |
| Norróna | `/norrona` | Norröna ferry |

### Ferðamenn (Tourists)

| Page | URL path | Description |
|------|----------|-------------|
| Aldur, kyn og fleiri bakgrunnsbreytur | `/aldur-kyn-og-fleiri-bakgrunnsbreytur` | Age, gender, demographics |
| Tilgangur ferðar og heimsóttir landshlutar | `/tilgangur-ferdar-og-heimsottir-landshlutar` | Purpose of travel, regions visited |
| Ánægja og upplifun | `/anaegja-og-upplifun` | Satisfaction and experience |
| Fjöldi gesta á áfangastöðum | `/fjoldi-gesta-a-afangastodum` | Visitors at destinations |
| Umferðarslys erlendra ferðamanna | `/umferdarslys-erlendra-ferdamanna` | Tourist traffic accidents |
| Spá um fjölda erlendra farþega | `/spa-um-fjolda-erlendra-farthega` | Forecast of foreign passengers |

### Gisting (Accommodation)

| Page | URL path | Description |
|------|----------|-------------|
| Hótel | `/hotel` | Hotel statistics |
| Verð á hótelgistingu | `/verd-a-hotelgistingu` | Hotel prices |
| Allir gististaðir | `/allir-gististadir` | All accommodation types |
| Dvalarlengd og gistimáti | `/dvalarlengd-og-gistimati` | Length of stay and accommodation type |

### Rekstur & efnahagur (Operations & Economy)

(Available but not yet explored)

## Key Data: Passenger Numbers (fjoldi-farthega-um-keflavik)

### Metrics

| Metric | Icelandic | Description |
|--------|-----------|-------------|
| Heildarfjöldi | Total passengers | All passengers through Keflavík in period |
| Fjöldi erlendra farþega | Foreign passengers | Non-Icelandic passengers (count + %) |
| Fjöldi Íslendinga | Icelandic passengers | Icelandic passengers (count + %) |
| Uppsafnaður heildarfjöldi | Cumulative YTD | Year-to-date total |

### Filters/Slicers

| Filter | Icelandic | Values |
|--------|-----------|--------|
| Markaðssvæði | Market area | All, Europe, North America, Asia, etc. |
| Ár | Year | 2016–2026+ |
| Mánuður | Month | janúar–desember |

### Report Tabs

| Tab | Description |
|-----|-------------|
| Fjöldi í [mánuður] | Monthly breakdown by nationality with YoY comparison |
| Yfirlit | Overview/summary |
| Árstíðardreifing | Seasonal distribution |

### Nationality Breakdown

Data includes passenger counts by nationality with flags. Top nationalities (Jan 2026 sample):
Ísland, Bandaríkin, Bretland, Kína, Ítalía, Þýskaland, Frakkland, Pólland, Suður-Kórea, Ástralía/Nýja-Sjáland, Japan, Spánn, Suður-Ameríka, Kanada, etc.

## Key Data: Stays (dvalarlengd-og-gistimati)

Report ID: `ae74ab2c-4b1a-4a5c-bf4f-a8ffdda1801f`

Tourist length of stay and accommodation type from Ferðamálastofa's border survey (landamærarannsókn).

### Metrics

| Metric | Icelandic | Description |
|--------|-----------|-------------|
| Meðalfjöldi gistinátta | Average guest nights | Monthly average nights stayed, 2024–2026 |
| Sundurliðun eftir bakgrunni | Breakdown by demographics | Average nights by age group (15–24, 25–34, ..., 65+) |
| Dvalarlengd | Length of stay distribution | % of tourists by stay duration (0, 1, 2–3, 4–5, 6–8, 9–12, 13+ days) |
| Sundurliðun eftir tegund gistingar | By accommodation type | Usage % and median stay by type |

### Accommodation Types (tegund gistingar)

| Icelandic | English | Category |
|-----------|---------|----------|
| Vinir/ættingjar, möbilhúsi… | Friends/family, motorhome | Ekki greitt fyrir náttuvöl |
| Tjaldstæði, ekki greitt f… | Campsite (unpaid) | Ekki greitt fyrir náttuvöl |
| Önnur gisting | Other accommodation | Ekki greitt fyrir náttuvöl |
| Hótel, gistiheimili | Hotel, guesthouse | Greitt fyrir náttuvöl |
| Ibúðagisting | Apartment rental (Airbnb etc.) | Greitt fyrir náttuvöl |
| Hostel | Hostel | Greitt fyrir náttuvöl |
| Tjald greitt fyri… | Campsite (paid) | Greitt fyrir náttuvöl |
| Húsbíll/tjaldv… | Campervan/motorhome | Greitt fyrir náttuvöl |
| Sumarhús eða skálar | Summer houses or huts | Greitt fyrir náttuvöl |
| Húsbíll greitt fyri… | Campervan (paid) | Greitt fyrir náttuvöl |

### Filters/Slicers

| Filter | Icelandic | Values |
|--------|-----------|--------|
| Bakgrunnsbreytur | Background variable | Aldur (age), Kyn (gender), etc. |
| Ár | Year | Multiple selections (2024, 2025, 2026) |
| Mánuður | Month | All, or specific months |

### Sample Output

```
age_group,avg_nights
15-24 ára,6.8
25-34 ára,7.0
35-44 ára,6.7
45-54 ára,6.8
55-64 ára,6.9
65 ára og eldri,7.2

stay_duration,pct
Gisti ekki,0.6%
1 dagur,2.7%
2-3 dagar,16.8%
4-5 dagar,25.2%
6-8 dagar,30.6%
9-12 dagar,16.0%
13 dagar eða meira,8.2%
```

## Extraction Method

Use Playwright to load the parent page and intercept Power BI `executeQueries` API calls:

```python
import asyncio
import json
from playwright.async_api import async_playwright

BASE_URL = "https://www.maelabordferdathjonustunnar.is"

async def scrape_passenger_data(page_path="/fjoldi-farthega-um-keflavik"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        query_results = []

        async def handle_response(response):
            url = response.url
            # Power BI data queries go through these endpoints
            if 'querydata' in url.lower() or 'public/reports' in url.lower():
                try:
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '')
                        if 'json' in content_type:
                            body = await response.json()
                            query_results.append({
                                'url': url,
                                'data': body
                            })
                except Exception:
                    pass

        page.on('response', handle_response)

        await page.goto(
            f"{BASE_URL}{page_path}",
            wait_until='networkidle',
            timeout=60000
        )
        # Power BI reports load async — wait for data queries
        await asyncio.sleep(10)

        await browser.close()
        return query_results
```

## Parsing Power BI Response

Power BI embedded reports use a compressed DSR (DataShapeResult) format:

```python
def parse_powerbi_results(results):
    """Extract tabular data from Power BI query results."""
    rows = []
    for result in results:
        data = result.get('data', {})
        if 'results' not in data:
            continue
        for res in data['results']:
            dsr = res.get('result', {}).get('data', {}).get('dsr', {})
            for ds in dsr.get('DS', []):
                for ph in ds.get('PH', []):
                    dm = ph.get('DM0', [])
                    # Value dictionaries for compressed references
                    value_dicts = dsr.get('ValueDicts', {})
                    for row in dm:
                        # G0, G1, ... = dimension values (nationality, month, etc.)
                        # C = compressed reference indices into ValueDicts
                        # X[n].M0 = measure values
                        # R = repeat flags (inherit from previous row)
                        rows.append(row)
    return rows


def decompress_dsr(dsr_data):
    """Decompress Power BI DSR format with ValueDicts and repeat flags.

    Power BI compresses data by:
    1. ValueDicts: shared string arrays referenced by index (C field)
    2. R (repeat): bitmask indicating which G values repeat from previous row
    3. Ø (null): marks null/missing values
    """
    value_dicts = dsr_data.get('ValueDicts', {})
    all_rows = []

    for ds in dsr_data.get('DS', []):
        for ph in ds.get('PH', []):
            dm = ph.get('DM0', [])
            prev_values = {}

            for row in dm:
                current = {}
                repeat_mask = row.get('R', 0)

                # Resolve G (group/dimension) values
                for i in range(10):  # G0..G9
                    key = f'G{i}'
                    if key in row:
                        current[key] = row[key]
                        prev_values[key] = row[key]
                    elif repeat_mask & (1 << i) and key in prev_values:
                        current[key] = prev_values[key]

                # Resolve C (compressed dict reference) values
                if 'C' in row:
                    for idx, val in enumerate(row['C']):
                        dict_key = f'D{idx}'
                        if dict_key in value_dicts and isinstance(val, int):
                            current[f'C{idx}'] = value_dicts[dict_key][val]
                        else:
                            current[f'C{idx}'] = val

                # Extract X (measure) values
                x_data = row.get('X', [])
                for xi, x in enumerate(x_data):
                    if isinstance(x, dict):
                        for mk, mv in x.items():
                            current[f'X{xi}_{mk}'] = mv

                all_rows.append(current)

    return all_rows
```

## Switching Report Tabs via Interaction

The dashboard has multiple tabs (Fjöldi, Yfirlit, Árstíðardreifing). To load data from different tabs, click the tab buttons:

```python
async def click_tab(page, tab_name):
    """Click a Power BI report tab within the iframe."""
    # Find the Power BI iframe
    iframe_element = await page.query_selector('iframe[src*="ferdapbi"]')
    if not iframe_element:
        return
    frame = await iframe_element.content_frame()
    if not frame:
        return

    # Click the tab button by text
    button = await frame.query_selector(f'button:has-text("{tab_name}")')
    if button:
        await button.click()
        await asyncio.sleep(5)  # Wait for new data to load
```

## Changing Filters (Year/Month)

To scrape different time periods, interact with the Power BI slicers:

```python
async def set_year_filter(frame, year):
    """Change the Ár (year) slicer in the Power BI report."""
    # Find and click the year dropdown
    year_slicer = await frame.query_selector('[aria-label*="Ár"]')
    if year_slicer:
        await year_slicer.click()
        await asyncio.sleep(1)
        option = await frame.query_selector(f'[title="{year}"]')
        if option:
            await option.click()
            await asyncio.sleep(3)
```

## Sample Output

```
month,year,nationality,passengers,yoy_change,yoy_pct
2026-01,2026,Ísland,43809,-3611,-8%
2026-01,2026,Bandaríkin,24069,-9066,-27%
2026-01,2026,Bretland,20973,+2244,+12%
2026-01,2026,Kína,8908,-764,-8%
2026-01,2026,Ítalía,7555,+5262,+229%
2026-01,2026,Þýskaland,6626,-1260,-16%
2026-01,2026,Frakkland,5803,-115,-2%
2026-01,2026,Pólland,3860,+654,+20%
2026-01,2026,Suður-Kórea,2921,+1304,+81%
2026-01,2026,Ástralía/Nýja-Sjáland,2751,+127,+5%
```

## Data Caveats

1. **Embed token auth:** The parent page (`maelabordferdathjonustunnar.is`) fetches a Power BI embed token from `ferdapbi.azurewebsites.net`. Direct Power BI API calls require this token.
2. **Rate limiting:** Don't scrape too frequently — the embed tokens have limited validity.
3. **DSR compression:** Power BI uses a compressed format with `ValueDicts`, `R` (repeat) flags, and `C` (compressed references). Must decompress before use.
4. **Icelandic number format:** Uses dots as thousands separators (163.175 = 163,175).
5. **Monthly updates:** Data is updated monthly after Isavia publishes new figures.
6. **Historical data:** Available from ~2016 onward via year slicer.

## Alternative Sources

- **Hagstofan:** Has some tourism statistics but less granular nationality breakdown
  - SAM01601: Passengers through Keflavík by nationality (annual)
- **Isavia:** Source of the raw data, publishes monthly press releases
- **UNWTO:** International comparison data

## Save Output

```bash
mkdir -p data/processed/ferdamalastofa
# After extraction:
# data/processed/ferdamalastofa/passengers_by_nationality.csv
# data/processed/ferdamalastofa/monthly_totals.csv
# data/processed/ferdamalastofa/stays_by_duration.csv
# data/processed/ferdamalastofa/stays_by_accommodation.csv
# data/processed/ferdamalastofa/hotel_occupancy.csv
```

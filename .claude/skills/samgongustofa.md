# Samgöngustofa (Iceland Transport Authority)

Vehicle registration statistics via Power BI dashboard scraping.

## Data Source

**Dashboard URL:** `https://bifreidatolur.samgongustofa.is/`

The dashboard is a Power BI embedded report. Data must be extracted by intercepting API calls.

## Available Data

| Dataset | Description |
|---------|-------------|
| Vehicle makes | All registered vehicles by make (TOYOTA, VW, etc.) |
| Fuel types | Vehicles by fuel type (Bensín, Dísel, Rafmagn, etc.) |
| Locations | Registrations by municipality with coordinates |
| Vehicle types | M1 (passenger), N1 (van), etc. |
| New vs used | New registrations vs imports |

## Extraction Method

Use Playwright to intercept Power BI query responses:

```python
import asyncio
from playwright.async_api import async_playwright
import json

async def scrape_vehicle_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        query_results = []

        async def handle_response(response):
            url = response.url
            if 'querydata' in url.lower() or 'executeQueries' in url.lower():
                try:
                    if response.status == 200:
                        body = await response.json()
                        query_results.append(body)
                except:
                    pass

        page.on('response', handle_response)

        await page.goto('https://bifreidatolur.samgongustofa.is/',
                       wait_until='networkidle', timeout=60000)
        await asyncio.sleep(8)  # Wait for all queries to complete

        await browser.close()
        return query_results
```

## Parsing Power BI Response

Power BI returns data in a nested structure:

```python
def parse_powerbi_data(results):
    """Extract tabular data from Power BI query results."""
    for result in results:
        if 'results' not in result:
            continue
        for res in result['results']:
            dsr = res.get('result', {}).get('data', {}).get('dsr', {})
            for ds in dsr.get('DS', []):
                for ph in ds.get('PH', []):
                    dm = ph.get('DM0', [])
                    for row in dm:
                        # G0 = dimension value (e.g., make name)
                        # X[0].M0 = first measure (e.g., registered count)
                        # X[1].M0 = second measure (e.g., new registrations)
                        make = row.get('G0', '')
                        x_data = row.get('X', [{}])
                        registered = x_data[0].get('M0', 0) if x_data else 0
                        new_reg = x_data[1].get('M0', 0) if len(x_data) > 1 else 0
                        yield {'make': make, 'registered': registered, 'new': new_reg}
```

## Sample Output

```
TOYOTA               |       52,065 |      8,947
VOLKSWAGEN, VW       |       19,683 |      4,302
KIA                  |       21,390 |      1,434
TESLA                |        9,241 |         62
BYD                  |          853 |          3
XPENG                |          352 |          2
```

## Known Chinese Brands in Iceland

| Brand | Owner | Status |
|-------|-------|--------|
| MG | SAIC (China) | Largest Chinese brand |
| Polestar | Geely (China) | Swedish-Chinese |
| BYD | BYD | Growing |
| XPENG | XPENG | New 2024 |
| Maxus | SAIC (China) | Commercial vehicles |
| Aiways | Aiways | Small presence |

## Data Caveats

1. **Real-time data:** Dashboard shows current state, no historical snapshots
2. **Rate limiting:** Don't scrape too frequently
3. **Structure changes:** Power BI report structure may change
4. **Navigation required:** Different tabs may require clicks to load additional data

## Alternative Sources

- **Hagstofan:** Has vehicle counts by fuel type but NOT by make
  - Path: `Umhverfi/5_samgongur/3_okutaekiogvegir/1_okutaeki/SAM30120.px`
- **Creditinfo API:** Commercial access to vehicle registry
- **Bílgreinasambandið:** Industry association statistics

## Evidence Integration

Save extracted data to `/data/processed/samgongustofa/`:

```sql
-- sources/samgongustofa/vehicles_by_make.sql
SELECT * FROM read_csv('/Users/jokull/Code/hagstofan/data/processed/samgongustofa/vehicles_by_make.csv')
```

# Mælaborð landbúnaðarins (Agriculture Dashboard)

Agricultural production, subsidies, and market data via Power BI dashboards on the Ministry of Agriculture website.

## Data Source

**Landing page:** `https://www.stjornarradid.is/verkefni/atvinnuvegir/landbunadur/maelabord-landbunadarins-/`

Launched February 2021 as a COVID-era transparency initiative. Three Power BI reports are embedded as iframes on the page, each covering a different domain. Data comes from the ministry's internal systems (Afurð, Bústaðir) and Statistics Iceland (imports/exports).

**Concepts/definitions PDF:** `https://www.stjornarradid.is/library/01--Frettatengt---myndir-og-skrar/ANR/MAelabord/Hugtök%20og%20skýringar-3.pdf`

**Contact:** `maelabord@anr.is`

## Power BI Reports

All three reports share tenant ID `f1025c1c-31ee-4240-bc30-d3addbf6d912`.

### Report 1: Búvörusamningar (Agricultural Subsidies)

**Tab:** Tab2 on the landing page
**Report key:** `261d87b4-d3c2-43a4-86e9-b8daf6183d49`
**Page:** `ReportSectiond8e11973307bd0229b14`

```
https://app.powerbi.com/view?r=eyJrIjoiMjYxZDg3YjQtZDNjMi00M2E0LTg2ZTktYjhkYWY2MTgzZDQ5IiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9&pageName=ReportSectiond8e11973307bd0229b14
```

| Dataset | Description |
|---------|-------------|
| Beingreiðslur | Direct payments to farmers (sheep, cattle, horticulture) |
| Fjárfestingastuðningur | Investment support for buildings, equipment, animal welfare |
| Nýliðunarstuðningur | New farmer support, generational transfers |
| Býlisstuðningur | Settlement support for family sheep farms |
| Svæðisbundinn stuðningur | Regional support for sheep-dependent areas |
| Gripagreiðslur | Per-cow payments from cattle agreement |
| Gæðastýring í sauðfé | Quality management payments for lamb |
| Jarðræktarstyrkur | Land cultivation support (hay, grain, outdoor vegetables) |
| Landgreiðslur | Payments for cultivated fodder land |
| Kynbótafé | Breeding support for livestock and plants |
| Framleiðslujafnvægi | Market balance measures (slaughter subsidies etc.) |
| Aðlögun að lífrænni ræktun | Organic farming transition support |

**Filterable by:** subsidy type, region, manager gender, individual farm.

### Report 2: Búvörumarkaður (Agricultural Market)

**Tab:** Tab4 on the landing page
**Report key:** `f4106b7d-35d3-4049-9f21-8b2f01dacd7d`

```
https://app.powerbi.com/view?r=eyJrIjoiZjQxMDZiN2QtMzVkMy00MDQ5LTlmMjEtOGIyZjAxZGFjZDdkIiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9
```

| Dataset | Description |
|---------|-------------|
| Meat production | By species (lamb, beef, pork, poultry, horse), age, sex |
| Meat sales | Domestic sales by product category |
| Meat inventory | Stock levels at year-end |
| Meat imports/exports | Volumes with bone-ratio adjustment option |
| Vegetable production | Greenhouse and field crops |
| Kjötmatsflokkur | Carcass grading classes (e.g. DU3, UN O2) |

**Key concept — Beinahlutfall (bone ratio):** Imported meat is mostly boneless. Domestic production is recorded as whole carcasses. The dashboard offers a toggle to view import volumes as-if with bone for fair comparison.

### Report 3: Bændur og búalið (Farmers & Livestock)

**Tab:** Tab3 on the landing page
**Report key:** `f8a8abac-d09b-49dc-a759-b043dbd0fa94`
**Page:** `ReportSection82cdd47287932a358e24`

```
https://app.powerbi.com/view?r=eyJrIjoiZjhhOGFiYWMtZDA5Yi00OWRjLWE3NTktYjA0M2RiZDBmYTk0IiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9&pageName=ReportSection82cdd47287932a358e24
```

| Dataset | Description |
|---------|-------------|
| Farm counts | Number of farms from 1981 onward |
| Regional distribution | Farms by landshluti (region) |
| Livestock by type | Sheep, cattle, horses, poultry, pigs |
| Manager demographics | Gender breakdown of farm managers |

## Underlying Data Systems

| System | Owner | Content |
|--------|-------|---------|
| Afurð | Ministry of Agriculture | Subsidy records, meat processing data, farm counts |
| Bústaðir | Ministry of Agriculture | Livestock registry |
| Hagstofa Íslands | Statistics Iceland | Import/export statistics for meat products |

## Key Terminology

| Term | Translation | Notes |
|------|-------------|-------|
| Búvörusamningar | Agricultural product agreements | 4 contracts: garðyrkja, sauðfjárrækt, nautgriparækt, rammasamningur |
| Beingreiðslur | Direct payments | Paid per volume (vegetables) or per greiðslumark (dairy/sheep) |
| Greiðslumark | Payment quota | Measured in litres (dairy) or ærgildi (sheep) — tradeable |
| Ærgildi | Ewe equivalents | Unit for sheep payment quota |
| Kjötmatsflokkur | Carcass grading class | e.g. DU3, UN O2 — determines price |
| Afurðaflokkur | Product category | e.g. kindakjöt covers both adult sheep and lamb |
| Beinahlutfall | Bone ratio | Adjustment factor for comparing boneless imports to whole carcass domestic production |

## Locating farms: búsnúmer → landsnúmer

The farm identifier rendered on the "Eftir búi" page is an **8-digit búsnúmer** (the dashboard usually shows it without its leading zero, so you see 7 digits in the UI). **Drop the last digit** to get the **7-digit landsnúmer**.

```
búsnúmer  12345678        →   integer(busnr) // 10
landsnúmer 1234567       ←   landsnúmer (may also have a leading zero)
```

Once you have the landsnúmer, two registries resolve it to coordinates:

| Source | Coverage | Geometry | When to use |
|--------|----------|----------|-------------|
| **iceaddr / Staðfangaskrá** (bundled SQLite, [iceaddr](iceaddr.md)) | ~138k landnúmer incl. historical farms | Point (lat/lon) | Default. ~100% hit rate for farm búsnúmer. |
| **HMS Landeignaskrá** (shapefile, [hms](hms.md#landeignaskrá-land-parcel-registry)) | ~89k formally surveyed parcels, only ~3.4k JÖRÐ | Polygon | When you need parcel boundaries, not just a point. Many farm búsnúmer miss here. |

Worked example — top cattle-subsidy recipient 2026 is búsnúmer `16656491` (Gunnbjarnarholt 2):

```python
landsnr = 16656491 // 10   # 1665649 → dropped the last digit
# Look up in iceaddr:
from iceaddr import iceaddr_lookup  # or direct SQLite SELECT on stadfong.landnr
# Returns lat 64.10, lon -20.52 — Skeiða- og Gnúpverjahreppur.
```

See `scripts/maelabord_nautgripa.py` + `scripts/nautgripa_map.py` for a concrete end-to-end scrape → geocode → map pipeline for the Nautgriparæktarsamningur recipients.

## Extraction Method

Use Playwright to intercept Power BI query responses (same pattern as samgongustofa/ferdamalastofa):

```python
import asyncio
from playwright.async_api import async_playwright
import json

REPORTS = {
    "buvorusamningar": "https://app.powerbi.com/view?r=eyJrIjoiMjYxZDg3YjQtZDNjMi00M2E0LTg2ZTktYjhkYWY2MTgzZDQ5IiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9&pageName=ReportSectiond8e11973307bd0229b14",
    "buvorumarkadur": "https://app.powerbi.com/view?r=eyJrIjoiZjQxMDZiN2QtMzVkMy00MDQ5LTlmMjEtOGIyZjAxZGFjZDdkIiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9",
    "baendur_og_bualid": "https://app.powerbi.com/view?r=eyJrIjoiZjhhOGFiYWMtZDA5Yi00OWRjLWE3NTktYjA0M2RiZDBmYTk0IiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9&pageName=ReportSection82cdd47287932a358e24",
}

async def scrape_report(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        query_results = []

        async def handle_response(response):
            if 'querydata' in response.url.lower() or 'executeQueries' in response.url.lower():
                try:
                    if response.status == 200:
                        body = await response.json()
                        query_results.append(body)
                except:
                    pass

        page.on('response', handle_response)
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(10)

        await browser.close()
        return query_results
```

These are public embed URLs (`/view?r=...`) — no authentication or embed token needed. Navigate directly to the Power BI URL, not the ministry landing page.

## Data Caveats

1. **No direct API:** Data must be scraped from Power BI — no REST API or CSV downloads available
2. **Structure changes:** Power BI report structure may change without notice
3. **Rate limiting:** Don't scrape too frequently
4. **Overlaps with Hagstofa:** Meat production and livestock data also available from Hagstofa tables LAN10201 and LAN10103 (possibly more up-to-date or with different breakdowns here)
5. **Subsidy data is unique:** The búvörusamningar data (farm-level subsidies by type and region) is not available from any other public source
6. **Best on desktop:** Dashboard designed for desktop/tablet viewing
7. **Encoding.** Power BI returns UTF-8 throughout. Farm names, búsnúmer labels, and subsidy categories all contain Icelandic chars (þ, ð, æ, ö); `nautgripa_recipients.csv` is written with `encoding="utf-8"`. The matching `iceaddr` lookup also returns Icelandic strings — handle accordingly.

## Complementary Sources

| Source | Skill | Overlap |
|--------|-------|---------|
| Hagstofa LAN10201 | [hagstofan](hagstofan.md) | Meat production by species, 1983–present (annual) |
| Hagstofa LAN10103 | [hagstofan](hagstofan.md) | Harvest & products, 1977–present (annual) |
| Hagstofa LAN10102 | [hagstofan](hagstofan.md) | Livestock by region, 1980–present |

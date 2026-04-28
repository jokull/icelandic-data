# Landlæknir — Directorate of Health (Embætti landlæknis)

Health statistics for Iceland: mortality, medication use, healthcare services, workforce, infectious disease surveillance, and public health indicators. Primary portal is **Mælaborð embættis landlæknis** (~30 Power BI dashboards); secondary is **Talnabrunnur**, a PDF newsletter series (2007–present).

Listed by the Hagtalnanefnd report (March 2026) as one of four other European-statistics producers for Iceland (alongside Seðlabanki, Ríkislögreglustjóri, Samgöngustofa). Produces European health statistics under regulation (EC) No 1338/2008.

## Landing pages

| Portal | URL | Format |
|--------|-----|--------|
| Mælaborð (dashboard index) | `https://island.is/maelabord` | HTML index → Power BI embeds |
| Talnabrunnur (newsletter archive) | `https://island.is/talnabrunnur` | PDF index, 2007–present |
| Tölfræði og rannsóknir (hub) | `https://island.is/tolfraedi-og-rannsoknir` | HTML |

Note: `landlaeknir.is/*` URLs now 301-redirect to `island.is/*`. Use the `island.is` canonical form.

## Mælaborð catalog (~30 dashboards, all Power BI)

All share tenant ID `4d762ac0-6205-42ce-b964-c3b8958fd4a9`. Embed URL form:
`https://app.powerbi.com/view?r=<base64-encoded {"k":report_key,"t":tenant,"c":8}>`

### Lýðheilsa (Public Health)

| Name | Report key | Subject |
|------|-----------|---------|
| Lýðheilsuvaktin | `e96fb72e-64c7-40b9-b413-9880b6d3ebb6` | Monitoring of selected health determinants |
| Lýðheilsuvísar | `b844ee2b-a5ac-47e3-8c32-fd4c9260a7b3` | Public health indicators by region |
| Reykingar | `8a8c91a6-8baa-4a92-91f7-c8bbb09a61cf` | Smoking habits by gender and age |

### Lyfjanotkun (Medication Usage)

| Name | Report key | Subject |
|------|-----------|---------|
| Lyfjanotkun | `91dbfdc1-b502-412d-b5b9-ed9195d13cc5` | All drug prescriptions by ATC, gender, age |
| ADHD-lyfja | `5964b5b1-e090-4295-876a-16d7818f5d89` | ADHD medication |
| Þunglyndislyfja | `da30ebd3-fdb3-4f61-85b2-c0eaf2475816` | Antidepressants |
| Ópíóíða | `7de4f8d0-1d91-4e36-9ada-d708069663be` | Opioids |
| Svefnlyfja og slævandi lyfja | `4c04de98-4ba9-499e-9de2-28e1169ca81f` | Sleep & sedatives |
| Sýklalyfja | `8ab229cd-6dc2-41b5-b472-b2e9bd62dcdf` | Antibiotics (outpatient) |

### Dánarorsakir (Mortality)

| Name | Report key | Subject |
|------|-----------|---------|
| Mortis | `9762f31f-75d5-44a0-84f4-2748ada887a5` | Mortality by cause, gender, age |
| Umframdánartíðni | `8434975c-221d-4cf8-be41-b3a018a341c8` | Excess mortality by period |
| Sjálfsvíg | `7099a77d-3bcb-4ecc-b3ad-555816b6d199` | Suicide by gender and age |
| Lyfjatengd andlát | `4b1b3b1f-627a-4b65-9088-35a5be7a0d80` | Drug-related deaths |

### Heilbrigðisstarfsfólk (Healthcare Workforce)

| Name | Report key | Subject |
|------|-----------|---------|
| Mannafli í heilbrigðisþjónustu | `100a2e7c-8e70-4f4d-8931-3a18f7743b54` | Workforce counts, specialty |

### Heilbrigðisþjónusta (Healthcare Services)

| Name | Report key | Subject |
|------|-----------|---------|
| Lykilvísar heilbrigðisþjónustu | `3c7aff7a-d011-49c0-999b-42e8572b333d` | Key indicators + Nordic comparison |
| Starfsemi sjúkrahúsa | `d397920c-ceeb-461e-8e5a-31637e0dfe2e` | Hospital admissions, length of stay |
| Samskipti við heilsugæslu | `aaa2dbb1-509c-4440-a487-9f9b17f74d04` | Primary care contacts |
| Skimun fyrir krabbameini | `695fcc55-c9cf-48f9-8dea-05114188eacd` | Cancer screening participation |
| Bið eftir skurðaðgerðum | `de0dd7d1-f6e8-4952-9dad-12f6d011338a` | Surgery waitlists |
| Liðskiptaaðgerðir | `66d4f15b-d403-41fb-9f46-11643f02f9ee` | Joint replacement procedures |
| Bið eftir hjúkrunarrými | `f78159f5-1187-49eb-9b21-c3240b96659c` | Nursing-home waitlists |
| Gæði þjónustu á hjúkrunarheimilum | `7280e4c3-e418-45e7-8109-c52c9da328f7` | InterRAI quality indicators |
| Tannheilsa barna | `9b56cbba-0997-47cb-819d-c4ad88c09083` | Children's dental health |
| Alvarleg atvik | `288bcc93-e451-4227-855e-f517c45d8523` | Serious healthcare incidents |
| Kvartanir | `6437ece5-4086-430e-9a6c-25e92c3f0cfd` | Patient complaints |
| Rekstur heilbrigðisþjónustu | `2b14022e-6e9a-4f31-a2e2-1ba08b7b9775` | Service operation notifications |
| DRG mælaborð | `7da1376f-51a7-4129-83dd-47e1d68ad45b` | Diagnosis-related groups (hospital costs) |
| ACG mælaborð | `f95fc235-5913-45a9-bd1a-c052c3f465b1` | Adjusted Clinical Groups (disease burden) |

### Sóttvarnir (Infectious Disease Control)

| Name | Report key | Subject |
|------|-----------|---------|
| Árlegur fjöldi smitsjúkdóma | `cd829644-4051-4a71-9571-e0ed60157d3b` | Annual notifiable disease counts |
| Lekandi, klamydía og sárasótt | `53f7eba1-f7bf-42dd-acad-9b4fa068cbd2` | STI diagnoses |
| Öndunarfærasýkingar | `f829b4c8-63dd-4cd3-9e37-1b1101e8e02d` | COVID-19, influenza, RSV surveillance |
| Veirugreiningar | `656ffb3f-8a7f-4746-b921-4f6e364754ce` | Lab viral diagnostics |
| Þátttaka í bólusetningum barna | `608e169f-867c-4b00-9224-925e92b6a247` | Child vaccination uptake |

## Embed-URL reconstruction

```python
import base64, json
TENANT = "4d762ac0-6205-42ce-b964-c3b8958fd4a9"
def embed_url(report_key: str) -> str:
    payload = {"k": report_key, "t": TENANT, "c": 8}
    token = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"https://app.powerbi.com/view?r={token}"
```

## Extraction method

Same Playwright-intercept pattern as [ferdamalastofa](ferdamalastofa.md), [samgongustofa](samgongustofa.md), and [maelabord_landbunadarins](maelabord_landbunadarins.md):

```python
import asyncio
from playwright.async_api import async_playwright

async def scrape_report(url: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        results = []
        async def on_response(r):
            if "querydata" in r.url.lower() or "executeQueries" in r.url.lower():
                if r.status == 200:
                    try:
                        results.append(await r.json())
                    except Exception:
                        pass
        page.on("response", on_response)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(10)
        await browser.close()
        return results
```

These are public `/view?r=...` URLs — no auth or embed-token refresh needed.

## Talnabrunnur (newsletter archive)

PDF index at `https://island.is/talnabrunnur`. Each issue is one PDF, 2007–present, usually covering one or two topics in detail. No API. Useful as **context** for dashboards (methodology, definitions, caveats) rather than as a data source.

## Script Usage

```bash
# Enumerate all dashboards (prints the catalog)
uv run python scripts/landlaeknir.py list

# Scrape one dashboard by slug (saves Power BI query responses to data/raw/landlaeknir/)
uv run python scripts/landlaeknir.py fetch --slug mortis
uv run python scripts/landlaeknir.py fetch --slug syklalyfja

# Scrape all dashboards (slow — ~30 × ~15s each)
uv run python scripts/landlaeknir.py fetch --all
```

## Data Files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/landlaeknir/{slug}.json` | JSON | Raw Power BI `executeQueries` responses for one dashboard |
| `data/processed/landlaeknir_catalog.csv` | CSV | Catalog of slugs, names, report keys, categories (from `list`) |

## Caveats

1. **Power BI structure is volatile.** Query response shape can change without notice. Do not hard-code column indices — inspect the `descriptor.Select` array per response.
2. **Suppression on small counts.** Dánarorsakir, Sjálfsvíg, Lyfjatengd andlát suppress cells where N is below a privacy threshold (typically ≤4 people). Treat missing cells as "suppressed", not zero.
3. **Excess mortality uses a rolling baseline.** The Umframdánartíðni baseline changes as new years shift in. Snapshot the response JSON, not just the delta, to preserve comparability.
4. **Nordic-comparison tables lag.** Lykilvísar heilbrigðisþjónustu compares against NOMESCO data which updates annually with a ~2-year lag.
5. **Antibiotic data excludes inpatients.** Sýklalyfja covers outpatient prescriptions only. Hospital antibiotic use is in a separate (non-public) dataset.
6. **Overlaps with Hagstofa for mortality.** Hagstofa publishes cause-of-death and life-expectancy series from the same underlying dánarmeinaskrá. Mortis has higher temporal granularity; Hagstofa has cleaner methodology docs.
7. **URL 301 redirect.** `www.landlaeknir.is/*` → `island.is/*`. Use the latter directly.
8. **Talnabrunnur is PDFs only** — no structured data, no API.
9. **Encoding.** Power BI responses are UTF-8 throughout (Icelandic chars þ, ð, æ, ö, í, ó, ú in dimension labels and ATC drug names). Write JSON with `ensure_ascii=False` and read with `encoding="utf-8"`.

## Complementary sources

| Source | Overlap |
|--------|---------|
| [hagstofan](hagstofan.md) | Cause of death (HEI02000), life expectancy, health status survey |
| [loftgaedi](loftgaedi.md) | Air-quality → respiratory health link |
| Eurostat (external) | Regulation 1338/2008 health stats (Landlæknir submits these) |
| OECD Health Statistics (external) | Nordic/OECD benchmarks used on Lykilvísar |

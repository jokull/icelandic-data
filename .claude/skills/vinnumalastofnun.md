# Vinnumálastofnun — Directorate of Labour (VMST)

Unemployment, job vacancies, and work-permit statistics. Monthly data with a rolling multi-year window. The Hagtalnanefnd report (March 2026) explicitly cites VMST's *mælaborð, Excel and PDF* triple-publication pattern.

## Landing page

`https://island.is/s/vinnumalastofnun/maelabord-og-toelulegar-upplysingar`

(Note: `vmst.is/*` → `island.is/redirects/vmst.is/*` 301 redirect.)

## Data sources

### 1. Power BI — "Gagnvirk tölfræði Vinnumálastofnunar"

Interactive dashboard, filterable by region, industry, gender, month, year.

| Property | Value |
|----------|-------|
| Tenant | `764a306d-0a68-45ad-9f07-6f1804447cd4` |
| Report key | `e74521bb-e501-4b02-8aa2-08a8bb84d087` |
| Default page | `ReportSection7e7dca64570c18a74eb9` |
| Embed URL | `https://app.powerbi.com/view?r=<base64>` — see `scripts/vinnumalastofnun.py` |

Scrape with the Playwright-intercept pattern (same as `landlaeknir`, `ferdamalastofa`, `maelabord_landbunadarins`).

### 2. Excel — "Helstu talnagögn um atvinnuleysi"

```
https://assets.ctfassets.net/8k0h54kbe6bj/688FRtXuoA4qkPXerKcuMT/e6b9794d1bdfcf5cb5747a46b9b3d836/Talnagogn_atvinnuleysi.xlsm
```

Monthly unemployment time-series workbook. Updated when monthly reports are published (typically second week of the following month). Direct download via httpx — no auth, no scraping.

### 3. Mánaðarskýrslur (Monthly PDF reports)

Listed on the landing page as a filtered "frétta" view. Each report is a PDF with narrative commentary + summary tables. Used alongside the Excel for context.

## Key series

- **Skráð atvinnuleysi** — registered unemployment rate (monthly, %).
- **Fjöldi í atvinnuleit** — job-seeker counts by gender, age, region, industry, duration.
- **Atvinnuleyfi til erlendra ríkisborgara** — work permits issued (law-mandated annual report).
- **Mannaflaþörf** — labor demand by occupation (annual, law-mandated).

## Script usage

```bash
# Fetch the Excel workbook + save a copy of the Power BI query responses
uv run python scripts/vinnumalastofnun.py fetch

# Just download the Excel
uv run python scripts/vinnumalastofnun.py excel

# Scrape Power BI only
uv run python scripts/vinnumalastofnun.py powerbi
```

## Data files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/vinnumalastofnun/Talnagogn_atvinnuleysi.xlsm` | Excel | Monthly headline series |
| `data/raw/vinnumalastofnun/powerbi.json` | JSON | Raw Power BI `executeQueries` responses |

## Caveats

1. **Registered ≠ ILO unemployment.** VMST reports *registered* unemployment (people claiming benefits / actively signing on). Hagstofan publishes the ILO-harmonized labour-force-survey rate (vinnumarkaðsrannsókn), which is typically higher and behaves differently over the cycle. Do not compare headlines across the two.
2. **Self-employed invisible.** Self-employed workers are not typically in VMST's registry. Hagstofa captures them.
3. **Revision pattern.** Historical months in the Excel occasionally revise when late registrations are reconciled — keep snapshots, don't assume immutability.
4. **No published API.** The Power BI dashboard has no stable query endpoint; scrape responses and re-extract from the JSON descriptor each run.
5. **Excel is `.xlsm`.** Contains macros. Open with `openpyxl` / `polars` read_excel — do not execute macros.
6. **Encoding.** Icelandic chars (þ, ð, æ, ö) in column headers — ensure UTF-8 all the way through.

## Complementary sources

| Source | Overlap |
|--------|---------|
| [hagstofan](hagstofan.md) | ILO unemployment via labour-force survey (VIN01101, VIN01000) |
| [opnirreikningar](opnirreikningar.md) | VMST benefit payments appear in government invoice data |

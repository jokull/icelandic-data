# Farsæld barna — Child Wellbeing Dashboard

Statistical indicators on child wellbeing in Iceland: health, happiness, education, safety, opportunities, living standards, social relationships, family life, participation, and influence on decisions.

Run by **Barna- og fjölskyldustofa (BOFS)**, operational since 1 January 2022 (merged from Barnaverndarstofa). Explicitly named in the Hagtalnanefnd report (March 2026, footnote 71) as an example of a dashboard where raw data is not made available — only the dashboard and reports.

## Landing page

`https://farsaeldbarna.is/` — consolidates statistical data underpinning the Farsældarlögin (Child Wellbeing Act, enacted 2022).

## Power BI dashboard

| Property | Value |
|----------|-------|
| Tenant | `bc14a44e-e0fb-4e0b-a535-100579d41b65` |
| Report key | `1fcb76a3-b53d-4ba1-a5c9-434d8c346408` |
| Embed URL | `https://app.powerbi.com/view?r=<base64>` — see `scripts/farsaeld_barna.py` |

Organized around five "foundations" of wellbeing (implementation framework from Farsældarlögin). Specific indicators not listed on the landing page — enumerate them from scraped Power BI descriptors.

## Extraction

Playwright-intercept pattern, but **note**: this dashboard is a "publish to web" Power BI with **static embedded data**, not live DAX queries. The data lives in the `modelsAndExploration` endpoint response (~2 MB JSON), not in `executeQueries`. The scraper captures: `modelsAndExploration`, `conceptualschema`, and `resourcePackage` blobs. No auth needed.

## Script usage

```bash
uv run python scripts/farsaeld_barna.py fetch
```

## Data files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/farsaeld_barna/powerbi.json` | JSON | Raw Power BI `executeQueries` responses |

## Caveats

1. **No raw data download.** The Hagtalnanefnd report flags this dashboard as one where grunngögn (raw data) are not made available to users — only the dashboard itself. Scraping the Power BI responses is the only route to structured data.
2. **Stale series warning.** Because the data aggregation is across many agency feeds (Hagstofa, HMS, Landlæknir, police, schools), individual indicators may lag the agency's own dashboard. Check the "last updated" text on each tile.
3. **Overlap with source datasets.** Many underlying series are already reachable more directly via [hagstofan](hagstofan.md), [landlaeknir](landlaeknir.md), or [reykjavik](reykjavik.md) (municipality-level welfare data). Prefer source when available.
4. **Attribution.** Data sourced from multiple public agencies — BOFS coordinates but does not own the underlying series.
5. **Encoding.** Power BI `modelsAndExploration` payload is UTF-8 throughout (Icelandic chars in dimension labels and indicator titles). Write JSON with `ensure_ascii=False` and read with `encoding="utf-8"`.

## Complementary sources

| Source | Overlap |
|--------|---------|
| [hagstofan](hagstofan.md) | Education, demographics, living conditions |
| [landlaeknir](landlaeknir.md) | Child health, vaccination, dental health |
| [reykjavik](reykjavik.md) | Municipal welfare services for children |
| [domstolar](domstolar.md) | Child-related court rulings |

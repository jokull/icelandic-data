# HMS - Húsnæðis- og mannvirkjastofnun

Property registry and housing market data from Iceland's Housing and Construction Authority.

## Data Sources

### Kaupskrá fasteigna (Property Purchase Registry)

**URL:** `https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com/n/frs3o1zldvgn/b/public_data_for_download/o/kaupskra.csv`

**Format:** CSV (semicolon delimited, ISO-8859-1 encoded)

**Update frequency:** Daily

**Coverage:** 2006-present, ~222k transactions

#### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| faerslunumer | int | Unique transaction ID |
| fastnum | str | Property number |
| heimilisfang | str | Address |
| postnr | int | Postal code |
| heinum | int | Location ID (7-digit, different from iceaddr hnitnum) |
| svfn | str | Municipality code |
| sveitarfelag | str | Municipality name |
| utgdag | date | Purchase agreement date |
| thinglystdags | timestamp | Registration date |
| kaupverd | int | Purchase price (**in thousands of ISK**) |
| fasteignamat | int | Property valuation at sale (thousands) |
| fasteignamat_gildandi | int | Current property valuation (thousands) |
| brunabotamat_gildandi | int | Fire insurance value (thousands) |
| byggar | int | Year built |
| einflm | float | Unit area (m²) |
| lod_flm | float | Lot area |
| fjherb | int | Number of rooms |
| tegund | str | Property type: Sérbýli, Fjölbýli, Sumarhús, Atvinnuhúsnæði, etc |
| fullbuid | bool | Whether property is complete |
| onothaefur_samningur | bool | Unusable for analysis (related party, multiple properties, etc) |

#### Caveats

- **Prices in thousands:** kaupverd=57000 means 57,000,000 ISK
- **heinum ≠ hnitnum:** Cannot join directly to iceaddr, use address+postnr instead
- **onothaefur_samningur:** Filter these for market analysis (related party sales, partial transfers)

## Geocoding with iceaddr

The `heinum` field does NOT match iceaddr's `hnitnum`. Join on parsed address components:

```sql
-- Parse address from kaupskra
TRIM(regexp_extract(HEIMILISFANG, '^([^0-9]+)', 1)) as street_name,
TRY_CAST(regexp_extract(HEIMILISFANG, '([0-9]+)', 1) AS INTEGER) as house_num,
upper(regexp_extract(HEIMILISFANG, '[0-9]+([a-zA-Z]?)$', 1)) as house_letter

-- Join to iceaddr.stadfong
ON lower(street_name) = lower(heiti_nf)
AND house_num = husnr
AND postnr = postnr
AND house_letter = COALESCE(upper(bokst), '')
```

**Match rate:** ~97%

## Processed Data

**Location:** `/data/processed/kaupskra_geocoded.parquet`

Includes all kaupskra fields plus:
- `lat`, `lng` - WGS84 coordinates from iceaddr
- `verd_per_m2` - Price per m² (in ISK, not thousands)

## Quick Queries

```bash
# Summary stats
duckdb -c "SELECT count(*), count(lat), median(kaupverd*1000/einflm_m2) FROM 'data/processed/kaupskra_geocoded.parquet' WHERE NOT onothaefur AND tegund='Fjölbýli'"

# Recent Reykjavík sales
duckdb -c "SELECT heimilisfang, kaupverd*1000 as kr, einflm_m2 FROM 'data/processed/kaupskra_geocoded.parquet' WHERE postnr BETWEEN 101 AND 128 AND kaupsamningur_dags >= '2024-01-01' ORDER BY kaupsamningur_dags DESC LIMIT 20"
```

## Landeignaskrá (Land Parcel Registry)

**Landing page** (Vercel-guarded, Icelandic): `https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/landeignaskrazip`
**Bulk ZIP** (Azure blob, no auth): `https://hmsstgsftpprodweu001.blob.core.windows.net/fasteignaskra/Landeignaskra.zip`
**Field descriptions PDF:** linked from the landing page as "Eigindalýsing".

~25 MB ZIP containing a single ESRI Shapefile (`LANDEIGNASKRA_AFHENDING.*`) with **89,050 parcels** in CRS **EPSG:3057** (ISN2016 Lambert). Script: `scripts/landeignaskra.py` (`download`, `extract`, `info`, `build`, `lookup`, `discover`).

### Schema

| Column | Meaning |
|--------|---------|
| `LANDE_NR` | **Landsnúmer** (parcel ID, 6–7 digit integer; keep leading zeros when expressing as 7-char) |
| `SVF_NR` | Municipality number |
| `GERD` | Type — `Lóð` (85,060 lots), `Jörð` (3,443 farms), `Þjóðlenda` (270 public) |
| `SKIKI_NR`, `SKIKI_AUDK` | Sub-parcel ID and share code (e.g. `"1/1"`, `"4/277"`) |
| `L_ST_SKRAD` / `L_ST_MAELD` | Registered vs. measured area |
| `DAGS_INN`, `DAGS_LEIDR` | Registration / last-correction dates |
| `GERD`, `ADFERD_INN`, `NAKVAEMNI`, `HEIMILD` | Provenance metadata |

The processed CSV (`data/processed/landeignaskra.csv`) adds `landsnr` (7-char zero-padded), `lon`, `lat` (WGS84 centroids).

### Encoding

The `.dbf` file is ISO-8859-1; `pyogrio` / `geopandas` will read it as Latin-1 and surface text as mojibake (`LÃ³Ã°` for `Lóð`). Either decode with `ISO-8859-1` explicitly or accept that the `GERD` / Icelandic text columns are cosmetic.

### Crosswalks from other registries

| Source ID | Length | Convert to landsnúmer |
|-----------|--------|-----------------------|
| **búsnúmer** (farm ID, Ministry of Agriculture — see [maelabord_landbunadarins](maelabord_landbunadarins.md)) | 8 digits (displayed as 7 after leading-zero strip) | `int(busnr) // 10` |

Example: búsnúmer `16656491` (Gunnbjarnarholt 2, top cattle recipient 2026) → landsnúmer `1665649`. **Caveat:** only ~3,443 of the 89k Landeignaskrá parcels are `GERD='Jörð'`; many active farm búsnúmer correspond to landnúmer that exist in **[iceaddr](iceaddr.md)**'s Staðfangaskrá (~138k landnúmer, including historical farms) but not yet in HMS's surveyed registry. For farm point-location, iceaddr is the practical primary source; Landeignaskrá gives you parcel polygons when you need them.

## Mælaborð íbúða í byggingu (Units Under Construction)

**Landing page:** `https://hms.is/gogn-og-maelabord/maelabord-ibuda-i-byggingu`
**Report page:** `https://hms.is/skyrslur/ibudir-i-byggingu`

Interactive dashboard + Iceland map showing every dwelling currently under construction, updated in real-time from HMS's building registry (byggingaskrá). Launched mid-2024. Used by municipalities, contractors, lenders, real-estate agents.

Most recent counts (March 2025): **7,181 units under construction**, 69.7% in the capital region.

**Scope:** Per-unit location, construction stage, municipality, project.

**Access:**
- Interactive dashboard (HTML + Leaflet map) on the landing page.
- Published reports (PDF) linked from `/skyrslur/ibudir-i-byggingu`.
- **No public API or raw data download** — the Hagtalnanefnd report (March 2026) specifically flags this as an example of HMS publishing "aðeins mælaborð eða skýrslur" (only dashboards and reports), with raw data not accessible under law 45/2018.

**Scraping notes:**
- `hms.is` is fronted by Vercel with an anti-bot checkpoint. `curl` and `httpx` get the "Vercel Security Checkpoint" HTML. Use Playwright (headless Chromium) to bypass.
- The dashboard fetches JSON from internal `/api/...` endpoints — inspect via DevTools Network tab while Playwright has the page loaded. Pattern similar to `landlaeknir` scraper but the source is custom (not Power BI).

**Complementary sources:**
- [hagstofan](hagstofan.md) table FAS01302 — completed dwellings by year (historical, not real-time).
- [skipulagsmal](skipulagsmal.md) — Planitor building-permit data (case-level, 5 municipalities).

## License

Open data, attribution required: "Byggir á upplýsingum frá Húsnæðis- og mannvirkjastofnun"

## Related

- [iceaddr](https://github.com/sveinbjornt/iceaddr) - Icelandic address geocoding
- [Kaupverðsjá](https://hms.is/gogn-og-maelabord/maelabordfasteignaskra/kaupverdsja) - HMS interactive price viewer

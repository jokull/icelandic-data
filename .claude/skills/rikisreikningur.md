# Ríkisreikningur — state accounts (Fjársýsla ríkisins)

Government-wide revenue, expenditure, and surplus/deficit from the state
treasury. `rikisreikningur.is` is the public disclosure portal operated by
**Fjársýsla ríkisins** (State Treasury / Financial Management Authority).

Published data:

- Annual state accounts (ríkisreikningur) back to 2004
- In-year monthly summaries (mánaðaryfirlit) for the current fiscal year
- "Heimamundur" — a detailed per-institution ledger published as XLSX
- A front-page dashboard of revenue/expense category and málefnasvið (policy-area) breakdown

## Architecture

React SPA at `rikisreikningur.is`. Data comes from a small Azure Functions
backend at `rikisreikningurapi.azurewebsites.net` with four JSON endpoints
plus a file-download endpoint. An **X-Api-Key** header is required — the key
is hard-coded in the public JS bundle and is effectively an anonymous
throttling key, not a secret.

### API

| Endpoint | Returns |
|----------|---------|
| `GET /api/FJS/NuverandiTimabil` | `{"ar": "2025", "timabil": "06"}` — latest closed period. `timabil` 01–12 = monthly, `13` = full-year accounts |
| `GET /api/FJS/TekjurOgGjold` | `{"afkoma":[…], "tekjur_gjold":[…]}` — yearly surplus/deficit + revenue/expense split into 7 categories (see below) |
| `GET /api/FJS/Data/malefni_tg` | Revenue & expense by **málefnasvið** (policy area 01–36) × year × type — ~620 rows |
| `GET /api/FJS/Data/skrar` | Manifest of downloadable Excel/CSV files (ríkisreikningur, heimamundur, forsidugogn) |
| `GET /api/Files/Rikisreikningur/{name}` | Raw file download (XLSX/CSV/PDF) |

Auth header: `X-Api-Key: 6d4d7394-2992-473d-9ea7-45946b39ad9d`

### Double-encoded payloads

The `/api/FJS/Data/*` endpoints return a **single-element list containing a
JSON-encoded string** that must be re-parsed:

```python
r = client.get("…/api/FJS/Data/malefni_tg")
outer = r.json()         # ["{\"malefni_tg\":[…]}"]
inner = json.loads(outer[0])  # {"malefni_tg": [{…}, {…}]}
rows  = inner["malefni_tg"]
```

`NuverandiTimabil` and `TekjurOgGjold` use normal single-layer JSON.

## Revenue/expense category schema

`tekjur_gjold` rows use two discriminators:

| `tegund` | `texti` | Meaning |
|----------|---------|---------|
| Tekjur | Skattar | Tax revenue |
| Tekjur | Sala | Sales of goods/services |
| Tekjur | Annað | Other revenue (grants, interest, etc.) |
| Gjöld | Laun | Wage expenditure |
| Gjöld | Tilfærslur | Transfer payments (welfare, grants) |
| Gjöld | Vörukaup | Purchases of goods/services |
| Gjöld | Annað | Other expenditure |

Each row carries `timabil_ar` (year), `timabil` (`13` = annual, `06` / `12` =
mid/full-year in-flight period), and `samtals` in ISK.

## Málefnasvið coverage

36 policy-area codes (01–37 with gaps), e.g.:

| Code | Málefnasvið (policy area) |
|------|---------------------------|
| 01 | Alþingi og eftirlitsstofnanir þess |
| 05 | Skatta-, eigna- og fjármálaumsýsla |
| 08 | Framhaldsskólastig |
| 18 | Menning, listir, íþrótta- og æskulýðsmál |
| 25 | Hjúkrunar- og endurhæfingarþjónusta |
| 34 | Almennur varasjóður og sértækar fjárráðstafanir |

Joined to revenue/expense sub-totals, this gives the "where does the money
go" breakdown at the level the parliament allocates appropriations.

## Usage

```bash
# Current fiscal period (quick health check)
uv run python scripts/rikisreikningur.py timabil

# Yearly afkoma + revenue/expense category CSVs
uv run python scripts/rikisreikningur.py summary

# Málefnasvið breakdown (620+ rows → CSV)
uv run python scripts/rikisreikningur.py malefni

# List the 35 published XLSX/CSV/PDF files
uv run python scripts/rikisreikningur.py files

# Download one (URL-encoding handled)
uv run python scripts/rikisreikningur.py download --name "Rikisreikningur_gogn_2024.csv"
```

## Processed outputs

| Path | Contents |
|------|----------|
| `data/processed/rikisreikningur_summary.csv` | `ar, tekjur, gjold, afkoma` (one row per year, values in ISK) |
| `data/processed/rikisreikningur_tekjur_gjold.csv` | revenue/expense sub-totals (category × year × period) |
| `data/processed/rikisreikningur_malefni.csv` | per-málefnasvið sub-totals |
| `data/processed/rikisreikningur_files.csv` | file manifest |
| `data/raw/rikisreikningur/{name}` | downloaded raw XLSX/CSV/PDF |

## Snapshot (2026-04 pull)

```
2015   rev=  732.9   exp=  693.8   net=  +39.2
2016   rev= 1215.2   exp=  759.8   net= +455.4   ← sale of stabilitetsframlag
2017   rev=  869.6   exp=  830.1   net=  +39.5
2018   rev=  972.0   exp=  887.6   net=  +84.4
2019   rev=  976.2   exp=  924.4   net=  +51.8
2020   rev=  906.5   exp= 1026.7   net= -120.2   ← COVID
2021   rev= 1014.3   exp= 1144.1   net= -129.8
2022   rev= 1095.6   exp= 1255.7   net= -160.1
2023   rev= 1080.8   exp= 1216.8   net= -136.0
2024   rev= 1125.9   exp= 1244.8   net= -118.9
2025   rev=  681.5   exp=  830.1   net= -148.7   ← YTD through timabil 06
```

All figures in ISK billions.

## Caveats

1. **API key rotates rarely but can rotate.** If the API starts returning 401,
   re-extract from the SPA bundle — grep the current `main.*.chunk.js` for
   a UUID assigned to a short variable name, currently `Ee = "6d4d…"`.
2. **Year 2015 starts the series.** Pre-2015 data is only available via the
   XLSX bundles in `files` (e.g. `Heimamundur gögn fyrir 2004–2016.xlsx` —
   70 MB).
3. **Mid-year totals are partial.** `timabil_ar=2025, timabil=06` is the
   first half of 2025 closed; do not compare it to full-year rows (`13`).
   The `summary` command preserves both; you need to filter by `timabil`.
4. **The 2016 surplus is an outlier.** The +ISK 455 B number comes from the
   one-off realisation of stability-contribution revenue from failed-bank
   estates (`stöðugleikaframlög`). Don't treat the surplus as run-rate.
5. **Double-encoded JSON** on `/api/FJS/Data/*`. Script handles it via
   `_decode_data`; if you call the API directly remember to `json.loads` the
   inner string.
6. **Files are served at `/api/Files/Rikisreikningur/{name}`** — `HEAD`
   returns 405 (method not allowed), use `GET` only. Content-type is
   generic `application/octet-stream`; trust the file-extension.
7. **Annual reports of state institutions and SOEs** live on sibling
   subdomains linked from the SPA:
   `arsreikningar.rikisreikningur.is/stofnun` (state institutions),
   `.../fyrirtaeki` (state-owned enterprises),
   `.../sveitarfelag` (municipalities). These are separate skills —
   currently covered opportunistically by [skatturinn](skatturinn.md) for
   SOEs and [reykjavik](reykjavik.md) for the Reykjavík municipality.
8. **Encoding.** Azure Functions returns UTF-8 JSON throughout. The 36
   málefnasvið names and account-line descriptions all contain Icelandic
   chars; write JSON with `ensure_ascii=False` and read CSV exports with
   `encoding="utf-8"`.

## Attribution

"Byggir á upplýsingum frá Fjársýslu ríkisins."

## Related

- [opnirreikningar](opnirreikningar.md) — invoice-level government-spending data
- [tenders](tenders.md) — public-procurement awards
- [hagstofan](hagstofan.md) — GFS-standard fiscal aggregates (THJ tables)
- Published PDF archive on island.is:
  `https://island.is/s/fjarsyslan/utgefid-efni?filters=…manadaryfirlit-rikissjods…`

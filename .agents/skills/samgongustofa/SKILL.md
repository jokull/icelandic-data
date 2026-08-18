---
name: samgongustofa
description: Icelandic vehicle registrations by make, fuel, class, model (Samgöngustofa) — new registrations + current on-road fleet via reverse-engineered Power BI API.
---

# Samgöngustofa (Iceland Transport Authority) — bifreiðatölur

Vehicle-registration statistics from `https://bifreidatolur.samgongustofa.is/`.
The site is a thin SPA that embeds a **separate Power BI report per section**,
each with its own resource key. `scripts/samgongustofa.py` extracts tidy CSVs
from two of them.

## Quick start

```bash
# What's available (both reports, their keys, every groupable dimension)
uv run python scripts/samgongustofa.py list

# Current fleet on the road, by fuel — the EV-transition read
uv run python scripts/samgongustofa.py fetch --report onroad --dimension fuel

# New registrations (imports) by brand, per year
uv run python scripts/samgongustofa.py fetch --dimension make --years 2020-2026

# Same, month by month, for a YoY view
uv run python scripts/samgongustofa.py fetch --dimension make --years 2025,2026 --monthly

# Only brand-new (exclude imported-used)
uv run python scripts/samgongustofa.py fetch --dimension fuel --years 2024-2026 --import-state new
```

Output lands in `data/processed/samgongustofa/<report>_<dimension>[_by_year[_month]][_new|_used].csv`
as tidy long format, e.g. `make,year,count` or `fuel,count`.

## Two reports: flow vs stock

| `--report` | Section | Meaning | Time |
|---|---|---|---|
| `nyskraningar` (default) | `#nyskraningar` | **New registrations = imports.** First Icelandic registration — brand-new *and* imported-used. The **flow** into the fleet. | year / month / new-vs-used slicers |
| `onroad` | `#tolfraedi` ("Tölfræði ökutækja") | **Current fleet on the road** ("í umferð") — every vehicle with an active registration. The **stock**. | snapshot (no year) |

## Four dimensions (`--dimension`)

Every report groups by the same four axes. Confusingly, the brand column is
named `Tegund` ("kind") in the model.

| `--dimension` | PB column (nyskr. / onroad) | Example values |
|---|---|---|
| `make` | `Tegund` | TOYOTA, KIA, VOLKSWAGEN, BYD, TESLA, MG, XPENG, … |
| `fuel` | `Orkugjafi` / `Orkugjafi (groups)` | Bensín, Dísel, **Rafmagn** (electric), **Tengiltvinn** (PHEV), Hybrid, Metan, Vetni, Vélarlaus (engineless=trailers), Annað |
| `class` | `Ökutækisflokkur` / `Ökutækjaflokkur` | Fólksbifreið M1, Sendibifreið N1, Vörubifreið N2/N3, Hópbifreið M2/M3, bifhjól, dráttarvél, eftirvagn, torfæruhjól, … |
| `model` | `Undirtegund` | MODEL Y, DUSTER, ID.4, RAV4, YARIS, … (top ~1000) |

`fuel` is the cleanest read on Iceland's EV transition: e.g. the current fleet
snapshot is ~171k Bensín, ~151k Dísel, ~44k Rafmagn, ~30k Tengiltvinn.

## Slicers & cross-filters

Temporal slicers (nyskraningar only):

- `--years 2020-2026` or `--years 2025,2026` — the `Ár - ísl.` slicer (values like `2023L`).
- `--monthly` — break each year into months (`Mánuður - ísl.`, text labels `01-janúar` … `12-desember`); `--through N` stops at month N.
- `--import-state new|used|all` — the `Innflutningsástand` slicer (`'Nýtt'`/`'Notað'`). Default `all` = both.

Cross-filter **either report by any model column** with `--where 'COL=VALUE'`
(repeatable = AND across columns; `;` inside a value = OR). This turns the
single-axis visuals into crosstabs the dashboard never shows directly:

```bash
# BEV imports by brand, 2026 — cross make × fuel
uv run python scripts/samgongustofa.py fetch --dimension make --years 2026 --where 'Orkugjafi=Rafmagn'

# Electric + PHEV vans on the road, by make
uv run python scripts/samgongustofa.py fetch --report onroad --dimension make \
    --where 'Orkugjafi (groups)=Rafmagn;Tengiltvinn' --where 'Ökutækjaflokkur=Sendibifreið N1'
```

Column names are the raw Power BI properties — `list` prints them all. Values
are matched as text; the year axis has its own `--years` path.

Note the current calendar month is **partial** — the newest month reflects
registrations to date, not a full month.

## How extraction works (and why the naive way fails)

Each visual POSTs a `SemanticQueryDataShapeCommand` to

```
https://wabi-europe-north-b-api.analysis.windows.net/public/reports/querydata?synchronous=true
```

with header `x-powerbi-resourcekey: <key>` and **no bearer token**. It is a
public report, but the anonymous grant is **session-, origin- and rate-bound**:

- a cold `httpx` client works for a few requests, then returns
  `401 PowerBINotAuthorizedException` (rate limit — the API even exposes
  `retry-after`);
- a POST from any origin other than the `app.powerbi.com` iframe is rejected
  outright with 401 (`access-control-allow-origin: *` on responses is a red
  herring — the *grant* is origin-bound).

**The reliable method** (what the script does): drive the SPA with Playwright,
then replay each query with `fetch()` executed **inside the app.powerbi.com
iframe** via `frame.evaluate` — reusing the report's own live session, origin
and pacing. Every year/month/state variant then returns 200.

Three more gotchas:

1. The POST body must keep its top-level `modelId` / `version` /
   `cancelQueries`, or the API answers `400 "ModelId must be between 1 and
   9.2e18"`.
2. **Resource keys and the model id rotate** — never hardcode them. The script
   decodes the key from the active iframe's embed token (`?r=<base64>` →
   `{"k": …}`) and reads templates off the section's own live requests.
3. Response rows come in two shapes: `nyskraningar` uses `C: [dimension, count]`;
   `onroad` uses `G0` + `X[0].M0` (in-traffic count) + `X[1].M0` (new-this-period).
   The parser handles both.

## Beyond the CLI — Playwright one-offs

`list`, `--dimension`, `--years/--monthly`, `--import-state` and `--where`
cover almost everything by composition. For anything they don't — a bespoke
aggregation, a multi-measure visual, driving a slicer in the UI — drop to the
generic **`scripts/powerbi.py`** primitives (see the `powerbi` skill) rather
than starting from scratch. They already solve discovery, the iframe-replay
auth, the modelId gotcha and the DSR decompression.

```python
import asyncio, sys; sys.path.insert(0, "scripts")
import powerbi as pb
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        d = await pb.discover(page, "https://bifreidatolur.samgongustofa.is/", anchor="#nyskraningar")
        payload = pb.where_in(d.templates["Tegund"], "Ár - ísl.", ["2026L"], text=False)  # make × 2026
        payload = pb.where_in(payload, "Orkugjafi", ["Rafmagn"])                            # ...BEV only
        rows = pb.group_counts(await pb.replay(d.frame, d.key, payload, retries=1))
        await b.close()
    print(sorted(rows.items(), key=lambda kv: -kv[1])[:10])

asyncio.run(main())
```

`d.templates` is keyed by each visual's first group-by column (`Tegund`,
`Orkugjafi`, `Ökutækisflokkur`, `Undirtegund`). To learn a new column or literal
format, drive the slicer once with a `page.on("request", …)` listener and read
the `post_data` — how every constant here was found (`pb.capture_requests`
helps). Full helper reference is in the `powerbi` skill.

## GEO-FENCE — must run from Iceland

`bifreidatolur.samgongustofa.is` answers Icelandic IPs in ~50 ms and
`ConnectTimeout`s from datacenter address space (GitHub runners, cloud VMs,
most hosted notebooks cannot reach it). Run the scraper and the health probe
from an Icelandic connection. The daily health probe therefore runs on the
self-hosted mac-mini in Iceland (see `AGENTS.md`).

## Caveats

1. **Real-time only.** The reports show current state; there are no historical
   snapshots beyond what the year/month slicers expose. Persist CSVs if you need
   a time series of the *stock*.
2. **`make` and `model` visuals are top-N** (200 makes / ~1000 models), so their
   column totals fall slightly below the all-inclusive `class`/`fuel` totals.
3. **Structure can drift.** Keys/model id rotate (handled). If a section is
   renamed or a slicer column changes, `list` will show what actually exists —
   start there.
4. **Pacing.** The script sleeps ~2.5 s between queries; don't hammer it.

## Example: Chinese-brand car imports (2026)

Filtering `make` to Chinese-owned brands (BYD, MG, XPENG, Polestar, Leapmotor,
Maxus, FAW, …) over `nyskraningar_make_by_year.csv` shows imports rising from
<1 % of new registrations (2020) to **11 %+ in 2026 YTD**, with Jan–Jul 2026
Chinese registrations up **~108 %** YoY — while they are still only ~1.6 % of
the *on-road* fleet (`onroad_make.csv`). The stock lags the flow.

## Alternative sources

- **Hagstofan** `Umhverfi/5_samgongur/…/SAM30120.px` — fleet by fuel type, **not** by make.
- **Bílgreinasambandið** — industry-association registration statistics.

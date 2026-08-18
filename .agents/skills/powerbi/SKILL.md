---
name: powerbi
description: Reverse-engineer public Power BI dashboards (app.powerbi.com/view embeds) — scripts/powerbi.py primitives: token/key, query replay, DSR decompression.
---

# Power BI dashboard reverse-engineering

Icelandic public bodies publish a lot of data only as embedded **Power BI**
dashboards (`https://app.powerbi.com/view?r=<token>`, often inside an
`<iframe>` on the agency's site). They all speak one protocol, so
`scripts/powerbi.py` factors out the generalizable parts. A per-source script
supplies only the SPA URL, which section to open, and the slicer/column names.

Sources in this repo that are Power BI underneath: **samgongustofa**
(fully migrated — the reference implementation), plus landlaeknir, vernd,
farsaeld_barna, ferdamalastofa, tekjusagan, vinnumalastofnun,
maelabord_nautgripa, sedlabanki_rates. The last group still only *captures
whatever fires on page load*; migrate them to `powerbi.py` when they need
parameterized queries (change a slicer, pull another year).

## The protocol (what's identical everywhere)

1. **Embed token** — `?r=<base64({"k":resourceKey,"t":tenant,"c":cluster})>`.
   `pb.embed_url(key, tenant)` builds it; `pb.key_of(url)` / `pb.token_of(url)`
   decode it. Keys **rotate** — never hardcode; read them live.
2. **Query endpoint** — `https://wabi-<region>-<x>-api.analysis.windows.net/
   public/reports/querydata?synchronous=true`, header
   `x-powerbi-resourcekey: <key>`, **no bearer** for public reports.
3. **Auth reality** — the anonymous grant is **session-, origin- and
   rate-bound**. A cold `httpx` client works for a few requests then 401s
   (`PowerBINotAuthorizedException`; the API even exposes `retry-after`), and a
   POST from any origin other than the app.powerbi.com iframe is rejected. So
   the robust move is to **replay queries with `fetch()` inside the iframe**.
4. **Request body** — a `SemanticQueryDataShapeCommand`. Capture the report's
   own request as a template and rewrite its `Where`; the body must keep its
   top-level `modelId`/`version`/`cancelQueries` or you get
   `400 "ModelId must be between 1 and 9.2e18"`.
5. **Response** — a DSR (DataShapeResult): a *compressed* columnar format with
   `ValueDicts` (int→string), an `R` repeat-bitmask (carry the previous row's
   value) and a `Ø` null-bitmask. **Decompress it or you silently undercount** —
   the naive `row["C"][0], row["C"][1]` reader drops every compressed row.

## The recipe

```python
import asyncio, sys; sys.path.insert(0, "scripts")
import powerbi as pb
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        # 1. open the dashboard, get the active report's iframe + key + templates
        d = await pb.discover(page, "https://<host>/", anchor="#section")   # anchor optional
        # 2. clone a visual's captured request and set filters
        body = pb.where_in(d.templates["<GroupCol>"], "<YearCol>", ["2026L"], text=False)
        body = pb.where_in(body, "<OtherCol>", ["SomeValue"])               # text literal
        # 3. replay inside the iframe (retries the transient 401/429) and decode
        counts = pb.group_counts(await pb.replay(d.frame, d.key, body, retries=1))
        await b.close()
    print(sorted(counts.items(), key=lambda kv: -kv[1])[:10])

asyncio.run(main())
```

## Helper reference (`scripts/powerbi.py`)

| helper | does |
|---|---|
| `embed_url(key, tenant, *, cluster=8, page=None)` | build an `app.powerbi.com/view?r=` URL |
| `token_of(url)` / `key_of(url)` | decode the `?r=` token / its resource key |
| `capture_requests(page, sink)` | attach a listener collecting `(key, body)` per querydata POST |
| `discover(page, spa_url, *, anchor=None)` | → `Discovery(frame, key, templates, requests)`; `templates` keyed by each visual's first group-by column, filtered to the active iframe's key |
| `replay(frame, key, payload, *, url=None, retries=1)` | POST `payload` inside the iframe → parsed JSON; retries transient 401/429 |
| `query_of(body)` | the `SemanticQuery` (Select/Where/OrderBy/Binding) inside a request body |
| `in_condition(col, values)` | build one `In` filter (values are literals: `'text'` or `2023L`) |
| `where_in(body, col, values, *, replace=True, text=True)` | clone + add/replace an `In` filter |
| `where_drop(body, *cols)` | clone + remove filters on those columns |
| `group_counts(body, *, measure=0)` | decode a `[dimension, measure]` visual → `{label: value}`; handles both DM0 shapes + compression |
| `parse_dsr(body)` | every DM0 row as a decoded value list (Select order) — for multi-measure / time-series visuals |

## Literal formats (the fiddly bit)

`In` values are sent **verbatim as literals**. Get the form right or the query
400s / returns empty:

- integer / date-key columns → `"2023L"` (note the `L`), pass `text=False`.
- text columns → `"'08-ágúst'"`, `"'Rafmagn'"` — `where_in(..., text=True)` (default) wraps them.

Discover a column's exact name and literal format by driving the slicer/visual
once with `pb.capture_requests` and reading the `post_data` it fires. That is
how every constant in the Power BI sources here was found.

## Onboarding a new Power BI source

1. `pb.discover(page, url)` (with `page.on("request")` via `capture_requests`)
   to enumerate the report's visuals, key, and the slicer columns.
2. Note the SPA URL, section anchors, group-by columns, slicer columns and
   their literal formats — the only source-specific facts.
3. Write a thin `scripts/<source>.py` CLI (copy `samgongustofa.py`'s shape:
   a `REPORTS`/dims config + `_slicer_payload` + a `fetch`/`list`).
4. Add a health probe and a Quick Command (see `new-data-source`).

## Caveats

- **Geo-fencing** is per-source, not a Power BI trait: e.g. Samgöngustofa's host
  only answers Icelandic IPs. Run from the right country.
- `group_counts` covers single-group visuals; genuinely hierarchical results
  (secondary `SH`/`DM1` groupings, e.g. a wide time-series matrix) need
  `parse_dsr` + custom shaping (see `sedlabanki_rates.parse_pbi_timeseries`).
- Pace replays (~2 s apart) — the anonymous grant rate-limits.

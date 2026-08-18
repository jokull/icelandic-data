---
name: lanamal
description: Government Debt Management Iceland (lanamal.is) — RIKB/RIKS government bond market yields, no auth, JSON API.
---

# Lánamál ríkisins (Government Debt Management Iceland)

Market data for Icelandic government bonds — yields, prices, chart history.
Publishes the RIKB (óverðtryggð, non-indexed) and RIKS (verðtryggð, indexed)
series that lanamal.is quotes on its `/markadsyfirlit` pages.

## API

**No auth, plain JSON.** Discovered by loading a `/markadsyfirlit/?type=bond`
page in a real browser and reading the network log — the page is ASP.NET
WebForms with a React island, and the bond detail panel calls:

```
GET https://www.lanamal.is/api/market/LoadIndexedDetail?orderbookId={ID}&lang=is
```

`{ID}` is the orderbook id in the page's own URL query string, e.g.
`RIKB_28_1115` (case-insensitive upstream, but the response echoes it
uppercased). Requires a browser-like `User-Agent` — a bare `curl` with no
headers gets blocked; a `Referer` pointing at the matching `/markadsyfirlit`
page plus a normal UA is enough, no cookies/session needed.

**Response encoding is UTF-16**, not UTF-8 — `httpx`/`requests` auto-detect it
fine from the BOM, but a raw `curl` dump looks like garbage without decoding.

```bash
curl -s -A "Mozilla/5.0" \
  -H "Referer: https://www.lanamal.is/markadsyfirlit/?type=bond&orderbookid=rikb_31_0124" \
  "https://www.lanamal.is/api/market/LoadIndexedDetail?orderbookId=RIKB_31_0124&lang=is"
```

## Response shape

A one-element JSON array:

```json
[{
  "closingYield": "7,54%", "closingPrice": "94,08",
  "bidYield": "7,55%", "askYield": "7,52%",
  "lastValidYield": "7,54%", "totalValueTraded": "94", "tradeCount": 1,
  "orderbookId": "RIKB_31_0124", "shortName": "RIKB 31 0124",
  "longName": "Óverðtryggð ríkisbréf",
  "attributes": [
    {"name": "ISIN númer", "value": "IS0000031234"},
    {"name": "Innlausnardagur", "value": "24.01.2031"},
    {"name": "Nafnvextir", "value": "5,00"}
  ],
  "chartData": {
    "header": "Ávöxtunarkr. í lok dags",
    "chartData": [["2025-08-18T00:00:00", 7.31], ["2025-08-19T00:00:00", 7.30], ...]
  }
}]
```

`attributes` is a flat list of Icelandic-labelled key/value pairs (maturity
date, ISIN, coupon, issue size, etc.) — parse by `name`, not by list position.

## Known quirk: `closingYield` can be stale — use `chartData` instead

The top-level `closingYield`/`bidYield`/`askYield`/`lastValidYield` fields
reflect the **last actual trade**, and these bonds trade thinly — one
observed response had `tradeCount: 1` for the whole lookback. That trade can
be days or weeks old and priced off a stale bid/ask spread, while
`chartData.chartData` (labelled "Ávöxtunarkr. í lok dags" — end-of-day yield)
is the market-maker's **daily fixing**, updated every business day regardless
of whether a trade happened. For "what is the yield today," read the last
point of `chartData`, not the top-level yield fields.

`chartData` covers roughly the trailing 12 months, daily, ascending by date —
enough to diff against a recent prior value for a day-over-day change without
a second request.

## Bond catalog (non-indexed / óverðtryggð, RIKB)

Fetch the orderbook id list from any `/markadsyfirlit/?type=bond` page's
links (`href="/markadsyfirlit/?type=bond&orderbookid=..."`). As of 2026-08,
the outstanding RIKB series:

| Orderbook ID | Maturity | Notes |
|---|---|---|
| RIKB_26_1015 | Oct 2026 | near maturity |
| RIKB_27_0415 | Apr 2027 | |
| RIKB_28_1115 | Nov 2028 | |
| RIKB_29_0416 | Apr 2029 | |
| RIKB_31_0124 | Jan 2031 | closest to a 5y horizon as of 2026 |
| RIKB_35_0917 | Sep 2035 | |
| RIKB_38_0215 | Feb 2038 | |
| RIKB_42_0217 | Feb 2042 | **longest outstanding non-indexed bond** — Iceland does not issue a 30y non-indexed bond, so this is the long-end proxy |

Indexed (verðtryggð, RIKS) series exist too (`riks_29_0917`, `riks_30_0701`,
`riks_33_0321`, `riks_37_0115`, `riks_50_0915`) — same API, `type=bond`,
different id prefix. Not currently consumed by anything in this repo.

**This catalog will drift** — bonds mature and new ones are auctioned. Re-scan
a `/markadsyfirlit` page's links if an orderbook id starts 404ing.

## Used by

`scripts/lanamal.py` — `fetch` pulls every outstanding RIKB/RIKS orderbook
from the catalog into `data/processed/lanamal.csv` (long format, daily
fixings per bond). `list` rescans the market page for the live catalog.

---
name: dashboard
description: Personal macro dashboard aggregator — collects IS + US/global indicators into data/processed/dashboard.json, published to GitHub Pages every 6h.
---

# Dashboard (mælaborð)

A personal, Austrian-econ-lens understanding tool, not a trading terminal.
`scripts/dashboard.py` is a thin aggregator over existing fetchers — it does
not re-implement parsing that already exists elsewhere in this repo — that
pulls a small set of Icelandic + global macro indicators into one JSON file,
published to GitHub Pages so a separate frontend (outside this repo) can
render it. Each metric carries a value, one period-over-period change, and
where it came from; there is no history in the output, only the latest read.

## Running

```bash
FRED_API_KEY=... uv run python scripts/dashboard.py
```

Writes `data/processed/dashboard.json`. `FRED_API_KEY` is required for the
six FRED metrics — without it, dashboard.py logs a warning and still writes
everything else (a source failing, including a missing key, never stops the
others; partial output beats none).

## Output shape

```json
{
  "fetched_at": "2026-08-16T20:33:23Z",
  "metrics": {
    "policy_rate_is": {
      "value": 7.75, "change": 0.25, "change_type": "pp",
      "label": "20. maí 2026",
      "source": "Seðlabanki Íslands", "source_url": "https://sedlabanki.is/",
      "decimals": 2, "suffix": "%"
    }
  }
}
```

`change_type` is `"pp"` for an absolute change (rates, yields — the `change`
number IS percentage points) or `"pct"` for a relative change (prices, index
levels — the `change` number is itself already a percentage). `label` is the
date (or month, for monthly series) the value is *as of* — not today's date,
the observation's own date, which can lag on weekends/holidays.

## Metrics

| Key | Value | Change | Source | Notes |
|---|---|---|---|---|
| `policy_rate_is` | Meginvextir (7d bundin innlán), % | pp, vs. last actual rate change | Seðlabanki (`xmltimeseries`, TS 17923) | 730-day lookback so the walk-back always finds the prior distinct value even across a long flat stretch |
| `cpi_is` | VNV, index level (1988=100) | pct, 12mo YoY | Hagstofa (`VIS01000.px`) | Hagstofa computes `change_A` (Ársbreyting) upstream — no YoY math done here |
| `usdisk` | USD/ISK official mid rate | pct, day-over-day | Seðlabanki (`xmltimeseries`, TS 4055) | |
| `eurisk` | EUR/ISK official mid rate | pct, day-over-day | Seðlabanki (`xmltimeseries`, TS 4064) | Same call `sedlabanki_fx.py` already makes for the FX-intervention pipeline |
| `bond_5y_is` | RIKB 31 0124 yield, % | pp, day-over-day | Lánamál ríkisins | ~4.4y to maturity as of 2026 — closest outstanding non-indexed bond to a 5y horizon, not literally 5y |
| `bond_long_is` | RIKB 42 0217 yield, % | pp, day-over-day | Lánamál ríkisins | Longest outstanding non-indexed bond (~15.5y). **Not a 30y bond** — Iceland doesn't issue one. Named `_long`, not `_30y`, on purpose |
| `treasury_5y_us` | US 5y Treasury yield, % | pp, day-over-day | FRED `DGS5` | |
| `treasury_30y_us` | US 30y Treasury yield, % | pp, day-over-day | FRED `DGS30` | |
| `fed_funds_rate` | Effective Fed funds rate, % | pp, day-over-day | FRED `DFF` | |
| `cpi_us` | US CPI-U, index level (1982-84=100) | pct, 12mo YoY | FRED `CPIAUCSL` | Monthly — YoY computed here (FRED doesn't hand it back pre-computed the way Hagstofa does) |
| `oil_brent` | Brent crude, USD/bbl | pct, day-over-day | FRED `DCOILBRENTEU` | |
| `btc_usd` | Bitcoin, USD | pct, 24h | CoinGecko `simple/price` | `include_24hr_change=true` — no separate history call needed |
| `btc_isk` | Bitcoin, ISK | pct, 24h (same % as `btc_usd`) | CoinGecko × `usdisk` | CoinGecko doesn't quote ISK directly — ISK value = `btc_usd.value × usdisk.value`, our own mid rate, not a second upstream call |

**No `gold` metric.** FRED discontinued `GOLDAMGBD228NLBM` (the LBMA gold
fixing) — the series 400s, confirmed via `GET /fred/series?series_id=...`
returning `"error_code":400,"error_message":"Bad Request.  The series does
not exist."`. A short search turned up no free source with both a live price
*and* history (needed for the change calc) — `gold-api.com` has the former
but not the latter, and is undocumented/unofficial. Revisit if a real
successor source turns up.

**No S&P 500 metric.** Stooq — the obvious free no-auth source — now gates
its CSV endpoints behind a JS proof-of-work challenge, so it's no longer
`curl`-able without a headless browser. The frontend already has its own
client-side fetch plus a static final fallback for S&P 500, so this was left
as a frontend-only concern rather than adding Playwright to a 6-hourly cron
job for one metric.

## The "last real change" trick

For a series that moves in discrete steps (`policy_rate_is` is the clear
case — it's flat for months between Central Bank board decisions), a plain
day-over-day diff is usually 0 and unhelpful. `last_change()` in
`dashboard.py` instead walks backward from the latest observation to the most
recent observation with a **different** value, and reports that as the
change — which for a step series recovers the size and date of the actual
last policy move. For a series that moves every observation (FX, bond
yields, FRED daily series) this collapses to an ordinary 1-day change, which
is exactly what you'd want anyway. Same function, both cases.

## Reused vs. new

Reused, not duplicated:
- `sedlabanki_fx.py`'s `XML_BASE` constant and `read_mid_rate()` parser
  (generalized from `read_eur_mid` — same rename, same behavior — so USD/EUR
  mid rates and meginvextir all go through one parser).
- The Hagstofa PX-Web POST pattern documented in the `hagstofan` skill.

New sources, each documented in its own skill:
- `lanamal` — RIKB bond yields (see that skill for the API, the
  `closingYield`-vs-`chartData` quirk, and the bond catalog).
- FRED and CoinGecko — no existing script touched these; both are
  well-documented public JSON APIs, so the fetch logic lives directly in
  `dashboard.py` rather than as separate `scripts/fred.py` /
  `scripts/coingecko.py` modules (neither is reused anywhere else yet).

## GitHub Action

`.github/workflows/dashboard.yml` — cron every 6h (00/06/12/18 UTC) +
`workflow_dispatch` + a push trigger on `scripts/dashboard.py`,
`scripts/sedlabanki_fx.py`, or the workflow file itself. Runs on
`ubuntu-latest` (none of these sources are Iceland-geo-fenced, unlike the
Power BI/Tableau sources that need the self-hosted mac-mini — see
`AGENTS.md`'s health-probe section for that distinction).

Steps: `uv sync --locked` → `uv run python scripts/dashboard.py` with
`FRED_API_KEY` from repo secrets → commit `data/processed/dashboard.json` iff
it changed → upload it as a Pages artifact → deploy.

`data/processed/` is otherwise gitignored (regenerable) — `dashboard.json` is
the one exception, via a `!data/processed/dashboard.json` negation in
`.gitignore`, because the whole point is that it's committed on every run so
Pages always serves the latest fetch.

Repo **Settings → Pages → Source** must be "GitHub Actions" for the deploy
job to have anywhere to publish to.

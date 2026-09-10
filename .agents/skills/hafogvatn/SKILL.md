---
name: hafogvatn
description: Hafrannsóknastofnun / MFRI — annual fish-stock assessments, advice, landings and survey series in embedded tables.
---

# Hafrannsóknastofnun — Marine and Freshwater Research Institute

**Requires:** Tier 0 (core).

MFRI publishes annual stock advice with current assessment tables embedded as
JSON inside static HTML pages.

## Data

**Catalogue:** `https://www.hafogvatn.is/en/moya/extras/categories/radgjof`

The current cod table has assessment summaries, landings, advice/TAC history,
catch-at-age and survey series. Its stable pattern is
`/static/extras/images/1_cod_{year}_1_tables_en.html`.

## Usage

```bash
uv run python scripts/hafogvatn.py list
uv run python scripts/hafogvatn.py fetch --stock cod --year 2026
```

## Caveats

1. Assessment vintages revise historic estimates: retain publication year.
2. The per-stock table schemas and assessment methods differ.
3. The old `data.hafro.is` CSV archive is useful historically but is not the
   current annual publication channel.

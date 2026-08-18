---
name: eurostat
description: Eurostat (EU statistics office) REST API — wages, HICP, GDP, unemployment for euro-area / EU aggregates; scripts/eurostat.py fetches any dataset to tidy CSV.
---

# Eurostat (Statistical Office of the EU)

Official statistics for the European Union and euro area — the counterpart
to Hagstofan for evrusvæðið. No authentication, no rate key, plain HTTP.

## API

**Base URL:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}`

- JSON via `?format=JSON`; filters as `&dim=code` params.
- Responses are **json-stat2**: `.dimension.<d>.category.index` maps
  code → position, `.label` position → human label, `.value` holds
  row-major composite-indexed values (first dimension varies fastest).
- No API key. Works from any CI runner (unlike geo-fenced Icelandic hosts).

`scripts/eurostat.py` wraps this: `fetch DATASET --filter KEY=VALUE`
(repeatable) flattens to a tidy long CSV in `data/processed/eurostat/`
(`--out` overrides).

## Fetching data

```bash
uv run python scripts/eurostat.py list                    # curated datasets
uv run python scripts/eurostat.py fetch prc_hicp_midx \
  --filter geo=EA20 --filter coicop=CP00 --filter unit=I15
uv run python scripts/eurostat.py fetch namq_10_a10 \
  --filter geo=EA20 --filter na_item=D1 --filter s_adj=SCA \
  --filter unit=CP_MEUR --filter nace_r2=TOTAL
uv run python scripts/eurostat.py fetch namq_10_pe \
  --filter geo=EA20 --filter na_item=EMP_DC --filter s_adj=SCA --filter unit=THS_PER
```

Filter values are codes, case-insensitive. The `time` dimension cannot be
range-filtered server-side (400) — fetch the series and slice locally
(duckdb/polars).

## Key datasets used in this repo

| Dataset | What | Key codes |
|---|---|---|
| `prc_hicp_midx` | HICP monthly **index** | `unit=I15` (2015=100), `coicop=CP00` (all items) |
| `prc_hicp_manr` | HICP monthly rate of change | `unit=RCH_A` (annual), `RCH_M` (monthly) |
| `namq_10_a10` | National accounts, quarterly | `na_item=D1` (compensation of employees, `CP_MEUR`), `D11` (wages & salaries), `s_adj=SCA`, `nace_r2=TOTAL` |
| `namq_10_pe` | Population & employment, quarterly | `na_item=EMP_DC` (employment, `THS_PER`), `s_adj=SCA` |
| `lc_lci_lev` | Labour cost levels, annual | `lcstruct=D11` (wages & salaries, €/h), `nace_r2=B-S_X_O` |
| `namq_10_lp_ulc` | Productivity & unit labour costs | `na_item=RLPR_*`, `NULC_*` |

## Real wages, euro area (the canonical recipe)

Real compensation per employee, quarterly, 2015=100:

```sql
-- data/processed/eurostat/{namq_10_a10,namq_10_pe,prc_hicp_midx}.csv fetched per above
WITH ea AS (
  SELECT make_date(CAST(regexp_extract(time,'(\\d{4})',1) AS INT),
                   1+3*(CAST(regexp_extract(time,'Q(\\d)',1) AS INT)-1), 1) q, value d1
  FROM read_csv_auto('data/processed/eurostat/namq_10_a10.csv')),
emp AS (
  SELECT make_date(CAST(regexp_extract(time,'(\\d{4})',1) AS INT),
                   1+3*(CAST(regexp_extract(time,'Q(\\d)',1) AS INT)-1), 1) q, value e
  FROM read_csv_auto('data/processed/eurostat/namq_10_pe.csv')),
hicp AS (
  SELECT date_trunc('quarter', strptime(time,'%Y-%m')) q, avg(value) h
  FROM read_csv_auto('data/processed/eurostat/prc_hicp_midx.csv') GROUP BY 1)
SELECT ea.q, 100.0*(d1/e*1000/h)/
       (SELECT avg(d1/e*1000/h) FROM ea JOIN emp USING(q) JOIN hicp USING(q)
        WHERE ea.q BETWEEN date '2015-01-01' AND date '2015-12-31') idx2015
FROM ea JOIN emp USING(q) JOIN hicp USING(q) WHERE ea.q >= date '2015-01-01';
```

`reports/real_wages_is_vs_euro.py` is the worked example — it builds the
Iceland-vs-euro-area real wage comparison chart.

## Caveats

1. **Codes change / datasets move.** `LC_LCI_R2` (quarterly LCI) is not
   available for dissemination (404) — use `namq_10_a10`/`namq_10_pe` instead.
   An invalid filter returns 200 with `value: {}` — check for empty values,
   not just HTTP status.
2. **`lc_lci_lev` is benchmark-year based** for EA20: 2008, 2012, 2016,
   2020-2025 only. Don't assume continuous annual series.
3. **json-stat indexes are 0-based positions**, and `.category.label` is
   keyed by position — the label for position 0 is a valid lookup; don't
   index labels by code.
4. EA20 includes Croatia (from 2023) — negligible for aggregates.
5. Seasonally adjusted (`SCA`) employment/compensation vs non-adjusted HICP
   is the standard real-wage mix; HICP has almost no seasonality.

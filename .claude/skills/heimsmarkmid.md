# Heimsmarkmið — Iceland's UN Sustainable Development Goal statistics

Iceland's implementation of the UN 2030 Agenda. Hagstofa Íslands publishes
137 national SDG indicators (all 17 goals) via a public `open-sdg` instance.

- **Site:** `heimsmarkmidin.hagstofa.is` (Icelandic) / `heimsmarkmidin.hagstofa.is/en/` (English)
- **Data repo:** `hagstofan.github.io/heimsmarkmid-data-prod/` (GitHub Pages)
- **Platform:** [open-sdg](https://open-sdg.org) — same toolkit used by UK, US, and
  ~20 other national SDG portals. If you know one, you know all of them.

## Architecture

Frontend is a server-rendered Jekyll static site. Underlying data and
metadata are published as flat files on a sibling GitHub Pages repo:

| Path | Contents |
|------|----------|
| `/is/data/{code}.csv` | Time-series data with disaggregation columns |
| `/is/meta/{code}.json` | Indicator metadata (name, source, graph config, units) |
| `/is/headline/{code}.csv` | Headline series only (no disaggregation) |
| `/is/comb/{code}.json` | Combined JSON (data + headline, structured for charting) |
| `/is/zip/all_indicators.zip` | All 137 data CSVs in one 437 KB download |
| `/en/...` | English-language mirror of the above |

Indicator codes follow the UN SDG nomenclature: goal-target-indicator, e.g.
`1-1-1` (Goal 1 · Target 1 · Indicator 1) or `16-b-1` (target "b", indicator 1).

## Usage

```bash
# Download the ZIP, extract to data/raw/heimsmarkmid/, build catalog CSV
uv run python scripts/heimsmarkmid.py fetch
uv run python scripts/heimsmarkmid.py fetch --force    # Re-download (ZIP is cached)

# Print catalog
uv run python scripts/heimsmarkmid.py list
uv run python scripts/heimsmarkmid.py list --goal 4

# Fetch data + metadata for one indicator
uv run python scripts/heimsmarkmid.py get 1-1-1
uv run python scripts/heimsmarkmid.py get 16-b-1
```

The ZIP is fetched once and cached; metadata is fetched live on `get` (the
open-sdg meta endpoint doesn't ship inside the ZIP).

## Catalog schema

`data/processed/heimsmarkmid_catalog.csv`:

| Column | Description |
|--------|-------------|
| `code` | Indicator code (e.g. `1-1-1`, `16-b-1`) |
| `goal` | Leading SDG goal number (1–17) |
| `target` | Middle segment (numeric or single letter) |
| `indicator` | Final segment of the code |
| `columns` | `\|`-separated disaggregation columns (excluding `Year`, `Value`) |
| `n_rows` | Number of data rows in the CSV |
| `first_year`, `last_year` | Range of years present (empty when no numeric rows) |

## Data-file schema

Every `/is/data/{code}.csv` has:

| Column | Meaning |
|--------|---------|
| `Year` | Calendar year (integer) |
| `<disaggregations>` | Zero or more columns (`Kyn`, `Aldur`, `Svæði`, etc.); empty value = "Total" |
| `Value` | Numeric measurement in the unit declared in the meta file |

Unit is in `meta.computation_units` — common values are `Hundraðshlutar (%)`,
`Fjöldi`, `krónur`. Units can vary within a single CSV if an indicator
publishes multiple measurement series side-by-side (see `4-1-1` where the
`Units` column differentiates reading vs. maths proficiency).

## Goal coverage (2026-04 snapshot)

| Goal | Indicators | Total rows |
|------|------------|-----------:|
| 1 · No poverty | 9 | 856 |
| 2 · Zero hunger | 7 | 124 |
| 3 · Good health | 22 | 1,187 |
| 4 · Quality education | 9 | 519 |
| 5 · Gender equality | 7 | 491 |
| 6 · Clean water | 8 | 48 |
| 7 · Clean energy | 6 | 353 |
| 8 · Decent work | 10 | 2,453 |
| 9 · Industry/infrastructure | 6 | 1,458 |
| 10 · Reduced inequalities | 5 | 267 |
| 11 · Sustainable cities | 9 | 324 |
| 12 · Responsible consumption | 8 | 595 |
| 13 · Climate action | 2 | 958 |
| 14 · Life below water | 2 | 6 |
| 15 · Life on land | 7 | 94 |
| 16 · Peace & institutions | 10 | 267 |
| 17 · Partnerships | 10 | 338 |
| **Total** | **137** | **~10,338** |

## Caveats

1. **Reporting gaps are normal.** Some indicators have `n_rows=0` — they're
   listed in the national framework but Iceland hasn't reported yet.
   Others have a single row (e.g. `4-a-1` has 2 rows, one per survey year).
2. **Disaggregation columns differ per indicator.** Don't assume a common
   schema across files — always join by `code` via the catalog, or inspect
   the header before parsing.
3. **"Total" rows use empty disaggregation cells.** When you need the
   headline series without breakdowns, filter rows where all disaggregation
   columns are empty — or use `/is/headline/{code}.csv` directly.
4. **Rows can duplicate across years with different units.** `4-1-1` reports
   both reading and maths proficiency in the same file, with a `Tegund
   færni` discriminator. Always disambiguate with the full key
   `(Year, *disaggregations)` before aggregating.
5. **Meta is English-labelled even on the `/is/` tree.** Field keys
   (`indicator_name`, `graph_title`) stay in English; only the values are
   translated.
6. **The data repo is rebuilt nightly.** If you're caching the ZIP,
   re-download with `fetch --force` when you need fresh values — the script
   does not compare timestamps for you.
7. **Overlap with [velsaeldarvisar](velsaeldarvisar.md).** About a dozen
   indicators (low-income share, gender gap, unemployment) appear in both
   publications but with different dimensional breakdowns. The SDG version
   follows UN methodology; the velsaeldarvísar version follows Eurostat/OECD.
8. **Encoding.** GitHub Pages serves all CSV/JSON/YAML as UTF-8. Icelandic
   chars appear in indicator titles, units (`Hundraðshlutar`, `krónur`), and
   disaggregation labels. Read with `encoding="utf-8"` and write JSON with
   `ensure_ascii=False`.

## Attribution

"Byggir á upplýsingum frá Hagstofu Íslands (landsvísar fyrir heimsmarkmið)."

## Related

- [velsaeldarvisar](velsaeldarvisar.md) — Hagstofa's wellbeing/social/cultural
  indicator portal. Separate content, partial thematic overlap.
- [hagstofan](hagstofan.md) — many SDG indicators are re-computations over
  PX-Web tables reachable here.

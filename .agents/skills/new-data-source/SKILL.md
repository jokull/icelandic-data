---
name: new-data-source
description: Methodology for adding a new Icelandic data source — discovery, probing, skill authoring, script conventions, health probe, testing.
---

# New Data Source — How to Learn and Integrate

Step-by-step methodology for adding a new Icelandic data source to this toolkit. Based on proven patterns from 20+ existing skills.

## Phase 1: Discovery

**Goal:** Understand what the source offers before writing any code.

### 1.1 Find the API

Most Icelandic public data is served via one of these patterns:

| Pattern | Examples | How to detect |
|---------|----------|---------------|
| REST/JSON API | Hagstofan, UST (loftgæði) | `/api/` in URL, returns JSON |
| WFS (GeoServer) | Vegagerðin, LMI | `geoserver` in URL, `?service=WFS` |
| PX-Web | Hagstofan, Reykjavík | `.px` files, POST with JSON query |
| Power BI embed | Samgöngustofa, Ferdamálastofa | `app.powerbi.com/view?r=` in page source |
| CKAN | Reykjavík open data | `/api/3/action/` in URL |
| Static files (Excel/CSV) | Seðlabanki | Direct download links |
| Web scraping needed | Skatturinn, Nasdaq | No API — HTML pages, login flows |

**First moves:**
```bash
# Check for WFS/WMS capabilities
curl -s "https://{domain}/geoserver/wfs?service=WFS&request=GetCapabilities" | head -50

# Check for REST API
curl -s "https://{domain}/api/" | jq .

# Check for CKAN
curl -s "https://{domain}/api/3/action/package_list" | jq '.result[:10]'
```

### 1.2 Probe the API

Once you know the type, enumerate what's available:

**For WFS (GeoServer):**
```bash
# List all layers
curl -s "{base}?service=WFS&version=2.0.0&request=GetCapabilities" 

# Fetch 3 features to inspect schema
curl -s "{base}?service=WFS&version=2.0.0&request=GetFeature&typeName={layer}&outputFormat=application/json&count=3&srsName=EPSG:4326"
```

**For REST APIs:**
```bash
# Hit the root/docs endpoint
curl -s "{base}/" | jq .

# Try common endpoint patterns
curl -s "{base}/stations" | jq '.[0]'
curl -s "{base}/data?limit=5" | jq .
```

**For Power BI:**
- Open the page, look for `<iframe>` with `app.powerbi.com/view?r=`
- Extract the embed token from the `r=` parameter
- Use browser DevTools Network tab to find the actual data requests

### 1.3 Document the Schema

For every field you discover, record:

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `field_name` | STRING/INT/DATE | `"Reykjavík"` | What it means |

**Critical details to capture:**
- Null handling — what does `null` mean? (offline sensor? missing data? zero?)
- Date formats — ISO 8601? Icelandic format? Unix timestamps?
- Encoding — UTF-8? Latin-1? Windows-1252? (check for þ, ð, æ, ö)
- ID fields — which uniquely identifies a record? Can IDs repeat? (e.g., directional traffic counters share station IDs)
- Classification codes — what do numeric codes mean? (station types, road categories)

### 1.4 Assess Data Scope

Answer these questions before writing code:
- **Historical depth:** Does the API serve historical data, or only current/rolling windows?
- **Update frequency:** Real-time? Daily? Annual?
- **Volume:** How many records? Will it fit in memory? Need pagination?
- **Rate limits:** Any throttling? Auth tokens needed?
- **Format size:** Will the raw download be <10 MB or >1 GB?

## Phase 2: Build the Skill File

**Create `.agents/skills/{source}/SKILL.md`** — a directory with a `SKILL.md`
inside, never a flat `.md`. Both Claude Code and Codex discover skills by
directory ([agentskills.io](https://agentskills.io)); a flat file is invisible
to both. `.claude/skills` is a symlink to `.agents/skills`, so one file serves
both agents — do not create anything under `.claude/` directly.

Naming: lowercase ASCII, hyphens only. No underscores, no `ð`/`æ`/`þ`
(`kortagerð` → `kortagerd`, `eea_sdi` → `eea-sdi`). The directory name is the
skill's identity; `name:` in the frontmatter must match it exactly.

The `description` is the whole basis on which an agent decides to load your
skill — it is the only part preloaded into context. Write it third-person,
front-loaded with the trigger words someone would actually type (the agency
name, the Icelandic term), saying what it covers *and when to reach for it*.

**Keep it under ~160 characters.** Codex truncates once all descriptions
combined exceed 8,000 characters; with 45 skills that budget, not the
per-skill limit, is what binds.

```markdown
---
name: {source}
description: {Agency/term} — {what data}. Use for {when}. Under ~160 chars.
---

# {Source Name} — {Agency}

{One sentence: what data, from whom.}

## API

**Base URL:** `{url}`

{Auth status}. {Protocol}. {Response format}.

## Available Data

{Table of endpoints/layers/datasets with descriptions}

## Request Examples

{curl/Python snippets that actually work — test them first}

## Schema

{Field tables with types, examples, descriptions}
{For complex responses, show a sample JSON/CSV block}

## Script Usage

{The CLI commands for the associated Python script}

## Data Files

{Table: file path, format, description}

## Caveats

{Numbered list of gotchas — this is the most valuable section}
1. {Encoding quirk}
2. {Null semantics}
3. {Historical data limitation}
4. {Double-counting risk}
5. {Classification changes over time}
```

**What makes a skill file valuable:**
- Someone can use the data source without reading the original docs
- Caveats prevent bugs before they happen
- Code examples are copy-pasteable and tested
- Field schemas include real example values, not just types

## Phase 3: Build the Script

**Create `scripts/{source}.py`** following project conventions:

```python
"""
{Source name} — {one line description}.

Usage:
    uv run python scripts/{source}.py {subcommand}
"""

import argparse
import json
from pathlib import Path

import httpx
import polars as pl

BASE_URL = "{api_url}"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "{source}"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
```

### Standard Subcommands

Design the CLI around the data lifecycle:

| Subcommand | Purpose | When to include |
|------------|---------|-----------------|
| `list` | Enumerate available datasets/stations/layers | Always |
| `fetch` / `snapshot` | Download current data | Always |
| `collect` | Accumulate over time (append + dedup) | When API only gives rolling windows |
| `report` | Generate HTML visualization | When visual output adds value |

### Data Processing Rules

- **polars** for DataFrames (never pandas)
- **httpx** for HTTP (with `timeout=60`)
- **pathlib.Path** for all file paths
- Save raw data to `data/raw/{source}/` (JSON, Excel, CSV as received)
- Save processed data to `data/processed/` (tidy CSV or Parquet)
- Print progress to stdout (`print(f"  {count} records fetched")`)
- Let exceptions bubble up — no silent error swallowing

### Accumulation Pattern (for rolling-window APIs)

When the API only provides recent data (e.g., last 7 days):

```python
# 1. Fetch current window
new_data = fetch_api()

# 2. Unpivot wide columns to long format if needed
# 3. Load existing history
if HISTORY_FILE.exists():
    existing = pl.read_parquet(HISTORY_FILE)
    combined = pl.concat([existing, new_data], how="diagonal_relaxed")
else:
    combined = new_data

# 4. Deduplicate on natural key
deduped = combined.unique(subset=["station_id", "date"], keep="last")

# 5. Write back
deduped.sort(["station_id", "date"]).write_parquet(HISTORY_FILE)
```

Use `keep="last"` so fresher data overwrites older snapshots (sources may revise).

## Phase 4: Test and Verify

Run each subcommand and verify output:

```bash
# 1. Basic connectivity
uv run python scripts/{source}.py list

# 2. Data fetch
uv run python scripts/{source}.py fetch

# 3. Query the output
duckdb -c "SELECT count(*), min(date), max(date) FROM 'data/processed/{output_file}'"

# 4. Spot-check values
duckdb -c "SELECT * FROM 'data/processed/{output_file}' LIMIT 5"
```

**What to check:**
- Icelandic characters (þ, ð, æ, ö) survive the pipeline
- Dates parse correctly (not strings)
- Numeric fields are numbers (not strings with commas)
- No duplicate rows
- Null counts make sense

## Phase 5: Visualize

If the data has a spatial or temporal dimension, create a report:

**HTML report** (for interactive/shareable): follow the pattern in `scripts/nasdaq_report.py`
- Embed data as JSON in `<script>` tags
- Chart.js for time series, Leaflet for maps
- Self-contained, no build step

**Static map** (for geo data): use cached LMI layers via `data/geodata/`
- `geopandas` + `matplotlib` for publication quality
- See `scripts/kortagerð.py` and the `kortagerd` skill for templates

## Phase 6: Add a Health Probe

Upstream sources change or vanish without anything in this repo changing. Add
`tests/health/test_{source}.py` so that breakage surfaces on its own rather
than the next time someone runs a fetch.

Probe the **smallest stable contract** the script depends on — not the data:

```python
"""Health probe — {Agency}."""

BASE = "https://..."

def test_catalog_is_served(http):
    r = http.get(f"{BASE}/...")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert payload, "catalog is empty"
    assert "expected_key" in payload[0], f"unexpected shape: {sorted(payload[0])}"
```

Rules:

- Everything under `tests/health/` is auto-marked `slow` + `health` by the
  local `conftest.py`. No decorators needed, and PR CI never touches it.
- Use the `http` fixture — it carries explicit connect/read timeouts and
  retries *connection* errors only, so a schema change reports on the first try.
- **Never write to `data/`.** Import the script's constants and regexes, but do
  not call fetch functions that cache raw responses as a side effect.
- Keep payloads small: WFS `count`, PX-Web single-year queries, one sub-page.
- Assert invariants that break loudly and rarely: status, content type, required
  keys, non-empty, a known identifier still present, plausible types. Never exact
  row counts, wording, or ordering.
- Staleness is **degraded, not failed** — mark those `@pytest.mark.degraded_ok`
  and use `assert_fresh()`. A source that is up but three days behind is a
  different problem from one that is down, and only the second should go red.
- Needs Playwright? Add `@pytest.mark.browser`. Those run manual-only.
- Needs credentials? `pytest.importorskip`/`pytest.skip` — skipped reports as
  skipped, not failed.

**Write failure messages the classifier can read.** `health_verdict.py` splits
*structural* failures (service answered wrong → the skill is out of date, convict
after 2) from *infra* failures (unreachable → could be a flake, convict after 3).
It infers which from the message text, so:

- Put the URL and status code in the assertion: `f"{r.request.url} -> {r.status_code}"`.
  A `-> 503` is then read as infra, a `-> 404` as structural.
- If you catch a transport error and re-raise via `pytest.fail`, **keep the
  original exception class in the string** — `f"unreachable: {type(exc).__name__}: {exc}"`.
  Drop it and a merely-unreachable host gets convicted as a broken skill after
  two days.

Verify it against the live source, then confirm it stays out of PR CI:

```bash
uv run pytest -m health tests/health/test_{source}.py -q
uv run pytest -m "not slow" -q     # must not include your probe
```

## Phase 7: Register

1. **No index to update** — the skill's frontmatter `description` *is* its index
   entry. Both agents preload it. Do not add a table anywhere.

2. **Add quick commands** to the Quick Commands section in `AGENTS.md`
   (`CLAUDE.md` is a symlink to it)

3. **Update `.gitignore`** if adding a new data directory outside `data/raw/` or `data/processed/`

4. **Add dependencies** to `pyproject.toml` if the source requires a new Python
   package — and run `uv sync` so `uv.lock` stays in step, or CI's
   `uv sync --locked` fails

## Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| Double-counting directional data | Check if source has "combined" records — use those OR directional, never both |
| Encoding corruption on Windows | Use `encoding="utf-8"` on all `open()` and `.write_text()` calls |
| Stale cache assumptions | Always note when cached data was last updated; add `--force` flag for re-download |
| Huge WFS responses | Use `maxFeatures`/`count` parameter when probing; download in full only for caching |
| Power BI token expiry | Tokens from embedded reports expire in ~1 hour; document the refresh flow |
| Rate limiting | Add `time.sleep()` between batch requests; document limits in the skill file |
| Schema changes over time | Note known classification changes with dates in the Caveats section |
| Missing `null` semantics | Document what null means for each field (offline? not applicable? zero?) |

## Checklist

Before considering a new data source complete:

- [ ] Skill at `.agents/skills/{source}/SKILL.md` with frontmatter, API, schema, caveats
- [ ] `name:` matches the directory; both lowercase ASCII + hyphens
- [ ] `description:` under ~160 chars, front-loaded with trigger words
- [ ] Script in `scripts/{source}.py` with `list`/`fetch` subcommands
- [ ] Raw data saved to `data/raw/{source}/`
- [ ] Processed data saved to `data/processed/`
- [ ] Output verified with DuckDB query
- [ ] Icelandic characters confirmed working
- [ ] Health probe at `tests/health/test_{source}.py`, verified against the live source
- [ ] `uv run pytest -m "not slow"` still green and still offline
- [ ] Quick commands added to `AGENTS.md`

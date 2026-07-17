# tests/health/ — upstream health probes

One file per data source: `test_<source>.py`. Everything here is auto-marked
`slow` + `health` by `conftest.py`, so PR CI never touches the network.

```bash
uv run pytest -m health                        # every probe
uv run pytest -m health -k hagstofan           # one source
uv run pytest -m "health and not browser and not degraded_ok"   # required lane (daily, gates)
uv run pytest -m "health and degraded_ok"      # staleness / known-soft (daily, reports)
uv run pytest -m browser                       # Playwright probes (manual only)
```

See the `new-data-source` skill for how to write one, and `AGENTS.md` for how
flake-vs-dead is decided.

## Skills with no upstream to probe

Coverage is per *upstream source*, not per skill. These skills are deliberately
not probed, because there is nothing upstream that can break. Probing them would
manufacture a green tick that means nothing — the more expensive kind of nothing,
because it looks like coverage.

| Skill | Why not probed | What would actually catch a break |
|---|---|---|
| `new-data-source` | Methodology. No API. | n/a |
| `pdf-parsing` | Tool-selection guide (docling vs liteparse vs pdfplumber). No API. | n/a |
| `liteparse` | Local library. Fails at install time, not at runtime. | `uv sync` in PR CI |
| `iceaddr` | Local library with bundled SQLite from Staðfangaskrá. No network at all. | `uv sync` in PR CI |
| `financials` | Local PDF extraction over files fetched by `skatturinn`. | the `skatturinn` probe |
| `kortagerd` | Renders maps from the cached LMI data. Derived, not fetched. | the `lmi` probe + `tests/test_maps_render.py` |
| `sectoral-balances` | Analysis over Hagstofan + Seðlabanki series. | the `hagstofan` and `sedlabanki` probes |
| `annual-report-cache` | Wrapper over `skatturinn` + `financials` with an R2 cache. | the `skatturinn` probe |
| `insurance` | Analytical. No `scripts/insurance.py` and no API of its own — combined ratios are read out of annual-report PDFs fetched by `skatturinn` and parsed by `financials`. FME publishes no API; the Nordic peer figures are read by hand from IR sites. | the `skatturinn` probe |

If one of these grows a real upstream, it gets a probe like anything else.

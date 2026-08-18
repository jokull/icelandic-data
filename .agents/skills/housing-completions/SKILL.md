---
name: housing-completions
description: Iceland housing completions 1970–2025 — Hagstofan IDN03001 + HMS húsnæðisáætlanir; scripts/housing_completions.py combines both into one tidy CSV.
---

# Housing completions (fullgerðar íbúðir)

Long-run annual count of completed dwellings in Iceland, built from two halves:

- **Hagstofan IDN03001** — 1970–2021 via PX-Web POST to
  `https://px.hagstofa.is/pxis/api/v1/is/Atvinnuvegir/idnadur/byggingar/IDN03001.px`
  with `Byggingarstaða=2` (fullgert á árinu) and `Eining=0` (fjöldi íbúða).
- **HMS húsnæðisáætlanir** — 2020–2025, hardcoded `HMS_COMPLETIONS` figures
  from sheet 2.1 of the annual housing-plan report (2026/1 publication).

```bash
uv run python scripts/housing_completions.py   # → data/processed/iceland_housing_completions.csv
```

Output is `year, completions, source`: Hagstofan 1970–2019, HMS 2020–2025
(HMS wins the 2020–21 overlap, which matches Hagstofan within ~30 units).

Gotchas that bite:

- **IDN03001 froze after 2021** — that is why the script exists. Never expect
  post-2021 years from the API; HMS takes over.
- **HMS figures are hardcoded and go stale** — update `HMS_COMPLETIONS`
  annually from the newest húsnæðisáætlanir report, or the tail silently
  stops moving.
- The PX response is **ISO-8859-1** CSV — decode from bytes; httpx's default
  guess will mangle it.
- The health probe (`tests/health/test_housing_completions.py`) covers only the
  live half; nothing watches the hardcoded HMS dict.

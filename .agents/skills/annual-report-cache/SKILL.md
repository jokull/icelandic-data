---
name: annual-report-cache
description: Cached Icelandic company annual reports (ársreikningar) via fetch-annual-report.sh. Prefer over skatturinn+financials for EBITDA, ratios, shareholders.
---

# Annual Report Cache

**Requires:** Tier 4 (restricted) — bash + R2 credentials inside the Sprite worker; use skatturinn + financials elsewhere.

**Always use `scripts/fetch-annual-report.sh` when fetching annual reports.**

The script is bash-only and expects R2 credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `R2_ENDPOINT`) plus a checkout at `/home/sprite/icelandic-data` — it runs inside the Sprite worker. On a laptop, or on Windows, or without those credentials, skip it and use the `skatturinn` + `financials` skills directly.

This script handles R2 caching transparently — you don't need to manage the cache yourself.

## Usage

```bash
# Fetch latest year for a kennitala
./scripts/fetch-annual-report.sh 4612023490

# Fetch specific year
./scripts/fetch-annual-report.sh 4612023490 2023

# Fetch multiple years
for year in 2022 2023 2024; do
  ./scripts/fetch-annual-report.sh 4612023490 $year > /tmp/report-$year.json
done
```

## How it works

1. Checks R2 cache at `annual-reports/{kennitala}/{year}.json`
2. If cached (CACHE_HIT) — returns JSON instantly (~100ms)
3. If not cached (CACHE_MISS) — runs skatturinn.py + financials.py, caches result in R2, returns JSON
4. Status messages go to stderr, JSON data goes to stdout

## Output

Structured JSON with: `incomeStatement`, `balanceSheet`, `cashFlow`, `ratios`, `bankFinancials` (if bank), `shareholders`, `boardMembers`.

## When to use

- Any query about ársreikningar, EBITDA, financial analysis, company financials
- **Prefer this over running skatturinn.py + financials.py directly**
- The R2 cache has ~2,500 pre-extracted reports for instant access

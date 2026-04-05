# Exchange Rates (Gengi)

Current card rates (Borgun) and historical ECB reference rates.

## Usage

```bash
# Current Borgun card rates (all currencies)
uv run python scripts/gengi.py

# Current rates for specific currencies
uv run python scripts/gengi.py USD,EUR,GBP

# Historical ECB rates — last 6 months (default)
uv run python scripts/gengi.py USD,EUR --history 6m

# Historical rates — last year
uv run python scripts/gengi.py USD --history 1y

# Historical rates — last 5 years
uv run python scripts/gengi.py EUR,GBP,DKK --history 5y

# Historical rates — last 30 days
uv run python scripts/gengi.py USD,EUR --history 30d
```

## Output — Current Rates

```json
{
  "USD": { "rate": 127.19, "description": "Us dollar" },
  "EUR": { "rate": 146.91, "description": "Euro" }
}
```

## Output — Historical Rates

```json
{
  "base": "ISK",
  "start": "2025-10-05",
  "end": "2026-04-05",
  "currencies": ["USD", "EUR"],
  "rows": [
    { "date": "2025-10-06", "USD": 137.5, "EUR": 149.2 },
    { "date": "2025-10-07", "USD": 138.1, "EUR": 149.8 }
  ]
}
```

Values are ISK per 1 unit of foreign currency (e.g. 1 USD = 127.19 ISK).

## Sources

- **Current rates**: Borgun card rates (consumer markup, NOT interbank)
- **Historical rates**: ECB reference rates via frankfurter.dev (daily interbank)
- Period format: `30d` (days), `6m` (months), `1y`/`5y` (years)
- Historical data available from 1999 onwards

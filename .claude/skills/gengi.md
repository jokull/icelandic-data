# Borgun Exchange Rates (Gengi)

Currency exchange rates from Borgun's public XML feed.

## API

- **Endpoint:** `GET https://www.borgun.is/currency/Default.aspx?function=all`
- **Auth:** None (public)
- **Format:** XML

## Usage

```bash
# All currencies
uv run python scripts/gengi.py

# Specific currencies
uv run python scripts/gengi.py USD,EUR,GBP
```

## Output

```json
{
  "USD": { "rate": 137.5, "description": "Us dollar" },
  "EUR": { "rate": 149.2, "description": "Euro" }
}
```

## Caveats

- Borgun card rates — includes markup, not interbank/Central Bank rates
- For official rates use Sedlabanki SDMX API instead
- Single snapshot, no historical data
- Rate updates during business hours only

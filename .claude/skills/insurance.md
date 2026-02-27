# Insurance — Icelandic Insurance Market

## Companies

| Company | Kennitala | Parent | Listed | Notes |
|---------|-----------|--------|--------|-------|
| VÍS tryggingar hf. | `6701120470` | Skagi hf. (`6906892009`) | SKAGI | Insurance ops transferred Jan 2025 |
| Sjóvá-Almennar tryggingar hf. | `6509091270` | Independent | SJOVA | Largest by premiums |
| TM tryggingar hf. | `6602693399` | Kvika → Landsbankinn | — | Sale pending competition approval |
| Vörður tryggingar hf. | `4410993399` | Arion banki | — | Bank subsidiary |

**Use Skagi (`6906892009`) for VÍS consolidated data** — the `6701120470` entity is a newly created operating company with limited standalone history.

## Key Metrics

- **Combined ratio** = loss ratio + expense ratio + reinsurance ratio
- **Loss ratio** (tjónahlutfall) = claims / premiums
- **Expense ratio** (kostnaðarhlutfall) = operating expenses / premiums
- **Samsett hlutfall** = Icelandic term for combined ratio

## Data Sources

### Annual reports (skatturinn.is)
```bash
uv run python scripts/skatturinn.py download 6906892009 --year 2024  # Skagi/VÍS
uv run python scripts/skatturinn.py download 6509091270 --year 2024  # Sjóvá
uv run python scripts/skatturinn.py download 6602693399 --year 2024  # TM
uv run python scripts/skatturinn.py download 4410993399 --year 2024  # Vörður
```

### Extraction
```bash
uv run python scripts/financials.py extract data/raw/skatturinn/6906892009_2024.pdf --format markdown
```

Insurance PDFs use IFRS 17 format. Key tables:
- "Helstu niðurstöður og lykiltölur" — has CR, loss ratio, expense ratio, ROE
- "Samsett hlutfall" table in notes — has 5-year history

### FME (Fjármálaeftirlitið)
- Regulatory filings, solvency ratios
- No public API — data from annual reports

### Nordic peers for comparison
- **Gjensidige** (Norway) — gjensidige.no investor relations
- **Tryg** (Denmark) — tryg.com investor relations
- **Sampo/If** (Finland) — sampo.com investor relations

## Processed Data

- `data/processed/insurance_company_financials.csv` — company-level metrics
- `data/processed/insurance_combined_ratios.csv` — CR by company and country
- `data/processed/insurance_nordic_comparison.csv` — Iceland vs Nordic averages

## Typical Values (2024)

| Company | CR | ROE | Equity (B ISK) |
|---------|-----|------|----------------|
| Sjóvá | 96.2% | 17.5% | 25.1 |
| Skagi/VÍS | 97.1% | 11.3% | 22.2 |
| TM | 93.9% | ~15% | 23.2 |
| Vörður | 88.9% | 30.8% | 13.8 |
| **Nordic avg** | **~84%** | **~20%** | — |

## Caveats

1. **IFRS 17 restatements** — 2022+ data uses IFRS 17; earlier years may be restated. Always use the most recent report's comparison figures.
2. **Skagi vs VÍS** — Skagi is the listed group; VÍS is the insurance operating company. Use Skagi for consolidated financials.
3. **TM comparison** — TM doesn't capitalize interest on installment premium payments, affecting CR comparability.
4. **Fiscal years** — All use calendar year (Jan-Dec).

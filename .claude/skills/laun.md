# Payday.is Salary Calculator (Laun)

Icelandic take-home salary calculator via payday.is public API.

## API

- **Endpoint:** `POST https://payday.is/is/ajax/calculator/calculateSalary/`
- **Auth:** None (public XHR, requires `X-Requested-With: XMLHttpRequest`)
- **Format:** JSON request/response

## Input Modes

1. **Gross salary** — set `Salary`, leave `TotalCost` null
2. **Employer total cost** — set `TotalCost`, leave `Salary` null

## 2025 Default Rates

| Parameter | Default | Description |
|-----------|---------|-------------|
| PensionContributionEmployeePercentage | 4.00% | Mandatory employee pension |
| PensionContributionEmployerPercentage | 11.50% | Mandatory employer pension |
| RehabilitationFundPercentage | 0.10% | Starfsendurhæfingarsjóður |
| IncomeTaxStep1Percentage | 31.49% | Up to ~446,136/mo |
| IncomeTaxStep2Percentage | 37.99% | 446,136–1,252,501/mo |
| IncomeTaxStep3Percentage | 46.29% | Above 1,252,501/mo |
| InsuranceFeePercentage | 6.35% | Tryggingagjald (employer) |
| PersonalTaxAllowancePercentage | 100% | Persónuafsláttur (72,492 kr/mo in 2025) |

## Usage

```bash
# Monthly gross -> take-home
uv run python scripts/laun.py 1000000

# From employer total cost
uv run python scripts/laun.py 1200000 --total-cost

# With union fee
uv run python scripts/laun.py 750000 --union 1.1

# Full JSON breakdown
uv run python scripts/laun.py 1000000 --json

# Additional voluntary pension (viðbótarlífeyrissparnaður)
uv run python scripts/laun.py 1000000 --additional-pension 4.0
```

## Response Fields

Key fields in the JSON response `data`:
- `salary` — gross monthly salary
- `totalCost` — total employer cost
- `payoutAmountSalary` — take-home pay
- `incomeTaxEmployeeTotalAmount` — total income tax
- `pensionContributionEmployeeTotalAmount` — employee pension
- `personalTaxAllowanceAmount` — tax credit applied

## Caveats

- Tax rates change yearly — defaults are 2025 rates baked into payday.is
- Union fee varies by union (typically 0.7–1.25%)
- Does not account for benefits in kind, car allowance, etc.
- Personal tax allowance is per-person; couples can transfer unused allowance via `SpouseTaxAllowancePercentage`

---
name: income-distribution
description: Icelandic income distribution — Hagstofan TEK01001 by source/age/gender (mean+median) plus tax-burden CSVs via scripts/income_distribution.py.
---

# Income distribution (TEK01001)

Hagstofan income-by-source statistics: mean and median income by income type,
age band and gender, 1990–2024. PX-Web table TEK01001 at

```
https://px.hagstofa.is/pxis/api/v1/is/Samfelag/launogtekjur/3_tekjur/1_tekjur_skattframtol/TEK01001.px
```

```bash
uv run python scripts/income_distribution.py
```

Writes six tidy CSVs to `data/processed/`: `income_by_source.csv`,
`income_by_source_gender.csv`, `income_by_age.csv`, `tax_burden.csv` (all
TEK01001 cuts) plus `total_income_distribution.csv` (TEK01006) and
`employment_income_distribution.csv` (TEK01007).

Code cheatsheet — `Tekjur og skattar`: 0=Heildartekjur, 1=Atvinnutekjur,
2=Fjármagnstekjur, 3=Aðrar tekjur, 4=Skattar, 5=Ráðstöfunartekjur
(disposable). `Eining`: 0=mean, 2=median. `Kyn`: 0=all. `Aldur`: 0=all,
Y16-64, Y25-54, 5-year bands 16–85+.

Gotchas that bite:

- **Values are in thousands of ISK**, not ISK — 8080 is 8,080,000 kr.
- `Eining=2` is the **median**, not a second mean — treating both columns as
  means silently double-counts.
- The PX response is **UTF-8 with a BOM** — decode `utf-8-sig` or the first
  header carries `\ufeff`.
- Income-type rows include taxes (4) and disposable income (5) — never sum
  across rows to get "total income"; 0 is already the total.

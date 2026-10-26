---
name: tekjusagan
description: Icelandic income history (tekjusagan.is) — disposable income, assets/debt, gender×education by decile 1991–2024, via the site's JSON API.
---

# Tekjusagan — "The Income Story" (Prime Minister's Office)

**Requires:** Tier 0 (core).

Iceland's most widely cited public income/inequality tool: how living standards
moved for demographic groups since 1991 (income, assets, gender, education).
Owned by **Forsætisráðuneytið**; data from Hagstofa Íslands. Credit both.

**All amounts are monthly ISK at constant 2024 prices** ("Allar fjárhæðir eru í
íslenskum krónum á föstu verðlagi ársins 2024" — the site's disclaimer; monthly
is inferred from magnitude: a couple's employment income is ~1.7M in 2024).
`growth_rate` is a fraction per year (0.0621 = 6.21%).

## API

The Angular SPA was redeployed on 2026-10-15 and **no longer uses Power BI**.
It charts JSON from its own backend — open, no token, no browser:

```
POST https://tekjusagan.is/api/sqlseries/<queryId>?from=1991&to=2024
Content-Type: application/json
{ "<filter>": "<value>" | ["<value>", ...], ... }
-> {"items": [{"Skattár", "Breyta Heiti", "Breyta Lýsing", "Breyta Röðun",
               "Breytugildi ISK", "Breytugildi Prósenta"}, ...]}
```

Each queryId is a SQL Server stored procedure (`<queryId>Series`), and the body
keys are its parameters — **exactly** its parameters. The backend relays the SQL
error, which is the fastest way to discover a body:

| Response | Meaning |
|---|---|
| 400 `expects parameter '@Búseta'` | add that key |
| 400 `too many arguments specified` | drop a key (usually `Breyta`) |
| 400 `Stored procedure is not available as a series.` | unknown queryId |
| 200 `{"items": []}` | parameters fine, a **value** matches nothing (typo) |

| Slug | Route | queryId | Body keys |
|---|---|---|---|
| `radstofun` | `/skyrslur/radstofun` | `IncomeVariables` | Aldurshópur, Tekjubil, Börn, Búseta, Hjúskaparstaða, Líkan, **Breyta**, Hópur |
| `eignirskuldir` | `/skyrslur/eignirskuldir` | `AssetVariables` | Aldurshópur, Tekjubil, Börn, Búseta, Hjúskaparstaða, Líkan, Hópur |
| `kynmenntun` | `/skyrslur/kynmenntun` | `GenderEducationVariables` | Aldurshópur, Tekjubil, Búseta, Hjúskaparstaða, Líkan, Menntunarstig |

Other endpoints the SPA calls (not wrapped by the script):
`POST /api/sqldata/GenderEducationGroups`, `GenderEducationGroupDistribution`
(kynmenntun detail), `incomemobilitydeciledistribution`,
`incomemobilitynumberpeople` (Lífshlaupið), `myincomedecile`
(`{Year, AgeGroup, MonthlySalary}`).

## Filter values

The values are labels, not codes; a near-miss returns zero rows, not an error.

- **Tekjubil**: `Tekjubil 1` … `Tekjubil 10`, `Tekjubil 1-10` (all deciles)
- **Aldurshópur**: `25 - 34 ára`, `35 - 49 ára`, `50 - 65 ára`, `66+ ára`, `25 - 64 ára`; seniors (not kynmenntun): `68+ ára`, `71+ ára`, `75+ ára`, `68-75 ára` (no spaces around the dash in that last one)
- **Hópur**: `Allir í aldursbili`, `Fá greitt frá TR` (receives social-insurance pension)
- **Búseta**: `Höfuðborg`, `Landsbyggð`, `Landið allt`
- **Börn**: `Engin börn`, `1 - 2 börn`, `3 eða fleiri börn`
- **Hjúskaparstaða** (radstofun/eignirskuldir): `Hjón`, or for singles the value depends on Börn — `Einstæðingur karl`/`Einstæðingur kona` with `Engin börn`, else `Einstætt foreldri karl`/`Einstætt foreldri kona`
- **Hjúskaparstaða** (kynmenntun): `Einhleypur karl`, `Einhleyp kona`, `Karl í sambúð`, `Kona í sambúð`, `Öll kyn óháð hjúskap`
- **Líkan**: `T3 - Tíundir eftir atvinnutekjum og bótum` (without capital income) or `T2 - Tíundir eftir atvinnutekjum, bótum og fjármagnstekjum` (with); kynmenntun uses `Raðað í tekjutíundir eftir heildartekjum með fjármagnstekjum`
- **Menntunarstig**: `Óháð menntun`, `Grunnmenntun`, `Framhaldsskóli`, `Viðbótarstig`, `Háskóli - Diploma`, `Háskóli (BSc)`, `Háskóli (MSc)`, `Háskóli (PhD)`

**Breyta (radstofun only) selects homeowner vs renter rows**, and it is the
only thing that does — "Fasteign" is not a parameter. The script defaults to the
homeowner, no-capital-income list. Renter (T3) list:
`Atvinnutekjur|Lífeyrissjóðstekjur|Bætur frá ríki og sveitarfélögum|Barnabætur|Húsnæðisbætur|Tekjuskattur|Ráðstöfunartekjur leigjendur|Tímabil 1991 - 2007 leigjendur|Tímabil 2007 - 2012 leigjendur|Ráðstöfunartekjur leigutaka án fjármagnstekna vöxtur frá 2012`.
The with-capital-income (T2) variants are in the SPA bundle's page config
(`setQueryFilters` under the Fjármagnstekjur/Fasteign filters).

Disposable income is **not** a row: the `Ráðstöfunartekjur…` row comes back
with both values null, and the SPA sums the ISK component rows (taxes are
negative). `tidy()` drops those header rows.

## Script

```bash
uv run python scripts/tekjusagan.py list                       # series + default bodies
uv run python scripts/tekjusagan.py fetch                      # all three, SPA defaults
uv run python scripts/tekjusagan.py fetch --series radstofun --set "Tekjubil=Tekjubil 1"
uv run python scripts/tekjusagan.py fetch --series radstofun --set "Breyta=Atvinnutekjur|Tekjuskattur"
```

Writes `data/raw/tekjusagan/{slug}.json` (request body + items) and
`data/processed/tekjusagan_{slug}.csv`: `series, tax_year, variable, label,
sort_order, value_isk, growth_rate` plus one column per filter, so each CSV says
which group it describes. One fetch = one group; loop `--set` for comparisons.

## Caveats

1. **The SPA hardcodes the year range** (`firstTaxYear = 1991`,
   `selectedTaxYear = 2024`). When 2025 data lands, `LAST_TAX_YEAR` in the
   script needs bumping; `to=2026` today simply returns through 2024.
2. **Bundle hashes change on every deploy** — find config by searching the
   chunks for `queryId:` / `/api/sql`, never by filename. The page config
   (`var ku=[{page:"radstofun",...}]`) evaluates as a plain JS literal.
3. **Every SPA route returns 200 index.html**, including dead ones and dead
   `/api/...` paths — check `content-type` before trusting a 200.
4. **Prefer Hagstofa for analysis.** Tekjusagan is a curated view of TEK
   series (TEK01001, TEK01101, TEK01106, TEK01401 via the `hagstofan` skill);
   use it when you want *its* group definitions (decile × household type ×
   tenure), not as a substitute for the raw tables.

## Complementary sources

| Source | Overlap |
|--------|---------|
| [hagstofan](../hagstofan/SKILL.md) | TEK01xxx — canonical tidy data |
| [income-distribution](../income-distribution/SKILL.md) | TEK01001 by source/age/gender |
| [laun](../laun/SKILL.md) | Take-home-salary calculator (prospective, not historical) |

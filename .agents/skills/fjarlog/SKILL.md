---
name: fjarlog
description: Icelandic state budget (fjárlög) — appropriations + 5-year plan by málaflokkur: actuals, enacted, bill, plan. Defense = 04.30.
---

# Fjárlög — Icelandic state budget (appropriations + 5-year plan)

The **forward-looking** counterpart to [rikisreikningur](../rikisreikningur/SKILL.md)
(which is *actuals*). Where ríkisreikningur answers "what was spent",
fjárlög answers "what was appropriated / planned". The newspaper tables on
defense, NATO targets, etc. are drawn from here — specifically from the
**fjármálaáætlun** (5-year fiscal plan) and the annual **fjárlagafrumvarp**
(budget bill), published by **Fjármála- og efnahagsráðuneytið** on
`stjornarradid.is`.

## Source

Per budget year there is a "Skjöl og gögn" page, e.g.
`https://www.stjornarradid.is/verkefni/opinber-fjarmal/fjarlog/fjarlog-fyrir-arid-2026/skjol-og-gogn/`

It links PDFs (frumvarp, samþykkt fjárlög, fylgirit) **and one machine-readable
CSV**: *"Talnagögn úr fjárlagafrumvarpi"*. That single CSV is the whole budget
at the level Alþingi appropriates it, and it is what this skill targets.

- Filename carries a version suffix that changes between revisions
  (`… - 003.csv`), so the script **discovers** the link from the page HTML
  rather than hard-coding it (regex on `href=".*[Tt]alnag.*\.csv"`).
- Sibling pages: `fjarmalaaaetlun/fjarmalaaaetlun-2026-2030/skjol-og-gogn/`
  (the 5-year plan), and `…/fjarlog-fyrir-arid-{Y}/fylgirit/` for the PDF
  "Yfirlit 3 — Fjárveitingar eftir málaflokkum og ráðuneytum".

No API key, no auth. Plain file download over HTTPS.

## CSV schema (semicolon-delimited, UTF-8 BOM)

| Column | Meaning |
|--------|---------|
| `Ár` | year |
| `Afurð` | **data product** — see below |
| `FlokkunNy` | (mostly empty; new-classification flag) |
| `Málefnasvið` | policy area, `"04 Utanríkismál"` (01–36) |
| `Málaflokkur` | policy sub-area, `"04.30 Samstarf um öryggis- og varnarmál"` |
| `Ráðuneyti` | ministry, `"02 Utanríkisráðuneyti"` |
| `Liður` | institution group |
| `Viðfang` | appropriation item, `"101 Varnarmál"` |
| `TegundNota` | **view** discriminator — see below |
| `Upphæð` | amount in **m.kr** (millions ISK) |

One file spans four `Afurð` products in one long table:

| Afurð | Years (in 2026 file) | Meaning |
|-------|----------------------|---------|
| `Ríkisreikningur` | 2024 | final state-accounts **actuals** (outturn) |
| `Fjárlög` | 2025 | **enacted** budget, prior year |
| `Frumvarp` | 2026 | the budget **bill** for the budget year |
| `Áætlun` | 2027–2028 | fiscal-**plan** projection |

### TegundNota is a *view*, never sum across it

The same money appears under several `TegundNota` values. Pick one; do **not**
add them up:

- `Gjöld` / `Heildarútgjöld` — **gross expenditure** (use for "spending")
- `Tekjur` / `Rekstrartekjur` — revenue / own-revenue (sértekjur)
- `Greiðsla` / `Fjárhæð` — net cash / net appropriation
- `Rekstrarframlög` + `Rekstrartilfærslur` + `Fjárfestingarframlög`
  (+ `Fjármagnstilfærslur`) — the funding-component breakdown that **sums to
  Heildarútgjöld**

## Defense — the worked example

Defense is málaflokkur **04.30 "Samstarf um öryggis- og varnarmál"**
(viðfang `101 Varnarmál` + `601 Tæki og búnaður`), under the
Utanríkisráðuneyti.

```
uv run python scripts/fjarlog.py mala 04.30        # Gjöld, all products
```

| Year | Afurð | Gjöld (m.kr) |
|------|-------|-------------:|
| 2024 | Ríkisreikningur (actual) | **6,553** |
| 2025 | Fjárlög (enacted) | 6,821 |
| 2026 | Frumvarp (bill) | **10,404** |

The 2026 bill figure (10.4 bn) matches the press characterisation of
*"bein útgjöld til varnar- og öryggismála … um 10,6 milljörðum … 0,22% af VLF"*.

⚠️ **The broad "varnar- og öryggismál" 0,9 %-of-GDP aggregate is NOT this
line.** That ~43–53 bn / 0.88–1.00 % series (Minnisblað fjármála- og
efnahagsráðuneytis, A1 + A3 + C-hluti + sveitarfélög) is a bespoke
cross-cutting construct: it folds in parts of the coast guard
(09.20 Landhelgi), civil defence (almannavarnir), cyber/network defence and
airport/harbour readiness on top of 04.30. It cannot be reproduced by summing a
single málaflokkur, and it lives only in the ministry memo, not in this CSV.
The raw heimamundur ledger in [rikisreikningur](../rikisreikningur/SKILL.md) slices
04.30 by *economic type* and yields a smaller ~3.2 bn — that is an artefact of
how grant-funded operations are booked, **not** the headline defense number.
Use the budget CSV's `Gjöld` (6.55 bn for 2024) as the official figure.

## Usage

```bash
uv run python scripts/fjarlog.py fetch                 # download + tidy → data/processed/fjarlog.parquet
uv run python scripts/fjarlog.py fetch --year 2026     # choose budget-year page
uv run python scripts/fjarlog.py products              # afurð × year coverage
uv run python scripts/fjarlog.py mala 04.30            # one málaflokkur across years (Gjöld)
uv run python scripts/fjarlog.py mala 04.30 --tegund Heildarútgjöld
```

Processed output `data/processed/fjarlog.parquet` columns: `ar, afurd,
flokkun_ny, malefnasvid, malefnasvid_nr, malaflokkur, malaflokkur_nr,
raduneyti, lidur, vidfang, tegund, mkr`. Query with DuckDB:

```bash
duckdb -c "SELECT ar, afurd, SUM(mkr)/1000 AS bn FROM 'data/processed/fjarlog.parquet'
           WHERE tegund='Gjöld' GROUP BY 1,2 ORDER BY 1"   -- total spending by year
```

## The fylgirit "Yfirlit" CSV exports (alternative source)

The interactive dashboard / fylgirit also lets you export each overview as its
own CSV. These are **SSRS report dumps** — raw `Textbox###` column names, repeated
group-header columns, dotted-leader padding (`"Alþingi   . . . ."`), 3-line
preamble — far messier than the single `Talnagögn` CSV above. Use `Talnagögn`
for programmatic work; reach for these only for cross-check or the revenue side.

| Export | Content | Verdict |
|--------|---------|---------|
| Yfirlit 2 | 2026 appropriations by economic split (rekstur/tilfærslur/fjárfesting) | duplicate of `Talnagögn` |
| **Yfirlit 3** | **2024–2028** by ráðuneyti → málaflokkur → ríkisaðili → viðfang, 5 year columns wide | best cross-check; **extends plan to 2028** |
| Yfirlit 4 | 2026 appropriations by ríkisaðili (entity) | duplicate |
| **Sundurliðun Tekna** (Yfirlit 1) | **A1 REVENUE** side: tax lines (income tax, VAT…), `álagt` (assessed) vs `greiðsla` (cash), 4 years | **not in `Talnagögn`** — the only additive file |

Validation (2025-06): Yfirlit 3 reproduces `Talnagögn` exactly — defense 04.30
= 6,553.3 / 6,820.9 / 10,404.3 m.kr (2024/25/26) and grand total
`Samtals útgjöld` 2024 = 1,491,095.1 m.kr both match. Yfirlit 3 additionally
gives plan years 2027 = 11,403.1 and 2028 = 9,915.3 m.kr for defense.

**Revenue gap:** the `Talnagögn` CSV / `fjarlog.parquet` only carries
per-málaflokkur *own-revenue* (sértekjur, ≤~19 bn rows), **not** the A1 macro
tax revenue (income tax ~304 bn, VAT ~465 bn). For the revenue side use
*Sundurliðun Tekna*. Parsing it means: skip 3 preamble lines, take leaf rows by
revenue key (111 income/profit tax, 112 payroll, 113 property, 114 goods &
services/VAT…), columns `alagt{n}`/`greidsla{n}` are assessed-vs-cash per year.

## Caveats

1. **`mkr` is millions ISK.** Divide by 1000 for billions. Number format
   varies by revision (dot-decimal `6381.1` in the current file; older
   revisions used comma-decimal `6.381,1`) — the script normalises both.
2. **Never sum across `TegundNota`** (see above). Filter to one view first.
3. **Year coverage shifts** with each budget edition: the 2026 file gives
   2024 actual → 2028 plan. Re-`fetch` to roll the window forward; pass
   `--year` to target a specific edition's page.
4. **Gross vs net.** `Gjöld`/`Heildarútgjöld` are gross of own-revenue; the
   málaflokkur-level totals are *before* inter-entity eliminations, so the
   project-wide sum (~1,491 bn for 2024) runs above the consolidated
   ríkisreikningur expenditure (~1,245 bn).
5. **Defense definition.** 04.30 = direct defense only. The 0.9 %-of-GDP
   "varnar- og öryggismál" aggregate is a separate ministry construct (see
   the worked example above).
6. **Discovery fallback.** If the page layout changes and the CSV link can't
   be found, the script falls back to a hard-coded 2026 URL and prints a
   warning — re-point `_FALLBACK_CSV` if needed.

## Related

- [rikisreikningur](../rikisreikningur/SKILL.md) — actuals (outturn); pairs with this skill's plan/appropriations
- [opnirreikningar](../opnirreikningar/SKILL.md) — invoice-level government spending
- [hagstofan](../hagstofan/SKILL.md) — GFS-standard fiscal aggregates (THJ tables), GDP (VLF) for %-of-GDP ratios

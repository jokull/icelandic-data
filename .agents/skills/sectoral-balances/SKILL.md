---
name: sectoral-balances
description: Iceland current account decomposition, NIIP attribution, pension fund foreign assets, Godley/MMT sectoral balances identity.
---

# Sectoral Balances & External Sector (Iceland)

**Requires:** Tier 0 (core).

Analytical skill for computing sectoral financial balances in the Godley/MMT accounting sense:

```
Private sector surplus = Government deficit + Current account surplus
```

…and related external-sector analysis: current account decomposition, NIIP attribution, pension-fund foreign asset holdings, who-owes-whom.

## When to use

- "Is the current account deficit driven by goods or services?"
- "How much of Iceland's positive NIIP comes from pension funds?"
- "Government surplus / deficit as % of GDP"
- "Private sector saving vs investment vs external balance"
- "Attribute Iceland's foreign asset position by holder sector"

## Primary data sources

All core series are on Hagstofan's PX-Web API (`https://px.hagstofa.is/pxis/api/v1/is/`). Seðlabanki's SDMX (`fr.sedlabanki.is`) has the authoritative quarterly BoP and IIP, but the endpoint is often unreachable from outside Iceland — fall back to Hagstofan + FSR PDFs.

| Purpose | Source | Table | Period | Freq |
|---|---|---|---|---|
| Current account (full decomposition) | Hagstofan | `THJ01102` | 1995–2025 | annual |
| Goods & services bridge to BoP basis | Hagstofan | `UTA05002` | 1995Q1–2025Q4 | quarterly |
| Goods & services bridge (monthly) | Hagstofan | `UTA05000` | 2018m1–2025m12 | monthly |
| Services trade detail | Hagstofan | `UTA04005`–`UTA04010` | 2009/2013–2024 | Q/annual |
| Financial accounts by sector (stocks) | Hagstofan | `THJ10001` | 2003–2024 | annual |
| Financial accounts as % of GDP | Hagstofan | `THJ10002` | 2003–2024 | annual |
| Government headline fiscal balance | Hagstofan | `THJ05111` | 1980–2025 | annual |
| Government revenue/expenditure/flow | Hagstofan | `THJ05123` | 1980–2025 | annual |
| Government fiscal, quarterly | Hagstofan | `fjarmal_arsfj/*` | — | quarterly |
| Government assets & debt | Hagstofan | `THJ05181` | 1998–2025 | annual |
| NIIP breakdown by instrument & sector | Seðlabanki FSR PDF | — | annual | — |
| Pension fund foreign asset share | Seðlabanki FSR PDF | — | annual | — |

## Table cheat-sheets

### `THJ01102` — Current account from SNA

Rows use zero-based API codes, **not the numbered labels**. Verified September 2026:

| API code | Label | Meaning |
|---|---|---|
| `11` | 8. Verg landsframleiðsla | Nominal GDP |
| `18` | 11. Viðskiptajöfnuður án rekstrarframlaga | CA excluding secondary transfers |
| `19` | 11.1 Vöruskiptajöfnuður fob/fob | Goods balance |
| `20` | 11.2 Þjónustujöfnuður | Services balance |
| `21` | 11.3 Launa- og eignatekjur frá útlöndum, nettó | Primary income |
| `24` | 14. Rekstrarframlög, nettó frá útlöndum | Secondary income |

Full current account = codes `18 + 24` (or `19 + 20 + 21 + 24`).
**Unit:** millions ISK, nominal. Fetch metadata to resolve other rows; label numbers are not API codes.

### `UTA05002` — BoP bridge table, quarterly

35 line items, reconciles customs-basis goods/services data with BoP-basis. Key rows:

| Code | Meaning |
|---|---|
| `21` | Vöruskiptajöfnuður í greiðslujöfnuði (goods balance, BoP basis) |
| `31` | Þjónustujöfnuður (services balance) |
| `32` | Vöru- og þjónustuviðskipti, útflutningur alls |
| `33` | Vöru- og þjónustuviðskipti, innflutningur alls |
| `34` | Vöru- og þjónustujöfnuður í greiðslujöfnuði |

Use this for quarterly time series; use `THJ01102` for full-CA annual decomposition.

### `THJ10001` — Financial accounts (sectoral)

Three dimensions:

- **`Efnahagsgeirar`** — sector code (S0=all, S1=resident, S11=non-financial corps, S12=financial corps, S13=government, S14=households, **S129=pension funds**, **S2=rest of world**, …)
- **`Fjármálagerningar`** — instrument (FA0=total assets, FL0=total liabilities, BF90=net = FA0 − FL0, and the FA1–FA8 / FL1–FL8 sub-instruments)
- **`Mælikvarði`** — `Stocks 31/12` (year-end position), `Transactions`, `Revaluation`, `Other volume changes`

**Reading the external position from this table:**

- `S2 Útlönd` × `BF90` × `Stocks 31/12` = rest-of-world's net position against Iceland
- Iceland's NIIP = −BF90(S2). A **negative** S2 BF90 means Iceland is a **net foreign creditor**.
- `S129 Lífeyrissjóðir` × `FA0` × `Stocks 31/12` = pension fund total financial assets
- This table does **not** provide a direct "pension fund foreign assets" breakdown — for that, see Seðlabanki FSR.

### Government sector — `THJ05111`

Contains headline numbers: revenue, expenditure, primary balance, overall balance, gross debt, net debt — for general government, central government, local government. Use this for the fiscal side of the sectoral balances identity.

## Example queries

### Full annual current account decomposition

```bash
curl -s -X POST \
  "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/THJ01102.px" \
  -H "Content-Type: application/json" \
  -d '{
    "query": [
      {"code": "Skipting", "selection": {"filter": "item",
        "values": ["11","18","19","20","21","24"]}}
    ],
    "response": {"format": "csv"}
  }' -o current_account_annual.csv
```

### Quarterly goods & services BoP bridge (last 10 years)

```bash
curl -s -X POST \
  "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/utanrikisverslun/3_voruthjonusta/voruthjonusta/UTA05002.px" \
  -H "Content-Type: application/json" \
  -d '{
    "query": [
      {"code": "Skipting", "selection": {"filter": "item", "values": ["21","31","32","33","34"]}}
    ],
    "response": {"format": "csv"}
  }' -o bop_bridge_qtr.csv
```

### Financial accounts — pension funds, rest of world, all-sectors totals

```bash
curl -s -X POST \
  "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/thjodhagsreikningar/fjarmalareikningar/fjarmalareikningar/THJ10001.px" \
  -H "Content-Type: application/json" \
  -d '{
    "query": [
      {"code": "Efnahagsgeirar", "selection": {"filter": "item", "values": ["S0","S129","S2"]}},
      {"code": "Fjármálagerningar", "selection": {"filter": "item", "values": ["FA0","FL0","BF90"]}},
      {"code": "Mælikvarði", "selection": {"filter": "item", "values": ["Stocks 31/12"]}}
    ],
    "response": {"format": "csv"}
  }' -o financial_accounts_stocks.csv
```

### Government headline fiscal balance

```bash
curl -s -X POST \
  "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/fjaropinber/fjarmal_opinber/fjarmal_opinber/THJ05111.px" \
  -H "Content-Type: application/json" \
  -d '{"query": [], "response": {"format": "csv"}}' -o government_headline.csv
```

## Computing sectoral financial balances

With consistent net-lending definitions: domestic non-government + general government + rest of world = 0. A surplus is positive. The familiar simplified identity is private surplus = government **deficit** + current-account surplus (not minus government deficit). Capital-account items and statistical discrepancies must be reconciled before substituting the current account for external net lending.

For a directly reported financial-account measure, use `THJ10001` with `Mælikvarði=Transactions`: FA0 minus FL0 for each sector. Combine S11 + S12 + S14 + S15 as domestic non-government; S13 is general government and S2 is rest of world. This includes financial corporations (including S121, the central bank, per national accounts sectoring); do not call it households alone. Never use balance-sheet stocks or stock differences as net lending.

Divide by nominal GDP, `THJ01102` code `11`, for the matching year. Keep financial-account balances distinct from nonfinancial-account net lending and the current account: discrepancies between these measures can be material. Financial accounts currently run through 2024; national accounts through 2025 (checked September 2026).

## NIIP attribution (the pension fund story)

Seðlabanki's *Fjármálastöðugleiki* (FSR) publishes the authoritative NIIP and pension fund foreign-asset breakdown. As of FSR 2026/1 (end-2025):

- **NIIP:** +44% of GDP ("Erlendar fjáreignir innlendra aðila umfram skuldir þeirra við erlenda aðila námu um 44% af vergri landsframleiðslu í lok árs 2025")
- **Pension fund total assets:** 8,878 bn ISK = 179% of GDP
- **Pension fund foreign assets:** 42% of total = ~70% of GDP
- **Seðlabanki's own attribution:** *"Jákvæða erlenda stöðu má fyrst og fremst rekja til erlendra eigna lífeyrissjóða"* — i.e. pension fund foreign holdings exceed Iceland's entire NIIP; the rest of the economy is a net foreign debtor.

FSR PDFs are already extracted to `data/processed/fsr_narrative/` (via docling). Grep there for `lífeyris|erlend` when you need the latest figures:

```bash
rg -n "lífeyris|erlend|NIIP|erlend staða" data/processed/fsr_narrative/fsr_2026_1_docling.md
```

Seðlabanki also publishes a standalone *Greiðslujöfnuður, ytri staða og áhættuþættir* report (October each year) with the full NIIP decomposition by instrument, sector and currency.

## Caveats

1. **Flows vs stocks confusion.** The current account is a *flow* (annual). The NIIP is a *stock* (cumulative). A small CA deficit (a flow) is entirely consistent with a large positive NIIP (a stock accumulated over decades) — especially when pension fund foreign holdings swamp the annual flow. Don't attribute CA deficits to pension funds "diversifying abroad" — that's a capital outflow, which is associated with a CA *surplus*, not a deficit.

2. **Sign convention on S2 Útlönd.** `BF90` for `S2` is the *rest-of-world's* net position *against Iceland*. A negative value means rest-of-world owes Iceland more than it owns in Iceland → Iceland is a net creditor. Flip the sign when reporting Iceland's NIIP.

3. **FA0 – FL0 on S129 is ~0 by construction.** Pension funds' liabilities are accrued pension entitlements to their members, which roughly match their assets. The interesting question is not their net position but the *asset-side composition* (domestic vs foreign) — that's in Seðlabanki, not Hagstofan.

4. **`Launa- og eignatekjur` is primary income on the CA.** High ISK policy rates make foreign investors earn a lot on ISK holdings, which pushes net primary income *negative* even when Iceland is a net foreign creditor. This is counterintuitive but correct: stocks and flows tell different stories.

5. **Secondary income is small but nonzero** (~−1% of GDP, mostly EU contributions and remittances) — remember to add it for the full CA.

6. **Seðlabanki SDMX is often unreachable.** The `fr.sedlabanki.is` endpoint times out from many networks. Prefer Hagstofan PX-Web + FSR PDF extraction.

## Key reference facts (end-2024 / end-2025)

Burn these in for quick sanity checks during analysis:

- Nominal GDP: ≈ 4,578 bn ISK (2024), ≈ 4,956 bn ISK (2025)
- Goods balance: ~−323 bn (2024, −7.1% GDP) / ~−385 bn (2025, −7.8%)
- Services balance: ~+265 bn (2024, +5.8% GDP) / ~+273 bn (2025, +5.5%)
- Current account (incl transfers): ~−149 bn (2024, −3.2% GDP) / ~−178 bn (2025, −3.6%)
- NIIP: +44% of GDP (end-2025, FSR 2026/1)
- Pension fund total assets: 8,878 bn ISK = 179% GDP
- Pension fund foreign assets: 42% of portfolio ≈ 70% of GDP

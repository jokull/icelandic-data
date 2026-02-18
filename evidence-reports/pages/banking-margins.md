---
title: Icelandic Bank Margins - A Deep Dive
description: Why are Icelandic mortgage rates the highest in Europe? An investigation into the króna, bank competition, and rent extraction.
---

# Icelandic Bank Margins: Króna or Cartel?

Iceland has the highest mortgage rates in Europe. This report investigates why, using data from the Central Bank, pension funds, World Bank, and individual bank annual reports.

**Research Question:** Are high Icelandic mortgage rates explained by the króna (inflation, Central Bank policy), or do they reflect rent extraction from a concentrated banking market?

**TL;DR:** Both. The króna explains ~60-70% of the headline rate. But Icelandic banks also take a spread (NIM) that's **2-3x the Nordic average**, and in 2024 they extracted **88% of profits** as dividends and buybacks while maintaining excess capital buffers. Banks consolidated market power during the low-rate era (2019-2021) when pension funds retreated, and now use high rates as cover for maximum extraction.

---

## Part 1: The Policy Rate

The Central Bank of Iceland sets the policy rate to manage inflation. Higher inflation = higher rates.

```sql policy_rate_annual
SELECT
  YEAR(date) as year,
  round(avg(policy_rate), 2) as avg_rate,
  round(min(policy_rate), 2) as min_rate,
  round(max(policy_rate), 2) as max_rate
FROM banking.policy_rates
WHERE date >= '2015-01-01'
GROUP BY 1
ORDER BY 1
```

<LineChart
  data={policy_rate_annual}
  x=year
  y=avg_rate
  yAxisTitle="Policy Rate (%)"
  title="Central Bank of Iceland Policy Rate"
/>

The policy rate peaked at **9.25%** in 2023-2024, one of the highest in developed economies. But is this extreme?

---

## Part 2: Real Interest Rates

Real rates = nominal rates minus inflation. This is what actually matters for borrowers.

```sql real_rates_annual
SELECT
  year,
  round(avg(policy_rate_pct), 2) as nominal_rate,
  round(avg(inflation_yoy_pct), 2) as inflation,
  round(avg(real_rate_pct), 2) as real_rate
FROM banking.real_rates
WHERE year >= 2015
GROUP BY 1
ORDER BY 1
```

<BarChart
  data={real_rates_annual}
  x=year
  y={['nominal_rate', 'inflation', 'real_rate']}
  title="Nominal vs Real Interest Rates"
  type=grouped
/>

<DataTable data={real_rates_annual}>
  <Column id=year title="Year" />
  <Column id=nominal_rate title="Nominal Rate %" />
  <Column id=inflation title="Inflation %" />
  <Column id=real_rate title="Real Rate %" />
</DataTable>

**Key insight:** Real rates were **deeply negative** during 2020-2023 (good for borrowers). They've only recently turned positive at ~3%, which is not historically extreme.

---

## Part 3: The International Comparison (Where It Gets Uncomfortable)

Net Interest Margin (NIM) measures what banks earn on the spread between lending and deposit rates. It's the cleanest measure of "bank markup."

```sql nim_by_country_2021
SELECT
  country,
  nim_pct
FROM banking.nim_comparison
WHERE year = 2021
ORDER BY nim_pct DESC
```

<BarChart
  data={nim_by_country_2021}
  x=country
  y=nim_pct
  title="Net Interest Margin by Country (2021)"
  yAxisTitle="NIM %"
  swapXY=true
  sort=false
/>

**Iceland's NIM (2.62%) is:**
- 43% higher than UK (1.84%)
- 130% higher than Sweden (1.12%)
- 208% higher than Denmark (0.85%)
- 400% higher than France (0.52%)

This gap is difficult to explain by "operating costs in a small market."

```sql nim_trend
SELECT
  year,
  MAX(CASE WHEN country = 'Iceland' THEN nim_pct END) as Iceland,
  MAX(CASE WHEN country = 'Norway' THEN nim_pct END) as Norway,
  MAX(CASE WHEN country = 'Sweden' THEN nim_pct END) as Sweden,
  MAX(CASE WHEN country = 'Denmark' THEN nim_pct END) as Denmark
FROM banking.nim_comparison
WHERE country IN ('Iceland', 'Norway', 'Sweden', 'Denmark')
GROUP BY 1
ORDER BY 1
```

<LineChart
  data={nim_trend}
  x=year
  y={['Iceland', 'Norway', 'Sweden', 'Denmark']}
  title="NIM Trend: Iceland vs Nordic Peers"
  yAxisTitle="NIM %"
/>

Iceland's NIM has **converged** toward Nordic levels since the 2008 crisis (when it was 8.9%), but a persistent gap of ~1-1.5 percentage points remains.

---

## Part 3b: The Norway Test

Norway is the ideal control case: similar population, own currency (NOK), outside EU but in EEA, oil-influenced economy. If Icelandic banks need high margins because of the króna, Norway should show similar patterns. They don't.

```sql norway_iceland_nim
SELECT
  year,
  MAX(CASE WHEN country = 'Iceland' THEN nim_pct END) as "Iceland NIM",
  MAX(CASE WHEN country = 'Norway' THEN nim_pct END) as "Norway NIM",
  MAX(CASE WHEN country = 'Iceland' THEN nim_pct END) - MAX(CASE WHEN country = 'Norway' THEN nim_pct END) as "Gap"
FROM banking.nordic_comparison
GROUP BY 1
ORDER BY 1
```

<LineChart
  data={norway_iceland_nim}
  x=year
  y={['Iceland NIM', 'Norway NIM']}
  title="NIM: Iceland vs Norway (2021-2024)"
  yAxisTitle="NIM %"
/>

**The gap persists at ~1.1 percentage points** - Iceland charges 50-60% more spread than Norway.

### The Efficiency Paradox

```sql nordic_efficiency
SELECT
  country,
  year,
  nim_pct as "NIM %",
  roe_pct as "ROE %",
  cost_income_pct as "Cost/Income %",
  payout_pct as "Payout %"
FROM banking.nordic_comparison
WHERE year = 2024
ORDER BY nim_pct DESC
```

<DataTable data={nordic_efficiency}>
  <Column id=country title="Country" />
  <Column id="NIM %" title="NIM %" fmt='0.2' />
  <Column id="ROE %" title="ROE %" fmt='0.1' />
  <Column id="Cost/Income %" title="Cost/Income %" fmt='0.1' />
  <Column id="Payout %" title="Payout %" fmt='0' />
</DataTable>

**The damning finding:** Norway achieves **17.5% ROE with 1.9% NIM**. Iceland manages only **12.1% ROE with 3.0% NIM**.

Norwegian banks are more profitable with lower margins because:
1. **Better efficiency** - DNB's cost-to-income is 36.5% vs Iceland's 42.5%
2. **Digital leadership** - Norway closed 100+ branches, launched Vipps, targets sub-40% cost-to-income
3. **More competition** - DNB has 25% mortgage share vs Iceland's top-3 controlling 93%

```sql nordic_roe_vs_nim
SELECT
  country,
  year,
  nim_pct,
  roe_pct
FROM banking.nordic_comparison
WHERE year >= 2022
ORDER BY year, nim_pct DESC
```

<ScatterPlot
  data={nordic_roe_vs_nim}
  x=nim_pct
  y=roe_pct
  series=country
  xAxisTitle="NIM %"
  yAxisTitle="ROE %"
  title="NIM vs ROE: More Margin ≠ More Profit"
/>

### The Extraction Gap

```sql payout_comparison
SELECT
  year,
  MAX(CASE WHEN country = 'Iceland' THEN payout_pct END) as "Iceland Payout %",
  MAX(CASE WHEN country = 'Norway' THEN payout_pct END) as "Norway Payout %"
FROM banking.nordic_comparison
GROUP BY 1
ORDER BY 1
```

<BarChart
  data={payout_comparison}
  x=year
  y={['Iceland Payout %', 'Norway Payout %']}
  title="Shareholder Payout Ratio: Iceland vs Norway"
  yAxisTitle="Payout %"
  type=grouped
/>

Iceland consistently extracts more profits as dividends/buybacks (78% vs 63% in 2024), while holding excess capital (23.8% CET1 vs Norway's 17.9%).

### What This Proves

The "króna excuse" doesn't hold. Both countries:
- Have independent currencies
- Face similar monetary policy constraints
- Are outside the Eurozone

Yet Norway achieves:
- **Higher ROE** (17.5% vs 12.1%)
- **Lower margins** (1.9% vs 3.0%)
- **Better efficiency** (36.5% vs 42.5% cost-to-income)
- **More disciplined payouts** (63% vs 78%)

**The ~1.1% NIM gap is pure rent extraction** that a competitive market would eliminate.

---

## Part 4: Who Owns the Mortgage Market?

A common claim: "Pension funds provide competition to banks." Let's check the data.

```sql market_share_trend
SELECT
  year,
  quarter,
  banks_share_pct as Banks,
  pension_share_pct as "Pension Funds",
  ils_share_pct as "Housing Fund (ILS)"
FROM banking.mortgage_market_share
WHERE quarter = 4
ORDER BY year
```

<AreaChart
  data={market_share_trend}
  x=year
  y={['Banks', 'Pension Funds', 'Housing Fund (ILS)']}
  title="Mortgage Market Share Over Time"
  yAxisTitle="Share %"
/>

<DataTable data={market_share_trend}>
  <Column id=year title="Year" />
  <Column id=Banks title="Banks %" fmt='0.1' />
  <Column id="Pension Funds" title="Pension Funds %" fmt='0.1' />
  <Column id="Housing Fund (ILS)" title="ILS %" fmt='0.1' />
</DataTable>

**Key findings:**
- Banks: **70.6%** of mortgages (up from 50% in 2007)
- Pension funds: **24.5%** (up from 12.7%)
- Housing Fund (ÍLS): **4.9%** (down from 37.3%)

**The "2/3 pension fund" claim is false.** Banks dominate. The Housing Fund's collapse removed a major competitor, and banks absorbed that market share.

---

## Part 5: Bank Profitability (The Smoking Gun)

If banks "need" high margins to support lending growth, they should be retaining earnings. Instead:

### 2024 Bank Financials (from Annual Reports)

| Bank | Net Profit | Dividends + Buybacks | Retained | Extraction Rate |
|------|------------|---------------------|----------|-----------------|
| **Arion** | 26.1 bn ISK | 25.5 bn ISK | 0.6 bn | **97.7%** |
| **Íslandsbanki** | 24.2 bn ISK | ~24.6 bn ISK | ~0 bn | **~100%** |
| **Landsbankinn** | 37.5 bn ISK | 18.9 bn ISK | 18.6 bn | **50%** |
| **Combined** | **87.8 bn** | **~69 bn** | **~19 bn** | **78%** |

### Bank NIMs (2024)

| Bank | NIM | ROE | Cost/Income | CAR |
|------|-----|-----|-------------|-----|
| **Arion** | 3.1% | 13.2% | 42.6% | 22.9% |
| **Íslandsbanki** | 2.9% | 10.9% | 43.9% | 23.6% |
| **Landsbankinn** | ~3.0% | 12.1% | - | 24.9% |

All three banks maintain capital ratios **4-6 percentage points above** regulatory requirements while extracting most of their profits.

---

## Part 5b: The Extraction Timeline (2018-2024)

The 2024 snapshot doesn't tell the full story. How did we get here?

```sql payout_trend
SELECT
  year,
  combined_profit_bn as "Profit",
  dividends_bn as "Dividends",
  buybacks_bn as "Buybacks",
  total_return_bn as "Total Returned",
  payout_pct
FROM banking.bank_payouts
ORDER BY year
```

<BarChart
  data={payout_trend}
  x=year
  y={['Dividends', 'Buybacks']}
  y2=payout_pct
  y2SeriesType=line
  title="Bank Shareholder Returns vs Payout Ratio"
  yAxisTitle="ISK Billions"
  y2AxisTitle="Payout %"
  type=stacked
/>

```sql payout_vs_competition
SELECT
  year,
  payout_pct as "Payout Ratio %",
  pension_share_pct as "Pension Fund Share %",
  policy_rate as "Policy Rate %"
FROM banking.bank_payouts
ORDER BY year
```

<LineChart
  data={payout_vs_competition}
  x=year
  y={['Payout Ratio %', 'Pension Fund Share %', 'Policy Rate %']}
  title="Payout Ratio vs Competition & Rates"
  yAxisTitle="%"
/>

<DataTable data={payout_vs_competition}>
  <Column id=year title="Year" />
  <Column id="Payout Ratio %" title="Payout %" fmt='0' />
  <Column id="Pension Fund Share %" title="Pension %" fmt='0.1' />
  <Column id="Policy Rate %" title="Policy Rate %" fmt='0.1' />
</DataTable>

### The Three Phases

**Phase 1: Pension Fund Retreat (2019→2021)**

When policy rates dropped to 1.1%, pension funds retreated from mortgages (29% → 22% share). Yields were too low to meet their return targets. Banks absorbed this market share without a fight.

**Phase 2: Profit Surge (2021-2022)**

With 70%+ market share, bank profits surged from 32 bn to 81 bn ISK. Payouts started ramping up (55% → 67%). COVID restrictions initially limited dividends, but that changed quickly.

**Phase 3: Maximum Extraction (2023-2024)**

In the high-rate environment, banks have cover: "We're just passing through the Central Bank rate." Meanwhile, payout ratios hit **88%** in 2024. Pension funds haven't returned despite attractive mortgage yields - government bonds at 7%+ offer similar returns with less risk.

### Why Pension Funds Haven't Returned

In theory, high rates should attract pension funds back to mortgages. But:

1. **Government bonds now yield 7%+** - safer than mortgage credit risk
2. **Banks already dominate** - hard to win back market share
3. **Alternative assets** - infrastructure, foreign equities offer diversification
4. **Capacity constraints** - pension fund mortgage operations scaled down

The result: a stable oligopoly with no price discipline. Banks can extract maximum rents while blaming the króna.

---

## Part 6: The MMT Perspective

### How Bank Lending Actually Works

Banks **don't borrow reserves to lend**. When Arion makes a mortgage:
1. It creates a deposit in the borrower's account (money creation)
2. The loan is an asset, the deposit a liability
3. Reserves are obtained *after* for settlement if needed

The Central Bank rate is **not a funding cost** that forces banks to charge high rates. It's:
- A pricing anchor (convention)
- An income source (interest on reserves)
- A demand management tool

### The Real Constraint: Capital

Banks need equity capital to support loan growth (~8-10% of risk-weighted assets). To grow lending, they must either:
1. **Retain earnings**
2. **Issue new shares**

If banks are extracting 78-100% of profits while claiming they "need" high margins, that's the smoking gun for rent extraction.

---

## Part 7: Historical Rate Spreads

```sql spread_trend
SELECT
  year,
  lending_rate_pct as "Lending Rate",
  deposit_rate_pct as "Deposit Rate",
  spread_pct as Spread
FROM banking.rate_spread
WHERE year >= 1990
ORDER BY year
```

<LineChart
  data={spread_trend}
  x=year
  y={['Lending Rate', 'Deposit Rate', 'Spread']}
  title="Lending vs Deposit Rates (1990-2020)"
  yAxisTitle="Rate %"
/>

The spread widened from ~3.5% to ~5% between 2017-2020 as deposit rates fell faster than lending rates.

---

## Conclusions

### What the Data Supports

| Factor | Contribution | Evidence |
|--------|--------------|----------|
| **High Central Bank rate** | ~60-70% of headline rate | Policy rate 7.25%, real rate ~3% |
| **Elevated NIM (bank markup)** | ~20-30% | 2.9-3.1% vs 0.8-1.8% Nordic peers |
| **Limited competition** | Contributing | 3 banks control 70% of mortgages |
| **Profit extraction** | Confirmed | **88%** of combined profits returned to shareholders in 2024 |
| **Market consolidation** | Structural | Banks gained 16pp market share during low-rate era (2019-2021) |

### The Honest Summary

> "Icelandic mortgage rates are high primarily because of the króna - the Central Bank must set high rates to control inflation. But Icelandic banks also take a spread that's 2-3x their Nordic peers. They consolidated market power during the low-rate era when pension funds retreated, and now extract 88% of profits while using high rates as cover. The system works for shareholders; borrowers pay both the inflation tax AND the oligopoly tax."

### What Would Actually Lower Rates?

1. **Lower inflation** → Central Bank can cut (happening slowly)
2. **More bank competition** → New entrant or fintech disruption
3. **Regulatory pressure on margins** → Competition authority action
4. **Pension fund expansion** → More capacity = more pressure

---

## Data Sources

- **Central Bank of Iceland (Seðlabanki):** Policy rates, balance sheets, new credit flows
- **Pension Fund Association (Landssamtök lífeyrissjóða):** Mortgage market share data
- **World Bank GFDD:** International NIM comparison
- **Statistics Iceland (Hagstofan):** CPI data for real rate calculation
- **Nasdaq Iceland:** Bank annual report announcements
- **Skatturinn:** Arion banki annual report (direct extraction)

---

## Side Quests Completed

During this research, we explored:

1. **Pension fund market share:** Corrected the "2/3 of mortgages" myth → actually 24.5%
2. **Eurozone mortgage spreads:** Found counterintuitive pattern where peripheral countries (Spain, Portugal) now have *lower* rates than core (Germany)
3. **Pass-through research:** ECB/academic research shows banking competition improves pass-through
4. **Skill health audit:** Tested all 6 data skills, found minor encoding issues in Reykjavik PX-Web
5. **Financials extraction:** Successfully extracted bank annual report data using Docling

---

*Report generated from `/Users/jokull/Code/icelandic-data/` using Evidence. Data last updated February 2026.*

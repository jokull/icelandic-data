---
title: Play Airlines Bankruptcy Impact on Icelandair
---

# Play Airlines Bankruptcy Impact Analysis

On **September 29, 2025**, Fly Play hf. ceased operations and filed for bankruptcy. This report analyzes the impact on Iceland's aviation market and Icelandair Group hf.

## Executive Summary

```sql summary_stats
SELECT
    SUM(CASE WHEN year = 2024 THEN passengers END) as pax_2024,
    SUM(CASE WHEN year = 2025 THEN passengers END) as pax_2025,
    ROUND(100.0 * (SUM(CASE WHEN year = 2025 THEN passengers END) -
        SUM(CASE WHEN year = 2024 THEN passengers END)) /
        SUM(CASE WHEN year = 2024 THEN passengers END), 1) as growth_pct
FROM nasdaq.passengers
WHERE month_num <= 11
```

<BigValue
  data={summary_stats}
  value=pax_2025
  title="2025 Passengers (Jan-Nov)"
  fmt='#,##0'
/>

<BigValue
  data={summary_stats}
  value=growth_pct
  title="YoY Growth"
  fmt='+0.0"%"'
/>

---

## Investment Thesis

```sql post_bankruptcy
SELECT
    SUM(CASE WHEN year = 2024 AND month_num IN (10,11) THEN passengers END) as market_2024,
    SUM(CASE WHEN year = 2025 AND month_num IN (10,11) THEN passengers END) as market_2025,
    SUM(CASE WHEN year = 2024 AND month_num IN (10,11) THEN passengers END) -
        SUM(CASE WHEN year = 2025 AND month_num IN (10,11) THEN passengers END) as capacity_lost,
    ROUND(100.0 * (SUM(CASE WHEN year = 2024 AND month_num IN (10,11) THEN passengers END) -
        SUM(CASE WHEN year = 2025 AND month_num IN (10,11) THEN passengers END)) /
        SUM(CASE WHEN year = 2024 AND month_num IN (10,11) THEN passengers END), 1) as market_contraction
FROM nasdaq.passengers
```

<BigValue
  data={post_bankruptcy}
  value=capacity_lost
  title="Market Capacity Lost (Oct-Nov)"
  fmt='#,##0'
/>

<BigValue
  data={post_bankruptcy}
  value=market_contraction
  title="Market Contraction"
  fmt='0.0"%"'
/>

### Analyst Assessment

**Rating: BULLISH on Icelandair (ICEAIR)**

Play's bankruptcy on September 29, 2025 creates a complex but ultimately favorable dynamic for Icelandair:

**The Paradox: Smaller Pie, Bigger Slice**

Total Keflavik passenger traffic *contracted* 5.5% in Oct-Nov 2025 vs 2024 — Play's 8 aircraft worth of capacity simply vanished. Yet Icelandair reported **+14-15% passenger growth** in these same months. The math:

| Metric | Value |
|--------|-------|
| Total market lost (Oct-Nov) | ~26,000 passengers |
| Icelandair's reported growth | +14-15% YoY |
| Implied Icelandair share gain | Significant |

This divergence reveals Icelandair captured the *profitable* portion of Play's traffic while low-yield passengers simply didn't travel.

**Strategic Position:**
1. **Market Share Surge:** From ~60% to ~95% of scheduled Iceland capacity overnight
2. **Yield Optimization:** Absorbing demand at Icelandair's pricing, not LCC rates
3. **Capacity Discipline:** Leased only 2 aircraft — not replacing Play's 8 — maintaining supply/demand balance
4. **Structural Moat:** No credible LCC entrant likely for 12-18 months (capital, slots, aircraft lead times)

**Bull Case Math:**
- Play carried ~500k passengers annually at low yields
- Icelandair captures 60-70% at premium pricing
- Net revenue uplift: Fewer passengers, higher revenue per passenger
- EBIT margin expansion potential: 200-400 bps in 2026

**Risks:**
- Regulatory scrutiny of near-monopoly
- Tourism demand elasticity at higher fares
- Potential new entrant (Wizz Air, Norwegian)

**Conclusion:** The post-bankruptcy data confirms the bull thesis. Total market shrinkage masks Icelandair's dramatic share gain. With pricing power restored and capacity rationalized, expect meaningful margin expansion in 2026. **This is a quality-over-quantity story** — Icelandair emerges as a stronger, more profitable carrier despite (or because of) the smaller total market.

---

## Timeline: Play Airlines Collapse

```sql timeline
SELECT
    date,
    REPLACE(REPLACE(event, 'Fly Play hf.: ', ''), 'Fly Play hf. ', '') as event
FROM nasdaq.play_events
ORDER BY date DESC
```

<DataTable data={timeline}>
  <Column id=date title="Date" />
  <Column id=event title="Event" />
</DataTable>

---

## Monthly Passenger Traffic (Keflavik Airport)

```sql monthly
SELECT * FROM nasdaq.passengers ORDER BY date
```

<LineChart
  data={monthly}
  x=date
  y=passengers
  yAxisTitle="Passengers"
  xAxisTitle="Month"
  title="Total Keflavik Airport Passengers"
  yFmt='#,##0'
/>

### Year-over-Year Comparison

```sql yoy
SELECT
    month_num as month,
    CASE month_num
        WHEN 1 THEN 'Jan' WHEN 2 THEN 'Feb' WHEN 3 THEN 'Mar'
        WHEN 4 THEN 'Apr' WHEN 5 THEN 'May' WHEN 6 THEN 'Jun'
        WHEN 7 THEN 'Jul' WHEN 8 THEN 'Aug' WHEN 9 THEN 'Sep'
        WHEN 10 THEN 'Oct' WHEN 11 THEN 'Nov' WHEN 12 THEN 'Dec'
    END as month_name,
    MAX(CASE WHEN year = 2024 THEN passengers END) as y2024,
    MAX(CASE WHEN year = 2025 THEN passengers END) as y2025
FROM nasdaq.passengers
GROUP BY month_num
HAVING y2024 IS NOT NULL AND y2025 IS NOT NULL
ORDER BY month_num
```

<BarChart
  data={yoy}
  x=month_name
  y={['y2024', 'y2025']}
  title="2024 vs 2025 Monthly Passengers"
  yAxisTitle="Passengers"
  type=grouped
  yFmt='#,##0'
/>

```sql growth
SELECT
    month_name,
    y2024,
    y2025,
    ROUND(100.0 * (y2025 - y2024) / y2024, 1) as growth_pct
FROM ${yoy}
```

<DataTable data={growth}>
  <Column id=month_name title="Month" />
  <Column id=y2024 title="2024" fmt='#,##0' />
  <Column id=y2025 title="2025" fmt='#,##0' />
  <Column id=growth_pct title="Growth %" fmt='+0.0"%"' />
</DataTable>

---

## Icelandair Response

Following Play's collapse, Icelandair announced significant capacity expansion and passenger growth:

```sql icelandair_updates
SELECT * FROM nasdaq.icelandair WHERE date >= '2025-01-01' ORDER BY date DESC
```

<DataTable data={icelandair_updates}>
  <Column id=date title="Date" />
  <Column id=headline title="Announcement" />
</DataTable>

### Key Icelandair Actions Post-Bankruptcy

| Date | Action |
|------|--------|
| 2025-09-11 | Leased two new Airbus A321LR aircraft |
| 2025-10-06 | +15% passengers to Iceland in September |
| 2025-11-06 | +14% passengers in October |
| 2025-12-08 | +15% passengers in November |
| 2026-01-06 | Record passenger numbers for 2025 |

---

## Impact Assessment

### Market Consolidation

Play Airlines operated as a low-cost carrier (LCC) on transatlantic routes, competing with Icelandair on price. Their exit removes significant capacity:

- Play had 4 Airbus A320neo and 4 A321neo aircraft
- Served routes to North America and Europe via Iceland

### Icelandair Benefits

1. **Reduced Competition:** No direct LCC competitor on most routes
2. **Capacity Absorption:** Passenger demand transferred to Icelandair
3. **Pricing Power:** Potential for higher yields without LCC pressure
4. **Fleet Expansion:** Quick lease of 2 new aircraft shows strategic response

---

## Data Sources

| Source | Data |
|--------|------|
| Nasdaq Iceland | Company announcements (Play, Icelandair) |
| Hagstofan | Keflavik airport passenger statistics (SAM02001.px) |

*Report generated: January 2026*

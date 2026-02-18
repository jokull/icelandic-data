---
title: Nationalities in Reykjavík
---

# Nationalities in Reykjavík

<Alert status="info">
Data from Reykjavík Municipality (gagnagatt.reykjavik.is and velstat.reykjavik.is). Foreign citizen statistics 1998-2023.
</Alert>

```sql foreign_citizens_growth
SELECT * FROM reykjavik.foreign_citizens_growth
```

```sql foreign_citizens_by_continent
SELECT * FROM reykjavik.foreign_citizens_by_continent
```

## Foreign Citizens Over Time

Reykjavík's foreign citizen population has grown dramatically, from ~2,400 in 1998 to over 25,000 by 2023—a 10x increase. The 2008 financial crisis caused a brief dip, followed by rapid growth driven by EU expansion and labor demand.

<LineChart
  data={foreign_citizens_growth}
  x=year
  y=total_foreign
  yAxisTitle="Foreign citizens"
/>

## By Region of Origin

The composition has shifted significantly. EU citizens (driven by Polish migration) now dominate, while the share of Nordic citizens has declined.

<AreaChart
  data={foreign_citizens_by_continent}
  x=year
  y={['eu', 'asia', 'nordic', 'other_europe', 'latin_america', 'africa', 'north_america', 'oceania']}
  yAxisTitle="Foreign citizens"
  type=stacked
/>

## Top Nationalities

```sql top_nationalities
SELECT * FROM reykjavik.top_nationalities
```

```sql top_2023
SELECT nationality, total
FROM reykjavik.top_nationalities
WHERE year = (SELECT MAX(year) FROM reykjavik.top_nationalities)
ORDER BY total DESC
LIMIT 10
```

<BarChart
  data={top_2023}
  x=nationality
  y=total
  swapXY=true
  yAxisTitle="Foreign citizens (most recent year)"
/>

### Growth of Top Nationalities Over Time

<LineChart
  data={top_nationalities}
  x=year
  y=total
  series=nationality
  yAxisTitle="Citizens"
/>

---

## Distribution by District

```sql foreign_share_by_district
SELECT * FROM reykjavik.foreign_share_by_district
```

Foreign citizens are not evenly distributed across Reykjavík. By 2022, **Miðborg (downtown) reached 35% foreign residents**—up from 18% in 2010. Breiðholt follows at 27%, while Grafarholt remains under 10%.

<BarChart
  data={foreign_share_by_district.filter(d => d.year === '2022')}
  x=year
  y={['midborg', 'vesturbær', 'breidholt', 'hlidar', 'laugardalur', 'haaleiti', 'arbaer', 'grafarvogur', 'grafarholt']}
  yAxisTitle="% foreign citizens (2022)"
  type=grouped
/>

### District Trends Over Time

<LineChart
  data={foreign_share_by_district}
  x=year
  y={['midborg', 'breidholt', 'vesturbær', 'total']}
  yAxisTitle="% foreign citizens"
/>

---

## Unemployment by Nationality

```sql unemployment_by_nationality
SELECT * FROM reykjavik.unemployment_by_nationality
```

Unemployment data shows distinct patterns between Icelandic and foreign citizens, particularly during economic shocks (2008 crisis, COVID-19 pandemic).

<LineChart
  data={unemployment_by_nationality}
  x=year_month
  y={['icelandic', 'polish', 'other_foreign']}
  yAxisTitle="Unemployed persons"
/>

---

## Financial Assistance by Nationality

```sql financial_aid_by_nationality
SELECT * FROM reykjavik.financial_aid_by_nationality
```

```sql financial_aid_wide
SELECT
  year,
  MAX(CASE WHEN nationality = 'Íslenskt ríkisfang' THEN recipients END) as icelandic,
  MAX(CASE WHEN nationality = 'Erlent ríkisfang' THEN recipients END) as foreign
FROM reykjavik.financial_aid_by_nationality
GROUP BY year
ORDER BY year
```

Financial assistance shows a dramatic post-pandemic shift. Foreign citizen recipients exploded from ~100 (2007) to **2,000+ (2021-2024)**—a 20x increase. Meanwhile, Icelandic recipient numbers have actually declined from peak crisis levels. By 2024, foreign citizens represent over 60% of financial assistance recipients despite being only 20% of the population.

<LineChart
  data={financial_aid_wide}
  x=year
  y={['icelandic', 'foreign']}
  yAxisTitle="Recipients of financial assistance"
/>

### Monthly Trend (2019-2025)

```sql welfare_nationality_monthly
SELECT * FROM reykjavik.welfare_nationality_monthly
```

<LineChart
  data={welfare_nationality_monthly}
  x=month
  y={['foreign', 'icelandic']}
  yAxisTitle="Monthly recipients"
/>

### Who Are the Recipients? Family Type Breakdown

```sql welfare_by_family_type
SELECT * FROM reykjavik.welfare_by_family_type
```

```sql family_type_latest
SELECT
  nationality,
  family_type,
  total
FROM reykjavik.welfare_by_family_type
WHERE month = (SELECT MAX(month) FROM reykjavik.welfare_by_family_type)
ORDER BY nationality, total DESC
```

Foreign welfare recipients are increasingly diverse: while single men dominated in 2019, single women now make up an equal share. Icelandic recipients remain predominantly single men.

<BarChart
  data={family_type_latest}
  x=family_type
  y=total
  series=nationality
  type=grouped
  yAxisTitle="Recipients (Dec 2024)"
  swapXY=true
/>

### Employment Status of Recipients

```sql welfare_by_employment
SELECT * FROM reykjavik.welfare_by_employment
```

```sql employment_2023
SELECT employment_status, total, pct
FROM reykjavik.welfare_by_employment
WHERE year = '2023'
ORDER BY total DESC
```

Most recipients are either unemployed without benefits, unable to work, or have disabilities.

<BarChart
  data={employment_2023}
  x=employment_status
  y=total
  yAxisTitle="Recipients (2023)"
  swapXY=true
/>

---

## Children in Education

<Alert status="warning">
Note: Kindergarten nationality data only available 2008-2016. The municipality stopped publishing this breakdown.
</Alert>

```sql kindergarten_nationalities
SELECT * FROM reykjavik.kindergarten_nationalities
```

Polish children were by far the largest foreign group in Reykjavík kindergartens (2008-2016), followed by Filipino and Lithuanian children.

<BarChart
  data={kindergarten_nationalities}
  x=year
  y={['poland', 'philippines', 'lithuania', 'germany', 'vietnam', 'romania']}
  yAxisTitle="Children in kindergartens"
  type=stacked
/>

---

## Tourism: Cruise Passengers

<Alert status="warning">
Note: Cruise data ends in 2019. COVID-19 halted cruise tourism in 2020.
</Alert>

```sql cruise_nationalities
SELECT * FROM reykjavik.cruise_nationalities
```

Cruise tourism grew 6x from 30k to 189k passengers (2002-2019), with Germans, Americans, and British dominating.

<AreaChart
  data={cruise_nationalities}
  x=year
  y={['germany', 'usa', 'uk', 'france', 'canada', 'australia']}
  yAxisTitle="Cruise passengers"
  type=stacked
/>

---

## Key Findings

1. **10x growth**: Foreign citizens in Reykjavík grew from 2,400 (1998) to 28,000+ (2022)
2. **Polish dominance**: Poland is by far the largest source country, especially after 2004 EU expansion
3. **Downtown transformation**: Miðborg went from 18% to **35% foreign residents** (2010-2022)
4. **Economic vulnerability**: Foreign citizens are more affected by economic downturns (higher unemployment spikes)
5. **Post-pandemic welfare surge**: Foreign citizen welfare recipients exploded 20x, now over 60% of all recipients
6. **Data gaps**: Education nationality data stopped being published in 2016; cruise data ends at 2019 (COVID)

<LastRefreshed/>

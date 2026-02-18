---
title: Fasteignaverð á Íslandi
---

# Fasteignaverð á Íslandi

Gögn úr kaupskrá HMS, tengd við staðfangaskrá með `iceaddr`.

```sql stats
SELECT
  count(*) as heildarfjoldi,
  count(*) FILTER (WHERE NOT onothaefur) as nothafir_samningar,
  count(lat) as geocoded,
  min(kaupsamningur_dags) as fyrsta_sala,
  max(kaupsamningur_dags) as sidasta_sala
FROM hms.kaupskra
```

<BigValue
  data={stats}
  value=nothafir_samningar
  title="Nothæfir samningar"
  fmt='#,##0'
/>

<BigValue
  data={stats}
  value=geocoded
  title="Með hnit"
  fmt='#,##0'
/>

## Verðþróun í Reykjavík (fjölbýli)

```sql reykjavik_price_trend
SELECT
  YEAR(kaupsamningur_dags) as ar,
  count(*) as fjoldi,
  round(avg(kaupverd * 1000 / einflm_m2) / 1000, 0) as avg_m2_thkr,
  round(median(kaupverd * 1000 / einflm_m2) / 1000, 0) as median_m2_thkr
FROM hms.kaupskra
WHERE NOT onothaefur
  AND tegund = 'Fjölbýli'
  AND postnr BETWEEN 101 AND 128
  AND einflm_m2 > 30
GROUP BY 1
ORDER BY 1
```

<LineChart
  data={reykjavik_price_trend}
  x=ar
  y=median_m2_thkr
  yAxisTitle="Miðgildi kr/m² (þús.)"
  xAxisTitle="Ár"
  title="Verð á fermetra í Reykjavík"
/>

<DataTable data={reykjavik_price_trend}>
  <Column id=ar title="Ár" />
  <Column id=fjoldi title="Sölur" fmt='#,##0' />
  <Column id=median_m2_thkr title="Miðgildi kr/m² (þús.)" fmt='#,##0' />
  <Column id=avg_m2_thkr title="Meðaltal kr/m² (þús.)" fmt='#,##0' />
</DataTable>

## Verð eftir póstnúmerum (2024-2025)

```sql price_by_postcode
SELECT
  postnr,
  sveitarfelag,
  count(*) as fjoldi,
  round(median(kaupverd * 1000 / einflm_m2) / 1000, 0) as median_m2_thkr,
  round(avg(lat), 5) as lat,
  round(avg(lng), 5) as lng
FROM hms.kaupskra
WHERE NOT onothaefur
  AND tegund IN ('Fjölbýli', 'Sérbýli')
  AND einflm_m2 > 30
  AND kaupsamningur_dags >= '2024-01-01'
  AND lat IS NOT NULL
  AND kaupverd * 1000 / einflm_m2 < 3000000
GROUP BY postnr, sveitarfelag
HAVING count(*) >= 10
ORDER BY median_m2_thkr DESC
```

<BarChart
  data={price_by_postcode}
  x=postnr
  y=median_m2_thkr
  title="Miðgildi kr/m² eftir póstnúmeri"
  xAxisTitle="Póstnúmer"
  yAxisTitle="kr/m² (þús.)"
  swapXY=true
  sort=false
/>

## Nýlegar sölur á korti

```sql recent_sales_map
SELECT
  kaupsamningur_dags,
  heimilisfang,
  postnr,
  sveitarfelag,
  tegund,
  einflm_m2,
  fjherb,
  byggar,
  kaupverd * 1000 as kaupverd_kr,
  round(kaupverd * 1000 / einflm_m2 / 1000, 0) as verd_m2_thkr,
  lat,
  lng
FROM hms.kaupskra
WHERE NOT onothaefur
  AND tegund IN ('Fjölbýli', 'Sérbýli')
  AND einflm_m2 > 30
  AND kaupsamningur_dags >= '2024-01-01'
  AND lat IS NOT NULL
  AND kaupverd * 1000 / einflm_m2 < 3000000
ORDER BY kaupsamningur_dags DESC
LIMIT 5000
```

<PointMap
  data={recent_sales_map}
  lat=lat
  long=lng
  value=verd_m2_thkr
  pointName=heimilisfang
  height=500
  tooltipType=hover
  colorPalette={['#22c55e', '#eab308', '#ef4444']}
/>

### Dýrustu sölurnar 2024-2025

```sql expensive
SELECT
  kaupsamningur_dags as dags,
  heimilisfang,
  postnr,
  einflm_m2 as m2,
  kaupverd * 1000 as verd_kr,
  round(kaupverd * 1000 / einflm_m2 / 1000, 0) as kr_m2_th
FROM hms.kaupskra
WHERE NOT onothaefur
  AND tegund IN ('Fjölbýli', 'Sérbýli')
  AND einflm_m2 > 50
  AND kaupsamningur_dags >= '2024-01-01'
  AND kaupverd * 1000 / einflm_m2 < 5000000
ORDER BY kaupverd DESC
LIMIT 20
```

<DataTable data={expensive}>
  <Column id=dags title="Dags" />
  <Column id=heimilisfang title="Heimilisfang" />
  <Column id=postnr title="Pnr" />
  <Column id=m2 title="m²" fmt='0.0' />
  <Column id=verd_kr title="Verð" fmt='#,##0 kr' />
  <Column id=kr_m2_th title="kr/m² (þ)" fmt='#,##0' />
</DataTable>

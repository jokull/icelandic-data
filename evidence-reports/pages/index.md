---
title: E-bike & Micromobility Imports to Iceland
---

# E-bike & Micromobility Imports

<Alert status="info">
Data from Statistics Iceland (Hagstofa) customs tariff records. 2025 data through October only.
</Alert>

```sql electric_vs_bikes
SELECT * FROM hagstofan.electric_vs_bikes
```

## Electric vs Traditional Bikes

Electric micromobility (e-bikes + e-scooters) has transformed Iceland's cycling market. While traditional bike imports have halved since 2017, electric alternatives now dominate by value.

<LineChart
  data={electric_vs_bikes}
  x=year
  y={['electric_units', 'bike_units']}
  yAxisTitle="Units imported"
/>

<BarChart
  data={electric_vs_bikes}
  x=year
  y={['electric_value_m', 'bike_value_m']}
  yAxisTitle="Import value (M ISK)"
/>

## Key Trends

```sql bike_imports
SELECT * FROM hagstofan.bike_imports
```

```sql summary
SELECT
  category,
  SUM(total_units) as total_units,
  ROUND(SUM(total_cif_isk) / 1e9, 2) as total_value_b
FROM hagstofan.bike_imports
GROUP BY category
ORDER BY total_units DESC
```

<BigValue
  data={summary.filter(d => d.category === 'ebikes')}
  value=total_units
  title="Total E-bikes Imported"
  fmt="#,##0"
/>

<BigValue
  data={summary.filter(d => d.category === 'bikes')}
  value=total_units
  title="Total Bikes Imported"
  fmt="#,##0"
/>

<BigValue
  data={summary.filter(d => d.category === 'escooters')}
  value=total_units
  title="Total E-scooters Imported"
  fmt="#,##0"
/>

## Detailed Breakdown by Category

<BarChart
  data={bike_imports}
  x=year
  y=total_units
  series=category
  yAxisTitle="Units"
/>

## Average Import Price

The average e-bike import price has risen 5x from 57k ISK (2017) to ~280k ISK (2025), reflecting a shift from cheap imports (IKEA era) to quality bikes.

```sql prices
SELECT
  year,
  category,
  ROUND(total_cif_isk / NULLIF(total_units, 0) / 1000, 0) as avg_price_k
FROM hagstofan.bike_imports
WHERE total_units > 0
```

<LineChart
  data={prices}
  x=year
  y=avg_price_k
  series=category
  yAxisTitle="Avg price (k ISK)"
/>

## Data Table

<DataTable data={bike_imports} rows=all>
  <Column id=year />
  <Column id=category />
  <Column id=total_units fmt="#,##0" />
  <Column id=total_cif_isk fmt="#,##0" />
  <Column id=avg_price_k title="Avg Price (k)" fmt="#,##0" />
</DataTable>

---

## Notes

- **Pre-2020**: E-scooters were classified together with e-bikes under code 87116010
- **2020 spike**: E-scooter rental companies (Hopp, etc.) imported ~20,000 scooters
- **IKEA effect (2017-18)**: Low average prices reflect cheap IKEA e-bikes pulling down averages
- **Classification codes**: 87116011 (e-bikes), 87116012 (e-scooters), 87120000 (bikes)

<LastRefreshed/>

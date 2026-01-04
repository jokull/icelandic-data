SELECT
  year,
  SUM(CASE WHEN category IN ('ebikes', 'escooters') THEN total_units ELSE 0 END) as electric_units,
  SUM(CASE WHEN category = 'bikes' THEN total_units ELSE 0 END) as bike_units,
  SUM(CASE WHEN category IN ('ebikes', 'escooters') THEN total_cif_isk ELSE 0 END) / 1e6 as electric_value_m,
  SUM(CASE WHEN category = 'bikes' THEN total_cif_isk ELSE 0 END) / 1e6 as bike_value_m
FROM read_csv('../data/processed/bike_imports_all.csv')
GROUP BY year
ORDER BY year

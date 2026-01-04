SELECT
  year,
  category,
  total_cif_isk,
  total_units,
  ROUND(total_cif_isk / NULLIF(total_units, 0) / 1000, 0) as avg_price_k
FROM read_csv('../data/processed/bike_imports_all.csv')
ORDER BY year, category

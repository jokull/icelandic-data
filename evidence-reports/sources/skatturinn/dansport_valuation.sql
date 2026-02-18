SELECT
  method,
  ROUND(low_estimate / 1e6, 0) as low_m,
  ROUND(mid_estimate / 1e6, 0) as mid_m,
  ROUND(high_estimate / 1e6, 0) as high_m,
  notes
FROM read_csv_auto('../data/processed/financials/dansport_valuation.csv')

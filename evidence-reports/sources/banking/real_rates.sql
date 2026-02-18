-- Real interest rates (policy rate minus inflation)
SELECT
  month as date,
  YEAR(month) as year,
  MONTH(month) as month_num,
  nominal_policy_rate as policy_rate_pct,
  cpi_inflation_yoy as inflation_yoy_pct,
  real_rate as real_rate_pct
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/real_interest_rates.csv')
ORDER BY month

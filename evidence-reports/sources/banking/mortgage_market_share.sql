-- Mortgage market share by lender type (2007-2024)
SELECT
  date,
  year,
  quarter,
  banks_nominal_mkr,
  pension_nominal_mkr,
  ils_nominal_mkr,
  total_nominal_mkr,
  banks_share_pct,
  pension_share_pct,
  ils_share_pct
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/mortgage_market_share.csv')
ORDER BY date

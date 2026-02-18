-- Nordic bank comparison (NIM, ROE, efficiency, payouts)
SELECT
  country,
  year,
  nim_pct,
  roe_pct,
  cost_income_pct,
  payout_pct,
  cet1_pct,
  source
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/nordic_bank_comparison.csv')
ORDER BY year, country

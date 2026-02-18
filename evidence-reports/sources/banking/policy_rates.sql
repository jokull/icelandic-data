-- Central Bank of Iceland policy rates (2007-2026)
SELECT
  date,
  policy_rate,
  overnight_lending_rate,
  current_account_rate
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/sedlabanki_policy_rates.csv')
ORDER BY date

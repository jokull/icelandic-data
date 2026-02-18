-- Historical lending vs deposit rate spread (1960-2020)
SELECT
  year,
  lending_rate_pct,
  deposit_rate_pct,
  spread_pct
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/sedlabanki_rate_spread.csv')
ORDER BY year

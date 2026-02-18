-- Net Interest Margin comparison (World Bank data)
SELECT
  country,
  country_code,
  year,
  nim_pct
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/worldbank_nim_comparison.csv')
ORDER BY year DESC, nim_pct DESC

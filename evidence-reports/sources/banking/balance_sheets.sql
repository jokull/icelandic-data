-- Bank balance sheet aggregates
SELECT
  date,
  item_is,
  item_en,
  value_mkr
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/sedlabanki_balance_sheets.csv')
WHERE value_mkr > 1000000  -- Filter for major items only
ORDER BY date DESC, value_mkr DESC

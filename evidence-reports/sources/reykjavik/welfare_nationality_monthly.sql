-- Welfare recipients by nationality (monthly totals, 2019-2025)
SELECT
  Mánuður as month,
  MAX(CASE WHEN Ríkisfang = 'Erlent ríkisfang' THEN Samtals END) as foreign,
  MAX(CASE WHEN Ríkisfang = 'Íslenskt ríkisfang' THEN Samtals END) as icelandic,
  MAX(CASE WHEN Ríkisfang = 'Samtals' THEN Samtals END) as total
FROM read_csv('../data/raw/reykjavik/nationalities/welfare_nationality_family.csv',
  header=true
)
WHERE Fjölskyldugerð = 'Samtals'
GROUP BY Mánuður
ORDER BY month

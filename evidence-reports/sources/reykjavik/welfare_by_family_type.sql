-- Welfare recipients by nationality and family type (monthly, 2019-2025)
SELECT
  Mánuður as month,
  SUBSTRING(Mánuður, 1, 4) as year,
  Ríkisfang as nationality,
  Fjölskyldugerð as family_type,
  Samtals as total
FROM read_csv('../data/raw/reykjavik/nationalities/welfare_nationality_family.csv',
  header=true
)
WHERE Fjölskyldugerð != 'Samtals'
  AND Ríkisfang != 'Samtals'
ORDER BY month, nationality, family_type

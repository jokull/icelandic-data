-- Total foreign citizens in Reykjavík over time
SELECT
  Ár as year,
  SUM(Alls) as total_foreign
FROM read_csv('../data/raw/reykjavik/nationalities/foreign_citizens_by_nationality.csv',
  delim=';',
  header=true
)
WHERE Ríkisfang NOT IN ('Alls', 'Ríkisfangslaus', 'Ótilgreint land')
GROUP BY Ár
ORDER BY year

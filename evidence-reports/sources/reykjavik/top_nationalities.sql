-- Top nationalities over time (most recent year = 2023)
WITH latest AS (
  SELECT MAX(Ár) as max_year
  FROM read_csv('../data/raw/reykjavik/nationalities/foreign_citizens_by_nationality.csv',
    delim=';', header=true)
),
ranked AS (
  SELECT
    Ár as year,
    Ríkisfang as nationality,
    Alls as total
  FROM read_csv('../data/raw/reykjavik/nationalities/foreign_citizens_by_nationality.csv',
    delim=';', header=true)
  WHERE Ríkisfang NOT IN ('Alls', 'Ríkisfangslaus', 'Ótilgreint land')
)
SELECT
  r.year,
  r.nationality,
  r.total
FROM ranked r
WHERE r.year >= 2015
  AND r.nationality IN (
    SELECT nationality
    FROM ranked
    WHERE year = (SELECT max_year FROM latest)
    ORDER BY total DESC
    LIMIT 15
  )
ORDER BY r.year, r.total DESC

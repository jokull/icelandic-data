-- Welfare recipients by employment status (annual)
SELECT
  Ár as year,
  Atvinnustaða as employment_status,
  "Alls Fjöldi" as total,
  "Alls Hlutfall (%)" as pct
FROM read_csv('../data/raw/reykjavik/nationalities/welfare_by_employment.csv',
  header=true
)
WHERE Atvinnustaða != 'Alls fjöldi notenda'
ORDER BY year, total DESC

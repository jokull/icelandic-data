-- Unemployment by nationality (Icelandic, Polish, Other foreign)
SELECT
  Ár as year,
  Mánuður as month,
  Ár || '-' ||
    CASE Mánuður
      WHEN 'Janúar' THEN '01'
      WHEN 'Febrúar' THEN '02'
      WHEN 'Mars' THEN '03'
      WHEN 'Apríl' THEN '04'
      WHEN 'Maí' THEN '05'
      WHEN 'Júní' THEN '06'
      WHEN 'Júlí' THEN '07'
      WHEN 'Ágúst' THEN '08'
      WHEN 'September' THEN '09'
      WHEN 'Október' THEN '10'
      WHEN 'Nóvember' THEN '11'
      WHEN 'Desember' THEN '12'
    END as year_month,
  TRY_CAST("Íslenskir ríkisborgarar" AS INTEGER) as icelandic,
  TRY_CAST("Pólskir ríkisborgarar" AS INTEGER) as polish,
  TRY_CAST("Aðrir erlendir ríkisborgarar" AS INTEGER) as other_foreign,
  TRY_CAST(Alls AS INTEGER) as total
FROM read_csv('../data/raw/reykjavik/nationalities/unemployment_by_nationality.csv',
  delim=';',
  header=true
)
WHERE Kyn = 'Allir'
  AND TRY_CAST("Íslenskir ríkisborgarar" AS INTEGER) IS NOT NULL
ORDER BY year, month

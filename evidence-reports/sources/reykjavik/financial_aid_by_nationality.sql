-- Financial assistance recipients by nationality over time
WITH wide_data AS (
  SELECT *
  FROM read_csv('../data/raw/reykjavik/nationalities/financial_aid_by_nationality.csv',
    header=true
  )
)
SELECT
  year,
  nationality,
  recipients
FROM (
  SELECT 2007 as year, Ríkisfang as nationality, "2007" as recipients FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2008, Ríkisfang, "2008" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2009, Ríkisfang, "2009" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2010, Ríkisfang, "2010" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2011, Ríkisfang, "2011" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2012, Ríkisfang, "2012" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2013, Ríkisfang, "2013" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2014, Ríkisfang, "2014" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2015, Ríkisfang, "2015" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2016, Ríkisfang, "2016" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2017, Ríkisfang, "2017" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2018, Ríkisfang, "2018" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2019, Ríkisfang, "2019" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2020, Ríkisfang, "2020" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2021, Ríkisfang, "2021" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2022, Ríkisfang, "2022" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2023, Ríkisfang, "2023" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
  UNION ALL SELECT 2024, Ríkisfang, "2024" FROM wide_data WHERE Þjónustumiðstöð = 'Samtals'
) unpivoted
WHERE nationality != 'Samtals'
ORDER BY year, nationality

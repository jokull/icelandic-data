-- Cruise passenger nationalities over time
SELECT
  Ár as year,
  Alls as total,
  Þýskaland as germany,
  USA as usa,
  England as uk,
  Frakkland as france,
  Kanada as canada,
  Ástralía as australia
FROM read_csv('../data/raw/reykjavik/nationalities/cruise_passengers_nationality.csv',
  delim=';',
  header=true
)
ORDER BY year

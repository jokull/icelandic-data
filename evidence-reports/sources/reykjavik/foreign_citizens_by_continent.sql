-- Foreign citizens by continent over time
SELECT
  Ár as year,
  Alls as total,
  "Norðurlönd" as nordic,
  "ESB lönd" as eu,
  "Önnur Evrópulönd" as other_europe,
  "Afríka" as africa,
  "Norður Ameríka" as north_america,
  "S. og Mið-Ameríka" as latin_america,
  "Asía" as asia,
  "Eyjaálfa" as oceania
FROM read_csv('../data/raw/reykjavik/nationalities/foreign_citizens_by_continent.csv',
  delim=';',
  header=true
)
ORDER BY year

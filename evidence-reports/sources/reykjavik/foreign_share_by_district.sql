-- Foreign citizen share by district (2022 latest)
SELECT
  "Ár" as year,
  "Ríkisfang" as citizenship,
  "Vesturbær" as vesturbær,
  "Miðborg" as midborg,
  "Hlíðar" as hlidar,
  "Laugardalur" as laugardalur,
  "Háaleiti" as haaleiti,
  "Breiðholt" as breidholt,
  "Árbær" as arbaer,
  "Grafarholt/Úlfarsfell" as grafarholt,
  "Grafarvogur" as grafarvogur,
  "Samtals" as total
FROM read_csv('../data/raw/reykjavik/nationalities/population_by_district_nationality_full_utf8.csv',
  header=true
)
WHERE "Fjöldi/Hlutfall" = 'Hlutfall'
  AND "Ríkisfang" = 'Erlent ríkisfang'
ORDER BY year

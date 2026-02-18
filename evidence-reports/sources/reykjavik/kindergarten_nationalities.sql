-- Top nationalities of children in kindergartens
SELECT
  Ár as year,
  Alls as total_foreign,
  Pólland as poland,
  Filippseyjar as philippines,
  Litháen as lithuania,
  Þýskaland as germany,
  Víetnam as vietnam,
  Rúmenía as romania,
  Lettland as latvia,
  Rússland as russia,
  Brasilía as brazil,
  Bretland as uk
FROM read_csv('../data/raw/reykjavik/nationalities/kindergarten_nationalities.csv',
  delim=';',
  header=true
)
ORDER BY year

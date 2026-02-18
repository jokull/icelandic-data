SELECT
  year,
  ROUND(revenue / 1e6, 1) as revenue_m,
  ROUND(operating_profit / 1e6, 1) as operating_profit_m,
  ROUND(net_profit / 1e6, 1) as net_profit_m,
  ROUND(total_assets / 1e6, 1) as total_assets_m,
  ROUND(total_equity / 1e6, 1) as total_equity_m,
  ROUND(short_term_debt / 1e6, 1) as short_term_debt_m,
  employees,
  equity_ratio,
  gross_margin,
  profit_margin
FROM read_csv_auto('../data/processed/financials/dansport_financials.csv')
ORDER BY year

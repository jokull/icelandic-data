SELECT
  year,
  combined_profit_bn,
  dividends_bn,
  buybacks_bn,
  total_return_bn,
  payout_pct,
  policy_rate,
  pension_share_pct
FROM read_csv('/Users/jokull/Code/icelandic-data/data/processed/bank_payouts.csv')
ORDER BY year

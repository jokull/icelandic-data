-- Monthly passenger data for Keflavik airport (2019-2025)
SELECT
    date,
    year,
    month_num as month,
    passengers,
    passengers - LAG(passengers) OVER (ORDER BY date) as mom_change,
    ROUND(100.0 * (passengers - LAG(passengers, 12) OVER (ORDER BY date)) /
        NULLIF(LAG(passengers, 12) OVER (ORDER BY date), 0), 1) as yoy_pct
FROM read_csv('../data/processed/keflavik_passengers_recent.csv')
ORDER BY date

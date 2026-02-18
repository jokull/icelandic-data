-- Year-over-year comparison 2024 vs 2025
WITH monthly AS (
    SELECT
        month_num as month,
        year,
        passengers
    FROM read_csv('../data/processed/keflavik_passengers_recent.csv')
),
pivoted AS (
    SELECT
        month,
        MAX(CASE WHEN year = 2024 THEN passengers END) as y2024,
        MAX(CASE WHEN year = 2025 THEN passengers END) as y2025
    FROM monthly
    GROUP BY month
)
SELECT
    month,
    CASE month
        WHEN 1 THEN 'Jan' WHEN 2 THEN 'Feb' WHEN 3 THEN 'Mar'
        WHEN 4 THEN 'Apr' WHEN 5 THEN 'May' WHEN 6 THEN 'Jun'
        WHEN 7 THEN 'Jul' WHEN 8 THEN 'Aug' WHEN 9 THEN 'Sep'
        WHEN 10 THEN 'Oct' WHEN 11 THEN 'Nov' WHEN 12 THEN 'Dec'
    END as month_name,
    y2024 as "2024",
    y2025 as "2025",
    ROUND(100.0 * (y2025 - y2024) / y2024, 1) as growth_pct
FROM pivoted
WHERE y2024 IS NOT NULL AND y2025 IS NOT NULL
ORDER BY month

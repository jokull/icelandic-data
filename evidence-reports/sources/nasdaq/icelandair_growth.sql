-- Icelandair passenger growth announcements
SELECT
    date,
    headline
FROM read_csv('../data/processed/icelandair_passenger_growth.csv')
ORDER BY date DESC

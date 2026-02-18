-- Key events in Play Airlines history
SELECT
    date,
    REPLACE(REPLACE(event, 'Fly Play hf.: ', ''), 'Fly Play hf. ', '') as event,
    category
FROM read_csv('../data/processed/play_key_events.csv')
ORDER BY date DESC

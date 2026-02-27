# Loftgæði (Air Quality) — UST / Reykjavik

PM10, PM2.5, NO2, SO2, H2S monitoring via Umhverfisstofnun (Environment Agency).

## API

**Base URL:** `https://api.ust.is/aq/a/`

No authentication required. Returns JSON. CORS enabled.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `getStations` | All stations with coordinates, parameters, activity dates |
| `getStation/{local_id}` | Single station metadata |
| `getLatest` | Last 24h for all stations |
| `getCurrent/{local_id}` | Last 24h for one station |
| `getDate/date/{YYYY-MM-DD}` | All stations, all params, one day (hourly) |

### Response Structure (getDate)

```json
{
  "STA-IS0005A": {
    "name": "Reykjavik Grensas",
    "local_id": "STA-IS0005A",
    "parameters": {
      "PM10": {
        "unit": "µg/m3",
        "resolution": "1h",
        "0": { "endtime": "2024-03-15 23:00:00", "value": "42.5", "verification": 3 },
        ...
      }
    }
  }
}
```

Values are strings — cast to float. Numbered keys (0, 1, ...) are hourly readings.

## Key Reykjavik Stations

| Station | local_id | Type | Active |
|---------|----------|------|--------|
| Grensásvegur | STA-IS0005A | traffic | 1990– |
| Húsdýragarðurinn | STA-IS0006A | background | 2002– |
| Norðlingaholt | STA-IS0022A | industrial | 2011– |
| Laugarnes | STA-IS0061A | industrial | 2021– |

**Primary station for PM10/nagladekk (studded tire) analysis: Grensásvegur** (traffic station on major road).

## Pollutants

| Parameter | Relevance |
|-----------|-----------|
| PM10 | Spring dust from studded tires. EU 24h limit: 50 µg/m³ |
| PM2.5 | Fine particles. EU annual limit: 25 µg/m³ |
| NO2 | Traffic. EU 1h limit: 200 µg/m³ |
| H2S | Geothermal (Hellisheiði). Nuisance smell at 5 µg/m³ |

## Fetching Historical Data

### Bulk CSVs (preferred for past years)

Annual CSVs at `https://api.ust.is/static/aq/ust_aq_timeseries_{YEAR}.csv` (62-113 MB each).

- Available: 2015–2024 (no 2025 yet as of Feb 2026)
- Columns: `station_name, pollutantnotation, local_id, endtime, the_value, resolution, verification, validity, station_local_id, concentration`
- Date formats vary: `YYYY-MM-DD HH:MM:SS` (2015-2021) and `DD/MM/YYYY HH:MM:SS` (2022+)
- Filter: `station_local_id == "STA-IS0005A"` and `pollutantnotation == "PM10"`
- **Sensor errors**: filter `the_value < 2000` (values >2000 are instrument faults)

### Per-day API (for current year)

```python
import httpx

def fetch_pm10_day(date_str: str, station: str = "STA-IS0005A") -> list[dict]:
    """Fetch hourly PM10 for one day. date_str: YYYY-MM-DD"""
    url = f"https://api.ust.is/aq/a/getDate/date/{date_str}"
    resp = httpx.get(url, timeout=30)
    data = resp.json()
    station_data = data.get(station, {})
    pm10 = station_data.get("parameters", {}).get("PM10", {})
    rows = []
    for k, v in pm10.items():
        if isinstance(v, dict) and "value" in v:
            rows.append({"datetime": v["endtime"], "pm10": float(v["value"])})
    return rows
```

**Rate limiting:** No documented limits. Use 0.15s delay between requests.

### Pre-built script

`uv run python scripts/air_quality.py` — downloads bulk CSVs + API for recent data, outputs `data/processed/reykjavik_pm10_daily.csv` with PM10 + wind + weather joined.

## Reykjavik loftapi (alternative, currently down)

**Base URL:** `http://loftapi.reykjavik.is/api/v1/stations/data/{station}/{pollutant}/{start}/{sh}/{sm}/{end}/{eh}/{em}`

- Station 02 = Grensásvegur, pollutant 91 = PM10
- Date format: DD-MM-YYYY
- As of Feb 2026: connection times out. Use UST API instead.

## Wind Data (for dust correlation)

Use Open-Meteo for historical daily wind speed in Reykjavik:

```
https://archive-api.open-meteo.com/v1/archive?latitude=64.13&longitude=-21.90&start_date=2024-01-01&end_date=2024-12-31&daily=wind_speed_10m_max,wind_speed_10m_mean,precipitation_sum&timezone=Atlantic/Reykjavik
```

Low wind + dry = high PM10 (dust not dispersed). High wind can also resuspend settled dust.

## Caveats

1. **getDate is slow for bulk** — one HTTP request per day. Multi-year fetch takes hours.
2. **Missing data** — some days return no PM10 readings (maintenance, sensor issues)
3. **Verification field** — 3 = unverified real-time, 1 = verified. Historical data may be adjusted.
4. **Grensásvegur bias** — traffic station, reads higher than background. Compare with Húsdýragarðurinn for urban background.

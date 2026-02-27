# Veðurstofa Íslands (Icelandic Meteorological Office)

Weather observations, forecasts, and climatological data for Iceland.

## API

**Base URL:** `https://xmlweather.vedur.is/`

No authentication required. Returns XML.

**Do NOT use `apis.is`** — SSL certificate expired. Use `xmlweather.vedur.is` directly.

## Fetching Data

### Current observations
```bash
curl -s "https://xmlweather.vedur.is/?op_w=xml&type=obs&lang=en&view=xml&ids=1&params=T;F;FX;FG;D;R;RH;P;N;TD;V&time=1h"
```

### Forecasts
```bash
curl -s "https://xmlweather.vedur.is/?op_w=xml&type=forec&lang=en&view=xml&ids=1"
```

### Available parameters

| Param | Description |
|-------|-------------|
| T | Temperature (°C) |
| F | Wind speed (m/s) |
| FX | Max wind speed (m/s) |
| FG | Wind gust (m/s) |
| D | Wind direction |
| SND | Snow depth (cm) — manual stations only |
| SNC | Snow description |
| SED | Snow type |
| R | Precipitation (mm) |
| RH | Relative humidity (%) |
| P | Atmospheric pressure (hPa) |
| N | Cloud cover |
| TD | Dew point (°C) |
| V | Visibility (km) |

## Key Stations

| Station | ID | Notes |
|---------|-----|-------|
| Reykjavík | 1 | Main station, records from 1866 |

Station IDs are integers. Full list available from the XML API or the vedur.is website.

## Historical / Climatological Data

**Web interface:** `https://en.vedur.is/climatology/data/`

- Monthly averages from 1961+ (some stations from 1830s)
- Reykjavík (station 1) has data from 1866
- Parameters: temperature (mean/max/min), precipitation, humidity, pressure, cloud cover, sunshine hours, wind
- **No direct API** — requires form-based navigation on the website
- Text file downloads at `vedur.is/vedur/vedurfar/medaltalstoflur/` serve HTML pages, not direct files — Playwright may be needed for bulk download

## Python Package

```bash
uv add iceweather
```

```python
from iceweather import observation_for_station, forecast_for_station, forecast_text

# Current observation
obs = observation_for_station(1)  # Reykjavík

# Forecast
fc = forecast_for_station(1)

# Text forecast (general)
text = forecast_text()
```

**Note:** `iceweather` wraps the XML API — current obs and forecasts only, no historical data.

## Caveats

1. **No historical API** — the XML API only provides current/recent observations and forecasts, not time series. Historical bulk data requires form-based downloads from the web interface (or Playwright scraping).
2. **Snow depth (SND)** — only measured at manual observation stations, not available from all automated stations.
3. **Station coverage** — not all parameters available at all stations. Highland stations may report fewer variables.
4. **Rate limiting** — no documented rate limits, but be reasonable with request frequency.

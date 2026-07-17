---
name: vedur
description: Icelandic Met Office (Veðurstofa) — weather observations, stations, forecasts and earthquakes via the modern JSON API at api.vedur.is.
---

# Veðurstofa Íslands (Icelandic Meteorological Office)

Weather observations, forecasts, climatological data and **earthquakes** for Iceland.

## API — use `api.vedur.is` (JSON, OpenAPI)

**Base URLs:** `https://api.vedur.is/weather` · `https://api.vedur.is/quakes`

No authentication. JSON. Both are OpenAPI-described and browsable:

| | |
|---|---|
| Swagger UI | `https://api.vedur.is/weather/` · `https://api.vedur.is/quakes/` |
| Spec | `https://api.vedur.is/weather/openapi.json` (274 KB) · `.../quakes/openapi.json` |
| Versions seen | Weather `2026-02-17`, Quakes `2026-07-01` |

**The spec is authoritative, the summaries are not.** `GET /quakes/events` is
summarised "Returns Quake Information As Geojson Or Csv", but `format` only
accepts `csv|json` — and `json` returns GeoJSON anyway. Read `openapi.json`
before believing prose.

### Weather

```bash
# The cheapest liveness/shape check — 2.9 KB, lists every observation type
curl -s "https://api.vedur.is/weather/capabilities"

# Stations (776 of them, ~150 KB)
curl -s "https://api.vedur.is/weather/stations"
curl -s "https://api.vedur.is/weather/stations/1"

# Latest automatic-weather-station observations
curl -s "https://api.vedur.is/weather/observations/aws/10min/latest"
curl -s "https://api.vedur.is/weather/observations/aws/hour/latest"

# Parameter descriptions (what T, F, FX… mean)
curl -s "https://api.vedur.is/weather/parameters"
```

Aggregations: `10min`, `hour`, `day`, `month`, `year`. There is also an OGC
**EDR** interface under `/weather/rodeo/collections/{aggregation}/` with
`locations`, `area` and `cube` queries — worth reaching for if you want
standards-based spatial/temporal slicing rather than the bespoke endpoints.

### Quakes (new — no equivalent in the old XML API)

```bash
# Events since a timestamp, magnitude filtered -> GeoJSON FeatureCollection
curl -s "https://api.vedur.is/quakes/events?start_time=2026-07-16T00:00:00&size_min=1"

# Just the count — returns a bare number, ideal for a cheap check
curl -s "https://api.vedur.is/quakes/events/count?start_time=2026-07-16T00:00:00"

curl -s "https://api.vedur.is/quakes/events/IMO2026nwqkrn"   # one event
curl -s "https://api.vedur.is/quakes/regions"                # seismic regions
```

Each feature carries `event_id`, `time`, `magnitude`, `depth`, `region`,
`type`, `evaluation_mode` (`manual`|`automatic`), `updated_time`.

Filters: `start_time`, `end_time`, `depth_min/max`, `size_min/max`, `lat`,
`lon`, `type`, `evaluation_mode`, `system`. Times are `yyyy-mm-ddTHH:MM:SS`.
There is **no `limit`** — bound queries with `start_time`, or you will pull the
lot (`limit` returns 422 `extra_forbidden`).

`system` defaults to `seiscomp`; `sil` is the legacy IMO system and the spec
says it "will eventually be phased out" — don't build on `sil`.

## Legacy: `xmlweather.vedur.is` (still up, but outdated)

The old XML endpoint still responds and is what this repo probed first, but
Veðurstofa now offers the API above and it should be preferred for anything new
([#9](https://github.com/jokull/icelandic-data/issues/9), thanks @thordurka).
It has no earthquake data at all.

```bash
# Current observations
curl -s "https://xmlweather.vedur.is/?op_w=xml&type=obs&lang=en&view=xml&ids=1&params=T;F;FX;FG;D;R;RH;P;N;TD;V&time=1h"

# Forecasts — still the simplest source for these
curl -s "https://xmlweather.vedur.is/?op_w=xml&type=forec&lang=en&view=xml&ids=1"
```

**Do NOT use `apis.is`** — SSL certificate expired. Use `api.vedur.is`.

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

# Umferð (Traffic) — Vegagerðin

Real-time traffic counter data from the Icelandic Road Administration via GeoServer WFS.

## API

**Base URL:** `https://gagnaveita.vegagerdin.is/geoserver/gis/ows?`

No authentication required. WFS 1.0.0 protocol. Returns GeoJSON, CSV, GML, or Shapefile.

### Layers

| Layer | Features | Description |
|-------|----------|-------------|
| `gis:umferdvika_2021_1` | ~254 | Real-time counters: 15-min count, today's count, rolling 7-day daily totals |
| `gis:umf_talningar_stefnugreint_stadir` | ~248 | Station metadata with direction, elevation, compass heading |

### WFS Request Pattern

```
{base}?service=WFS&version=1.0.0&request=GetFeature&typeName={layer}&outputFormat=application/json&srsName=EPSG:4326
```

### Parameters

| Parameter | Values |
|-----------|--------|
| `srsName` | `EPSG:4326` (WGS84) or `EPSG:3057` (ISN93) |
| `outputFormat` | `application/json`, `csv`, `GML2`, `GML3`, `shape-zip` |
| `cql_filter` | e.g. `IDSTOD=912` to filter by station |
| `maxFeatures` | Limit number of features returned |

### Example Requests

```bash
# All stations as GeoJSON (WGS84)
curl "https://gagnaveita.vegagerdin.is/geoserver/gis/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=gis:umferdvika_2021_1&outputFormat=application/json&srsName=EPSG:4326"

# Single station
curl "https://gagnaveita.vegagerdin.is/geoserver/gis/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=gis:umferdvika_2021_1&cql_filter=IDSTOD=912&outputFormat=application/json&srsName=EPSG:4326"
```

## Real-Time Layer Schema (`gis:umferdvika_2021_1`)

| Field | Type | Description |
|-------|------|-------------|
| OBJECTID | INT | Unique per measurement point (direction-specific) |
| IDSTOD | INT | Station ID (may appear twice for directional stations) |
| NAFN | STRING | Station name (e.g., "Gufuá", "Dettifoss") |
| STEFNA | STRING | Direction — see below |
| UMF_15MIN | INT | Vehicles in last 15 minutes |
| MEDALHRADI_15MIN | INT | Avg speed km/h last 15 min (only for type 4 classifiers) |
| UMF_I_DAG | INT | Vehicles since midnight |
| DAGS_SIDUSTUGAGNA | DATE | Timestamp of latest data received |
| UMF_DAGUR1..7 | INT | Daily vehicle count for last 1..7 days |
| DAGS_DAGUR1..7 | DATE | Date for each of the 7 daily counts |
| MAELISTOD_TEGUND | INT | Station type (see below) |
| SHAPE | POINT | Coordinates [lon, lat] in requested SRS |

## Station Metadata Layer (`gis:umf_talningar_stefnugreint_stadir`)

| Field | Type | Description |
|-------|------|-------------|
| IDSTADUR | STRING | Location ID |
| IDSTOD | INT | Station ID |
| IDSTEFNA | INT | Direction code |
| NAFN | STRING | Station name |
| STEFNA_TXT | STRING | Direction text |
| NSAV_STEFNA | STRING | Compass code |
| HAED | INT | Elevation (m) |
| UMFERD | INT | Latest traffic count |
| DAGS_UMFERD | DATE | Timestamp of latest count |
| MEDALHRADI | INT | Average speed (if available) |
| STAERDARFLOKKUR | STRING | Size class ("all") |
| MAELISTOD_TEGUND | INT | Station type |

## Station Types (MAELISTOD_TEGUND)

| Code | Type | Description |
|------|------|-------------|
| 1 | Veðurstöð | Counter co-located with weather station |
| 2 | Umferðarteljari | Dedicated traffic counter |
| 4 | Umferðargreinir | Traffic classifier (provides speed data) |

## Direction Field (STEFNA)

- Directional: `"Til norðurs"`, `"Frá Þingvöllum"`, etc.
- Combined: `"Samanlögð umferð óháð stefnu"` (both directions summed)
- Directional stations have two OBJECTIDs sharing the same IDSTOD

**Double-count warning:** When aggregating, use either combined records OR directional records, never both.

## Key Caveat: No Historical API

The API only provides a **rolling 7-day window**. There is no endpoint for historical data. To build a time series, you must poll regularly (daily) and accumulate into a local store. The `collect` subcommand handles this.

## Script Usage

```bash
# List all counting stations
uv run python scripts/umferd.py stations

# Fetch current real-time snapshot
uv run python scripts/umferd.py snapshot

# Collect rolling 7-day data into history (run daily via cron)
uv run python scripts/umferd.py collect

# Generate HTML traffic report
uv run python scripts/umferd.py report
```

## Data Files

| File | Format | Description |
|------|--------|-------------|
| `data/raw/umferd/stations.csv` | CSV | Station metadata with coordinates |
| `data/raw/umferd/snapshot_*.json` | GeoJSON | Raw API snapshots |
| `data/processed/umferd_snapshot.csv` | CSV | Latest real-time flat data |
| `data/processed/umferd_daily.parquet` | Parquet | Accumulated daily history (append + dedup) |
| `reports/umferd-traffic.html` | HTML | Self-contained traffic report |

## Other Caveats

- **Encoding.** GeoServer WFS returns UTF-8 GeoJSON. Station names contain Icelandic chars (`Þingvellir`, `Hvalfjörður`, `Mývatn`, `Sólheimasandur`); direction labels combine spatial Icelandic (`Til norðurs`, `Frá Reykjavík`). Read with `httpx.json()` defaults; write CSV with `encoding="utf-8"`.
- **Rate-limiting.** No declared rate limit on `gagnaveita.vegagerdin.is`. Intended cadence is one snapshot per quarter-hour (matches the source update interval). A daily `collect` cron is well within budget.
- **Double-counting directional data.** A single physical site often emits two rows — one per direction. When summing flows for a region, group by station-id-without-direction or filter on a single `STEFNA` value.

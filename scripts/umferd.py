"""
Vegagerðin traffic counter data — fetch, accumulate, and report.

Data source: GeoServer WFS at gagnaveita.vegagerdin.is
See .claude/skills/umferd.md for full API documentation.

Usage:
    uv run python scripts/umferd.py stations   # List all counting stations
    uv run python scripts/umferd.py snapshot    # Current real-time data
    uv run python scripts/umferd.py collect     # Accumulate 7-day rolling data
    uv run python scripts/umferd.py report      # Generate HTML traffic report
"""

import argparse
import json
from datetime import datetime, date
from pathlib import Path

import httpx
import polars as pl

WFS_BASE = "https://gagnaveita.vegagerdin.is/geoserver/gis/ows"
LAYER_REALTIME = "gis:umferdvika_2021_1"
LAYER_STATIONS = "gis:umf_talningar_stefnugreint_stadir"

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "umferd"
PROCESSED_DIR = ROOT / "data" / "processed"
HISTORY_FILE = PROCESSED_DIR / "umferd_daily.parquet"
REPORTS_DIR = ROOT / "reports"

STATION_TYPES = {1: "Veðurstöð", 2: "Umferðarteljari", 4: "Umferðargreinir"}


def fetch_wfs(layer: str) -> list[dict]:
    """Fetch all features from a WFS layer as GeoJSON."""
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    resp = httpx.get(WFS_BASE, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("features", [])


def parse_geojson(features: list[dict], extra_fields: list[str] | None = None) -> list[dict]:
    """Extract properties + lon/lat from GeoJSON features."""
    rows = []
    for f in features:
        props = {k.lower(): v for k, v in f.get("properties", {}).items()}
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        props["lon"] = coords[0]
        props["lat"] = coords[1]
        if extra_fields:
            rows.append({k: props.get(k) for k in extra_fields})
        else:
            rows.append(props)
    return rows


# ---------------------------------------------------------------------------
# stations
# ---------------------------------------------------------------------------

def cmd_stations():
    """List all counting stations with metadata and coordinates."""
    print("Fetching station metadata...")
    features = fetch_wfs(LAYER_STATIONS)
    print(f"  {len(features)} features received")

    fields = [
        "idstadur", "idstod", "idstefna", "nafn", "stefna_txt",
        "nsav_stefna", "haed", "umferd", "dags_umferd", "medalhradi",
        "staerdarflokkur", "maelistod_tegund", "lon", "lat",
    ]
    rows = parse_geojson(features, fields)
    df = pl.DataFrame(rows, infer_schema_length=len(rows))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "stations.csv"
    df.write_csv(out)
    print(f"  Wrote {out}")

    # Summary
    type_counts = (
        df.group_by("maelistod_tegund")
        .len()
        .sort("maelistod_tegund")
    )
    print("\nStation types:")
    for row in type_counts.iter_rows(named=True):
        t = row["maelistod_tegund"]
        label = STATION_TYPES.get(t, f"Unknown ({t})")
        print(f"  {label}: {row['len']}")

    print(f"\nTotal stations: {len(df)}")


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def cmd_snapshot():
    """Fetch current real-time traffic data."""
    print("Fetching real-time traffic data...")
    features = fetch_wfs(LAYER_REALTIME)
    print(f"  {len(features)} measurement points received")

    # Save raw GeoJSON
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    raw_path = RAW_DIR / f"snapshot_{ts}.json"
    raw_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    print(f"  Raw GeoJSON: {raw_path}")

    # Parse flat fields
    flat_fields = [
        "objectid", "idstod", "nafn", "stefna", "umf_15min",
        "medalhradi_15min", "umf_i_dag", "dags_sidustugagna",
        "maelistod_tegund", "lon", "lat",
    ]
    rows = parse_geojson(features, flat_fields)
    df = pl.DataFrame(rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "umferd_snapshot.csv"
    df.write_csv(out)
    print(f"  Snapshot CSV: {out}")

    # Print current stats
    total_15 = df.select(pl.col("umf_15min").sum()).item()
    total_today = df.select(pl.col("umf_i_dag").sum()).item()
    print(f"\n  Vehicles in last 15 min (all stations): {total_15 or 0:,}")
    print(f"  Vehicles since midnight (all stations):  {total_today or 0:,}")

    # Top 5 busiest right now
    busiest = (
        df.filter(pl.col("umf_i_dag").is_not_null())
        .sort("umf_i_dag", descending=True)
        .head(5)
    )
    print("\n  Top 5 stations today:")
    for row in busiest.iter_rows(named=True):
        print(f"    {row['nafn']:30s} {row['stefna']:40s} {row['umf_i_dag']:>6,} vehicles")


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

def cmd_collect():
    """Collect rolling 7-day data and accumulate into Parquet history."""
    print("Fetching real-time data for collection...")
    features = fetch_wfs(LAYER_REALTIME)
    print(f"  {len(features)} measurement points received")

    # Unpivot wide DAGUR1..7 columns into long format
    today = date.today().isoformat()
    long_rows = []
    for f in features:
        props = {k.lower(): v for k, v in f.get("properties", {}).items()}
        coords = f.get("geometry", {}).get("coordinates", [None, None])

        base = {
            "idstod": props.get("idstod"),
            "nafn": props.get("nafn"),
            "stefna": props.get("stefna"),
            "maelistod_tegund": props.get("maelistod_tegund"),
            "lon": coords[0],
            "lat": coords[1],
            "collected_at": today,
        }

        for i in range(1, 8):
            count = props.get(f"umf_dagur{i}")
            dags = props.get(f"dags_dagur{i}")
            if count is None or dags is None:
                continue
            row = dict(base)
            # Parse date: "2026-04-14T23:59:59Z" -> "2026-04-14"
            row["date"] = str(dags)[:10]
            row["daily_count"] = count
            long_rows.append(row)

    if not long_rows:
        print("  No data to collect.")
        return

    new_df = pl.DataFrame(long_rows).with_columns(
        pl.col("date").str.to_date("%Y-%m-%d"),
        pl.col("collected_at").str.to_date("%Y-%m-%d"),
    )
    new_count = len(new_df)
    print(f"  Unpivoted {new_count} daily records from rolling 7-day window")

    # Load existing history and merge
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        existing = pl.read_parquet(HISTORY_FILE)
        combined = pl.concat([existing, new_df], how="diagonal_relaxed")
    else:
        combined = new_df

    # Deduplicate: keep latest collection for each station+direction+date
    deduped = (
        combined
        .sort("collected_at")
        .unique(subset=["idstod", "stefna", "date"], keep="last")
        .sort(["idstod", "date"])
    )

    before = len(combined) - len(new_df) if HISTORY_FILE.exists() else 0
    deduped.write_parquet(HISTORY_FILE)

    added = len(deduped) - before
    date_min = deduped.select(pl.col("date").min()).item()
    date_max = deduped.select(pl.col("date").max()).item()
    print(f"\n  History: {HISTORY_FILE}")
    print(f"  New rows added: {added}")
    print(f"  Total rows:     {len(deduped):,}")
    print(f"  Date range:     {date_min} to {date_max}")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def cmd_report():
    """Generate self-contained HTML traffic report."""
    if not HISTORY_FILE.exists():
        print(f"No history file found at {HISTORY_FILE}")
        print("Run 'collect' first: uv run python scripts/umferd.py collect")
        return

    print("Reading traffic history...")
    df = pl.read_parquet(HISTORY_FILE)

    # --- Station map data ---
    stations_file = RAW_DIR / "stations.csv"
    if stations_file.exists():
        stations_df = pl.read_csv(stations_file)
        stations_data = stations_df.select(
            "idstod", "nafn", "stefna_txt", "haed", "maelistod_tegund", "lon", "lat"
        ).unique(subset=["idstod", "stefna_txt"]).to_dicts()
    else:
        # Fall back to extracting from history
        stations_data = (
            df.select("idstod", "nafn", "stefna", "maelistod_tegund", "lon", "lat")
            .unique(subset=["idstod", "stefna"])
            .rename({"stefna": "stefna_txt"})
            .with_columns(pl.lit(None).alias("haed"))
            .to_dicts()
        )

    # --- Daily trend: total vehicles per day ---
    # Prefer "Samanlögð umferð" records to avoid double-counting
    combined_mask = pl.col("stefna").str.contains("(?i)samanlögð|samanlagð|samanlög")
    has_combined = df.filter(combined_mask).height > 0

    if has_combined:
        trend_df = df.filter(combined_mask)
    else:
        # Use all records but deduplicate by station+date (sum directions)
        trend_df = (
            df.group_by(["idstod", "date"])
            .agg(pl.col("daily_count").sum())
        )

    daily_trend = (
        trend_df
        .group_by("date")
        .agg(pl.col("daily_count").sum().alias("total"))
        .sort("date")
        .with_columns(pl.col("date").cast(pl.Utf8))
        .to_dicts()
    )

    # --- Top 15 stations by average daily count ---
    top_stations = (
        trend_df
        .group_by(["idstod"])
        .agg(
            pl.col("daily_count").mean().round(0).alias("avg_daily"),
            pl.col("nafn").first(),
            pl.col("stefna").first() if "stefna" in trend_df.columns else pl.lit(""),
        )
        .sort("avg_daily", descending=True)
        .head(15)
        .to_dicts()
    )

    # Serialize for JSON
    for s in stations_data:
        for k, v in s.items():
            if isinstance(v, (date, datetime)):
                s[k] = str(v)

    stations_json = json.dumps(stations_data, ensure_ascii=False)
    trend_json = json.dumps(daily_trend, ensure_ascii=False)
    top_json = json.dumps(top_stations, ensure_ascii=False)

    # KPIs
    total_stations = df.select(pl.col("idstod").n_unique()).item()
    total_days = df.select(pl.col("date").n_unique()).item()
    date_min = str(df.select(pl.col("date").min()).item())
    date_max = str(df.select(pl.col("date").max()).item())
    avg_daily_total = int(sum(d["total"] for d in daily_trend) / max(len(daily_trend), 1))

    html = _build_report_html(
        stations_json=stations_json,
        trend_json=trend_json,
        top_json=top_json,
        total_stations=total_stations,
        total_days=total_days,
        date_min=date_min,
        date_max=date_max,
        avg_daily_total=avg_daily_total,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "umferd-traffic.html"
    out.write_text(html, encoding="utf-8")
    print(f"Report written to {out}")


def _build_report_html(
    stations_json: str,
    trend_json: str,
    top_json: str,
    total_stations: int,
    total_days: int,
    date_min: str,
    date_max: str,
    avg_daily_total: int,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="is">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Umferðarteljarar — Vegagerðin</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f5f6fa; color: #2d3436; line-height: 1.6; padding: 2rem 1rem;
  }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }}
  .subtitle {{ color: #636e72; font-size: 0.95rem; margin-bottom: 2rem; }}
  .card {{
    background: #fff; border-radius: 12px; padding: 1.5rem;
    margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .card h2 {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem; }}
  .chart-wrap {{ height: 360px; position: relative; }}
  .kpi-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem; margin-bottom: 1.5rem;
  }}
  .kpi {{
    background: #fff; border-radius: 12px; padding: 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .kpi .label {{ font-size: 0.8rem; color: #636e72; text-transform: uppercase; letter-spacing: 0.5px; }}
  .kpi .value {{ font-size: 1.6rem; font-weight: 700; margin-top: 0.25rem; }}
  .kpi .detail {{ font-size: 0.85rem; margin-top: 0.15rem; color: #636e72; }}
  #map {{ height: 420px; border-radius: 8px; }}
  .footer {{ text-align: center; color: #b2bec3; font-size: 0.8rem; margin-top: 2rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>Umferðarteljarar — Vegagerðin</h1>
  <p class="subtitle">Traffic counter data &middot; {date_min} to {date_max}</p>

  <div class="kpi-row">
    <div class="kpi">
      <div class="label">Counting Stations</div>
      <div class="value">{total_stations}</div>
    </div>
    <div class="kpi">
      <div class="label">Days Collected</div>
      <div class="value">{total_days}</div>
    </div>
    <div class="kpi">
      <div class="label">Avg Daily Total</div>
      <div class="value">{avg_daily_total:,}</div>
      <div class="detail">vehicles / day (all stations)</div>
    </div>
  </div>

  <div class="card">
    <h2>Station Map</h2>
    <div id="map"></div>
  </div>

  <div class="card">
    <h2>Daily Traffic Trend</h2>
    <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Top 15 Stations — Average Daily Count</h2>
    <div class="chart-wrap"><canvas id="topChart"></canvas></div>
  </div>

  <p class="footer">
    Data: Vegagerðin &middot; Leaflet + Chart.js &middot; Generated {date.today().isoformat()}
  </p>
</div>

<script>
const stations = {stations_json};
const trend = {trend_json};
const top = {top_json};

// === Station Map ===
const map = L.map('map').setView([64.9, -18.5], 6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 15
}}).addTo(map);

const typeColors = {{ 1: '#0984e3', 2: '#00b894', 4: '#e17055' }};
const typeLabels = {{ 1: 'Weather station', 2: 'Traffic counter', 4: 'Traffic classifier' }};

stations.forEach(s => {{
  if (s.lat == null || s.lon == null) return;
  const color = typeColors[s.maelistod_tegund] || '#636e72';
  const label = typeLabels[s.maelistod_tegund] || 'Unknown';
  L.circleMarker([s.lat, s.lon], {{
    radius: 6, fillColor: color, color: '#fff', weight: 1.5,
    fillOpacity: 0.85
  }}).addTo(map).bindPopup(
    `<strong>${{s.nafn}}</strong><br>` +
    `${{s.stefna_txt || ''}}<br>` +
    `Type: ${{label}}<br>` +
    (s.haed != null ? `Elevation: ${{s.haed}} m` : '')
  );
}});

// Legend
const legend = L.control({{ position: 'bottomright' }});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div', 'leaflet-control');
  div.style.cssText = 'background:#fff;padding:8px 12px;border-radius:8px;font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.2)';
  div.innerHTML = Object.entries(typeColors).map(([k,c]) =>
    `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{c}};margin-right:4px"></span>${{typeLabels[k]}}`
  ).join('<br>');
  return div;
}};
legend.addTo(map);

// === Daily Trend Chart ===
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: trend.map(d => d.date),
    datasets: [{{
      label: 'Total vehicles',
      data: trend.map(d => d.total),
      borderColor: '#0984e3',
      backgroundColor: 'rgba(9,132,227,0.08)',
      fill: true, tension: 0.3,
      pointRadius: trend.length > 30 ? 0 : 4,
      borderWidth: 2,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{
        label: ctx => ctx.parsed.y.toLocaleString() + ' vehicles'
      }} }}
    }},
    scales: {{
      y: {{ beginAtZero: false, grid: {{ color: '#f0f0f0' }},
        ticks: {{ callback: v => (v / 1000).toFixed(0) + 'k' }} }},
      x: {{ grid: {{ display: false }},
        ticks: {{ maxTicksLimit: 14 }} }}
    }}
  }}
}});

// === Top Stations Bar Chart ===
new Chart(document.getElementById('topChart'), {{
  type: 'bar',
  data: {{
    labels: top.map(d => d.nafn + (d.stefna ? ' (' + d.stefna.substring(0, 20) + ')' : '')),
    datasets: [{{
      label: 'Avg daily vehicles',
      data: top.map(d => d.avg_daily),
      backgroundColor: 'rgba(0,184,148,0.7)',
      borderColor: '#00b894',
      borderWidth: 1, borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{
        label: ctx => ctx.parsed.x.toLocaleString() + ' vehicles/day'
      }} }}
    }},
    scales: {{
      x: {{ grid: {{ color: '#f0f0f0' }},
        ticks: {{ callback: v => v.toLocaleString() }} }},
      y: {{ grid: {{ display: false }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Vegagerðin traffic counter data"
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("stations", help="List all counting stations")
    sub.add_parser("snapshot", help="Fetch current real-time data")
    sub.add_parser("collect", help="Collect rolling 7-day data into history")
    sub.add_parser("report", help="Generate HTML traffic report")

    args = parser.parse_args()
    commands = {
        "stations": cmd_stations,
        "snapshot": cmd_snapshot,
        "collect": cmd_collect,
        "report": cmd_report,
    }
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

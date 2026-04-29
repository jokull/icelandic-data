"""
Iceland map generator — static and interactive maps from cached LMI geodata.

Reads pre-downloaded GeoJSON layers from data/geodata/ and produces either
interactive Leaflet HTML reports or static PNG/SVG maps via geopandas+matplotlib.

Usage:
    uv run python scripts/kortagerð.py html -o reports/iceland-map.html
    uv run python scripts/kortagerð.py static -o reports/iceland-map.png
    uv run python scripts/kortagerð.py static --bounds capital -o reports/reykjavik.png
    uv run python scripts/kortagerð.py static --highlight "Reykjavíkurborg" -o reports/rvk.png
"""

import argparse
import json
from datetime import date
from pathlib import Path

GEODATA_DIR = Path(__file__).parent.parent / "data" / "geodata"
REPORTS_DIR = Path(__file__).parent.parent / "reports"

# Named bounding boxes [west, south, east, north] in WGS84
BOUNDS_PRESETS = {
    "iceland": [-24.7, 63.2, -13.1, 66.6],
    "capital": [-22.1, 63.95, -21.3, 64.25],
    "reykjavik": [-22.1, 63.95, -21.3, 64.25],
    "southwest": [-22.5, 63.6, -19.5, 64.5],
    "north": [-20.0, 65.2, -15.0, 66.6],
    "east": [-16.0, 64.2, -13.3, 65.8],
    "westfjords": [-24.7, 65.0, -21.0, 66.6],
    "south": [-21.0, 63.2, -17.5, 64.3],
    "akureyri": [-18.4, 65.5, -17.7, 65.8],
}


def load_layer(name: str):
    """Load a cached GeoJSON layer by short name (e.g., 'Landmask')."""
    path = GEODATA_DIR / f"{name}.geojson"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def available_layers() -> list[str]:
    """List cached layer names (without extension)."""
    if not GEODATA_DIR.exists():
        return []
    return sorted(p.stem for p in GEODATA_DIR.glob("*.geojson"))


# ---------------------------------------------------------------------------
# Interactive HTML map (Leaflet)
# ---------------------------------------------------------------------------

def cmd_html(args):
    """Generate interactive Leaflet HTML map."""
    layers = available_layers()
    if not layers:
        print("No cached geodata. Run: uv run python scripts/lmi.py download")
        return

    # Load core layers for the interactive map
    landmask = load_layer("Landmask")
    roads = load_layer("RoadLines")
    glaciers = load_layer("LandIceArea")
    lakes = load_layer("Lake_Reservoir")
    settlements = load_layer("BuiltupAreaPoints")
    admin = load_layer("AdministrativeUnit_level2")
    if admin is None:
        admin = load_layer("AdministrativeAreas")
    nature = load_layer("NatureParkArea")

    # Determine bounds
    if args.bounds and args.bounds in BOUNDS_PRESETS:
        bounds = BOUNDS_PRESETS[args.bounds]
    else:
        bounds = BOUNDS_PRESETS["iceland"]

    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    zoom = 6 if args.bounds in (None, "iceland") else 9

    title = args.title or "Iceland"

    # Serialize layers
    def to_json(layer):
        return json.dumps(layer, ensure_ascii=False) if layer else "null"

    html = f"""<!DOCTYPE html>
<html lang="is">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  #map {{ width: 100vw; height: 100vh; }}
  .title-overlay {{
    position: absolute; top: 12px; left: 60px; z-index: 1000;
    background: rgba(255,255,255,0.92); padding: 8px 16px;
    border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-size: 1.1rem; font-weight: 600;
  }}
  .info {{ padding: 6px 8px; font: 13px/1.4 sans-serif; background: rgba(255,255,255,0.9); border-radius: 6px; box-shadow: 0 0 6px rgba(0,0,0,0.2); }}
</style>
</head>
<body>
<div class="title-overlay">{title}</div>
<div id="map"></div>
<script>
const map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_nolabels/{{z}}/{{x}}/{{y}}@2x.png', {{
  attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OSM</a>',
  maxZoom: 18
}}).addTo(map);

// --- Layers ---
const landmask = {to_json(landmask)};
const roads = {to_json(roads)};
const glaciers = {to_json(glaciers)};
const lakes = {to_json(lakes)};
const settlements = {to_json(settlements)};
const admin = {to_json(admin)};
const nature = {to_json(nature)};

const overlays = {{}};

if (landmask) {{
  const lm = L.geoJSON(landmask, {{
    style: {{ fillColor: '#f8f4ec', fillOpacity: 1, color: '#2d3436', weight: 1.2 }}
  }}).addTo(map);
  overlays['Land'] = lm;
}}

if (admin) {{
  const adm = L.geoJSON(admin, {{
    style: {{ fillColor: 'transparent', fillOpacity: 0, color: '#b2bec3', weight: 0.6, dashArray: '4 3' }},
    onEachFeature: (f, layer) => {{
      const p = f.properties;
      layer.bindPopup(`<strong>${{p.namn || p.namn1 || p.name || ''}}</strong>`);
    }}
  }}).addTo(map);
  overlays['Municipalities'] = adm;
}}

if (nature) {{
  const nat = L.geoJSON(nature, {{
    style: {{ fillColor: '#a8e6cf', fillOpacity: 0.35, color: '#00b894', weight: 1 }},
    onEachFeature: (f, layer) => {{
      layer.bindPopup(`<strong>${{f.properties.namn1 || ''}}</strong><br>Nature reserve`);
    }}
  }});
  overlays['Nature Parks'] = nat;
}}

if (glaciers) {{
  const gl = L.geoJSON(glaciers, {{
    style: {{ fillColor: '#dfe6e9', fillOpacity: 0.9, color: '#b2bec3', weight: 0.8 }}
  }}).addTo(map);
  overlays['Glaciers'] = gl;
}}

if (lakes) {{
  const lk = L.geoJSON(lakes, {{
    style: {{ fillColor: '#74b9ff', fillOpacity: 0.6, color: '#0984e3', weight: 0.7 }}
  }}).addTo(map);
  overlays['Lakes'] = lk;
}}

if (roads) {{
  const rd = L.geoJSON(roads, {{
    style: f => {{
      const rtt = f.properties.rtt;
      if (rtt <= 3) return {{ color: '#d63031', weight: 2.5, opacity: 0.8 }};
      if (rtt <= 10) return {{ color: '#e17055', weight: 1.5, opacity: 0.7 }};
      return {{ color: '#b2bec3', weight: 0.8, opacity: 0.5 }};
    }},
    onEachFeature: (f, layer) => {{
      const p = f.properties;
      layer.bindPopup(`<strong>${{p.namn1 || 'Road'}}</strong><br>Route: ${{p.rtn || '—'}}`);
    }}
  }}).addTo(map);
  overlays['Roads'] = rd;
}}

if (settlements) {{
  const st = L.geoJSON(settlements, {{
    pointToLayer: (f, latlng) => {{
      const pop = f.properties.ppl || 0;
      const r = pop > 10000 ? 8 : pop > 1000 ? 5 : 3;
      return L.circleMarker(latlng, {{
        radius: r, fillColor: '#2d3436', color: '#fff',
        weight: 1.5, fillOpacity: 0.85
      }});
    }},
    onEachFeature: (f, layer) => {{
      const p = f.properties;
      layer.bindPopup(`<strong>${{p.namn1}}</strong><br>Population: ${{p.ppl ? p.ppl.toLocaleString() : '—'}}`);
      if (p.ppl && p.ppl > 800) {{
        layer.bindTooltip(p.namn1, {{ permanent: true, direction: 'right',
          className: 'settlement-label', offset: [8, 0] }});
      }}
    }}
  }}).addTo(map);
  overlays['Settlements'] = st;
}}

L.control.layers(null, overlays, {{ collapsed: false, position: 'topright' }}).addTo(map);

// Scale bar
L.control.scale({{ imperial: false, position: 'bottomleft' }}).addTo(map);
</script>
<style>
.settlement-label {{
  background: transparent; border: none; box-shadow: none;
  font-size: 11px; font-weight: 600; color: #2d3436;
  text-shadow: 1px 1px 2px #fff, -1px -1px 2px #fff, 1px -1px 2px #fff, -1px 1px 2px #fff;
}}
</style>
</body>
</html>"""

    out = Path(args.output) if args.output else REPORTS_DIR / "iceland-map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"Interactive map: {out} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Static map (matplotlib + geopandas)
# ---------------------------------------------------------------------------

def cmd_static(args):
    """Generate static PNG/SVG map via geopandas + matplotlib."""
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    layers_available = available_layers()
    if not layers_available:
        print("No cached geodata. Run: uv run python scripts/lmi.py download")
        return

    # Determine bounds
    if args.bounds and args.bounds in BOUNDS_PRESETS:
        bbox = BOUNDS_PRESETS[args.bounds]
    else:
        bbox = BOUNDS_PRESETS["iceland"]

    # Figure sizing
    aspect = (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])
    # Correct for latitude (at 65°N, longitude degrees are ~0.42x latitude degrees)
    lat_correction = 0.42
    aspect *= lat_correction
    fig_h = 10
    fig_w = max(fig_h * aspect, 6)

    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), facecolor="#f0f4f8")
    ax.set_facecolor("#c8d6e5")  # Ocean color

    def load_gdf(name):
        path = GEODATA_DIR / f"{name}.geojson"
        if path.exists():
            return gpd.read_file(path)
        return None

    # --- Draw layers bottom to top ---

    # Landmask
    gdf = load_gdf("Landmask")
    if gdf is not None:
        gdf.plot(ax=ax, color="#f5f0e6", edgecolor="#2d3436", linewidth=0.6, zorder=1)

    # Islands
    gdf = load_gdf("IslandArea")
    if gdf is not None:
        gdf.plot(ax=ax, color="#f5f0e6", edgecolor="#2d3436", linewidth=0.4, zorder=1)

    # Nature parks
    gdf = load_gdf("NatureParkArea")
    if gdf is not None:
        gdf.plot(ax=ax, color="#a8e6cf", alpha=0.4, edgecolor="#00b894", linewidth=0.5, zorder=2)

    # Administrative boundaries — prefer EBM (has namn) over ERM (code-based)
    gdf = load_gdf("AdministrativeUnit_level2")
    if gdf is None:
        gdf = load_gdf("AdministrativeAreas")
    if gdf is not None:
        name_col = "namn" if "namn" in gdf.columns else "namn1" if "namn1" in gdf.columns else None
        if args.highlight and name_col:
            mask = gdf[name_col].str.contains(args.highlight, case=False, na=False)
            gdf[~mask].plot(ax=ax, facecolor="none", edgecolor="#b2bec3", linewidth=0.3, linestyle="--", zorder=3)
            gdf[mask].plot(ax=ax, color="#ffeaa7", edgecolor="#fdcb6e", linewidth=1.5, zorder=3)
        else:
            gdf.plot(ax=ax, facecolor="none", edgecolor="#b2bec3", linewidth=0.3, linestyle="--", zorder=3)

    # Glaciers
    gdf = load_gdf("LandIceArea")
    if gdf is not None:
        gdf.plot(ax=ax, color="#dfe6e9", edgecolor="#b2bec3", linewidth=0.4, zorder=4)

    # Lakes
    gdf = load_gdf("Lake_Reservoir")
    if gdf is not None:
        gdf.plot(ax=ax, color="#74b9ff", edgecolor="#0984e3", linewidth=0.3, zorder=5)

    # Rivers
    gdf = load_gdf("WatercourseLine")
    if gdf is not None:
        gdf.plot(ax=ax, color="#0984e3", linewidth=0.25, alpha=0.5, zorder=6)

    # Roads
    gdf = load_gdf("RoadLines")
    if gdf is not None:
        if "rtt" in gdf.columns:
            major = gdf[gdf["rtt"].fillna(99) <= 3]
            minor = gdf[(gdf["rtt"].fillna(99) > 3) & (gdf["rtt"].fillna(99) <= 10)]
            other = gdf[gdf["rtt"].fillna(99) > 10]
            if not other.empty:
                other.plot(ax=ax, color="#b2bec3", linewidth=0.3, zorder=7)
            if not minor.empty:
                minor.plot(ax=ax, color="#e17055", linewidth=0.6, zorder=8)
            if not major.empty:
                major.plot(ax=ax, color="#d63031", linewidth=1.2, zorder=9)
        else:
            gdf.plot(ax=ax, color="#e17055", linewidth=0.5, zorder=7)

    # Settlements
    gdf = load_gdf("BuiltupAreaPoints")
    if gdf is not None:
        gdf = gdf.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        if not gdf.empty:
            sizes = gdf["ppl"].fillna(100).apply(lambda p: max(8, min(80, p / 200)))
            gdf.plot(ax=ax, color="#2d3436", markersize=sizes, zorder=10, edgecolor="white", linewidth=0.5)

            # Label settlements
            min_pop = 500 if args.bounds in (None, "iceland") else 200
            for _, row in gdf[gdf["ppl"].fillna(0) > min_pop].iterrows():
                ax.annotate(
                    row.get("namn1", ""),
                    xy=(row.geometry.x, row.geometry.y),
                    xytext=(5, 3), textcoords="offset points",
                    fontsize=7, fontweight="bold", color="#2d3436",
                    path_effects=[
                        __import__("matplotlib.patheffects", fromlist=["withStroke"]).withStroke(linewidth=2, foreground="white")
                    ],
                    zorder=11,
                )

    # Overlay custom points if provided
    if args.points:
        import polars as pl
        pts = pl.read_csv(args.points)
        lat_col = next((c for c in pts.columns if c.lower() in ("lat", "latitude", "breiddargrad")), None)
        lon_col = next((c for c in pts.columns if c.lower() in ("lon", "lng", "longitude", "lengdargrad")), None)
        if lat_col and lon_col:
            ax.scatter(
                pts[lon_col].to_list(), pts[lat_col].to_list(),
                c="#e74c3c", s=30, zorder=12, edgecolors="white", linewidth=0.8,
                marker="o",
            )
            name_col = next((c for c in pts.columns if c.lower() in ("name", "nafn", "label")), None)
            if name_col:
                for row in pts.iter_rows(named=True):
                    ax.annotate(
                        row[name_col], xy=(row[lon_col], row[lat_col]),
                        xytext=(5, 3), textcoords="offset points",
                        fontsize=6, color="#c0392b", zorder=13,
                    )

    # Set bounds and styling
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.set_aspect(1 / lat_correction)
    ax.set_title(args.title or "Iceland", fontsize=16, fontweight="bold", pad=12)
    ax.tick_params(labelsize=7, colors="#b2bec3")
    for spine in ax.spines.values():
        spine.set_edgecolor("#dfe6e9")

    # Legend
    legend_items = [
        Patch(facecolor="#d63031", label="Major roads"),
        Patch(facecolor="#dfe6e9", edgecolor="#b2bec3", label="Glaciers"),
        Patch(facecolor="#74b9ff", edgecolor="#0984e3", label="Lakes"),
        Patch(facecolor="#a8e6cf", edgecolor="#00b894", label="Nature parks"),
    ]
    if args.highlight:
        legend_items.insert(0, Patch(facecolor="#ffeaa7", edgecolor="#fdcb6e", label=args.highlight))
    ax.legend(handles=legend_items, loc="lower left", fontsize=7, framealpha=0.9,
              edgecolor="#dfe6e9", fancybox=True)

    # Attribution
    ax.text(0.99, 0.01, f"Data: Landmælingar Íslands (ERM 1:250k) · {date.today().isoformat()}",
            transform=ax.transAxes, fontsize=5.5, color="#b2bec3", ha="right", va="bottom")

    plt.tight_layout()

    # Output
    out = Path(args.output) if args.output else REPORTS_DIR / "iceland-map.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    dpi = 200 if out.suffix == ".png" else 150
    fig.savefig(out, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"Static map: {out} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Iceland map generator")
    sub = parser.add_subparsers(dest="command")

    # HTML subcommand
    html_p = sub.add_parser("html", help="Interactive Leaflet HTML map")
    html_p.add_argument("-o", "--output", help="Output file path")
    html_p.add_argument("--title", help="Map title")
    html_p.add_argument("--bounds", help="Bounding box preset or 'w,s,e,n'")

    # Static subcommand
    static_p = sub.add_parser("static", help="Static PNG/SVG map")
    static_p.add_argument("-o", "--output", help="Output file path")
    static_p.add_argument("--title", help="Map title")
    static_p.add_argument("--bounds", help="Bounding box preset or 'w,s,e,n'")
    static_p.add_argument("--highlight", help="Highlight a municipality by name")
    static_p.add_argument("--points", help="CSV file with lat/lon columns to overlay")

    args = parser.parse_args()
    if args.command == "html":
        cmd_html(args)
    elif args.command == "static":
        cmd_static(args)
    else:
        parser.print_help()
        print("\nAvailable bounds presets:", ", ".join(BOUNDS_PRESETS.keys()))
        print("Cached layers:", ", ".join(available_layers()) or "(none)")


if __name__ == "__main__":
    main()

"""Map of Iceland's agricultural land — habitat L14.2 *Tún og akurlendi*.

Polygons come from Náttúrufræðistofnun (NÍ) ``LMI_vektor:vistgerd`` (the
1:25.000 3rd-edition vector vistgerðir). Run scripts/natt.py first:

    uv run python scripts/natt.py habitat --dn 95
    uv run python scripts/agricultural_land_map.py

Output:
    reports/agricultural-land-map.png    (matplotlib, ISN93/EPSG:3057)
    reports/agricultural-land-map.html   (Leaflet, single self-contained file)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from utils.cache import CacheMissingError, iceland_constants  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

GEODATA = Path("data/geodata")
SOURCE = Path("data/raw/natt/vistgerdir/L14.2__tun_og_akurlendi.geojson")
OUT_PNG = Path("reports/agricultural-land-map.png")
OUT_HTML = Path("reports/agricultural-land-map.html")


def load_data() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if not SOURCE.exists():
        raise SystemExit(
            f"Missing {SOURCE}. Run: uv run python scripts/natt.py habitat --dn 95"
        )
    tun = gpd.read_file(SOURCE)
    if tun.crs is None:
        tun.set_crs("EPSG:3057", inplace=True)
    land = gpd.read_file(GEODATA / "Landmask.geojson")
    glaciers = gpd.read_file(GEODATA / "LandIceArea.geojson")
    lakes = gpd.read_file(GEODATA / "Lake_Reservoir.geojson")
    return tun, land, glaciers, lakes


def render_static(tun: gpd.GeoDataFrame, land: gpd.GeoDataFrame,
                  glaciers: gpd.GeoDataFrame, lakes: gpd.GeoDataFrame,
                  out: Path) -> None:
    """ISN93 (EPSG:3057) projection — undistorted Iceland."""
    tun_3057 = tun.to_crs("EPSG:3057")
    land_3057 = land.to_crs("EPSG:3057")
    glaciers_3057 = glaciers.to_crs("EPSG:3057")
    lakes_3057 = lakes.to_crs("EPSG:3057")

    total_km2 = tun_3057.geometry.area.sum() / 1e6
    n_patches = len(tun_3057)
    try:
        iceland_km2 = float(iceland_constants()["iceland_total_area_km2"])
    except CacheMissingError:
        iceland_km2 = land_3057.geometry.area.sum() / 1e6
    share = total_km2 / iceland_km2 * 100

    fig, ax = plt.subplots(figsize=(13, 9), facecolor="#f6f1e6")
    ax.set_facecolor("#dfe9f5")

    land_3057.plot(ax=ax, color="#f5efe2", edgecolor="#3a3a3a",
                   linewidth=0.55, zorder=1)
    glaciers_3057.plot(ax=ax, color="#e9eef3", edgecolor="#b8c1c8",
                       linewidth=0.2, zorder=2)
    lakes_3057.plot(ax=ax, color="#9fc7e8", edgecolor="#5687ad",
                    linewidth=0.15, zorder=3)
    tun_3057.plot(ax=ax, color="#1f7a3a", edgecolor="none", alpha=0.85,
                  zorder=4)

    minx, miny, maxx, maxy = land_3057.total_bounds
    pad = 8000
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.suptitle(
        "Tún og akurlendi á Íslandi  ·  L14.2 vistgerð",
        fontsize=17, fontweight="600", x=0.5, y=0.96, color="#1a1a1a",
    )
    ax.set_title(
        f"{total_km2:,.0f} km²  ·  {n_patches:,} reitir  ·  "
        f"{share:.2f}% af landi  ·  Heimild: Náttúrufræðistofnun (vistgerðir 1:25.000, 3. útg.)",
        fontsize=10.5, color="#444", pad=8,
    )

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {out}", file=sys.stderr)


HTML_TEMPLATE = """<!doctype html>
<html lang="is"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tún og akurlendi á Íslandi — L14.2</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
  body{{margin:0;background:#0f172a;color:#e2e8f0}}
  #header{{padding:14px 20px;background:#111827;border-bottom:1px solid #1f2937}}
  h1{{margin:0 0 4px;font-size:17px;font-weight:600}}
  #meta{{font-size:13px;color:#94a3b8}}
  #map{{position:absolute;top:72px;bottom:0;left:0;right:0}}
  .legend{{background:rgba(15,23,42,.92);color:#e2e8f0;padding:10px 12px;
           border-radius:8px;font-size:12px;line-height:1.55;max-width:300px}}
  .legend b{{color:#fff}}
  .legend .swatch{{display:inline-block;width:14px;height:10px;background:#1f7a3a;
                   border:1px solid #0e3d1d;vertical-align:middle;margin-right:6px}}
</style>
</head><body>
<div id="header">
  <h1>Tún og akurlendi á Íslandi — L14.2 vistgerð</h1>
  <div id="meta">{n_patches} reitir · {area_km2} km² · {share}% af landi · Náttúrufræðistofnun, vistgerðir 1:25.000 (3. útg.)</div>
</div>
<div id="map"></div>
<script>
const fc = {geojson};
const map = L.map('map', {{zoomSnap:0.25, preferCanvas:true}}).setView([64.9,-18.5],6.6);
L.tileLayer('https://cartodb-basemaps-{{s}}.global.ssl.fastly.net/light_all/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; OSM &copy; CARTO · Vistgerðir: Náttúrufræðistofnun',
  maxZoom: 18
}}).addTo(map);
const layer = L.geoJSON(fc, {{
  style: {{color:'#0e3d1d', weight:0.4, fillColor:'#1f7a3a', fillOpacity:0.75}}
}}).addTo(map);
map.fitBounds(layer.getBounds(), {{padding:[20,20]}});
const legend = L.control({{position:'bottomright'}});
legend.onAdd = () => {{
  const d = L.DomUtil.create('div','legend');
  d.innerHTML =
    '<b>L14.2 Tún og akurlendi</b><br>'+
    '<span class="swatch"></span> ræktað land — tún, akrar, garðlönd<br>'+
    '<small>Heimild: <a href="https://www.natt.is/is/grodur/vistgerdir/land/tun-og-akurlendi" '+
    'style="color:#9ec5fe">Náttúrufræðistofnun</a> · vistgerðir 1:25.000, 3. útg.</small>';
  return d;
}};
legend.addTo(map);
</script>
</body></html>
"""


def _round_geom(geom, ndigits: int = 5):
    """Round coordinates to ~1 m precision in lat/lon to shrink the JSON
    blob roughly 30–40% without visible loss at country scale."""
    obj = mapping(geom)

    def _r(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, ndigits) for c in coords]
        return [_r(c) for c in coords]

    obj["coordinates"] = _r(obj["coordinates"])
    return obj


def render_html(tun: gpd.GeoDataFrame, out: Path) -> None:
    tun_4326 = tun.to_crs("EPSG:4326")
    tun_3057 = tun.to_crs("EPSG:3057")

    n = len(tun_4326)
    area_km2 = tun_3057.geometry.area.sum() / 1e6

    # Iceland total area (cached scalar; ~1.5 s saved per render).
    try:
        iceland_km2 = float(iceland_constants()["iceland_total_area_km2"])
    except CacheMissingError:
        land_3057 = gpd.read_file(GEODATA / "Landmask.geojson").to_crs("EPSG:3057")
        iceland_km2 = land_3057.geometry.area.sum() / 1e6
    share = area_km2 / iceland_km2 * 100

    # Light simplification (~10 m at lat 65°) and coordinate rounding to keep
    # the page well under ~30 MB.
    simplified = tun_4326.geometry.simplify(1e-4, preserve_topology=True)
    feats = []
    for geom in simplified:
        if geom.is_empty:
            continue
        feats.append({"type": "Feature", "properties": {},
                      "geometry": _round_geom(geom, ndigits=5)})
    fc = {"type": "FeatureCollection", "features": feats}

    html = HTML_TEMPLATE.format(
        n_patches=f"{n:,}",
        area_km2=f"{area_km2:,.0f}",
        share=f"{share:.2f}",
        geojson=json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


def main() -> None:
    tun, land, glaciers, lakes = load_data()
    print(f"Loaded {len(tun):,} L14.2 polygons", file=sys.stderr)
    render_static(tun, land, glaciers, lakes, OUT_PNG)
    render_html(tun, OUT_HTML)


if __name__ == "__main__":
    main()

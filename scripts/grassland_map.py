"""High-resolution map of Iceland's grasslands.

Source: Copernicus High Resolution Layer — Grassland 2015, served by
Landmælingar Íslands at https://gis.lmi.is/geoserver/High_Resolution_Layer/wcs
(metadata UUID 58e1ed85-df4d-408d-a34f-d0a60628cb34).

Native raster: 20 m resolution, EPSG:5325 (LAEA Iceland), pixel coding
``1 = grassland`` ``0 = non-grassland`` ``254/255 = no-data``.

Run::

    uv run python scripts/lmi_hrl.py fetch grassland           # 865 MB GeoTIFF
    uv run python scripts/build_cache.py rasters               # → 9 MB ISN93 cache
    uv run python scripts/grassland_map.py                     # warm: ≈3-6 s

Output:

    reports/grassland-map.png       static, ISN93 (EPSG:3057), 5000 px wide
    reports/grassland-map.html      Leaflet, WMS tile layer for live zoom
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

# scripts/utils/cache.py provides Tier 3+4 cache readers (see
# .claude/skills/kortagerð.md "Caching strategy").
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from utils.cache import (  # noqa: E402
    CacheMissingError, cached_raster, iceland_constants,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GEODATA = ROOT / "data" / "geodata"
SOURCE_20M = ROOT / "data" / "raw" / "lmi_hrl" / "grassland_20m.tif"
SOURCE_100M = ROOT / "data" / "raw" / "lmi_hrl" / "grassland_100m.tif"
OUT_PNG = ROOT / "reports" / "grassland-map.png"
OUT_HTML = ROOT / "reports" / "grassland-map.html"

WMS_URL = "https://gis.lmi.is/geoserver/High_Resolution_Layer/wms"
WMS_LAYER = "Grassland"

# Output PNG geometry — 5000 px wide → ~120 m/pixel at country scale
PNG_WIDTH = 5000
PNG_HEIGHT = 3600
DST_CRS = "EPSG:3057"


def _load_base_layers() -> dict[str, gpd.GeoDataFrame]:
    needed = ["Landmask", "LandIceArea", "Lake_Reservoir", "CoastalLine"]
    layers: dict[str, gpd.GeoDataFrame] = {}
    for name in needed:
        path = GEODATA / f"{name}.geojson"
        if not path.exists():
            raise SystemExit(
                f"Missing base layer {path}. Run: uv run python scripts/lmi.py download")
        gdf = gpd.read_file(path)
        layers[name] = gdf.to_crs(DST_CRS)
    return layers


def _read_grassland_from_cache() -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Read the Tier-3 cached, ISN93-reprojected, LZW-compressed raster directly
    at PNG resolution. ~50-100× faster than the from-source reproject path."""
    cache_path = cached_raster("grassland_isn93")  # raises CacheMissingError if absent
    with rasterio.open(cache_path) as src:
        arr = src.read(1, out_shape=(PNG_HEIGHT, PNG_WIDTH),
                       resampling=Resampling.nearest)
        # Build the extent matching the source's footprint, scaled to our shape.
        xmin, ymin, xmax, ymax = src.bounds
    return arr, (xmin, xmax, ymin, ymax)


def _read_grassland_from_source(src_path: Path) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Fallback: reproject from source EPSG:5325 raster — slow path used only
    when the Tier-3 cache is missing."""
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, DST_CRS, src.width, src.height, *src.bounds,
            dst_width=PNG_WIDTH, dst_height=PNG_HEIGHT,
        )
        dst = np.full((PNG_HEIGHT, PNG_WIDTH), 255, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=DST_CRS,
            resampling=Resampling.nearest,
            num_threads=4,
        )
        xmin = transform.c
        ymax = transform.f
        xmax = xmin + transform.a * PNG_WIDTH
        ymin = ymax + transform.e * PNG_HEIGHT
        return dst, (xmin, xmax, ymin, ymax)


def _grassland_area_km2_from_source(src_path: Path) -> float:
    """Stream the source raster in row blocks to compute total grassland area
    without materialising the full 826 MB array — fallback for when Tier 4
    constants.json is absent."""
    total = 0
    with rasterio.open(src_path) as src:
        px_area = abs(src.transform.a * src.transform.e)  # m²
        block_h = 4096
        for off in range(0, src.height, block_h):
            h = min(block_h, src.height - off)
            window = rasterio.windows.Window(0, off, src.width, h)
            arr = src.read(1, window=window)
            total += int((arr == 1).sum())
    return total * px_area / 1e6


def _resolve_inputs() -> tuple[np.ndarray, tuple[float, float, float, float], float, float]:
    """Use Tier 3 raster + Tier 4 constants when present; otherwise fall back to
    the source raster + Landmask polygon. Returns ``(arr, extent, grassland_km2,
    iceland_km2)``."""
    # Tier 3 raster — fast path
    try:
        arr, extent = _read_grassland_from_cache()
        cache_used_raster = True
    except CacheMissingError:
        src = SOURCE_20M if SOURCE_20M.exists() else SOURCE_100M
        if not src.exists():
            raise SystemExit(
                "No grassland raster found. Run:\n"
                "    uv run python scripts/lmi_hrl.py fetch grassland\n"
                "    uv run python scripts/build_cache.py rasters")
        print(f"  cache miss — reprojecting from {src.name}", file=sys.stderr)
        arr, extent = _read_grassland_from_source(src)
        cache_used_raster = False

    # Tier 4 scalars — sub-millisecond JSON read
    try:
        K = iceland_constants()
        iceland_km2 = float(K["iceland_total_area_km2"])
        grassland_km2 = float(K["hrl_sources"]["grassland_isn93"]["area_km2"])
        cache_used_scalars = True
    except (CacheMissingError, KeyError):
        print("  cache miss — recomputing scalars from source", file=sys.stderr)
        cache_used_scalars = False
        if SOURCE_20M.exists():
            grassland_km2 = _grassland_area_km2_from_source(SOURCE_20M)
        else:
            # Approximate from the (lossy) reprojected array as last resort
            xmin, xmax, ymin, ymax = extent
            px_area = ((xmax - xmin) * (ymax - ymin)) / arr.size
            grassland_km2 = float((arr == 1).sum()) * px_area / 1e6
        # Iceland total area still falls through to the polygon-based path below
        iceland_km2 = 0.0

    if not cache_used_raster:
        print("  hint: run scripts/build_cache.py rasters to skip reproject",
              file=sys.stderr)
    if not cache_used_scalars:
        print("  hint: run scripts/build_cache.py constants for sub-ms scalar reads",
              file=sys.stderr)

    return arr, extent, grassland_km2, iceland_km2


def render_static(out: Path) -> None:
    arr, (xmin, xmax, ymin, ymax), grassland_km2, iceland_km2 = _resolve_inputs()

    print("Loading base layers ...", file=sys.stderr)
    base = _load_base_layers()
    if iceland_km2 == 0.0:
        iceland_km2 = base["Landmask"].geometry.area.sum() / 1e6
    share_pct = grassland_km2 / iceland_km2 * 100

    print("Rendering ...", file=sys.stderr)
    fig = plt.figure(figsize=(17, 12.5), facecolor="#f5efe2")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    ax.set_facecolor("#cfdfe9")  # pale ocean

    base["Landmask"].plot(
        ax=ax, color="#f5efe2", edgecolor="#3a3a3a", linewidth=0.55, zorder=1)
    base["LandIceArea"].plot(
        ax=ax, color="#eef2f6", edgecolor="#b8c1c8", linewidth=0.25, zorder=2)
    base["Lake_Reservoir"].plot(
        ax=ax, color="#9fc7e8", edgecolor="#5687ad", linewidth=0.15, zorder=3)

    # Build an RGBA layer: only pixel==1 (grassland) is opaque green; everything
    # else is fully transparent so the base map shines through.
    rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
    g = arr == 1
    rgba[g] = (31, 122, 58, 235)   # forest green
    ax.imshow(rgba, extent=(xmin, xmax, ymin, ymax),
              origin="upper", interpolation="nearest", zorder=4)

    bx0, by0, bx1, by1 = base["Landmask"].total_bounds
    pad = 8000
    ax.set_xlim(bx0 - pad, bx1 + pad)
    ax.set_ylim(by0 - pad, by1 + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.text(0.5, 0.945, "Graslendi á Íslandi",
             fontsize=28, fontweight="700", ha="center", color="#1a1a1a")
    fig.text(0.5, 0.910, "Copernicus HRL Grassland 2015 — 20 m upplausn",
             fontsize=14, ha="center", color="#444")
    fig.text(0.5, 0.885,
             f"{grassland_km2:,.0f} km²  ·  {share_pct:.2f}% af landi  ·  "
             "Heimild: Landmælingar Íslands / Copernicus Land Monitoring Service",
             fontsize=11, ha="center", color="#666")

    from matplotlib.patches import Patch
    legend = [
        Patch(facecolor="#1f7a3a", edgecolor="#0e3d1d",
              label=f"Graslendi  ({grassland_km2:,.0f} km²)"),
        Patch(facecolor="#eef2f6", edgecolor="#b8c1c8", label="Jöklar"),
        Patch(facecolor="#9fc7e8", edgecolor="#5687ad", label="Vötn"),
        Patch(facecolor="#f5efe2", edgecolor="#3a3a3a", label="Annað þurrlendi"),
    ]
    ax.legend(handles=legend, loc="lower left", frameon=True, framealpha=0.95,
              edgecolor="#bdbdbd", fontsize=11)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=320, facecolor=fig.get_facecolor())
    plt.close(fig)
    size_mb = out.stat().st_size / 1e6
    print(f"Wrote {out}  ({size_mb:.1f} MB)", file=sys.stderr)


HTML_TEMPLATE = """<!doctype html>
<html lang="is"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graslendi á Íslandi — Copernicus HRL 2015</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  body{margin:0;background:#0f172a;color:#e2e8f0}
  #header{padding:14px 20px;background:#111827;border-bottom:1px solid #1f2937}
  h1{margin:0 0 4px;font-size:17px;font-weight:600}
  #meta{font-size:13px;color:#94a3b8}
  #meta a{color:#9ec5fe;text-decoration:none}
  #map{position:absolute;top:72px;bottom:0;left:0;right:0}
  .legend{background:rgba(15,23,42,.92);color:#e2e8f0;padding:10px 12px;
          border-radius:8px;font-size:12px;line-height:1.55;max-width:340px}
  .legend b{color:#fff}
  .legend .swatch{display:inline-block;width:14px;height:10px;background:#1f7a3a;
                  border:1px solid #0e3d1d;vertical-align:middle;margin-right:6px}
</style>
</head><body>
<div id="header">
  <h1>Graslendi á Íslandi — Copernicus HRL Grassland 2015</h1>
  <div id="meta">__AREA__ km² (__SHARE__% af landi) · 20 m upplausn ·
    Heimild: <a href="https://gatt.lmi.is/geonetwork/srv/eng/catalog.search#/metadata/58e1ed85-df4d-408d-a34f-d0a60628cb34">Landmælingar Íslands</a> / Copernicus Land Monitoring Service</div>
</div>
<div id="map"></div>
<script>
const map = L.map('map', {zoomSnap:0.25, preferCanvas:true}).setView([64.9,-18.5],6.6);
const base = L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png', {
  attribution:'&copy; OSM &copy; CARTO',
  maxZoom: 18
}).addTo(map);
const grassland = L.tileLayer.wms('__WMS_URL__', {
  layers: '__WMS_LAYER__',
  format: 'image/png',
  transparent: true,
  version: '1.3.0',
  opacity: 0.85,
  attribution:'Grassland: Copernicus HRL via Landmælingar Íslands'
}).addTo(map);
const overlays = {'Graslendi (Copernicus HRL)': grassland};
L.control.layers(null, overlays, {collapsed:false, position:'topright'}).addTo(map);
const legend = L.control({position:'bottomright'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div','legend');
  d.innerHTML =
    '<b>Graslendi 2015</b><br>'+
    '<span class="swatch"></span> Copernicus HRL grassland mask, 20 m<br>'+
    '<small>Sýnir „managed, semi-natural &amp; natural grassy vegetation"<br>'+
    'samkvæmt Pan-European HRL flokkun (EEA39 mörkin).<br>'+
    'Yfirlag yfir CARTO Light grunnmynd.</small>';
  return d;
};
legend.addTo(map);
L.control.scale({imperial:false, position:'bottomleft'}).addTo(map);
</script>
</body></html>
"""


def render_html(out: Path, area_km2: float, share_pct: float) -> None:
    html = (HTML_TEMPLATE
            .replace("__AREA__", f"{area_km2:,.0f}")
            .replace("__SHARE__", f"{share_pct:.2f}")
            .replace("__WMS_URL__", WMS_URL)
            .replace("__WMS_LAYER__", WMS_LAYER))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size / 1024:.1f} KB)", file=sys.stderr)


def main() -> None:
    render_static(OUT_PNG)

    # HTML metadata bar reuses the same scalar lookups (cache-aware).
    try:
        K = iceland_constants()
        grassland_km2 = float(K["hrl_sources"]["grassland_isn93"]["area_km2"])
        iceland_km2 = float(K["iceland_total_area_km2"])
    except (CacheMissingError, KeyError):
        # Fallback already exercised inside render_static; recompute lightly here.
        base = _load_base_layers()
        iceland_km2 = base["Landmask"].geometry.area.sum() / 1e6
        grassland_km2 = (_grassland_area_km2_from_source(SOURCE_20M)
                         if SOURCE_20M.exists() else 0.0)
    share_pct = (grassland_km2 / iceland_km2 * 100) if iceland_km2 else 0.0
    render_html(OUT_HTML, grassland_km2, share_pct)


if __name__ == "__main__":
    main()

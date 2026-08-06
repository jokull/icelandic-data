"""Map of Iceland's agricultural land — habitat L14.2 *Tún og akurlendi*.

Source: Náttúrufræðistofnun's 1:25.000 3rd-edition habitat raster
``vistgerdir:ni_vg25r_3utg_lzw`` (EPSG:3057, 5 m, band 1 = habitat code).
``scripts/natt.py`` fetches band 1 over WCS and writes an ISN93 ``==95`` mask;
this script renders it. The polygon layer this map used until 2026-08 was
withdrawn upstream — see ``.agents/skills/natt/SKILL.md``.

Run::

    uv run python scripts/natt.py habitat --dn 95        # 50 m mask, ~2 min, once
    uv run python scripts/agricultural_land_map.py

If several masks are on disk this takes the finest — the PNG draws at 120 m/px
and the Leaflet overlay at 200 m/px, so anything at or below 100 m is plenty.

Output:
    reports/agricultural-land-map.png    (matplotlib, ISN93/EPSG:3057)
    reports/agricultural-land-map.html   (Leaflet, single self-contained file)
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from utils.cache import CacheMissingError, iceland_constants  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GEODATA = ROOT / "data" / "geodata"
NATT_RAW = ROOT / "data" / "raw" / "natt" / "vistgerdir"
SOURCE_GLOB = "vistgerd_dn95_*m.tif"
OUT_PNG = ROOT / "reports" / "agricultural-land-map.png"
OUT_HTML = ROOT / "reports" / "agricultural-land-map.html"

DST_CRS = "EPSG:3057"
TARGET_PX_M = 120.0     # PNG ground resolution — same scale as grassland_map.py
HTML_PX_M = 200.0       # Leaflet overlay: coarser, keeps the data-URI small
FETCH_HINT = "Run: uv run python scripts/natt.py habitat --dn 95"


# ── source discovery ─────────────────────────────────────────────────────

def find_source() -> Path:
    """Finest-resolution L14.2 mask on disk (``vistgerd_dn95_<res>m.tif``)."""
    candidates = sorted(NATT_RAW.glob(SOURCE_GLOB))
    if not candidates:
        raise SystemExit(
            f"Missing {NATT_RAW.relative_to(ROOT)}/{SOURCE_GLOB}. {FETCH_HINT}")

    def res_of(p: Path) -> float:
        m = re.search(r"_(\d+(?:\.\d+)?)m\.tif$", p.name)
        return float(m.group(1)) if m else float("inf")

    return min(candidates, key=res_of)


def source_area_km2(src_path: Path, mask: np.ndarray | None = None,
                    px_m: float | None = None) -> float:
    """Area from natt.py's sidecar (exact, full resolution) when available."""
    side = src_path.with_suffix(".json")
    if side.exists():
        meta = json.loads(side.read_text(encoding="utf-8"))
        if meta.get("area_km2"):
            return float(meta["area_km2"])
    if mask is None or px_m is None:
        with rasterio.open(src_path) as s:
            px_area = abs(s.transform.a * s.transform.e)
            total = 0
            for _, window in s.block_windows(1):
                total += int((s.read(1, window=window) > 0).sum())
        return total * px_area / 1e6
    return float((mask > 0).sum()) * px_m ** 2 / 1e6


# ── raster reading ───────────────────────────────────────────────────────

def read_mask(src_path: Path, target_px_m: float
              ) -> tuple[np.ndarray, tuple[float, float, float, float], float]:
    """Downsample the binary mask by an integer factor using a **max** reduce.

    Nearest-neighbour would drop most fields: at 120 m/px a single 20 m tún
    pixel survives only if it happens to sit under the sample point. Max keeps
    every cell that contains any cultivated land, which is the honest reading of
    a sparse presence mask at country scale.

    Returns ``(mask, (xmin, xmax, ymin, ymax), pixel_metres)``.
    """
    with rasterio.open(src_path) as src:
        res = abs(src.transform.a)
        factor = max(1, int(round(target_px_m / res)))
        h, w = src.height, src.width
        pad_y = (-h) % factor
        pad_x = (-w) % factor
        out_h = (h + pad_y) // factor
        out_w = (w + pad_x) // factor
        out = np.zeros((out_h, out_w), dtype=np.uint8)

        # Stream in row bands so the 468 MB 20 m mask never lands in RAM whole.
        band_rows = factor * 256
        for top in range(0, h, band_rows):
            rows = min(band_rows, h - top)
            chunk = src.read(1, window=rasterio.windows.Window(0, top, w, rows))
            cy = (-chunk.shape[0]) % factor
            if cy or pad_x:
                chunk = np.pad(chunk, ((0, cy), (0, pad_x)))
            red = chunk.reshape(chunk.shape[0] // factor, factor,
                                out_w, factor).max(axis=(1, 3))
            r0 = top // factor
            out[r0:r0 + red.shape[0]] = np.maximum(out[r0:r0 + red.shape[0]], red)

        xmin = src.transform.c
        ymax = src.transform.f
        xmax = xmin + (w + pad_x) * res
        ymin = ymax - (h + pad_y) * res
    return out, (xmin, xmax, ymin, ymax), factor * res


def load_base_layers() -> dict[str, gpd.GeoDataFrame]:
    layers = {}
    for name in ("Landmask", "LandIceArea", "Lake_Reservoir"):
        path = GEODATA / f"{name}.geojson"
        if not path.exists():
            raise SystemExit(f"Missing base layer {path}. "
                             "Run: uv run python scripts/lmi.py download")
        layers[name] = gpd.read_file(path).to_crs(DST_CRS)
    return layers


# ── static PNG ───────────────────────────────────────────────────────────

def render_static(mask: np.ndarray, extent: tuple[float, float, float, float],
                  base: dict[str, gpd.GeoDataFrame],
                  total_km2: float, iceland_km2: float, out: Path) -> None:
    """ISN93 (EPSG:3057) projection — undistorted Iceland."""
    xmin, xmax, ymin, ymax = extent
    share = total_km2 / iceland_km2 * 100

    fig, ax = plt.subplots(figsize=(13, 9), facecolor="#f6f1e6")
    ax.set_facecolor("#dfe9f5")

    base["Landmask"].plot(ax=ax, color="#f5efe2", edgecolor="#3a3a3a",
                          linewidth=0.55, zorder=1)
    base["LandIceArea"].plot(ax=ax, color="#e9eef3", edgecolor="#b8c1c8",
                             linewidth=0.2, zorder=2)
    base["Lake_Reservoir"].plot(ax=ax, color="#9fc7e8", edgecolor="#5687ad",
                                linewidth=0.15, zorder=3)

    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[mask > 0] = (31, 122, 58, 217)
    ax.imshow(rgba, extent=(xmin, xmax, ymin, ymax), origin="upper",
              interpolation="nearest", zorder=4)

    bx0, by0, bx1, by1 = base["Landmask"].total_bounds
    pad = 8000
    ax.set_xlim(bx0 - pad, bx1 + pad)
    ax.set_ylim(by0 - pad, by1 + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.suptitle("Tún og akurlendi á Íslandi  ·  L14.2 vistgerð",
                 fontsize=17, fontweight="600", x=0.5, y=0.96, color="#1a1a1a")
    ax.set_title(
        f"{total_km2:,.0f} km²  ·  {share:.2f}% af landi  ·  "
        f"Heimild: Náttúrufræðistofnun (vistgerðakort 1:25.000, 3. útg., 5 m rasti)",
        fontsize=10.5, color="#444", pad=8,
    )

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {out}", file=sys.stderr)


# ── Leaflet HTML ─────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!doctype html>
<html lang="is"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tún og akurlendi á Íslandi — L14.2</title>
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
          border-radius:8px;font-size:12px;line-height:1.55;max-width:320px}
  .legend b{color:#fff}
  .legend .swatch{display:inline-block;width:14px;height:10px;background:#1f7a3a;
                  border:1px solid #0e3d1d;vertical-align:middle;margin-right:6px}
</style>
</head><body>
<div id="header">
  <h1>Tún og akurlendi á Íslandi — L14.2 vistgerð</h1>
  <div id="meta">__AREA__ km² · __SHARE__% af landi · __PXM__ m myndeining ·
    Heimild: <a href="https://www.natt.is/is/grodur/vistgerdir/land/tun-og-akurlendi">Náttúrufræðistofnun</a>, vistgerðakort 1:25.000 (3. útg.)</div>
</div>
<div id="map"></div>
<script>
const map = L.map('map', {zoomSnap:0.25, preferCanvas:true}).setView([64.9,-18.5],6.6);
L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png', {
  attribution:'&copy; OSM &copy; CARTO · Vistgerðir: Náttúrufræðistofnun',
  maxZoom: 18
}).addTo(map);
// The overlay is a Web-Mercator (EPSG:3857) render of the L14.2 mask, so
// Leaflet's linear corner-to-corner placement is geometrically exact.
const bounds = [[__S__, __W__], [__N__, __E__]];
const tun = L.imageOverlay('__IMG__', bounds, {opacity:0.9,
  attribution:'L14.2 Tún og akurlendi — Náttúrufræðistofnun'}).addTo(map);
L.control.layers(null, {'Tún og akurlendi (L14.2)': tun},
                 {collapsed:false, position:'topright'}).addTo(map);
map.fitBounds(bounds, {padding:[20,20]});
const legend = L.control({position:'bottomright'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div','legend');
  d.innerHTML =
    '<b>L14.2 Tún og akurlendi</b><br>'+
    '<span class="swatch"></span> ræktað land — tún, akrar, garðlönd<br>'+
    '<small>Úr 5 m vistgerðarasta NÍ (band 1 = vistgerðarkóði, DN 95),'+
    ' endursýnt í __PXM__ m.</small>';
  return d;
};
legend.addTo(map);
L.control.scale({imperial:false, position:'bottomleft'}).addTo(map);
</script>
</body></html>
"""


def _mask_to_webmercator_png(mask: np.ndarray,
                             extent: tuple[float, float, float, float],
                             px_m: float) -> tuple[str, tuple[float, float, float, float]]:
    """Reproject the ISN93 mask to EPSG:3857 and encode it as an RGBA data URI.

    Returns ``(data_uri, (west, south, east, north))`` in lon/lat.
    """
    from PIL import Image
    from pyproj import Transformer

    xmin, xmax, ymin, ymax = extent
    src_transform = rasterio.Affine(px_m, 0, xmin, 0, -px_m, ymax)
    dst_transform, w, h = calculate_default_transform(
        DST_CRS, "EPSG:3857", mask.shape[1], mask.shape[0],
        xmin, ymin, xmax, ymax)
    dst = np.zeros((h, w), dtype=np.uint8)
    reproject(
        source=mask, destination=dst,
        src_transform=src_transform, src_crs=DST_CRS,
        dst_transform=dst_transform, dst_crs="EPSG:3857",
        resampling=Resampling.nearest,
    )

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[dst > 0] = (31, 122, 58, 235)
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    mx0 = dst_transform.c
    my1 = dst_transform.f
    mx1 = mx0 + dst_transform.a * w
    my0 = my1 + dst_transform.e * h
    t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, south = t.transform(mx0, my0)
    east, north = t.transform(mx1, my1)
    return uri, (west, south, east, north)


def render_html(src_path: Path, total_km2: float, iceland_km2: float,
                out: Path) -> None:
    mask, extent, px_m = read_mask(src_path, HTML_PX_M)
    uri, (west, south, east, north) = _mask_to_webmercator_png(mask, extent, px_m)
    html = (HTML_TEMPLATE
            .replace("__AREA__", f"{total_km2:,.0f}")
            .replace("__SHARE__", f"{total_km2 / iceland_km2 * 100:.2f}")
            .replace("__PXM__", f"{px_m:g}")
            .replace("__IMG__", uri)
            .replace("__W__", f"{west:.6f}").replace("__E__", f"{east:.6f}")
            .replace("__S__", f"{south:.6f}").replace("__N__", f"{north:.6f}"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


def main() -> None:
    src = find_source()
    print(f"Source: {src.relative_to(ROOT)}", file=sys.stderr)

    mask, extent, _px_m = read_mask(src, TARGET_PX_M)
    total_km2 = source_area_km2(src)
    base = load_base_layers()
    try:
        iceland_km2 = float(iceland_constants()["iceland_total_area_km2"])
    except CacheMissingError:
        iceland_km2 = base["Landmask"].geometry.area.sum() / 1e6
    print(f"  L14.2: {total_km2:,.1f} km²  "
          f"({total_km2 / iceland_km2 * 100:.2f}% af landi)", file=sys.stderr)

    render_static(mask, extent, base, total_km2, iceland_km2, OUT_PNG)
    render_html(src, total_km2, iceland_km2, OUT_HTML)


if __name__ == "__main__":
    main()

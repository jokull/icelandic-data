"""Heatmap of Iceland's Grassland Vegetation Probability Index (GRAVPI 2015).

The GRAVPI is the Copernicus HRL companion product to the Grassland binary
mask: it expresses the *reliability* (1-100 %) of the multi-seasonal optical
grassland classification at each 20 m pixel.

Landmælingar Íslands does not republish the GRAVPI for Iceland, so this
script pulls the rendered raster from the European Environment Agency's
public ArcGIS WMS:

    https://image.discomap.eea.europa.eu/arcgis/services/GioLandPublic/
        HRL_GrasslandProbabilityIndex_2015/MapServer/WMSServer

The EEA WMS only returns *styled* RGB images (10 discrete probability bins
+ "no grassland" + "outside area"). We therefore (a) fetch a high-res
rendering, (b) match each pixel to the legend's canonical colours to
recover the probability bin, (c) reproject to EPSG:3057 (ISN93) for an
area-correct heatmap, and (d) render with a custom blue→dark-green
colour ramp.

Run::

    uv run python scripts/grassland_probability_heatmap.py

Output: ``reports/grassland-probability-heatmap.png``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import httpx
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from utils.cache import (  # noqa: E402
    CacheMissingError, cached_array, iceland_constants,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GEODATA = ROOT / "data" / "geodata"
RAW = ROOT / "data" / "raw" / "lmi_hrl"
OUT_PNG = ROOT / "reports" / "grassland-probability-heatmap.png"

WMS = ("https://image.discomap.eea.europa.eu/arcgis/services/GioLandPublic/"
       "HRL_GrasslandProbabilityIndex_2015/MapServer/WMSServer")

# Iceland bounding box in EPSG:3857 (Web Mercator) — slightly padded.
BBOX_3857 = (-2_780_000, 9_080_000, -1_440_000, 10_100_000)
# EEA discomap rejects WMS GetMap requests above ~10 M output pixels. Pick the
# largest aspect-correct frame under that cap.
WMS_W, WMS_H = 3500, 2666

DST_CRS = "EPSG:3057"
DST_W, DST_H = 5000, 3600

# Canonical EEA legend colours (sampled from GetLegendGraphic). Bin centres
# are the midpoints of the documented 10 % probability ranges.
LEGEND = [
    # (bin_center, R, G, B, range_label)
    (5.5,  232, 252, 114, "1–10 %"),
    (15.5, 175, 245,  83, "11–20 %"),
    (25.5, 114, 235,  49, "21–30 %"),
    (35.5,  55, 222,  18, "31–40 %"),
    (45.5,  62, 199,  78, "41–50 %"),
    (55.5,  55, 173, 122, "51–60 %"),
    (65.5,  34, 150, 163, "61–70 %"),
    (75.5,  33, 110, 158, "71–80 %"),
    (85.5,  31,  70, 143, "81–90 %"),
    (95.5,  22,  34, 128, "91–100 %"),
]
LEGEND_RGB = np.array([(r, g, b) for _, r, g, b, _ in LEGEND], dtype=np.int32)
LEGEND_PROB = np.array([p for p, *_ in LEGEND], dtype=np.float32)
NON_GRASSLAND_RGB = (255, 255, 255)   # "All non-grassland areas"
OUTSIDE_RGB = (153, 153, 153)         # "Unclassifiable / Outside area"
# Anti-aliased pixels near class boundaries may not exactly match a swatch.
# Reject pixels whose nearest legend swatch is more than this RGB distance
# (squared) — about 30 RGB units in the worst channel.
MAX_SWATCH_DIST_SQ = 2700


def fetch_gravpi(out: Path) -> Path:
    """Download the EEA-rendered RGB raster covering Iceland."""
    if out.exists():
        print(f"Re-using {out}", file=sys.stderr)
        return out
    params = {
        "service": "WMS", "version": "1.3.0", "request": "GetMap",
        "layers": "0", "styles": "", "format": "image/tiff",
        "transparent": "false",
        "width": str(WMS_W), "height": str(WMS_H),
        "crs": "EPSG:3857",
        "bbox": ",".join(str(c) for c in BBOX_3857),
    }
    print(f"Fetching GRAVPI rendering ({WMS_W}×{WMS_H}) from EEA discomap ...",
          file=sys.stderr)
    r = httpx.get(WMS, params=params, timeout=180.0, follow_redirects=True)
    r.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"  wrote {out}  ({len(r.content) / 1e6:.1f} MB)", file=sys.stderr)
    return out


def decode_rgb_to_probability(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map each RGB pixel to its closest legend swatch.

    Returns
    -------
    prob : float32 array, NaN for non-grassland or outside-area
    bin  : int8 array, 1-10 for grassland bins, 0 = non-grassland, -1 = outside
    """
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.int32)   # int32 to avoid overflow

    diffs = flat[:, None, :] - LEGEND_RGB[None, :, :]
    d2 = (diffs * diffs).sum(axis=2)
    nearest = d2.argmin(axis=1)
    nearest_d2 = d2.min(axis=1)

    prob = LEGEND_PROB[nearest].astype(np.float32)
    bin_idx = (nearest + 1).astype(np.int8)

    # Reject any pixel whose nearest swatch is too far away (i.e. white,
    # grey, ocean, or anti-aliased boundary pixels).
    too_far = nearest_d2 > MAX_SWATCH_DIST_SQ
    prob[too_far] = np.nan
    bin_idx[too_far] = 0

    return prob.reshape(h, w), bin_idx.reshape(h, w)


def reproject_to_iceland(arr: np.ndarray, *, nodata: float) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Reproject a 2-D array from EPSG:3857 (BBOX_3857) to ISN93 (EPSG:3057)
    on a DST_W × DST_H grid sized to Iceland's bounds."""
    src_transform = from_bounds(*BBOX_3857, WMS_W, WMS_H)

    # Compute the EPSG:3057 footprint by reprojecting the corners
    dst_transform, dw, dh = calculate_default_transform(
        "EPSG:3857", DST_CRS, WMS_W, WMS_H, *BBOX_3857,
        dst_width=DST_W, dst_height=DST_H,
    )
    dst = np.full((DST_H, DST_W), nodata, dtype=arr.dtype)
    reproject(
        source=arr, destination=dst,
        src_transform=src_transform, src_crs="EPSG:3857",
        src_nodata=nodata,
        dst_transform=dst_transform, dst_crs=DST_CRS,
        dst_nodata=nodata,
        resampling=Resampling.nearest,
    )
    xmin = dst_transform.c
    ymax = dst_transform.f
    xmax = xmin + dst_transform.a * DST_W
    ymin = ymax + dst_transform.e * DST_H
    return dst, (xmin, xmax, ymin, ymax)


def _load_base_layers() -> dict[str, gpd.GeoDataFrame]:
    layers = {}
    for name in ("Landmask", "LandIceArea", "Lake_Reservoir"):
        path = GEODATA / f"{name}.geojson"
        if not path.exists():
            raise SystemExit(f"Missing {path} — run scripts/lmi.py download")
        layers[name] = gpd.read_file(path).to_crs(DST_CRS)
    return layers


def _decode_and_reproject(raster_path: Path) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Run the (slow) RGB-decode + reproject pipeline and return prob_3057
    plus the EPSG:3057 extent."""
    with rasterio.open(raster_path) as src:
        rgb = src.read([1, 2, 3])
    rgb = np.transpose(rgb, (1, 2, 0))
    prob_3857, _bin = decode_rgb_to_probability(rgb)
    prob_with_sentinel = np.where(np.isnan(prob_3857), -1.0, prob_3857)
    prob_3057, extent = reproject_to_iceland(
        prob_with_sentinel.astype(np.float32), nodata=-1.0)
    prob_3057 = np.where(prob_3057 < 0, np.nan, prob_3057)
    return prob_3057, extent


def _load_or_compute_prob_3057(raster_path: Path) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Tier 5 cache: write the decoded+reprojected probability grid to .npy
    on first run; reuse on subsequent runs when the source TIFF is unchanged."""
    npy = cached_array("gravpi_prob_3057")
    sidecar = npy.with_suffix(".json")
    src_mtime = raster_path.stat().st_mtime
    if npy.exists() and sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            if meta.get("source_mtime") == src_mtime:
                print(f"  Tier-5 cache hit — reading {npy.name}", file=sys.stderr)
                arr = np.load(npy)
                ex = tuple(meta["extent"])
                return arr, ex                                # type: ignore[return-value]
        except (OSError, ValueError, KeyError):
            pass
    print("Decoding RGB → probability bins + reprojecting ...", file=sys.stderr)
    arr, extent = _decode_and_reproject(raster_path)
    np.save(npy, arr)
    sidecar.write_text(json.dumps(
        {"source": str(raster_path).replace("\\", "/"),
         "source_mtime": src_mtime,
         "extent": list(extent),
         "shape": list(arr.shape)}, indent=2),
        encoding="utf-8")
    print(f"  wrote Tier-5 cache → {npy.name} ({npy.stat().st_size / 1e6:.1f} MB)",
          file=sys.stderr)
    return arr, extent


def main() -> None:
    raster_path = RAW / "gravpi_full.tif"
    fetch_gravpi(raster_path)

    prob_3057, (xmin, xmax, ymin, ymax) = _load_or_compute_prob_3057(raster_path)

    pixel_w = (xmax - xmin) / DST_W
    pixel_h = (ymax - ymin) / DST_H
    pixel_area_m2 = pixel_w * pixel_h
    print(f"  pixel size: {pixel_w:.1f} m × {pixel_h:.1f} m  "
          f"({pixel_area_m2 / 1e4:.2f} ha)", file=sys.stderr)

    # ── statistics ────────────────────────────────────────────────────────
    valid = ~np.isnan(prob_3057)
    n_valid = int(valid.sum())
    n_over_50 = int(((prob_3057 > 50.0) & valid).sum())
    n_any = int((valid).sum())
    area_over_50_km2 = n_over_50 * pixel_area_m2 / 1e6
    area_any_km2 = n_any * pixel_area_m2 / 1e6

    base = _load_base_layers()
    try:
        iceland_km2 = float(iceland_constants()["iceland_total_area_km2"])
    except CacheMissingError:
        iceland_km2 = base["Landmask"].geometry.area.sum() / 1e6
    share_over_50 = area_over_50_km2 / iceland_km2 * 100

    print(f"\n  Pixels with grassland-probability bin assigned : {n_any:>10,}",
          file=sys.stderr)
    print(f"  Pixels with probability > 50 %                : {n_over_50:>10,}",
          file=sys.stderr)
    print(f"  Area, any probability bin                     : "
          f"{area_any_km2:>10,.0f} km²", file=sys.stderr)
    print(f"  Area with probability > 50 %                  : "
          f"{area_over_50_km2:>10,.0f} km²"
          f"   ({share_over_50:.2f} % of Iceland)", file=sys.stderr)

    # ── render heatmap ───────────────────────────────────────────────────
    print("\nRendering heatmap ...", file=sys.stderr)

    # Custom colour ramp: blue (low probability) → dark green (high probability).
    # 10 discrete steps so we mirror the EEA bin structure.
    blue_to_green = ListedColormap([
        "#1e3a8a",  # ~5 %  : indigo / royal blue
        "#1d4ed8",  # ~15 % : strong blue
        "#1d77c5",  # ~25 % : sky blue
        "#1aa3a3",  # ~35 % : teal
        "#179c7a",  # ~45 % : sea green
        "#15894e",  # ~55 % : medium green
        "#13742f",  # ~65 % : forest green
        "#0e5d20",  # ~75 % : darker green
        "#0a4818",  # ~85 % : darker still
        "#06310f",  # ~95 % : near-black green
    ])

    fig = plt.figure(figsize=(17, 12.5), facecolor="#f5efe2")
    ax = fig.add_axes([0.02, 0.04, 0.96, 0.84])
    ax.set_facecolor("#cfdfe9")  # pale ocean

    base["Landmask"].plot(ax=ax, color="#f5efe2", edgecolor="#3a3a3a",
                          linewidth=0.55, zorder=1)
    base["LandIceArea"].plot(ax=ax, color="#eef2f6", edgecolor="#b8c1c8",
                             linewidth=0.25, zorder=2)
    base["Lake_Reservoir"].plot(ax=ax, color="#9fc7e8", edgecolor="#5687ad",
                                linewidth=0.15, zorder=3)

    # Quantize probability into 10 bins so the colour mapping is discrete and
    # legible (matches EEA's documented bin structure). NaN cells are masked
    # before casting to avoid the np.floor(NaN)→int conversion warning.
    masked = np.ma.masked_invalid(prob_3057)
    bin_idx = np.clip(np.floor(masked.filled(0.0) / 10.0), 0, 9).astype(np.int8)
    binned = np.ma.masked_array(bin_idx, mask=masked.mask)

    im = ax.imshow(binned, extent=(xmin, xmax, ymin, ymax),
                   origin="upper", cmap=blue_to_green,
                   vmin=-0.5, vmax=9.5,
                   interpolation="nearest", zorder=4)

    bx0, by0, bx1, by1 = base["Landmask"].total_bounds
    pad = 8000
    ax.set_xlim(bx0 - pad, bx1 + pad)
    ax.set_ylim(by0 - pad, by1 + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.text(0.5, 0.945, "Líkindi á graslendi á Íslandi",
             fontsize=28, fontweight="700", ha="center", color="#1a1a1a")
    fig.text(0.5, 0.910, "Copernicus HRL Grassland Vegetation Probability Index 2015 — 20 m",
             fontsize=14, ha="center", color="#444")
    fig.text(0.5, 0.885,
             f"{area_over_50_km2:,.0f} km² með >50 % líkur  ·  "
             f"{share_over_50:.2f} % af landi  ·  "
             "Heimild: EEA Copernicus Land Monitoring Service",
             fontsize=11, ha="center", color="#666")

    # Discrete colourbar legend
    cax = fig.add_axes([0.06, 0.10, 0.34, 0.028])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal",
                        ticks=range(10))
    cbar.set_ticklabels([f"{i*10+1}" for i in range(10)])
    cbar.ax.tick_params(labelsize=10, colors="#333")
    cbar.outline.set_edgecolor("#bdbdbd")
    cbar.set_label("Líkindi á graslendi (%) — neðri mörk hvers flokks",
                   fontsize=11, color="#333")

    # Headline figure: area with probability > 50 %
    fig.text(0.06, 0.055,
             f">50 % líkur  →  {area_over_50_km2:,.0f} km²   "
             f"({share_over_50:.2f} % af Íslandi)",
             fontsize=14, fontweight="700", color="#0e5d20")

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=320, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"\nWrote {OUT_PNG}  ({OUT_PNG.stat().st_size / 1e6:.1f} MB)",
          file=sys.stderr)


if __name__ == "__main__":
    main()

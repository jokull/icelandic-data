"""Náttúrufræðistofnun open-data fetcher — habitat types ("vistgerðir").

**Raster-native since 2026-08.** NÍ withdrew the polygonised vector layer
``LMI_vektor:vistgerd`` (see the natt skill's caveats). The surviving publication
of the same 3rd-edition 1:25.000 habitat map is the raster, served from the same
GeoServer:

- WCS coverage ``vistgerdir__ni_vg25r_3utg_lzw`` — EPSG:3057 (ISN93), 5 m grid,
  102928 × 72798 px. **Band 1 is the habitat code**; band 2 is alpha.
- WMS layer ``vistgerdir:ni_vg25r_3utg_lzw`` — same coverage, styled.

The pixel codes are unchanged from the old vector layer's ``DN`` column, so
``--dn 95`` still means *L14.2 Tún og akurlendi* (cultivated hay + arable land,
≈1,800 km²). The ``DN`` → label inventory is no longer streamed out of 24M WFS
rows — it is one WMS ``GetLegendGraphic`` request returning the raster colormap.

CLI::

    # habitat mask as an ISN93 GeoTIFF (1 = habitat, 0 = everything else)
    uv run python scripts/natt.py habitat --dn 95                # 50 m default, ~2 min
    uv run python scripts/natt.py habitat --code L14.2 --res 100 # ~1 min, map-grade
    uv run python scripts/natt.py habitat --dn 95 --res 20       # ~30 min, detail work

The fetch is server-bound, not bandwidth-bound: WCS is asked for one
``scaleFactor`` -downsampled tile at a time and the tiles are stitched locally.

    # DN -> htxt inventory (73 codes) straight off the raster colormap
    uv run python scripts/natt.py inventory

Output::

    data/raw/natt/vistgerdir/vistgerd_dn<DN>_<RES>m.tif    (EPSG:3057, uint8 mask)
    data/raw/natt/vistgerdir/vistgerd_dn<DN>_<RES>m.json   (sidecar: label, area)
    data/raw/natt/vistgerdir/inventory.csv                 (DN -> htxt map)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE = "https://gis.natt.is/geoserver"
WCS = f"{BASE}/wcs"
WMS = f"{BASE}/wms"
WFS = f"{BASE}/wfs"

# WCS uses `__` where WMS/WFS use `:` for the workspace separator.
COVERAGE = "vistgerdir__ni_vg25r_3utg_lzw"
WMS_LAYER = "vistgerdir:ni_vg25r_3utg_lzw"

CRS = "EPSG:3057"
NATIVE_RES_M = 5.0
# Native grid envelope, from DescribeCoverage (EPSG:3057 metres).
NATIVE_BOUNDS = (244069.50866238773, 311026.6611954048,
                 758709.5086623877, 675016.6611954048)
NATIVE_WIDTH = 102928
NATIVE_HEIGHT = 72798

DEFAULT_DN = 95           # L14.2 Tún og akurlendi
# 50 m: 6 tiles / ~2 min, and still 2.4× finer than the 120 m grid every
# country-scale render in this repo draws on. 20 m (matching the Copernicus HRL
# stack in scripts/grassland_map.py) is 24 tiles and ~30 minutes — worth it once
# for detail work, a bad default for a first run. All three agree on the L14.2
# total to within 0.1% (1,805.8–1,807.5 km²).
DEFAULT_RES_M = 50
DEFAULT_TILE_PX = 5000    # 250 km square at 50 m — ~25 MB per WCS request

RAW = Path("data/raw/natt/vistgerdir")


# ── inventory: the raster colormap is the DN → htxt table ────────────────

def legend() -> list[tuple[int, str]]:
    """``DN`` → label, read from the WMS legend of the habitat raster.

    One request, ~73 entries. Labels come back as ``"L14.2 Tún og akurlendi"``
    — the exact string the withdrawn vector layer carried in ``htxt``.
    """
    r = httpx.get(
        WMS,
        params={
            "service": "WMS", "version": "1.1.1",
            "request": "GetLegendGraphic",
            "layer": WMS_LAYER,
            "format": "application/json",
        },
        timeout=60.0, follow_redirects=True,
    )
    r.raise_for_status()
    payload = r.json()
    try:
        entries = (payload["Legend"][0]["rules"][0]["symbolizers"][0]
                   ["Raster"]["colormap"]["entries"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"unexpected GetLegendGraphic payload for {WMS_LAYER}: {exc}") from exc
    out: dict[int, str] = {}
    for e in entries:
        label = (e.get("label") or "").strip()
        q = e.get("quantity")
        if q is None or not label:
            continue
        out[int(float(q))] = label
    return sorted(out.items())


def dn_for_code(code: str, table: list[tuple[int, str]] | None = None) -> int:
    """Resolve an L-code prefix (``"L14.2"``) to its raster ``DN``."""
    table = table if table is not None else legend()
    matches = [(dn, ht) for dn, ht in table
               if ht.split()[0].casefold() == code.casefold()]
    if not matches:
        near = [ht for _, ht in table if ht.casefold().startswith(code.casefold())]
        raise SystemExit(
            f"no habitat code {code!r} in the raster colormap"
            + (f" — did you mean {near[0]!r}?" if near else
               " — run: uv run python scripts/natt.py inventory"))
    return matches[0][0]


# ── WCS: fetch band 1 and mask it to one habitat code ────────────────────

def _dest_grid(res_m: float) -> tuple[int, int, rasterio.Affine]:
    xmin, _ymin, _xmax, ymax = NATIVE_BOUNDS
    factor = res_m / NATIVE_RES_M
    width = math.ceil(NATIVE_WIDTH / factor)
    height = math.ceil(NATIVE_HEIGHT / factor)
    transform = rasterio.Affine(res_m, 0.0, xmin, 0.0, -res_m, ymax)
    return width, height, transform


def _wcs_tile(x0: float, y0: float, x1: float, y1: float, res_m: float,
              *, timeout: float = 300.0) -> tuple[np.ndarray, rasterio.Affine]:
    """GetCoverage for one bbox, band 1 only, scaled to ``res_m``."""
    params = {
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": COVERAGE,
        "format": "image/tiff",
        "rangeSubset": "GRAY_INDEX",         # band 1 = habitat code; skip alpha
        "scaleFactor": NATIVE_RES_M / res_m,
    }
    # httpx keeps repeated keys, which is how WCS 2.0 expresses a 2-D subset.
    query = list(params.items()) + [
        ("subset", f"X({x0},{x1})"), ("subset", f"Y({y0},{y1})")]
    r = httpx.get(WCS, params=query, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    if r.content[:5] == b"<?xml":
        raise RuntimeError(f"WCS returned an exception: {r.text[:300]}")
    with MemoryFile(r.content) as mem, mem.open() as src:
        return src.read(1), src.transform


def fetch_mask(dn: int, *, res_m: float = DEFAULT_RES_M,
               tile_px: int = DEFAULT_TILE_PX) -> tuple[np.ndarray, rasterio.Affine]:
    """Mosaic the whole country at ``res_m`` and return a uint8 ``==dn`` mask.

    The 5 m source is 7.5 Gpx, so it is never fetched whole: WCS is asked for
    ``scaleFactor`` -downsampled tiles (nearest-neighbour server-side) and the
    tiles are stitched on the destination grid.
    """
    if res_m % NATIVE_RES_M:
        raise SystemExit(f"--res must be a multiple of {NATIVE_RES_M:g} m "
                         f"(the native grid), got {res_m:g}")
    width, height, transform = _dest_grid(res_m)
    out = np.zeros((height, width), dtype=np.uint8)
    xmin, _ymin, _xmax, ymax = NATIVE_BOUNDS

    cols = math.ceil(width / tile_px)
    rows = math.ceil(height / tile_px)
    print(f"  destination grid {width:,} × {height:,} px @ {res_m:g} m "
          f"({rows}×{cols} tiles)", file=sys.stderr)

    n = 0
    for r_i in range(rows):
        for c_i in range(cols):
            j0, j1 = c_i * tile_px, min((c_i + 1) * tile_px, width)
            i0, i1 = r_i * tile_px, min((r_i + 1) * tile_px, height)
            tx0 = xmin + j0 * res_m
            tx1 = xmin + j1 * res_m
            ty1 = ymax - i0 * res_m
            ty0 = ymax - i1 * res_m
            band, t = _wcs_tile(tx0, ty0, tx1, ty1, res_m)
            # Place by the tile's own georeference rather than trusting that the
            # server honoured the requested bbox exactly.
            oj = int(round((t.c - transform.c) / res_m))
            oi = int(round((transform.f - t.f) / res_m))
            h = min(band.shape[0], height - oi)
            w = min(band.shape[1], width - oj)
            if h > 0 and w > 0:
                out[oi:oi + h, oj:oj + w] = (band[:h, :w] == dn)
            n += 1
            print(f"    tile {n}/{rows * cols}  {band.shape[1]}×{band.shape[0]} px  "
                  f"→ [{oi}:{oi + h}, {oj}:{oj + w}]", file=sys.stderr)
    return out, transform


def write_mask(mask: np.ndarray, transform: rasterio.Affine, out: Path) -> None:
    """Tiled + LZW GeoTIFF, same on-disk conventions as the Tier-3 cache
    (``scripts/build_cache.py``): ISN93, uint8, predictor=2, 512 px blocks."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out, "w", driver="GTiff", dtype="uint8", count=1,
        width=mask.shape[1], height=mask.shape[0],
        crs=CRS, transform=transform, nodata=0,
        compress="lzw", predictor=2, tiled=True,
        blockxsize=512, blockysize=512,
    ) as dst:
        dst.write(mask, 1)


def mask_path(dn: int, res_m: float) -> Path:
    return RAW / f"vistgerd_dn{dn}_{res_m:g}m.tif"


# ── commands ─────────────────────────────────────────────────────────────

def cmd_habitat(args: argparse.Namespace) -> None:
    if args.format == "geojson":
        raise SystemExit(
            "GeoJSON output was retired in 2026-08: NÍ withdrew the polygon "
            "layer LMI_vektor:vistgerd it came from, and the surviving "
            "vistgerdir:v_vg25v_fl_* vector layers cover geothermal, freshwater "
            "and littoral habitats ONLY — not the terrestrial map. Habitat "
            "extents now come from the raster; use --format geotiff. "
            "See .agents/skills/natt/SKILL.md.")

    table = legend()
    if args.code:
        dn = dn_for_code(args.code, table)
    else:
        dn = args.dn if args.dn is not None else DEFAULT_DN
    label = dict(table).get(dn)
    if label is None:
        raise SystemExit(
            f"DN={dn} is not in the raster colormap — run: "
            f"uv run python scripts/natt.py inventory")

    print(f"Fetching DN={dn} ({label}) at {args.res:g} m ...", file=sys.stderr)
    mask, transform = fetch_mask(dn, res_m=args.res, tile_px=args.tile_px)

    px = int(mask.sum())
    area_km2 = px * (args.res ** 2) / 1e6
    out = mask_path(dn, args.res)
    write_mask(mask, transform, out)
    side = out.with_suffix(".json")
    side.write_text(json.dumps({
        "dn": dn,
        "htxt": label,
        "code": label.split()[0],
        "resolution_m": args.res,
        "crs": CRS,
        "coverage": COVERAGE,
        "pixel_count": px,
        "area_km2": area_km2,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
    print(f"  {px:,} px  →  {area_km2:,.1f} km²  ({label})", file=sys.stderr)


def cmd_inventory(_: argparse.Namespace) -> None:
    pairs = legend()
    out = RAW / "inventory.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DN", "htxt"])
        w.writerows(pairs)
    print(f"Wrote {len(pairs)} DN→htxt rows to {out}", file=sys.stderr)
    for dn, ht in pairs:
        print(f"  DN={dn:>4}  {ht}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    h = sp.add_parser("habitat", help="download one habitat type as a raster mask")
    g = h.add_mutually_exclusive_group()
    g.add_argument("--dn", type=int,
                   help=f"raster code, e.g. {DEFAULT_DN} = L14.2 (default)")
    g.add_argument("--code", help="L-code, e.g. L14.2 — resolved via the colormap")
    h.add_argument("--res", type=float, default=DEFAULT_RES_M, metavar="METRES",
                   help=f"output resolution, multiple of {NATIVE_RES_M:g} "
                        f"(default {DEFAULT_RES_M})")
    h.add_argument("--tile-px", type=int, default=DEFAULT_TILE_PX,
                   help="WCS request tile size in output pixels "
                        f"(default {DEFAULT_TILE_PX})")
    h.add_argument("--format", choices=["geotiff", "geojson"], default="geotiff",
                   help="geojson is retired — kept only to explain the change")
    h.set_defaults(fn=cmd_habitat)

    inv = sp.add_parser("inventory", help="dump the DN→htxt mapping (73 codes)")
    inv.set_defaults(fn=cmd_inventory)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

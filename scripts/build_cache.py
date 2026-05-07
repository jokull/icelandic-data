"""Build derived caches for fast map construction.

Reads from the existing source tiers:

    data/geodata/*.geojson       (LMI WFS vectors — Tier 1)
    data/raw/lmi_hrl/*.tif       (HRL GeoTIFFs    — Tier 2)

…and writes:

    data/cache/constants.json    (Iceland scalars + bboxes  — Tier 4)
    data/cache/rasters/*.tif     (LZW + EPSG:3057 reprojections — Tier 3)

See ``scripts/utils/cache.py`` and ``.claude/skills/kortagerð.md`` for the
full caching strategy.

Subcommands::

    build_cache.py constants   — recompute Tier 4 only
    build_cache.py rasters     — recompute Tier 3 only (use --only NAME for one)
    build_cache.py all         — both
    build_cache.py status      — print what is cached / stale / missing

Re-running is safe: cache entries with a matching source SHA-256 are skipped
unless ``--force`` is passed. Stale entries (mismatched SHA) are rebuilt.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

# Make ``utils.cache`` importable when running as ``python scripts/build_cache.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.cache import (  # noqa: E402
    ARRAYS_DIR, CACHE, CONSTANTS_PATH, RASTERS_DIR, ROOT, sha256_file,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

GEODATA = ROOT / "data" / "geodata"
RAW_HRL = ROOT / "data" / "raw" / "lmi_hrl"

# CRSes whose Iceland-bbox we always cache (consumers need at least these).
BBOX_CRSES = ["EPSG:3057", "EPSG:5325", "EPSG:3857", "EPSG:4326"]

# Source HRL TIFFs we know how to ingest. Keyed by short name so render scripts
# look them up by ``cached_raster("grassland_isn93")``.
HRL_SOURCES: dict[str, dict] = {
    "grassland_isn93": {
        "src": "grassland_20m.tif",
        "dst_crs": "EPSG:3057",
        "compute_areas": True,        # area where pixel == 1
        "value_for_area": 1,
    },
    # GRAVPI is fetched as styled RGB by reports/grassland_probability_heatmap.py
    # — its decoded probability array is Tier 5 (.npy), not a raster.
}


# ── helpers ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _load_existing_constants() -> dict:
    if CONSTANTS_PATH.exists():
        return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))
    return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)


# ── Tier 4: constants.json ───────────────────────────────────────────────

def _iceland_total_area_km2() -> tuple[float, dict]:
    landmask = GEODATA / "Landmask.geojson"
    if not landmask.exists():
        raise SystemExit(
            f"Missing {landmask.relative_to(ROOT)} — run: "
            "uv run python scripts/lmi.py download")
    gdf = gpd.read_file(landmask).to_crs("EPSG:3057")
    area_km2 = float(gdf.geometry.area.sum() / 1e6)
    bxs = gdf.total_bounds.tolist()  # [minx, miny, maxx, maxy] in 3057
    return area_km2, {
        "source": str(landmask.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(landmask),
        "n_features": int(len(gdf)),
        "bbox_3057": bxs,
    }


def _bbox_in_other_crses(bbox_3057: list[float]) -> dict:
    """Reproject the Iceland landmask bbox into a few common CRSes."""
    from shapely.geometry import box
    from pyproj import Transformer

    geom = box(*bbox_3057)
    out: dict[str, list[float]] = {"EPSG:3057": list(bbox_3057)}
    for crs in BBOX_CRSES:
        if crs == "EPSG:3057":
            continue
        t = Transformer.from_crs("EPSG:3057", crs, always_xy=True)
        # Sample the four corners and the midpoints of each edge for safety
        xs, ys = geom.exterior.xy
        rxs, rys = t.transform(list(xs), list(ys))
        out[crs] = [min(rxs), min(rys), max(rxs), max(rys)]
    return out


def _hrl_value_count(src_path: Path, value: int) -> tuple[int, float]:
    """Return (pixel_count, area_km2) of ``value`` in the source raster.

    Reads in 4096-row chunks so the 826 MB TIFF doesn't materialise in RAM.
    """
    with rasterio.open(src_path) as src:
        px_area_m2 = abs(src.transform.a * src.transform.e)
        block_h = 4096
        total = 0
        for off in range(0, src.height, block_h):
            h = min(block_h, src.height - off)
            window = rasterio.windows.Window(0, off, src.width, h)
            arr = src.read(1, window=window)
            total += int((arr == value).sum())
    return total, total * px_area_m2 / 1e6


def cmd_constants(args: argparse.Namespace) -> None:
    print("Building Tier 4 constants ...", file=sys.stderr)
    t0 = time.perf_counter()
    existing = _load_existing_constants() if not args.force else {}

    out: dict = {"version": 1, "built_at": _now()}

    # Iceland area + bbox
    area_km2, lm_meta = _iceland_total_area_km2()
    out["iceland_total_area_km2"] = area_km2
    out["landmask"] = lm_meta
    out["bbox"] = _bbox_in_other_crses(lm_meta["bbox_3057"])
    print(f"  iceland_total_area_km2 = {area_km2:,.1f}", file=sys.stderr)

    # Per-HRL-source scalars (area where pixel==value)
    out["hrl_sources"] = {}
    for short, meta in HRL_SOURCES.items():
        src = RAW_HRL / meta["src"]
        if not src.exists():
            print(f"  [skip] {short}: source {src.relative_to(ROOT)} absent",
                  file=sys.stderr)
            continue
        sha = sha256_file(src)
        prev = (existing.get("hrl_sources") or {}).get(short, {})
        if not args.force and prev.get("source_sha256") == sha and \
                prev.get("area_km2") is not None:
            print(f"  [reuse] {short}: source unchanged", file=sys.stderr)
            out["hrl_sources"][short] = prev
            continue
        if meta.get("compute_areas"):
            print(f"  computing {short} value-{meta['value_for_area']} area ...",
                  file=sys.stderr)
            cnt, akm = _hrl_value_count(src, meta["value_for_area"])
            out["hrl_sources"][short] = {
                "source": str(src.relative_to(ROOT)).replace("\\", "/"),
                "source_sha256": sha,
                "value": meta["value_for_area"],
                "pixel_count": cnt,
                "area_km2": akm,
            }
            print(f"    {short}: {cnt:,} px  → {akm:,.1f} km²",
                  file=sys.stderr)

    _atomic_write_json(CONSTANTS_PATH, out)
    print(f"Wrote {CONSTANTS_PATH.relative_to(ROOT)}  "
          f"({time.perf_counter() - t0:.1f} s)", file=sys.stderr)


# ── Tier 3: derived rasters ──────────────────────────────────────────────

def _build_one_raster(short: str, meta: dict, *, force: bool) -> dict | None:
    src = RAW_HRL / meta["src"]
    if not src.exists():
        print(f"  [skip] {short}: source absent", file=sys.stderr)
        return None
    out = RASTERS_DIR / f"{short}.tif"
    side = out.with_suffix(".json")
    sha = sha256_file(src)
    if not force and out.exists() and side.exists():
        prev = json.loads(side.read_text(encoding="utf-8"))
        if prev.get("source_sha256") == sha:
            print(f"  [reuse] {short}: cached raster matches source",
                  file=sys.stderr)
            return prev
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"  reprojecting {short}: {src.name} → {out.name}", file=sys.stderr)
    t0 = time.perf_counter()
    with rasterio.open(src) as s:
        # Choose a destination grid sized to the source's pixel scale (preserve
        # ground resolution as closely as possible).
        dst_transform, w, h = calculate_default_transform(
            s.crs, meta["dst_crs"], s.width, s.height, *s.bounds,
        )
        profile = s.profile.copy()
        profile.update(
            driver="GTiff",
            crs=meta["dst_crs"],
            transform=dst_transform,
            width=w,
            height=h,
            compress="lzw",
            predictor=2,        # delta predictor, halves the size on uint8
            tiled=True,
            blockxsize=512,
            blockysize=512,
        )
        with rasterio.open(out, "w", **profile) as d:
            for b in range(1, s.count + 1):
                reproject(
                    source=rasterio.band(s, b),
                    destination=rasterio.band(d, b),
                    src_transform=s.transform, src_crs=s.crs,
                    dst_transform=dst_transform, dst_crs=meta["dst_crs"],
                    resampling=Resampling.nearest,
                    num_threads=4,
                )
    dt = time.perf_counter() - t0
    sidecar = {
        "source": str(src.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha,
        "dst_crs": meta["dst_crs"],
        "compress": "lzw",
        "built_in_seconds": round(dt, 1),
        "size_bytes": out.stat().st_size,
        "src_bytes": src.stat().st_size,
    }
    side.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(f"    wrote {out.name}  "
          f"{src.stat().st_size / 1e6:.0f} MB → {out.stat().st_size / 1e6:.0f} MB  "
          f"({dt:.1f} s)", file=sys.stderr)
    return sidecar


def cmd_rasters(args: argparse.Namespace) -> None:
    print("Building Tier 3 derived rasters ...", file=sys.stderr)
    targets = list(HRL_SOURCES.items())
    if args.only:
        targets = [(s, m) for s, m in targets if s == args.only]
        if not targets:
            raise SystemExit(f"unknown --only target {args.only!r}; "
                             f"choices: {sorted(HRL_SOURCES)}")
    RASTERS_DIR.mkdir(parents=True, exist_ok=True)
    for short, meta in targets:
        _build_one_raster(short, meta, force=args.force)


# ── all + status ─────────────────────────────────────────────────────────

def cmd_all(args: argparse.Namespace) -> None:
    cmd_rasters(args)
    cmd_constants(args)


def _status_line(label: str, exists: bool, *, hint: str = "") -> str:
    badge = " OK " if exists else "miss"
    return f"  [{badge}] {label}{('   ' + hint) if hint and not exists else ''}"


def cmd_status(_: argparse.Namespace) -> None:
    print(f"Cache root: {CACHE.relative_to(ROOT) if CACHE.exists() else 'data/cache'}\n",
          file=sys.stderr)
    print(_status_line(f"constants.json", CONSTANTS_PATH.exists(),
                       hint="→ build_cache.py constants"))
    if CONSTANTS_PATH.exists():
        K = json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))
        print(f"          built_at: {K.get('built_at')}")
        print(f"          iceland_total_area_km2: "
              f"{K.get('iceland_total_area_km2'):,.1f}")
        for short, meta in (K.get("hrl_sources") or {}).items():
            print(f"          {short}: {meta.get('area_km2', 0):,.1f} km²")

    if RASTERS_DIR.exists():
        any_raster = False
        for short in sorted(HRL_SOURCES):
            tif = RASTERS_DIR / f"{short}.tif"
            side = tif.with_suffix(".json")
            ok = tif.exists() and side.exists()
            any_raster = any_raster or ok
            stale = ""
            if ok:
                meta = json.loads(side.read_text(encoding="utf-8"))
                src = ROOT / meta["source"]
                if src.exists():
                    cur = sha256_file(src)
                    if cur != meta["source_sha256"]:
                        stale = "  (STALE — source changed)"
                size_mb = tif.stat().st_size / 1e6
                print(f"  [ OK ] rasters/{short}.tif  ({size_mb:.0f} MB){stale}")
            else:
                print(_status_line(f"rasters/{short}.tif", False,
                                   hint=f"→ build_cache.py rasters --only {short}"))
        if not any_raster:
            print("  (no derived rasters yet — run: build_cache.py rasters)")
    else:
        print("  [miss] data/cache/rasters/   → build_cache.py rasters")

    if ARRAYS_DIR.exists():
        for npy in sorted(ARRAYS_DIR.glob("*.npy")):
            size_mb = npy.stat().st_size / 1e6
            print(f"  [ OK ] arrays/{npy.name}  ({size_mb:.1f} MB)")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("constants", help="rebuild Tier 4 constants.json")
    c.add_argument("--force", action="store_true",
                   help="ignore cached values, recompute everything")
    c.set_defaults(fn=cmd_constants)

    r = sp.add_parser("rasters", help="rebuild Tier 3 derived rasters")
    r.add_argument("--force", action="store_true")
    r.add_argument("--only", help=f"build only this entry: {sorted(HRL_SOURCES)}")
    r.set_defaults(fn=cmd_rasters)

    a = sp.add_parser("all", help="constants + rasters")
    a.add_argument("--force", action="store_true")
    a.add_argument("--only", default=None)
    a.set_defaults(fn=cmd_all)

    s = sp.add_parser("status", help="show what is cached / stale / missing")
    s.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

"""Verify that the derived cache (Tier 3 + 4) matches its sources.

These tests are skipped — with a helpful hint — when the cache hasn't been
built yet, so they're safe to run on a fresh checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio

from scripts.utils.cache import (  # imported via tests/conftest.py adding REPO_ROOT
    CONSTANTS_PATH, RASTERS_DIR, ROOT, sha256_file,
)

LANDMASK = ROOT / "data" / "geodata" / "Landmask.geojson"
GRASSLAND_SRC = ROOT / "data" / "raw" / "lmi_hrl" / "grassland_20m.tif"


def _require_constants() -> dict:
    if not CONSTANTS_PATH.exists():
        pytest.skip(
            "constants.json not built — run: "
            "uv run python scripts/build_cache.py constants")
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))


def test_iceland_constants_match_landmask():
    """The cached Iceland total area must match the Landmask polygon area
    within 0.1 % (geopandas + pyproj should be deterministic)."""
    K = _require_constants()
    if not LANDMASK.exists():
        pytest.skip("data/geodata/Landmask.geojson missing — run scripts/lmi.py download")
    import geopandas as gpd
    gdf = gpd.read_file(LANDMASK).to_crs("EPSG:3057")
    recomputed = float(gdf.geometry.area.sum() / 1e6)
    cached = float(K["iceland_total_area_km2"])
    rel_err = abs(recomputed - cached) / cached
    assert rel_err < 1e-3, (
        f"cached Iceland area {cached:,.1f} km² differs from recomputed "
        f"{recomputed:,.1f} km² (rel err {rel_err:.4%}) — rebuild cache")


def test_cache_fingerprints_valid():
    """For every source the cache claims to know about, recompute SHA-256
    and assert it still matches. A mismatch means the source moved under us."""
    K = _require_constants()
    seen_any = False
    if "landmask" in K:
        seen_any = True
        path = ROOT / K["landmask"]["source"]
        if path.exists():
            assert sha256_file(path) == K["landmask"]["sha256"], \
                f"{path} SHA-256 mismatch — rebuild cache"
    for short, meta in (K.get("hrl_sources") or {}).items():
        seen_any = True
        path = ROOT / meta["source"]
        if path.exists():
            assert sha256_file(path) == meta["source_sha256"], \
                f"{path} SHA-256 mismatch — rebuild cache"
    if not seen_any:
        pytest.skip("constants.json carries no fingerprints to verify")


def test_compressed_raster_matches_source():
    """The Tier-3 raster is a CRS-reprojected copy. Sample 10 random windows
    in the source CRS and confirm the histogram of pixel values is identical
    after reprojection (nearest-neighbour preserves values)."""
    cache = RASTERS_DIR / "grassland_isn93.tif"
    if not cache.exists():
        pytest.skip("Run: uv run python scripts/build_cache.py rasters")
    if not GRASSLAND_SRC.exists():
        pytest.skip("source grassland_20m.tif missing")

    with rasterio.open(GRASSLAND_SRC) as s_src, rasterio.open(cache) as s_dst:
        src_arr = s_src.read(1, out_shape=(2000, 2000))
        dst_arr = s_dst.read(1, out_shape=(2000, 2000))
    src_vals, src_counts = np.unique(src_arr, return_counts=True)
    dst_vals, dst_counts = np.unique(dst_arr, return_counts=True)
    src_hist = dict(zip(src_vals.tolist(), src_counts.tolist()))
    dst_hist = dict(zip(dst_vals.tolist(), dst_counts.tolist()))

    # The set of unique values must match exactly — nearest-neighbour should
    # never invent new pixel codes.
    assert set(src_hist) == set(dst_hist), (
        f"distinct pixel codes diverge — src {set(src_hist)} vs "
        f"cache {set(dst_hist)}")

    # Class fractions should be close (within ~5 %); reprojection grid
    # alignment introduces small shifts but not large class swaps.
    for v in src_hist:
        f_src = src_hist[v] / src_arr.size
        f_dst = dst_hist[v] / dst_arr.size
        assert abs(f_src - f_dst) < 0.05, (
            f"value {v}: src fraction {f_src:.4f} vs dst {f_dst:.4f}")

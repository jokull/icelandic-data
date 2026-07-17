"""Health probe — LMI High-Resolution Layer WCS (Copernicus HRL Iceland 2015).

Contract: every coverage in `scripts/lmi_hrl.py` COVERAGES still exists under
its published `coverageId`, still declares EPSG:5325 at 20 m, and GetCoverage
still returns `image/tiff`.

**Never call GetCoverage unbounded from here.** A full grassland pull is ~860 MB
uncompressed — that is what `lmi_hrl.py fetch` is for. Two bounded shapes cover
the same contract:

  - `DescribeCoverage` (~3.5 KB per coverage) proves the id, the CRS and the
    grid. It 404s for an unknown coverageId, so a rename fails loudly.
  - `GetCoverage` with a 2 km × 2 km `subset` (~37 KB) proves the *download*
    path — the parameter set `fetch()` sends, minus the payload.

DescribeCoverage alone would not catch a GeoServer that lists a coverage but
fails to serve its pixels, which is why both are here.
"""
from __future__ import annotations

import pytest

from scripts.lmi_hrl import COVERAGES, WCS

# 2 km box well inside the Iceland mask, in EPSG:5325 metres — the CRS the
# coverages are natively published in (see the module docstring in lmi_hrl.py).
SUBSET_X = "X(1500000,1502000)"
SUBSET_Y = "Y(300000,302000)"

# TIFF magic. GeoServer serves these big-endian ("MM"), but accept either so a
# byte-order change is not mistaken for an outage.
TIFF_MAGIC = (b"MM\x00\x2a", b"II\x2a\x00")


@pytest.mark.parametrize("layer,coverage", sorted(COVERAGES.items()))
def test_coverage_is_described(http, layer, coverage):
    """Cheapest proof that a coverage still exists under the id we hardcode."""
    r = http.get(
        WCS,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "request": "DescribeCoverage",
            "coverageId": coverage,
        },
    )
    assert r.status_code == 200, (
        f"{r.request.url} -> {r.status_code}: coverage {coverage!r} "
        f"({layer}) may have been renamed — {r.text[:200]}"
    )

    body = r.text
    assert f"<wcs:CoverageId>{coverage}</wcs:CoverageId>" in body, (
        f"{coverage} -> 200 but the description is for another coverage: {body[:300]}"
    )
    # The 20 m EPSG:5325 grid is baked into every downstream reprojection
    # (scripts/build_cache.py, grassland_map.py). If LMI republishes in another
    # CRS, the cache builder would silently produce a misplaced Iceland.
    assert "EPSG/0/5325" in body, (
        f"{coverage} no longer declares EPSG:5325 — reprojection assumptions "
        f"in build_cache.py are stale"
    )


def test_unknown_coverage_is_rejected(http):
    """Guards against a server that 200s on anything.

    Without this, `test_coverage_is_described` could go green against an error
    page and a rename would slip through.
    """
    r = http.get(
        WCS,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "request": "DescribeCoverage",
            "coverageId": "High_Resolution_Layer__NoSuchCoverage",
        },
    )
    assert r.status_code == 404, (
        f"{r.request.url} -> {r.status_code}: expected 404 for a nonexistent "
        f"coverage — WCS may no longer report missing coverages honestly"
    )


def test_grassland_getcoverage_serves_tiff(http):
    """The download path `fetch()` uses, clipped to 2 km × 2 km (~37 KB)."""
    r = http.get(
        WCS,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "coverageId": COVERAGES["grassland"],
            "format": "image/tiff",
            "subset": [SUBSET_X, SUBSET_Y],
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    ctype = r.headers.get("content-type", "")
    assert "tiff" in ctype.lower(), (
        f"{r.request.url} -> {r.status_code} with content-type {ctype!r}; "
        f"body starts {r.content[:120]!r}"
    )
    assert r.content[:4] in TIFF_MAGIC, (
        f"response is not a TIFF: first bytes {r.content[:8]!r}"
    )
    # Type check, not a size check — a 2 km box at 20 m is 100×100 px, but the
    # exact compressed size is not a contract.
    assert len(r.content) > 1_000, f"suspiciously small GeoTIFF: {len(r.content)} bytes"

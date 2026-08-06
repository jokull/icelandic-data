"""Health probe — Náttúrufræðistofnun habitat map (gis.natt.is GeoServer).

Contract: the 1:25.000 3rd-edition habitat raster `scripts/natt.py` reads still
exists under the name that script requests, and its colormap still maps
`DN=95` → `"L14.2 Tún og akurlendi"` — the cultivated-land code behind
`scripts/agricultural_land_map.py`. That colormap is also the `inventory`
subcommand's only data source, so one request covers both.

Payload discipline: the coverage is 7.5 Gpx at 5 m, so nothing here fetches
pixels at map resolution. Capabilities proves the name, the legend JSON is a few
KB, and the one `GetCoverage` is scaled down to a 1 km grid (~200 × 150 px).

History: `LMI_vektor:vistgerd`, the polygonised vector edition this script used
until 2026-08, was withdrawn from gis.natt.is, gis.lmi.is and ogc.gis.is alike.
The `vistgerdir:v_vg25v_fl_*` vector layers that appeared alongside are NOT its
replacement — they carry only geothermal, freshwater and littoral habitats. The
raster is, and it kept the codes. See `.agents/skills/natt/SKILL.md`.
"""
from __future__ import annotations

from scripts.natt import COVERAGE, DEFAULT_DN, WCS, WMS, WMS_LAYER

L14_2 = "L14.2 Tún og akurlendi"


def test_capabilities_lists_the_habitat_coverage(http):
    """A rename is the documented failure mode — catch it by name."""
    r = http.get(
        WCS,
        params={"service": "WCS", "version": "2.0.1", "request": "GetCapabilities"},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert f"<wcs:CoverageId>{COVERAGE}</wcs:CoverageId>" in r.text, (
        f"{r.request.url} -> {r.status_code}: {COVERAGE} absent from WCS "
        f"capabilities — renamed or withdrawn; see the natt skill"
    )


def test_legend_still_maps_dn95_to_cultivated_land(http):
    """The raster colormap *is* the DN→htxt inventory natt.py emits."""
    r = http.get(
        WMS,
        params={
            "service": "WMS", "version": "1.1.1",
            "request": "GetLegendGraphic",
            "layer": WMS_LAYER,
            "format": "application/json",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    entries = (payload["Legend"][0]["rules"][0]["symbolizers"][0]
               ["Raster"]["colormap"]["entries"])
    table = {int(float(e["quantity"])): (e.get("label") or "").strip()
             for e in entries if e.get("quantity") is not None}

    # Non-emptiness, not an exact count — a 4th edition may add or drop codes.
    assert len(table) > 50, f"colormap shrank to {len(table)} entries: {sorted(table)}"
    assert table.get(DEFAULT_DN) == L14_2, (
        f"DN={DEFAULT_DN} is {table.get(DEFAULT_DN)!r}, expected {L14_2!r} — "
        f"the habitat codes were renumbered; scripts/natt.py and "
        f"scripts/agricultural_land_map.py both assume this pair"
    )


def test_wcs_serves_band_1_habitat_codes(http):
    """`GetCoverage` returns the code band, and DN=95 is actually in it.

    `scaleFactor=0.005` collapses the 5 m grid to 1 km — a ~30 KB TIFF that
    still contains thousands of cultivated-land pixels.
    """
    r = http.get(
        WCS,
        params=[
            ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
            ("coverageId", COVERAGE),
            ("format", "image/tiff"),
            ("rangeSubset", "GRAY_INDEX"),
            ("scaleFactor", "0.005"),
        ],
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.content[:5] != b"<?xml", (
        f"{r.request.url} -> WCS exception: {r.text[:300]}")

    import numpy as np
    from rasterio.io import MemoryFile

    with MemoryFile(r.content) as mem, mem.open() as src:
        assert src.crs is not None and src.crs.to_string() == "EPSG:3057", (
            f"coverage CRS is {src.crs}, expected EPSG:3057 (ISN93) — the whole "
            f"map stack assumes the raster arrives already projected")
        band = src.read(1)

    present = set(np.unique(band).tolist())
    assert DEFAULT_DN in present, (
        f"DN={DEFAULT_DN} ({L14_2}) absent from band 1 at 1 km; "
        f"values present: {sorted(present)[:25]}"
    )

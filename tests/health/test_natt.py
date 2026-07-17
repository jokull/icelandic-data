"""Health probe — Náttúrufræðistofnun GeoServer WFS (gis.natt.is).

Contract: the habitat-type layer `scripts/natt.py` LAYER points at still exists
and still serves the `DN` / `htxt` attribute pair that every CQL filter in that
script is built from (`DN=95` = L14.2 Tún og akurlendi, the cultivated-land
polygons behind `scripts/agricultural_land_map.py`).

**This probe is expected to fail as of 2026-07-17** — that is the point, not a
bug in the test. `LMI_vektor:vistgerd` has been withdrawn from gis.natt.is,
gis.lmi.is and ogc.gis.is alike; all three answer
`InvalidParameterValue: Feature type LMI_vektor:vistgerd unknown`. NÍ appear to
have reorganised the habitat data into a new `vistgerdir:` workspace
(`v_vg25v_fl_land`, `_fl_vatn`, `_fl_fjorur`), but those layers are *not* a
drop-in replacement: they carry a different schema (`vg1`, `vg1_texti`, … — no
`DN`/`htxt`) and orders of magnitude fewer polygons. Migrating natt.py needs a
decision about which new layer maps to the old habitat codes, so the probe
records the break rather than papering over it.

Payload discipline: the layer is ~24M polygons (the polygonised 5 m raster), so
neither request here transfers geometry — capabilities proves the name,
`resultType=hits` proves non-emptiness, and the attribute check uses
`propertyName=DN,htxt` with `count=5`.
"""
from __future__ import annotations

import re

from scripts.natt import LAYER, WFS


def test_capabilities_lists_the_habitat_layer(http):
    """A rename is the documented failure mode — catch it by name."""
    r = http.get(
        WFS,
        params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert f"<Name>{LAYER}</Name>" in r.text, (
        f"{r.request.url} -> {r.status_code}: {LAYER} absent from WFS "
        f"capabilities — renamed or withdrawn; see the natt skill"
    )


def test_habitat_layer_serves_dn_and_htxt(http):
    """`DN` + `htxt` are the only two attributes natt.py reads.

    Bounded with count=5 and propertyName so no geometry crosses the wire.
    """
    r = http.get(
        WFS,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": LAYER,
            "propertyName": "DN,htxt",
            "outputFormat": "application/json",
            "count": 5,
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert payload.get("type") == "FeatureCollection", (
        f"unexpected payload type {payload.get('type')!r}"
    )
    features = payload.get("features") or []
    assert features, f"{LAYER} returned zero features"

    props = features[0].get("properties") or {}
    assert "DN" in props and "htxt" in props, (
        f"{LAYER} no longer exposes DN/htxt; got {sorted(props)}"
    )
    assert isinstance(props["DN"], int), (
        f"DN is {type(props['DN']).__name__}, expected int — CQL filters like "
        f"DN=95 assume an integer column"
    )


def test_cultivated_land_filter_still_matches(http):
    """DN=95 (L14.2 Tún og akurlendi) — the filter the agricultural-land map runs.

    `hits` only: the real fetch is ~16.6k polygons and belongs in a fetch run.
    """
    r = http.get(
        WFS,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": LAYER,
            "resultType": "hits",
            "CQL_FILTER": "DN=95",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    match = re.search(r'numberMatched="(\d+)"', r.text)
    assert match, f"{r.request.url} -> {r.status_code}: no numberMatched in {r.text[:200]}"
    # Non-emptiness, not a count — the polygon total shifts between editions.
    assert int(match.group(1)) > 0, "DN=95 (L14.2) matched zero polygons"

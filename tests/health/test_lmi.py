"""Health probe — Landmælingar Íslands geodata WFS (gis.lmi.is).

Contract: every layer in `scripts/lmi.py` CORE_LAYERS still exists under its
published name, and the GeoServer still answers the one request shape
`fetch_layer()` makes — GetFeature with `outputFormat=application/json` and
`srsName=EPSG:4326`.

Layer *renames* are the realistic break here, not an outage: LMI reorganises
workspaces (the sibling `natt` probe documents one such disappearance), and a
renamed layer only surfaces as "0 features" at the bottom of a download run.
GetCapabilities catches it up front, for ~130 KB per workspace.

Payload discipline: CORE_LAYERS spans two workspaces, so capabilities is
fetched once per workspace rather than once per layer. The GeoJSON round-trip
is exercised against a *point* layer only — `ERM:Landmask` returns 800 KB for
a single feature, and the whole core bundle is ~50 MB. Feature-serving for the
polygon layers is proven with `resultType=hits`, which is ~700 bytes and does
not transfer geometry.
"""
from __future__ import annotations

import re

import pytest

from scripts.lmi import CORE_LAYERS, WFS_BASE, layer_workspace

WORKSPACES = sorted({layer_workspace(layer) for layer in CORE_LAYERS})

# A small point layer — proves the GeoJSON/EPSG:4326 contract without pulling
# a country-sized polygon.
POINT_LAYER = "ERM:BuiltupAreaPoints"

# The flagship layer every map script starts from. Probed via `hits` because
# its geometry is enormous.
LANDMASK = "ERM:Landmask"


def _wfs(workspace: str) -> str:
    return WFS_BASE.format(workspace=workspace)


@pytest.mark.parametrize("workspace", WORKSPACES)
def test_capabilities_lists_every_core_layer(http, workspace):
    """Each CORE_LAYERS name must still be advertised by its workspace."""
    url = _wfs(workspace)
    r = http.get(
        url,
        params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    body = r.text
    expected = [layer for layer in CORE_LAYERS if layer_workspace(layer) == workspace]
    missing = [layer for layer in expected if f"<Name>{layer}</Name>" not in body]
    assert not missing, (
        f"{url} -> {r.status_code}: layers absent from WFS capabilities "
        f"(renamed or removed?): {missing}"
    )


def test_point_layer_serves_geojson(http):
    """The exact request shape `fetch_layer()` builds, bounded to 5 features."""
    r = http.get(
        _wfs(layer_workspace(POINT_LAYER)),
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": POINT_LAYER,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "count": 5,
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert payload.get("type") == "FeatureCollection", (
        f"{POINT_LAYER} -> unexpected payload type {payload.get('type')!r}"
    )
    features = payload.get("features") or []
    assert features, f"{POINT_LAYER} returned zero features"

    first = features[0]
    assert first.get("properties"), f"{POINT_LAYER} feature has empty properties"

    # srsName=EPSG:4326 must actually be honoured — a GeoServer that silently
    # served ISN93 metres would put every map in the North Atlantic.
    lon, lat = first["geometry"]["coordinates"][:2]
    assert -25 < lon < -13, f"{POINT_LAYER} lon {lon} outside Iceland — wrong CRS?"
    assert 63 < lat < 67, f"{POINT_LAYER} lat {lat} outside Iceland — wrong CRS?"


def test_landmask_is_non_empty(http):
    """`resultType=hits` — non-emptiness without the 800 KB polygon."""
    url = _wfs(layer_workspace(LANDMASK))
    r = http.get(
        url,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": LANDMASK,
            "resultType": "hits",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    match = re.search(r'numberMatched="(\d+)"', r.text)
    assert match, f"{url} -> {r.status_code}: no numberMatched in {r.text[:200]}"
    assert int(match.group(1)) > 0, f"{LANDMASK} matched zero features"

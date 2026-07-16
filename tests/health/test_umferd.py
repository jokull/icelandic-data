"""Health probe — Vegagerðin traffic-counter WFS.

Contract: both layers scripts/umferd.py reads still exist and serve features.
Uses WFS `count` so the probe pulls a handful of features, never the full set.
"""
from __future__ import annotations

import pytest

from scripts.umferd import LAYER_REALTIME, LAYER_STATIONS, WFS_BASE


def _features(http, layer, count=5):
    r = http.get(
        WFS_BASE,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": layer,
            "outputFormat": "application/json",
            "count": count,
        },
    )
    assert r.status_code == 200, f"{layer} -> {r.status_code}: {r.text[:200]}"
    payload = r.json()
    assert payload.get("type") == "FeatureCollection", f"unexpected payload: {payload.get('type')}"
    return payload["features"]


@pytest.mark.parametrize("layer", [LAYER_REALTIME, LAYER_STATIONS])
def test_layer_serves_features(http, layer):
    features = _features(http, layer)
    assert features, f"{layer} returned zero features"

    first = features[0]
    assert "properties" in first, f"{layer} feature has no properties"
    assert first["properties"], f"{layer} feature has empty properties"


def test_capabilities_lists_both_layers(http):
    """Catches a layer being renamed, which is the likelier break than an outage."""
    r = http.get(
        WFS_BASE,
        params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    body = r.text
    for layer in (LAYER_REALTIME, LAYER_STATIONS):
        assert layer in body, f"{layer} absent from WFS capabilities — renamed or removed?"

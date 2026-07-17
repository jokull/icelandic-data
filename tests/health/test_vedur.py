"""Health probe — Veðurstofa Íslands (Icelandic Met Office).

Two upstreams, probed separately because they fail independently and mean
different things:

  1. api.vedur.is — the modern JSON/OpenAPI service (weather + quakes). This is
     what the skill recommends, so this is what must stay green.
  2. xmlweather.vedur.is — the legacy XML endpoint. Still serving, but
     superseded (issue #9). Probed `degraded_ok`: the day Veðurstofa retire it
     we want to be told, not woken — nothing here depends on it any more except
     forecasts, and a planned retirement is not an outage.

Contract for the modern API, in order of cost:
  - /weather/capabilities   2.9 KB, lists every observation type — cheapest
                            proof the service is really up, not just a 200
  - /weather/stations       776 stations; probed for shape via one station
  - /quakes/events          GeoJSON FeatureCollection, magnitude-filtered

Note `format=json` on /quakes/events returns GeoJSON despite the name, and there
is NO `limit` parameter (it 422s). Queries are bounded with start_time instead.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import pytest

from tests.health.conftest import assert_fresh

WEATHER = "https://api.vedur.is/weather"
QUAKES = "https://api.vedur.is/quakes"
LEGACY_OBS = "https://xmlweather.vedur.is/?op_w=xml&type=obs&lang=en&view=xml&ids=1&params=T"


def _since(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------
# Modern API — weather
# --------------------------------------------------------------------------


def test_weather_capabilities(http):
    """The cheapest real contract: 2.9 KB describing every observation type."""
    r = http.get(f"{WEATHER}/capabilities")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    caps = r.json()
    assert caps, "capabilities is empty"
    # aws = automatic weather stations, the backbone of the observation endpoints.
    assert "aws" in caps, f"no 'aws' capability; got {sorted(caps)}"
    assert caps["aws"].get("observation_type"), "aws advertises no observation types"


def test_weather_stations(http):
    r = http.get(f"{WEATHER}/stations")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    stations = r.json()
    assert isinstance(stations, list) and stations, "station list is empty"
    # Loose floor — stations get added and retired. ~776 as of 2026-07.
    assert len(stations) > 300, f"only {len(stations)} stations; expected several hundred"

    first = stations[0]
    assert isinstance(first, dict) and first, f"unexpected station shape: {first!r}"


def test_weather_latest_aws_observations(http):
    """The endpoint anything reading current conditions would call."""
    r = http.get(f"{WEATHER}/observations/aws/10min/latest")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    payload = r.json()
    assert payload, "latest AWS observations returned nothing"


# --------------------------------------------------------------------------
# Modern API — quakes
# --------------------------------------------------------------------------


def test_quake_count_is_a_number(http):
    """/events/count returns a bare number — the cheapest quake check there is."""
    r = http.get(f"{QUAKES}/events/count", params={"start_time": _since(24)})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    count = int(r.text.strip())
    # Iceland is seismically busy; 0 in 24h is possible but implausible enough
    # to be worth knowing about, so only the type/sign is asserted.
    assert count >= 0, f"implausible quake count {count}"


def test_quake_events_are_geojson_with_expected_properties(http):
    r = http.get(
        f"{QUAKES}/events",
        params={"start_time": _since(72), "size_min": 1},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert payload.get("type") == "FeatureCollection", f"not GeoJSON: {payload.get('type')!r}"

    features = payload.get("features", [])
    if not features:
        pytest.skip("no quakes >=M1 in the last 72h — nothing to assert on")

    props = features[0]["properties"]
    required = {"event_id", "time", "magnitude", "depth", "region"}
    missing = required - set(props)
    assert not missing, f"quake properties missing {missing}; got {sorted(props)}"

    assert isinstance(props["magnitude"], (int, float)), f"magnitude: {props['magnitude']!r}"
    assert -1 < props["magnitude"] < 10, f"implausible magnitude {props['magnitude']}"
    assert features[0]["geometry"]["type"] == "Point"


def test_quake_regions(http):
    r = http.get(f"{QUAKES}/regions")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.json(), "no seismic regions returned"


@pytest.mark.degraded_ok
def test_quake_data_is_recent(http):
    """Staleness, not outage — the feed can legitimately be quiet."""
    r = http.get(f"{QUAKES}/events", params={"start_time": _since(24 * 14)})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    features = r.json().get("features", [])
    assert features, "no quakes at all in 14 days — feed stalled?"

    newest = max(f["properties"]["time"] for f in features)
    assert_fresh(
        datetime.fromisoformat(newest.replace("Z", "+00:00")),
        timedelta(days=7),
        label="vedur latest quake",
    )


# --------------------------------------------------------------------------
# Legacy XML — superseded, so degraded rather than failed
# --------------------------------------------------------------------------


@pytest.mark.degraded_ok
def test_legacy_xml_endpoint_still_serves(http):
    """xmlweather is outdated (#9). Report its retirement; don't page for it.

    Still probed because the skill documents it for forecasts, which the modern
    API does not obviously replace.
    """
    r = http.get(LEGACY_OBS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    root = ElementTree.fromstring(r.content)
    assert root.tag == "observations", f"expected <observations>, got <{root.tag}>"

    stations = root.findall("station")
    assert stations, "legacy endpoint returned no <station> elements"
    assert stations[0].findtext("T"), "legacy station returned no temperature"

"""Health probe — Veðurstofa Íslands XML weather API.

Contract: station 1 (Reykjavík) returns a current observation with a
temperature and a parseable timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from xml.etree import ElementTree

import pytest

from tests.health.conftest import assert_fresh

OBS = "https://xmlweather.vedur.is/?op_w=xml&type=obs&lang=en&view=xml&ids=1&params=T"


@pytest.fixture(scope="module")
def station(http):
    r = http.get(OBS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert "xml" in r.headers["content-type"], r.headers["content-type"]

    root = ElementTree.fromstring(r.content)
    assert root.tag == "observations", f"expected <observations>, got <{root.tag}>"

    stations = root.findall("station")
    assert stations, "no <station> elements returned"
    return stations[0]


def test_station_reports_temperature(station):
    temp = station.findtext("T")
    assert temp, "station returned no <T> temperature"
    # Type check, not a value check — Iceland's range is wide and we don't
    # want a cold snap failing CI.
    value = float(temp)
    assert -40 < value < 40, f"implausible temperature {value}°C"


def test_station_is_identified(station):
    assert station.findtext("name"), "station has no <name>"
    assert station.get("id") == "1", f"expected station id=1, got {station.get('id')}"


@pytest.mark.degraded_ok
def test_observation_is_recent(station):
    """Stale-but-serving is degraded, not failed — so this is degraded_ok."""
    stamp = station.findtext("time")
    assert stamp, "station has no <time>"
    observed = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S")
    assert_fresh(observed, timedelta(hours=6), label="vedur station 1 observation")

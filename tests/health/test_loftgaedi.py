"""Health probe — Umhverfisstofnun air-quality API.

Contract: the station catalog is served and carries the identifiers the
loftgaedi scripts key on.
"""
from __future__ import annotations

BASE = "https://api.ust.is/aq/a"


def test_station_catalog(http):
    r = http.get(f"{BASE}/getStations")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    stations = r.json()
    assert isinstance(stations, list), f"expected a list, got {type(stations).__name__}"
    assert stations, "station catalog is empty"

    # Loose floor, not an exact count — stations get added and retired.
    assert len(stations) >= 30, f"only {len(stations)} stations; expected ~57"

    required = {"name", "local_id", "municipality"}
    missing = required - set(stations[0])
    assert not missing, f"station record missing {missing}; got {sorted(stations[0])}"

    assert any(s["local_id"].startswith("STA-IS") for s in stations), (
        "no station carries a STA-IS* local_id"
    )

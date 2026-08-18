"""Health probe - Eurostat REST dissemination API (scripts/eurostat.py).

Smallest stable contract: the datasets this repo consumes must answer with
plausible euro-area values. All plain HTTP — safe from any CI runner.
"""
from __future__ import annotations

import httpx

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def get_json(dataset: str, **filters) -> dict:
    r = httpx.get(f"{BASE}/{dataset}", params={"format": "JSON", **filters},
                  timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def test_hicp_index_served():
    """HICP monthly index, euro area, 2015=100 — the repo's EA deflator."""
    js = get_json("prc_hicp_midx", geo="EA20", coicop="CP00", unit="I15")
    vals = [v for v in js["value"].values()]
    assert len(vals) > 100, "HICP series too short"
    assert max(vals) > 100, "euro-area HICP index (2015=100) should be above 100 by now"


def test_compensation_of_employees_served():
    """Compensation of employees (D1), EA20, quarterly — the repo's EA wage bill."""
    js = get_json("namq_10_a10", geo="EA20", na_item="D1", s_adj="SCA",
                  unit="CP_MEUR", nace_r2="TOTAL")
    vals = [v for v in js["value"].values()]
    assert len(vals) > 20, "D1 series too short"
    assert max(vals) > 400_000, "EA20 quarterly compensation should be ~EUR 1 trillion, not less"

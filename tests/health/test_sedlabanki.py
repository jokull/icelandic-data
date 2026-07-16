"""Health probe — Seðlabanki Íslands.

Two upstreams, probed separately because they fail independently:

- gagnabanki.is  — Power BI config behind the daily key-interest-rate series.
- fr.sedlabanki.is — SDMX endpoint documented in the sedlabanki skill.

The SDMX host was unreachable when these probes were written (connections hang
rather than refuse). It is probed with an explicit reason string so a scheduled
run says which of the two is broken instead of just "sedlabanki".
"""
from __future__ import annotations

import httpx
import pytest

GAGNABANKI_CONFIG = "https://gagnabanki.is/api/config"
SDMX_BASE = "https://fr.sedlabanki.is/sdmx/v2"


def test_gagnabanki_config_is_served(http):
    r = http.get(GAGNABANKI_CONFIG)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    config = r.json()
    assert config, "gagnabanki config is empty"
    # Power BI embed configs are the thing scripts/sedlabanki_rates.py drives.
    # Assert only that it is a populated mapping — the internal shape churns.
    assert isinstance(config, (dict, list)), f"unexpected config type {type(config).__name__}"


@pytest.mark.degraded_ok
def test_sdmx_host_responds(http):
    """fr.sedlabanki.is was hanging when this probe was written.

    Marked degraded_ok: no script in the repo reads SDMX today (the skill
    documents it), so it should not fail a scheduled run on its own. If this
    starts passing, promote it out of degraded_ok.
    """
    try:
        r = http.get(f"{SDMX_BASE}/structure/dataflow/IS2_EXT")
    except httpx.TransportError as exc:
        pytest.fail(
            f"SDMX host unreachable: {type(exc).__name__}: {exc}. "
            f"Documented in the sedlabanki skill; verify whether the endpoint moved."
        )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

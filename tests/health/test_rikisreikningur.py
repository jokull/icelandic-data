"""Health probe — Fjársýsla ríkisins state-accounts API.

Contract: the API answers with the configured key and reports a current
period. Expired or revoked keys surface here as a 401 rather than as a
confusing failure inside a fetch run.
"""
from __future__ import annotations

import re

import pytest

from scripts.rikisreikningur import API_BASE, API_KEY


@pytest.fixture(scope="module")
def auth():
    return {"X-Api-Key": API_KEY, "accept": "text/plain"}


def test_key_is_accepted_and_period_is_current(http, auth):
    r = http.get(f"{API_BASE}/api/FJS/NuverandiTimabil", headers=auth)
    assert r.status_code != 401, "API key rejected — rotated or revoked upstream"
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    payload = r.json()
    assert set(payload) >= {"ar", "timabil"}, f"unexpected shape: {sorted(payload)}"
    assert re.fullmatch(r"\d{4}", payload["ar"]), f"bad year: {payload['ar']!r}"
    assert re.fullmatch(r"\d{2}", payload["timabil"]), f"bad period: {payload['timabil']!r}"

    # Sanity floor only — the repo documents coverage from 2015.
    assert int(payload["ar"]) >= 2015, f"implausible reporting year {payload['ar']}"


def test_file_index_is_populated(http, auth):
    r = http.get(f"{API_BASE}/api/FJS/Data/skrar", headers=auth)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.json(), "published-file index is empty"

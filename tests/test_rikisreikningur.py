"""Tests for scripts/rikisreikningur.py.

Fast unit tests cover constants, the double-JSON decoder, and argparse wiring.
Slow integration tests hit the live Fjársýsla API (no auth beyond the public
X-Api-Key hard-coded in the SPA bundle).
"""
from __future__ import annotations

import json
import re

import pytest

from scripts import rikisreikningur as rr


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_api_base_points_at_azure_functions():
    assert rr.API_BASE.startswith("https://")
    assert "rikisreikningur" in rr.API_BASE.lower()


def test_api_key_is_a_uuid():
    """A drift here means the SPA was re-issued with a different key —
    re-extract with grep '[A-Za-z0-9_]{1,3} *= *\"[0-9a-f]{8}-' on the
    current main chunk."""
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", rr.API_KEY
    )


def test_decode_data_unwraps_single_element_string_list():
    """The /api/FJS/Data/* endpoints return [json_str]; decoder must unwrap."""
    inner = {"malefni_tg": [{"x": 1}]}
    payload = [json.dumps(inner)]
    assert rr._decode_data(payload) == inner


def test_decode_data_passes_through_regular_json():
    """Non-wrapped payloads (TekjurOgGjold, NuverandiTimabil) pass through."""
    payload = {"afkoma": [{"ar": 2024}]}
    assert rr._decode_data(payload) is payload
    passthrough_list = [{"a": 1}, {"b": 2}]
    assert rr._decode_data(passthrough_list) is passthrough_list


def test_raw_dir_under_data_raw():
    parts = rr.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert rr.RAW_DIR.name == "rikisreikningur"


# --------------------------------------------------------------------------
# Slow integration tests (live API)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_timabil_returns_current_period():
    """Contract test — the SPA's home page depends on this exact shape."""
    with rr._client() as c:
        t = rr.fetch_timabil(c)
    assert set(t.keys()) == {"ar", "timabil"}
    assert t["ar"].isdigit() and 2015 <= int(t["ar"]) <= 2099
    assert t["timabil"] in {f"{i:02}" for i in range(1, 14)}


@pytest.mark.slow
def test_tekjur_og_gjold_has_yearly_and_category_payloads():
    with rr._client() as c:
        d = rr.fetch_tekjur_og_gjold(c)
    assert set(d.keys()) >= {"afkoma", "tekjur_gjold"}
    assert len(d["afkoma"]) >= 5
    # Expected keys on each afkoma row
    for r in d["afkoma"]:
        assert {"ar", "tekjur", "gjold", "afkoma"} <= r.keys()
    # Expected keys + categories on the breakdown
    categories = {(r["tegund"], r["texti"]) for r in d["tekjur_gjold"]}
    assert ("Gjöld", "Laun") in categories
    assert ("Tekjur", "Skattar") in categories


@pytest.mark.slow
def test_malefni_endpoint_returns_policy_area_rows():
    with rr._client() as c:
        rows = rr.fetch_malefni(c)
    assert isinstance(rows, list)
    assert len(rows) > 100, f"only {len(rows)} rows — shape may have changed"
    # Every row needs the policy-area identifier + year + measure
    sample = rows[0]
    assert {"malefnasvid_numer", "malefnasvid_heiti", "timabil_ar", "tegund", "samtals"} <= sample.keys()


@pytest.mark.slow
def test_file_list_includes_main_rikisreikningur_reports():
    with rr._client() as c:
        files = rr.fetch_file_list(c)
    names = [f["nafn"] for f in files]
    # There must be at least one XLSX whose name contains "Rikisreikningur"
    assert any("Rikisreikningur" in n and n.endswith(".xlsx") for n in names), names[:5]

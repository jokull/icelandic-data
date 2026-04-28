"""Tests for scripts/vernd.py.

Fast unit tests verify the embed-URL reconstruction and constants; the slow
integration test runs the full Playwright scrape against the live Power BI
embed and asserts at least one data-bearing visual response.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from scripts import vernd as v


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_ids_are_canonical_uuids():
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v.REPORT_KEY
    )
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v.TENANT
    )


def test_cluster_is_nine():
    """Cluster 9 is baked into the official government-published embed URL.
    If this flips (e.g. Power BI migration), the URL we synthesize will no
    longer match the upstream and the scrape will silently break."""
    assert v.CLUSTER == 9


def test_embed_url_decodes_to_expected_payload():
    """Reversing the base64 must yield {k, t, c} matching our constants.
    This is the contract: the URL we ship has to be byte-identical to what
    stjornarradid.is publishes so consumers can cross-check."""
    url = v.embed_url()
    assert url.startswith("https://app.powerbi.com/view?r=")
    token = url.split("r=", 1)[1]
    # base64 decode with padding tolerated
    token += "=" * (-len(token) % 4)
    payload = json.loads(base64.b64decode(token))
    assert payload == {"k": v.REPORT_KEY, "t": v.TENANT, "c": v.CLUSTER}


def test_embed_url_matches_published_constant():
    """Tight coupling check: the exact URL published on stjornarradid.is is
    kept here verbatim; if Power BI changes the base64 encoding, this fails
    first. Update this test when the upstream URL rotates."""
    published = (
        "https://app.powerbi.com/view?r="
        "eyJrIjoiYTJhMDczNTMtMGY1NS00MGQyLWI3NjEtYmFiMjlhYmE2N2JjIiwidCI6"
        "IjUwOTQ4NGE4LWMwZmYtNDk2MC1iNWRhLTNiZGI3NWU5ODQ2MCIsImMiOjl9"
    )
    assert v.embed_url() == published


def test_raw_dir_under_data_raw():
    parts = v.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert v.RAW_DIR.name == "vernd"


# --------------------------------------------------------------------------
# Slow integration test (live network + Playwright)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_captures_some_responses(tmp_path, monkeypatch):
    """End-to-end scrape must produce at least one data-bearing response.
    Silent zero-responses is the regression we care about (Power BI change,
    cluster flip, tenant change, report key removal)."""
    monkeypatch.setattr(v, "RAW_DIR", tmp_path)
    v.cmd_fetch()

    out = tmp_path / "responses.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0, "scrape captured zero responses — embed likely broken"

    # At least one response must contain a DSR payload (the actual data).
    # Token/metadata-only responses are also valid, but we want to see real
    # measured rows too.
    has_data = any(
        "dsr" in str(r) and "DS" in str(r) for r in data
    )
    assert has_data, "no DSR/DS payload in any response — Power BI data contract may have changed"

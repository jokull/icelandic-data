"""Tests for scripts/tekjusagan.py.

Two layers:
  - Fast unit tests (default): import module, check constants, test pure
    functions that don't hit the network.
  - Network integration tests (marked 'slow'): hit the live Tekjusagan token
    endpoint and verify response shape. Run with:
        uv run pytest -m slow tests/test_tekjusagan.py

A full end-to-end Playwright scrape test is even slower (~1 min) and is also
gated behind the 'slow' marker so default `pytest` stays quick.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import tekjusagan as tk


# --------------------------------------------------------------------------
# Fast unit tests (no network)
# --------------------------------------------------------------------------


def test_report_id_is_expected_uuid():
    """The Power BI report ID should be a canonical UUID and match what the
    Tekjusagan site embeds. If either changes, scraping will break; the
    tight coupling is what we want to detect."""
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", tk.REPORT_ID)
    assert tk.REPORT_ID == "04ba62a1-8e38-44bd-a6b0-cb63d1fec3d8"


def test_group_id_is_expected_uuid():
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", tk.GROUP_ID)


def test_token_url_is_derived_from_report_id():
    assert tk.TOKEN_URL == f"https://tekjusagan.is/api/report/{tk.REPORT_ID}"


def test_reports_are_non_empty_route_pairs():
    """Every REPORTS entry is a (slug, url) pair pointing at tekjusagan.is."""
    assert len(tk.REPORTS) >= 1
    seen_slugs = set()
    for slug, url in tk.REPORTS:
        assert slug and re.fullmatch(r"[a-z_]+", slug), f"bad slug: {slug!r}"
        assert slug not in seen_slugs, f"duplicate slug: {slug}"
        seen_slugs.add(slug)
        assert url.startswith("https://tekjusagan.is/"), f"off-site url: {url}"


def test_raw_dir_is_under_data_raw():
    """Contract: scraped output lives in data/raw/{source}/, not scattered."""
    parts = tk.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert tk.RAW_DIR.name == "tekjusagan"


# --------------------------------------------------------------------------
# Network integration tests
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_token_shape():
    """Live network: the token endpoint returns {embedToken, id}.

    Tokens are short-lived (~1h) and public (no auth needed). If Tekjusagan
    changes its backend contract, this test surfaces it immediately.
    """
    tok = tk.fetch_token()

    # Shape
    assert isinstance(tok, dict)
    assert set(tok.keys()) >= {"embedToken", "id"}

    # id matches what the SPA uses
    assert tok["id"] == tk.REPORT_ID

    # Token shape: Power BI uses a custom 2-segment format
    # (base64(gzip(payload)).base64(metadata)), not a standard 3-segment JWT.
    # Current prod tokens are ~1700 chars; we check >= 500 to catch truncation.
    assert isinstance(tok["embedToken"], str)
    assert len(tok["embedToken"]) > 500, f"suspiciously short token: {len(tok['embedToken'])}"
    assert "." in tok["embedToken"], "embedToken missing expected '.' separator"
    # Metadata segment (after the '.') is base64-encoded JSON and must decode
    # to an object containing 'clusterUrl' and 'exp' fields.
    import base64, json as _json
    meta_b64 = tok["embedToken"].rsplit(".", 1)[-1]
    meta_b64 += "=" * (-len(meta_b64) % 4)
    meta = _json.loads(base64.b64decode(meta_b64))
    assert "clusterUrl" in meta, f"metadata missing clusterUrl: {meta.keys()}"
    assert "exp" in meta, f"metadata missing exp: {meta.keys()}"
    assert meta["clusterUrl"].startswith("https://"), meta["clusterUrl"]


@pytest.mark.slow
def test_cmd_token_writes_file(tmp_path, monkeypatch):
    """cmd_token writes the response to RAW_DIR/token.json. We redirect
    RAW_DIR to a tmp path to avoid polluting data/raw/ in tests."""
    monkeypatch.setattr(tk, "RAW_DIR", tmp_path)
    tk.cmd_token()
    out = tmp_path / "token.json"
    assert out.exists(), "cmd_token did not write token.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["id"] == tk.REPORT_ID
    assert len(data["embedToken"]) > 500


@pytest.mark.slow
def test_end_to_end_scrape_captures_something(tmp_path, monkeypatch):
    """The full SPA + Power BI drive captures at least one data response.

    This is a minimal contract test — we don't assert on the shape of the
    captured DAX results (which can change), only that the pipeline end-to-
    end produces *something*. A silent regression (0 responses) is the
    failure mode we care about.
    """
    monkeypatch.setattr(tk, "RAW_DIR", tmp_path)
    tk.cmd_fetch()
    out = tmp_path / "responses.json"
    assert out.exists()
    results = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(results, list)
    assert len(results) > 0, "scrape captured zero responses — SPA or Power BI contract likely changed"

    # Each entry should have a section + url, and either body or text
    for r in results:
        assert "section" in r and "url" in r
        assert ("body" in r) or ("text" in r)

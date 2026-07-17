"""Health probe — Mælaborð landbúnaðarins (Ministry of Agriculture).

scripts/maelabord_nautgripa.py hardcodes a published-to-web embed URL and the
name of one page inside it (`EFTIR_BUI_PAGE`, the per-farm matrix). The scrape
is a scroll-paginated Playwright run over a virtualised matrix visual — far too
heavy for a health check, and manual-only by policy anyway.

What is cheap and plain-HTTP is everything that scrape depends on:

  1. the report key inside REPORT is still published to web (else 401), and
  2. the "Eftir búi" page still exists under that exact section name — a
     renamed page is the likeliest break, and it would otherwise surface as the
     scraper silently capturing zero farms.
"""
from __future__ import annotations

import base64
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from scripts.maelabord_nautgripa import EFTIR_BUI_PAGE, REPORT
from tests.health.conftest import assert_fresh


def _report_key(view_url: str) -> str:
    """The `k` of the base64 `r=` payload the script pins."""
    token = parse_qs(urlparse(view_url).query)["r"][0]
    payload = json.loads(base64.b64decode(token + "=" * (-len(token) % 4)))
    return payload["k"]


REPORT_KEY = _report_key(REPORT)


@pytest.fixture(scope="module")
def model(powerbi):
    return powerbi.model(REPORT, REPORT_KEY)


def test_eftir_bui_page_still_exists(model, powerbi):
    sections = powerbi.sections(model)
    assert EFTIR_BUI_PAGE in sections, (
        f"page {EFTIR_BUI_PAGE} ('Eftir búi') absent from report {REPORT_KEY}; "
        f"pages are now {sorted(sections.values())}"
    )


@pytest.mark.degraded_ok
def test_subsidy_data_is_recent(model, powerbi):
    """Payments accrue year-round and the model refreshes on its own schedule,
    so the limit is deliberately loose — this catches a dead pipeline, not a
    quiet week."""
    assert_fresh(
        powerbi.last_refresh(model),
        timedelta(days=90),
        label="mælaborð landbúnaðarins dataset refresh",
    )

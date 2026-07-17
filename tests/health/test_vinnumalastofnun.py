"""Health probe — Vinnumálastofnun (Directorate of Labour).

scripts/vinnumalastofnun.py has two upstreams, and only one of them can fail
loudly on its own:

  1. **The Excel workbook on Contentful.** Contentful is content-addressed: each
     monthly upload lands on a *new* asset URL and the old one keeps serving
     200 forever. So a dead constant never 404s — it just quietly pins us to an
     old workbook. The probe therefore checks two different things: that
     EXCEL_URL still serves a workbook (hard), and that it is still the URL
     island.is links (degraded — we are up, just behind).
  2. **The Power BI embed.** Report key still published, and the default page
     the script deep-links to (POWERBI_PAGE) still exists in the report.

All plain HTTP. The Playwright scrape itself is manual-only by policy; what
this asserts is its precondition.
"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest

from scripts.vinnumalastofnun import (
    EXCEL_URL,
    LANDING,
    POWERBI_PAGE,
    POWERBI_REPORT_KEY,
    _embed_url,
)
from tests.health.conftest import assert_fresh

XLSM_TYPE = "application/vnd.ms-excel.sheet.macroenabled.12"

_ASSET_RE = re.compile(
    r"https://assets\.ctfassets\.net/[\w/]+/Talnagogn_atvinnuleysi\.xlsm"
)


def test_excel_workbook_is_served(http):
    """HEAD only — a health probe never pulls the half-megabyte workbook."""
    r = http.head(EXCEL_URL)
    assert r.status_code == 200, f"{EXCEL_URL} -> {r.status_code}"
    assert r.headers["content-type"].startswith(XLSM_TYPE), r.headers["content-type"]
    assert int(r.headers["content-length"]) > 10_000, (
        f"{EXCEL_URL} -> suspiciously small workbook: {r.headers['content-length']} bytes"
    )


@pytest.mark.degraded_ok
def test_hardcoded_excel_url_is_the_current_upload(http):
    """Degraded, not failed: an old asset URL still serves, so the fetch works —
    it just returns last quarter's numbers. This is the only signal that a new
    workbook was published."""
    r = http.get(LANDING)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    linked = set(_ASSET_RE.findall(r.text))
    assert linked, (
        f"no Talnagogn_atvinnuleysi.xlsm link on {LANDING} — the page was "
        f"restructured, or the workbook was renamed"
    )
    assert EXCEL_URL in linked, (
        f"EXCEL_URL in scripts/vinnumalastofnun.py is behind: {LANDING} now "
        f"links {sorted(linked)} — Contentful rotated the asset URL, update the constant"
    )


@pytest.fixture(scope="module")
def model(powerbi):
    return powerbi.model(_embed_url(), POWERBI_REPORT_KEY)


def test_powerbi_default_page_still_exists(model, powerbi):
    """The script deep-links `&pageName=`; a renamed page means it lands on a
    report page that never fires the DAX queries the scrape is waiting for."""
    sections = powerbi.sections(model)
    assert POWERBI_PAGE in sections, (
        f"page {POWERBI_PAGE} absent from the report; pages are now "
        f"{sorted(sections.values())}"
    )


@pytest.mark.degraded_ok
def test_powerbi_data_is_recent(model, powerbi):
    """Monthly publication, second week of the following month."""
    assert_fresh(
        powerbi.last_refresh(model),
        timedelta(days=45),
        label="vinnumalastofnun dashboard dataset refresh",
    )

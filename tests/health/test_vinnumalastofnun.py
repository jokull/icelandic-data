"""VMST health: resolve the current Contentful upload and probe Power BI.

Old assets stay available, so a hardcoded workbook URL cannot prove freshness.
"""
from __future__ import annotations

import re
from datetime import timedelta

import pytest

from scripts.vinnumalastofnun import (
    resolve_excel,
    LANDING,
    POWERBI_PAGE,
    POWERBI_REPORT_KEY,
    _embed_url,
)
from tests.health.conftest import assert_fresh

XLSM_TYPE = "application/vnd.ms-excel.sheet.macroenabled.12"

_ASSET_RE = re.compile(r"https://assets\.ctfassets\.net/[\w/-]+\.xlsm")


def test_excel_workbook_is_served(http):
    """HEAD only — a health probe never pulls the half-megabyte workbook."""
    page = http.get(LANDING)
    page.raise_for_status()
    url = resolve_excel(page.text)
    r = http.head(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    assert r.headers["content-type"].startswith(XLSM_TYPE), r.headers["content-type"]
    assert int(r.headers["content-length"]) > 10_000, (
        f"{url} -> suspiciously small workbook: {r.headers['content-length']} bytes"
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

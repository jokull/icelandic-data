"""Health probe — Farsæld barna (Barna- og fjölskyldustofa).

Contract: the single public embed scripts/farsaeld_barna.py reconstructs from
TENANT + REPORT_KEY still resolves, and still carries the report pages whose
`modelsAndExploration` payload *is* the data for this source — the dashboard
ships its numbers as static model data rather than live DAX, which is why the
scraper captures modelsAndExploration at all.

That makes this the rare Power BI source where the probed endpoint is not just
the scrape's precondition but literally the endpoint the scrape reads. Plain
HTTP, so no `browser` marker: Playwright is only how the script gets a browser
to issue this same request with the right resource key.

No freshness assertion: the underlying indicators are published in irregular
batches (the dataset can legitimately sit unrefreshed for months), so an age
limit here would be noise, not signal.
"""
from __future__ import annotations

import pytest

from scripts.farsaeld_barna import REPORT_KEY, embed_url


@pytest.fixture(scope="module")
def model(powerbi):
    return powerbi.model(embed_url(), REPORT_KEY)


def test_embed_still_resolves(model):
    assert model["models"][0].get("dbName"), (
        f"model has no dbName; got {sorted(model['models'][0])}"
    )


def test_report_exposes_its_pages(model, powerbi):
    """The dashboard is a many-page report; an empty page list means the scrape
    would capture a shell with no indicators in it."""
    sections = powerbi.sections(model)
    assert sections, "report resolved but exposes no pages — nothing to scrape"

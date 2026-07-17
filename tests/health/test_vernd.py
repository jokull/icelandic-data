"""Health probe — Lykilupplýsingar um vernd (Ríkislögreglustjóri).

Contract: scripts/vernd.py does not have an embed URL — it *reconstructs* one
from three constants (REPORT_KEY, TENANT, CLUSTER) that were read out of a
base64 payload on stjornarradid.is once, by hand. So the reconstruction inputs
are the thing that rots, and this probe asserts exactly them:

  1. embed_url() still resolves to a tenant cluster (TENANT is live)
  2. REPORT_KEY still resolves on that cluster (the report is still published
     to web — otherwise 401 UnableToFindKeyInDBorCacheException)

Lightweight, not `browser`: the Playwright scrape in vernd.py cannot be run
daily from a datacenter IP without the failures meaning bot detection rather
than upstream breakage. Its precondition — a live key on a live tenant — is
plain HTTP, and that is what actually breaks.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from scripts.vernd import REPORT_KEY, embed_url
from tests.health.conftest import assert_fresh


@pytest.fixture(scope="module")
def model(powerbi):
    return powerbi.model(embed_url(), REPORT_KEY)


def test_embed_reconstruction_still_resolves(model, powerbi):
    """The k/t/c constants still name a live, published report."""
    sections = powerbi.sections(model)
    assert sections, "report resolved but exposes no pages — nothing to scrape"


@pytest.mark.degraded_ok
def test_dashboard_data_is_recent(model, powerbi):
    """Monthly publication. Stale-but-serving is degraded, not down."""
    assert_fresh(
        powerbi.last_refresh(model),
        timedelta(days=45),
        label="vernd dashboard dataset refresh",
    )

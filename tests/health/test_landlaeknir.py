"""Health probe — Embætti landlæknis mælaborð (Directorate of Health).

scripts/landlaeknir.py carries a hand-transcribed CATALOG of ~33 dashboards
(slug -> report key) under one tenant. Two things rot independently:

  1. **The catalog drifts.** island.is/maelabord is where the keys came from,
     and it still embeds them as `app.powerbi.com/view?r=<base64>` links — so
     the catalog is checkable against its own source of truth over one GET.
  2. **A key stops resolving.** Probed on one representative dashboard
     (`mortis`, the one the skill documents), not all 33 — a health probe
     checks the contract, not the corpus.

Lightweight, not `browser`: the per-dashboard Playwright scrape is manual-only
by policy, and its precondition (live tenant + live key) is plain HTTP.
"""
from __future__ import annotations

import base64
import binascii
import json
import re

import pytest

from scripts.landlaeknir import CATALOG, TENANT, embed_url

MAELABORD = "https://island.is/maelabord"

_EMBED_RE = re.compile(r"app\.powerbi\.com/view\?r=([A-Za-z0-9_-]+)")

CATALOG_KEYS = {key for _, _, _, key in CATALOG}
MORTIS_KEY = next(key for _, slug, _, key in CATALOG if slug == "mortis")


def _decode(token: str) -> dict | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        return json.loads(base64.b64decode(padded).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


@pytest.fixture(scope="module")
def listed(http):
    """{report_key: tenant} for every embed linked from island.is/maelabord."""
    r = http.get(MAELABORD)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html")

    found = {}
    for token in set(_EMBED_RE.findall(r.text)):
        payload = _decode(token)
        if payload and "k" in payload:
            found[payload["k"]] = payload.get("t")
    assert found, (
        f"{MAELABORD} -> 200 but no app.powerbi.com/view?r= embeds — the page "
        f"was re-rendered and CATALOG can no longer be checked against it"
    )
    return found


def test_catalog_tenant_still_owns_the_dashboards(listed):
    assert TENANT in set(listed.values()), (
        f"tenant {TENANT} owns none of the {len(listed)} embeds on {MAELABORD} — "
        f"the dashboards were republished under a new tenant"
    )


def test_catalog_keys_are_still_published(listed):
    """A floor, not equality — individual dashboards live on sub-pages and come
    and go, but a wholesale republish (every key rotated) must go red."""
    still_listed = CATALOG_KEYS & set(listed)
    assert len(still_listed) >= len(CATALOG_KEYS) // 2, (
        f"only {len(still_listed)}/{len(CATALOG_KEYS)} catalog report keys are "
        f"still linked from {MAELABORD}; missing: {sorted(CATALOG_KEYS - set(listed))}"
    )


def test_one_dashboard_still_resolves(powerbi):
    """`mortis` stands in for the other 32 — same tenant, same embed backend."""
    model = powerbi.model(embed_url(MORTIS_KEY), MORTIS_KEY)
    assert powerbi.sections(model), "mortis resolved but exposes no pages"

"""Health probe — co2.is climate action plan (Webflow).

Contract, mirroring scripts/co2.py:

  1. /allar-adgerdir lists /adgerdir/<slug> viðfangsefni links.
  2. Each viðfangsefni page carries the accordion markup the parser splits on.

Scraper targets break by re-render far more often than by going down, so this
asserts on the two regexes co2.py actually depends on, not just a 200. It
fetches exactly one sub-page — never the full crawl — and writes nothing to
data/ (so it deliberately does not call fetch_vidfangsefni, which caches raw
HTML as a side effect).
"""
from __future__ import annotations

import pytest

from scripts.co2 import _ACCORDION_SPLIT_RE, _VIDFANGSEFNI_RE, INDEX


@pytest.fixture(scope="module")
def slugs(http):
    r = http.get(INDEX)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html")

    found = sorted(set(_VIDFANGSEFNI_RE.findall(r.text)))
    assert found, (
        f"no /adgerdir/<slug> links at {INDEX} — Webflow re-render would break "
        f"discover_vidfangsefni()"
    )
    return found


def test_index_lists_vidfangsefni(slugs):
    # The plan spans 4 kerfi; a loose floor tolerates page restructuring
    # without tolerating an empty crawl.
    assert len(slugs) >= 4, f"only {len(slugs)} viðfangsefni discovered: {slugs}"


def test_one_vidfangsefni_page_has_accordions(http, slugs):
    """Fetch a single sub-page — a health probe never runs the full crawl."""
    url = f"https://www.co2.is{slugs[0]}"
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"

    blocks = list(_ACCORDION_SPLIT_RE.finditer(r.text))
    assert blocks, f"no accordion blocks at {url} — _ACCORDION_SPLIT_RE no longer matches"

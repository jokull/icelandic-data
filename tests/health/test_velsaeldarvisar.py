"""Health probe — visar.hagstofa.is indicator catalogs (Webflow).

scripts/velsaeldarvisar.py crawls five Webflow pages and scrapes indicator
names plus the PX-Web table URLs each indicator points at. The catalog is only
useful as a bridge into the `hagstofan` skill, so the contract is:

  1. The page is served and still emits `data-w-tab` / `w-tab-pane` markup —
     _TAB_PANE_RE is what separates indicators from parent category panes.
  2. Indicator panes still link px.hagstofa.is PX-Web tables in the URL form
     _PX_URL_RE matches, and _px_code() can still pull a table code out.

Webflow re-renders break this far more often than the host goes down, so both
assertions run the script's real regexes over the real HTML. parse_page() is a
pure function over a string — safe to call, unlike build_catalog(), which
writes raw HTML into data/raw/.

Two pages are probed, not all five: /felagsvisar (single page, densest in PX
links) and one /velsaeldarvisar sub-page (the nested URL shape). A health probe
does not re-run the crawl.
"""
from __future__ import annotations

import re

import pytest

from scripts.velsaeldarvisar import PAGES, parse_page

FELAGSVISAR = next(url for section, _, url in PAGES if section == "felagsvisar")
VELSAELD = next(url for section, _, url in PAGES if section == "velsaeldarvisar")

# The PX table codes hagstofan tables are addressed by, e.g. THJ09000.
_PX_CODE_RE = re.compile(r"^[A-Z]{3}\d{5}$")


@pytest.fixture(scope="module")
def felagsvisar_rows(http):
    r = http.get(FELAGSVISAR)
    assert r.status_code == 200, f"{FELAGSVISAR} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]

    rows = parse_page(r.text)
    assert rows, (
        f"no tab panes parsed from {FELAGSVISAR} — a Webflow re-render would "
        f"break _TAB_PANE_RE and empty the catalog"
    )
    return rows


def test_felagsvisar_page_yields_indicators(felagsvisar_rows):
    # Loose floor: the catalog spans dozens of indicators across all sections.
    # This tolerates Hagstofa retiring indicators, not an empty crawl.
    assert len(felagsvisar_rows) >= 10, f"only {len(felagsvisar_rows)} indicators parsed"
    assert all(r["indicator"] for r in felagsvisar_rows), "an indicator pane has no name"


def test_indicators_still_link_px_web_tables(felagsvisar_rows):
    """The whole point of the catalog: indicator → PX-Web table code."""
    with_px = [r for r in felagsvisar_rows if r["px_tables"]]
    assert with_px, (
        f"no indicator on {FELAGSVISAR} links a px.hagstofa.is table — either "
        f"_PX_URL_RE stopped matching or the links moved"
    )

    codes = {c for r in with_px for c in r["px_tables"].split("|") if c}
    assert codes, "px_tables populated but _px_code() extracted nothing"
    bad = [c for c in codes if not _PX_CODE_RE.match(c)]
    assert not bad, f"malformed PX table codes: {bad}"


def test_velsaeldarvisar_subpage_is_served_and_parses(http):
    """The nested /velsaeldarvisar/<dimension> URL shape — one page, not all."""
    r = http.get(VELSAELD)
    assert r.status_code == 200, f"{VELSAELD} -> {r.status_code}"

    rows = parse_page(r.text)
    assert rows, f"no tab panes parsed from {VELSAELD} — _TAB_PANE_RE no longer matches"
    assert any(r["px_tables"] for r in rows), f"{VELSAELD}: no PX-Web tables linked"

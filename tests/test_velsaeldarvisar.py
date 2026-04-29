"""Tests for scripts/velsaeldarvisar.py.

Two layers:
  - Fast unit tests: parser exercised against an inline HTML fixture that
    mirrors the live Webflow structure. No network.
  - Slow integration tests: hit live visar.hagstofa.is. Gated behind `slow`.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from scripts import velsaeldarvisar as vv


# --------------------------------------------------------------------------
# Fixture: minimal HTML mirroring the live Webflow structure
# --------------------------------------------------------------------------

_FIXTURE_HTML = """
<html><body>
<div data-w-tab="Hagkerfið" class="w-tab-pane w--tab-active">
  <p>Parent category content (ignored).</p>
</div>
<div data-w-tab="Skuldastaða heimila" class="tab-pane-xyz w-tab-pane">
  <span class="text-span">Stutt lýsing</span><br/>Skuldir heimila sem hlutfall af tekjum.<br/>
  <span class="text-span-3">Eining</span><br/>Hlutfall í %.<br/>
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__lifskjor__5_skuldastada_heimili__1_skuldir_eignir/THJ09000.px">Skuldir</a>
  <a href="https://hagstofas3bucket.hagstofa.is/hagstofan/media/public/2024/abc.pdf">metadata</a>
</div>
<div data-w-tab="Atvinnuleysi" class="tab-pane-abc w-tab-pane">
  <span class="text-span">Stutt lýsing</span><br/>Skráð atvinnuleysi.<br/>
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__vinnumarkadur__vinnumarkadsrannsokn__1_manadartolur/VIN00001.px">A</a>
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__vinnumarkadur__vinnumarkadsrannsokn__1_manadartolur/VIN00002.px">B</a>
</div>
<div data-w-tab="Atvinna" class="w-tab-pane">
  <p>Another parent (ignored).</p>
</div>
<div data-w-tab="Starfsánægja" class="tab-pane-qwe w-tab-pane">
  <p>No PX links here — only Eurostat.</p>
  <a href="https://ec.europa.eu/eurostat/databrowser/view/abc">Eurostat</a>
</div>
</body></html>
"""


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_pages_list_is_well_formed():
    """Every PAGES entry is a (section, slug, url) tuple pointing at visar.hagstofa.is."""
    assert len(vv.PAGES) >= 1
    seen: set[tuple[str, str]] = set()
    for section, slug, url in vv.PAGES:
        assert section and slug
        assert (section, slug) not in seen, f"duplicate page: {section}/{slug}"
        seen.add((section, slug))
        assert url.startswith("https://visar.hagstofa.is/"), url


def test_px_code_extracts_canonical_code():
    assert vv._px_code(
        "https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__lifskjor__5_skuldastada_heimili__1_skuldir_eignir/THJ09000.px"
    ) == "THJ09000"
    # Lowercase URL still yields upper-case code (consistency)
    assert vv._px_code(
        "https://px.hagstofa.is/pxis/pxweb/is/samfelag/x/vin00001.px"
    ) == "VIN00001"


def test_parse_page_finds_expected_indicators():
    rows = vv.parse_page(_FIXTURE_HTML)
    # 3 indicators (parent tabs Hagkerfið/Atvinna are skipped)
    names = [r["indicator"] for r in rows]
    assert names == ["Skuldastaða heimila", "Atvinnuleysi", "Starfsánægja"]


def test_parse_page_extracts_px_codes_in_order():
    rows = vv.parse_page(_FIXTURE_HTML)
    by_name = {r["indicator"]: r for r in rows}
    assert by_name["Skuldastaða heimila"]["px_tables"] == "THJ09000"
    assert by_name["Atvinnuleysi"]["px_tables"] == "VIN00001|VIN00002"
    # Indicator with no PX links still yields an empty px_tables column
    assert by_name["Starfsánægja"]["px_tables"] == ""


def test_parse_page_attaches_running_category():
    rows = vv.parse_page(_FIXTURE_HTML)
    by_name = {r["indicator"]: r for r in rows}
    # Skuldastaða & Atvinnuleysi sit under Hagkerfið (the first parent we saw);
    # the parser then sees the Atvinna parent before Starfsánægja.
    assert by_name["Skuldastaða heimila"]["category"] == "Hagkerfið"
    assert by_name["Atvinnuleysi"]["category"] == "Hagkerfið"
    assert by_name["Starfsánægja"]["category"] == "Atvinna"


def test_parse_page_captures_description_and_unit():
    rows = vv.parse_page(_FIXTURE_HTML)
    by_name = {r["indicator"]: r for r in rows}
    assert "Skuldir heimila" in by_name["Skuldastaða heimila"]["short_description"]
    assert by_name["Skuldastaða heimila"]["unit"] == "Hlutfall í %."


def test_parse_page_captures_first_metadata_pdf():
    rows = vv.parse_page(_FIXTURE_HTML)
    by_name = {r["indicator"]: r for r in rows}
    assert by_name["Skuldastaða heimila"]["metadata_pdf"].endswith("/abc.pdf")
    assert by_name["Atvinnuleysi"]["metadata_pdf"] == ""  # no PDF in fixture


def test_raw_dir_under_data_raw():
    parts = vv.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert vv.RAW_DIR.name == "velsaeldarvisar"


# --------------------------------------------------------------------------
# Slow integration tests (live network)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_catalog_populates_expected_sections(tmp_path, monkeypatch):
    """End-to-end crawl. The live site must yield all three sections with
    at least one indicator each, and at least some PX table mappings."""
    monkeypatch.setattr(vv, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(vv, "PROCESSED_DIR", tmp_path / "processed")

    vv.cmd_fetch()

    csv_path = tmp_path / "processed" / "velsaeldarvisar_catalog.csv"
    assert csv_path.exists()
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sections = {r["section"] for r in rows}
    assert sections == {"velsaeldarvisar", "felagsvisar", "menningarvisar"}, sections

    # Every section has at least one indicator
    for s in sections:
        assert sum(1 for r in rows if r["section"] == s) > 0

    # At least 10 PX codes discovered overall — guards against a regex
    # regression that silently drops all px links.
    codes = {c for r in rows for c in (r["px_tables"] or "").split("|") if c}
    assert len(codes) >= 10, f"only {len(codes)} PX codes — parser likely broken"

    # All PX codes match the canonical Hagstofa pattern (3 letters + 5 digits).
    # Allow the known typo prefix `LFI` as well — it's a genuine source bug
    # documented in the skill; failing on it would be a false alarm.
    for c in codes:
        assert re.fullmatch(r"[A-Z]{3}\d{5}", c), f"malformed PX code: {c}"

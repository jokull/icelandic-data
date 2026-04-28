"""Tests for scripts/co2.py.

Fast unit tests exercise code parsing and extraction against an inline HTML
fixture that mirrors the live Webflow accordion structure (notably the
non-breaking-space quirk in "Upphaf /\xa0Endir"). The slow integration test
runs the full crawl against co2.is.
"""
from __future__ import annotations

import csv

import pytest

from scripts import co2


# --------------------------------------------------------------------------
# Fixture — minimal HTML mirroring one Webflow viðfangsefni page
# --------------------------------------------------------------------------

_FIXTURE = """
<html><body>
<div id="s5c1" class="adgerd-accordion">
  <div class="adgerd-number">
    <div class="label-big">S</div><div class="label-big">.</div>
    <div class="label-big">5</div><div class="label-big">.</div>
    <div class="label-big">C</div><div class="label-big">.</div>
    <div class="label-big">1</div>
  </div>
  <h3 class="text-small adgerd">Full orkuskipti ríkisflota og samgönguþjónustu fyrir 2030</h3>
  <div class="adgerd-expanded">
    <h3 class="title-6">Full orkuskipti ríkisflota og samgönguþjónustu fyrir 2030</h3>
    <div class="adgerd-body"><p class="text-small">Ríkið sé fyrirmynd í innkaupum.</p></div>
    <div class="adgerd-content"><div class="adgerd-body">
      <div class="adgerd-meta-item">
        <div class="label-big strong">Markmið aðgerðar</div>
        <div class="text-small">Full orkuskipti ríkisflota fyrir 2030</div>
      </div>
      <div class="adgerd-meta-item">
        <div class="label-big strong">Upphaf /\u00a0Endir</div>
        <div class="adgerd-meta-dates">
          <div class="text-small">2023</div><div>–</div><div class="text-small">2030</div>
        </div>
      </div>
      <div class="adgerd-meta-item">
        <div class="label-big strong">Staða aðgerðar</div>
        <div class="adgerd-status-wrapper">
          <div status-color="Í framkvæmd" class="status-color"></div>
          <div class="text-small">Í framkvæmd</div>
        </div>
      </div>
      <div class="adgerd-meta-item">
        <div class="label-big strong">Ábyrgðaraðili</div>
        <div class="text-small">Fjármála- og efnahagsráðuneyti</div>
      </div>
    </div></div>
  </div>
</div>
<div id="th2a3" class="adgerd-accordion">
  <div class="adgerd-expanded">
    <h3 class="title-6">Dæmi um þverlæga aðgerð með &quot;gæsalöppum&quot;</h3>
    <div class="adgerd-content"><div class="adgerd-body">
      <div class="adgerd-meta-item">
        <div class="label-big strong">Staða aðgerðar</div>
        <div><div status-color="Fyrirhugað" class="status-color"></div></div>
      </div>
      <div class="adgerd-meta-item">
        <div class="label-big strong">Ábyrgðaraðili</div>
        <div class="text-small">Forsætisráðuneyti</div>
      </div>
    </div></div>
  </div>
</div>
</body></html>
"""


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_parse_code_handles_s_prefix():
    assert co2._parse_code("s5c1") == ("S", "5", "C", "1")


def test_parse_code_handles_v_and_l():
    assert co2._parse_code("v1b2") == ("V", "1", "B", "2")
    assert co2._parse_code("l1a3") == ("L", "1", "A", "3")


def test_parse_code_handles_th_prefix_for_thorn():
    """th → Þ. The URL slug uses ASCII `th`; the canonical kerfi letter is Þ."""
    assert co2._parse_code("th2a3") == ("Þ", "2", "A", "3")


def test_parse_code_handles_two_digit_action_idx():
    """Some viðfangsefni have >9 actions (e.g. S.5.C.11)."""
    assert co2._parse_code("s5c11") == ("S", "5", "C", "11")


def test_strip_unescapes_html_entities():
    """Titles on the live site contain &quot;, &#39;, &amp;."""
    assert co2._strip("A &quot;B&quot; C") == 'A "B" C'
    assert co2._strip("x &amp; y") == "x & y"


def test_extract_action_pulls_all_fields_from_fixture():
    matches = list(co2._ACCORDION_SPLIT_RE.finditer(_FIXTURE))
    assert len(matches) == 2

    first_id = matches[0].group(1)
    first_end = matches[1].start()
    first_block = _FIXTURE[matches[0].end() : first_end]
    action = co2._extract_action(first_id, first_block)

    assert action["code"] == "S.5.C.1"
    assert action["kerfi"] == "S"
    assert action["title"].startswith("Full orkuskipti")
    assert action["markmid"].startswith("Full orkuskipti ríkisflota")
    assert action["upphaf"] == "2023"
    assert action["endir"] == "2030"
    assert action["stada"] == "Í framkvæmd"
    assert action["abyrgdaradili"] == "Fjármála- og efnahagsráðuneyti"


def test_extract_action_handles_html_entities_in_title():
    matches = list(co2._ACCORDION_SPLIT_RE.finditer(_FIXTURE))
    second_block = _FIXTURE[matches[1].end() :]
    action = co2._extract_action("th2a3", second_block)
    # &quot; must be decoded in the title
    assert '"gæsalöppum"' in action["title"]
    # Status still resolves via the status-color attribute
    assert action["stada"] == "Fyrirhugað"


def test_extract_action_handles_missing_start_end_years():
    """Actions without any Upphaf/Endir block should leave upphaf and endir blank."""
    matches = list(co2._ACCORDION_SPLIT_RE.finditer(_FIXTURE))
    second_block = _FIXTURE[matches[1].end() :]
    action = co2._extract_action("th2a3", second_block)
    assert action["upphaf"] == ""
    assert action["endir"] == ""


def test_raw_dir_under_data_raw():
    parts = co2.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert co2.RAW_DIR.name == "co2"


# --------------------------------------------------------------------------
# Slow integration test (live network)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_all_builds_substantive_catalog(tmp_path, monkeypatch):
    """End-to-end crawl. Iceland's climate plan has >100 numbered actions
    across all four kerfi (S, V, L, Þ). A regression that drops any kerfi
    entirely should trip this test."""
    monkeypatch.setattr(co2, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(co2, "PROCESSED_DIR", tmp_path / "processed")

    class Args:
        pass

    co2.cmd_fetch(Args())

    out = tmp_path / "processed" / "co2_actions.csv"
    assert out.exists()
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 90, f"only {len(rows)} actions — catalog may have changed shape"
    kerfi = {r["kerfi"] for r in rows}
    assert kerfi == {"S", "V", "L", "Þ"}, f"missing kerfi: {kerfi}"

    # Majority should have valid status and a start year
    with_status = sum(1 for r in rows if r["stada"])
    with_start = sum(1 for r in rows if r["upphaf"].isdigit())
    assert with_status / len(rows) > 0.95
    assert with_start / len(rows) > 0.90

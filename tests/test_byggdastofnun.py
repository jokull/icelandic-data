"""Tests for scripts/byggdastofnun.py.

Fast tests verify the seed catalog shape and the URL builder; slow tests
re-scrape the live site and assert parity with the seed.
"""
from __future__ import annotations

import csv
import re

import pytest

from scripts import byggdastofnun as bs


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_seed_catalog_covers_eleven_dashboards():
    """Byggdastofnun ships exactly eleven dashboards (2026-04 count). If the
    seed diverges from that, either a dashboard was added/removed upstream
    or we broke the list — either way run `fetch` and check."""
    assert len(bs.SEED_CATALOG) == 11


def test_seed_catalog_slugs_are_unique():
    slugs = [row["slug"] for row in bs.SEED_CATALOG]
    assert len(slugs) == len(set(slugs))


def test_seed_catalog_has_required_fields():
    required = {"slug", "title", "workbook", "view"}
    for row in bs.SEED_CATALOG:
        missing = required - row.keys()
        assert not missing, f"{row['slug']} missing: {missing}"
        for k in required:
            assert row[k], f"{row['slug']} has empty {k}"


def test_embed_url_points_at_tableau_public():
    url = bs.embed_url("tekjur", "tekjur")
    assert url.startswith("https://public.tableau.com/views/tekjur/tekjur")
    assert ":embed=true" in url


def test_page_url_structure():
    url = bs.page_url("ibuafjoldi-1-januar")
    assert url == "https://www.byggdastofnun.is/is/utgefid-efni/maelabord/ibuafjoldi-1-januar"


def test_tableau_view_regex_handles_amp_encoding():
    """The live HTML uses `&amp;` inside iframe src. After unescaping we
    should be able to extract workbook + view via the regex in scrape_one()."""
    sample = (
        '<iframe src="https://public.tableau.com/views/tekjur/tekjur?'
        ':language=en-GB&amp;:display_count=y&amp;publish=yes">'
    )
    m = bs._TABLEAU_VIEW_RE.search(sample)
    assert m is not None
    url = m.group(1).replace("&amp;", "&")
    parts = re.search(r"/views/([^/]+)/([^?]+)", url)
    assert parts is not None
    assert parts.group(1) == "tekjur"
    assert parts.group(2) == "tekjur"


def test_raw_dir_under_data_raw():
    parts = bs.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert bs.RAW_DIR.name == "byggdastofnun"


# --------------------------------------------------------------------------
# Slow integration test (live network)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_produces_parity_with_seed(tmp_path, monkeypatch):
    """Live fetch should produce the same 11 dashboards (at minimum the
    same slugs) as the seed catalog. Workbook/view names are allowed to
    drift over time — we only check slug presence."""
    monkeypatch.setattr(bs, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(bs, "PROCESSED_DIR", tmp_path / "processed")

    class Args:
        pass

    bs.cmd_fetch(Args())
    out = tmp_path / "processed" / "byggdastofnun_catalog.csv"
    assert out.exists()
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    slugs_live = {r["slug"] for r in rows}
    slugs_seed = {r["slug"] for r in bs.SEED_CATALOG}
    assert slugs_live == slugs_seed, (
        f"live catalog drifted: added={slugs_live - slugs_seed}, "
        f"removed={slugs_seed - slugs_live}"
    )

    # Every row has workbook + view + embed_url
    for r in rows:
        assert r["workbook"], f"empty workbook for {r['slug']}"
        assert r["view"], f"empty view for {r['slug']}"
        assert r["embed_url"].startswith("https://public.tableau.com/")

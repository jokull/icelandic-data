"""Tests for scripts/heimsmarkmid.py.

Fast unit tests verify constants + the code-parser. Slow integration tests
download the live ZIP and assert shape across all 17 SDG goals.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts import heimsmarkmid as hm


# --------------------------------------------------------------------------
# Fast unit tests
# --------------------------------------------------------------------------


def test_zip_url_points_at_github_pages():
    assert hm.ZIP_URL.startswith("https://hagstofan.github.io/")
    assert hm.ZIP_URL.endswith("/all_indicators.zip")


def test_raw_dir_under_data_raw():
    parts = hm.RAW_DIR.parts
    assert "data" in parts and "raw" in parts
    assert hm.RAW_DIR.name == "heimsmarkmid"


def test_parse_code_handles_three_segment_numeric():
    assert hm._parse_code("1-1-1") == ("1", "1", "1")
    assert hm._parse_code("10-3-1") == ("10", "3", "1")


def test_parse_code_handles_letter_targets():
    """Targets use letters for cross-cutting means-of-implementation
    indicators (e.g. 4-a-1 'education facilities', 16-b-1 'discrimination
    laws'). Parser must keep the letter as the target segment."""
    assert hm._parse_code("4-a-1") == ("4", "a", "1")
    assert hm._parse_code("16-b-1") == ("16", "b", "1")


def test_parse_code_handles_two_segment_fallback():
    # Some aggregate codes may lack the third segment; parser should not crash.
    goal, target, ind = hm._parse_code("1-a")
    assert goal == "1" and target == "a" and ind == ""


def test_parse_code_returns_code_itself_when_malformed():
    # Ensures build_catalog() doesn't crash on unexpected filenames that
    # might slip into the ZIP — we keep the raw stem in `goal` rather than
    # raising. Defensive because the ZIP is rebuilt nightly.
    goal, target, ind = hm._parse_code("unexpected_name")
    assert goal == "unexpected_name"


# --------------------------------------------------------------------------
# Slow integration tests (live network)
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_builds_catalog_covering_all_17_goals(tmp_path, monkeypatch):
    monkeypatch.setattr(hm, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(hm, "PROCESSED_DIR", tmp_path / "processed")

    class Args:
        force = False

    hm.cmd_fetch(Args())

    catalog_path = tmp_path / "processed" / "heimsmarkmid_catalog.csv"
    assert catalog_path.exists()
    with catalog_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Iceland's national framework has 100+ indicators across all 17 goals
    assert len(rows) >= 100, f"only {len(rows)} indicators — ZIP contract may have changed"

    goals = {r["goal"] for r in rows if r["goal"].isdigit()}
    expected = {str(i) for i in range(1, 18)}
    assert goals == expected, f"missing goals: {expected - goals}"

    # At least one indicator per goal has data
    has_data_per_goal = {r["goal"] for r in rows if r["n_rows"] and int(r["n_rows"]) > 0}
    assert has_data_per_goal == expected, f"no data for goals: {expected - has_data_per_goal}"


@pytest.mark.slow
def test_load_meta_returns_live_json():
    """The meta JSON is fetched over HTTP on demand; verify the contract."""
    meta = hm._load_meta("1-1-1")
    assert isinstance(meta, dict)
    # Both fields are populated in the Iceland open-sdg deployment.
    assert meta.get("indicator_name"), meta
    assert meta.get("computation_units"), meta
    assert meta["indicator_number"].startswith("1.1.1"), meta

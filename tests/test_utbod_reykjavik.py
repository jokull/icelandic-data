"""Offline tests for scripts/utbod_reykjavik.py parsing."""
from __future__ import annotations

from scripts.utbod_reykjavik import NULL_DATE, parse_fields, to_frame

FIELDS = [
    {"key": "Title", "value": "16209 - Ræsting fyrir grunnskóla Reykjavíkurborgar"},
    {"key": "Description", "value": "  um 47.200 m².  "},
    {"key": "Reference", "value": ""},
    {"key": "Award", "value": NULL_DATE},
    {"key": "Estimated Value", "value": ""},
    {"key": "CPV Code", "value": "98341130-5"},
    {"key": "Date documents can be requested until", "value": "2026-04-28T10:15:00"},
    {"key": "Something New", "value": "x"},
]


def test_parse_fields_maps_and_nulls():
    rec = parse_fields(1479, FIELDS)
    assert rec["title"].startswith("16209")
    assert rec["description"] == "um 47.200 m²."
    assert rec["award_date"] is None and rec["estimated_value"] is None
    assert rec["reference"] == "16209"  # fallback from title
    assert '"Something New"' in rec["extra_fields"]


def test_empty_project_is_none():
    assert parse_fields(9999, []) is None
    assert parse_fields(9999, [{"key": "Title", "value": ""}]) is None


def test_to_frame_types_and_dedupe():
    rec = parse_fields(1479, FIELDS)
    df = to_frame([rec, rec])
    assert df.height == 1
    assert str(df["docs_available_until"].dtype).startswith("Datetime")
    assert df["year"][0] == 2026
    assert "ræsting" in df["title"][0].lower()

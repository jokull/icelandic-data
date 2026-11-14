"""Offline tests for the HMS mánaðarskýrsla slug and sheet parsing."""

from __future__ import annotations

from datetime import datetime

import pytest

from scripts.hms_manadarskyrsla import sheet_table, slug_month


@pytest.mark.parametrize(
    ("slug", "month"),
    [
        ("manadarskyrsla-oktober-2026", "2026-10"),
        ("manadarskyrsla-agust-25", "2025-08"),
        ("https://hms.is/skyrslur/manadarskyrsla-januar-2026", "2026-01"),
    ],
)
def test_slug_month(slug, month):
    assert slug_month(slug) == month


def test_slug_month_rejects_other_reports():
    with pytest.raises(ValueError):
        slug_month("ibudir-i-byggingu-september-2026")


def test_sheet_table_drops_padding_and_formats_dates():
    rows = [
        ("Fjöldi auglýstra eigna", None, None, None),
        ("Dags.", "Landshlutaflokkun", "Fjöldi", None),
        (datetime(2017, 10, 1), "Nágrenni\nhöfuðborgarsvæðis", 375, None),
        (None, None, None, None),
        (datetime(2017, 11, 1), "Höfuðborgarsvæði", 1630, None),
    ]
    title, header, body = sheet_table(rows)
    assert title == "Fjöldi auglýstra eigna"
    assert header == ["Dags.", "Landshlutaflokkun", "Fjöldi"]
    assert body == [
        ["2017-10-01", "Nágrenni höfuðborgarsvæðis", "375"],
        ["2017-11-01", "Höfuðborgarsvæði", "1630"],
    ]


def test_sheet_table_names_unlabelled_columns_with_values():
    rows = [("T", None, None), ("Ár", "Íslandsbanki", None), (2026, -0.034, 0.5)]
    _, header, body = sheet_table(rows)
    assert header == ["Ár", "Íslandsbanki", "col3"]
    assert body == [["2026", "-0.034", "0.5"]]


def test_sheet_table_skips_subtitle_row():
    rows = [("Spár", None, None), ("Magnbreytingar, %", None, None), ("Banki", 2026, 2027), ("Arion banki", -0.082, -0.12)]
    _, header, body = sheet_table(rows)
    assert header == ["Banki", "2026", "2027"]
    assert body == [["Arion banki", "-0.082", "-0.12"]]


def test_sheet_table_without_header_row():
    rows = [("Hlutfall undir 80 m²", None), ("Ísland", 0.232), ("Noregur", 0.2962)]
    _, header, body = sheet_table(rows)
    assert header == ["col1", "col2"]
    assert body == [["Ísland", "0.232"], ["Noregur", "0.2962"]]

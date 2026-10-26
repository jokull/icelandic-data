"""Offline tests for scripts/tekjusagan.py — body overrides and row tidying.

The live API contract is covered by tests/health/test_tekjusagan.py.
"""
from __future__ import annotations

import pytest

from scripts import tekjusagan as tk


def _row(year, label, isk=None, pct=None, order=1):
    return {
        "Skattár": year,
        "Breyta Heiti": f"{label} ISK",
        "Breyta Lýsing": label,
        "Breyta Röðun": order,
        "Breytugildi ISK": isk,
        "Breytugildi Prósenta": pct,
    }


def test_breyta_is_only_sent_where_the_procedure_takes_it():
    """The backend 400s on an extra parameter, and the SPA strips Breyta
    everywhere but radstofun — the defaults must match."""
    for slug, s in tk.SERIES.items():
        assert ("Breyta" in s["body"]) == (slug == "radstofun"), slug


def test_parse_overrides_splits_lists_on_pipe():
    assert tk.parse_overrides(["Tekjubil=Tekjubil 10", "Breyta=A|B"]) == {
        "Tekjubil": "Tekjubil 10",
        "Breyta": ["A", "B"],
    }


def test_parse_overrides_rejects_missing_equals():
    with pytest.raises(SystemExit):
        tk.parse_overrides(["Tekjubil"])


def test_tidy_drops_header_rows_and_carries_filters():
    items = [
        _row(2024, "Atvinnutekjur", isk=1_698_994.74),
        _row(2024, "Tímabil 2007 - 2012", pct=-0.031, order=20),
        _row(2024, "Ráðstöfunartekjur fasteignaeigenda", order=99),  # header: both null
    ]
    df = tk.tidy(items, "radstofun", tk.SERIES["radstofun"]["body"])
    assert df["label"].to_list() == ["Atvinnutekjur", "Tímabil 2007 - 2012"]
    assert df["growth_rate"].to_list() == [None, -0.031]
    assert set(df["Hjúskaparstaða"]) == {"Hjón"}
    assert "Breyta" not in df.columns


def test_tidy_dedupes_on_natural_key_keeping_last():
    items = [_row(2024, "Atvinnutekjur", isk=1.0), _row(2024, "Atvinnutekjur", isk=2.0)]
    df = tk.tidy(items, "radstofun", {})
    assert df["value_isk"].to_list() == [2.0]

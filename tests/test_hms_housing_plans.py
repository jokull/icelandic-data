"""Offline tests for the HMS húsnæðisáætlanir parser (scripts/hms_housing_plans.py).

Builds a minimal workbook with the same sheet layout as the real annual
`husnaedisaaetlanir_<year>_gogn.xlsx`, then asserts the parser produces the
tidy outputs. No network, no real data file.
"""
from __future__ import annotations

import openpyxl
import polars as pl

from scripts.hms_housing_plans import (
    parse_completions_and_need,
    parse_plot_availability,
    parse_waitlist,
)


def _build_workbook(path):
    wb = openpyxl.Workbook()

    # Sheet 2.1 — completions + forecast band; first column has no header.
    ws = wb.active
    ws.title = "2.1"
    ws.append([None, "Fjöldi fullbúinna íbúða", "Miðspá", "Spábil neðri mörk", "Spábil efri mörk"])
    for year, done, mid, lo, hi in [
        (2020, 3816, None, None, None),
        (2021, 3220, None, None, None),
        (2022, 2885, None, None, None),
        (2023, 3458, 3928, 2869, 4943),
        (2024, 3637, 4134, 2900, 5161),
        (2025, 3371, 3957, 2503, 5152),
    ]:
        ws.append([year, done, mid, lo, hi])

    # Sheet 3.1 — national real need.
    ws = wb.create_sheet("3.1")
    ws.append(["Allt landið", "Raunveruleg þörf - neðri mörk", "Raunveruleg þörf - efri mörk"])
    for year, lo, hi in [(2023, 4473.3878, 5532.3629), (2024, 3857.5134, 4752.9077), (2025, 2441.5079, 2696.8176)]:
        ws.append([year, lo, hi])

    # Sheet 3.2 — capital-area real need.
    ws = wb.create_sheet("3.2")
    ws.append(["Höfuðborgarsvæðið", "Raunveruleg þörf - neðri mörk", "Raunveruleg þörf - efri mörk"])
    for year, lo, hi in [(2023, 2917.3607, 3810.3358), (2024, 2441.6040, 3008.6948), (2025, 1378.3435, 1537.0766)]:
        ws.append([year, lo, hi])

    # Sheet 4.2 — plot availability by region.
    ws = wb.create_sheet("4.2")
    ws.append([None, "Hlutfall byggingarhæfra lóða af íbúðaþörf 2025"])
    for region, ratio in [("Vesturland", 2.53), ("Höfuðborgarsvæði", 0.58), ("Austurland", 0.03)]:
        ws.append([region, ratio])

    # Sheet 5.2 — waitlists; row 0 title, row 1 header.
    ws = wb.create_sheet("5.2")
    ws.append(["Biðlistar eftir leiguíbúðum utan markaðsleigu skv. húsnæðisáætlunum"])
    ws.append(["Búsetuform", 2022, 2023, 2024, 2025])
    for cat, w22, w23, w24, w25 in [
        ("Leiguíbúðir fyrir tekju- og eignalága", 1923, 3265, 3821, 3871),
        ("Búseturéttaríbúðir", 42, 183, 110, 32),
        ("Félagslegar íbúðir ", 1369, 1756, 1704, 1570),
        ("Samtals", 5215, 6881, 7259, 6864),
    ]:
        ws.append([cat, w22, w23, w24, w25])

    wb.save(path)
    return path


def test_completions_and_need_merges_sheets(tmp_path):
    xlsx = _build_workbook(tmp_path / "husnaedisaaetlanir_2026_gogn.xlsx")

    df = parse_completions_and_need(xlsx)

    # Rows: 2.1 (2020-2025) full-joined with 3.1/3.2 (2023-2025).
    assert sorted(df["year"].to_list()) == [2020, 2021, 2022, 2023, 2024, 2025]

    row = df.filter(pl.col("year") == 2020).row(0, named=True)
    assert row["completed_national"] == 3816
    assert row["forecast_mid_national"] is None

    row = df.filter(pl.col("year") == 2023).row(0, named=True)
    assert row["completed_national"] == 3458
    assert row["forecast_mid_national"] == 3928
    assert abs(row["real_need_low_national"] - 4473.3878) < 0.01
    assert abs(row["real_need_low_capital"] - 2917.3607) < 0.01

    # Pre-2023 rows have no real need values.
    no_need = df.filter(pl.col("year") == 2021).row(0, named=True)
    assert no_need["real_need_low_national"] is None


def test_waitlist_is_long_and_mapped(tmp_path):
    xlsx = _build_workbook(tmp_path / "husnaedisaaetlanir_2026_gogn.xlsx")

    df = parse_waitlist(xlsx)

    # 4 categories x 4 years in long format.
    assert df.height == 16

    total = df.filter(pl.col("category_en") == "Total").sort("year")
    assert total["waitlist"].to_list() == [5215, 6881, 7259, 6864]

    # Trailing-space category maps to the English label.
    social = df.filter(pl.col("category") == "Félagslegar íbúðir ")
    assert set(social["category_en"].to_list()) == {"Social apartments"}


def test_plot_availability_regions(tmp_path):
    xlsx = _build_workbook(tmp_path / "husnaedisaaetlanir_2026_gogn.xlsx")

    df = parse_plot_availability(xlsx)

    assert "region" in df.columns and "plot_to_need_ratio" in df.columns
    assert df.height == 3
    assert df.row(0, named=True)["region"] == "Vesturland"


def test_plot_need_year_is_read_from_the_workbook(tmp_path):
    p=_build_workbook(tmp_path/'next.xlsx')
    wb=openpyxl.load_workbook(p);wb['4.2']['B1']='Hlutfall byggingarhæfra lóða af íbúðaþörf 2027';wb.save(p)
    assert parse_plot_availability(p)['need_year'].to_list()==[2027]*3


def test_completions_consumer_keeps_history_and_excludes_forecasts(tmp_path,monkeypatch):
    import argparse
    from scripts import housing_completions as m
    p=tmp_path/'hms.csv';p.write_text('year,completed_national\n2025,3400\n2026,\n',encoding='utf-8')
    monkeypatch.setattr(m,'HMS_PROCESSED',p);monkeypatch.setattr(m,'DST',tmp_path/'merged.csv')
    monkeypatch.setattr(m,'fetch_hagstofan',lambda:{y:100 for y in range(1970,2022)})
    assert m.cmd_fetch(argparse.Namespace(use_cached=False))==0
    rows=dict(pl.read_csv(m.DST).select('year','completions').iter_rows())
    assert rows[2020]==3816 and rows[2025]==3400 and 2026 not in rows


def test_invalid_present_completions_file_does_not_fall_back(tmp_path,monkeypatch):
    import pytest
    from scripts import housing_completions as m
    p=tmp_path/'hms.csv';monkeypatch.setattr(m,'HMS_PROCESSED',p)
    for content in ['year,completed_national\n2025,\n','year,completed_national\n2025,3.5\n','year,completed_national\n2025,1\n2025,2\n']:
        p.write_text(content, encoding='utf-8')
        with pytest.raises(ValueError):m.load_hms_completions()

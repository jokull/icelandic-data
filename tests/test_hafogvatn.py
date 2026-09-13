import polars as pl
from scripts.hafogvatn import mark_projections


def test_mark_projections_flags_assessment_year_and_landings_null():
    df = pl.DataFrame({"Year": [2024, 2025, 2026, 2027], "Landings": [220340, 218683, None, None]})
    out = mark_projections(df, 2026)
    assert out["is_projection"].to_list() == [False, False, True, True]


def test_mark_projections_landings_null_alone_is_a_projection():
    df = pl.DataFrame({"Year": [2025], "Landings": [None]}).with_columns(pl.col("Landings").cast(pl.Int64))
    assert mark_projections(df, 2026)["is_projection"].to_list() == [True]

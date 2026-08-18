"""Health probe — Hagstofan TEK01001 (income by source, age, gender).

scripts/income_distribution.py fetches TEK01001 five times with different
filters plus TEK01006/07 for the distribution CSVs. The stable contract is the
TEK01001 table itself: served, with the dimensions the filters name, and a
core query (kyn=0 all, aldur=Y25-54, eining=0 mean) still returning total
income ("Heildartekjur", code 0) for a fixed year.
"""
from __future__ import annotations

BASE = "https://px.hagstofa.is/pxis/api/v1/is"
TABLE = f"{BASE}/Samfelag/launogtekjur/3_tekjur/1_tekjur_skattframtol/TEK01001.px"


def test_table_metadata_has_expected_dimensions(http):
    r = http.get(TABLE)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    assert "variables" in meta, f"no 'variables' key; got {sorted(meta)}"
    codes = {v["code"] for v in meta["variables"]}
    assert {"Tekjur og skattar", "Eining", "Kyn", "Aldur", "Ár"} <= codes, (
        f"expected income dims, got {sorted(codes)}"
    )


def test_income_query_returns_data(http):
    """POST the script's core query — mean total income, 25–54, all genders."""
    r = http.post(
        TABLE,
        json={
            "query": [
                {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
                {"code": "Aldur", "selection": {"filter": "item", "values": ["Y25-54"]}},
                {"code": "Eining", "selection": {"filter": "item", "values": ["0"]}},
                {"code": "Ár", "selection": {"filter": "item", "values": ["2020"]}},
            ],
            "response": {"format": "json"},
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    # One row per income type (Tekjur og skattar 0–5): total, earned, capital,
    # other, taxes, disposable. A lone row means the dimension collapsed.
    assert len(payload["data"]) >= 2, f"expected income-type rows, got {payload['data']}"

    total = payload["data"][0]
    assert total["key"][0] == "0", f"expected Heildartekjur row first, got {total}"

    v = float(total["values"][0])
    # Thousands of ISK: mean total income for 25–54 has stayed ~2k–15k since
    # 1990; 2020 was 8,080. The bound catches unit/NaN drift without pinning
    # Hagstofan revisions.
    assert 1_000 < v < 100_000, f"mean total income implausible: {v}"

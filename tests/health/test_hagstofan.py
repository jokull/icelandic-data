"""Health probe — Hagstofa Íslands PX-Web API.

Contract: browse the catalog, read one table's metadata, and POST one small
filtered query. Together these cover the three call shapes every hagstofan_*.py
script makes.
"""
from __future__ import annotations

BASE = "https://px.hagstofa.is/pxis/api/v1/is"

# Key GDP figures 1945+ — a stable, decades-old table.
TABLE = f"{BASE}/Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/THJ01000.px"

# State-treasury balance 1980-2025 — fills the pre-2015 gap in the
# ríkisreikningur API (2015+ only). Fetched by scripts/hagstofan_rikissjod.py.
RIKISSJOD_TABLE = f"{BASE}/Efnahagur/fjaropinber/fjarmal_rikissjods/THJ05211.px"


def test_catalog_is_browsable(http):
    r = http.get(f"{BASE}/")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    catalog = r.json()
    assert isinstance(catalog, list) and catalog, "catalog is empty"
    ids = {entry["dbid"] for entry in catalog}
    # The categories the scripts navigate into. If these are renamed, every
    # hardcoded table path in the repo is already broken.
    assert {"Efnahagur", "Ibuar"} <= ids, f"expected categories missing, got {sorted(ids)}"


def test_table_metadata_has_expected_dimensions(http):
    r = http.get(TABLE)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    assert "variables" in meta, f"no 'variables' key; got {sorted(meta)}"
    codes = {v["code"] for v in meta["variables"]}
    assert "Ár" in codes, f"expected 'Ár' dimension, got {sorted(codes)}"


def test_small_query_returns_data(http):
    """POST the smallest useful query rather than pulling the whole table."""
    r = http.post(
        TABLE,
        json={
            "query": [
                {"code": "Ár", "selection": {"filter": "item", "values": ["2020"]}}
            ],
            "response": {"format": "json"},
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert "data" in payload, f"no 'data' key; got {sorted(payload)}"
    assert payload["data"], "query returned zero rows"

    first = payload["data"][0]
    assert "key" in first and "values" in first, f"unexpected row shape: {first}"


def test_rikissjod_table_exists(http):
    """THJ05211 carries the pre-2015 state budget balance (API is 2015+ only)."""
    r = http.get(RIKISSJOD_TABLE)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    codes = {v["code"] for v in meta["variables"]}
    assert {"Skipting", "Ár"} <= codes, f"expected Skipting/Ár dims, got {sorted(codes)}"


def test_rikissjod_2008_crisis_balance(http):
    """Contract value: the 2008 state-treasury deficit exceeded 100 bn ISK.

    Structural drift (renamed table, reordered rows, NaN) surfaces here; a
    Hagstofan revision of the exact figure stays within the bound.
    """
    r = http.post(
        RIKISSJOD_TABLE,
        json={
            "query": [
                {"code": "Skipting", "selection": {"filter": "item", "values": ["2"]}},
                {"code": "Ár", "selection": {"filter": "item", "values": ["2008"]}},
            ],
            "response": {"format": "json"},
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert payload["data"], "query returned zero rows"
    row = payload["data"][0]
    assert row["key"][0] == "2", f"expected Tekjuafgangur/-halli row, got {row}"
    v = row["values"][0]
    assert v is not None, "2008 balance is missing"
    v = float(v)
    assert v < -100000, f"2008 afkoma should be a >100 bn deficit (m.kr), got {v}"

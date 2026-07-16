"""Health probe — Hagstofa Íslands PX-Web API.

Contract: browse the catalog, read one table's metadata, and POST one small
filtered query. Together these cover the three call shapes every hagstofan_*.py
script makes.
"""
from __future__ import annotations

BASE = "https://px.hagstofa.is/pxis/api/v1/is"

# Key GDP figures 1945+ — a stable, decades-old table.
TABLE = f"{BASE}/Efnahagur/thjodhagsreikningar/landsframl/1_landsframleidsla/THJ01000.px"


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

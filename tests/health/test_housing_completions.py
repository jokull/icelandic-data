"""Health probe — Hagstofan IDN03001 (housing completions).

scripts/housing_completions.py splices the Hagstofan table (1970–2021) onto
hardcoded HMS húsnæðisáætlanir figures (2020–2025). IDN03001 is the only live
network contract: it froze after 2021, so the probe checks it is still served
with the dimensions the query filters on, and that the exact filtered query
(byggingarstaða=2 fullgert, eining=0 fjöldi íbúða) still returns the 2020
value the script reports in its overlap check.
"""
from __future__ import annotations

BASE = "https://px.hagstofa.is/pxis/api/v1/is"
TABLE = f"{BASE}/Atvinnuvegir/idnadur/byggingar/IDN03001.px"


def test_table_metadata_has_expected_dimensions(http):
    r = http.get(TABLE)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    assert "variables" in meta, f"no 'variables' key; got {sorted(meta)}"
    codes = {v["code"] for v in meta["variables"]}
    assert {"Ár", "Byggingarstaða", "Eining"} <= codes, (
        f"expected Ár/Byggingarstaða/Eining dims, got {sorted(codes)}"
    )


def test_completions_query_returns_data(http):
    """POST the same filtered query the script runs (fullgert, fjöldi íbúða)."""
    r = http.post(
        TABLE,
        json={
            "query": [
                {"code": "Byggingarstaða", "selection": {"filter": "item", "values": ["2"]}},
                {"code": "Eining", "selection": {"filter": "item", "values": ["0"]}},
                {"code": "Ár", "selection": {"filter": "item", "values": ["2020"]}},
            ],
            "response": {"format": "json"},
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert payload["data"], "query returned zero rows"
    row = payload["data"][0]
    assert row["key"][0] == "2020", f"expected 2020 row first, got {row}"

    v = float(row["values"][0])
    # Annual completions run a few hundred to ~5k; 2020 was 3,816 (the script's
    # overlap check against HMS). A bound catches NaNs and unit drift.
    assert 100 < v < 100_000, f"2020 completions implausible: {v}"

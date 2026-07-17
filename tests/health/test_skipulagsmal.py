"""Health probe — Planitor planning/building-permit API.

Contract: `GET /api/minutes/search` answers a keyword+date-window query with a
paginated `items` envelope, and each item still carries the fields
scripts/skipulagsmal.py reads:

  - `council`     — the Reykjavík filter (REYKJAVIK_COUNCILS) keys off this
  - `case_address` — the deduplication key
  - `inquiry` / `remarks` — the text the stage/outcome classifiers regex over

The script paginates 12 years × 7 building types; this probe asks for one
month, one keyword, `limit=5`. Same call shape, ~1/1000th of the traffic.
"""
from __future__ import annotations

from scripts.skipulagsmal import BASE, BUILDING_TYPES, REYKJAVIK_COUNCILS

# A month with dense Reykjavík activity, using the script's own keyword.
PARAMS = {
    "q": BUILDING_TYPES[0][1],  # "fjölbýlishús"
    "after": "2025-01-01",
    "before": "2025-02-01",
    "limit": 5,
    "offset": 0,
}


def test_search_returns_paginated_envelope(http):
    r = http.get(BASE, params=PARAMS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    # fetch_all() reads `items` and compares len(batch) against the limit to
    # decide whether to advance the offset — both halves must exist.
    assert "items" in payload, f"no 'items' key; got {sorted(payload)}"
    assert payload["items"], f"{r.request.url} returned zero minutes for a known-busy month"


def test_item_carries_the_fields_the_script_reads(http):
    r = http.get(BASE, params=PARAMS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    item = r.json()["items"][0]
    required = {"council", "case_address", "inquiry", "remarks"}
    missing = required - set(item)
    assert not missing, (
        f"{r.request.url} -> 200 but minute is missing {sorted(missing)} — "
        f"skipulagsmal.py's filter/dedup/classify would silently produce empty "
        f"columns. Got: {sorted(item)}"
    )


def test_reykjavik_council_names_still_match(http):
    """The Reykjavík filter is an exact string match against REYKJAVIK_COUNCILS.

    If Planitor ever re-labels a council, fetch_all() keeps returning 200 and
    silently filters *everything* out — a zero-row dataset with no error. This
    is the assertion that catches that.
    """
    r = http.get(BASE, params=PARAMS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    seen = {i.get("council") for i in r.json()["items"]}
    assert seen & REYKJAVIK_COUNCILS, (
        f"{r.request.url} -> 200 but no council matched REYKJAVIK_COUNCILS "
        f"({sorted(REYKJAVIK_COUNCILS)}); saw {sorted(c for c in seen if c)}"
    )

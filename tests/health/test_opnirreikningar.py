"""Health probe — opnirreikningar.is (Open Accounts of the State).

There is no documented API here: the site is a DataTables front end and
scripts/opnirreikningar.py drives its AJAX endpoints directly. That makes the
request *shape* the fragile part, so this probes all three endpoints the script
uses, built with the script's own URL builder:

  1. /rest/org      — org name → org_id, the input to every fetch
  2. /rest/vendor   — vendor name → kennitala
  3. /data_pagination_search — the DataTables endpoint _paginate() walks

Quirk worth knowing before you "fix" an assertion: /rest/org and /rest/vendor
return JSON with `Content-Type: text/html`, while /data_pagination_search
returns `application/json`. So the two rest endpoints are checked by parsing
the body, not by content type.

The search probe pins a closed historical window (Jan 2024, Veðurstofa) with
length=5 — one page, no pagination, a result set that cannot drift. It is not a
freshness check; it asks whether the endpoint still answers in the shape
fetch() unpacks.
"""
from __future__ import annotations

import pytest

from scripts.opnirreikningar import (
    BASE_URL,
    CSV_FIELDS,
    HEADERS,
    _build_search_url,
    _to_dd_mm_yyyy,
)

# Veðurstofa Íslands — a long-lived org with steady invoice traffic.
ORG_ID = "14412"
ORG_TERM = "Veðurstofa"


def test_org_lookup_resolves_a_known_org(http):
    url = f"{BASE_URL}/rest/org"
    r = http.get(url, params={"term": ORG_TERM}, headers=HEADERS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    # NB: this endpoint declares text/html but returns JSON.
    payload = r.json()
    data = payload.get("data")
    assert data, f"{r.request.url}: no 'data' in {sorted(payload)}"
    assert {"id", "text"} <= set(data[0]), f"unexpected org shape: {data[0]}"

    ids = {item["id"] for item in data}
    assert ORG_ID in ids, (
        f"{r.request.url}: org_id {ORG_ID} (Veðurstofa Íslands) no longer resolves — "
        f"org IDs may have been renumbered; got {sorted(ids)}"
    )


def test_vendor_lookup_returns_kennitala_ids(http):
    url = f"{BASE_URL}/rest/vendor"
    r = http.get(url, params={"term": "N1"}, headers=HEADERS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    data = r.json().get("data")
    assert data, f"{r.request.url}: vendor search returned nothing"
    assert {"id", "text"} <= set(data[0]), f"unexpected vendor shape: {data[0]}"
    # Vendor ids are kennitölur — 10 digits. fetch --vendor passes them straight
    # through, so a format change breaks the filter silently.
    assert any(item["id"].isdigit() and len(item["id"]) == 10 for item in data), (
        f"{r.request.url}: no 10-digit kennitala among vendor ids "
        f"{[i['id'] for i in data]}"
    )


@pytest.fixture(scope="module")
def search_rows(http):
    """One page of a closed historical window — never the full pagination."""
    url = _build_search_url(
        org_id=ORG_ID,
        fra=_to_dd_mm_yyyy("2024-01-01"),
        til=_to_dd_mm_yyyy("2024-01-31"),
        start=0,
        length=5,
    )
    r = http.get(url, headers=HEADERS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json"), r.headers["content-type"]

    payload = r.json()
    assert "data" in payload, f"no 'data' key; got {sorted(payload)}"
    assert payload["data"], (
        "search for Veðurstofa invoices in Jan 2024 returned zero rows — a "
        "closed historical window should never empty out"
    )
    return payload["data"]


def test_search_rows_carry_every_field_the_csv_needs(search_rows):
    row = search_rows[0]
    missing = set(CSV_FIELDS) - set(row)
    assert not missing, f"invoice row lost fields {sorted(missing)}; got {sorted(row)}"


def test_search_rows_carry_the_dedup_key(search_rows):
    """_paginate() dedupes on unique_id and stops when a page adds nothing new.
    Without it, pagination would loop or emit duplicates rather than fail."""
    row = search_rows[0]
    assert row.get("unique_id"), f"no unique_id on invoice row: {sorted(row)}"
    assert len({r["unique_id"] for r in search_rows}) == len(search_rows), (
        "unique_id is not unique within a single page"
    )


def test_invoice_amounts_are_plausible(search_rows):
    """top-vendors sums invoice_amount. The API has shipped it both as int and
    as a formatted string, which is why the script coerces — assert only that
    it is one of those, not which."""
    for row in search_rows:
        amount = row["invoice_amount"]
        assert isinstance(amount, (int, float, str)), (
            f"invoice_amount is {type(amount).__name__}: {amount!r}"
        )
        assert row["check_date"], f"row has no check_date: {row}"

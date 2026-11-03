"""Health probe — Reykjavík procurement portal (utbod.reykjavik.is → In-Tend).

scripts/utbod_reykjavik.py relies on two unauthenticated JSON endpoints of the
In-Tend SPA backend. The fragile parts are the endpoint paths, the POST body
shape of GetTendersList, and the English field labels that parse_fields() maps.
Project 1559 (16338 Ræsting stjórnsýsluhúsa, 2026) is a closed historical notice
and should keep answering the same way.
"""
from __future__ import annotations

from scripts.utbod_reykjavik import BASE, FIELD_MAP, parse_fields

KNOWN_PROJECT = 1559


def test_current_tenders_list(http):
    url = f"{BASE}/Tenders/GetTendersList"
    r = http.post(
        url,
        params={"list": "current", "customerId": -1},
        json={"page": 0, "orderBy": "", "orderByDescending": False, "pageLength": 5, "SearchText": ""},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    payload = r.json()
    assert {"totalResults", "data"} <= set(payload), f"unexpected shape: {sorted(payload)}"
    for row in payload["data"]:
        assert "projectID" in row and "title" in row, f"unexpected row keys: {sorted(row)}"


def test_project_fields_by_id(http):
    url = f"{BASE}/Tenders/GetProjectFields"
    r = http.get(url, params={"summary": "false", "projectId": KNOWN_PROJECT, "lng": "en-GB"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    fields = r.json()
    keys = {f["key"] for f in fields}
    missing = {"Title", "Reference", "CPV Code", "Date documents can be requested until"} - keys
    assert not missing, f"{r.request.url}: labels changed, missing {missing}; got {sorted(keys)}"
    unmapped = keys - set(FIELD_MAP)
    assert not unmapped, f"new unmapped labels {unmapped}"
    rec = parse_fields(KNOWN_PROJECT, fields)
    assert rec and rec["reference"] == "16338", f"unexpected record {rec}"

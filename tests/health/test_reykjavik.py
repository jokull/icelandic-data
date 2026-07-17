"""Health probe — Reykjavíkurborg open data.

The skill covers two unrelated services that fail independently, so both are
probed:

  1. CKAN at gagnagatt.reykjavik.is — the catalog, and the `arsuppgjor` dataset
     (Opin Fjármál: vendor-level A-part spending). Resource download URLs carry
     a per-file UUID that changes every time the city republishes, so the
     documented curl URLs go stale by design — the durable contract is
     `package_show?id=arsuppgjor` still resolving and still listing CSVs. This
     probe therefore discovers the resource rather than hard-coding it.
  2. PX-Web at velstat.reykjavik.is — welfare statistics, GET metadata +
     POST query, the same call shape as the hagstofan probe.

Payloads stay small: the arsuppgjor CSVs run ~94k rows a year, so the schema
check is a Range request for the header, never the file.
"""
from __future__ import annotations

import pytest

CKAN = "https://gagnagatt.reykjavik.is/api/3/action"
PXWEB = "https://velstat.reykjavik.is/PxWeb/api/v1/is/VELSTAT"

# Population by district and nationality, 2010–2022 — a closed, stable table.
PX_TABLE = f"{PXWEB}/200. Arsskyrsla/11 Mannfjoldi/VEL11008.px"

# Columns the skill's DuckDB queries and every downstream analysis rely on.
UPPGJOR_COLUMNS = {
    "fyrirtaeki",   # fund
    "samtala1",     # division (svið)
    "samtala0",     # unit
    "tegund1",      # expense type
    "vm_nafn",      # vendor name
    "ar",           # year
    "arsfjordungur",
    "raun",         # amount ISK
}


@pytest.fixture(scope="module")
def arsuppgjor(http) -> dict:
    r = http.get(f"{CKAN}/package_show", params={"id": "arsuppgjor"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert payload.get("success") is True, f"CKAN reported failure: {payload.get('error')}"
    return payload["result"]


def test_ckan_lists_the_arsuppgjor_resources(arsuppgjor):
    """The dataset is the entry point for every "what does Reykjavík buy"
    question; its resources are one CSV per quarter/year since 2014."""
    resources = arsuppgjor.get("resources")
    assert resources, f"arsuppgjor has no resources; keys: {sorted(arsuppgjor)}"

    csvs = [r for r in resources if r.get("format", "").upper() == "CSV"]
    assert csvs, f"no CSV resources among formats {[r.get('format') for r in resources]}"
    assert all(r.get("url") for r in csvs), "a CSV resource has no download URL"


def test_arsuppgjor_csv_keeps_its_schema(http, arsuppgjor):
    """Range-request the header — the full year is ~94k rows and we need one line.

    Resource UUIDs rotate on republish, so the newest CSV is discovered from the
    package rather than pinned.
    """
    csvs = [r for r in arsuppgjor["resources"] if r.get("format", "").upper() == "CSV"]
    url = csvs[0]["url"]

    r = http.get(url, headers={"Range": "bytes=0-1023"})
    assert r.status_code in (200, 206), f"{url} -> {r.status_code}"

    header = r.content.decode("utf-8-sig", errors="replace").split("\n", 1)[0].strip()
    cols = {c.strip() for c in header.split(";")}
    missing = UPPGJOR_COLUMNS - cols
    assert not missing, f"{url}: lost columns {sorted(missing)}; got {sorted(cols)}"


def test_pxweb_catalog_is_browsable(http):
    r = http.get(f"{PXWEB}/")
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    catalog = r.json()
    assert isinstance(catalog, list) and catalog, "velstat catalog is empty"
    ids = {entry["id"] for entry in catalog}
    # The three top-level paths the skill documents table locations under.
    assert {"100. Manadarleg tolfraedi", "200. Arsskyrsla"} <= ids, (
        f"velstat categories renamed — every documented table path breaks; got {sorted(ids)}"
    )


def test_pxweb_table_metadata_has_expected_dimensions(http):
    r = http.get(PX_TABLE)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    assert "variables" in meta, f"no 'variables' key; got {sorted(meta)}"
    codes = {v["code"] for v in meta["variables"]}
    assert {"Ár", "Ríkisfang", "Hverfi"} <= codes, (
        f"VEL11008 dimensions changed; got {sorted(codes)}"
    )


def test_pxweb_small_query_returns_data(http):
    """POST one year, not the whole table.

    velstat indexes the Ár dimension positionally ("0".."12" for 2010–2022)
    rather than by year label, unlike Hagstofa's px.hagstofa.is — so this asks
    for the last index, and that difference is the reason this probe exists
    separately from test_hagstofan.py.
    """
    r = http.post(
        PX_TABLE,
        json={
            "query": [{"code": "Ár", "selection": {"filter": "item", "values": ["12"]}}],
            "response": {"format": "json"},
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert "data" in payload, f"no 'data' key; got {sorted(payload)}"
    assert payload["data"], "query returned zero rows"

    first = payload["data"][0]
    assert "key" in first and "values" in first, f"unexpected row shape: {first}"

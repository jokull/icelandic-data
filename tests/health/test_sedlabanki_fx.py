"""Health probe — Seðlabanki FX intervention (scripts/sedlabanki_fx.py).

Contract has two independent links, like the balance-sheet probe:

  1. The xmltimeseries endpoint serves the FX-market group (GroupID 8) as
     semicolon CSV with the CBI purchase/sale series — this is a plain
     public GET, no proxy, and the data the script depends on.
  2. The CBI balance-sheet workbook (monthly FX reserves) is still reachable
     through the gagnabanki.is/api/download proxy from its library item.

Probe the endpoint + the series contract, not the values: pinning the króna
to a number would fail on a currency move rather than on a broken source.
"""
from __future__ import annotations

XML_BASE = "https://sedlabanki.is/xmltimeseries/Default.aspx"
PROXY = "https://gagnabanki.is/api/download"
CB_BALANCE_LIBRARY = (
    "https://sedlabanki.is/library?itemid=c0126d81-fd88-42bd-aee3-449e09b9089f"
)

# series ids the processed CSV depends on (see scripts/sedlabanki_fx.py)
FX_SERIES_IDS = {"282", "284", "285", "287"}
EUR_MID_TS = "4064"


def test_fx_market_group_is_served(http):
    """GroupID 8 must still be the FX-market semicolon CSV with the CBI's own
    purchase/sale series — a renumbering would silently break the script."""
    r = http.get(XML_BASE, params={"DagsFra": "LATEST", "GroupID": "8", "Type": "csv"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    lines = r.text.splitlines()
    assert lines, "empty FX-market response"
    present = {line.split(";")[2] for line in lines if len(line.split(";")) >= 8}
    missing = FX_SERIES_IDS - present
    assert not missing, f"FX series missing from GroupID 8: {sorted(missing)}"


def test_eur_mid_rate_series_is_served(http):
    """TS 4064 (EUR skráð miðgengi) feeds isk_per_eur in the processed CSV."""
    r = http.get(XML_BASE, params={"DagsFra": "LATEST", "TimeSeriesID": EUR_MID_TS, "Type": "csv"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    line = r.text.splitlines()[0]
    parts = line.split(";")
    assert parts[2] == EUR_MID_TS, f"unexpected series id {parts[2]!r}"
    assert "Evra" in parts[4], f"unexpected series name: {parts[4]!r}"
    assert float(parts[7]) > 0, "EUR mid rate is not positive"


def test_balance_sheet_library_item_fetches_through_proxy(http):
    """The reserves workbook must stay fetchable via the documented proxy."""
    r = http.post(PROXY, json={"url": CB_BALANCE_LIBRARY})
    assert r.status_code == 200, f"proxy -> {r.status_code}: {r.text[:200]}"
    assert r.content[:2] == b"PK", "response is not a valid xlsx/zip archive"
    assert len(r.content) > 10_000, f"suspiciously small workbook: {len(r.content)} bytes"

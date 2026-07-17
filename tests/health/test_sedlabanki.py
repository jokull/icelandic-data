"""Health probe — Seðlabanki Íslands.

Contract, and the thing to understand before editing this file: the SDMX host
`fr.sedlabanki.is` is **not reachable from the public internet**. It resolves
(217.151.180.10, a Vodafone Iceland xDSL pool address) but black-holes on both
80 and 443. Every documented fetch goes through Seðlabanki's own server-side
proxy at `POST https://gagnabanki.is/api/download`, which does the GET from
inside their network and streams the file back.

So the real contract has two links, and either can break independently:

  1. gagnabanki.is serves its Power BI config  — drives scripts/sedlabanki_rates.py
  2. the proxy still fetches a known SDMX table — the documented path to the
     balance-sheet / exchange-rate data

Do NOT "fix" this by probing fr.sedlabanki.is directly. It has never been
publicly reachable (archive.org has zero captures, ever), so a direct probe
tests a contract that was never true and reports a permanent false failure.
"""
from __future__ import annotations

import pytest

GAGNABANKI_CONFIG = "https://gagnabanki.is/api/config"
PROXY = "https://gagnabanki.is/api/download"

# A stable, long-lived SDMX table — the one the skill documents.
SDMX_TABLE = (
    "https://fr.sedlabanki.is/sdmx/v2/table/IS2_EXT/"
    "INN_BALANCE_SHEETS_TOTAL/1.0?format=xlsx"
)

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_gagnabanki_config_is_served(http):
    r = http.get(GAGNABANKI_CONFIG)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    config = r.json()
    assert config, "gagnabanki config is empty"
    assert isinstance(config, (dict, list)), f"unexpected type {type(config).__name__}"

    # The config is what still points at the SDMX host. If Seðlabanki ever
    # migrates off fr.sedlabanki.is, it changes here first — and this probe
    # is how we would find out.
    assert "fr.sedlabanki.is" in r.text, (
        "gagnabanki config no longer references fr.sedlabanki.is — the SDMX "
        "endpoint may have migrated; re-check the sedlabanki skill"
    )


def test_sdmx_table_is_fetchable_through_the_proxy(http):
    """The documented path to SDMX data. ~188 KB, once a day — no lighter
    endpoint exists, so this *is* the smallest stable contract."""
    r = http.post(PROXY, json={"url": SDMX_TABLE})
    assert r.status_code == 200, f"proxy -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith(XLSX_TYPE), r.headers["content-type"]

    # Type check, not a size check — the table grows as periods are added.
    assert r.content[:2] == b"PK", "response is not a valid xlsx/zip archive"
    assert len(r.content) > 10_000, f"suspiciously small workbook: {len(r.content)} bytes"


@pytest.mark.degraded_ok
def test_proxy_reports_a_missing_table_rather_than_lying(http):
    """Guards the failure mode that would otherwise be invisible.

    If the proxy ever starts returning 200 with an error page or canned bytes
    instead of passing the upstream status through, the probe above would go
    green on garbage. A bogus table must still 404. degraded_ok because this
    tests the proxy's manners, not whether our data is reachable.
    """
    r = http.post(
        PROXY,
        json={"url": "https://fr.sedlabanki.is/sdmx/v2/table/IS2_EXT/NOPE_NOT_A_TABLE/1.0?format=xlsx"},
    )
    assert r.status_code == 404, (
        f"expected 404 for a nonexistent table, got {r.status_code} — the proxy "
        f"may no longer pass upstream status through"
    )

"""Health probe — Nasdaq Iceland exchange-notice API.

Contract: the two call shapes scripts/nasdaq.py makes against
`api.news.eu.nasdaq.com` — `metadata.action` for filter values (companies,
categories) and `query.action` for announcements.

Both are driven by the *exact* `globalName` / `market` pair. Those strings are
the fragile part: "Main Market, Iceland" is a filter value, not an id, so a
rename upstream returns an empty-but-successful result rather than an error.
The probes therefore assert a known company is still in the list, which is what
actually breaks if the market string drifts.

The documented caveat for this source is Icelandic character encoding, so one
probe pins that: names must round-trip as decoded text (`Íslandsbanki`), not as
mojibake.
"""
from __future__ import annotations

import pytest

from scripts.nasdaq import BASE_URL

MARKET = "Main Market, Iceland"
GLOBAL_NAME = "NordicMainMarkets"

# Listed since 2018, one of the largest issuers on the exchange — if this name
# is absent the market/globalName pair no longer selects Iceland.
KNOWN_COMPANY = "Arion banki hf."


@pytest.fixture(scope="module")
def companies(http):
    r = http.get(
        f"{BASE_URL}/metadata.action",
        params={
            "globalGroup": "exchangeNotice",
            "globalName": GLOBAL_NAME,
            "market": MARKET,
            "resultType": "company",
            "displayLanguage": "is",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert "facts" in payload, f"no 'facts' key; got {sorted(payload)}"
    facts = payload["facts"]
    assert facts, "company metadata returned zero facts"
    assert "id" in facts[0], f"unexpected fact shape: {sorted(facts[0])}"

    # list_companies() reads exactly this projection.
    return [fact["id"] for fact in facts]


def test_company_list_still_covers_iceland(companies):
    assert KNOWN_COMPANY in companies, (
        f"{KNOWN_COMPANY!r} missing from {MARKET!r} — the market/globalName "
        f"filter may have been renamed upstream ({len(companies)} companies returned)"
    )


def test_icelandic_characters_survive_decoding(companies):
    """The documented caveat for this source.

    If the API stops declaring its charset, or the client starts guessing, the
    failure is silent: names still arrive, just mangled. Assert that at least
    one known-accented issuer decodes to real Icelandic text rather than the
    latin-1-over-utf-8 mojibake ("Ãslandsbanki") that this would produce.
    """
    accented = [c for c in companies if not c.isascii()]
    assert accented, "no non-ASCII company names at all — encoding may have been stripped"

    joined = "\n".join(accented)
    assert "Íslandsbanki hf." in companies, (
        f"expected 'Íslandsbanki hf.' among non-ASCII names; got {accented[:10]}"
    )
    assert "Ã" not in joined, f"mojibake in company names: {accented[:5]}"


def test_announcement_query_returns_expected_row_shape(http):
    """One announcement, not a page — the projection in nasdaq.py's `search`
    reads these keys, so a rename here breaks every downstream fetch."""
    r = http.get(
        f"{BASE_URL}/query.action",
        params={
            "globalGroup": "exchangeNotice",
            "globalName": GLOBAL_NAME,
            "market": MARKET,
            "company": KNOWN_COMPANY,
            "limit": 1,
            "start": 0,
            "dir": "DESC",
            "displayLanguage": "is",
            "dateMask": "yyyy-MM-dd HH:mm:ss",
            "countResults": "true",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert "results" in payload, f"no 'results' key; got {sorted(payload)}"

    items = payload["results"].get("item", [])
    assert items, f"no announcements for {KNOWN_COMPANY} — filter may be broken"

    first = items[0]
    required = {"releaseTime", "company", "headline", "cnsCategory", "messageUrl"}
    assert required <= set(first), (
        f"announcement is missing keys {sorted(required - set(first))}; "
        f"got {sorted(first)}"
    )
    assert first["company"] == KNOWN_COMPANY, (
        f"company filter ignored: asked for {KNOWN_COMPANY!r}, got {first['company']!r}"
    )

    # query_all() paginates against this counter; a missing/zero count would
    # silently truncate every multi-page fetch to one request.
    assert isinstance(payload.get("count"), int), f"bad 'count': {payload.get('count')!r}"
    assert payload["count"] > 0, "countResults returned 0 for a company with announcements"

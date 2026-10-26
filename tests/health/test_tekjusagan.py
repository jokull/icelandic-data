"""Health probe — Tekjusagan (Forsætisráðuneytið).

Since an October 2026 redeploy the SPA charts JSON from its own backend,
`POST /api/sqlseries/<queryId>` with the group filters as the body — the
Power BI embed and its `/api/report/<id>` token endpoint are gone (that path
now falls through to the SPA's index.html with a 200).

The contract is the stored-procedure call itself: a queryId, its exact
parameter set, and the `items` row shape. Each failure mode answers
distinctly — a dropped/renamed procedure gives 400 "not available as a
series", a changed parameter list gives 400 "expects parameter '@X'" / "too
many arguments", and a dead backend falls back to text/html.

The SPA routes are deliberately *not* probed: every route of the Angular app,
including ones that no longer exist, returns the same 200 index.html.
"""
from __future__ import annotations

import pytest

from scripts.tekjusagan import LAST_TAX_YEAR, SERIES, SERIES_URL

ROW_KEYS = {"Skattár", "Breyta Heiti", "Breyta Lýsing", "Breyta Röðun", "Breytugildi ISK", "Breytugildi Prósenta"}


@pytest.mark.parametrize("slug", list(SERIES))
def test_series_returns_rows_for_the_spa_defaults(http, slug):
    s = SERIES[slug]
    r = http.post(
        SERIES_URL.format(query_id=s["query_id"]),
        params={"from": LAST_TAX_YEAR - 1, "to": LAST_TAX_YEAR},
        json=s["body"],
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json"), (
        f"{r.request.url} -> {r.headers['content-type']} (SPA fallback — API route moved?)"
    )
    items = r.json()["items"]
    assert items, f"{r.request.url} -> 0 rows for the SPA's own default filters"
    assert ROW_KEYS <= set(items[0]), f"row keys changed: {sorted(items[0])}"
    assert {i["Skattár"] for i in items} == {LAST_TAX_YEAR - 1, LAST_TAX_YEAR}


@pytest.mark.degraded_ok
def test_backend_rejects_an_unknown_series(http):
    """Guards the probe above: if any queryId got 200, a renamed procedure
    would go unnoticed. degraded_ok — this tests the API's manners."""
    r = http.post(SERIES_URL.format(query_id="NoSuchSeries"), params={"from": 2024, "to": 2024}, json={})
    assert r.status_code == 400, f"{r.request.url} -> {r.status_code} for a nonexistent series"

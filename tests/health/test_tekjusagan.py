"""Health probe — Tekjusagan (Forsætisráðuneytið).

Unlike the publish-to-web dashboards, Tekjusagan's Power BI report is *private*
and token-gated: the SPA asks its own backend for a short-lived embed token
before it can render anything. No credentials are involved — the token endpoint
is open to the public internet — so the gate itself is probeable, and it is the
single point where this source breaks:

    GET https://tekjusagan.is/api/report/<REPORT_ID>  ->  {id, embedToken}

If REPORT_ID is ever re-published (new workspace, new report), the SPA gets a
new one and our hardcoded constant starts returning 400 while tekjusagan.is
itself stays perfectly up. That is what this asserts.

The SPA routes in REPORTS are deliberately *not* probed: it is an Angular app,
so every route — including ones that no longer exist — returns the same 200
index.html. A probe over them would be green by construction. Verifying them
needs a browser, and browser probes are manual-only here.
"""
from __future__ import annotations

import pytest

from scripts.tekjusagan import REPORT_ID, SPA_URL, TOKEN_URL


@pytest.fixture(scope="module")
def token(http):
    r = http.get(TOKEN_URL)
    assert r.status_code == 200, (
        f"{r.request.url} -> {r.status_code}: {r.text[:200]} "
        f"(400 = report {REPORT_ID} is unknown to the backend — re-published?)"
    )
    assert r.headers["content-type"].startswith("application/json")
    return r.json()


def test_embed_token_is_issued(token):
    """A token, not just a 200 — the backend brokers Power BI auth for us, and
    an empty/absent token means the SPA cannot render the report either."""
    assert token.get("embedToken"), f"no embedToken in response; got {sorted(token)}"
    assert len(token["embedToken"]) > 100, (
        f"embedToken is implausibly short ({len(token['embedToken'])} chars)"
    )


def test_token_is_bound_to_the_report_we_pin(token):
    assert token.get("id") == REPORT_ID, (
        f"{TOKEN_URL} issued a token for report {token.get('id')}, not {REPORT_ID}"
    )


@pytest.mark.degraded_ok
def test_backend_rejects_an_unknown_report(http):
    """Guards the failure mode that would make the probe above meaningless: if
    the endpoint ever starts minting tokens for any id, a rotated REPORT_ID
    would go undetected. degraded_ok — this tests the API's manners, not
    whether our data is reachable."""
    url = f"{SPA_URL}api/report/00000000-0000-0000-0000-000000000000"
    r = http.get(url)
    assert r.status_code != 200, (
        f"{url} -> 200 for a nonexistent report — the token endpoint no longer "
        f"validates the report id, so test_token_is_bound_to_the_report_we_pin "
        f"proves nothing"
    )

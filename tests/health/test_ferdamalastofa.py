"""Health probe — Ferðamálastofa tourism dashboards (Power BI).

scripts/ferdamalastofa.py drives Playwright at maelabordferdathjonustunnar.is
and scrapes intercepted Power BI responses. That does *not* mean the probe needs
a browser: the two links the scrape depends on are both plain HTTP.

  1. Each dashboard page embeds an iframe pointing at
     `ferdapbi.azurewebsites.net/embed/{report_id}`. The report_id in DASHBOARDS
     is only ever used to *identify* a dashboard — the script navigates by
     `path` — so a page whose iframe no longer carries the expected id means
     DASHBOARDS has drifted and the scrape is pulling the wrong report.
  2. `GET ferdapbi.azurewebsites.net/api/report/{report_id}` mints the Power BI
     embed token. This is the bootstrap the embedded report calls before any
     querydata request — if it fails, the Playwright run intercepts nothing and
     reports "No Power BI data intercepted" with no other clue why.

Probing (2) directly is what makes this cheap and honest: it is the actual
upstream, one small JSON call, no Chromium, no 15-second wait.

Careful: the embed host is an Angular SPA that serves the same 200 HTML for
*any* /embed/<anything> path — so a 200 there proves nothing. Only /api/report
distinguishes a real report from a missing one (400).
"""
from __future__ import annotations

import re

import pytest

from scripts.ferdamalastofa import BASE_URL, DASHBOARDS

EMBED_HOST = "https://ferdapbi.azurewebsites.net"

# The dashboard the skill leads with — Keflavík passenger counts by nationality.
PRIMARY = "passengers"


def report_api(report_id: str) -> str:
    return f"{EMBED_HOST}/api/report/{report_id}"


def test_dashboard_page_embeds_the_expected_report(http):
    """One page, not all four — asserts DASHBOARDS' path→report_id pairing."""
    info = DASHBOARDS[PRIMARY]
    url = f"{BASE_URL}{info['path']}"
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html")

    iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', r.text)
    assert iframes, f"{url} -> 200 but has no <iframe> — the page was re-rendered"
    assert any(info["report_id"] in src for src in iframes), (
        f"{url} no longer embeds report {info['report_id']} (from DASHBOARDS); "
        f"iframe srcs: {iframes[:3]}"
    )


def test_embed_token_endpoint_serves_a_token(http):
    """The Power BI bootstrap. If this breaks, the Playwright scrape returns
    zero tables and blames the wait time."""
    info = DASHBOARDS[PRIMARY]
    url = report_api(info["report_id"])
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert payload.get("embedToken"), (
        f"{url} -> 200 but no embedToken; got {sorted(payload)}"
    )
    assert payload.get("workspaceId"), (
        f"{url} -> 200 but no workspaceId; got {sorted(payload)}"
    )


def test_every_catalogued_report_id_is_live(http):
    """All four DASHBOARDS entries, one small JSON call each.

    Worth the extra three calls: the report_ids are hardcoded constants nothing
    else validates, and they rot one at a time as Ferðamálastofa republishes
    reports. A per-id failure names the exact dashboard to fix.
    """
    for key, info in DASHBOARDS.items():
        url = report_api(info["report_id"])
        r = http.get(url)
        assert r.status_code == 200, (
            f"{url} -> {r.status_code} — report_id for DASHBOARDS[{key!r}] "
            f"is no longer valid: {r.text[:150]}"
        )
        assert r.json().get("embedToken"), f"{url} -> 200 but no embedToken for {key!r}"


@pytest.mark.degraded_ok
def test_embed_api_rejects_an_unknown_report(http):
    """Guards the probes above from going green on a permissive API.

    If /api/report ever starts minting tokens for any id, the coverage check
    becomes meaningless. degraded_ok — this is about the API's manners, not
    about whether our dashboards are reachable.
    """
    url = report_api("00000000-0000-0000-0000-000000000000")
    r = http.get(url)
    assert r.status_code >= 400, (
        f"{url} -> {r.status_code}, expected a 4xx for a nonexistent report — "
        f"/api/report may no longer validate report ids"
    )

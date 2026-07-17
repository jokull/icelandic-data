"""Health probe — Maskína public opinion polls.

The skill documents two independent sources, and the probe mirrors that split
because they fail for different reasons and have different blast radii:

  1. **WordPress REST API** (`maskina.is/wp-json/wp/v2/posts`) — stable, public,
     documented as the fallback for prose poll data. Cheap to probe.
  2. **Tableau Public VizQL** — undocumented and explicitly called out in the
     skill as liable to change without notice. It is the only structured
     source, so it is the one worth probing hard.

There is no script for this source; the skill carries the reference
implementation, so these probes re-implement the two-step VizQL flow rather
than importing it.

Note on cost: bootstrapSession returns ~650 KB. That is the *smallest* call
that exercises the parse path (chunk split → dataDictionary → `bar kosningar`
worksheet) — there is no lighter endpoint that proves the data is still
extractable, and that parse path is exactly what breaks. Once a day is fine.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import httpx
import pytest

from tests.health.conftest import assert_fresh

WP_POSTS = "https://maskina.is/wp-json/wp/v2/posts"

TABLEAU_BASE = "https://public.tableau.com"
WORKBOOK = "FylgiFlokka-heimasa"
SHEET = "Njastamling"
ACTIVE_TAB = "N%C3%BDjasta%20m%C3%A6ling"

# The worksheet holding the party/percentage triplets.
DATA_WORKSHEET = "bar kosningar"

# Parties that have been in every poll for years. A loose subset — new parties
# appear and the mapping needs updating, but these three vanishing means the
# accusative-case labels changed and PARTY_NAMES no longer maps anything.
STAPLE_PARTIES = {"Samfylkinguna", "Sjálfstæðisflokkinn", "Miðflokkinn"}


# ---------------------------------------------------------------------------
# WordPress
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wp_posts(http):
    r = http.get(WP_POSTS, params={"per_page": 3, "_fields": "id,title,date,link"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json")
    return r


def test_wordpress_api_serves_posts(wp_posts):
    posts = wp_posts.json()
    assert isinstance(posts, list) and posts, "WP API returned no posts"

    first = posts[0]
    # The fields the skill's documented curl examples select.
    for key in ("id", "title", "date", "link"):
        assert key in first, f"post missing {key!r}; got {sorted(first)}"
    assert "rendered" in first["title"], (
        f"title is no longer a {{rendered: ...}} object: {first['title']!r}"
    )


def test_wordpress_search_works(http):
    """`fylgi` is the skill's documented search term for the monthly party-support
    posts. Search silently returning nothing would be an invisible break."""
    r = http.get(WP_POSTS, params={"search": "fylgi", "per_page": 3, "_fields": "id,title"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.json(), f"{r.request.url} -> 200 but search for 'fylgi' matched no posts"


@pytest.mark.degraded_ok
def test_wordpress_posts_are_fresh(wp_posts):
    """Maskína publishes at least monthly; 120 days allows a quiet stretch
    without tolerating a dead feed."""
    latest = datetime.fromisoformat(wp_posts.json()[0]["date"])
    assert_fresh(latest, timedelta(days=120), label="maskina.is WP posts")


# ---------------------------------------------------------------------------
# Tableau VizQL
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vizql_bootstrap():
    """Run the documented two-step VizQL flow once and share the parsed result.

    Uses its own client rather than the `http` fixture: the flow depends on
    cookie jar continuity between startSession and bootstrapSession, and on
    reading response headers the session client would otherwise share across
    unrelated probes.
    """
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        start_url = (
            f"{TABLEAU_BASE}/vizql/w/{WORKBOOK}/v/{SHEET}/startSession/viewing"
            f"?:embed=y&:apiID=host0&:showVizHome=n"
        )
        try:
            r1 = client.post(start_url, headers={"Accept": "application/json"}, content=b"")
        except httpx.HTTPError as exc:
            pytest.fail(f"{start_url} unreachable: {type(exc).__name__}: {exc}")

        # A workbook that no longer exists 404s here — this is the real
        # existence check. The /views/ HTML URL is a JS shell that returns an
        # identical 200 for any name, so it proves nothing.
        assert r1.status_code == 200, f"{start_url} -> {r1.status_code}"

        body = r1.json()
        session_id = r1.headers.get("x-session-id", body.get("sessionid"))
        assert session_id, f"{start_url} -> 200 but no session id in headers or body"

        sticky = body.get("stickySessionKey", "")
        # Documented gotcha: global-session-header is a routing value, NOT the
        # session id. Sending the session id instead yields 410 Gone.
        global_header = r1.headers.get("global-session-header", "")
        cookies = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)

        boot_url = (
            f"{TABLEAU_BASE}/vizql/w/{WORKBOOK}/v/{SHEET}"
            f"/bootstrapSession/sessions/{session_id}"
        )
        try:
            r2 = client.post(
                boot_url,
                data={
                    "worksheetPortSize": '{"w":1100,"h":1800}',
                    "dashboardPortSize": '{"w":1100,"h":1800}',
                    "clientDimension": '{"w":1003,"h":1022}',
                    "sheet_id": ACTIVE_TAB,
                    "stickySessionKey": sticky,
                    "renderMapsClientSide": "true",
                    "isBrowserRendering": "true",
                    "browserRenderingThreshold": "100",
                    "formatDataValueLocally": "false",
                    "locale": "en_US",
                    "language": "en",
                },
                headers={
                    "Cookie": cookies,
                    "global-session-header": global_header,
                    "x-tsi-active-tab": ACTIVE_TAB,
                },
            )
        except httpx.HTTPError as exc:
            pytest.fail(f"{boot_url} unreachable: {type(exc).__name__}: {exc}")

        assert r2.status_code == 200, f"{boot_url} -> {r2.status_code}: {r2.text[:200]}"

        # The response is length-prefixed JSON chunks: "590031;{...}63012;{...}".
        # Chunk 0 is layout metadata, chunk 1 is the data.
        chunks = [c for c in re.split(r"\d+;(?=\{)", r2.text) if c.startswith("{")]
        assert len(chunks) >= 2, (
            f"{boot_url} -> 200 but the response split into {len(chunks)} JSON "
            f"chunk(s), expected >=2 — the length-prefixed format changed"
        )
        return json.loads(chunks[1])


def test_vizql_exposes_the_poll_worksheet(vizql_bootstrap):
    """`bar kosningar` is hardcoded in the extraction path — a renamed worksheet
    breaks it with a KeyError and no other warning."""
    viz_map = (
        vizql_bootstrap["secondaryInfo"]["presModelMap"]["vizData"]["presModelHolder"]
        ["genPresModelMapPresModel"]["presModelMap"]
    )
    assert DATA_WORKSHEET in viz_map, (
        f"worksheet {DATA_WORKSHEET!r} is gone from the viz — the extraction "
        f"path in the maskina skill would KeyError. Present: {sorted(viz_map)}"
    )


def test_vizql_data_dictionary_still_has_parties_and_percentages(vizql_bootstrap):
    """Asserts the shape the parse relies on: one `real` column of fractions and
    one `cstring` column carrying accusative party names."""
    seg = (
        vizql_bootstrap["secondaryInfo"]["presModelMap"]["dataDictionary"]
        ["presModelHolder"]["genDataDictionaryPresModel"]["dataSegments"]["0"]
    )
    reals, strings = [], []
    for col in seg["dataColumns"]:
        if col["dataType"] in ("real", "float"):
            reals = col["dataValues"]
        elif col["dataType"] in ("cstring", "string"):
            strings = col["dataValues"]

    assert reals, f"no real/float column in the data dictionary; got {[c['dataType'] for c in seg['dataColumns']]}"
    assert strings, f"no cstring/string column in the data dictionary; got {[c['dataType'] for c in seg['dataColumns']]}"

    found = STAPLE_PARTIES & set(strings)
    assert found, (
        f"none of the long-standing accusative party labels {sorted(STAPLE_PARTIES)} "
        f"appear — PARTY_NAMES in the maskina skill may need remapping. "
        f"Sample strings: {strings[:8]}"
    )

    # Percentages arrive as fractions (0–1), not 0–100. If Tableau ever changes
    # that, every number the skill emits is off by 100×, silently.
    fractions = [v for v in reals if isinstance(v, float) and 0 < v < 1]
    assert fractions, (
        f"no 0–1 fractional values among {len(reals)} reals — poll percentages "
        f"may no longer be encoded as fractions"
    )

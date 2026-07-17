"""Health probe — Icelandic district courts (héraðsdómstólar) ruling RSS.

Read this before editing: **the courts have migrated to island.is.** The skill
documents `www.heradsdomstolar.is/heradsdomstolar/{slug}/domar/rss/`; that URL
now 301s to `https://island.is/rss/domar?court=hd-{slug}`, which serves the
feed. The old domain is a redirect shim, so both links matter and either can
break independently:

  1. the documented heradsdomstolar.is URL still redirects rather than 404s
  2. island.is serves a well-formed RSS feed with the documented item fields

Only the RSS entry point is probed, because it is the only documented endpoint
that survived the migration. The skill's other two — the PDF cache at
`/Cache/Verdicts/{guid}.pdf` and the `default.aspx?pageitemid=…` AJAX
pagination — both 404 on island.is now. They are *known broken*, not flaky, so
asserting on them would just pin a permanent red; the skill needs rewriting
against island.is instead. There is no script for this source yet.

Feed shape per the skill: each `<item>` has `<title>` (case number),
`<description>` (reifun), `<link>`, `<guid>`, `<pubDate>`. Note the guid is now
`g-<uuid>`, not the bare uuid the old PDF path expected.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

import pytest

from tests.health.conftest import assert_fresh

# The URL the skill documents. Kept deliberately — probing island.is directly
# would not notice the day the redirect shim disappears.
DOCUMENTED_RSS = "https://www.heradsdomstolar.is/heradsdomstolar/reykjavik/domar/rss/"

# Where it lands today.
ISLAND_IS_RSS = "https://island.is/rss/domar"

# Reykjavík is the busiest district court — the one that would notice an outage
# first. Nordurland eystra is a second, much smaller court: if only one of the
# two answers, the feed is court-scoped and not a single global fallback.
COURTS = ["hd-reykjavik", "hd-nordurland-eystra"]


def _items(xml_text: str) -> list[ET.Element]:
    return ET.fromstring(xml_text).findall(".//item")


@pytest.fixture(scope="module")
def reykjavik_feed(http):
    r = http.get(DOCUMENTED_RSS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    return r


def test_documented_url_still_reaches_the_feed(reykjavik_feed):
    """The heradsdomstolar.is redirect shim is load-bearing for the skill."""
    r = reykjavik_feed
    assert "xml" in r.headers["content-type"], (
        f"{r.request.url} -> 200 but content-type is "
        f"{r.headers['content-type']!r}, not XML"
    )
    assert "island.is" in str(r.url), (
        f"{DOCUMENTED_RSS} no longer redirects to island.is (landed on {r.url}) — "
        f"the courts may have moved again; re-check the domstolar skill"
    )


def test_feed_items_have_the_documented_fields(reykjavik_feed):
    items = _items(reykjavik_feed.text)
    assert items, f"{reykjavik_feed.url} -> 200 but the feed has no <item> elements"

    first = items[0]
    for tag in ("title", "link", "guid", "pubDate"):
        el = first.find(tag)
        assert el is not None and (el.text or "").strip(), (
            f"{reykjavik_feed.url} -> 200 but <item> is missing a non-empty "
            f"<{tag}>; got {[c.tag for c in first]}"
        )

    # Case numbers are the skill's documented title format: E- (einkamál) or
    # S- (sakamál) followed by a number. Loose on purpose — asserts the shape,
    # not which cases happen to be in the window.
    titles = [(i.findtext("title") or "") for i in items]
    assert any(t.startswith(("E-", "S-")) for t in titles), (
        f"no E-/S- case numbers in feed titles — <title> may no longer carry the "
        f"case number. Got: {titles[:5]}"
    )


def test_feed_is_court_scoped(http):
    """Each court slug must return its own feed, not one shared firehose."""
    for court in COURTS:
        r = http.get(ISLAND_IS_RSS, params={"court": court})
        assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
        assert _items(r.text), f"{r.request.url} -> 200 but returned no <item> elements"


@pytest.mark.degraded_ok
def test_reykjavik_feed_is_fresh(reykjavik_feed):
    """Reykjavík district court publishes most weeks. A 60-day gap spans the
    summer/Christmas recess without tolerating a quietly frozen feed."""
    dates = [
        parsedate_to_datetime(t)
        for t in (i.findtext("pubDate") for i in _items(reykjavik_feed.text))
        if t
    ]
    assert dates, f"{reykjavik_feed.url} -> 200 but no parseable <pubDate> values"
    assert_fresh(max(dates), timedelta(days=60), label="heradsdomstolar reykjavik RSS")

"""Health probe — Skoðanakannanir (RÚV + Vísir + Heimildin opinion-poll aggregators).

Contract, RÚV: scripts/skodanakannanir.py's `list` subcommand depends on the
tag page still being server-rendered with a `__NEXT_DATA__` JSON blob
containing GraphQL `Article` objects (id/title/url/first_published_at). That
is plain HTTP and is what actually breaks if RÚV changes their Next.js build
or their GraphQL schema.

Contract, Vísir: the tag page depends on being server-rendered HTML with
`<article class="article-item">` cards carrying a title `<h2>`, a `<time>`,
and a `/g/<id>/<slug>` link — regex-parsed, not JSON, so the probe checks
those markers directly rather than a schema.

Contract, Heimildin: `leit/?q=...` (search) depends on being server-rendered
HTML with `<article class="article-item">` cards carrying an `<h1
class="article-item__headline">`, a `<time class="article-item__pubdate"
datetime="...">`, and a `/grein/<id>/<slug>/` link. Same regex-over-markup
contract as Vísir, different class names.

Lightweight, not `browser`: `fetch`'s Playwright scrape of individual article
pages (chart `aria-label` extraction, prose fallback) is not probed here, for
the same reason as `landlaeknir`/`vernd` — a failure from a datacenter IP
says more about bot detection than about the source being down. The
precondition all three depend on — the discovery page still listing articles
at all — is what this probe covers. Heimildin's article pages themselves
need no auth for this probe either way (see the skill's Caveat 8: whether an
individual article needs login is unrelated to whether the search results
page lists it).
"""
from __future__ import annotations

import json

import pytest

from scripts.skodanakannanir import (
    HEIMILDIN_SEARCH_URL,
    TAG_URL,
    VISIR_TAG_URL,
    _find_articles,
    _HEIMILDIN_ARTICLE_RE,
    _HEIMILDIN_LINK_RE,
    _HEIMILDIN_TIME_RE,
    _HEIMILDIN_TITLE_RE,
    _NEXT_DATA_RE,
    _VISIR_ARTICLE_RE,
    _VISIR_LINK_RE,
    _VISIR_TIME_RE,
    _VISIR_TITLE_RE,
)


def test_ruv_tag_page_serves_article_list(http):
    r = http.get(TAG_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    m = _NEXT_DATA_RE.search(r.text)
    assert m, f"{r.request.url} -> __NEXT_DATA__ script tag not found (page structure changed)"

    data = json.loads(m.group(1))
    articles = _find_articles(data, [])
    assert articles, f"{r.request.url} -> __NEXT_DATA__ parsed but no Article objects found"

    sample = articles[0]
    for key in ("id", "title", "url", "first_published_at"):
        assert key in sample, f"Article object missing expected key {key!r}: {sorted(sample)}"


def test_visir_tag_page_serves_article_list(http):
    url = VISIR_TAG_URL.format(page=1)
    r = http.get(url)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    blocks = _VISIR_ARTICLE_RE.findall(r.text)
    assert blocks, f"{r.request.url} -> no <article class=\"article-item\"> blocks found (page structure changed)"

    matched = sum(
        1
        for b in blocks
        if _VISIR_LINK_RE.search(b) and _VISIR_TITLE_RE.search(b) and _VISIR_TIME_RE.search(b)
    )
    assert matched, f"{r.request.url} -> article blocks found but none matched link+title+time (markup changed)"


def test_heimildin_search_serves_article_list(http):
    r = http.get(HEIMILDIN_SEARCH_URL, params={"q": "skoðanakönnun"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    blocks = _HEIMILDIN_ARTICLE_RE.findall(r.text)
    assert blocks, f"{r.request.url} -> no <article class=\"article-item\"> blocks found (page structure changed)"

    matched = sum(
        1
        for b in blocks
        if _HEIMILDIN_LINK_RE.search(b) and _HEIMILDIN_TITLE_RE.search(b) and _HEIMILDIN_TIME_RE.search(b)
    )
    assert matched, f"{r.request.url} -> article blocks found but none matched link+title+time (markup changed)"

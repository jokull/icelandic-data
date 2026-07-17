"""Health probe — Byggðastofnun regional-development dashboards.

scripts/byggdastofnun.py is a catalog + URL builder over 11 Tableau Public
embeds. Two things can rot independently:

  1. the byggdastofnun.is mælaborð index, whose regexes feed `discover()` and
     `scrape_one()` when the catalog is re-fetched
  2. the Tableau workbook/view coordinates in SEED_CATALOG, which `embed_url()`
     reconstructs blind — nothing validates them

**Do not probe a `/views/<workbook>/<view>` URL and assert 200.** That page is a
JS shell: Tableau serves byte-identical HTML for a real workbook and for
`NoSuchWorkbookXYZ`, so a 200 there proves only that public.tableau.com is up.
`POST .../startSession/viewing` is the real existence check — 200 for a live
workbook, 404 for a missing one — and it returns `workbookName`, which confirms
we resolved the intended workbook rather than merely *a* workbook.

One workbook is probed, not all 11: a broken coordinate is a per-dashboard
data problem, but Tableau dropping the account or the VizQL route is what this
probe is for, and one call detects it.
"""
from __future__ import annotations

import pytest

from scripts.byggdastofnun import (
    INDEX,
    SEED_CATALOG,
    _SUBPAGE_RE,
    _TABLEAU_VIEW_RE,
    embed_url,
    page_url,
)

TABLEAU_BASE = "https://public.tableau.com"

# "Tekjur einstaklinga eftir svæðum" — the income dashboard, one of the oldest.
PROBE = next(row for row in SEED_CATALOG if row["slug"] == "tekjur")


def _start_session(http, workbook: str, view: str):
    url = (
        f"{TABLEAU_BASE}/vizql/w/{workbook}/v/{view}/startSession/viewing"
        f"?:embed=y&:apiID=host0&:showVizHome=n"
    )
    return url, http.post(url, headers={"Accept": "application/json"}, content=b"")


def test_maelabord_index_lists_dashboards(http):
    """Guards `discover()` — _SUBPAGE_RE is how slugs are found on re-fetch."""
    r = http.get(INDEX)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html")

    slugs = {
        m.group(1).rsplit("/", 1)[-1]
        for m in _SUBPAGE_RE.finditer(r.text)
        if not m.group(1).endswith("/maelabord")
    }
    assert slugs, (
        f"no /is/utgefid-efni/maelabord/<slug> links at {INDEX} — _SUBPAGE_RE no "
        f"longer matches and discover() would return nothing"
    )
    # Loose floor: the site lists 11 today. Tolerates dashboards being retired
    # without tolerating an empty crawl.
    assert len(slugs) >= 5, f"only {len(slugs)} dashboard slugs discovered: {sorted(slugs)}"


def test_dashboard_page_still_embeds_a_tableau_iframe(http):
    """Guards `scrape_one()` — one sub-page, never the full crawl.

    _TABLEAU_VIEW_RE is what turns a page into workbook/view coordinates. A
    Byggðastofnun re-render that swaps the iframe (or moves to a different viz
    host) empties the catalog silently.
    """
    url = page_url(PROBE["slug"])
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"

    m = _TABLEAU_VIEW_RE.search(r.text)
    assert m, f"no Tableau Public iframe at {url} — _TABLEAU_VIEW_RE no longer matches"
    assert f"/views/{PROBE['workbook']}/" in m.group(1).replace("&amp;", "&"), (
        f"{url} embeds {m.group(1)!r}, but SEED_CATALOG expects workbook "
        f"{PROBE['workbook']!r} — the catalog is out of date"
    )


def test_tableau_workbook_coordinates_resolve(http):
    """The SEED_CATALOG coordinates `embed_url()` reconstructs must be live."""
    url, r = _start_session(http, PROBE["workbook"], PROBE["view"])
    assert r.status_code == 200, (
        f"{url} -> {r.status_code} — Tableau workbook "
        f"{PROBE['workbook']}/{PROBE['view']} from SEED_CATALOG no longer exists"
    )
    assert r.headers["content-type"].startswith("application/json")

    body = r.json()
    assert body.get("sessionid"), f"{url} -> 200 but no sessionid in the response"
    assert body.get("workbookName"), (
        f"{url} -> 200 but no workbookName — resolved something other than a workbook"
    )

    # Sanity-check that embed_url() still builds a URL pointing at what we just
    # proved exists. Pure string construction, no network.
    assert f"/views/{PROBE['workbook']}/{PROBE['view']}" in embed_url(
        PROBE["workbook"], PROBE["view"]
    )


@pytest.mark.degraded_ok
def test_tableau_404s_a_missing_workbook(http):
    """Guards the failure mode that would make the probe above meaningless.

    If startSession ever starts answering 200 for anything, the coordinate check
    goes green on a dead dashboard. degraded_ok because this tests Tableau's
    manners, not whether Byggðastofnun's data is reachable.
    """
    url, r = _start_session(http, "NoSuchWorkbookXYZ", "nope")
    assert r.status_code == 404, (
        f"{url} -> {r.status_code}, expected 404 for a nonexistent workbook — "
        f"startSession may no longer be a valid existence check"
    )

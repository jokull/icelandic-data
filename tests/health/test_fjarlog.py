"""Health probe — fjárlög (state budget) on stjornarradid.is.

Contract, mirroring scripts/fjarlog.py:

  1. The budget year's "skjöl og gögn" page still links a `Talnagögn…csv`.
     fetch() discovers the URL from that HTML because the filename carries a
     revision suffix ("- 003.csv") that changes without notice — so the link
     regex, not the URL, is the thing that has to keep working.
  2. That CSV is still the semicolon-separated long table whose header carries
     every column `_RENAME` maps. A silent header rename would leave fetch()
     raising a polars rename error on a file that downloaded fine.

The CSV is a few MB, so the body check is a Range request for the first
kilobytes — enough to see the header and one data row, which is the whole
contract. Discovery is reimplemented here rather than calling
`_discover_csv_url`, which swallows HTTP errors and silently substitutes
`_FALLBACK_CSV` — exactly the failure this probe exists to surface.
"""
from __future__ import annotations

import pytest

from scripts.fjarlog import BASE, _CSV_LINK_RE, _RENAME, _gogn_url

# Matches the `fetch --year` default in scripts/fjarlog.py. Bump both together
# when the ministry publishes the next budget year.
YEAR = 2026


@pytest.fixture(scope="module")
def csv_url(http) -> str:
    """Discover the Talnagögn CSV the way fetch() does — from the page HTML."""
    url = _gogn_url(YEAR)
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]

    m = _CSV_LINK_RE.search(r.text)
    assert m, (
        f"no Talnagögn CSV link at {url} — _CSV_LINK_RE no longer matches, so "
        f"_discover_csv_url() would silently fall back to the pinned 2026 file"
    )
    from urllib.parse import urljoin

    return urljoin(BASE, m.group(1))


def test_gogn_page_links_the_talnagogn_csv(csv_url):
    assert csv_url.lower().endswith(".csv"), f"discovered link is not a CSV: {csv_url}"


def test_csv_header_still_carries_every_renamed_column(http, csv_url):
    """Range-request the head of the file — never the whole multi-MB CSV."""
    r = http.get(csv_url, headers={"Range": "bytes=0-2047"})
    assert r.status_code in (200, 206), f"{csv_url} -> {r.status_code}"

    text = r.content.decode("utf-8-sig", errors="replace")
    header = text.split("\n", 1)[0].strip()
    cols = {c.strip() for c in header.split(";")}
    missing = set(_RENAME) - cols
    assert not missing, f"{csv_url}: header lost columns {sorted(missing)}; got {sorted(cols)}"


def test_csv_body_is_semicolon_rows_of_the_expected_shape(http, csv_url):
    """One data row is enough to catch a delimiter or afurð-vocabulary change."""
    r = http.get(csv_url, headers={"Range": "bytes=0-4095"})
    assert r.status_code in (200, 206), f"{csv_url} -> {r.status_code}"

    text = r.content.decode("utf-8-sig", errors="replace")
    lines = text.split("\n")
    assert len(lines) > 2, f"{csv_url}: no data rows in the first 4 KB"

    row = lines[1].split(";")
    assert len(row) == len(_RENAME), f"row has {len(row)} fields, expected {len(_RENAME)}: {lines[1]!r}"

    year, afurd = row[0], row[1]
    assert year.isdigit(), f"first column is not a year: {year!r}"
    # The four data products the script's `products` command reports on. Rows
    # are ordered by year, so the head of the file is always the oldest afurð.
    assert afurd in {"Ríkisreikningur", "Fjárlög", "Frumvarp", "Áætlun"}, (
        f"unknown afurð {afurd!r} — the product vocabulary changed"
    )

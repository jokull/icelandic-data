"""Health probe — heimsmarkmið (Iceland's UN SDG statistics, open-sdg).

The site at heimsmarkmidin.hagstofa.is is a front end; the data lives in a
GitHub Pages repo. scripts/heimsmarkmid.py depends on three separate things
there, and they fail independently:

  1. `is/zip/all_indicators.zip` — the bundle fetch_zip() downloads.
  2. `is/data/<code>.csv` — the per-indicator CSVs the ZIP unpacks to, whose
     Year/Value columns build_catalog() parses. Probing one over HTTP checks
     the shape without unpacking the bundle.
  3. `is/meta/<code>.json` — deliberately *not* in the ZIP (open-sdg keeps meta
     live), so cmd_get() always hits the network for it. A working ZIP tells us
     nothing about whether meta is still served.

The ZIP is only ~450 KB but there is no reason to pull it: HEAD proves it is
served and sized plausibly, and the CSV probe covers the payload shape.
"""
from __future__ import annotations

from scripts.heimsmarkmid import DATA_BASE, ZIP_URL, _parse_code

# Goal 1 indicator, present since the site launched: share of the population
# below the international poverty line.
CODE = "1-1-1"


def test_indicator_bundle_is_served(http):
    """HEAD only — the probe never downloads the bundle."""
    r = http.head(ZIP_URL)
    assert r.status_code == 200, f"{ZIP_URL} -> {r.status_code}"

    ctype = r.headers.get("content-type", "")
    assert "zip" in ctype, f"{ZIP_URL} served as {ctype!r}, not a zip"

    # A GitHub Pages 404 page would still be a few KB, and the real bundle
    # covers 137 indicators. Loose floor, no ceiling — it only grows.
    size = int(r.headers.get("content-length", 0))
    assert size > 50_000, f"{ZIP_URL}: suspiciously small bundle, {size} bytes"


def test_indicator_csv_has_year_and_value_columns(http):
    """build_catalog() reads Year/Value and treats every other column as a
    disaggregation. Losing either would produce a silently empty catalog row."""
    url = f"{DATA_BASE}/is/data/{CODE}.csv"
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"

    lines = r.text.strip().split("\n")
    assert len(lines) > 1, f"{url}: header only, no data rows"

    header = {c.strip() for c in lines[0].split(",")}
    assert {"Year", "Value"} <= header, f"{url}: expected Year+Value, got {sorted(header)}"

    first_year = lines[1].split(",")[0]
    assert first_year.isdigit(), f"{url}: first Year is not numeric: {first_year!r}"


def test_indicator_meta_is_served_live(http):
    """Meta is never bundled — this is the only path cmd_get() has to it."""
    url = f"{DATA_BASE}/is/meta/{CODE}.json"
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"

    meta = r.json()
    assert isinstance(meta, dict) and meta, f"{url}: empty meta"
    # The fields cmd_get() prints. open-sdg emits them as empty strings rather
    # than omitting them, so presence — not truthiness — is the contract.
    expected = {"indicator_name", "graph_title", "computation_units", "graph_type"}
    missing = expected - set(meta)
    assert not missing, f"{url}: meta lost fields {sorted(missing)}"


def test_code_parsing_matches_the_published_codes(http):
    """_CODE_RE drives goal/target splitting for every catalog row. Guard it
    against a code-format change (e.g. goal 16's letter targets, `16-b-1`)."""
    url = f"{DATA_BASE}/is/meta/16-b-1.json"
    r = http.get(url)
    assert r.status_code == 200, f"{url} -> {r.status_code}"

    goal, target, indicator = _parse_code("16-b-1")
    assert (goal, target, indicator) == ("16", "b", "1"), (
        f"_parse_code no longer splits letter targets: {(goal, target, indicator)}"
    )

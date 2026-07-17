"""Health probe — Icelandic public procurement (TED API + OCDS bulk).

Two independent upstreams, mirroring scripts/tenders.py:

  1. TED v3 search API (api.ted.europa.eu) — live notices, queried with the
     expert query language. The fragile parts are the query grammar
     (`organisation-country-buyer=ISL`) and the multilingual field encoding
     that `_ted_field` unwraps: a field comes back as a plain string, a list,
     or a `{"eng": [...]}` dict depending on the field. This probes with
     limit=1, not a crawl.
  2. OCDS bulk (data.open-contracting.org publication 57 = Iceland) — a
     1.8 MB gzipped JSONL. HEAD proves it is served; a 64 KB Range request
     partially inflated proves the first release still has the ocid / buyer /
     tender keys extract_awards() reads. Never the full download.

Known discrepancy, deliberately not asserted: search_ted() reads
`data.get("total", 0)`, but the API returns the count as `totalNoticeCount`.
The script prints "Found 0 total" regardless. This probe asserts the real key —
pinning `total` would encode the bug and fail forever.
"""
from __future__ import annotations

import json
import zlib

import pytest

from scripts.tenders import OCDS_DOWNLOAD_URL, TED_API_URL, _ted_field

TED_FIELDS = [
    "notice-title",
    "publication-date",
    "organisation-name-buyer",
    "classification-cpv",
]


@pytest.fixture(scope="module")
def ted_notice(http) -> dict:
    """One notice — the smallest query that still exercises the grammar."""
    body = {
        "query": "organisation-country-buyer=ISL",
        "fields": TED_FIELDS,
        "limit": 1,
        "page": 1,
    }
    r = http.post(TED_API_URL, json=body)
    assert r.status_code == 200, f"{TED_API_URL} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    notices = payload.get("notices")
    assert notices, (
        f"{TED_API_URL}: query 'organisation-country-buyer=ISL' returned no notices — "
        f"the expert query grammar or the country code may have changed; "
        f"response keys {sorted(payload)}"
    )

    # Iceland has ~1.8k notices in TED. A loose floor catches a query that
    # silently degrades to matching almost nothing.
    total = payload.get("totalNoticeCount")
    assert isinstance(total, int) and total > 100, (
        f"{TED_API_URL}: implausible totalNoticeCount {total!r}"
    )
    return notices[0]


def test_ted_returns_the_requested_fields(ted_notice):
    missing = set(TED_FIELDS) - set(ted_notice)
    assert not missing, (
        f"TED dropped requested fields {sorted(missing)}; got "
        f"{sorted(k for k in ted_notice if k != 'links')}"
    )


def test_ted_field_unwrapping_still_works(ted_notice):
    """_ted_field flattens str / list / {lang: [...]} into a display string.
    If TED changes the encoding, every column in `search` goes blank — not an
    error, just empty output. Assert the unwrap actually yields text."""
    buyer = _ted_field(ted_notice, "organisation-name-buyer")
    assert buyer and isinstance(buyer, str), (
        f"buyer name did not unwrap: {ted_notice.get('organisation-name-buyer')!r}"
    )
    title = _ted_field(ted_notice, "notice-title")
    assert title and isinstance(title, str), (
        f"notice title did not unwrap: {type(ted_notice.get('notice-title')).__name__}"
    )
    assert str(ted_notice["publication-date"])[:4].isdigit(), (
        f"publication-date is not date-like: {ted_notice['publication-date']!r}"
    )


def test_ocds_bulk_is_served(http):
    """HEAD only — the probe never downloads the 1.8 MB bundle."""
    r = http.head(OCDS_DOWNLOAD_URL)
    assert r.status_code == 200, f"{OCDS_DOWNLOAD_URL} -> {r.status_code}"

    ctype = r.headers.get("content-type", "")
    assert "gzip" in ctype, f"{OCDS_DOWNLOAD_URL} served as {ctype!r}, not gzip"

    size = int(r.headers.get("content-length", 0))
    assert size > 100_000, f"{OCDS_DOWNLOAD_URL}: suspiciously small bundle, {size} bytes"


def test_ocds_first_release_has_the_keys_we_read(http):
    """Range-request 64 KB and inflate what arrives.

    Confirms publication 57 is still Iceland's and that releases still carry the
    fields extract_awards()/list_buyers() walk. `awards` is not asserted — not
    every release has one, and that is normal.
    """
    r = http.get(OCDS_DOWNLOAD_URL, headers={"Range": "bytes=0-65535"})
    assert r.status_code in (200, 206), f"{OCDS_DOWNLOAD_URL} -> {r.status_code}"

    # gzip-wrapped deflate; a truncated stream inflates fine up to the cut.
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        head = inflater.decompress(r.content)
    except zlib.error as exc:
        pytest.fail(f"{OCDS_DOWNLOAD_URL} is not gzip: zlib.error: {exc}")

    line = head.split(b"\n", 1)[0]
    try:
        release = json.loads(line)
    except json.JSONDecodeError as exc:
        pytest.fail(f"{OCDS_DOWNLOAD_URL}: first line is not JSONL: JSONDecodeError: {exc}")

    missing = {"ocid", "buyer", "tender"} - set(release)
    assert not missing, f"OCDS release lost keys {sorted(missing)}; got {sorted(release)}"
    assert release["ocid"].startswith("ocds-"), f"malformed ocid: {release['ocid']!r}"
    assert release["buyer"].get("name"), f"release has no buyer name: {release['buyer']}"

"""Health probe — Gasvaktin fuel-price data (upstream of scripts/fuel.py).

Contract: `scripts/fuel.py` does not fetch anything. It reads
`data/raw/gasvaktin/vaktin/trends.json` out of a shallow git clone of
github.com/gasvaktin/gasvaktin. So the upstream that can break is GitHub — the
repo, the file's path within it, and the record shape `load_trends()` unpacks.

Probed against GitHub directly rather than the local clone: a clone that is
present but six months stale would pass a filesystem check while the actual
source had gone away, and a probe must never re-clone into data/.

trends.json is ~1.8 MB — too big to pull on a schedule for a liveness check. So
existence and size come from the contents API (metadata only), and shape from a
1 KB ranged read of the real file. Between them they prove the file is there and
still looks like what the parser expects, at ~1/1800th the bytes.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from scripts.fuel import COMPANY_NAMES
from tests.health.conftest import assert_fresh

REPO = "gasvaktin/gasvaktin"
BRANCH = "master"
PATH = "vaktin/trends.json"

API = f"https://api.github.com/repos/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{PATH}"


def _skip_if_rate_limited(r) -> None:
    """Unauthenticated GitHub allows 60 API calls/hour per IP.

    A throttled probe has observed *nothing* about Gasvaktin, so it must report
    skipped. Failing would be worse than useless here: the classifier reads a
    bare 403 as structural — the never-transient kind — and would convict a
    perfectly healthy source after two throttled runs.
    """
    if r.status_code in (403, 429) and r.headers.get("x-ratelimit-remaining") == "0":
        reset = r.headers.get("x-ratelimit-reset", "?")
        pytest.skip(f"GitHub API rate limit exhausted (resets at {reset}) — probe inconclusive")


def test_trends_file_exists_at_the_documented_path(http):
    """Metadata only — proves the repo, branch and path still resolve."""
    r = http.get(f"{API}/contents/{PATH}", params={"ref": BRANCH})
    _skip_if_rate_limited(r)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    meta = r.json()
    assert meta.get("type") == "file", f"expected a file, got type={meta.get('type')!r}"
    assert meta.get("path") == PATH, f"path moved: {meta.get('path')!r}"
    # Floor, not an exact size — the file grows with every observation. This
    # only catches truncation-to-a-stub.
    assert meta.get("size", 0) > 100_000, f"trends.json suspiciously small: {meta.get('size')} bytes"


def test_trends_records_still_have_the_parsed_fields(http):
    """Ranged read — the first ~1 KB is enough to see one company's first record.

    load_trends() keys on the company codes and reads mean_bensin95 /
    mean_diesel / stations_count / timestamp off each entry. A rename upstream
    turns those into silent nulls in every processed CSV, which is exactly the
    failure this catches.
    """
    r = http.get(RAW, headers={"Range": "bytes=0-2047"})
    assert r.status_code in (200, 206), f"{r.request.url} -> {r.status_code}"

    head = r.text
    assert head.lstrip().startswith("{"), (
        f"trends.json no longer starts as a JSON object: {head[:80]!r}"
    )

    # The head of the file is a truncated object, so match on text rather than
    # parsing. The first key is a company code the script maps by name.
    first_code = head.split('"')[1]
    assert first_code in COMPANY_NAMES, (
        f"leading key {first_code!r} is not a known company code; "
        f"scripts/fuel.py knows {sorted(COMPANY_NAMES)}"
    )
    for field in ("mean_bensin95", "mean_diesel", "stations_count"):
        assert f'"{field}"' in head, (
            f"field {field!r} absent from the first trends.json record — "
            f"load_trends() would emit nulls"
        )


@pytest.mark.degraded_ok
def test_prices_are_still_being_committed(http):
    """Gasvaktin is a volunteer scraper committing to git. Stale-but-present is
    a real state for it, and a different problem from the repo being gone — so
    degraded, not failed. Observations land roughly weekly per company; two
    weeks without a commit means the collector has stopped."""
    r = http.get(f"{API}/commits", params={"path": PATH, "per_page": 1})
    _skip_if_rate_limited(r)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    commits = r.json()
    assert commits, f"no commits touching {PATH} at all"

    stamp = commits[0]["commit"]["committer"]["date"]
    committed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    assert_fresh(committed, timedelta(days=14), label="gasvaktin trends.json")

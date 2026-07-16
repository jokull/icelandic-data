"""Shared plumbing for upstream data-source health probes.

Health probes answer one question per source: *is the smallest stable contract
this repo depends on still there?* They are deliberately not fetch runs — no
full datasets, no PDF extraction, no geodata rebuilds. Probe the contract, not
the payload.

Everything under tests/health/ is auto-marked `slow` and `health`, so:

    uv run pytest -m "not slow"            # PR CI — never touches the network
    uv run pytest -m "health and not browser"   # daily scheduled run
    uv run pytest -m browser               # weekly / manual, Playwright probes

Probes must not write into data/ — they hold responses in memory.
"""
from __future__ import annotations

import pathlib

import httpx
import pytest

# Explicit connect + read timeouts. A hung upstream is a failure, not a wait.
TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)

# Retry connection-level errors only. httpx's transport retries apply to
# connect failures, never to a response that arrived — so a 500 or a schema
# change is reported on the first try rather than retried three times.
RETRIES = 2

USER_AGENT = "icelandic-data health probe (+https://github.com/jokull/icelandic-data)"


HEALTH_DIR = pathlib.Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Auto-mark everything in tests/health/ as `slow` + `health`.

    Keeps `pytest -m "not slow"` (the default addopts, and what PR CI runs)
    free of network calls without every probe repeating two decorators.

    A conftest hook in a subdirectory is still handed *every* collected item,
    not just the local ones — so filter by path or this marks the whole suite
    slow and PR CI silently runs nothing.
    """
    for item in items:
        if HEALTH_DIR in pathlib.Path(item.fspath).parents:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.health)


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    """Bounded HTTP client for probes."""
    with httpx.Client(
        timeout=TIMEOUT,
        transport=httpx.HTTPTransport(retries=RETRIES),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        yield client


def assert_fresh(observed, max_age, *, label: str) -> None:
    """Staleness assertion — a *degraded* signal, not a hard failure.

    Call only from tests marked `degraded_ok`, so a stale-but-working source
    reports as degraded rather than failing the scheduled run. An upstream that
    is up but three days behind is a different problem from one that is down.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age = now - observed
    assert age <= max_age, (
        f"{label} is stale: latest observation {observed.isoformat()} "
        f"is {age.total_seconds() / 3600:.1f}h old (limit {max_age.total_seconds() / 3600:.0f}h)"
    )

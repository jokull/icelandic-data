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
import re
from datetime import datetime

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


_FIXED_CLUSTER_RE = re.compile(r'"FixedClusterUri"\s*:\s*"https://([^"/]+)')


class PowerBIPublicEmbed:
    """Plain-HTTP client for the *public* ("publish to web") Power BI backend.

    Six sources in this repo are `app.powerbi.com/view?r=<base64>` embeds that
    the scripts scrape with Playwright. Those scrapes are not probeable daily —
    from a datacenter IP a headless-Chromium failure says more about bot
    detection than about the source. But the scrape's *precondition* is: the
    report key still exists and the report still has the pages we query. That
    is checkable over two plain GETs, exactly as the embed shell page itself
    does it before booting any JavaScript:

      1. GET the /view?r= shell. It is a static SPA page (a revoked key still
         returns 200 with byte-identical HTML — do NOT probe it for liveness),
         but the server stamps a per-tenant ``FixedClusterUri`` into it. That
         is the only way to learn which wabi-* cluster serves this tenant; they
         differ (west-europe, north-europe-q/-l/-n, europe-north-b …) and
         guessing wrong returns a misleading 401.
      2. GET ``/public/reports/<key>/modelsAndExploration`` on that cluster's
         APIM host with an ``X-PowerBI-ResourceKey`` header. A live key returns
         the model + the report's page list; an expired, revoked or
         un-republished key returns **401 UnableToFindKeyInDBorCacheException**.

    That 401 is the single most likely breakage for every one of these sources,
    and this is how it surfaces without a browser.
    """

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def cluster_api_host(self, view_url: str) -> str:
        """Resolve the tenant's wabi-* APIM host from the embed shell page.

        Mirrors the shell's own ``getAPIMUrl()``: drop ``-redirect``/``global-``
        from the first label, append ``-api``.
        """
        r = self._http.get(view_url)
        assert r.status_code == 200, f"{view_url} -> {r.status_code}"

        match = _FIXED_CLUSTER_RE.search(r.text)
        assert match, (
            f"{view_url} -> 200 but no FixedClusterUri in the embed shell — "
            f"Power BI changed the publish-to-web bootstrap; re-check how the "
            f"cluster is resolved"
        )
        host = match.group(1)
        label, _, domain = host.partition(".")
        label = label.replace("-redirect", "").replace("global-", "") + "-api"
        return f"{label}.{domain}"

    def model(self, view_url: str, report_key: str) -> dict:
        """Return modelsAndExploration for a public embed. Asserts the key lives."""
        host = self.cluster_api_host(view_url)
        url = (
            f"https://{host}/public/reports/{report_key}"
            f"/modelsAndExploration?preferReadOnlySession=true"
        )
        r = self._http.get(
            url,
            headers={"Accept": "application/json", "X-PowerBI-ResourceKey": report_key},
        )
        assert r.status_code == 200, (
            f"{url} -> {r.status_code}: {r.text[:200]} "
            f"(401 = report key {report_key} no longer published to web)"
        )
        payload = r.json()
        assert payload.get("models"), f"{url} -> 200 but no models; got {sorted(payload)}"
        return payload

    @staticmethod
    def sections(payload: dict) -> dict[str, str]:
        """{sectionName: displayName} — the report's pages."""
        return {
            s["name"]: s.get("displayName", "")
            for s in payload.get("exploration", {}).get("sections", [])
        }

    @staticmethod
    def last_refresh(payload: dict) -> datetime:
        """When the embedded dataset last refreshed (naive UTC)."""
        stamp = payload["models"][0].get("LastRefreshTime")
        assert stamp, f"model has no LastRefreshTime; got {sorted(payload['models'][0])}"
        return datetime.fromisoformat(stamp)


@pytest.fixture(scope="session")
def powerbi(http) -> PowerBIPublicEmbed:
    """Plain-HTTP probe helper for public Power BI embeds — see the class."""
    return PowerBIPublicEmbed(http)


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

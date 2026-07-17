"""Health probe — exchange rates: Borgun card rates + ECB via frankfurter.

Contract: scripts/gengi.py has two independent upstreams and either can break
on its own, so they get a probe each.

  1. Borgun  — an XML endpoint of current *card* rates (consumer markup). Parsed
     with ElementTree over `.//Rate` -> CurrencyCode / CurrencyRate.
  2. frankfurter.dev — ECB reference rates for history, queried base=ISK over a
     date range. The script inverts the response (`1 / val`), so a zero or a
     missing symbol is a ZeroDivisionError / KeyError downstream.

No rate *values* are asserted — only types and orders of magnitude. A probe that
pins the króna to a number is a probe that fails on a currency move rather than
on a broken source.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from xml.etree import ElementTree

import pytest

from scripts.gengi import BORGUN_URL, FRANKFURTER_URL
from tests.health.conftest import assert_fresh

# Wide sanity bands for ISK per 1 unit. Present to catch a units change or an
# inverted response, not to track the market.
PLAUSIBLE_ISK = (30.0, 500.0)


@pytest.fixture(scope="module")
def borgun(http):
    r = http.get(BORGUN_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    root = ElementTree.fromstring(r.text)
    assert root.tag == "Rates", f"expected <Rates>, got <{root.tag}>"

    status = root.findtext(".//Status/ResultCode")
    assert status == "0", (
        f"Borgun reports ResultCode={status!r} "
        f"({root.findtext('.//Status/ResultText')!r})"
    )
    return root


def test_borgun_serves_the_major_currencies(borgun):
    """fetch_current_rates() walks `.//Rate` and reads CurrencyCode +
    CurrencyRate. Both the traversal and the majors are asserted."""
    rates = borgun.findall(".//Rate")
    assert rates, "no <Rate> elements — the XML shape changed"

    parsed = {
        el.findtext("CurrencyCode", "").strip(): el.findtext("CurrencyRate", "").strip()
        for el in rates
    }
    parsed.pop("", None)

    missing = {"USD", "EUR", "GBP", "DKK"} - set(parsed)
    assert not missing, f"missing currencies {sorted(missing)}; got {len(parsed)} codes"

    for code in ("USD", "EUR", "GBP"):
        value = float(parsed[code])  # the script does exactly this, unguarded
        low, high = PLAUSIBLE_ISK
        assert low < value < high, (
            f"{code} at {value} ISK is outside the sanity band {PLAUSIBLE_ISK} — "
            f"suspect a units change or an inverted quote, not a market move"
        )


@pytest.mark.degraded_ok
def test_borgun_rates_are_current(borgun):
    """Card rates refresh on business days. A frozen RateDate means Borgun is
    serving a cached sheet — degraded, since the endpoint still answers."""
    stamp = borgun.findtext(".//Rate/RateDate")
    assert stamp, "no RateDate on the first <Rate>"

    # dd.m.yyyy — not zero-padded upstream.
    observed = datetime.strptime(stamp.strip(), "%d.%m.%Y")
    # 5 days absorbs a long weekend plus an Icelandic public holiday.
    assert_fresh(observed, timedelta(days=5), label="borgun card rates")


def test_frankfurter_returns_an_invertible_series(http):
    """A 3-day window, not the 6-month default the CLI uses.

    Asserts the response is invertible, because fetch_historical_rates() does
    `1 / val` on every cell with only a falsy guard.
    """
    r = http.get(
        f"{FRANKFURTER_URL}/2025-01-06..2025-01-08",
        params={"base": "ISK", "symbols": "USD,EUR"},
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json")

    payload = r.json()
    assert payload.get("base") == "ISK", f"base is {payload.get('base')!r}, not ISK"
    assert "rates" in payload, f"no 'rates' key; got {sorted(payload)}"

    rates = payload["rates"]
    assert rates, "empty series for a known-good historical window"

    day, quotes = sorted(rates.items())[0]
    assert datetime.strptime(day, "%Y-%m-%d"), f"unparseable date key {day!r}"
    assert {"USD", "EUR"} <= set(quotes), f"symbols filter ignored: got {sorted(quotes)}"

    for code, value in quotes.items():
        assert isinstance(value, (int, float)), f"{code} is {type(value).__name__}, not numeric"
        assert value > 0, f"{code} quoted at {value} — the script would divide by zero"
        low, high = PLAUSIBLE_ISK
        inverted = 1 / value
        assert low < inverted < high, (
            f"{code} inverts to {inverted:.1f} ISK, outside {PLAUSIBLE_ISK} — "
            f"the base= direction may have flipped"
        )

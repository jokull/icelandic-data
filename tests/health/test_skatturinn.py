"""Health probe — Skatturinn fyrirtækjaskrá (company registry).

Contract, and the thing to know before editing: **the skill file says this
source needs Playwright — it does not.** `scripts/skatturinn.py` scrapes the
company page with plain httpx and regexes (see its module docstring: "Uses
httpx for plain HTTP requests — no browser automation needed"). Only the
shopping-cart PDF download flow ever needed a browser. So this probe is
unmarked rather than `browser`: it tests what the code actually calls.

Probed here is the one page every code path starts from —
`/fyrirtaekjaskra/leit/kennitala/{kt}` — and the two HTML structures the
regexes depend on:

  1. `<h1>Name (kennitala)</h1>`      -> get_company_info() name extraction
  2. `<td data-itemid=… data-typeid=…>` -> the annual-report rows, and the
     itemid/typeid pair download_annual_report() feeds to the cart service

This is a registry lookup, so one page fetch per run — the cart/download flow
is deliberately not probed. It mutates server-side session state and would mean
hammering an endpoint the skill itself asks us to rate-limit to one request per
three seconds.
"""
from __future__ import annotations

import re

import pytest

from scripts.skatturinn import _HTTP_HEADERS

BASE = "https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala"

# Festi hf. — listed, decades old, files every year. A stable probe target.
KENNITALA = "5402062010"
NAME = "Festi hf."


@pytest.fixture(scope="module")
def page(http):
    r = http.get(f"{BASE}/{KENNITALA}", headers=_HTTP_HEADERS)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]

    html = r.text
    # The sentinel get_company_info() treats as "no such company". Seeing it for
    # a live kennitala means the lookup route changed, not that Festi vanished.
    assert "engri niðurstöðu" not in html and "Engin fyrirtæki fundust" not in html, (
        f"{r.request.url} -> 200 but reports no results for {KENNITALA}"
    )
    return html


def test_company_name_is_in_the_h1(page):
    """get_company_info() reads the name out of the h1 and strips the trailing
    "(kennitala)". Both halves of that assumption are asserted here."""
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    assert h1, "no <h1> on the company page"

    text = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
    assert NAME in text, f"expected {NAME!r} in h1, got {text!r}"
    assert re.search(r"\(\d{6}-?\d{4}\)", text), (
        f"h1 no longer carries a '(kennitala)' suffix: {text!r} — the strip "
        f"regex in get_company_info() would leave it in the name"
    )


def test_annual_report_rows_carry_itemid_and_typeid(page):
    """The report table is the whole point of the page.

    download_annual_report() needs both attributes: itemid identifies the
    report, typeid selects the format (1 = PDF ársreikningur, which the script
    prefers). Encoding is checked here too — the page is UTF-8 and the script's
    Icelandic marker strings only match if it decoded correctly.
    """
    pairs = re.findall(r'data-itemid="(\d+)"\s+data-typeid="(\d+)"', page)
    assert pairs, "no data-itemid/data-typeid rows — the report table markup changed"

    typeids = {typeid for _, typeid in pairs}
    assert "1" in typeids, (
        f"no typeid=1 (PDF ársreikningur) rows; got typeids {sorted(typeids)} — "
        f"download_annual_report() prefers typeid=1 and would fall through"
    )
    assert "Ársreikningur" in page, (
        "the string 'Ársreikningur' is absent — either the page is no longer "
        "UTF-8 decoded, or the report table was relabelled"
    )

"""
Currency exchange rates — current card rates (Borgun) + historical ECB reference rates.

Usage:
    uv run python scripts/gengi.py                        # Current rates, all currencies
    uv run python scripts/gengi.py USD,EUR,GBP            # Current rates, specific codes
    uv run python scripts/gengi.py USD,EUR --history 6m    # Historical rates, last 6 months
    uv run python scripts/gengi.py USD --history 1y        # Historical rates, last year
    uv run python scripts/gengi.py EUR --history 5y        # Historical rates, last 5 years

Sources:
    Current: Borgun card rates (consumer markup, not interbank)
    Historical: ECB reference rates via frankfurter.dev (daily, interbank)
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

BORGUN_URL = "https://www.borgun.is/currency/Default.aspx?function=all"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1"


def fetch_current_rates(codes: list[str] | None = None) -> dict[str, dict]:
    """Fetch current card rates from Borgun."""
    resp = httpx.get(BORGUN_URL)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    rates = {}
    for rate_el in root.findall(".//Rate"):
        code = rate_el.findtext("CurrencyCode", "").strip()
        description = rate_el.findtext("CurrencyDescription", "").strip()
        value = rate_el.findtext("CurrencyRate", "").strip()
        if not code or not value:
            continue

        entry: dict = {"rate": float(value)}
        if description:
            parts = [p.strip() for p in description.split(",")]
            parts.reverse()
            entry["description"] = " ".join(parts).capitalize()

        rates[code] = entry

    if codes:
        rates = {k: v for k, v in rates.items() if k in codes}

    return rates


def parse_period(period: str) -> date:
    """Parse a period string like '6m', '1y', '30d' into a start date."""
    m = re.match(r"^(\d+)([dmy])$", period.lower())
    if not m:
        raise ValueError(f"Invalid period: {period}. Use e.g. 30d, 6m, 1y, 5y")
    n, unit = int(m.group(1)), m.group(2)
    today = date.today()
    if unit == "d":
        return today - timedelta(days=n)
    elif unit == "m":
        month = today.month - n
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        day = min(today.day, 28)
        return date(year, month, day)
    else:  # y
        return date(today.year - n, today.month, min(today.day, 28))


def fetch_historical_rates(
    codes: list[str], period: str = "6m"
) -> dict:
    """Fetch historical ECB reference rates via frankfurter.dev.

    Returns ISK per unit of foreign currency (inverted from the API's
    foreign-per-ISK format) so rates are directly comparable to Borgun.
    """
    start = parse_period(period)
    end = date.today()
    symbols = ",".join(codes)
    url = f"{FRANKFURTER_URL}/{start}..{end}?base=ISK&symbols={symbols}"

    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # API returns foreign currency per 1 ISK — invert to get ISK per 1 foreign
    rows = []
    for dt, rates in sorted(data["rates"].items()):
        row = {"date": dt}
        for code, val in rates.items():
            row[code] = round(1 / val, 2) if val else None
        rows.append(row)

    return {
        "base": "ISK",
        "start": str(start),
        "end": str(end),
        "currencies": codes,
        "rows": rows,
    }


def main():
    codes = None
    history = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--history":
            history = args[i + 1] if i + 1 < len(args) else "6m"
            i += 2
        elif not codes:
            codes = [c.strip().upper() for c in args[i].split(",")]
            i += 1
        else:
            i += 1

    if history:
        if not codes:
            codes = ["USD", "EUR", "GBP"]
        result = fetch_historical_rates(codes, history)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        rates = fetch_current_rates(codes)
        print(json.dumps(rates, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

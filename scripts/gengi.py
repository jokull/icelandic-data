"""
Currency exchange rates from Borgun.

Usage:
    uv run python scripts/gengi.py              # All currencies
    uv run python scripts/gengi.py USD,EUR,GBP  # Specific codes
"""

import json
import sys
import xml.etree.ElementTree as ET

import httpx

BORGUN_URL = "https://www.borgun.is/currency/Default.aspx?function=all"


def fetch_rates(codes: list[str] | None = None) -> dict[str, dict]:
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
            # "Dollar, US" -> "US Dollar"
            parts = [p.strip() for p in description.split(",")]
            parts.reverse()
            entry["description"] = " ".join(parts).capitalize()

        rates[code] = entry

    if codes:
        rates = {k: v for k, v in rates.items() if k in codes}

    return rates


def main():
    codes = None
    if len(sys.argv) > 1:
        codes = [c.strip().upper() for c in sys.argv[1].split(",")]

    rates = fetch_rates(codes)
    print(json.dumps(rates, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

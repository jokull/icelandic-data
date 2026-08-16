"""
Aggregates Icelandic + global macro indicators into data/processed/dashboard.json,
published to GitHub Pages for a personal (Austrian-econ-lens) understanding tool —
not a trading terminal. Each metric is deliberately minimal: latest value, one
period-over-period change, and where it came from.

Thin layer on top of existing fetchers — does not duplicate their parsing:
  - Seðlabanki XML time series (scripts/sedlabanki_fx.py): reuses read_mid_rate()
    for meginvextir + USD/EUR mid rates (all three are single-series xmltimeseries
    CSVs, same shape sedlabanki_fx.py already parses for the EUR mid rate).
  - Hagstofa PX-Web (see .agents/skills/hagstofan/SKILL.md): headline CPI, one
    table hit — VIS01000.px already returns the 12-month change (Liður=change_A)
    computed upstream, so there is no YoY math to get wrong here.

New for this script (see .agents/skills/lanamal/SKILL.md and .agents/skills/dashboard/SKILL.md):
  - lanamal.is (Government Debt Management) bond market API for RIKB yields
  - FRED (St. Louis Fed) for US/global series
  - CoinGecko for BTC (ISK leg is derived from our own USD/ISK mid rate — CoinGecko
    does not quote ISK directly)

A failure in any single source must not stop the others: this script always
writes whatever metrics it managed to fetch, and only exits non-zero if NOTHING
came back at all.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from sedlabanki_fx import XML_BASE, read_mid_rate  # noqa: E402  (reuse, not duplicate)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "dashboard"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = PROCESSED_DIR / "dashboard.json"

FRED_API_KEY = os.environ.get("FRED_API_KEY")

SEDLABANKI = ("Seðlabanki Íslands", "https://sedlabanki.is/")
HAGSTOFAN = ("Hagstofa Íslands", "https://hagstofa.is/")
LANAMAL = ("Lánamál ríkisins", "https://www.lanamal.is/")
COINGECKO = ("CoinGecko", "https://www.coingecko.com/en/coins/bitcoin")

IS_MONTHS = [
    "janúar", "febrúar", "mars", "apríl", "maí", "júní",
    "júlí", "ágúst", "september", "október", "nóvember", "desember",
]


def is_date(d: date) -> str:
    return f"{d.day}. {IS_MONTHS[d.month - 1]} {d.year}"


def is_month(d: date) -> str:
    return f"{IS_MONTHS[d.month - 1]} {d.year}"


def metric(
    value: float,
    change: float,
    change_type: str,
    label: str,
    source: tuple[str, str],
    decimals: int = 2,
    suffix: str = "%",
    change_decimals: int | None = None,
) -> dict[str, Any]:
    """change_decimals defaults to `decimals`, but a metric shown with 0 decimals
    (e.g. whole-dollar BTC price) still needs its % change rounded with more
    precision than that, or small moves silently become 0."""
    name, url = source
    return {
        "value": round(value, decimals),
        "change": round(change, change_decimals if change_decimals is not None else decimals),
        "change_type": change_type,
        "label": label,
        "source": name,
        "source_url": url,
        "decimals": decimals,
        "suffix": suffix,
    }


def last_change(dates: list[date], values: list[float]) -> tuple[date, float, float]:
    """Latest (date, value), plus the diff vs the most recent *different* earlier
    value — for a step-like series (e.g. a policy rate) this recovers the size and
    date of the last actual change; for a series that moves every observation
    (FX, bond yields) it is just the latest period-over-period move."""
    latest_date, latest_val = dates[-1], values[-1]
    prev_val = latest_val
    for v in reversed(values[:-1]):
        if v != latest_val:
            prev_val = v
            break
    return latest_date, latest_val, latest_val - prev_val


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True)


# --- Seðlabanki: meginvextir + USD/EUR mid rates (xmltimeseries, direct HTTP) ---

def fetch_xml_series(client: httpx.Client, ts_id: int, name: str, days_back: int) -> pl.DataFrame:
    since = (date.today() - timedelta(days=days_back)).isoformat()
    r = client.get(XML_BASE, params={"DagsFra": since, "TimeSeriesID": ts_id, "Type": "csv"})
    r.raise_for_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{name}.csv"
    out.write_bytes(r.content)
    return read_mid_rate(out)  # generic single-series parser from sedlabanki_fx.py


def build_policy_rate(client: httpx.Client) -> dict | None:
    # 730-day window: meginvextir only moves on CB board decisions (~6/year),
    # so a short window risks never finding the previous distinct value.
    df = fetch_xml_series(client, 17923, "meginvextir_daily", days_back=730)
    d, val, chg = last_change(df["date"].to_list(), df["mid_rate"].to_list())
    return metric(val, chg, "pp", is_date(d), SEDLABANKI, decimals=2, suffix="%")


def build_fx_mid(client: httpx.Client, ts_id: int, name: str) -> dict | None:
    df = fetch_xml_series(client, ts_id, name, days_back=60)
    d, val, chg = last_change(df["date"].to_list(), df["mid_rate"].to_list())
    prev = val - chg
    chg_pct = (chg / prev * 100) if prev else 0.0
    return metric(val, chg_pct, "pct", is_date(d), SEDLABANKI, decimals=2, suffix=" kr.")


# --- Hagstofa: headline CPI, level + 12mo change in one PX-Web hit -------------

def build_cpi_is(client: httpx.Client) -> dict | None:
    url = "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/visitolur/1_vnv/1_vnv/VIS01000.px"
    meta = client.get(url).json()
    latest_month = meta["variables"][0]["values"][-1]  # e.g. "2026M07"
    body = {
        "query": [
            {"code": "Mánuður", "selection": {"filter": "item", "values": [latest_month]}},
            {"code": "Vísitala", "selection": {"filter": "item", "values": ["CPI"]}},
            {"code": "Liður", "selection": {"filter": "item", "values": ["index", "change_A"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    r = client.post(url, json=body)
    r.raise_for_status()
    idx, chg_a = r.json()["value"]
    year, mon = int(latest_month[:4]), int(latest_month[5:7])
    return metric(idx, chg_a, "pct", is_month(date(year, mon, 1)), HAGSTOFAN, decimals=1, suffix="")


# --- Lánamál ríkisins: RIKB government bond yields (new source) ---------------
# See .agents/skills/lanamal/SKILL.md for how this endpoint was found and why
# we read the daily chartData series rather than the top-level closingYield
# field (which reflects the last actual trade — stale for a thinly-traded bond
# — instead of the market-maker's daily fixing).

LANAMAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; icelandic-data-dashboard/1.0)",
    "Accept": "application/json",
}


def build_bond(client: httpx.Client, orderbook_id: str) -> dict | None:
    r = client.get(
        "https://www.lanamal.is/api/market/LoadIndexedDetail",
        params={"orderbookId": orderbook_id, "lang": "is"},
        headers={
            **LANAMAL_HEADERS,
            "Referer": f"https://www.lanamal.is/markadsyfirlit/?type=bond&orderbookid={orderbook_id.lower()}",
        },
    )
    r.raise_for_status()
    data = r.json()[0]
    chart = data["chartData"]["chartData"]  # [[iso_datetime, yield_pct], ...] ascending
    if not chart:
        return None
    dates = [datetime.fromisoformat(pt[0]).date() for pt in chart]
    values = [float(pt[1]) for pt in chart]
    d, val, chg = last_change(dates, values)
    return metric(val, chg, "pp", is_date(d), LANAMAL, decimals=2, suffix="%")


# --- FRED: US treasuries, Fed funds, CPI, Brent, gold --------------------------

def fred_source(series_id: str) -> tuple[str, str]:
    return ("FRED (Federal Reserve Bank of St. Louis)", f"https://fred.stlouisfed.org/series/{series_id}")


def fetch_fred_obs(client: httpx.Client, series_id: str, limit: int) -> list[tuple[date, float]]:
    r = client.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        },
    )
    r.raise_for_status()
    out = []
    for o in r.json()["observations"]:
        if o["value"] == ".":  # FRED's own "no observation" marker
            continue
        out.append((date.fromisoformat(o["date"]), float(o["value"])))
    out.reverse()
    return out


def build_fred_rate(client: httpx.Client, series_id: str) -> dict | None:
    """Daily rate/yield series (DGS5, DGS30, DFF) — change in percentage points."""
    obs = fetch_fred_obs(client, series_id, limit=120)
    if not obs:
        return None
    dates, values = zip(*obs)
    d, val, chg = last_change(list(dates), list(values))
    return metric(val, chg, "pp", is_date(d), fred_source(series_id), decimals=2, suffix="%")


def build_fred_price(client: httpx.Client, series_id: str) -> dict | None:
    """Daily price series (oil, gold) — change as a relative percentage."""
    obs = fetch_fred_obs(client, series_id, limit=30)
    if not obs:
        return None
    dates, values = zip(*obs)
    d, val, chg = last_change(list(dates), list(values))
    prev = val - chg
    chg_pct = (chg / prev * 100) if prev else 0.0
    return metric(val, chg_pct, "pct", is_date(d), fred_source(series_id), decimals=2, suffix=" USD")


def build_fred_cpi_us(client: httpx.Client) -> dict | None:
    """CPIAUCSL is monthly — compute 12-month YoY ourselves (unlike VNV, FRED
    doesn't hand us the change pre-computed)."""
    obs = fetch_fred_obs(client, "CPIAUCSL", limit=15)
    if len(obs) < 13:
        return None
    d, val = obs[-1]
    _, val_12mo_ago = obs[-13]
    yoy = (val - val_12mo_ago) / val_12mo_ago * 100
    return metric(val, yoy, "pct", is_month(d), fred_source("CPIAUCSL"), decimals=1, suffix="")


# --- CoinGecko: BTC (ISK leg derived from our own USD/ISK mid rate) -----------

def build_btc(client: httpx.Client, usd_isk_mid: float | None) -> tuple[dict | None, dict | None]:
    r = client.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true"},
    )
    r.raise_for_status()
    d = r.json()["bitcoin"]
    usd_val = float(d["usd"])
    chg_pct = float(d.get("usd_24h_change") or 0.0)
    today = is_date(date.today())
    btc_usd = metric(usd_val, chg_pct, "pct", today, COINGECKO, decimals=0, suffix=" USD", change_decimals=2)
    if usd_isk_mid is None:
        return btc_usd, None
    btc_isk = metric(
        usd_val * usd_isk_mid, chg_pct, "pct", today, COINGECKO,
        decimals=0, suffix=" kr.", change_decimals=2,
    )
    return btc_usd, btc_isk


# --- Orchestration --------------------------------------------------------------

def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    metrics: dict[str, dict] = {}

    def add(key: str, fn: Callable, *args) -> None:
        try:
            result = fn(*args)
            if result is not None:
                metrics[key] = result
                print(f"  ok    {key}: {result['value']}{result['suffix']}")
            else:
                print(f"  skip  {key} (no data)")
        except Exception as e:
            print(f"  FAIL  {key}: {e}", file=sys.stderr)
            traceback.print_exc()

    with _client() as client:
        print("Innlend (Seðlabanki + Hagstofa)...")
        add("policy_rate_is", build_policy_rate, client)
        add("cpi_is", build_cpi_is, client)
        add("usdisk", build_fx_mid, client, 4055, "usd_mid_daily")
        add("eurisk", build_fx_mid, client, 4064, "eur_mid_daily")
        add("bond_5y_is", build_bond, client, "RIKB_31_0124")
        add("bond_long_is", build_bond, client, "RIKB_42_0217")

        print("Erlend (FRED)...")
        if not FRED_API_KEY:
            print("  WARNING: FRED_API_KEY not set — skipping all FRED metrics", file=sys.stderr)
        else:
            add("treasury_5y_us", build_fred_rate, client, "DGS5")
            add("treasury_30y_us", build_fred_rate, client, "DGS30")
            add("fed_funds_rate", build_fred_rate, client, "DFF")
            add("cpi_us", build_fred_cpi_us, client)
            add("oil_brent", build_fred_price, client, "DCOILBRENTEU")
            # No gold metric: FRED discontinued GOLDAMGBD228NLBM (LBMA fixing) —
            # the series 400s. No free source with both a live price AND history
            # (for the change calc) was found; revisit if one turns up.

        print("Markaðir (CoinGecko)...")
        try:
            usd_isk_mid = metrics.get("usdisk", {}).get("value")
            btc_usd, btc_isk = build_btc(client, usd_isk_mid)
            if btc_usd:
                metrics["btc_usd"] = btc_usd
                print(f"  ok    btc_usd: {btc_usd['value']}{btc_usd['suffix']}")
            if btc_isk:
                metrics["btc_isk"] = btc_isk
                print(f"  ok    btc_isk: {btc_isk['value']}{btc_isk['suffix']}")
        except Exception as e:
            print(f"  FAIL  btc: {e}", file=sys.stderr)
            traceback.print_exc()

    if not metrics:
        print("\nERROR: no metrics fetched from any source", file=sys.stderr)
        sys.exit(1)

    out = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": metrics,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(metrics)} metrics to {OUT_PATH}")


if __name__ == "__main__":
    main()

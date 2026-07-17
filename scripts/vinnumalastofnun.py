"""Vinnumálastofnun (Directorate of Labour) — mælaborð + Excel fetcher.

Two sources combined:
  1. Power BI dashboard "Gagnvirk tölfræði Vinnumálastofnunar"
  2. Excel workbook "Helstu talnagögn um atvinnuleysi"

Usage:
    uv run python scripts/vinnumalastofnun.py fetch     # both
    uv run python scripts/vinnumalastofnun.py excel     # Excel only
    uv run python scripts/vinnumalastofnun.py powerbi   # Power BI only
"""
import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "vinnumalastofnun"

POWERBI_TENANT = "764a306d-0a68-45ad-9f07-6f1804447cd4"
POWERBI_REPORT_KEY = "e74521bb-e501-4b02-8aa2-08a8bb84d087"
POWERBI_PAGE = "ReportSection7e7dca64570c18a74eb9"

# Contentful serves each upload at a fresh, content-addressed asset URL — the
# old one keeps working forever, so a stale constant here silently pins us to an
# old workbook rather than 404ing. The current URL is the one linked from
# LANDING; tests/health/test_vinnumalastofnun.py compares the two and reports
# degraded when they drift apart.
LANDING = "https://island.is/s/vinnumalastofnun/maelabord-og-toelulegar-upplysingar"
EXCEL_URL = (
    "https://assets.ctfassets.net/8k0h54kbe6bj/6X68LGOlf4zSrosSlpBnEV/"
    "a52ab7855e63039569523b912cd005b3/Talnagogn_atvinnuleysi.xlsm"
)


def _embed_url() -> str:
    payload = {"k": POWERBI_REPORT_KEY, "t": POWERBI_TENANT, "c": 8}
    token = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"https://app.powerbi.com/view?r={token}&pageName={POWERBI_PAGE}"


def cmd_excel(args=None):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "Talnagogn_atvinnuleysi.xlsm"
    print(f"Downloading {EXCEL_URL}", file=sys.stderr)
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        r = c.get(EXCEL_URL)
        r.raise_for_status()
        out.write_bytes(r.content)
    print(f"  → {out} ({len(r.content):,} bytes)", file=sys.stderr)


async def _scrape_powerbi() -> list[dict]:
    from playwright.async_api import async_playwright

    url = _embed_url()
    results: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def on_response(r):
                u = r.url.lower()
                if ("querydata" in u or "executequeries" in u) and r.status == 200:
                    try:
                        results.append(await r.json())
                    except Exception:
                        pass

            page.on("response", on_response)
            print(f"Loading {url}", file=sys.stderr)
            await page.goto(url, wait_until="networkidle", timeout=90000)
            await asyncio.sleep(15)
        finally:
            await browser.close()
    return results


def cmd_powerbi(args=None):
    results = asyncio.run(_scrape_powerbi())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "powerbi.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  captured {len(results)} query responses → {out}", file=sys.stderr)


def cmd_fetch(args=None):
    cmd_excel()
    cmd_powerbi()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("fetch", cmd_fetch), ("excel", cmd_excel), ("powerbi", cmd_powerbi)]:
        p = sub.add_parser(name)
        p.set_defaults(func=fn)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

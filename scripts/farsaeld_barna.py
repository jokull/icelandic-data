"""Farsæld barna (Child Wellbeing Dashboard) — Power BI scraper.

Single Power BI embed from Barna- og fjölskyldustofa (BOFS), aggregating child
wellbeing indicators.

Usage:
    uv run python scripts/farsaeld_barna.py fetch
"""
import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "farsaeld_barna"

TENANT = "bc14a44e-e0fb-4e0b-a535-100579d41b65"
REPORT_KEY = "1fcb76a3-b53d-4ba1-a5c9-434d8c346408"


def embed_url() -> str:
    payload = {"k": REPORT_KEY, "t": TENANT, "c": 8}
    token = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"https://app.powerbi.com/view?r={token}"


async def _scrape() -> list[dict]:
    from playwright.async_api import async_playwright

    url = embed_url()
    results: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def on_response(r):
                u = r.url.lower()
                wanted = (
                    u.startswith("blob:")
                    or "querydata" in u
                    or "executequeries" in u
                    or "modelsandexploration" in u
                    or "conceptualschema" in u
                    or "resourcepackage" in u
                )
                if wanted and r.status == 200:
                    try:
                        body = await r.json()
                        results.append({"url": r.url, "body": body})
                        return
                    except Exception:
                        pass
                    try:
                        text = await r.text()
                        if text:
                            results.append({"url": r.url, "text": text[:200000]})
                    except Exception:
                        pass

            page.on("response", on_response)
            print(f"Loading {url}", file=sys.stderr)
            await page.goto(url, wait_until="networkidle", timeout=90000)
            await asyncio.sleep(25)
        finally:
            await browser.close()
    return results


def cmd_fetch(args=None):
    results = asyncio.run(_scrape())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "powerbi.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  captured {len(results)} query responses → {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch")
    p.set_defaults(func=cmd_fetch)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

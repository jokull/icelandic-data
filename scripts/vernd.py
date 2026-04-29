"""Lykilupplýsingar um vernd — international-protection (asylum) dashboard.

Power BI `/view?r=...` public embed published by Ríkislögreglustjóri (National
Commissioner of Police). Monthly key stats on applicants for international
protection in Iceland — counts, nationality, decisions, processing time.

Same scrape pattern as `landlaeknir`: headless Chromium intercepts
`querydata`/`executeQueries` responses from the Power BI backend.

Usage:
    uv run python scripts/vernd.py info          # Print embed URL + metadata
    uv run python scripts/vernd.py fetch         # Scrape Power BI query responses
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

REPORT_KEY = "a2a07353-0f55-40d2-b761-bab29aba67bc"
TENANT = "509484a8-c0ff-4960-b5da-3bdb75e98460"
# Cluster number — public embeds commonly use 8, this one is 9.
# Visible in the base64-decoded embed payload on stjornarradid.is.
CLUSTER = 9

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "vernd"


def embed_url() -> str:
    payload = {"k": REPORT_KEY, "t": TENANT, "c": CLUSTER}
    token = (
        base64.b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    return f"https://app.powerbi.com/view?r={token}"


def cmd_info(args=None):
    print("Lykilupplýsingar um vernd — umsækjendur um alþjóðlega vernd")
    print(f"  owner       : Ríkislögreglustjóri")
    print(f"  tenant      : {TENANT}")
    print(f"  report key  : {REPORT_KEY}")
    print(f"  cluster     : {CLUSTER}")
    print(f"  embed URL   : {embed_url()}")


async def _scrape() -> list[dict]:
    from playwright.async_api import async_playwright

    results: list[dict] = []
    url = embed_url()
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
            print(f"  loading {url}", file=sys.stderr)
            await page.goto(url, wait_until="networkidle", timeout=90000)
            # Power BI does not reliably fire networkidle; give DAX calls
            # time to flow after the visuals mount.
            await asyncio.sleep(15)
        finally:
            await browser.close()
    return results


def cmd_fetch(args=None):
    results = asyncio.run(_scrape())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "responses.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ncaptured {len(results)} query responses → {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Show dashboard metadata and embed URL.")
    p_info.set_defaults(func=cmd_info)

    p_fetch = sub.add_parser("fetch", help="Scrape Power BI query responses.")
    p_fetch.set_defaults(func=cmd_fetch)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

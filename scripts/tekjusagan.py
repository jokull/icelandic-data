"""Tekjusagan — income history dashboard (Forsætisráðuneytið).

Token-authenticated Power BI embed wrapped in an Angular SPA. Scraping is done
by driving the SPA with Playwright and intercepting Power BI data responses.

Usage:
    uv run python scripts/tekjusagan.py token      # Fetch embed token (for debugging)
    uv run python scripts/tekjusagan.py fetch      # Drive SPA + capture responses
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPORT_ID = "04ba62a1-8e38-44bd-a6b0-cb63d1fec3d8"
GROUP_ID = "a08a802a-ca7b-4103-9052-18a85d009ec4"
TOKEN_URL = f"https://tekjusagan.is/api/report/{REPORT_ID}"
SPA_URL = "https://tekjusagan.is/"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "tekjusagan"

# Direct SPA routes that render Power BI report pages. Each triggers its own
# set of DAX queries. Hitting these with page.goto() is more reliable than
# clicking menu items.
REPORTS = [
    ("radstofun", "https://tekjusagan.is/skyrslur/radstofun"),
    ("eignirskuldir", "https://tekjusagan.is/skyrslur/eignirskuldir"),
    ("kynmenntun", "https://tekjusagan.is/skyrslur/kynmenntun"),
    ("kynmenntun_details", "https://tekjusagan.is/kynmenntun/details"),
    ("lifshlaupid", "https://tekjusagan.is/lifshlaupid"),
]


def fetch_token() -> dict:
    """Fetch a fresh Power BI embed token from Tekjusagan's backend."""
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = c.get(TOKEN_URL)
        r.raise_for_status()
        return r.json()


def cmd_token(args=None):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tok = fetch_token()
    out = RAW_DIR / "token.json"
    # Preserve for debugging but warn: tokens are short-lived.
    out.write_text(json.dumps(tok, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"token saved to {out}", file=sys.stderr)
    print(f"  id         : {tok.get('id')}")
    print(f"  embedToken : [{len(tok.get('embedToken', ''))} chars]")


async def _scrape() -> list[dict]:
    """Drive the Angular SPA and capture Power BI responses.

    Returns a list of {section, url, body | text} dicts.
    """
    from playwright.async_api import async_playwright

    captured: list[dict] = []
    current_section = {"name": "initial"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def on_response(r):
                u = r.url.lower()
                is_pbi_data = (
                    u.startswith("blob:")
                    or "querydata" in u
                    or "executequeries" in u
                    or "modelsandexploration" in u
                    or "conceptualschema" in u
                )
                if is_pbi_data and r.status == 200:
                    entry = {"section": current_section["name"], "url": r.url}
                    try:
                        entry["body"] = await r.json()
                    except Exception:
                        try:
                            entry["text"] = (await r.text())[:200000]
                        except Exception:
                            return
                    captured.append(entry)

            page.on("response", on_response)

            # Visit each report route directly. The SPA fetches a token and
            # initializes the Power BI embed on each route.
            for slug, url in REPORTS:
                current_section["name"] = slug
                print(f"  section: {slug} → {url}", file=sys.stderr)
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                except Exception as e:
                    print(f"    [warn] goto failed: {e}", file=sys.stderr)
                    continue
                # Power BI does not reliably fire networkidle; wait for the
                # DAX calls to flow. 20s is enough for modelsAndExploration
                # + a couple of executeQueries.
                await asyncio.sleep(20)
        finally:
            await browser.close()
    return captured


def cmd_fetch(args=None):
    results = asyncio.run(_scrape())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "responses.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # Small summary
    by_section: dict[str, int] = {}
    for r in results:
        by_section[r["section"]] = by_section.get(r["section"], 0) + 1
    print(f"\ncaptured {len(results)} responses → {out}", file=sys.stderr)
    for s, n in by_section.items():
        print(f"  {s}: {n}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("token", cmd_token), ("fetch", cmd_fetch)]:
        p = sub.add_parser(name)
        p.set_defaults(func=fn)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

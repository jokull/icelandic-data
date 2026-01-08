#!/usr/bin/env python3
"""
Debug script for skatturinn.is - opens browser with DevTools for inspection.

Usage:
    uv run python scripts/skatturinn_debug.py 5012043070

    # Or with Playwright inspector:
    PWDEBUG=1 uv run python scripts/skatturinn_debug.py 5012043070
"""

import asyncio
import sys

from playwright.async_api import async_playwright


async def debug_company_page(kennitala: str):
    """Open company page in headed browser for inspection."""

    async with async_playwright() as p:
        # Launch in headed mode (visible browser)
        browser = await p.chromium.launch(
            headless=False,
            devtools=True,  # Auto-open DevTools
            slow_mo=500,    # Slow down actions so you can see them
        )

        page = await browser.new_page()

        url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
        print(f"Opening {url}")
        print()
        print("=" * 60)
        print("INSTRUCTIONS:")
        print("=" * 60)
        print()
        print("1. Look for 'Raunverulegir eigendur' (Beneficial owners) section")
        print("2. Right-click on owner name/kennitala -> Inspect")
        print("3. Note the CSS selector path for the table/rows")
        print()
        print("4. Look for 'Gögn úr ársreikningaskrá' section")
        print("5. Find checkboxes next to annual reports")
        print("6. Note selectors for: checkbox, cart button, download button")
        print()
        print("7. Try clicking a checkbox - watch Network tab for XHR requests")
        print()
        print("Press Ctrl+C in terminal when done inspecting...")
        print("=" * 60)

        await page.goto(url, wait_until="networkidle")

        # Pause here - browser stays open for inspection
        # User can interact with DevTools
        await page.pause()

        await browser.close()


async def debug_download_flow(kennitala: str):
    """Step through the download flow with pauses."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            devtools=True,
            slow_mo=1000,
        )

        page = await browser.new_page()

        url = f"https://www.skatturinn.is/fyrirtaekjaskra/leit/kennitala/{kennitala}"
        print(f"Opening {url}")

        await page.goto(url, wait_until="networkidle")

        print()
        print("Page loaded. Now manually:")
        print("1. Scroll to 'Gögn úr ársreikningaskrá'")
        print("2. Click a checkbox to add report to cart")
        print("3. Watch what happens - look for cart icon/count change")
        print("4. Click cart to proceed to download")
        print()
        print("Watch the Network tab for any XHR/fetch requests!")
        print()

        await page.pause()

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/skatturinn_debug.py <kennitala> [--download]")
        print()
        print("Examples:")
        print("  uv run python scripts/skatturinn_debug.py 5012043070")
        print("  uv run python scripts/skatturinn_debug.py 5012043070 --download")
        sys.exit(1)

    kennitala = sys.argv[1]

    if "--download" in sys.argv:
        asyncio.run(debug_download_flow(kennitala))
    else:
        asyncio.run(debug_company_page(kennitala))

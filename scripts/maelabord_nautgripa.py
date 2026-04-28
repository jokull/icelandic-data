"""Scrape per-farm cattle subsidy recipients from Mælaborð landbúnaðarins.

The dashboard's "Eftir búi" page contains a hierarchical matrix visual:
  - Level 0 (DM1): one row per farm, labelled "<búsnúmer> - <heiti>".
  - Level 1 (DM3): per-Samningur breakdown for that farm. G1 indexes into the
    samningur value-dict: 0=Ýmis stuðningur, 1=Nautgriparækt, 2=Sauðfjárrækt,
    3=Garðyrkja, 4=Rammasamningur.
  - DM2 on each farm: that farm's column totals (sauðfé, nautgripir, land, …).

Power BI virtualises matrix rows, so we scroll-paginate. We keep *every* farm
that ever contributed to a Nautgriparækt (G1 == 1) row — those are the recipients
of a Nautgriparæktarsamningur payment.

Output
------
data/raw/hagstofan/nautgripa_recipients_raw.json   — all captured querydata bodies
data/processed/nautgripa_recipients.csv            — flat farm list with
    busnr, landsnr, nafn, nautgripir, nautgripa_upphaed, total_upphaed
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPORT = (
    "https://app.powerbi.com/view?r=eyJrIjoiMjYxZDg3YjQtZDNjMi00M2E0LTg2ZTktYjhk"
    "YWY2MTgzZDQ5IiwidCI6ImYxMDI1YzFjLTMxZWUtNDI0MC1iYzMwLWQzYWRkYmY2ZDkxMiIsImMiOjh9"
)
EFTIR_BUI_PAGE = "ReportSection6ce1bcdf21048698c67b"

OUT_RAW = Path("data/raw/hagstofan/nautgripa_recipients_raw.json")
OUT_CSV = Path("data/processed/nautgripa_recipients.csv")

FARM_LABEL_RE = re.compile(r"^\s*(\d{6,8})\s*-\s*(.+?)\s*$")
NAUTGRIPA_LABEL = "Nautgriparækt"  # resolve per-body via the D0 value-dict
NAUTGRIPA_IDX = 1  # canonical position; runtime uses d0.index(NAUTGRIPA_LABEL) for safety


# ---------------------------------------------------------------------------
# DM parsing
# ---------------------------------------------------------------------------

def _walk_results(body: dict):
    """Yield every (ph_dict, schema_cols) pair anywhere in the body."""
    for res in body.get("results", []):
        yield from _walk_data(res.get("result", {}).get("data", {}).get("dsr", {}))


def _walk_data(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("DM") and isinstance(v, list):
                # This is a list of rows; surface it
                yield k, v
            yield from _walk_data(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_data(it)


def _rows_from_dm(dm: list[dict], fallback_schema: list[str] | None = None) -> list[dict]:
    """Decompress a DM list — handles R (repeat) and Ø (null) bitmasks.

    Power BI only emits the schema ("S") on the first row of each DM block in
    the first body it is sent in; subsequent rows (or subsequent bodies, for
    paginated fetches) rely on the client already knowing it. Callers pass the
    resolved schema via ``fallback_schema``.
    """
    if not dm:
        return []
    schema = [s.get("N") for s in dm[0].get("S", [])] if dm[0].get("S") else fallback_schema
    out = []
    prev = {}
    for row in dm:
        if row.get("S"):
            schema = [s.get("N") for s in row["S"]]
        if not schema:
            continue
        vals = {}
        r_mask = row.get("R", 0)
        null_mask = row.get("Ø", 0)
        c = row.get("C", [])
        named_direct = {k: v for k, v in row.items() if k in schema}
        ci = 0
        for i, name in enumerate(schema):
            bit = 1 << i
            if name in named_direct:
                vals[name] = named_direct[name]
            elif r_mask & bit:
                vals[name] = prev.get(name)
            elif null_mask & bit:
                vals[name] = None
            elif ci < len(c):
                vals[name] = c[ci]
                ci += 1
        prev = vals
        if "M" in row:
            vals["_M"] = row["M"]
        if "X" in row:
            vals["_X"] = row["X"]
        out.append(vals)
    return out


# Hard-coded fallback schemas for the three matrix-body DM blocks. The first
# body sent by Power BI declares them in its descriptor; paginated follow-ups
# omit the "S" field and rely on the client remembering.
DM2_SCHEMA = ["A7", "A8", "A9", "A10", "A11", "A12", "A13"]
DM3_SCHEMA = ["G1", "M0", "M1", "M2", "M3", "M4", "M5", "M6"]


def _find_value_dict(body: dict, key: str = "D0") -> list | None:
    """Return the Power BI ValueDicts entry for *key* in this body.

    Each response carries its own value-dict mapping; the ordering is *per
    query* (it's just the distinct values that happened to appear in that
    batch), so you cannot cache a single mapping across responses.
    """
    def _walk(obj):
        if isinstance(obj, dict):
            vd = obj.get("ValueDicts")
            if isinstance(vd, dict) and key in vd:
                return vd[key]
            for v in obj.values():
                got = _walk(v)
                if got is not None:
                    return got
        elif isinstance(obj, list):
            for it in obj:
                got = _walk(it)
                if got is not None:
                    return got
        return None
    return _walk(body)


def parse_matrix(body: dict):
    """Extract farm-level rows from the Eftir búi matrix query body.

    Yields dicts: {busnr, nafn, total_upphaed, nautgripir, nautgripa_upphaed}
    """
    d0 = _find_value_dict(body, "D0") or []
    try:
        nautgripa_idx = d0.index(NAUTGRIPA_LABEL)
    except ValueError:
        nautgripa_idx = None  # this body's batch has no Nautgriparækt rows
    for name, dm in _walk_results(body):
        if name != "DM1":
            continue
        for frow in dm:
            label = frow.get("G0") or ""
            m = FARM_LABEL_RE.match(label)
            if not m:
                continue
            busnr = m.group(1)
            nafn = m.group(2)
            total_upphaed = None
            nautgripir = None
            nautgripa_upphaed = None
            for sub in frow.get("M", []):
                for subname, subdm in _walk_data(sub):
                    if subname == "DM2":
                        rows = _rows_from_dm(subdm, fallback_schema=DM2_SCHEMA)
                        for r in rows:
                            if r.get("A13") is not None:
                                total_upphaed = r["A13"]
                            if r.get("A10") is not None:
                                nautgripir = r["A10"]
                    elif subname == "DM3" and nautgripa_idx is not None:
                        rows = _rows_from_dm(subdm, fallback_schema=DM3_SCHEMA)
                        for r in rows:
                            if r.get("G1") == nautgripa_idx and r.get("M6") is not None:
                                nautgripa_upphaed = r["M6"]
            yield {
                "busnr": busnr,
                "nafn": nafn,
                "nautgripir": nautgripir,
                "nautgripa_upphaed": nautgripa_upphaed,
                "total_upphaed": total_upphaed,
            }


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

async def _set_year(page, year: str) -> bool:
    """Change the Greiðsluár slicer to the given year via its dropdown.

    Returns True if we clicked something and the dropdown closed. Power BI
    dropdown slicers expose their currently-selected value as a button whose
    accessible text is the year; clicking it opens a list of options, each a
    listitem whose text is the year.
    """
    # The dropdown button shows the currently selected year. We open it by
    # clicking the combobox, then click the target year's listitem.
    opener = None
    for sel in [
        "div[role=combobox][aria-label*='Greiðsluár' i]",
        "div[aria-label*='Greiðsluár' i]",
    ]:
        try:
            opener = await page.query_selector(sel)
            if opener:
                break
        except Exception:
            continue
    if opener is None:
        # Fall back to text search
        try:
            opener = page.get_by_text("Greiðsluár", exact=False).first
            await opener.click(timeout=3000)
        except Exception:
            return False
    else:
        try:
            await opener.click(timeout=3000)
        except Exception:
            return False
    await asyncio.sleep(1)
    # Now find the year listitem and click it
    try:
        item = page.get_by_role("listitem", name=re.compile(rf"^\s*{year}\s*$"))
        if await item.count() == 0:
            item = page.get_by_text(re.compile(rf"^\s*{year}\s*$"))
        await item.first.click(timeout=3000)
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"  [warn] year click failed: {e}", file=sys.stderr)
        return False


async def _scrape(headed: bool, year: str | None) -> list[dict]:
    captured: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        async def on_resp(response):
            if "querydata" in response.url.lower():
                try:
                    if response.status == 200:
                        body = await response.json()
                        captured.append(body)
                except Exception:
                    pass

        page.on("response", on_resp)

        nav = f"{REPORT}&pageName={EFTIR_BUI_PAGE}"
        print(f"Loading {nav}", file=sys.stderr)
        await page.goto(nav, wait_until="load", timeout=90000)
        await asyncio.sleep(12)

        if year:
            print(f"  selecting Greiðsluár = {year}", file=sys.stderr)
            ok = await _set_year(page, year)
            print(f"  year switch ok={ok}", file=sys.stderr)
            # Let the query re-run
            await asyncio.sleep(6)

        # Focus the matrix visual and scroll its body to paginate.
        print("  paging matrix via keyboard…", file=sys.stderr)
        # Power BI renders the matrix inside a visual container with role=group
        # and an inner .bodyCells that actually scrolls.
        target = None
        for sel in [".bodyCells", ".pivotTable .bodyCells", "[class*='pivotTable']"]:
            target = await page.query_selector(sel)
            if target:
                print(f"    using selector: {sel}", file=sys.stderr)
                break

        if target:
            try:
                await target.click()
            except Exception:
                pass

        seen_farms = 0
        stable_rounds = 0
        for round_idx in range(80):
            # PageDown + End both help Power BI ask for more rows
            for _ in range(30):
                await page.keyboard.press("PageDown")
                await asyncio.sleep(0.15)
            await page.keyboard.press("End")
            await asyncio.sleep(2)

            farms = set()
            for body in captured:
                for r in parse_matrix(body):
                    farms.add(r["busnr"])
            print(f"    round {round_idx + 1}: distinct_farms={len(farms)} queries={len(captured)}",
                  file=sys.stderr)
            if len(farms) == seen_farms:
                stable_rounds += 1
                if stable_rounds >= 4:
                    break
            else:
                stable_rounds = 0
            seen_farms = len(farms)

        await browser.close()

    return captured


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def busnr_to_landsnr(busnr: str | int) -> int:
    """Convert búsnúmer (8-digit, leading zero padded) → landsnúmer (integer)."""
    return int(str(busnr)) // 10


def _flatten(captured: list[dict]) -> list[dict]:
    # Merge farm rows across captures, picking the record with the largest
    # total_upphaed (a farm can be partially visible across multiple fetches).
    merged: dict[str, dict] = {}
    for body in captured:
        for row in parse_matrix(body):
            busnr = row["busnr"]
            prev = merged.get(busnr)
            if prev is None or (row.get("total_upphaed") or 0) > (prev.get("total_upphaed") or 0):
                merged[busnr] = row
            else:
                # Fill any missing fields from the new row
                for k, v in row.items():
                    if prev.get(k) is None and v is not None:
                        prev[k] = v
    return list(merged.values())


def cmd_fetch(args: argparse.Namespace) -> None:
    captured = asyncio.run(_scrape(headed=args.headed, year=args.year))
    OUT_RAW.parent.mkdir(parents=True, exist_ok=True)
    OUT_RAW.write_text(json.dumps(captured, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {OUT_RAW} ({OUT_RAW.stat().st_size:,} bytes, {len(captured)} queries)",
          file=sys.stderr)
    cmd_parse(args)


def cmd_parse(args: argparse.Namespace) -> None:
    if not OUT_RAW.exists():
        sys.exit(f"Missing {OUT_RAW}. Run `fetch` first.")
    captured = json.loads(OUT_RAW.read_text(encoding="utf-8"))
    all_farms = _flatten(captured)
    # Strict: only farms that *received* a Nautgriparækt payment this year.
    # (Farms with cattle on record but zero payment are noise for this map.)
    recipients = [f for f in all_farms if (f.get("nautgripa_upphaed") or 0) > 0]
    recipients.sort(key=lambda r: -(r.get("nautgripa_upphaed") or 0))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "busnr", "landsnr", "nafn",
            "nautgripir", "nautgripa_upphaed", "total_upphaed",
        ])
        w.writeheader()
        for r in recipients:
            w.writerow({
                "busnr": r["busnr"],
                "landsnr": busnr_to_landsnr(r["busnr"]),
                "nafn": r["nafn"],
                "nautgripir": r.get("nautgripir") or "",
                "nautgripa_upphaed": r.get("nautgripa_upphaed") or 0,
                "total_upphaed": r.get("total_upphaed") or 0,
            })
    print(f"Wrote {OUT_CSV}: {len(recipients)} cattle recipients, "
          f"{len(all_farms)} farms scraped total.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Scrape Power BI + write raw + CSV")
    f.add_argument("--headed", action="store_true")
    f.add_argument("--year", default=None,
                   help="Greiðsluár to select (e.g. 2025). Default: dashboard default (current year).")
    f.set_defaults(func=cmd_fetch)

    p = sub.add_parser("parse", help="Re-parse existing raw JSON into CSV")
    p.set_defaults(func=cmd_parse)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

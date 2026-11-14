"""HMS mánaðarskýrsla — monthly housing-market report: narrative + "Myndir" workbook.

Source: https://hms.is/skyrslur (report pages `manadarskyrsla-{month}-{year}`)

Each report is a web page (no PDF) with one Excel workbook, "Myndir að baki
mánaðarskýrslu", holding the data behind every chart: sheets FM.* (fasteigna-
markaður), LEIGA.* (leigumarkaður), LM.* (lánamarkaður), BM.* (byggingar-
markaður), plus one manifest sheet per section listing figure id → title.

hms.is is behind a Vercel checkpoint, so discovery runs headless Chromium. The
workbook lives on Prismic's CDN under a random hash prefix, so its URL cannot
be constructed — it has to be read off the report page. The download itself is
plain httpx.

Every month is archived even though each workbook carries full history: HMS
revises back-series and changes which charts it publishes, and both are signal.

Raw:
    data/raw/hms/manadarskyrsla/{YYYY-MM}/{original}.xlsx
    data/raw/hms/manadarskyrsla/{YYYY-MM}/page.txt     (report narrative, as rendered)
    data/raw/hms/manadarskyrsla/{YYYY-MM}/meta.json    (urls, sha256, fetched_at)
Processed:
    data/processed/hms_manadarskyrsla/{YYYY-MM}/figures.csv   (sheet, section, title)
    data/processed/hms_manadarskyrsla/{YYYY-MM}/{sheet}.csv   (one table per figure)

The per-figure tables keep HMS's own column headers: the sheets are too
heterogeneous (monthly, quarterly, survey-year, size bins) for one long format
to be honest.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "hms" / "manadarskyrsla"
PROCESSED_DIR = ROOT / "data" / "processed" / "hms_manadarskyrsla"

LISTING_URL = "https://hms.is/skyrslur"
REPORT_URL = "https://hms.is/skyrslur/{slug}"
HEADERS = {"User-Agent": "icelandic-data/1.0 (data toolkit fetcher)"}

MONTHS = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "agust": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}
SLUG_RE = re.compile(r"manadarskyrsla-([a-z]+)-(\d{2}|\d{4})$")


def slug_month(slug: str) -> str:
    """`manadarskyrsla-oktober-2026` / `manadarskyrsla-agust-25` → `2026-10` / `2025-08`."""
    m = SLUG_RE.search(slug)
    if not m or m.group(1) not in MONTHS:
        raise ValueError(f"Not a mánaðarskýrsla slug: {slug!r}")
    year = int(m.group(2))
    if year < 100:
        year += 2000
    return f"{year}-{MONTHS[m.group(1)]:02d}"


async def _page_links(url: str) -> tuple[list[tuple[str, str]], str]:
    """Render `url` in headless Chromium; return (text, href) for every link and the main text."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        await page.goto(url, wait_until="networkidle", timeout=120000)
        links = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a')).map(a => [a.innerText.trim(), a.href])"
        )
        text = await page.evaluate("() => (document.querySelector('main') || document.body).innerText")
        await browser.close()
    if "Vercel Security Checkpoint" in text:
        raise RuntimeError(f"{url} -> stuck at Vercel checkpoint")
    return [tuple(link) for link in links], text


def list_reports() -> list[tuple[str, str]]:
    """(slug, title) for mánaðarskýrslur on the listing page, newest first (page order)."""
    links, _ = asyncio.run(_page_links(LISTING_URL))
    seen: dict[str, str] = {}
    for text, href in links:
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if "/skyrslur/" in href and SLUG_RE.search(slug) and slug not in seen:
            seen[slug] = text.splitlines()[-1] if text else slug
    return list(seen.items())


def cmd_list(args: argparse.Namespace) -> None:
    for slug, title in list_reports():
        print(f"{slug_month(slug)}  {slug:40s}  {title}")


def cmd_fetch(args: argparse.Namespace) -> None:
    import httpx

    slug = args.slug or list_reports()[0][0]
    month = slug_month(slug)
    out = RAW_DIR / month
    if (out / "meta.json").exists() and not args.force:
        print(f"Already fetched {month}: {out} (use --force to refresh)")
        return
    url = REPORT_URL.format(slug=slug)
    print(f"Rendering {url}…")
    links, text = asyncio.run(_page_links(url))
    xlsx = [href for _, href in links if href.lower().split("?")[0].endswith(".xlsx")]
    if not xlsx:
        raise RuntimeError(f"{url} -> no .xlsx link; links={links}")
    xlsx_url = xlsx[0]

    r = httpx.get(xlsx_url, timeout=60, follow_redirects=True, headers=HEADERS)
    r.raise_for_status()
    if r.content[:2] != b"PK":
        raise ValueError(f"{xlsx_url} -> not an xlsx (starts {r.content[:16]!r})")

    out.mkdir(parents=True, exist_ok=True)
    # Prismic prefixes the original filename with a 16-char asset id + "_"; the
    # id itself may contain "_" (e.g. "-wFV6eaX_H1cA_Rr_Gogn_…"), so cut by length.
    base = xlsx_url.split("?")[0].rsplit("/", 1)[-1]
    name = base[17:] if len(base) > 17 and base[16] == "_" else base
    (out / name).write_bytes(r.content)
    (out / "page.txt").write_text(text, encoding="utf-8")
    meta = {
        "slug": slug,
        "month": month,
        "report_url": url,
        "xlsx_url": xlsx_url,
        "xlsx_file": name,
        "xlsx_sha256": hashlib.sha256(r.content).hexdigest(),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {name} ({len(r.content):,} bytes), page.txt ({len(text):,} chars) -> {out}")
    process(month)


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v).replace("\n", " ").strip() if isinstance(v, str) else repr(v) if isinstance(v, float) else str(v)


def sheet_table(rows: list[tuple]) -> tuple[str, list[str], list[list[str]]]:
    """Figure sheet → (title, header, body). Row 1 is the title, row 2 usually the header.

    Columns with a blank header and no values are dropped (HMS pads sheets);
    fully blank rows are dropped (FM.7 carries ~29k empty rows).
    """
    title = _cell(rows[0][0]) if rows else ""
    rest = list(rows[1:])
    # A lone cell under the title is a subtitle (BM.3 "Magnbreytingar frá fyrra ári, %").
    while rest and sum(v is not None for v in rest[0]) == 1 and isinstance(rest[0][0], str):
        rest.pop(0)
    # A fractional value means the sheet has no header row at all (BM.6);
    # integers are allowed, since year columns ("2026", "2025") are headers.
    if rest and any(isinstance(v, float) and not v.is_integer() for v in rest[0]):
        header, body_rows = [], rest
    else:
        header, body_rows = ([_cell(v) for v in rest[0]], rest[1:]) if rest else ([], [])
    body = [[_cell(v) for v in r] for r in body_rows]
    body = [r for r in body if any(r)]
    width = max([len(header), *map(len, body)], default=0)
    header += [""] * (width - len(header))
    body = [r + [""] * (width - len(r)) for r in body]
    keep = [i for i in range(width) if header[i] or any(r[i] for r in body)]
    header = [header[i] or f"col{i + 1}" for i in keep]
    body = [[r[i] for i in keep] for r in body]
    return title, header, body


def process(month: str) -> None:
    import openpyxl

    src = RAW_DIR / month
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    wb = openpyxl.load_workbook(src / meta["xlsx_file"], read_only=True, data_only=True)
    out = PROCESSED_DIR / month
    out.mkdir(parents=True, exist_ok=True)

    manifest: list[tuple[str, str, str]] = []
    section = ""
    titles: dict[str, str] = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if "." not in ws.title:  # section manifest sheet: "Myndir | Titill"
            section = ws.title
            titles = {_cell(r[0]): _cell(r[1]) for r in rows if r and len(r) > 1 and r[0] and r[1]}
            continue
        title, header, body = sheet_table(rows)
        # The manifest title is the published one; the sheet's own title row
        # sometimes differs by a typo ("fasteignlána" in LM.3, October 2026).
        manifest.append((ws.title, section, titles.get(ws.title, title)))
        with (out / f"{ws.title}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(body)
    with (out / "figures.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sheet", "section", "title"])
        w.writerows(manifest)
    print(f"  {len(manifest)} figures -> {out}")


def cmd_process(args: argparse.Namespace) -> None:
    months = [args.month] if args.month else sorted(p.name for p in RAW_DIR.iterdir() if (p / "meta.json").exists())
    if not months:
        sys.exit(f"Nothing fetched in {RAW_DIR}. Run `fetch` first.")
    for month in months:
        process(month)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers()
    sp = sub.add_parser("list", help="list mánaðarskýrslur on hms.is/skyrslur")
    sp.set_defaults(func=cmd_list)
    sp = sub.add_parser("fetch", help="fetch a report (default: newest) and process it")
    sp.add_argument("slug", nargs="?", help="e.g. manadarskyrsla-oktober-2026")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_fetch)
    sp = sub.add_parser("process", help="re-process fetched workbooks into per-figure CSVs")
    sp.add_argument("--month", help="YYYY-MM (default: every fetched month)")
    sp.set_defaults(func=cmd_process)
    args = p.parse_args()
    if not hasattr(args, "func"):
        args = p.parse_args(["fetch"])
    args.func(args)


if __name__ == "__main__":
    main()

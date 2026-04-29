"""Byggdastofnun — Icelandic Regional Development Institute (mælaborð catalog).

byggdastofnun.is publishes 11 regional-development dashboards as **Tableau
Public** embeds. Scope: population, income, property taxes, energy costs,
state employment, grants, municipality history.

This skill is currently a catalog only: it enumerates each dashboard with its
Tableau workbook/view coordinates, so downstream callers can either:

1. Point a browser at the `embed_url` for interactive exploration.
2. Drive the VizQL extraction flow (the maskina skill documents the pattern
   if structured data is needed).

Usage:
    uv run python scripts/byggdastofnun.py list
    uv run python scripts/byggdastofnun.py fetch           # Re-scrape catalog
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "byggdastofnun"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

BASE = "https://www.byggdastofnun.is"
INDEX = f"{BASE}/is/utgefid-efni/maelabord"

TABLEAU_BASE = "https://public.tableau.com"
_TABLEAU_VIEW_RE = re.compile(
    r'<iframe[^>]+src="(https://public\.tableau\.com/views/[^"]+)"',
    re.IGNORECASE,
)
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.IGNORECASE)
_SUBPAGE_RE = re.compile(
    r'href="(/is/utgefid-efni/maelabord/[a-z0-9-]+)"', re.IGNORECASE
)

# Pre-verified catalog (2026-04). Replaced by `fetch` if the live site shifts.
SEED_CATALOG: list[dict] = [
    {"slug": "breytingar-a-ibuafjolda-sundurlidun",
     "title": "Breytingar á íbúafjölda — sundurliðun",
     "workbook": "ibuafj-breyting", "view": "sveitarfelog"},
    {"slug": "fasteignagjold",
     "title": "Fasteignagjöld viðmiðunareignar",
     "workbook": "fasteignagjold", "view": "fasteignagjold"},
    {"slug": "ibuafjoldi-1-januar",
     "title": "Íbúafjöldi sveitarfélaga og byggðakjarna",
     "workbook": "ibuafj_sveitarf-byggdakj", "view": "ibuafjoldi"},
    {"slug": "ibuakonnun",
     "title": "Íbúakönnun landshlutanna",
     "workbook": "ibuakonnun", "view": "spurningar"},
    {"slug": "mannfjoldaspa",
     "title": "Mannfjöldaspá 2023–2074",
     "workbook": "mannfjoldaspa", "view": "mannspa"},
    {"slug": "orkukostnadur",
     "title": "Orkukostnaður heimila",
     "workbook": "Orkukostnaurheimila", "view": "orkukostnadur"},
    {"slug": "rikisfang",
     "title": "Ríkisfang íbúa",
     "workbook": "rikisfang", "view": "rikisfang"},
    {"slug": "rikisstorf",
     "title": "Stöðugildi á vegum ríkisins",
     "workbook": "rikisstorf", "view": "stodugildi"},
    {"slug": "styrkir",
     "title": "Styrkir og framlög",
     "workbook": "styrkir", "view": "styrkir"},
    {"slug": "sveitarfelagaskipan",
     "title": "Sveitarfélagaskipan frá 1875",
     "workbook": "sveitarfelagamork", "view": "Tmabil"},
    {"slug": "tekjur",
     "title": "Tekjur einstaklinga eftir svæðum",
     "workbook": "tekjur", "view": "tekjur"},
]


def embed_url(workbook: str, view: str) -> str:
    """Reconstruct the Tableau Public embed URL for a (workbook, view)."""
    return (
        f"{TABLEAU_BASE}/views/{workbook}/{view}"
        "?:language=en-GB&:display_count=y&:origin=viz_share_link"
        "&:showVizHome=no&:embed=true"
    )


def page_url(slug: str) -> str:
    return f"{BASE}/is/utgefid-efni/maelabord/{slug}"


def discover(client: httpx.Client) -> list[str]:
    """Return slug list from the mælaborð index page."""
    r = client.get(INDEX)
    r.raise_for_status()
    slugs = sorted({
        m.group(1).rsplit("/", 1)[-1]
        for m in _SUBPAGE_RE.finditer(r.text)
        if not m.group(1).endswith("/maelabord")
    })
    return slugs


def scrape_one(client: httpx.Client, slug: str) -> dict:
    url = page_url(slug)
    r = client.get(url)
    r.raise_for_status()
    title_m = _H1_RE.search(r.text)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    iframe_m = _TABLEAU_VIEW_RE.search(r.text)
    if not iframe_m:
        return {"slug": slug, "title": title, "workbook": "", "view": "",
                "embed_url": "", "page_url": url}
    iframe_url = iframe_m.group(1)
    iframe_url = iframe_url.replace("&amp;", "&")
    # Extract workbook + view from /views/<wb>/<view>
    parts = re.search(r"/views/([^/]+)/([^?]+)", iframe_url)
    workbook, view = (parts.group(1), parts.group(2)) if parts else ("", "")
    return {
        "slug": slug, "title": title,
        "workbook": workbook, "view": view,
        "embed_url": iframe_url,
        "page_url": url,
    }


def cmd_fetch(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers={"User-Agent": "icelandic-data-toolkit/0.1"},
        follow_redirects=True, timeout=30,
    ) as client:
        slugs = discover(client)
        print(f"discovered {len(slugs)} dashboards", file=sys.stderr)
        rows = []
        for i, slug in enumerate(slugs, 1):
            print(f"[{i}/{len(slugs)}] {slug}", file=sys.stderr)
            try:
                rows.append(scrape_one(client, slug))
            except Exception as e:
                print(f"    [error] {e}", file=sys.stderr)
            time.sleep(0.4)

    out = PROCESSED_DIR / "byggdastofnun_catalog.csv"
    fields = ["slug", "title", "workbook", "view", "embed_url", "page_url"]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} rows → {out}", file=sys.stderr)


def _load_catalog() -> list[dict]:
    path = PROCESSED_DIR / "byggdastofnun_catalog.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    # Fallback: use seed catalog, reconstructing embed_url
    return [
        {**row,
         "embed_url": embed_url(row["workbook"], row["view"]),
         "page_url": page_url(row["slug"])}
        for row in SEED_CATALOG
    ]


def cmd_list(args):
    rows = _load_catalog()
    for r in rows:
        print(f"  {r['slug']:40} · {r['title']}")
        print(f"      workbook={r['workbook']}  view={r['view']}")
        print(f"      {r['embed_url']}")
    print(f"\n{len(rows)} dashboards", file=sys.stderr)


def cmd_url(args):
    """Print just the embed URL for a given slug — handy for shell pipelines."""
    rows = _load_catalog()
    match = next((r for r in rows if r["slug"] == args.slug), None)
    if not match:
        slugs = ", ".join(r["slug"] for r in rows)
        raise SystemExit(f"slug not found: {args.slug!r}. Known slugs: {slugs}")
    print(match["embed_url"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Re-scrape catalog from byggdastofnun.is").set_defaults(func=cmd_fetch)
    sub.add_parser("list", help="Print the cached catalog").set_defaults(func=cmd_list)

    p_url = sub.add_parser("url", help="Print the Tableau embed URL for a slug.")
    p_url.add_argument("slug")
    p_url.set_defaults(func=cmd_url)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

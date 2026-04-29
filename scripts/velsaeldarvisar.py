"""Velsældarvísar + Félagsvísar + Menningarvísar — Hagstofa indicator catalogs.

All three are Webflow sites at `visar.hagstofa.is` that wrap curated subsets of
Hagstofa's PX-Web tables. Each "indicator" tab links to one or more PX-Web
tables + a metadata PDF. This script crawls the HTML and builds a tidy catalog
(indicator → PX-Web tables) so consumers can pull the underlying data via the
existing `hagstofan` skill.

Usage:
    uv run python scripts/velsaeldarvisar.py list                 # Print catalog
    uv run python scripts/velsaeldarvisar.py fetch                # Crawl + write CSV
    uv run python scripts/velsaeldarvisar.py pxtables             # Just PX table codes
"""
import argparse
import csv
import re
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "velsaeldarvisar"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

BASE = "https://visar.hagstofa.is"

# (section, slug, url) — each URL is a Webflow page with tab-pane indicators.
# velsaeldarvisar has 3 sub-pages (one per "dimension"); felagsvisar and
# menningarvisar are single pages.
PAGES: list[tuple[str, str, str]] = [
    ("velsaeldarvisar", "felagslegir", f"{BASE}/velsaeldarvisar/felagslegir-maelikvardar"),
    ("velsaeldarvisar", "efnahagslegir", f"{BASE}/velsaeldarvisar/efnahagslegir-maelikvardar"),
    ("velsaeldarvisar", "umhverfislegir", f"{BASE}/velsaeldarvisar/umhverfislegir-maelikvardar"),
    ("felagsvisar", "felagsvisar", f"{BASE}/felagsvisar"),
    ("menningarvisar", "menningarvisar", f"{BASE}/menningarvisar"),
]

# Indicator panes carry a `tab-pane-...` prefix in their class.
# Parent category panes carry only `w-tab-pane`. Attribute order is
# `data-w-tab` before `class` in the live Webflow output.
_TAB_PANE_RE = re.compile(
    r'<div[^>]*data-w-tab="([^"]+)"[^>]*class="([^"]*w-tab-pane[^"]*)"[^>]*>',
    re.IGNORECASE,
)
_PX_URL_RE = re.compile(
    r'href="(https://px\.hagstofa\.is/pxis/pxweb/[^"]+?\.px)"',
    re.IGNORECASE,
)
_PDF_URL_RE = re.compile(
    r'href="(https://hagstofas3bucket\.hagstofa\.is/[^"]+?\.pdf)"',
    re.IGNORECASE,
)
# Fallback: any hagstofas3bucket URL (some use http:// without s)
_PDF_URL_ALT_RE = re.compile(
    r'href="(https?://hagstofas3bucket\.hagstofa\.is/[^"]+?\.pdf)"',
    re.IGNORECASE,
)
# "Stutt lýsing" short description block
_SHORT_DESC_RE = re.compile(
    r'Stutt lýsing</span>\s*<br\s*/?>\s*([^<]+)', re.IGNORECASE
)
_UNIT_RE = re.compile(r'Eining</span>\s*<br\s*/?>\s*([^<]+)', re.IGNORECASE)


def _px_code(url: str) -> str:
    """Extract the PX table code (e.g. 'THJ09000') from a full URL."""
    m = re.search(r"/([A-Z]{3}\d{5})\.px", url, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def parse_page(html: str) -> list[dict]:
    """Parse a Webflow indicator page into a list of indicator dicts.

    Returns one dict per indicator pane. Parent category panes are used only
    to attach a `category` field; they do not become their own rows.
    """
    matches = list(_TAB_PANE_RE.finditer(html))
    out: list[dict] = []
    current_category = ""
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        cls = m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        slice_ = html[start:end]

        if "tab-pane-" not in cls:
            # Parent category pane — just update the running category.
            current_category = name
            continue

        px_urls = list(dict.fromkeys(_PX_URL_RE.findall(slice_)))
        pdf_urls = list(
            dict.fromkeys(_PDF_URL_RE.findall(slice_) + _PDF_URL_ALT_RE.findall(slice_))
        )
        desc = _SHORT_DESC_RE.search(slice_)
        unit = _UNIT_RE.search(slice_)

        out.append(
            {
                "category": current_category,
                "indicator": name,
                "short_description": desc.group(1).strip() if desc else "",
                "unit": unit.group(1).strip() if unit else "",
                "px_tables": "|".join(_px_code(u) for u in px_urls if _px_code(u)),
                "px_urls": "|".join(px_urls),
                "metadata_pdf": pdf_urls[0] if pdf_urls else "",
            }
        )
    return out


def fetch_page(url: str) -> str:
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def build_catalog() -> list[dict]:
    """Crawl all configured pages and return a flat list of indicator rows."""
    catalog: list[dict] = []
    for section, slug, url in PAGES:
        print(f"fetching: {section}/{slug}  ({url})", file=sys.stderr)
        html = fetch_page(url)
        # Save raw HTML for debugging / replay.
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / f"{section}_{slug}.html").write_text(html, encoding="utf-8")
        rows = parse_page(html)
        for r in rows:
            r["section"] = section
            r["page"] = slug
        catalog.extend(rows)
        print(f"  → {len(rows)} indicators", file=sys.stderr)
    return catalog


def cmd_fetch(args=None):
    catalog = build_catalog()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "velsaeldarvisar_catalog.csv"
    cols = [
        "section",
        "page",
        "category",
        "indicator",
        "unit",
        "short_description",
        "px_tables",
        "px_urls",
        "metadata_pdf",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in catalog:
            w.writerow({k: row.get(k, "") for k in cols})
    print(f"wrote {len(catalog)} rows → {out}", file=sys.stderr)


def _load_catalog() -> list[dict]:
    path = PROCESSED_DIR / "velsaeldarvisar_catalog.csv"
    if not path.exists():
        raise SystemExit(f"catalog missing: {path}. Run `fetch` first.")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_list(args):
    rows = _load_catalog()
    if args.section:
        rows = [r for r in rows if r["section"] == args.section]
    for r in rows:
        tables = r["px_tables"] or "-"
        print(f"[{r['section']:15}] {r['category']:25} · {r['indicator']:45} · {tables}")
    print(f"\n{len(rows)} indicators", file=sys.stderr)


def cmd_pxtables(args):
    """Print distinct PX table codes (one per line, sorted)."""
    rows = _load_catalog()
    tables: set[str] = set()
    for r in rows:
        for t in (r["px_tables"] or "").split("|"):
            t = t.strip()
            if t:
                tables.add(t)
    for t in sorted(tables):
        print(t)
    print(f"\n{len(tables)} unique tables", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Crawl all pages, write catalog CSV.")
    p_fetch.set_defaults(func=cmd_fetch)

    p_list = sub.add_parser("list", help="Print the cached catalog.")
    p_list.add_argument("--section", help="Filter to one section")
    p_list.set_defaults(func=cmd_list)

    p_px = sub.add_parser("pxtables", help="Print unique PX table codes.")
    p_px.set_defaults(func=cmd_pxtables)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

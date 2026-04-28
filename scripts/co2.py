"""CO2.is — Aðgerðaáætlun í loftslagsmálum (Iceland's climate action plan).

co2.is is a Webflow site owned by Umhverfis-, orku- og loftslagsráðuneytið
that catalogues every action in Iceland's climate action plan through 2035.
Each action is a numbered measure (e.g. S.5.C.1) with a title, goal, status,
ministry, and start/end years.

Actions are organised in a three-level taxonomy:
    Kerfi (system)        → L / S / T / V
    Málaflokkur           → L.1, S.5, T.2, V.3, ...
    Viðfangsefni          → L.1.A, S.5.C, T.2.B, V.3.A, ...
    Aðgerð (action)       → L.1.A.1, S.5.C.3, ... (one per row in the output)

The scraper crawls each viðfangsefni page listed on /allar-adgerdir and
extracts the individual accordion entries (32 pages, ~110 actions).

Usage:
    uv run python scripts/co2.py fetch          # crawl, write CSV
    uv run python scripts/co2.py list
    uv run python scripts/co2.py list --kerfi S
    uv run python scripts/co2.py list --status "Í framkvæmd"
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE = "https://www.co2.is"
INDEX = f"{BASE}/allar-adgerdir"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "co2"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

# Viðfangsefni slugs on /allar-adgerdir
_VIDFANGSEFNI_RE = re.compile(r'href="(/adgerdir/[a-z0-9-]+)"')

# Action accordion blocks on each viðfangsefni page.
# Each action has id="sXYN" where X=digit, Y=letter, N=digit. The prefix can be
# s/v/l/th (for Samfélagslosun/Viðskiptakerfi/Landnotkun/Þverlægar).
_ACCORDION_SPLIT_RE = re.compile(
    r'<div id="((?:s|v|l|th)\d+[a-z]\d+)" class="adgerd-accordion">',
    re.IGNORECASE,
)

# Within each action block:
_TITLE_RE = re.compile(
    r'<h3 class="title-6">([^<]+)</h3>', re.IGNORECASE
)
_DESCRIPTION_RE = re.compile(
    r'<div class="adgerd-body"><p class="text-small">([^<]+)</p></div>',
    re.IGNORECASE,
)
_META_ITEM_RE = re.compile(
    r'<div class="label-big strong">([^<]+)</div>\s*'
    r'(.*?)(?=<div class="label-big strong">|</div>\s*</div>\s*</div>)',
    re.DOTALL | re.IGNORECASE,
)
_STATUS_RE = re.compile(r'status-color="([^"]+)"', re.IGNORECASE)
_YEAR_RE = re.compile(r'<div class="text-small">\s*(\d{4})\b')
# Captures the inner text of a `<div class="text-small">` block. We don't
# require the closing `</div>`, because the enclosing meta-item body is
# truncated at the next label's start — which can fall *before* the value's
# own closing tag for the final meta-item of the accordion.
_TEXT_SMALL_RE = re.compile(
    r'<div class="text-small">\s*([^<]+?)\s*(?:</div>|\Z|<)', re.IGNORECASE
)


def _strip(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def discover_vidfangsefni(client: httpx.Client) -> list[str]:
    r = client.get(INDEX)
    r.raise_for_status()
    slugs = sorted(set(_VIDFANGSEFNI_RE.findall(r.text)))
    return slugs


def _parse_code(action_id: str) -> tuple[str, str, str, str]:
    """
    's5c1' → ('S', '5', 'C', '1')
    'th2a3' → ('Þ', '2', 'A', '3')  (th → Þ)
    """
    m = re.match(r"^(th|[svl])(\d+)([a-z])(\d+)$", action_id, re.IGNORECASE)
    if not m:
        return ("", "", "", "")
    prefix, num, letter, idx = m.groups()
    system = {"s": "S", "v": "V", "l": "L", "th": "Þ"}.get(prefix.lower(), prefix.upper())
    return system, num, letter.upper(), idx


def _extract_action(block_id: str, block_html: str) -> dict:
    """Parse one accordion block. Called with the HTML starting at the action
    and ending at the next action (or page end)."""
    system, num, letter, idx = _parse_code(block_id)
    code = f"{system}.{num}.{letter}.{idx}" if system else block_id

    # Title from the expanded section
    title_m = _TITLE_RE.search(block_html)
    title = _strip(title_m.group(1)) if title_m else ""

    # Description
    desc_m = _DESCRIPTION_RE.search(block_html)
    description = _strip(desc_m.group(1)) if desc_m else ""

    # Iterate meta items: label → value pairs
    fields = {"markmid": "", "upphaf": "", "endir": "", "stada": "", "abyrgd": ""}

    for m in _META_ITEM_RE.finditer(block_html):
        label = _strip(m.group(1)).lower()
        body = m.group(2)
        if "markmið" in label:
            # Body has one or more <div class="text-small">
            parts = [_strip(x) for x in _TEXT_SMALL_RE.findall(body) if _strip(x)]
            fields["markmid"] = " | ".join(parts)
        elif "upphaf" in label:
            years = _YEAR_RE.findall(body)
            if len(years) >= 2:
                fields["upphaf"], fields["endir"] = years[0], years[1]
            elif len(years) == 1:
                fields["upphaf"] = years[0]
        elif "staða" in label:
            status_m = _STATUS_RE.search(body)
            if status_m:
                fields["stada"] = _strip(status_m.group(1))
            else:
                # Fall back to text content
                parts = [_strip(x) for x in _TEXT_SMALL_RE.findall(body) if _strip(x)]
                fields["stada"] = parts[0] if parts else ""
        elif "ábyrgð" in label or "abyrgd" in label:
            parts = [_strip(x) for x in _TEXT_SMALL_RE.findall(body) if _strip(x)]
            fields["abyrgd"] = " | ".join(parts)

    return {
        "code": code,
        "id": block_id,
        "kerfi": system,
        "malaflokkur_nr": num,
        "vidfangsefni_letter": letter,
        "action_idx": idx,
        "title": title,
        "description": description,
        "markmid": fields["markmid"],
        "upphaf": fields["upphaf"],
        "endir": fields["endir"],
        "stada": fields["stada"],
        "abyrgdaradili": fields["abyrgd"],
    }


def fetch_vidfangsefni(client: httpx.Client, slug: str) -> list[dict]:
    """Fetch one /adgerdir/<slug> page and return a list of action dicts."""
    url = f"{BASE}{slug}"
    r = client.get(url)
    r.raise_for_status()

    # Save raw HTML for debugging / replay.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    key = slug.strip("/").split("/")[-1]
    (RAW_DIR / f"{key}.html").write_text(r.text, encoding="utf-8")

    # Split the page at each accordion start; each slice is one action block.
    matches = list(_ACCORDION_SPLIT_RE.finditer(r.text))
    results = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(r.text)
        block_id = m.group(1).lower()
        block_html = r.text[start:end]
        action = _extract_action(block_id, block_html)
        action["vidfangsefni_slug"] = key
        action["vidfangsefni_url"] = url
        results.append(action)
    return results


def fetch_all() -> list[dict]:
    all_actions: list[dict] = []
    with httpx.Client(
        headers={"User-Agent": "icelandic-data-toolkit/0.1"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        slugs = discover_vidfangsefni(client)
        print(f"discovered {len(slugs)} viðfangsefni", file=sys.stderr)
        for i, slug in enumerate(slugs, 1):
            print(f"[{i}/{len(slugs)}] {slug}", file=sys.stderr)
            try:
                actions = fetch_vidfangsefni(client, slug)
            except Exception as e:
                print(f"    [error] {e}", file=sys.stderr)
                continue
            print(f"    {len(actions)} actions", file=sys.stderr)
            all_actions.extend(actions)
            time.sleep(0.3)  # be polite to Webflow CDN
    return all_actions


def cmd_fetch(args):
    actions = fetch_all()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "co2_actions.csv"
    fields = [
        "code", "id", "kerfi", "malaflokkur_nr", "vidfangsefni_letter", "action_idx",
        "vidfangsefni_slug", "title", "description",
        "markmid", "upphaf", "endir", "stada", "abyrgdaradili", "vidfangsefni_url",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(actions)
    print(f"\nwrote {len(actions)} actions → {out}", file=sys.stderr)
    # Summary by kerfi + status
    from collections import Counter
    kerfi = Counter(a["kerfi"] for a in actions)
    stada = Counter(a["stada"] for a in actions)
    print(f"\nBy kerfi:  {dict(kerfi)}", file=sys.stderr)
    print(f"By staða:  {dict(stada)}", file=sys.stderr)


def _load() -> list[dict]:
    path = PROCESSED_DIR / "co2_actions.csv"
    if not path.exists():
        raise SystemExit(f"{path} missing — run `fetch` first")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_list(args):
    rows = _load()
    if args.kerfi:
        rows = [r for r in rows if r["kerfi"] == args.kerfi]
    if args.status:
        rows = [r for r in rows if args.status.lower() in r["stada"].lower()]
    if args.ministry:
        rows = [r for r in rows if args.ministry.lower() in r["abyrgdaradili"].lower()]
    for r in rows:
        print(f"  {r['code']:10} · {r['stada']:15} · {r['upphaf']}-{r['endir']:4} · {r['title'][:80]}")
    print(f"\n{len(rows)} actions", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Crawl co2.is and build the catalog CSV.").set_defaults(func=cmd_fetch)

    p_l = sub.add_parser("list", help="Print the cached catalog.")
    p_l.add_argument("--kerfi", help="Filter by kerfi (S, V, L, Þ)")
    p_l.add_argument("--status", help="Filter by status (substring)")
    p_l.add_argument("--ministry", help="Filter by responsible ministry (substring)")
    p_l.set_defaults(func=cmd_list)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

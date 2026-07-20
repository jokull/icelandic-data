"""RÚV skoðanakannanir (opinion polls) — tag-page aggregator across pollsters.

Two-stage pipeline:
  1. `list`  — plain httpx GET of the tag page, parsed from the embedded
     __NEXT_DATA__ JSON blob (no browser needed; server-rendered).
  2. `fetch` — one article at a time via Playwright. Article bodies are
     client-side rendered (curl/httpx sees an empty shell), and the party
     support numbers live in a Highcharts bar chart whose bars carry a
     real `aria-label="<Party>, <pct>%."` attribute on each SVG <path> —
     that's the extraction target, not OCR or color-matching.

Usage:
    uv run python scripts/skodanakannanir.py list
    uv run python scripts/skodanakannanir.py list --scope reykjavik
    uv run python scripts/skodanakannanir.py fetch 479261
    uv run python scripts/skodanakannanir.py fetch --all --limit 20
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TAG_URL = "https://www.ruv.is/frettir/tag/skodanakonnun"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "skodanakannanir"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

REYKJAVIK_KEYWORDS = re.compile(r"reykjav[ií]k|borgarst[jó]órn|í borginni", re.IGNORECASE)

# Case-sensitive and stem-based on purpose: "Prósent" is both a pollster's
# proper name and the ordinary Icelandic word for "percent" ("prósent"),
# which appears in nearly every poll subtitle lowercase mid-sentence
# ("...prósentustigi á eftir"). Matching case-sensitively on the
# capitalized stem is what actually distinguishes the two.
_POLLSTER_RE = re.compile(r"\b(Maskín\w*|Prósent\w*|Gallup\w*|Félagsvísindastofnun\w*)\b")
_POLLSTER_CANONICAL = {
    "maskín": "Maskína",
    "prósent": "Prósent",
    "gallup": "Gallup",
    "félagsvísindastofnun": "Félagsvísindastofnun",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

# --- Prose fallback -----------------------------------------------------
# Not every poll article embeds a Highcharts chart (verified: articles
# 451831 and 428434, both Reykjavík polls, have zero chart <path> elements
# despite being full ~5,900-char articles). When there's no chart, the
# numbers only exist in prose, in sentences like:
#   "Sjálfstæðisflokkurinn fengi 29 prósent atkvæða..."          <- poll figure
#   "...og fékk þá 19 prósent atkvæða."                          <- 2022 election result, NOT a poll figure
# The distinguishing signal is verb mood, not proximity: "fengi"/"mælist"/
# "mælast"/"stæði" (conditional/present, hypothetical-if-election-were-now)
# mark a current poll number; "fékk"/"fengu" (simple past) mark a historical
# election result mentioned for comparison. This is a real, reliable
# Icelandic grammar distinction, not a heuristic guess.
_POLL_CUE_RE = re.compile(r"\b(mælist|mælast|fengi|fengju|stæði|stæðu|stendur)\b")
_HISTORICAL_CUE_RE = re.compile(r"\b(fékk|fengu)\b")

_PARTY_STEMS = [
    ("Sjálfstæðisflokkur", r"Sjálfstæðisflokk\w*"),
    ("Samfylking", r"Samfylking\w*"),
    ("Framsóknarflokkur", r"Framsókn(?:arflokk\w*)?"),
    ("Viðreisn", r"Viðreisn\w*"),
    ("Vinstri græn", r"Vinstri\s*g?ræn\w*|\bVG\b"),
    ("Píratar", r"Píra\w*"),
    ("Miðflokkur", r"Miðflokk\w*"),
    ("Flokkur fólksins", r"Flokk\w*\s+fólksins"),
    ("Sósíalistaflokkur", r"Sósíalist\w*"),
]
_PARTY_RE = re.compile("|".join(f"(?P<p{i}>{pat})" for i, (_, pat) in enumerate(_PARTY_STEMS)))
_PARTY_CANONICAL = {i: name for i, (name, _) in enumerate(_PARTY_STEMS)}

_APPROX_RE = re.compile(r"\b(rúm(?:t|lega)?|tæp(?:t|lega)?|um)\s+$")

_ONES = {
    "núll": 0, "eitt": 1, "einn": 1, "tvö": 2, "tveir": 2, "þrjú": 3, "þrír": 3,
    "fjögur": 4, "fjórir": 4, "fimm": 5, "sex": 6, "sjö": 7, "átta": 8, "níu": 9,
    "tíu": 10, "ellefu": 11, "tólf": 12, "þrettán": 13, "fjórtán": 14,
    "fimmtán": 15, "sextán": 16, "sautján": 17, "átján": 18, "nítján": 19,
}
_TENS = {
    "tuttugu": 20, "þrjátíu": 30, "fjörutíu": 40, "fimmtíu": 50,
    "sextíu": 60, "sjötíu": 70, "áttatíu": 80, "níutíu": 90,
}
_NUMBER_WORD_RE = re.compile(
    r"\b(?:(?:" + "|".join(_TENS) + r")(?:\s+og\s+(?:" + "|".join(_ONES) + r"))?"
    r"|(?:" + "|".join(_ONES) + r"))\b(?:\s+og\s+hálf\w*)?",
    re.IGNORECASE,
)
_DIGIT_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# "NN prósent" or "NN%" — the number-word or digit immediately preceding
# "prósent"/"%", with an optional "rúm/tæp/um" approximation marker before it.
_PERCENT_RE = re.compile(
    r"(?P<approx>(?:rúm(?:t|lega)?|tæp(?:t|lega)?|um)\s+)?"
    r"(?P<num>\d+(?:[.,]\d+)?|(?:" + "|".join(list(_TENS) + list(_ONES)) + r")"
    r"(?:\s+og\s+(?:" + "|".join(_ONES) + r"))?(?:\s+og\s+hálf\w*)?)"
    r"\s*(?:prósent\w*|%)",
    re.IGNORECASE,
)


def _word_to_number(text: str) -> float:
    text = text.strip().lower()
    if re.match(r"^\d", text):
        half = " og hálf" in text
        base = float(_DIGIT_NUMBER_RE.match(text).group().replace(",", "."))
        return base + 0.5 if half else base
    half = "hálf" in text
    text = re.sub(r"\s+og\s+hálf\w*", "", text).strip()
    parts = text.split(" og ")
    if len(parts) == 2:
        value = _TENS[parts[0]] + _ONES[parts[1]]
    else:
        value = _TENS.get(text, _ONES.get(text))
    if value is None:
        raise ValueError(f"unparsed number word: {text!r}")
    return value + 0.5 if half else value


def _sentences(text: str) -> list[str]:
    # Icelandic uses standard sentence-final punctuation; good enough for
    # prose that's already been through a professional editor.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract_prose_poll_figures(paragraphs: list[str]) -> tuple[list[dict], list[str]]:
    """Party/percent pairs from prose, for articles with no chart.

    Verb mood distinguishes a current poll figure ("fengi", "mælist" —
    conditional/present, "if the election were held now") from a historical
    election result mentioned for comparison ("fékk", "fengu" — simple
    past). A sentence with a historical cue and no poll cue is skipped
    entirely, even if it has a percent number — that number belongs to a
    past election, not this poll. `current_party` carries the most recently
    named party across sentences (and paragraphs) so pronoun-only sentences
    ("Flokkurinn fékk X í kosningum en fengi nú Y") still resolve.
    """
    results = []
    skipped = []
    current_party = None
    seen_parties: set[str] = set()

    for para in paragraphs:
        for sentence in _sentences(para):
            party_matches = list(_PARTY_RE.finditer(sentence))
            if party_matches:
                last = party_matches[-1]
                idx = next(i for i, g in last.groupdict().items() if g)
                current_party = _PARTY_CANONICAL[int(idx[1:])]

            percent_matches = list(_PERCENT_RE.finditer(sentence))
            if not percent_matches:
                continue

            poll_cue_matches = list(_POLL_CUE_RE.finditer(sentence))
            historical_cue_matches = list(_HISTORICAL_CUE_RE.finditer(sentence))
            if not poll_cue_matches:
                skipped.append(
                    f"[{'historical, no poll cue' if historical_cue_matches else 'no poll cue'}] {sentence}"
                )
                continue

            # "nú" (now) is a more specific and more reliably present marker
            # for the current figure than any fixed verb list — historical
            # baselines get phrased too many distinct ways ("fékk þá X",
            # "X frá kosningum", "hafa verið stöðugir í X frá kosningum") to
            # enumerate, but the current number is consistently "nú" when a
            # sentence states both. When present with 2+ numbers, it wins
            # outright; the other numbers in that sentence are not
            # considered at all, regardless of verb-cue proximity.
            nu_matches = [m for m in re.finditer(r"\bnú\b", sentence)]
            preferred = None
            if nu_matches and len(percent_matches) > 1:
                nu_pos = nu_matches[0].start()
                preferred = min(percent_matches, key=lambda m: abs(m.start() - nu_pos))

            for pm in percent_matches:
                if preferred is not None and pm is not preferred:
                    continue

                if preferred is None:
                    # A number belongs to a poll figure only if it's nearer a
                    # poll-cue verb ("fengi"/"mælist") than a historical-cue
                    # verb ("fékk"/"fengu") — distinguishes "fékk fimm... en
                    # fengi nú 14" (only 14 counts) from a sentence with no
                    # historical cue at all (every number counts).
                    nearest_poll_dist = min(abs(pm.start() - c.start()) for c in poll_cue_matches)
                    if historical_cue_matches:
                        nearest_hist_dist = min(abs(pm.start() - c.start()) for c in historical_cue_matches)
                        if nearest_hist_dist < nearest_poll_dist:
                            continue

                # Nearest party mention to *this* number, not just the first
                # party named anywhere in the sentence — comparison sentences
                # ("Sjálfstæðisflokkurinn ... 39%, ... Samfylkingin ... 19%")
                # otherwise misattribute the second number to the first party.
                # Gap between spans, not start-to-start: a long party name
                # immediately before the number (e.g. "Sjálfstæðisflokkurinn",
                # 21 chars) must not look farther away than a short one after
                # it just because start-to-start distance ignores span length.
                if party_matches:
                    def _gap(pmatch):
                        return max(0, max(pm.start() - pmatch.end(), pmatch.start() - pm.end()))

                    party_match = min(party_matches, key=_gap)
                    idx = next(i for i, g in party_match.groupdict().items() if g)
                    party = _PARTY_CANONICAL[int(idx[1:])]
                else:
                    party = current_party

                if not party:
                    skipped.append(f"[no party in context] {sentence}")
                    continue

                if party in seen_parties:
                    # A party's first mention is its topline figure. Later
                    # re-mentions in the same article are sub-group /
                    # geographic breakdowns (verified: a district-level
                    # "39% east of Elliðaá" re-mention of a party whose
                    # citywide topline was already captured earlier) — not a
                    # correction, so don't overwrite.
                    skipped.append(f"[{party} already recorded, later mention ignored] {sentence}")
                    continue

                try:
                    pct = _word_to_number(pm.group("num"))
                except (ValueError, KeyError):
                    skipped.append(f"[unparsed number {pm.group('num')!r}] {sentence}")
                    continue

                results.append(
                    {"party": party, "pct": pct, "approx": bool(pm.group("approx")), "source": "prose"}
                )
                seen_parties.add(party)

    return results, skipped


def _article_url(raw_url: str) -> str:
    """Article listing URLs use the nyr.ruv.is staging host; www.ruv.is serves the same content."""
    return raw_url.replace("nyr.ruv.is", "www.ruv.is").rstrip("/")


def _find_articles(node, out: list[dict]) -> list[dict]:
    if isinstance(node, dict):
        if node.get("__typename") == "Article" and "id" in node and node.get("title"):
            out.append(node)
        for v in node.values():
            _find_articles(v, out)
    elif isinstance(node, list):
        for v in node:
            _find_articles(v, out)
    return out


def _guess_scope(title: str, subtitle: str) -> str:
    text = f"{title} {subtitle or ''}"
    return "reykjavik" if REYKJAVIK_KEYWORDS.search(text) else "national"


def _guess_pollster(title: str, subtitle: str) -> str | None:
    text = f"{title} {subtitle or ''}"
    m = _POLLSTER_RE.search(text)
    if not m:
        return None
    for stem, canonical in _POLLSTER_CANONICAL.items():
        if m.group(1).lower().startswith(stem):
            return canonical
    return None


def fetch_article_list() -> list[dict]:
    resp = httpx.get(TAG_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    m = _NEXT_DATA_RE.search(resp.text)
    if not m:
        raise RuntimeError(f"__NEXT_DATA__ not found on {TAG_URL} — page structure changed")
    data = json.loads(m.group(1))
    articles = _find_articles(data, [])

    seen = {}
    for a in articles:
        seen[a["id"]] = {
            "id": a["id"],
            "title": a["title"],
            "subtitle": a.get("subtitle"),
            "url": _article_url(a["url"]),
            "published_at": a.get("first_published_at"),
            "scope": _guess_scope(a["title"], a.get("subtitle")),
            "pollster": _guess_pollster(a["title"], a.get("subtitle")),
        }
    return sorted(seen.values(), key=lambda r: r["published_at"] or "", reverse=True)


def cmd_list(args):
    articles = fetch_article_list()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RAW_DIR / "articles.json"
    out_file.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    shown = [a for a in articles if not args.scope or a["scope"] == args.scope]
    print(f"{len(shown)} poll articles ({out_file} holds all {len(articles)})")
    for a in shown[: args.limit]:
        pollster = a["pollster"] or "?"
        print(f"  [{a['id']}] {a['published_at'][:10]} ({a['scope']}, {pollster}) {a['title']}")


async def _scrape_article(url: str) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60_000)

        # Chart bars: SVG <path aria-label="Samfylking, 22.2%."> per party
        bars = await page.eval_on_selector_all(
            'path[aria-label*="%"]',
            "els => els.map(e => e.getAttribute('aria-label'))",
        )
        parties = []
        source = "chart"
        for label in bars:
            m = re.match(r"^(.+?),\s*([\d.,]+)\s*%\.?$", label.strip())
            if m:
                parties.append(
                    {"party": m.group(1).strip(), "pct": float(m.group(2).replace(",", "."))}
                )

        skipped: list[str] = []
        if not parties:
            # No chart on this article — fall back to prose. Scoped to
            # .article-body, not all of <main>: the page footer/sidebar
            # carries unrelated "most read" and nav content that could
            # coincidentally contain party names. See
            # extract_prose_poll_figures() for why verb mood, not proximity,
            # decides which numbers are current poll figures — the
            # first-mention-wins dedup there (not this selector) is what
            # actually keeps embedded "related article" teaser excerpts
            # (rendered inline in .article-body, same as real paragraphs)
            # from overwriting this article's own topline numbers.
            body_text = await page.eval_on_selector(".article-body", "el => el.innerText")
            paragraphs = [p for p in body_text.split("\n") if p.strip()]
            prose_results, skipped = extract_prose_poll_figures(paragraphs)
            for r in prose_results:
                parties.append({"party": r["party"], "pct": r["pct"], "approx": r["approx"]})
            source = "prose" if prose_results else "none"

        title = await page.title()
        await browser.close()

    return {"url": url, "page_title": title, "parties": parties, "source": source, "prose_skipped": skipped}


def cmd_fetch(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    articles = json.loads((RAW_DIR / "articles.json").read_text(encoding="utf-8")) if (
        RAW_DIR / "articles.json"
    ).exists() else fetch_article_list()
    by_id = {a["id"]: a for a in articles}

    if args.all:
        targets = articles[: args.limit]
    elif args.article_id:
        if args.article_id not in by_id:
            print(f"Unknown article id {args.article_id} — run `list` first", file=sys.stderr)
            sys.exit(1)
        targets = [by_id[args.article_id]]
    else:
        print("Provide an article id or --all", file=sys.stderr)
        sys.exit(1)

    rows = []
    for meta in targets:
        print(f"  fetching [{meta['id']}] {meta['title']} ...")
        result = asyncio.run(_scrape_article(meta["url"]))
        if not result["parties"]:
            print(f"    no chart and no prose figures extracted ({len(result['prose_skipped'])} sentences skipped)")
            continue
        print(f"    {len(result['parties'])} parties via {result['source']}"
              + (f", {len(result['prose_skipped'])} sentences skipped" if result["source"] == "prose" else ""))
        for p in result["parties"]:
            rows.append(
                {
                    "article_id": meta["id"],
                    "published_at": meta["published_at"],
                    "scope": meta["scope"],
                    "pollster": meta["pollster"],
                    "title": meta["title"],
                    "party": p["party"],
                    "pct": p["pct"],
                    "approx": p.get("approx", False),
                    "source": result["source"],
                }
            )
        (RAW_DIR / f"{meta['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not rows:
        print("No poll data extracted.")
        return

    df = pl.DataFrame(rows)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = PROCESSED_DIR / "skodanakannanir.csv"
    if out_file.exists():
        existing = pl.read_csv(out_file)
        df = pl.concat([existing, df], how="diagonal_relaxed").unique(
            subset=["article_id", "party"], keep="last"
        )
    df = df.sort(["published_at", "article_id", "party"])
    df.write_csv(out_file)
    print(f"{len(rows)} party-support rows written -> {out_file}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List poll articles from the RÚV tag page")
    p_list.add_argument("--scope", choices=["national", "reykjavik"], default=None)
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="Scrape party-support numbers from one or more articles")
    p_fetch.add_argument("article_id", type=int, nargs="?", default=None)
    p_fetch.add_argument("--all", action="store_true", help="Fetch every listed article")
    p_fetch.add_argument("--limit", type=int, default=10)
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

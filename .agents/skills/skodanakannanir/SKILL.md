---
name: skodanakannanir
description: RÚV + Vísir + Heimildin opinion-poll aggregators (skoðanakannanir) — national Alþingi and Reykjavík city party support across pollsters (Maskína, Prósent, Gallup).
---

# Skoðanakannanir — RÚV + Vísir + Heimildin Opinion-Poll Aggregators

Three outlets' discovery mechanisms, each surfacing news coverage of opinion
polls from every major Icelandic pollster — not just one firm's own
dashboard. Use this skill for "what's the latest party support / fylgi
flokka" questions, at either national (Alþingi) or Reykjavík city
(borgarstjórn) level.

**Use Vísir/Heimildin for discovery, RÚV for numbers.** Verified: RÚV's tag
page holds only ~51 recent items with no working pagination (see Caveat 7),
while Vísir's is genuinely paginated back to at least September 2021 and
Heimildin's search goes back to 2019+ for this query. `list --source visir
--since 2025 --scope reykjavik` alone found 40 Reykjavík polls against RÚV's
4 — including the entire Feb–May 2026 city-election polling season RÚV's own
tag had already dropped. RÚV and Vísir are both wired into `fetch`'s
chart/prose number-extraction (see Vísir Extraction below) — Heimildin is
still discovery-only. Vísir is actually the *simpler* of the two to fetch:
its article bodies are server-rendered, so `fetch_visir_article()` is plain
`httpx`, no Playwright, no browser at all (RÚV needs one — see the RÚV
`fetch` section).

**Related but different scope:** the [`maskina`](../maskina/SKILL.md) skill
covers Maskína's own structured Tableau dashboard directly — one pollster,
always current. This skill covers the RÚV-reported layer across *all*
pollsters (Maskína, Prósent, Gallup, Félagsvísindastofnun), including polls
those firms only ever published as one-off RÚV stories.

## Two-Stage Pipeline

1. **`list`** — plain HTTP GET of the tag page, no browser needed. The page
   is server-rendered: `https://www.ruv.is/frettir/tag/skodanakonnun`
   embeds a full `__NEXT_DATA__` JSON blob containing every listed article
   (id, title, subtitle, url, `first_published_at`) as GraphQL `Article`
   objects. Walk the JSON tree for `"__typename": "Article"` nodes — do not
   regex the raw HTML, the JSON is already there and clean.

2. **`fetch <id>`** — one article's party-support numbers, via Playwright.
   **Article bodies are client-side rendered** — `httpx`/`curl` sees only
   the page chrome (nav, footer, ~0 chars of article text); the real content
   only exists in the DOM after JS hydration. Confirmed by comparing a raw
   `curl` fetch (empty `<main>`) against a Chrome DevTools MCP snapshot of
   the same URL (full prose + chart).

## Where the Numbers Actually Live

Poll articles that include a chart render it as **Highcharts**, and each bar
is an SVG `<path>` with a real `aria-label` attribute:

```html
<path aria-label="Samfylking, 22.2%." ...>
```

This is the extraction target — not OCR, not Highcharts internals, not
color-matching against Iceland's standard party colors (which the chart also
uses consistently, but the aria-labels are simpler and don't require a color
lookup table). In Playwright:

```python
bars = await page.eval_on_selector_all(
    'path[aria-label*="%"]',
    "els => els.map(e => e.getAttribute('aria-label'))",
)
# ["Samfylking, 22.2%.", "Sjálfstæðisflokkur, 19.3%.", ...]
```

Parse with `r"^(.+?),\s*([\d.,]+)\s*%\.?$"`.

### Prose Fallback — When There's No Chart

Verified: articles 451831 and 428434 (both real Reykjavík polls, ~5,900+
chars each) have **zero** chart `<path>` elements. The numbers only exist in
prose, and extracting them correctly needs three Icelandic-grammar signals,
not proximity alone — verified against two full real articles end-to-end
(hand-traced, then run through Playwright, then cross-checked against a
manual reading of the rendered page):

1. **Verb mood distinguishes a current poll figure from a historical
   election result.** `mælist`/`mælast`/`fengi`/`fengju`/`stæði`/`stæðu`/
   `stendur` (conditional/present — "if the election were held now") mark a
   poll number; `fékk`/`fengu` (simple past) mark a result from an actual
   past election mentioned for comparison. These are genuinely distinct word
   forms in Icelandic, not a fuzzy heuristic.
2. **"nú" (now) beats verb-cue proximity when both appear in one sentence.**
   Historical baselines get phrased too many ways to enumerate as a verb
   list — `"fékk þá 19 prósent"`, `"tæp tólf í síðasta mánuði"`, `"hafa
   verið stöðugir í tæplega tólf prósent frá kosningum"` — but the *current*
   number is consistently marked `nú` whenever a sentence states both. When
   `nú` is present with 2+ percent numbers, it wins outright over the
   verb-proximity check.
3. **Nearest-party-to-number pairing, not first-party-in-sentence.**
   Comparison sentences ("Sjálfstæðisflokkurinn er langstærstur austan
   Elliðaáa með 39%, ... Samfylkingin mælist með 19%") name two parties —
   pairing every number in the sentence with whichever party is named first
   silently reattributes the second party's number to the first. Distance
   must be measured edge-to-edge (`min` over the four start/end
   combinations), not start-to-start — start-to-start systematically
   penalizes a long party name immediately before the number in favor of a
   short one further away.
4. **First mention per party wins; later re-mentions are ignored, not
   merged.** A party's topline citywide number is always stated once, early.
   Later re-mentions in the same article are sub-group breakdowns — verified
   example: article 451831 restates "Sjálfstæðisflokkurinn ... 39%" in a
   district-level paragraph ("east of Elliðaá") *after* already stating the
   citywide 29% earlier. Overwriting on second mention would silently
   replace the correct citywide topline with a geographic subset.

`extract_prose_poll_figures()` implements all four and returns
`(results, skipped)` — every sentence it declines to use is logged with a
reason (`no poll cue`, `historical, no poll cue`, `<party> already recorded,
later mention ignored`, `no party in context`, `unparsed number`), printed
via `fetch`'s `prose_skipped` count and saved in the raw `{id}.json`. Nothing
is silently dropped or guessed — a skip means "read this one by hand."

**Known residual gap:** constructions with no recognized poll-cue verb at
all — e.g. `"Fylgi Sósíalistaflokksins er farið úr 7,8 í 10,4 prósent"`
("went from X to Y") — are correctly skipped rather than mis-parsed, but
that also means they're **not extracted**. Verified on article 428434: 7 of
9 parties resolved automatically, 2 (Sósíalistaflokkur, Vinstri græn) needed
manual reading of the skipped-sentence log. Extending the cue-verb list is
possible but each new construction is a real (if small) NLP-scope increase
— weigh against just reading the skip log for the rare case.

## Article JSON Shape (from `__NEXT_DATA__`)

```json
{
  "__typename": "Article",
  "id": 479261,
  "title": "Samfylkingin stærst en Sjálfstæðisflokkur vinnur á",
  "subtitle": "Samfylkingin mælist með mest fylgi í könnun Maskínu en Sjálfstæðisflokkurinn er tveimur og hálfu prósentustigi á eftir. ...",
  "url": "https://nyr.ruv.is/frettir/innlent/2026-06-24-samfylkingin-staerst-en-sjalfstaedisflokkur-vinnur-a-479261/",
  "first_published_at": "2026-06-24T08:04:27.617332Z",
  "topic": {"category": {"slug": "innlent", "title": "Innlendar fréttir"}}
}
```

- `url` uses the `nyr.ruv.is` staging host in the embedded JSON — swap for
  `www.ruv.is`, both serve the same content but the public site is the
  documented one.
- `topic.category.slug` is always `innlent` for both national and Reykjavík
  polls — it does **not** distinguish scope. Guess scope from
  title/subtitle keywords instead (`reykjavík`, `borgarstjórn`, `í borginni`).
- `tags` is `null` in the listing query (per-article tags like `maskína`,
  `Skoðanakönnun`, party names only appear on the rendered article page,
  not in this JSON).

## Pollster Detection — the "Prósent" Trap

**"Prósent" is both a pollster's proper name and the ordinary Icelandic word
for "percent."** A case-insensitive substring match on `prósent` false-fires
on nearly every poll subtitle, because generic phrases like
`"...prósentustigi á eftir"` contain the substring. The fix verified against
real data: match case-sensitively on the **capitalized stem**
(`\bPrósent\w*\b`), since the common noun is lowercase mid-sentence in
practice and the company name is not:

```python
_POLLSTER_RE = re.compile(r"\b(Maskín\w*|Prósent\w*|Gallup\w*|Félagsvísindastofnun\w*)\b")
```

`Maskína`/`Gallup`/`Félagsvísindastofnun` have no ordinary-word collision and
would work case-insensitively too, but the shared regex is simpler to keep
one way.

## Scope Detection

`national` vs `reykjavik`, guessed from title+subtitle:
`r"reykjav[ií]k|borgarst[jó]órn|í borginni"` (case-insensitive). This is a
geography classifier, not a topic classifier — a Reykjavík-scope poll about
airport siting (`Reykjavíkurflugvöllur`) will be tagged `reykjavik` even
though it isn't a party-support question. That's expected: the skill scopes
by *where*, not *what*.

## Vísir Discovery

`https://www.visir.is/t/2296/skodanakannanir/{page}` — server-rendered HTML
(no JSON blob), `<article class="article-item">` cards, genuinely paginated:
verified by fetching pages 1/5/10/20/40 and finding distinct,
chronologically-descending content from July 2026 (page 1) back through
September 2021 (page 20), with page 40 empty (end of history reached).
`fetch_visir_article_list()` walks pages until an empty page, or — with
`--since <year>` — until a whole page's articles are all older than the
cutoff (pages are date-descending, so that's a safe stopping point without
walking all ~35+ pages every time).

```html
<article class="article-item ...">
  <h2 class="article-item__title"><a href="/g/20262904348d/fylgi-...">Fylgi Sjálfstæðis­flokks ekki meira í sex ár</a></h2>
  <p class="article-item__text">Sjálfstæðisflokkurinn mælist með 24,9 prósenta fylgi í nýjum þjóðarpúlsi Gallups. ...</p>
  <time class="article-item__time">1.7.2026 19:45</time>
</article>
```

- **The listing subtitle (`article-item__text`) often states the headline
  number directly** — unlike RÚV's subtitles, which are usually pure prose
  summary. For a quick "what's the latest" answer, `list`'s output alone may
  already be enough; no need to visit the article page.
- Titles/subtitles carry HTML entities (`&#xF6;` = ö) and literal soft
  hyphens (`\xad`, rendered as `­`) mid-word from the source markup — both
  must be stripped/unescaped (`html.unescape` + `.replace("\xad", "")`) or
  matching against `_PARTY_RE`/`_POLLSTER_RE` silently fails on words that
  are visually identical but byte-different.
- Dates are Icelandic `D.M.YYYY HH:MM` (`"1.7.2026 19:45"`), converted to
  ISO 8601 by `_visir_date_to_iso()`.
- IDs are the numeric prefix of the `/g/<id>d/<slug>` URL path, stored as
  `visir-<id>` (RÚV ids are stored as `ruv-<id>` for the same reason —
  disambiguating which source's numbering a bare id belongs to once both
  are combined in one cache file).
- **Recurring feature to know about:** "Kosningaspá Vísis" (Vísir's own
  election-forecast/projection series) — not a raw poll report, an
  aggregated model. Shows up correctly under this skill's scope/pollster
  guessing as `pollster: null` (no known-pollster name in the text) since
  it isn't a single firm's poll.
- The same underlying poll is frequently reported by **both** RÚV and
  Vísir/Heimildin. `cross_reference_duplicates()` (run automatically when
  `--source all`) flags this: a Vísir or Heimildin article gets
  `duplicate_of: "<ruv-id>"` and the matched RÚV article gets
  `also_reported_by: [{source, id, url}, ...]` when — and only when — all
  three hold: same non-null pollster (exact string match), same scope, and
  published within 48 hours of each other. RÚV is always the anchor side of
  the match (it's the only source with number-extraction wired up — see
  Extraction Status below). `list`'s printed view and its distinct-article
  count exclude anything with `duplicate_of` set; the saved `articles.json`
  keeps every row either way, so nothing is lost, just marked. Verified
  match (2026-03-24): RÚV's "Samfylkingin dalar enn" and Vísir's "Fylgi
  Samfylkingar ekki verið minna í eitt ár", ~15 hours apart, both Maskína,
  both national — genuinely the same poll release covered two ways.
  **When there's more than one same-pollster/same-scope candidate in the
  window, nothing is merged** — logged as `ambiguous, N candidates` instead.
  This is common and expected, not a bug: Vísir regularly runs a follow-up
  angle piece on the same poll a day or two after the first report (verified
  across RÚV+Vísir+Heimildin combined, 2024–2026: 7 ambiguous cases, each
  with 2-5 genuinely distinct stories about one poll release). Picking the
  "closest in time" candidate would be a guess dressed up as a match — left
  for manual reconciliation instead.

## Vísir Extraction

`fetch_visir_article(url)` — plain `httpx`, no browser. Verified against a
real article (visir-20262904348): the full prose, including the methodology
paragraph, is present in a `curl`-only fetch. No Highcharts/`aria-label`
chart was found on that article either (the chart check still runs first,
in case some Vísir articles do embed one) — Vísir's house style leans on
thorough prose instead, and `extract_prose_poll_figures()` (the exact same
function RÚV's prose fallback uses — this is Icelandic-grammar logic, not
RÚV-specific) is the primary path here, not a fallback.

**Locating the real content:** the article body spans two HTML regions that
both have to be captured — a lead `<p>` right after an
`<!-- ARTICLE SUMMARY -->` comment (sits *outside* the body div, and is
often where the headline number lives — verified: "Sjálfstæðisflokkurinn
mælist með 24,9 prósenta fylgi..." is the very first sentence), followed by
`<div itemprop="articleBody">` containing the rest as `<p>` tags. Both
regions run up to the first `<hr>` after the summary marker, which reliably
follows the last real paragraph (share buttons and "RELATED NEWS" come
after it) — verified: exactly 10 `<p>` tags in that span, matching a full
manual read including the closing methodology sentence.

**Two bugs caught during verification, both real, neither hypothetical —
found by fetching this one real article and checking the output against a
manual read before trusting the extraction at all:**

1. **`<p class="">` doesn't match a literal `<p>` regex.** One of the
   article's ten paragraphs (Miðflokkur's, "mælist nú 15,1 prósent") used
   `<p class="">` instead of bare `<p>` — an empty but present attribute.
   The paragraph-extraction regex must be `<p[^>]*>`, not `<p>`, or that
   paragraph silently vanishes with no error, no skip log entry, nothing —
   it's just never seen.
2. **A stale `current_party` can attach to an aggregate sentence that names
   no party at all.** "Samanlagt fylgi ríkisstjórnarflokkanna dregst þó
   saman um eitt prósentustig og mælist 42 prósent..." ("Combined support
   for the governing coalition parties... polls at 42%") has a poll-cue verb
   (`mælist`) and a number, but names no single party — `_PARTY_RE` doesn't
   match "ríkisstjórnarflokkanna." The pronoun-carry design (`current_party`
   persisting across sentences for "Flokkurinn fékk X en fengi nú Y") wrongly
   inherited whichever party was named two sentences earlier and recorded
   "um eitt prósentustig" (1%, approx) as if it were that party's number.
   Fixed with `_AGGREGATE_RE` (`samanlagt`/`flokkanna`) — a sentence matching
   it gets `party = None` unconditionally, skipping the `current_party`
   fallback rather than guessing an owner for a number that has none.

**A third gap found and left unfixed, deliberately:** "úr X í Y" ("from X to
Y") is a common current-value marker with no recognized verb at all —
"Fylgi Framsóknarflokksins ... fór úr 6,7 prósentum í 5,3 prósent",
"Stuðningur við Sósíalistaflokkinn eykst ... úr 2,4 prósentum í 4,3
prósent" — both appeared in the same single article. `_TREND_CUE_RE` handles
this and stands in for a poll-cue verb on its own (see
`extract_prose_poll_figures`'s docstring) — but when the "from" number's
`prósent`/`prósentum` word is dropped for the "from" side (verified: the
live article literally has the typo "úr 2, prósentum í 4,3 prósent" — a
missing digit after the comma, `_PERCENT_RE` never matches "2," at all), only
one `_PERCENT_RE` match exists in the sentence and there's nothing to rank it
against. That case is logged (`trend cue but no verb, single number,
ambiguous`) and skipped rather than assumed to be the "Y" value — right call
even though in this specific instance it happened to be correct, because the
rule can't tell "single leftover Y with a botched X" apart from "single
number that's actually the historical X, with Y omitted by the writer."

## Heimildin Discovery

`https://heimildin.is/leit/?q=<query>&page=<n>` (search, default query
`"skoðanakönnun"`) — **not** a tag page, Heimildin has no equivalent to
RÚV/Vísir's. The trailing slash on `/leit/` matters: `heimildin.is/leit`
(no slash) 301-redirects to `/leit/`, and query params on the *original*
URL are preserved through that redirect, so either form works via `httpx`
(which follows redirects) — but hitting `/leit/` directly skips a hop.
Server-rendered HTML, genuinely paginated via `&page=N`: verified fetching
pages 1 and 2 of the default query and finding zero overlapping article
IDs, with page 1 spanning Nov 2024 and page 2 jumping to 2019 — a real
content gap for this specific query on this outlet, not a pagination bug
(the "Niðurstöður eru í tímaröð" / "results are in chronological order"
label on the search page is accurate).

```html
<article class="article-item ...">
  <a href="/grein/23196/sjalfstaedisflokkurinn-sigur-sosialistaflokkurinn-saekir-a/">
    <div class="article-item__headlines">
      <h1 class="article-item__headline">Sjálf&shy;stæð&shy;is&shy;flokk&shy;ur&shy;inn síg&shy;ur, ...</h1>
    </div>
    <div class="article-item__subhead">
      <time class="article-item__pubdate" datetime="2024-11-08 15:06">8. nóvember 2024</time>
      Fylgi Sjálf&shy;stæð&shy;is&shy;flokks&shy;ins mæl&shy;ist rétt rúm tólf pró&shy;sent ...
    </div>
  </a>
</article>
```

- `datetime="2024-11-08 15:06"` is already ISO-shaped (space instead of
  `T`) — `fetch_heimildin_article_list()` just replaces the space and
  appends `:00`, no Icelandic-date parsing needed (unlike Vísir).
- Titles/subheads use `&shy;` (soft hyphen) entities mid-word, same
  strip-after-unescape requirement as Vísir's `\xad` — `&shy;` decodes to
  `\xad` via `html.unescape`, then gets stripped the same way.
- IDs are the numeric segment of `/grein/<id>/<slug>/`, stored as
  `heimildin-<id>`.
- The default search query is literally `"skoðanakönnun"` — broadening it
  (e.g. adding `"kosningaspá"` or running multiple queries and merging) is
  a plausible way to widen coverage further; not done here, single-query
  is what's verified.

## Extraction Status by Source

| Source | Discovery (`list`) | Numbers (`fetch`) |
|---|---|---|
| RÚV | ✅ `__NEXT_DATA__` JSON | ✅ chart `aria-label` + prose fallback (needs Playwright — client-rendered) |
| Vísir | ✅ paginated HTML | ✅ chart check + prose fallback (plain `httpx` — server-rendered, no browser) |
| Heimildin | ✅ paginated search HTML | ❌ not built — `fetch heimildin-...` errors with the URL to read by hand |

**Heimildin's paywall is per-article, not per-outlet — do not assume every
article is free just because some were.** Verified on only 3 articles (2
poll stories + the Samherji investigation), all fully open logged-out; a
larger sample would very likely turn up truncated ones needing the stored
`heimildin-is-credentials` login to read past the teaser, the same pattern
confirmed on VB. Treat "some Heimildin poll articles may be paywalled" as
the working assumption until `fetch` is actually built for this source and
that gets tested at scale, not "Heimildin poll articles are free" as
previously (over-)stated after too small a sample.

## Script Usage

```bash
uv run python scripts/skodanakannanir.py list                                  # RÚV only (default) -> data/raw/skodanakannanir/articles.json
uv run python scripts/skodanakannanir.py list --source visir --since 2025      # Vísir only, paginated back to a year cutoff
uv run python scripts/skodanakannanir.py list --source heimildin --since 2020  # Heimildin only, search-based
uv run python scripts/skodanakannanir.py list --source all --since 2025 --scope reykjavik --limit 30
uv run python scripts/skodanakannanir.py fetch 479261                          # bare int = RÚV, backward-compatible
uv run python scripts/skodanakannanir.py fetch ruv-479261                      # equivalent, explicit
uv run python scripts/skodanakannanir.py fetch visir-20262904348               # Vísir works too — plain httpx, no browser
uv run python scripts/skodanakannanir.py fetch heimildin-23196                 # errors clearly: not implemented yet, prints the URL to read by hand
uv run python scripts/skodanakannanir.py fetch --all --limit 20                # batch over cached RÚV + Vísir articles (Heimildin excluded, not built)
```

## Data Files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/skodanakannanir/articles.json` | JSON | Article listing from whichever `--source` was last run (id prefixed `ruv-`/`visir-`, title, subtitle, url, published_at, scope, pollster, source) |
| `data/raw/skodanakannanir/{id}.json` | JSON | Raw scrape result for one RÚV or Vísir article (page title + party/pct pairs) |
| `data/processed/skodanakannanir.csv` | CSV | Long-format party support, RÚV + Vísir: article_id, published_at, scope, pollster, title, party, pct, approx, source |

## Caveats

1. **Not every poll article has a chart** — see Prose Fallback above.
   `fetch` tries the chart first, falls back to prose, and reports which
   source it used (`chart`/`prose`/`none`).
2. **`list`'s cache file always holds the full unfiltered set for whatever
   `--source` was requested** — `--scope` only filters what's printed to the
   terminal, not what's written to `articles.json`. But `--source` *does*
   determine what's in the cache: `list` (RÚV only) followed by `fetch
   visir-...` fails with "unknown article id" until you re-run `list
   --source all` (or `--source visir`) to populate the cache with Vísir rows
   too — verified, this is the actual failure mode, not a hypothetical.
3. **Percentages don't always sum to exactly 100** — verified example
   (article 479261) summed to 99.9 due to per-party rounding in the source
   chart. Treat as expected, not a parsing bug.
4. **`nyr.ruv.is` vs `www.ruv.is`** — the embedded JSON's `url` field points
   at the `nyr.` staging host; `_article_url()` rewrites it to `www.` before
   fetching. Same content either way, but `www.` is the citable public URL
   and still current as of the most recent articles checked (June 2026).
5. **`--all` launches one headless Chromium per *RÚV* article** — no batching
   inside a single browser session. Fine for a handful; expect several
   seconds each for 20+. Vísir articles in the same `--all` batch are much
   cheaper — plain `httpx` GETs, no browser launch at all.
6. **The prose fallback is scoped to `.article-body`, not all of `<main>`.**
   RÚV embeds "related article" teaser cards inline as `<aside>` elements
   between an article's own paragraphs — the `<aside>` itself only holds the
   kicker+title link, but the *excerpt paragraph* that follows it sits in a
   sibling `<div>` styled identically to the article's own paragraphs (same
   `.article-body .maincontent` class), so there is no DOM-level way to tell
   them apart by selector alone. That's exactly what item 4 of the Prose
   Fallback section (first-mention-per-party-wins) guards against — a
   teaser's re-mention of a party already recorded from the real article
   text is ignored rather than overwriting the correct number. `.article-body`
   only trims unrelated page chrome (nav, "most read," footer); it does not
   and cannot exclude the embedded teasers by itself.
7. **RÚV's own topic tagging is inconsistent — the `skodanakonnun` tag is
   not a complete index of poll articles.** Verified: a February 2026
   Reykjavík poll article (id 468121, found via a general web search) is
   tagged with every party name plus `Reykjavíkurborg`, but carries **no**
   `Skoðanakönnun` tag at all — most likely because party-name/location tags
   are auto-applied (entity detection over the content) while the topical
   `Skoðanakönnun` tag is set by a human editor and gets missed. Compounding
   this: **every RÚV tag page — `skodanakonnun`, `borgarstjorn`, and
   `reykjavikurborg` were all checked — caps at the ~51 most recent tagged
   items, with no working pagination** (`?page=2`/`?page=3` return byte-
   identical content to page 1). During a high-volume period (city-election
   season, Feb–May 2026 in this case) that window can be as short as a few
   weeks, silently dropping older-but-still-recent articles regardless of
   which tag you use. `list` surfaces only what's inside that live window —
   there is no way to page back further via any `frettir/tag/*` endpoint
   found so far. **Use `--source visir` (or `all`) instead of chasing this
   with `WebSearch`** — Vísir's tag page has none of these gaps (see Vísir
   Discovery above) and is the better default for anything historical.
   `WebSearch site:ruv.is` (the same fallback the [`ruv`](../ruv/SKILL.md)
   skill documents for `/sok`) remains a fine one-off check, just not the
   first move anymore.

8. **Heimildin discovery is built (`--source heimildin`); a real login was
   also tested and works.** Playwright login against the stored
   `heimildin-is-credentials` was confirmed working — active paid
   subscription, "Þú ert með áskrift að Heimildinni." See Heimildin
   Discovery and Extraction Status above for what's actually wired up
   versus documented-only, and the paywall-is-per-article correction
   (initial 3-article sample all happened to be open; don't generalize
   that to "Heimildin is unpaywalled").

9. **VB (Viðskiptablaðið) has no discovery mechanism found so far, but its
   own commissioned Gallup polls are genuinely valuable and the paywall
   pattern is now understood.** Full findings, verified against a real
   article (`stal-i-stal-i-borginni`, 3 Feb 2026):
   - **No tags.** No `skodanakonnun`/`skoðanakönnun` tag found on the
     article page.
   - **`?s=` search returns nothing.** `vb.is/?s=<query>` 200s but the
     response contains zero article links — likely client-rendered, not a
     usable discovery path as a plain GET.
   - **`/frettir/innlent/` category page has no server-side pagination** —
     only 2 article links in the raw HTML, no `?page=` markers. Same
     client-rendering issue as search.
   - **`sitemap.xml` exists (200 OK, 50,000 URL cap) but article slugs are
     headline-derived, not keyword-descriptive** — e.g. this article's slug
     is `stal-i-stal-i-borginni` ("head to head in the city"), containing
     neither `konnun` nor `fylgi`. Filtering the sitemap by slug keyword
     found 126 historical matches but **zero** from 2025 or later — the
     50k-entry sample plainly doesn't include recent content by slug
     matching, so this isn't a usable discovery path as-is either.
   - **The paywall boundary is the URL, not the content type.** The public,
     un-paywalled URL (`.../stal-i-stal-i-borginni-/`, trailing hyphen) is a
     *teaser* — real prose, 2 of ~10 parties' numbers, genuinely useful on
     its own. The **same article at the URL without the trailing hyphen**
     (`.../stal-i-stal-i-borginni/`) is the full version — every party,
     direct quotes from the party leader, full methodology. Both were
     fetched and diffed to confirm this pattern: the "Áskrifendur geta
     lesið fréttina í heild" ("subscribers can read it in full") note on
     the teaser links directly to that unsuffixed URL.
   - **A logged-in session unlocks the unsuffixed URL directly** — verified
     via Chrome DevTools MCP on the user's live, already-authenticated
     browser session (not a fresh login this skill performed — the session
     predated this check). No further auth flow needed once a session
     cookie exists; this skill does not yet manage that cookie for
     unattended/scripted use.
   - **VB's poll credit was previously unseen: VB commissions its own
     Gallup polls**, not just Maskína/Prósent/Gallup-for-somebody-else —
     "könnun sem Gallup gerði fyrir Viðskiptablaðið." Add `Viðskiptablaðið`
     as a pollster-commissioner distinct from the pollster itself if VB
     coverage gets built out.
   - **VB's poll charts use Infogram**, not Highcharts — a genuinely
     different embed (`e.infogram.com` iframe) if chart-based extraction is
     ever built for this source. Not investigated further (no aria-label
     equivalent confirmed).
   - **A one-off election alliance surfaced that isn't in the standing
     party list**: "Vor til vinstri" — VG running a joint 2026 Reykjavík
     city-council list with Vor, led by Sanna Magdalena Mörtudóttir
     (ex-Sósíalistaflokkur city councillor) after she left that party's
     leadership in 2025. Deliberately **not** added to `_PARTY_STEMS` —
     it's a single-election joint list, not a standing national party, and
     hardcoding election-specific alliances into the general regex would
     misfire on other elections.
   - **Net assessment: extraction is solved (once you have the real URL and
     a session), discovery is not.** Until a real discovery path is found —
     candidates not yet tried: an actual XHR-based search API distinct from
     the `?s=` GET, RSS if one exists, or simply `WebSearch site:vb.is` per
     poll as a manual backfill — VB stays a manual/occasional source, not
     wired into `list`/`fetch`.

## Related Skills

- [maskina](../maskina/SKILL.md) — Maskína's own structured Tableau dashboard, one pollster, always current
- [ruv](../ruv/SKILL.md) — general RÚV news/TV search and download (tag-page pattern, yt-dlp)
- [reykjavik](../reykjavik/SKILL.md) — Reykjavík city open data (not polls, but same municipal-politics domain)

---
name: maskina
description: Maskína public opinion polls — structured data via Tableau VizQL + WordPress API. First stop for poll questions, before article-scraping skills.
---

# Maskína — Public Opinion Polls

Public opinion polls and surveys from Iceland's leading polling company. Two data sources: WordPress articles (prose) and Tableau Public dashboard (structured).

**This is the first stop for opinion-poll questions.** The data here comes
structured, straight from the pollster — no browser, no news-article
scraping. Only when the question needs other pollsters (Gallup, Prósent,
Félagsvísindastofnun), cross-pollster comparison, or polls Maskína never
published itself should you fall back to the heavier `skodanakannanir` skill
(number extraction from RÚV/Vísir/Heimildin news articles).

## Data Sources

### 1. WordPress REST API (articles)

**Base URL:** `https://maskina.is/wp-json/wp/v2/posts`

Open API, no authentication. Standard WP REST endpoints.

```bash
# Latest posts
curl 'https://maskina.is/wp-json/wp/v2/posts?per_page=5&orderby=date&order=desc&_fields=id,title,date,link,excerpt'

# Search for party support polls
curl 'https://maskina.is/wp-json/wp/v2/posts?search=fylgi&per_page=5&_fields=id,title,date,link,excerpt'

# Full article by ID
curl 'https://maskina.is/wp-json/wp/v2/posts/6412?_fields=id,title,date,link,content'
```

**Content format:** HTML in `content.rendered`. Requires HTML stripping. Poll data is embedded as prose text — "Samfylkingin stendur nú í um 25% fylgi".

**Search is a full-text index, not a fixed set of topics.** `/wp/v2/categories`
returns only `Fréttir` (339 posts) and `Uncategorized @is` (32) — there is no
real taxonomy to browse. `/wp/v2/tags` is empty. The `?search=` parameter is
the only practical way to find topical content, and it matches title + body
text freely — any word Maskína has ever polled about works, not just the
terms below.

**Known recurring, branded series** (repeated release after release — worth
building a systematic fetcher around, the way `fylgi` already is):

| Series | Search term(s) | Example title |
|---|---|---|
| Fylgi flokka (national party support) | `fylgi` | "Ný fylgismæling fyrir flokka á Alþingi" |
| Borgarviti (Reykjavík city politics) | `borgarviti` | "Borgarviti Maskínu: vaxandi óánægja með störf borgarstjóra" |
| Stofnanaviti (institutional trust) | `stofnanaviti` | "Stofnanaviti Maskínu er kominn út!" |
| ESB/aðild (EU membership) | `ESB`, `aðild`, `Evrópusambandið` | "53% hlynnt áframhaldandi aðildarviðræðum við ESB" (2026-01-12) |
| Traust til ráðherra/ríkisstjórnar (government/minister trust & approval) | `ríkisstjórnin`, `ráðherra` | "Ný traust mæling allra ráðherra" |
| Meðmæling Maskínu (annual "recommended companies") | `Meðmæling` | "12 fyrirtæki hljóta Meðmælingu Maskínu 2023" |
| Kryddsíld (year-end TV special poll) | `Kryddsíld` | "Kannanir úr Kryddsíld 2023" |
| Áramótaskaupið (satisfaction with the New Year's Eve comedy show) | `Áramótaskaupið` | "Gríðarleg ánægja með Áramótaskaupið" |
| Eurovision | `Eurovision` | "13% horfðu á Eurovision í ár" |

All nine confirmed live (2026-08-01) via `curl .../wp/v2/posts?search=<term>`
— each returns real, on-topic results, not just a single title-match fluke.

Beyond these, the archive is 371 posts deep (`x-wp-total` response header)
and covers plenty of one-off newsworthy topics that never repeat as a named
series — laxeldi (fish farming), veggjöld (road tolls), leiguþak (rent
caps), flóttafólk (refugees), Borgarlína, hvalveiðar (whaling), and more.
These are real and searchable, just not catalogued here individually — if
asked about a topic not in the table above, search for it directly rather
than assuming Maskína hasn't polled on it.

**Worked example — ESB** (2026-01-12,
`https://maskina.is/53-hlynnt-aframhaldandi-adildarvidraedum-vid-esb/`): a
poll originally commissioned for Sýn's Kryddsíld broadcast, published with
Sýn's permission. Prose carries one clean extractable figure — "um 53%
þeirra sem taka afstöðu í könnuninni eru hlynnt áframhaldandi
aðildarviðræðum sem eru um 2 prósentustigum meira en þegar spurningin var
borin upp ári áður" — followed by full methodology (Þjóðgátt panel,
n=1,765, weighted by Þjóðskrá, fielded 3.-15. October 2025). Same shape as
party-support articles: one prose sentence carries the headline number,
methodology follows in the paragraphs after.

The article also embeds a Tableau viz (`<div id="viz1768228030864">`)
distinct from the `FylgiFlokka-heimasa` workbook documented below —
**confirmed live 2026-08-01**: workbook `12_01_2026-ESB_virur`, view
`Frtt-ESB`, worksheet `helstu-ESB (2)`, readable with the exact VizQL flow
below (response ~100KB, 2 chunks). It carries the referendum question
("Ef haldin verður atkvæðagreiðsla um áframhaldandi aðildarviðræður við
ESB, myndir þú greiða atkvæði með eða á móti?") across two waves
(`2024-12-01`, `2025-12-01`): Með 50.9% → 53.0%, Á móti 49.1% → 47.0%,
plus weighted respondent counts — matching the article's "um 2
prósentustigum meira en ári áður" exactly. Two generalizable lessons:
the dated workbook name implies **one-off per-article workbooks** (future
ESB releases will likely ship a new workbook, not update this one), and
the workbook/view names are **discoverable from the article HTML** — grep
for the static-image URL, shaped
`public.tableau.com/static/images/12/12_01_2026-ESB_virur/Frtt-ESB/1.png`.

**Caveat: broad search terms return false positives — verify each hit,
don't trust title-matching alone.** Pulling the 3 most recent
`ESB`/`aðild`/`Evrópusambandið` hits live (2026-08-01) surfaced:

1. 2026-01-12 — the ESB-referendum poll above. Relevant.
2. **2022-04-04 — "Maskína gerir reglulega kannanir á Íslandi fyrir
   Framkvæmdastjórn Evrópusambandsins"** — matched only because
   "Evrópusambandið"/"Evrópusvæðinu" appear often in the text. It's an EU
   Commission survey of European SMEs' green-market practices (89% of EU
   SMEs, 37% of Icelandic ones, have taken sustainability steps) — **not**
   an Icelandic membership-opinion poll at all. A naive `--topic esb`
   fetcher would misparse this as a referendum-support article and either
   extract garbage or (more likely, since it has no hlynnt/andvígt framing)
   silently produce nothing — either way, don't assume a search hit is
   on-topic without reading it.
3. 2021-02-06 — inngöngu-stuðningur (membership support, not just
   "continue negotiations"): ~30% hlynnt, ~42% andvíg, plus a
   party-affiliation breakdown (Viðreisn 76.9% hlynnt, Miðflokkur 75.8%
   andvígt, etc.) — a genuinely different question from "aðildarviðræður"
   in the 2026 article. Worth keeping the two framings (support continuing
   *negotiations* vs. support *membership* itself) distinct in any
   extraction logic — they are not interchangeable numbers.

### 2. Tableau Public Dashboard (structured data)

**Dashboard:** `FylgiFlokka-heimasa` on `public.tableau.com`
**Sheet:** `Nýjasta mæling` (latest poll)

The dashboard provides structured party support data — percentages, month-over-month changes, and election comparison. Updated automatically when Maskína publishes a new poll.

#### VizQL Extraction Flow

Tableau Public uses an undocumented VizQL API. Two-step session flow:

**Step 1: startSession**

```
POST https://public.tableau.com/vizql/w/FylgiFlokka-heimasa/v/Njastamling/startSession/viewing
  ?:display_static_image=y&:bootstrapWhenNotified=true&:embed=true
  &:language=en-US&:embed=y&:showVizHome=n&:apiID=host0&:redirect=auth

Body: empty
Response: JSON with sessionid, stickySessionKey
Headers: x-session-id, global-session-header, set-cookie
```

Key response fields:
- `sessionid` — session identifier (also in `x-session-id` header)
- `stickySessionKey` — JSON string for server affinity
- `global-session-header` — Base64-encoded routing value (NOT the same as session ID)

**Step 2: bootstrapSession**

```
POST https://public.tableau.com/vizql/w/FylgiFlokka-heimasa/v/Njastamling
  /bootstrapSession/sessions/{sessionId}

Headers:
  Content-Type: application/x-www-form-urlencoded
  Cookie: {set-cookie values from step 1}
  global-session-header: {from step 1 response header}
  x-tsi-active-tab: N%C3%BDjasta%20m%C3%A6ling

Body (form-encoded):
  worksheetPortSize={"w":1100,"h":1800}
  dashboardPortSize={"w":1100,"h":1800}
  clientDimension={"w":1003,"h":1022}
  sheet_id=N%C3%BDjasta%20m%C3%A6ling
  stickySessionKey={from step 1 JSON}
  renderMapsClientSide=true
  isBrowserRendering=true
  browserRenderingThreshold=100
  formatDataValueLocally=false
  locale=en_US
  language=en

Response: ~650KB proprietary format (length-prefixed JSON chunks)
```

#### Parsing the Bootstrap Response

The response contains two length-prefixed JSON chunks:

```
590031;{...chunk 0 (layout/metadata)...}63012;{...chunk 1 (data)...}
```

Split on `/\d+;(?=\{)/` regex. Chunk 0 (~576KB) is layout metadata — skip. Chunk 1 (~61KB) contains `secondaryInfo` with actual poll data.

**Data dictionary path:**
```
secondaryInfo.presModelMap.dataDictionary.presModelHolder
  .genDataDictionaryPresModel.dataSegments["0"].dataColumns
```

Two arrays:
- `real` (529 values) — percentages as fractions (0–1), bar heights, and other numerics
- `cstring` (93 values) — party names, dates, labels

**Viz data path (column mapping):**
```
secondaryInfo.presModelMap.vizData.presModelHolder
  .genPresModelMapPresModel.presModelMap["bar kosningar"]
  .presModelHolder.genVizDataPresModel.paneColumnsData.paneColumnsList
```

The `bar kosningar` worksheet has three columns via `valueIndices`:

| Column | Type | Pattern | Example |
|--------|------|---------|---------|
| Dates | cstring indices | N× per party | `[11,12,14,16, 11,12,14,16, ...]` → "20260601", "20260501", "20260401", "20241130" |
| Party names | cstring indices | N× repeated | `[2,2,2,2, 3,3,3,3, ...]` → "Samfylkinguna", "Sjálfstæðisflokkinn", ... |
| Percentages | real indices | sequential N-tuples | `[36,37,38,39, 40,41,42,43, ...]` → latest, previous month, month before that, election |

**Period count is N=4 as of 2026-07-21 (latest, previous month, month before
that, last election "Kosningar '24"), NOT 3.** This was originally
documented as 3 — verified wrong live: naively striding by 3 through a
period-4 array desyncs party names from percentages roughly every other
party, producing duplicate party rows with garbage values (e.g. "Samfylkingin"
appearing twice at 25.2% and 20.8%) instead of one row per party. **Don't
hardcode the stride** — detect it live from the data instead (see
`_detect_stride()` below): find the smallest N where `party_indices` is
consistent in contiguous blocks of N (same party name repeats exactly N
times, then changes). Verified live: for the current 9-party × 4-period
= 36-length array, both N=3 and N=4 divide 36 evenly, so a "does the
count divide evenly" check alone is not sufficient — cross-checking
block-by-block consistency is what actually catches the 4-vs-3 case
correctly.

#### Party Names (accusative → nominative)

Tableau uses accusative case. Map to nominative for display:

| Tableau (þolfall) | Display (nefnifall) |
|-------------------|---------------------|
| Samfylkinguna | Samfylkingin |
| Miðflokkinn | Miðflokkurinn |
| Sjálfstæðisflokkinn | Sjálfstæðisflokkurinn |
| Viðreisn | Viðreisn |
| Framsóknarflokkinn | Framsóknarflokkurinn |
| Flokk fólksins | Flokkur fólksins |
| Pírata | Píratar |
| VG | Vinstrihreyfingin – grænt framboð |
| Sósíalistaflokkinn | Sósíalistaflokkurinn |

## Extraction with Python

```python
import httpx
import re
import json

TABLEAU_BASE = "https://public.tableau.com"
WORKBOOK = "FylgiFlokka-heimasa"
SHEET = "Njastamling"
ACTIVE_TAB = "N%C3%BDjasta%20m%C3%A6ling"

PARTY_NAMES = {
    "Samfylkinguna": "Samfylkingin",
    "Miðflokkinn": "Miðflokkurinn",
    "Sjálfstæðisflokkinn": "Sjálfstæðisflokkurinn",
    "Viðreisn": "Viðreisn",
    "Framsóknarflokkinn": "Framsóknarflokkurinn",
    "Flokk fólksins": "Flokkur fólksins",
    "Pírata": "Píratar",
    "VG": "Vinstrihreyfingin – grænt framboð",
    "Sósíalistaflokkinn": "Sósíalistaflokkurinn",
}


def fetch_polls():
    """Fetch structured poll data from Maskína's Tableau dashboard."""
    client = httpx.Client(follow_redirects=True)

    # Step 1: startSession
    start_url = (
        f"{TABLEAU_BASE}/vizql/w/{WORKBOOK}/v/{SHEET}/startSession/viewing"
        f"?:display_static_image=y&:bootstrapWhenNotified=true&:embed=true"
        f"&:language=en-US&:embed=y&:showVizHome=n&:apiID=host0&:redirect=auth"
    )
    r1 = client.post(start_url, headers={"Accept": "application/json"}, content=b"")
    r1.raise_for_status()
    body = r1.json()

    session_id = r1.headers.get("x-session-id", body.get("sessionid"))
    sticky_key = body.get("stickySessionKey", "")
    global_header = r1.headers.get("global-session-header", "")
    cookies = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)

    # Step 2: bootstrapSession
    boot_url = (
        f"{TABLEAU_BASE}/vizql/w/{WORKBOOK}/v/{SHEET}"
        f"/bootstrapSession/sessions/{session_id}"
    )
    form_data = {
        "worksheetPortSize": '{"w":1100,"h":1800}',
        "dashboardPortSize": '{"w":1100,"h":1800}',
        "clientDimension": '{"w":1003,"h":1022}',
        "sheet_id": ACTIVE_TAB,
        "stickySessionKey": sticky_key,
        "renderMapsClientSide": "true",
        "isBrowserRendering": "true",
        "browserRenderingThreshold": "100",
        "formatDataValueLocally": "false",
        "locale": "en_US",
        "language": "en",
    }
    r2 = client.post(
        boot_url,
        data=form_data,
        headers={
            "Cookie": cookies,
            "global-session-header": global_header,
            "x-tsi-active-tab": ACTIVE_TAB,
        },
    )
    r2.raise_for_status()

    # Parse response
    chunks = re.split(r"\d+;(?=\{)", r2.text)
    json_chunks = [c for c in chunks if c.startswith("{")]
    data = json.loads(json_chunks[1])

    seg = (
        data["secondaryInfo"]["presModelMap"]["dataDictionary"]["presModelHolder"]
        ["genDataDictionaryPresModel"]["dataSegments"]["0"]
    )
    reals, strings = [], []
    for col in seg["dataColumns"]:
        if col["dataType"] in ("real", "float"):
            reals = col["dataValues"]
        elif col["dataType"] in ("cstring", "string"):
            strings = col["dataValues"]

    # Find bar kosningar worksheet pane columns
    viz_map = (
        data["secondaryInfo"]["presModelMap"]["vizData"]["presModelHolder"]
        ["genPresModelMapPresModel"]["presModelMap"]
    )
    bar_ws = viz_map["bar kosningar"]["presModelHolder"]["genVizDataPresModel"]
    pane_cols = bar_ws["paneColumnsData"]["paneColumnsList"]

    party_indices, pct_indices = None, None
    for pane in pane_cols:
        for vpc in pane.get("vizPaneColumns", []):
            indices = vpc.get("valueIndices", [])
            if not indices:
                continue
            first = indices[0]
            if first < len(strings) and strings[first] in PARTY_NAMES:
                party_indices = indices
            elif first < len(reals) and 0 < reals[first] < 1:
                sample = [reals[i] for i in indices[:8]]
                if all(0 < v < 1 for v in sample):
                    pct_indices = indices

    # Period count varies (was 3, is 4 as of 2026-07-21) — detect it live
    # rather than hardcoding, by finding the block size where the party
    # name is constant within each block and changes between blocks.
    def _detect_stride(party_names_seq, candidates=(3, 4, 5, 6)):
        n = len(party_names_seq)
        for s in candidates:
            if n % s != 0:
                continue
            if all(
                len(set(party_names_seq[b * s: b * s + s])) == 1
                for b in range(n // s)
            ):
                return s
        raise RuntimeError(f"could not determine period stride from {n} values")

    party_names_seq = [strings[i] for i in party_indices]
    stride = _detect_stride(party_names_seq)

    # Extract one row per party, all `stride` periods (index 0 = latest,
    # index -1 = last election "Kosningar '24").
    results = []
    for i in range(0, len(party_indices), stride):
        party_acc = strings[party_indices[i]]
        pcts = [round(reals[pct_indices[i + k]] * 100, 1) for k in range(stride)]
        results.append({
            "party": PARTY_NAMES.get(party_acc, party_acc),
            "pcts": pcts,  # [latest, ...intermediate periods..., election]
            "latest_pct": pcts[0],
            "change_vs_prev_period": round(pcts[0] - pcts[1], 1),
            "change_vs_election": round(pcts[0] - pcts[-1], 1),
        })

    return sorted(results, key=lambda r: -r["latest_pct"])


if __name__ == "__main__":
    for row in fetch_polls():
        print(
            f"{row['party']:<35} {row['latest_pct']:>5.1f}%  "
            f"(mán: {row['change_vs_prev_period']:+.1f}, kosn: {row['change_vs_election']:+.1f})"
        )
```

## Sample Output

Verified live 2026-07-21 (periods: 1 June 2026 / 1 May 2026 / 1 April 2026 /
30 Nov 2024 election), sums to 99.9%:

```
Samfylkingin                         25.2%  (mán: -0.1, kosn: +4.4)
Sjálfstæðisflokkurinn                22.7%  (mán: +2.9, kosn: +3.3)
Miðflokkurinn                        14.2%  (mán: -0.8, kosn: +2.1)
Viðreisn                             12.4%  (mán: -2.0, kosn: -3.4)
Framsóknarflokkurinn                  8.5%  (mán: +0.7, kosn: +0.7)
Vinstrihreyfingin – grænt framboð     5.4%  (mán: +0.1, kosn: +3.1)
Flokkur fólksins                      4.1%  (mán: -0.6, kosn: -9.7)
Sósíalistaflokkurinn                  3.9%  (mán: +0.2, kosn: -0.1)
Píratar                               3.5%  (mán: -0.6, kosn: +0.5)
```

Flokkur fólksins' -9.7pt collapse since the 2024 election (13.8% → 4.1%)
matches the well-documented real-world drop in their support — a useful
sanity anchor when verifying future extractions.

Re-verified 2026-08-01 with the code block above run verbatim against the
following month's poll (published 2026-07-22, "Sjálfstæðisflokkurinn á
flugi"): Sjálfstæðisflokkurinn leads at 25.0%, all nine parties extract
once each, sum exactly 100.0% — stride detection handled the new
measurement without changes.

## Data Caveats

1. **VizQL API is undocumented** — Tableau could change the response format without notice. The WordPress API is a stable fallback for prose data.
2. **Accusative party names** — Tableau data uses accusative case (þolfall). Must map to nominative for display. If a new party appears, the mapping needs updating.
3. **Percentages as fractions** — Values come as 0–1, multiply by 100.
4. **`global-session-header` is NOT the session ID** — It is a Base64-encoded routing value. Using the session ID instead causes `410 Gone` on bootstrapSession.
5. **Cookie forwarding required** — The `set-cookie` headers from startSession must be passed as `Cookie` header to bootstrapSession.
6. **Response size** — bootstrapSession returns ~650KB. The data is in chunk 1 (~61KB); chunk 0 is layout metadata.
7. **Monthly updates** — Polls are published monthly. The dashboard updates automatically.
8. **Time-period count is not fixed at 3 — detect it live.** Verified live
   2026-07-21: the dashboard now carries 4 periods per party (latest,
   previous month, month before that, last election), not the 3 originally
   documented here. A naive fixed stride silently desyncs party names from
   percentages and produces duplicate party rows with garbage values instead
   of erroring — the sum-of-percentages sanity check below is what caught
   it, not an exception. Always detect the stride from the data (see
   `_detect_stride()`), and sanity-check the result sums to roughly 100%
   before trusting it.
9. **Sanity-check before trusting the output.** `sum(latest_pct for all
   parties)` should land in the 95-105% range. If it doesn't (or if any
   party name repeats), the stride detection or column-matching heuristic
   picked the wrong `valueIndices` array — don't report the numbers as-is.

## Alternative Sources

- **maskina.is articles** — WordPress REST API, prose format, full article text
- **RÚV/Vísir/Heimildin** — media coverage of polls from all pollsters; the `skodanakannanir` skill extracts numbers from those articles
- **Gallup (gallup.is)** — Competing polling firm; no direct integration, but its polls reach the `skodanakannanir` pipeline via news coverage
- **Prósent (prosent.is)** — Former MMR, another polling firm; same — reachable via `skodanakannanir` news coverage

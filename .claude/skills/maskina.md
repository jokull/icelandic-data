# Maskína — Public Opinion Polls

Public opinion polls and surveys from Iceland's leading polling company. Two data sources: WordPress articles (prose) and Tableau Public dashboard (structured).

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

**Key search terms:**
- `fylgi` — party support (monthly polls)
- `borgarviti` — Reykjavík politics
- `stofnanaviti` — institutional trust

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
| Dates | cstring indices | 3× per party | `[11,12,14, 11,12,14, ...]` → "20260301", "20260201", "20241130" |
| Party names | cstring indices | 3× repeated | `[2,2,2, 3,3,3, ...]` → "Samfylkinguna", "Miðflokkinn", ... |
| Percentages | real indices | sequential triplets | `[27,28,29, 30,31,32, ...]` → latest, previous month, election |

Each party has 3 data points: latest poll, previous month, last election ("Kosningar '24").

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
                sample = [reals[i] for i in indices[:6]]
                if all(0 < v < 1 for v in sample):
                    pct_indices = indices

    # Extract triplets: [latest, previous_month, election] per party
    results = []
    for i in range(0, min(len(party_indices), len(pct_indices)) - 2, 3):
        party_acc = strings[party_indices[i]]
        latest = reals[pct_indices[i]]
        previous = reals[pct_indices[i + 1]]
        election = reals[pct_indices[i + 2]]
        results.append({
            "party": PARTY_NAMES.get(party_acc, party_acc),
            "latest_pct": round(latest * 100, 1),
            "previous_pct": round(previous * 100, 1),
            "election_pct": round(election * 100, 1),
            "change": round((latest - previous) * 100, 1),
        })

    return sorted(results, key=lambda r: -r["latest_pct"])


if __name__ == "__main__":
    for row in fetch_polls():
        print(f"{row['party']:<35} {row['latest_pct']:>5.1f}%  ({row['change']:+.1f}%)")
```

## Sample Output

```
Samfylkingin                         25.5%  (-1.6%)
Miðflokkurinn                        18.4%  (-0.6%)
Sjálfstæðisflokkurinn                16.1%  (-0.1%)
Viðreisn                             14.0%  (+0.6%)
Framsóknarflokkurinn                  7.1%  (+0.2%)
Flokkur fólksins                      5.8%  (+1.1%)
Píratar                               5.0%  (-0.2%)
Vinstrihreyfingin – grænt framboð     4.4%  (+0.3%)
Sósíalistaflokkurinn                  3.5%  (+0.4%)
```

## Data Caveats

1. **VizQL API is undocumented** — Tableau could change the response format without notice. The WordPress API is a stable fallback for prose data.
2. **Accusative party names** — Tableau data uses accusative case (þolfall). Must map to nominative for display. If a new party appears, the mapping needs updating.
3. **Percentages as fractions** — Values come as 0–1, multiply by 100.
4. **`global-session-header` is NOT the session ID** — It is a Base64-encoded routing value. Using the session ID instead causes `410 Gone` on bootstrapSession.
5. **Cookie forwarding required** — The `set-cookie` headers from startSession must be passed as `Cookie` header to bootstrapSession.
6. **Response size** — bootstrapSession returns ~650KB. The data is in chunk 1 (~61KB); chunk 0 is layout metadata.
7. **Monthly updates** — Polls are published monthly. The dashboard updates automatically.
8. **Three time periods** — Each party has data for: latest poll, previous month, last election (Kosningar '24).

## Alternative Sources

- **maskina.is articles** — WordPress REST API, prose format, full article text
- **RÚV/Vísir** — Icelandic media sometimes republish poll highlights
- **Gallup (gallup.is)** — Competing polling firm, separate data source (not yet explored)
- **Prósent (prosent.is)** — Former MMR, another polling firm (not yet explored)

---
name: ruv
description: RÚV.is — search news articles and TV episodes (Kastljós, fréttir), download with handhönnuð VTT subtitles via yt-dlp, deep-link to timestamps.
---

# RÚV (Ríkisútvarpið — Icelandic State Broadcasting)

Search RÚV.is for news articles, TV episodes (Kastljós, fréttir, sérþættir) and download episodes with **handhönnuð VTT subtitles** (manually-authored captions — much higher quality than YouTube auto-captions).

## Data Scope

- **News archive** at `/frettir/` — categorized (innlent, erlent, ithrottir, menning), tagged by topic
- **TV catch-up** at `/sjonvarp/spila/<show>/<series-id>/<episode-id>` — long-running shows like Kastljós (35422) have hundreds of episodes
- **Subtitles**: most current-affairs and news content has handhönnuð VTT closed captions
- **Metadata via yt-dlp**: episode title, description, chapter timings, thumbnail, format list

## Discovery — Finding Content

### 1. Tag pages (most reliable browsing entry)

```
https://www.ruv.is/frettir/tag/<slug>
```

Tag slugs are URL-friendly (no Icelandic chars: `bensinstodvar`, not `bensínstöðvar`). Tag pages list news articles in reverse chronological order. Common tags appear at the bottom of any related article. Example:

```bash
# All bensínstöðva-related news
https://www.ruv.is/frettir/tag/bensinstodvar
```

Use Chrome DevTools MCP to scrape — `/frettir/tag/...` pages are server-rendered and links are immediately available in the DOM.

### 2. Site search via Google (the `/sok?searchterm=` endpoint returns 404)

`https://www.ruv.is/sok?searchterm=...` is **broken** as of April 2026 — returns the site's 404 page. Use WebSearch with `site:ruv.is` instead:

```
WebSearch: Kastljós bensínstöðvar Reykjavíkurborg site:ruv.is
```

### 3. Series listing scrape (for catch-up shows like Kastljós)

Hit the series root and scrape episode IDs directly from HTML:

```bash
curl -s "https://www.ruv.is/sjonvarp/spila/kastljos/35422" \
  -H "User-Agent: Mozilla/5.0" \
  | grep -oE "/sjonvarp/spila/kastljos/35422/[a-z0-9]+" \
  | sort -u
```

Returns ~224 unique episode slugs. Combine with the embedded JSON in the page (search for `"firstrun":"YYYY-MM"` and `"description":"..."`) to filter by date or content.

### 4. News articles often embed the related TV clip

When a news article reports on a Kastljós story, the Kastljós video is usually embedded in the article via a `<ruv-player>` element. Extract the episode ID from the HTML:

```js
// Run via Chrome DevTools MCP evaluate_script
() => {
  const html = document.documentElement.outerHTML;
  // Find embedded Kastljós/show ID
  return [...new Set((html.match(/kastljos\/35422\/[a-z0-9]+/g) || []))];
}
```

This is how to find a specific Kastljós episode when you know it exists but don't know the slug — find the news article first, then extract the embedded ID.

## Downloading Episodes — yt-dlp

The `yt-dlp` `ruv.is:spila` extractor handles RÚV TV episodes. Subtitle handling has a quirk: yt-dlp warns "Ignoring subtitle tracks found in the HLS manifest" but the closed-caption VTT is still fetched separately from the metadata API.

### Standard download (subs + info.json only, no video)

```bash
yt-dlp --skip-download --write-subs --sub-langs is --convert-subs vtt \
  --write-info-json \
  -o "%(upload_date)s_%(id)s_%(title)s.%(ext)s" \
  "https://www.ruv.is/sjonvarp/spila/kastljos/35422/<id>"
```

Outputs:
- `<date>_<id>_<title>.is.vtt` — handhönnuð subtitles
- `<date>_<id>_<title>.info.json` — metadata, formats, chapters
- `<date>_<id>_<title>.description` — show description
- `<date>_<id>_<title>.jpg` — thumbnail

### info.json fields worth knowing

```json
{
  "id": "ahpu0u",
  "title": "Samningar um bensínstöðvalóðir",
  "description": "Fjallað um samninga Reykjavíkurborgar...",
  "subtitles": {"is": [{"url": "https://muninn.nyr.ruv.is/files/subtitles/webvtt/closed/...mp4", "ext": "vtt"}]},
  "timestamp": 1715024400,        // unix epoch of first broadcast
  "upload_date": "20240506",
  "formats": [...],                // 480/720/1080 m3u8 manifests
  "chapters": [                    // when present, useful for navigation
    {"start_time": 0, "end_time": 67, "title": "Inngangur"},
    ...
  ]
}
```

### Chapter-aware episodes

Long episodes (Kastljós, sérþættir) sometimes have `chapters` populated. When present, use them to identify which segment is relevant before processing the full transcript:

```bash
jq '.chapters' <file>.info.json
```

## Working with VTT subtitles

VTT is hard to grep directly because timestamps are on separate lines from text. Convert to a one-cue-per-line `[start - end] text` format:

```python
import re
with open('episode.is.vtt') as f:
    vtt = f.read()

def to_sec(t):
    t = t.split('.')[0]
    parts = t.split(':')
    if len(parts) == 3: h,m,s = parts; return int(h)*3600+int(m)*60+int(s)
    if len(parts) == 2: m,s = parts; return int(m)*60+int(s)
    return 0

out = []
for block in re.split(r'\n\n+', vtt):
    lines = [l for l in block.strip().split('\n') if l]
    time_line = next((l for l in lines if '-->' in l), None)
    if not time_line: continue
    m = re.match(r'([\d:.]+)\s*-->\s*([\d:.]+)', time_line)
    if not m: continue
    start, end = to_sec(m.group(1)), to_sec(m.group(2))
    text = ' '.join(lines[lines.index(time_line)+1:]).strip()
    if text: out.append(f'[{start} - {end}] {text}')

print('\n'.join(out))
```

Now `grep` works naturally:

```bash
grep -i "byggingarréttur" episode_textun.txt
# [413 - 415] að olíufélögin myndu fá
# [415 - 419] svona gríðarlega mikinn byggingarrétt.
```

## Deep-linking — `?t=<seconds>`

The RÚV player supports timestamp deep-links — append `?t=<seconds>` to any episode URL:

```
https://www.ruv.is/sjonvarp/spila/kastljos/35422/ahpu0u?t=446
```

Quotes in research documents should always include the deep-link to the exact timestamp where the speaker said it.

## URL Patterns

| Path | Description |
|------|-------------|
| `/frettir/<category>/<YYYY-MM-DD>-<slug>-<id>` | News article |
| `/frettir/tag/<slug>` | Tag listing (chronological) |
| `/sjonvarp/spila/<show>/<series-id>/<episode-id>` | TV episode |
| `/sjonvarp/spila/<show>/<series-id>` | Series root (lists episodes) |
| `/sjonvarp/spila/<show>/<series-id>/<episode-id>?t=<seconds>` | Deep-link |
| `/utvarp/spila/<show>/<series-id>/<episode-id>` | Radio episode (same yt-dlp extractor) |

## Common Show IDs

| Show | Series ID |
|------|-----------|
| Kastljós | 35422 |
| Fréttir og íþróttir | 34285 |
| Áramótaskaup | varies by year (e.g. 37588 = 2024) |

## Caveats

- **`/sok` search returns 404** — use Google `site:ruv.is` via WebSearch instead
- **yt-dlp warns about HLS subtitle tracks** but downloads the proper closed-caption VTT from a separate URL — ignore the warning
- **Subtitles are Icelandic only (`is`)** — RÚV does not produce English subs except for `/english/` content
- **Episode IDs are short alphanumeric slugs** (`b12gpk`, `ahpu0u`, `b12gp3`) — there is no obvious mapping from date to slug; you have to scrape or extract from a related article
- **Some episode IDs returned by yt-dlp are clip IDs, not full-episode IDs** — when you see suspicious metadata (different episodes returning the same title), the slug is likely a chapter clip; find the actual full-episode slug via the related news article
- **Articles older than 6 months show "Þessi færsla er meira en 6 mánaða gömul"** banner — content is preserved; this is just a UX warning
- **VTT URLs in info.json point to muninn.nyr.ruv.is** with auth-free access — but the path includes `.mp4` even though the file is `.vtt` (cosmetic)

## Workflow — finding a specific episode

When you know an episode exists but not its slug:

1. **Search the RÚV news archive** for the topic (`WebSearch site:ruv.is <topic>`)
2. **Open the related news article** in Chrome DevTools MCP
3. **Extract the embedded video ID** from HTML: `kastljos/35422/<id>`
4. **Verify** by visiting the spila URL — check `<title>` and `<meta property="og:description">`
5. **Download** with the yt-dlp command above

## Example: bensínstöðva Kastljós (6 May 2024)

```bash
# Step 1: tag page lists related news
curl -s "https://www.ruv.is/frettir/tag/bensinstodvar" | head -200

# Step 2: open the article on the date of the Kastljós broadcast
# https://www.ruv.is/frettir/innlent/2024-05-06-umdeildir-samningar-um-bensinstodvalodir-412005

# Step 3: extract episode ID from article HTML
curl -s "https://www.ruv.is/frettir/innlent/2024-05-06-umdeildir-samningar-um-bensinstodvalodir-412005" \
  | grep -oE 'kastljos/35422/[a-z0-9]+' | sort -u
# kastljos/35422/ahpu0u

# Step 4: download
yt-dlp --skip-download --write-subs --sub-langs is --convert-subs vtt \
  --write-info-json \
  -o "%(upload_date)s_%(id)s_%(title)s.%(ext)s" \
  "https://www.ruv.is/sjonvarp/spila/kastljos/35422/ahpu0u"
```

## When to use this skill

Use when researching:
- Political statements (Kastljós interviews, Silfur, fréttatímar)
- Media framing of public-policy debates
- Verbatim quotes from on-air remarks (verbatim subs are crucial — paraphrases lose nuance)
- Cross-referencing news article claims with the original TV/radio clip they cite
- Building timelines that combine news articles + TV appearances + meeting minutes

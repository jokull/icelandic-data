# Tekjusagan — "The Income Story" (Prime Minister's Office)

Iceland's most widely-cited public income/inequality tool. Interactive dashboard showing changes in living standards for demographic groups over ~25 years (income, assets, gender, education). Owned by **Forsætisráðuneytið**; data source Hagstofa Íslands.

## Architecture

A thin Angular SPA (`tekjusagan.is`) that embeds a **token-authenticated** Power BI report. Unlike public `/view?r=...` embeds (e.g. `landlaeknir`), Tekjusagan's Power BI is private — clients fetch a short-lived embed token from Tekjusagan's own backend, then initialize the Power BI JS SDK with that token.

### API

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `GET https://tekjusagan.is/api/report/04ba62a1-8e38-44bd-a6b0-cb63d1fec3d8` | Issue a Power BI embed token for the report | `{"embedToken": "<1773-char JWT>", "id": "04ba62a1-..."}` |

| Field | Value |
|-------|-------|
| Power BI report ID | `04ba62a1-8e38-44bd-a6b0-cb63d1fec3d8` |
| Power BI group ID | `a08a802a-ca7b-4103-9052-18a85d009ec4` |
| Embed container | `https://app.powerbi.com/reportEmbed?reportId={id}&groupId={group}` |
| DAX endpoint (authenticated) | `https://wabi-europe-north-b-redirect.analysis.windows.net/explore/...` |

**Auth flow:** The token is issued without any input credentials (public anonymous endpoint). It scopes access to *this one report* for the current session. Tokens expire after ~1 hour — re-fetch if a long scrape session is needed.

## Dashboard routes (5)

The SPA exposes five Power BI report routes. Each triggers its own DAX queries — drive them via `page.goto()` rather than clicking menu items (menus only expand the nav tree).

| Slug | Route | Content |
|------|-------|---------|
| `radstofun` | `/skyrslur/radstofun` | Þróun ráðstöfunartekna — disposable income over time |
| `eignirskuldir` | `/skyrslur/eignirskuldir` | Eignir og skuldir — assets and debt |
| `kynmenntun` | `/skyrslur/kynmenntun` | Kyn og menntun — gender × education |
| `kynmenntun_details` | `/kynmenntun/details` | Kyn og menntun — detailed breakdown |
| `lifshlaupid` | `/lifshlaupid` | Lífshlaupið — life-course income trajectories |

## Extraction strategy

Because the Power BI is token-embedded, the simplest extraction is:

1. Drive the Angular SPA with Playwright (headless Chromium).
2. Let the SPA fetch its own token and initialize the Power BI embed.
3. Intercept `executeQueries`, `querydata`, and `modelsAndExploration` responses from the `wabi-europe-north-b-redirect.analysis.windows.net` host.
4. Navigate between sections (click nav buttons) to trigger section-specific queries.

Direct backend-only extraction (token + raw DAX) is possible but requires reverse-engineering Power BI's query protocol — **not worth it**; the Playwright path is reliable and matches the pattern already used in `landlaeknir`, `farsaeld_barna`, `maelabord_landbunadarins`.

## Script usage

```bash
# Fetch a fresh token and inspect its shape
uv run python scripts/tekjusagan.py token

# Scrape the dashboard (Playwright drive, saves raw responses)
uv run python scripts/tekjusagan.py fetch

# Run tests
uv run pytest tests/test_tekjusagan.py -v
```

## Data files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/tekjusagan/token.json` | JSON | Last embed-token response (for debugging) |
| `data/raw/tekjusagan/responses.json` | JSON | Captured Power BI responses (modelsAndExploration, executeQueries, etc.) |

## Alternative: go straight to Hagstofa

The underlying data comes from Hagstofa's TEK (tekjur) series — primarily:

| PX-Web table | Content |
|--------------|---------|
| TEK01001 | Medaltekjur einstaklinga eftir tekjuhóp |
| TEK01101 | Ráðstöfunartekjur (disposable income) |
| TEK01106 | Tekjur eftir kyni og aldri |
| TEK01401 | Eignastaða heimila |

If the goal is analysis (not replicating the dashboard UX), **prefer the Hagstofa route** — it's a clean JSON API via the existing `hagstofan` skill, and the raw data goes further back and is more granular than what Tekjusagan exposes.

## Caveats

1. **Token expiry (~1 hour)** — don't cache tokens in source control or long-running scripts. Always re-fetch.
2. **No public anonymous DAX query endpoint** — cannot bypass Power BI JS SDK cleanly.
3. **Attribution.** The tool credits Hagstofa as data source and Forsætisráðuneytið as publisher. Do the same.
4. **Icelandic characters in responses** — verified UTF-8 throughout the Power BI `modelsAndExploration` payload.
5. **SPA is Angular 19+ standalone build** — chunks and main.js hashes change on redeploy. Don't hard-code script names.
6. **Analytics tracking** — the site reports to Matomo and Google Analytics. If you care about that, add a block list in Playwright.

## Complementary sources

| Source | Overlap |
|--------|---------|
| [hagstofan](hagstofan.md) | TEK01xxx — canonical tidy data, use when possible |
| [laun](laun.md) | Take-home-salary calculator (prospective, not historical) |

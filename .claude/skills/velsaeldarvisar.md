# Velsældarvísar / Félagsvísar / Menningarvísar — Hagstofa indicator catalogs

Three curated Hagstofa Íslands indicator sites that wrap subsets of the PX-Web
data tree with narrative context. All three share the same host
(`visar.hagstofa.is`), same tech stack (Webflow), and the same per-indicator
structure — so one skill covers all three.

## What this skill gives you

A flat catalog mapping every published indicator to its backing PX-Web table(s)
plus a metadata PDF. Once you have the catalog, actual data values are fetched
via the existing [hagstofan](hagstofan.md) skill.

| Section | What it measures | Size (2026-04) |
|---------|------------------|----------------|
| `velsaeldarvisar` | OECD-style well-being dashboard: 3 dimensions × 13 categories | 39 indicators |
| `felagsvisar` | Social indicators — demographics, employment, health, housing, income, crime | 43 indicators |
| `menningarvisar` | Cultural participation / expenditure indicators | 6 indicators |

~77 unique PX-Web tables are referenced across the three sites. Not every
indicator links to a PX table — several reference Eurostat-only series
(`ec.europa.eu/eurostat/...`) or only a `hagstofa.is/talnaefni/...` topic page.
Those rows still carry the metadata PDF.

## Architecture

Each page is a static Webflow export. The crawler is a plain `httpx.get` +
regex-based slicing — no Playwright needed.

Per page, indicator content sits in a `<div data-w-tab="NAME" class="tab-pane-... w-tab-pane">`.
Parent categories use bare `class="w-tab-pane"` (no `tab-pane-` prefix).

### Source pages

| Section | Slug | URL |
|---------|------|-----|
| velsaeldarvisar | felagslegir | `/velsaeldarvisar/felagslegir-maelikvardar` |
| velsaeldarvisar | efnahagslegir | `/velsaeldarvisar/efnahagslegir-maelikvardar` |
| velsaeldarvisar | umhverfislegir | `/velsaeldarvisar/umhverfislegir-maelikvardar` |
| felagsvisar | felagsvisar | `/felagsvisar` |
| menningarvisar | menningarvisar | `/menningarvisar` |

All relative to `https://visar.hagstofa.is`.

## Catalog schema

`data/processed/velsaeldarvisar_catalog.csv`:

| Column | Description |
|--------|-------------|
| `section` | One of `velsaeldarvisar`, `felagsvisar`, `menningarvisar` |
| `page` | Sub-page slug (e.g. `efnahagslegir`) |
| `category` | Parent Webflow tab (e.g. `Hagkerfið`, `Atvinna`). Empty for top-level. |
| `indicator` | Indicator name as shown on site |
| `unit` | Unit string ("Hlutfall í %", "Árafjöldi", etc.) — present when page declares it |
| `short_description` | First line after "Stutt lýsing" |
| `px_tables` | `\|`-separated PX table codes (e.g. `THJ09000\|THJ09003`) |
| `px_urls` | `\|`-separated full PX-Web URLs |
| `metadata_pdf` | First metadata PDF URL (`hagstofas3bucket.hagstofa.is/...`) |

## Usage

```bash
# Crawl the 5 Webflow pages, write the catalog
uv run python scripts/velsaeldarvisar.py fetch

# Print catalog (optionally filtered by section)
uv run python scripts/velsaeldarvisar.py list
uv run python scripts/velsaeldarvisar.py list --section velsaeldarvisar

# Get the deduplicated list of PX table codes (useful for bulk-fetch scripts)
uv run python scripts/velsaeldarvisar.py pxtables
```

### Combining with the hagstofan skill

Once you've selected an indicator from the catalog, go through `hagstofan` to
pull the actual values:

```bash
# Example: indicator "Skuldastaða heimila" (velsaeldarvisar/Hagkerfið)
# → table THJ09000
# Inspect the table's metadata to find dimension codes
uv run python scripts/hagstofan.py meta THJ09000
# Then query using the codes you need
```

## Caveats

1. **Not all indicators have a PX table code.** Some (e.g. `Lífslíkur`, most of
   `Öryggi`) only link to the `hagstofa.is/talnaefni/...` topic page or to
   Eurostat. The catalog keeps those rows; `px_tables` is just empty.
2. **Typos in source.** The live Webflow content has a handful of genuine typos
   in table codes (`LFI03305` should be `LIF03305`). The crawler preserves the
   source verbatim — **always sanity-check a code before fetching** (try the
   URL; if 404, replace `LFI` with `LIF` and retry).
3. **Öryggi (safety) duplication.** On `felagslegir-maelikvardar`, the "Öryggi"
   parent incorrectly reuses the sub-indicator names from "Menntun"
   (`Menntunarstig`, `Brotthvarf...`). This is a content bug on the live site,
   not a parser bug.
4. **Webflow CDN class names rotate occasionally.** The regex keys on the
   `w-tab-pane` / `tab-pane-*` pattern, which has been stable on Webflow for
   years. If Hagstofa redesigns the site, the parser will need updating.
5. **Nested sub-tabs.** Some categories (e.g. `Heilsa` on the social page) use
   nested tab structures where the parent is itself a `tab-pane-*`. The parser
   treats all `tab-pane-*` divs as indicators; when a parent gets re-classified
   as an indicator, it appears as a row with an empty `category` column.
6. **No cache-busting.** Webflow edits are reflected immediately; re-run `fetch`
   if the site is known to have updated.
7. **Encoding.** Webflow pages are served as UTF-8. Indicator titles, category
   labels, and PX-table descriptions all contain Icelandic chars (þ, ð, æ, ö);
   the parser writes CSV with `utf_8` and reads source HTML with `httpx` defaults.

## Related

- Upstream: [hagstofan](hagstofan.md) — fetch actual values from a PX table code.
- Complementary dashboards on `stjornarradid.is/gogn/maelabord/` index:
  - [tekjusagan](tekjusagan.md) — income-distribution history (overlaps on
    `Lágtekjuhlutfall`, `Ójöfnuður tekna`).
  - [farsaeld_barna](farsaeld_barna.md) — child wellbeing.
- SDG indicators (`heimsmarkmidin.hagstofa.is`) are a **separate** site on a
  different host with different tech — out of scope for this skill.

## Attribution

"Byggir á upplýsingum frá Hagstofu Íslands."

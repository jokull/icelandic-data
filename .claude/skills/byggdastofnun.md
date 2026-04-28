# Byggdastofnun — Regional-development dashboards

Iceland's Regional Development Institute (**Byggdastofnun**, from
`byggdastofnun.is`) publishes 11 Tableau-Public dashboards covering rural and
regional statistics: population, income, property taxes, energy, state
employment, grants, and the municipal-history map.

All 11 dashboards live on `byggdastofnun.is/is/utgefid-efni/maelabord/<slug>`
and embed a viz from `public.tableau.com/views/<workbook>/<view>`.

## Scope & dashboards

| Slug | Title | Workbook / view |
|------|-------|-----------------|
| `breytingar-a-ibuafjolda-sundurlidun` | Breytingar á íbúafjölda — sundurliðun | `ibuafj-breyting` / `sveitarfelog` |
| `fasteignagjold` | Fasteignagjöld viðmiðunareignar | `fasteignagjold` / `fasteignagjold` |
| `ibuafjoldi-1-januar` | Íbúafjöldi sveitarfélaga og byggðakjarna | `ibuafj_sveitarf-byggdakj` / `ibuafjoldi` |
| `ibuakonnun` | Íbúakönnun landshlutanna | `ibuakonnun` / `spurningar` |
| `mannfjoldaspa` | Mannfjöldaspá 2023–2074 | `mannfjoldaspa` / `mannspa` |
| `orkukostnadur` | Orkukostnaður heimila | `Orkukostnaurheimila` / `orkukostnadur` |
| `rikisfang` | Ríkisfang íbúa | `rikisfang` / `rikisfang` |
| `rikisstorf` | Stöðugildi á vegum ríkisins | `rikisstorf` / `stodugildi` |
| `styrkir` | Styrkir og framlög | `styrkir` / `styrkir` |
| `sveitarfelagaskipan` | Sveitarfélagaskipan frá 1875 | `sveitarfelagamork` / `Tmabil` |
| `tekjur` | Tekjur einstaklinga eftir svæðum | `tekjur` / `tekjur` |

All 11 Tableau workbooks are **public** (no auth, no token). They are cached
content on Tableau Public's CDN and refresh when Byggdastofnun republishes.

## Architecture

`byggdastofnun.is` is built on **Moya CMS** (Icelandic vendor). The index
page `.../maelabord` lists each dashboard with an anchor; each sub-page
embeds the Tableau view inside an `<iframe>`. This skill parses that pattern
— one iframe per sub-page — to keep a catalog fresh.

For **structured data extraction**, Tableau Public does not expose a clean
CSV path (`?:format=csv` returns HTML). The [maskina](maskina.md) skill
documents the two-step VizQL `startSession` → `bootstrapSession` flow used
to scrape structured poll data from a Tableau Public workbook; the same
pattern applies here if/when a downstream task needs tabular access.

## Usage

```bash
# Refresh the catalog from the live site (11 HTTP requests, ~5s)
uv run python scripts/byggdastofnun.py fetch

# Print the cached catalog
uv run python scripts/byggdastofnun.py list

# Get the Tableau embed URL for one slug — handy for shell pipelines
uv run python scripts/byggdastofnun.py url tekjur
# → https://public.tableau.com/views/tekjur/tekjur?:showVizHome=no&:embed=true
```

## Catalog schema

`data/processed/byggdastofnun_catalog.csv`:

| Column | Description |
|--------|-------------|
| `slug` | Sub-page slug on byggdastofnun.is |
| `title` | H1 title from the live page |
| `workbook` | Tableau Public workbook identifier (from `/views/<wb>/`) |
| `view` | Tableau view within the workbook (specific dashboard tab) |
| `embed_url` | Full Tableau Public URL for direct embedding |
| `page_url` | Source page on byggdastofnun.is |

## Caveats

1. **Catalog-only skill.** Tabular data extraction would require implementing
   the VizQL flow (see `maskina.md`). Current scope is the URL/metadata
   catalog so a downstream consumer can pick the right workbook/view
   quickly.
2. **Workbook name stability.** Byggdastofnun has re-uploaded several
   workbooks in the past — the naming is inconsistent (note the mix of
   English + Icelandic + typo'd "Orkukostnaurheimila" without the ð). If a
   dashboard disappears, re-run `fetch` to pick up the new identifier.
3. **Data sourcing.** Most series are derived from Hagstofa PX-Web tables
   ([hagstofan](hagstofan.md) skill) plus additional Byggdastofnun surveys
   (`ibuakonnun`). For straight demographic and income work, prefer
   fetching raw PX-Web; Byggdastofnun's value is the regional cuts and the
   composite indices.
4. **Mælaborð vs. publications.** Byggdastofnun also publishes annual
   reports ("Byggðaþróunarskýrsla") and sector studies at
   `byggdastofnun.is/is/utgefid-efni/skyrslur-og-rannsoknir`. Those are
   PDFs and are out of scope for this skill; handle via a dedicated PDF
   extractor if needed.
5. **Moya redirects.** The landing page doesn't auto-redirect malformed
   slugs; `url <slug>` raises if the slug isn't in the catalog rather
   than guessing.
6. **`display_count` parameter.** Some pages use `display_count=n` (hidden
   visit counter), others `display_count=y`. The scraper preserves whatever
   the source iframe declares, so the embed URL is a faithful mirror.
7. **Encoding.** byggdastofnun.is HTML and the Tableau workbook identifiers
   are served as UTF-8. Note the typo'd workbook `Orkukostnaurheimila`
   (without ð) — preserve it verbatim in catalog output.

## Attribution

"Byggir á upplýsingum frá Byggðastofnun."

## Related

- [hagstofan](hagstofan.md) — raw PX-Web for most underlying series
- [maskina](maskina.md) — documents the VizQL flow for extracting
  structured data from a Tableau Public workbook
- [reykjavik](reykjavik.md) — Reykjavík-municipality-specific data, complements
  the national/regional view

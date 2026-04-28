# CO2 — Aðgerðaáætlun í loftslagsmálum

Iceland's climate action plan tracker, covering every numbered action through
2035. Published at `co2.is` by **Umhverfis-, orku- og loftslagsráðuneytið**.

Each action has a title, goal, start/end years, status, and responsible
ministry. The tracker is the primary public accountability mechanism for
Iceland's nationally determined contribution (NDC) under the Paris Agreement.

## Taxonomy

Four-level hierarchy; actions are coded `<Kerfi>.<Málaflokkur>.<Viðfangsefni>.<Index>`.

| Level | Example | Meaning |
|-------|---------|---------|
| Kerfi (system) | `S` | One of four accounting systems |
| Málaflokkur | `S.5` | Sub-sector |
| Viðfangsefni (focus area) | `S.5.C` | Specific target |
| Aðgerð (action) | `S.5.C.1` | Individual measure (catalog row) |

### Kerfi

| Code | Kerfi | Meaning | Actions (2026-04) |
|------|-------|---------|:----:|
| `S` | Samfélagslosun | Community emissions (covered by Iceland's EU effort-sharing commitment) | 61 |
| `V` | Viðskiptakerfi | ETS — EU emissions-trading system sectors (stationary industry, aviation, maritime) | 9 |
| `L` | Landnotkun | Land use, land-use change and forestry (LULUCF) | 12 |
| `Þ` | Þverlægar aðgerðir | Cross-cutting actions (financial incentives, social) | 24 |
| **Total** | | | **106** |

## Architecture

Webflow-hosted SPA-ish site (static HTML output from Webflow CMS) at
`co2.is`. The action catalog lives on `/allar-adgerdir`, which references 32
**viðfangsefni** pages (`/adgerdir/<slug>`). Each viðfangsefni page contains
1–11 individual action accordion blocks. The scraper discovers all 32 slugs
from `/allar-adgerdir` then crawls each.

No API, no JSON endpoint — all data is rendered server-side into the HTML.
Regex parsing of the Webflow accordion blocks is the reliable path.

### Accordion block structure

Each action block has:

```html
<div id="s5c1" class="adgerd-accordion">
  ...
  <h3 class="title-6">Full orkuskipti ríkisflota og samgönguþjónustu fyrir 2030</h3>
  <p class="text-small">Ríkið sé fyrirmynd í innkaupum hreinorkuökutækja ...</p>
  <div class="label-big strong">Markmið aðgerðar</div>
  <div class="text-small">Full orkuskipti ríkisflota ...</div>
  <div class="label-big strong">Upphaf /&nbsp;Endir</div>
  <div class="adgerd-meta-dates">
    <div class="text-small">2023</div><div>–</div><div class="text-small">2030</div>
  </div>
  <div class="label-big strong">Staða aðgerðar</div>
  <div status-color="Í framkvæmd" class="status-color"></div>
  <div class="label-big strong">Ábyrgðaraðili</div>
  <div class="text-small">Fjármála- og efnahagsráðuneyti</div>
</div>
```

The status-color attribute on the status marker is the authoritative status
string (avoids ambiguity when the label is truncated for layout).

## Status vocabulary

| Status | Meaning | Color on the site |
|--------|---------|-------------------|
| `Lokið` | Completed | Green |
| `Í framkvæmd` | In progress | Yellow |
| `Samþykkt` | Approved (not yet started) | Dark grey |
| `Fyrirhugað` | Planned | Light grey |
| `Á hugmyndastigi` | Conceptual | Very light grey |

## Usage

```bash
# Crawl all 32 viðfangsefni pages, write data/processed/co2_actions.csv
uv run python scripts/co2.py fetch

# List the catalog, optionally filtered
uv run python scripts/co2.py list
uv run python scripts/co2.py list --kerfi S
uv run python scripts/co2.py list --status "Í framkvæmd"
uv run python scripts/co2.py list --ministry Fjármála
```

## Catalog schema

`data/processed/co2_actions.csv`:

| Column | Description |
|--------|-------------|
| `code` | Canonical action code (e.g. `S.5.C.1`) |
| `id` | Lowercase id from the HTML anchor (e.g. `s5c1`) |
| `kerfi` | `S`, `V`, `L`, or `Þ` |
| `malaflokkur_nr` | Second-level digit (1–7) |
| `vidfangsefni_letter` | Third-level letter (A–D) |
| `action_idx` | Action number within its viðfangsefni |
| `vidfangsefni_slug` | URL slug of the parent viðfangsefni |
| `title` | Short title |
| `description` | First-paragraph summary |
| `markmid` | Goal (Markmið aðgerðar) |
| `upphaf` | Start year (integer) |
| `endir` | End year (integer, blank if open-ended) |
| `stada` | Status enum (`Lokið`, `Í framkvæmd`, `Samþykkt`, `Fyrirhugað`, `Á hugmyndastigi`) |
| `abyrgdaradili` | Responsible ministry / ministries (pipe-separated) |
| `vidfangsefni_url` | Source URL |

## Snapshot (2026-04-22 pull)

- **106 actions** across 4 kerfi × ~30 viðfangsefni
- Status: 70 Í framkvæmd · 28 Fyrirhugað · 8 Samþykkt (no Lokið or Á hugmyndastigi yet)
- 75 actions have a fixed end year; 31 are open-ended (mostly ongoing regulatory measures)
- 10 ministries participate; most frequent are Umhverfis-, orku- og loftslagsráðuneytið and the sector ministries (Matvæla, Innviða, Fjármála)

## Caveats

1. **Count vs. hero.** The site's hero text aggregates to 110 measures
   (58 + 14 + 30 + 8). The scraper finds 106; the 4-item gap may reflect
   rounding in the hero or a handful of measures that only appear under
   the `/adlogun/` (adaptation plan) tree, which this skill does not yet
   scrape.
2. **Open-ended dates.** Many regulatory actions have a start year but no
   end year (they're "permanent"). `endir` is blank for those — don't
   default-fill with `upphaf`.
3. **Icelandic special char in system code.** Þ (þ/Thorn) is not ASCII; the
   URL slug prefix is `th2b-…`. The scraper maps `th` → `Þ` for the `kerfi`
   column so catalogs are human-readable; `id` keeps the ASCII prefix.
4. **Non-breaking space in the "Upphaf / Endir" label.** Webflow renders it
   as `Upphaf /&nbsp;Endir` (U+00A0 between `/` and `Endir`). The scraper
   normalises whitespace before matching.
5. **Webflow class rotation.** The site uses hand-authored class names
   (`adgerd-accordion`, `label-big strong`, `adgerd-meta-dates`) that
   appear stable, but CSS refactors could break the scraper. Re-save one
   viðfangsefni HTML and diff against the cached `data/raw/co2/*.html` to
   verify before blaming the regex.
6. **No CO₂-ígildi target per action.** The site shows aggregate CO₂
   targets at the viðfangsefni and málaflokkur level but does not publish a
   per-action emissions-reduction figure. The scraper does not attempt to
   attribute aggregate targets to individual actions.
7. **Aðlögunaráætlun (adaptation plan) not included.** The site has a
   separate toggle for adaptation actions at `/adlogun`. Those are a
   distinct catalog (fewer actions, different vocabulary) and are out of
   scope for this skill.
8. **Encoding.** Webflow serves the page as UTF-8. Action titles,
   ministry names, and the kerfi letter Þ (Þvert á kerfi) all need
   UTF-8 handling. Watch the non-breaking space (U+00A0) in some Webflow
   labels — the parser normalises these to regular spaces.

## Attribution

"Byggir á upplýsingum frá Umhverfis-, orku- og loftslagsráðuneytinu
(co2.is)."

## Related

- [loftgaedi](loftgaedi.md) — real-time air-quality monitoring data
- [rikisreikningur](rikisreikningur.md) — state accounts (some CO₂ actions
  have funded line items visible there)
- [heimsmarkmid](heimsmarkmid.md) — SDG 13 (Climate action) reporting

---
name: althingi
description: Alþingi XML — MPs, per-MP vote records, bills, committees, speeches, ministers, lobbying submissions. Use for Icelandic parliamentary analysis.
---

# Alþingi — Parliament XML

Open XML feeds from the Alþingi database: every MP since 1875, per-MP roll-call
votes, the parliamentary matter catalogue, committee membership, speeches, ministerial
appointments and consultation submissions.

## API

**Base URL:** `https://www.althingi.is/altext/xml/`

No authentication, no rate limit published. Plain `GET`, no query language —
each endpoint is a fixed path with query-string filters. Responses are
`text/xml; charset=utf-8`.

**Send a User-Agent.** The site returns **403 Forbidden** to httpx's default
UA. Any identifying string is accepted — sending none, or a default library
UA, is the failure mode. `curl` works out of the box, so this bites only when
moving from a shell probe to code.

Responses are served through Cloudflare and come back `cf-cache-status: HIT`
with an `age` of up to ~10 minutes. Combined with the daily refresh, treat
anything you read as up to a day old.

Data refreshes **once per day** ("Gögnin uppfærast að öllu jöfnu einu sinni á
sólarhring"), so there is nothing to gain from polling faster.

### There is no schema

Alþingi states outright: *"Ekki er til xml-skema fyrir gögnin, nema
Alþingistíðindi"* and *"Framsetningin á gögnunum geta tekið breytingum án
fyrirvara"* — no XSD except for Alþingistíðindi, and the shape may change
without notice.

In practice there is **no schema at all**. The two XSDs the index page links
for the record proper —
`http://skema.althingi.is/skema/althingi_{gerdabok,raedur}.xsd` — are dead:
`skema.althingi.is` returns no DNS answer (checked 2026-08-15, while
`www.althingi.is` resolves normally). Do not plan on validating against them.

So everything here is shape-by-observation. That is what the health probe
guards, and it is why it asserts Icelandic element *names* rather than values.

### Element names are Icelandic

Tags are `<þingmaður>`, `<atkvæðagreiðsla>`, `<þingflokkur>`, `<kjördæmi>` —
non-ASCII, which is legal XML but unusual. Both `lxml` and stdlib
`xml.etree.ElementTree` handle it; this repo uses the stdlib parser, so no new
dependency. Parse from **bytes** (`resp.content`), never `resp.text` — the
documents carry their own encoding declaration and a `str` input trips
`ValueError: Unicode strings with encoding declaration are not supported`.

## Common parameters

| Parameter | Applies to | Example | Notes |
|-----------|-----------|---------|-------|
| `lthing` | most list endpoints | `?lthing=156` | Parliament (löggjafarþing) number |
| `dagur` | rosters, votes, speeches | `?dagur=14.2.2013` or `?dagur=20190916` | **Two date formats in the wild** — `D.M.YYYY` for rosters, `YYYYMMDD` for votes/speeches |
| `dagar` | votes, speeches | `?dagar=100` | Trailing window in days |
| `malnr` | matter detail | `?lthing=156&malnr=1` | Only unique *within* a `málsflokkur` — see caveat 3 |
| `nr` | per-person detail | `?nr=1547` | Person id, stable across parliaments |
| `nnefnd` | committee members | `?lthing=156&nnefnd=201` | Committee id |

## Endpoints

### Core — what `scripts/althingi.py` fetches

| Endpoint | Root element | Purpose |
|----------|-------------|---------|
| `loggjafarthing/` | `löggjafarþing` | Every parliament 1..N with dates and per-þing index links |
| `loggjafarthing/yfirstandandi/` | `löggjafarþing` | The **current** parliament — resolve this at runtime, never hardcode |
| `thingmenn/?lthing=N` | `þingmannalisti` | Everyone who sat during þing N (members *and* substitutes) |
| `thingmenn/thingmadur/thingseta/?nr=N` | `þingmaður` | **Party + constituency + seat, per parliament.** The only route to party affiliation |
| `atkvaedagreidslur/?lthing=N` | `atkvæðagreiðslur` | All vote events of a parliament |
| `atkvaedagreidslur/atkvaedagreidsla/?numer=N` | `atkvæðagreiðsla` | One vote **with the per-MP ballot** (`<atkvæðaskrá>`) |
| `thingmalalisti/?lthing=N` | `málaskrá` | All matters (bills, resolutions, questions) of a parliament |
| `nefndir/nefndarmenn/?lthing=N` | `nefndarmenn` | Committee membership with start/end dates |
| `thingfundir/?lthing=N` | `þingfundir` | Sittings: number, title, start/end timestamps |
| `raedulisti/?lthing=N` | `ræðulisti` | Speech **metadata** — speaker, times, links. Not the text |

### Also available — documented, not yet scripted

| Endpoint | Root element | What it holds |
|----------|-------------|---------------|
| `thingmenn/thingmadur/?nr=N` | `þingmaður` | One MP: name, birth date, links |
| `thingmalalisti/thingmal/?lthing=N&malnr=M` | `þingmál` | A-matter detail: sponsors, stages, documents |
| `thingmalalisti/bmal/?lthing=N&malnr=M` | `bmál` | **B-matter detail — a separate route**, see caveat 3 |
| `nefndir/?lthing=N` | `nefndir` | Committees active in þing N |
| `thingmenn/thingmadur/hagsmunir/?nr=N` | `þingmaður` | **Declarations of interest** — an MP's directorships, shareholdings, paid roles. Joins to `skatturinn` ownership data by company name |
| `erindi/?lthing=N` | `erindaskrá` | **Consultation submissions** to committees — the lobbying trail. ~800 KB per parliament |
| `erindi/sendandi/?lthing=N` | `sendendur` | Who submitted, aggregated by sender |
| `thingmenn/thingmadur/lifshlaup/?nr=N` | `þingmaður` | Biography — education, career, offices |
| `thingmenn/thingmadur/nefndaseta/?nr=N` | `þingmaður` | One MP's committee history |
| `thingskjol/?lthing=N` | `þingskjöl` | Parliamentary documents index |
| `thingskjol/thingskjal/?lthing=N&skjalnr=N` | `þingskjal` | One document |
| `samantektir/?lthing=N` | `samantektir` | Plain-language summaries of matters |
| `samantektir/samantekt/?lthing=N&malnr=M` | `samantekt` | One summary (often empty — 87 bytes) |
| `efnisflokkar/` | `efnisflokkar` | Subject taxonomy, two levels (`yfirflokkur` → `efnisflokkur`) |
| `efnisflokkar/efnisflokkur/?lthing=N&efnisflokkur=K` | `efnisflokkar` | Matters in a subject category |
| `nefndarfundir/` | `nefndarfundir` | Committee meetings. **Trailing slash required** — without it, 301 to HTML |
| `dagskra/thingfundur/?lthing=N&fundur=M` | `dagskráþingfundar` | Order paper for one sitting |
| `forsetar/?lthing=N` | `forsetalisti` | Speaker and deputy speakers |
| `framsogumenn/?lthing=N` | `framsögumannaskrá` | Committee rapporteurs per matter |
| `thingflokkar/?lthing=N` | `þingflokkar` | Parliamentary groups with abbreviations |
| `thingflokksformenn/?lthing=N` | `þingflokksformenn` | Group chairs |
| `kjordaemi/?lthing=N` | `kjördæmin` | Constituencies |
| `radherrar/?dagur=D.M.YYYY` | `ráðherralisti` | Ministers on a given date |
| `radherrar/radherraseta/?nr=N` | `einstaklingur` | One person's ministerial terms |
| `radherraembaetti/` | `ráðherrar` | Ministerial offices over time |
| `saetaskipan/?timi=ISO` | `sætaskipun` | Chamber seating. Seat numbers only — **no party** |

## Historical depth

Coverage starts at a different parliament per dataset — this is the first thing
to check before any long-run series:

| Dataset | From | Roughly |
|---------|------|---------|
| MPs (`þingmenn`) | þing 1 | 1875 |
| Matters, documents, speeches | þing 20 | 1907 |
| Committees | þing 74 | 1954 |
| Submissions (`erindi`) | þing 111 | 1988 |

## Request examples

```bash
# Which parliament is sitting right now
curl -s "https://www.althingi.is/altext/xml/loggjafarthing/yfirstandandi/"

# Everyone who sat in þing 156
curl -s "https://www.althingi.is/altext/xml/thingmenn/?lthing=156"

# One MP's party and constituency, per parliament
curl -s "https://www.althingi.is/altext/xml/thingmenn/thingmadur/thingseta/?nr=1261"

# A single vote, with every MP's ballot
curl -s "https://www.althingi.is/altext/xml/atkvaedagreidslur/atkvaedagreidsla/?numer=67566"

# Votes on one matter / on one day / in the last 100 days
curl -s "https://www.althingi.is/altext/xml/atkvaedagreidslur/?lthing=150&malnr=1"
curl -s "https://www.althingi.is/altext/xml/atkvaedagreidslur/?dagur=20190916"
curl -s "https://www.althingi.is/altext/xml/atkvaedagreidslur/?dagar=100"
```

## Schema

### Vote event — `atkvaedagreidslur/?lthing=N`

```xml
<atkvæðagreiðsla málsnúmer='104' þingnúmer='156' málsflokkur='A' atkvæðagreiðslunúmer='67566'>
  <mál málsnúmer='104' þingnúmer='156' málsflokkur='A'>
    <málsheiti>ráðstöfun útvarpsgjalds</málsheiti>
  </mál>
  <tími>2025-02-18T14:09:52</tími>
  <fundur>7</fundur>
  <tegund tegund='as'>Of skammt var liðið frá útbýtingu --- Afbrigði</tegund>
  <samantekt>
    <aðferð>atkvæðagreiðslukerfi</aðferð>
    <já><fjöldi>44</fjöldi></já>
    <nei><fjöldi>0</fjöldi></nei>
    <greiðirekkiatkvæði><fjöldi>0</fjöldi></greiðirekkiatkvæði>
    <afgreiðsla>samþykkt</afgreiðsla>
  </samantekt>
  <nánar><xml>.../atkvaedagreidsla/?numer=67566</xml></nánar>
</atkvæðagreiðsla>
```

| Field | XML | Type | Example |
|-------|-----|------|---------|
| `atkvgr_nr` | `@atkvæðagreiðslunúmer` | INT | `67566` — globally unique, the join key |
| `thing` | `@þingnúmer` | INT | `156` |
| `malsnumer` | `@málsnúmer` | INT | `104` |
| `malsflokkur` | `@málsflokkur` | STR | `A` or `B` |
| `malsheiti` | `mál/málsheiti` | STR | `ráðstöfun útvarpsgjalds` |
| `timi` | `tími` | DATETIME | `2025-02-18T14:09:52` (ISO) |
| `fundur` | `fundur` | INT | `7` — sitting number |
| `tegund` | `tegund` | STR | What was voted on |
| `tegund_kodi` | `tegund/@tegund` | STR | `as`, `v2`, `n2` … |
| `adferd` | `samantekt/aðferð` | STR | See vote-method table |
| `ja` / `nei` / `greidir_ekki` | `samantekt/{já,nei,greiðirekkiatkvæði}/fjöldi` | INT | Null when no ballot was taken |
| `afgreidsla` | `samantekt/afgreiðsla` | STR | `samþykkt` / `fellt` |

### Per-MP ballot — `atkvaedagreidsla/?numer=N`

```xml
<atkvæðaskrá>
  <þingmaður id='1004'><nafn>Arna Lára Jónsdóttir</nafn><atkvæði>já</atkvæði></þingmaður>
  <þingmaður id='1510'><nafn>Alma D. Möller</nafn><atkvæði>fjarverandi</atkvæði></þingmaður>
</atkvæðaskrá>
```

`<atkvæði>` values, with Alþingi's own gloss from the XML comments:

| Value | n (þing 156) | Meaning |
|-------|---|---------|
| `já` | 12,258 | Yes |
| `nei` | 1,676 | No |
| `greiðir ekki atkvæði` | 1,324 | Abstain — *present in the chamber and pressed the abstain button* |
| `fjarverandi` | 3,160 | Absent, not notified — pressed no button |
| `boðaði fjarvist` | 482 | Absent, notified — illness, or on parliamentary business |

**The abstain string is spaced here and unspaced in the summary block.** The
`<samantekt>`/`<niðurstaða>` count element is `<greiðirekkiatkvæði>` (one
word); the `<atkvæði>` value inside `<atkvæðaskrá>` is `greiðir ekki atkvæði`
(three words). Matching the element spelling against ballot values silently
returns nothing — and because plenty of votes are unanimous, a spot check can
easily miss it.

The distinction between the last two matters: `boðaði fjarvist` is an excused
absence, `fjarverandi` is not. Collapsing them loses the signal.

### Vote methods — `aðferð`

Observed across þing 156 (598 vote events):

| `aðferð` | Count | Carries `<atkvæðaskrá>`? |
|----------|-------|--------------------------|
| `atkvæðagreiðslukerfi` | 299 | **yes** — electronic voting |
| `yfirlýsing forseta/mál gengur` | 297 | no — Speaker's declaration, no ballot |
| `nafnakall` | 1 | **yes** — roll call |
| `handaupprétting` | 1 | no — show of hands, count only |

### MP roster — `thingmenn/?lthing=N`

| Field | XML | Example |
|-------|-----|---------|
| `thingmadur_id` | `@id` | `1547` — stable person id |
| `nafn` | `nafn` | `Aðalsteinn Leifsson` |
| `faedingardagur` | `fæðingardagur` | `1967-06-17` (ISO) |
| `skammstofun` | `skammstöfun` | `ALeif` |

### Parliamentary service — `thingseta/?nr=N`

This is where party and constituency live. One `<þingseta>` per parliament, and
**more than one if the MP changed party or seat mid-þing**.

| Field | XML | Example |
|-------|-----|---------|
| `thing` | `þing` | `156` |
| `tegund` | `tegund` | `þingmaður`, `varamaður` (substitute), or `með varamann` (seat-holder currently *replaced by* a substitute) — three values, not two |
| `thingflokkur` / `thingflokkur_id` | `þingflokkur` + `@id` | `Viðreisn` / `45` |
| `kjordaemi` / `kjordaemi_id` | `kjördæmi` (CDATA) + `@id` | `Reykjavíkurkjördæmi suður` / `45` |
| `kjordaemanumer` | `kjördæmanúmer` | `7` |
| `thingsalssaeti` | `þingsalssæti` | `2` |
| `inn` / `ut` | `tímabil/{inn,út}` | `21.05.2025` / `27.05.2025` — **`D.M.YYYY`, not ISO** |

`<út>` is absent for a currently-serving MP.

### Matters — `thingmalalisti/?lthing=N`

| Field | XML | Example |
|-------|-----|---------|
| `malsnumer` | `@málsnúmer` | `1` |
| `thing` | `@þingnúmer` | `156` |
| `malsflokkur` | `@málsflokkur` | `A` or `B` |
| `malsheiti` | `málsheiti` | `breytt skipan ráðuneyta í Stjórnarráði Íslands` |
| `malstegund` | `málstegund/heiti` | `Tillaga til þingsályktunar` |
| `malstegund_kodi` | `málstegund/@málstegund` | `a`, `l`, `m`, `þi` … |

Matter types on þing 156 — 716 matters, 504 A and 212 B:

| `málstegund` | n |
|---|---|
| Fyrirspurn (written question) | 266 |
| óundirbúinn fyrirspurnatími (oral questions) | 202 |
| Frumvarp til laga (bill) | 131 |
| Tillaga til þingsályktunar (resolution) | 71 |
| Skýrsla (report) | 23 |
| sérstök umræða (special debate) | 10 |
| Beiðni um skýrslu (report request) | 9 |
| Álit (opinion) | 4 |

### Committee membership — `nefndir/nefndarmenn/?lthing=N`

| Field | XML | Type | Example |
|-------|-----|------|---------|
| `thing` | request `lthing` | INT | `156` |
| `nefnd_id` | `nefnd/@id` | INT | `201` |
| `nefnd` | `nefnd/heiti` | STR | `allsherjar- og menntamálanefnd` |
| `thingmadur_id` | `nefnd/nefndarmaður/@id` | INT | `1547` |
| `nafn` | `nefnd/nefndarmaður/nafn` | STR | `Aðalsteinn Leifsson` |
| `stada` | `nefnd/nefndarmaður/staða` | STR | `varamaður` |
| `hofst` / `lauk` | `nefndasetahófst` / `nefndasetulauk` | DATE | `2025-02-04` / `2025-09-08`; `lauk` is null while active |

### Sittings — `thingfundir/?lthing=N`

| Field | XML | Type | Example |
|-------|-----|------|---------|
| `thing` | request `lthing` | INT | `156` |
| `fundur` | `þingfundur/@númer` | INT | `1` |
| `fundarheiti` | `fundarheiti` | STR | Sitting title |
| `dagur` | `hefst/dagur`, falling back to `fundursettur` | DATE | `2025-02-04` |
| `dagur_aaetlad` | derived | BOOL | Whether `dagur` came from the schedule |
| `hefst_texti` | `hefst/texti` | STR | Free-text scheduling note, nullable |
| `hefst` | `hefst/dagurtími` | DATETIME | Scheduled start, nullable |
| `fundursettur` / `fundarslit` | `fundursettur` / `fuslit` | DATETIME | Actual opening and close |

### Speeches — `raedulisti/?lthing=N`

| Field | XML | Type | Example |
|-------|-----|------|---------|
| `thing` | request `lthing` | INT | `156` |
| `thingmadur_id` | `ræðumaður/@id` | INT | Speaker/person id when present |
| `nafn` | `ræðumaður/nafn` | STR | Speaker name |
| `dagur` | `dagur` | DATE | `2025-02-18` |
| `fundur` | `fundur` | INT | Sitting number |
| `fundarheiti` | `fundarheiti` | STR | Sitting title |
| `hofst` / `lauk` | `ræðahófst` / `ræðulauk` | DATETIME | Speech start and end |
| `tegund` | `tegundræðu` | STR | Speech type |
| `umraeda` | `umræða` | STR | Debate stage |
| `malsflokkur` / `malsnumer` | `mál/{málsflokkur,málsnúmer}` | STR / INT | Matter key, nullable |
| `malsheiti` | `mál/málsheiti` | STR | Matter title, nullable |

## Script usage

```bash
uv run python scripts/althingi.py list                        # every parliament, current one flagged
uv run python scripts/althingi.py list --datasets             # what fetch can pull

uv run python scripts/althingi.py fetch --dataset members     # roster + party + constituency
uv run python scripts/althingi.py fetch --dataset votes       # vote events + per-MP ballots
uv run python scripts/althingi.py fetch --dataset bills
uv run python scripts/althingi.py fetch --dataset committees
uv run python scripts/althingi.py fetch --dataset sittings
uv run python scripts/althingi.py fetch --dataset speeches
uv run python scripts/althingi.py fetch --dataset all

uv run python scripts/althingi.py fetch --dataset votes --thing 155      # a past parliament
uv run python scripts/althingi.py fetch --dataset members --thing 150-156
uv run python scripts/althingi.py fetch --dataset votes --force          # ignore the raw cache
```

`--thing` defaults to the parliament returned by `loggjafarthing/yfirstandandi/`.

## Data files

| Path | Format | Description |
|------|--------|-------------|
| `data/raw/althingi/*.xml` | XML | Every response, cached verbatim. Closed þing are cached permanently; current feeds refresh after 24h. `--force` always re-downloads |
| `data/processed/althingi_members.parquet` | Parquet | One row per (MP, parliament, party spell) |
| `data/processed/althingi_votes.parquet` | Parquet | One row per vote event |
| `data/processed/althingi_ballots.parquet` | Parquet | One row per (vote, MP) — the per-MP records |
| `data/processed/althingi_bills.parquet` | Parquet | One row per matter in the catalogue; no stage/document detail |
| `data/processed/althingi_committees.parquet` | Parquet | One row per (committee, MP, spell) |
| `data/processed/althingi_sittings.parquet` | Parquet | One row per sitting. `dagur` is the scheduled date, or the opening date when none was scheduled; `dagur_aaetlad` flags which |
| `data/processed/althingi_speeches.parquet` | Parquet | One row per speech (metadata only) |

Column names are ASCII snake_case transliterations of the Icelandic tags — the
mapping is in the schema tables above. Values keep their Icelandic characters.

## Caveats

1. **Half the "votes" are not votes.** `atkvaedagreidslur/?lthing=N` returned
   598 entries for þing 156, but only 301 involved a ballot; the other 297 are
   `yfirlýsing forseta/mál gengur` — the Speaker declaring a matter advanced
   unopposed. Counting rows to get "votes this session" roughly doubles the
   real figure. Filter on `afgreidsla` / vote counts being present.

2. **Do not filter per-MP ballots on `aðferð == 'atkvæðagreiðslukerfi'`.**
   `nafnakall` (roll call) also carries a full `<atkvæðaskrá>` — 63 MPs on the
   one þing-156 instance. It is rare, and it is exactly the kind of vote that
   gets called on contentious matters, so dropping it biases the sample in the
   worst possible direction. `handaupprétting` (show of hands) carries counts
   but no per-MP record. The script keys off the presence of `<atkvæðaskrá>`,
   not the method name.

3. **`málsnúmer` is only unique within a `málsflokkur`.** A- and B-matters
   number independently *and* have separate detail routes. On þing 156,
   `thingmal/?malnr=11` is "sameiningar háskóla" (a question) while
   `bmal/?malnr=11` is "forseti Íslands setur þingið" (the state opening) —
   different matters, same number. The natural key is
   `(þingnúmer, málsflokkur, málsnúmer)`. Joining on málsnúmer alone silently
   mixes them.

4. **Dates come in three formats, and Alþingi intends to change them.**
   `D.M.YYYY` (`01.07.1875`) in `löggjafarþing`, `þingseta`, `þingfundir`;
   ISO `YYYY-MM-DD` in `fæðingardagur`; ISO datetime in votes and speeches.
   The site's own To-Do list has *"Breyta dagsetningum í ISO"* pending, so the
   first form will migrate at some point without notice. Normalise on read and
   accept both.

5. **The sitting parliament has no `<þinglok>`.** Every closed þing carries an
   end date; the current one carries only `<þingsetning>`. A parser that
   assumes the element is present breaks on the current þing specifically — the
   one you most want to query.

6. **Never hardcode the parliament number.** Resolve it from
   `loggjafarthing/yfirstandandi/`. Þing 157 opened 2025-09-09.

7. **Sentinel rows with empty names.** `kjördæmi id=1` and `þingflokkur id=26`
   have empty CDATA `<heiti>` and `-` as their abbreviation. They are
   "unknown/none" placeholders, not real constituencies or parties. Filter them
   out or they show up as a blank category in every grouping.

8. **`<niðurstaða>` nests inside `<niðurstaða>`.** In the vote-detail document
   the outer element is the result block and the inner one is the verdict
   string (`samþykkt`). An unanchored XPath grabs whichever comes first — use
   `niðurstaða/niðurstaða` for the verdict. Note the list endpoint calls the
   same block `<samantekt>` and the verdict `<afgreiðsla>`: **the two endpoints
   use different tag names for the same thing.**

9. **The MP roster includes substitutes.** `thingmenn/?lthing=156` returns 105
   people for a 63-seat parliament, because every varamaður who sat for even a
   week is in there. `þingseta/tegund` separates `þingmaður` from `varamaður`,
   and `tímabil` gives the spell. Head-counting the roster is not a seat count.

10. **One MP can have several `<þingseta>` entries for one þing** — and the
    usual reason is not a party switch. Þing 156 yields 313 spells for 105
    people, because the record is re-cut every time a substitute steps in:
    Alma D. Möller alone has six consecutive spells, same party, same
    constituency, differing only in `tímabil`. `members` is therefore one row
    per *spell*, not per MP. Deduplicate on `(thingmadur_id, thing)` before
    joining to votes, or every ballot gets multiplied.

    Spells can also start **before the parliament convenes** — þing 156 opened
    2025-02-04, but spells run from 2024-11-30, the day after the election that
    produced it.

11. **Speeches are metadata only.** `raedulisti` gives speaker, sitting, times
    and links to the text and audio — not the text itself. It is also large:
    12.4 MB and 13,623 speeches for þing 156 alone.

    Speakers are not all MPs. `<ræðumaður>` carries role elements such as
    `<forsetiÍslands>`; the first speech of þing 156 is by Halla Tómasdóttir,
    President of Iceland, opening the session. An inner join from `speeches` to
    `members` on `thingmadur_id` therefore drops real speeches — use a left
    join and expect unmatched rows.

12. **`nefndarfundir` needs a trailing slash.** Without it the server 301s to
    an HTML page, so a naive fetch parses HTML as XML and fails obscurely.

    Relatedly, **not every sitting has a scheduled date.** A sitting called
    relative to another one carries only free text —
    `<hefst><texti>að loknum 37. fundi</texti></hefst>`, "once the 37th
    concludes" — with no `<dagur>` and no `<dagurtími>`. That is 8 of 92
    sittings on þing 156. The script falls back to the date part of
    `<fundursettur>` (when the sitting was actually opened) and sets
    `dagur_aaetlad = false` on those rows, so `dagur` is never null and the
    provenance stays visible.

13. **Parse bytes, not text.** The documents carry an encoding declaration;
    handing a decoded `str` to an XML parser raises `ValueError`. Use
    `resp.content`.

14. **No schema, changes without notice.** Alþingi says so explicitly, and the
    XSDs they link are on a host that no longer resolves. This is what
    `tests/health/test_althingi.py` watches — it asserts the Icelandic element
    names still exist, since a silent retag is the likeliest break.

15. **`greiðir ekki atkvæði` (value) vs `greiðirekkiatkvæði` (element).** The
    same concept is spelled two ways in the same document family — see the
    ballot-value table above. This one is easy to get wrong and hard to notice.

## Sources

- Endpoint index: <https://www.althingi.is/altext/xml/>
- Alþingistíðindi XSDs: <http://skema.althingi.is/skema/> — **linked from the
  index but dead**; the host does not resolve

# Vernd — Lykilupplýsingar um umsækjendur um alþjóðlega vernd

Key monthly/weekly stats on **international-protection (asylum) applicants** to
Iceland. Power BI dashboard published by **Ríkislögreglustjóri** (National
Commissioner of Police) via the Ministry of Justice's mælaborð index at
`stjornarradid.is/gogn/maelabord/`.

## Architecture

Public `/view?r=<base64>` Power BI embed — same scrape pattern as
[landlaeknir](landlaeknir.md). No auth, no token, no Playwright-drivable SPA:
just point headless Chromium at the embed URL and intercept the Power BI data
responses.

| Field | Value |
|-------|-------|
| Tenant | `509484a8-c0ff-4960-b5da-3bdb75e98460` |
| Report key | `a2a07353-0f55-40d2-b761-bab29aba67bc` |
| Cluster | `9` |
| Embed URL | `https://app.powerbi.com/view?r=<base64(json{k:report,t:tenant,c:9})>` |

The cluster number matters — it's embedded in the base64 payload on the
official government page. Most `landlaeknir` dashboards use cluster 8; this
one uses 9.

## Usage

```bash
# Print embed URL + IDs for verification
uv run python scripts/vernd.py info

# Scrape Power BI query responses (~15s headless browser run)
uv run python scripts/vernd.py fetch
```

Output: `data/raw/vernd/responses.json` — list of raw Power BI semantic-query
results, one per visual on the page.

## What the dashboard publishes

Each Power BI "visual" corresponds to one query response. Captured shape
(2026-04):

| Visual | Row count | Dimensions | Measure |
|--------|-----------|------------|---------|
| Yearly total | 5 | `Dags stofnað hælisleit.Ár` | count |
| Monthly trend | 57 | `Ár × Mánuður_stutt` | count |
| Weekly trend by gender | 142 | `Ár × Vikunúmer × Kyn2` | count |
| Age × gender | 9 | `Aldursflokkun2 × Kyn2` | count |
| By nationality | 38 | `Hælisleitandi.Ríkisfang` | count |
| Nationality × year | 104 | `Ríkisfang × Ár` | count |
| KPI cards | 1 each | — | totals/averages |

### Data-model entities

| Entity (`Source.Entity`) | Fields used | Meaning |
|-------------------------|-------------|---------|
| `Nafnaskrá` | `Kyn2`, `Aldursflokkun2` | Applicant demographics |
| `Hælisleitandi` | `Ríkisfang` | Citizenship / country of origin |
| `Dags stofnað hælisleit` | `Ár`, `Mánuður_stutt`, `Vikunúmer` | Application-opened date |
| `Dags beiðni` | `Ár` | Request date |

### Values (sanity check, 2026-04-21 snapshot)

Applications-opened per year (from the yearly-trend visual):

| Year | Count |
|------|-------|
| 2022 | 4,493 |
| 2023 | 4,159 |
| 2024 | 1,932 |
| 2025 | 1,712 |
| 2026 (YTD) | 421 |

The 2022 peak + subsequent decline is consistent with the surge during
the Ukraine-war influx and the 2023 policy tightening.

## Decoding the Power BI "DSR" payload

Each captured response contains `result.data.dsr.DS[*].PH[*].DM0` — a list of
row objects with a `C` array holding values in the order declared by
`descriptor.Select`. The first row carries a schema (`S`) that names each
slot; subsequent rows omit the schema and reuse the column order. Numeric
values are plain ints; categorical values are strings.

Minimal parser sketch:

```python
import json
payload = json.loads(open("data/raw/vernd/responses.json").read_text())
for visual in payload:
    dm0 = visual["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"]
    # dm0[0]["S"] holds the column schema; each dm0[i]["C"] is a row tuple
    for row in dm0:
        print(row.get("C"))
```

Heads-up: sparse rows use the `R` key to indicate "repeat previous column
value" and the `C` key may be absent when all columns repeat. Full decoding
requires handling those two shorthands.

## Caveats

1. **No public CSV / API** — the underlying immigration-case database is not
   published. The dashboard is the only open view.
2. **Definitions.** "Umsókn um alþjóðlega vernd" includes all applicants
   (Convention refugees, subsidiary protection, humanitarian). The dashboard
   does not break down by outcome.
3. **Reporting lag.** Latest weeks often under-count — applications logged
   late in the case-management system filter through over the following
   weeks. Don't compare the current-week count to prior weeks directly.
4. **Ukraine influx.** The 2022 and early 2023 numbers are dominated by
   Ukrainian arrivals under the temporary-protection regime. Trend
   comparisons pre-/post-2022 should flag this.
5. **Cluster number stays at 9.** Don't assume cluster 8 like most
   `/view?r=` embeds — it's in the payload for a reason.
6. **Encoding.** Power BI responses are UTF-8 throughout (nationality names,
   month-name strings like "Mánuður_stutt"). Write JSON with `ensure_ascii=False`
   and read with `encoding="utf-8"`.

## Attribution

"Byggir á upplýsingum frá Ríkislögreglustjóra."

## Related

- [landlaeknir](landlaeknir.md) — same `/view?r=` scrape pattern, 33 health dashboards
- [vinnumalastofnun](vinnumalastofnun.md) — related on labour-market side (work permits)
- Policy tracker at `stjornarradid.is/verkefni/utlendingar/upplysingavefur-verndarmala`
  (`upplysingavefur_verndar` in the mælaborð backlog) — narrative companion,
  no additional raw data.

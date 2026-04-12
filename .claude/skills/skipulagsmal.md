# Skipulagsmál — Planitor (Planning & Building Permits)

Planitor aggregates municipal planning and building committee data across Iceland. Tracks cases, permits, meeting minutes, entities (applicants), and addresses.

**Base URL:** `https://www.planitor.io`
**Auth:** Public read API (some endpoints require auth, noted below)
**Rate limits:** Unknown — be polite
**OpenAPI spec:** `https://www.planitor.io/openapi.json`
**Enums:** `https://www.planitor.io/api/_enums`

## Coverage

96,835 minutes, 42,052 cases, 3,648 meetings across 3 municipalities:
- Reykjavík: ~70k minutes
- Hafnarfjörður: ~20k minutes
- Árborg: ~6k minutes

All minutes have Icelandic lemmas for text classification. No structured permit data in the public API — classification must be done via lemma/text matching on the `inquiry` field.

## API Endpoints

### Municipalities

```bash
curl -s 'https://www.planitor.io/api/municipalities' | jq .
```

3 active municipalities: Reykjavík (0), Hafnarfjörður (1400), Árborg (8200). Seltjarnarnesbær and Mosfellsbær listed but have no council data.

### Search Minutes

Full-text search across 96,835 minutes. **Supports Icelandic via URL encoding.**

```bash
curl -s 'https://www.planitor.io/api/minutes/search?q=hótel&limit=50' | jq .
```

**Params:** `q`, `after` (date), `before` (date), `council_type`, `entity` (kennitala), `limit` (max 200), `offset`

**Key search counts:**
| Term | Count |
|------|-------|
| `deiliskipulag` | 14,129 |
| `íbúðir` | 13,396 |
| `fjölbýlishús` | 6,222 |
| `bílastæði` | 3,463 |
| `hótel` | 2,207 |
| `leiguíbúðir` | 89 |

**Working filters:** `after`/`before` (dates), `council_type`, `entity` (kennitala), full pagination
**Broken:** `municipality_id` (ignored)

### Nearby Cases

```bash
curl -s 'https://www.planitor.io/api/cases/nearby?lat=64.1466&lon=-21.9426&radius_m=500&limit=100' | jq .
```

**Params:** `lat`, `lon`, `radius_m` (max 5000), `updated_after`, `limit` (max 500), `offset`

Central Reykjavík (3km): 14,705 cases. Full pagination works.

Returns: `id`, `serial`, `address`, `lat`, `lon`, `status`, `updated`, `last_sale_price`, `last_sale_date`

### Case Detail

```bash
curl -s 'https://www.planitor.io/api/cases/SERIAL' | jq .
```

Returns full case with `minutes[]` (meeting history) and `transactions[]` (HMS property transactions with kaupverd, tegund, flatarmal, fjoldi_herbergja, byggingarar).

### Entity Search

```bash
curl -s 'https://www.planitor.io/api/entities/search?q=Reitir' | jq .
```

Key entities found:
- **Reitir fasteignafélag hf.** (7112080700) — 282 minutes
- **Bjarg íbúðafélag** (4909160670) — 117 minutes
- **Gamma ehf.** (6507050410) — 38 minutes

### Entity Minutes

```bash
curl -s 'https://www.planitor.io/api/entities/KENNITALA/minutes?limit=200' | jq .
```

Full permit history for any entity. Supports `council_type`, `after`, `before`, pagination.

### Enums

```bash
curl -s 'https://www.planitor.io/api/_enums' | jq .
```

#### Council Types
`byggingarfulltrui`, `skipulagsfulltrui`, `skipulagsrad`, `borgarrad`, `borgarstjorn`

#### Building Types
`einbylishus`, `fjolbylishus`, `gestahus`, `geymsluskur`, `hotel`, `idnadarhus`, `parhus`, `radhus`, `sumarhus`, `verslun_skrifstofur`

#### Permit Types
`nybygging` (new build), `vidbygging` (extension), `breyting_inni` (interior change), `breyting_uti` (exterior change), `nidurrif` (demolition)

#### Case Statuses
`samthykkt` (approved/green), `jakvaett` (positive/green), `frestad` (postponed/yellow), `grenndarkynning` (yellow), `visad-til-*` (referred/yellow), `neikvaett` (negative/red), `neitad` (rejected/red), `visad-fra` (dismissed/red), `engar-athugasemdir` (no comments/blue)

### Permits Endpoint (broken)

`/api/permits` returns 500. Schema exists (`units`, `areaAdded`, `buildingType`, `permitType`, `approved`, `address`, `postcode`) but the underlying data is sparse (43 manually classified records).

## Classification via Lemmas

No structured building type or permit type in the public API. Classify by filtering the `inquiry` text or searching for Icelandic lemma keywords:

**Building type keywords** (search via `q` parameter):
- `hótel` → hotel
- `fjölbýlishús` / `tvíbýlishús` → apartment building
- `einbýlishús` → single-family house
- `raðhús` → row house / `parhús` → semi-detached
- `gestahús` → guesthouse / `sumarhús` → summer house
- `verslunarhúsnæði` / `skrifstofuhúsnæði` / `veitingastaður` → commercial

**Permit type keywords:**
- `byggja` → new construction
- `viðbygging` → extension
- `innra skipulagi` / `baðherbergi` → interior modification
- `gluggi` / `svalir` / `svalalokun` → exterior modification
- `rífa` → demolition

**Area extraction:** Inquiry text often contains `N ferm.` (square meters). Parse with regex.

**Unit counts:** Inquiry text often contains `N íbúðum` or `N íbúðir`. Parse with regex.

### Example: classify and count via API pagination

```python
# Paginate through all "fjölbýlishús" minutes in 2024
import httpx, re
url = "https://www.planitor.io/api/minutes/search"
params = {"q": "fjölbýlishús", "after": "2024-01-01", "before": "2025-01-01", "limit": 200, "offset": 0}
total_units = 0
while True:
    r = httpx.get(url, params=params).json()
    for item in r["items"]:
        m = re.search(r"(\d+) íbúð", item.get("inquiry") or "")
        if m:
            total_units += int(m.group(1))
    if len(r["items"]) < 200:
        break
    params["offset"] += 200
```

## Caveats

- Only 3 municipalities indexed — **Kópavogur, Mosfellsbær, Garðabær are NOT covered**
- `municipality_id` filter on minutes search does not work (ignored)
- Status filter on nearby endpoint returns 422
- Hotel minutes ≠ hotel permits — many are modifications to existing hotels, not new builds
- Address deduplication: same address appears in multiple minutes as a case progresses through councils
- Planning throughput dropped ~50% from 2019 (5,695 minutes) to 2022 (2,692) — reflects both COVID and restructuring of the planning division

# Skipulagsmál — Planitor (Planning & Building Permits)

Planitor aggregates municipal planning and building committee data across Iceland. Tracks cases, permits, meeting minutes, entities (applicants), and addresses.

**Base URL:** `https://www.planitor.io`
**Auth:** Public read API, no key needed
**Rate limits:** Unknown — be polite

## Municipalities

```bash
curl -s 'https://www.planitor.io/api/municipalities' | jq .
```

Returns array of `{id, name, councils: [{id, name, council_type}]}`.
Current municipalities: Reykjavík (0), Hafnarfjörður (1400), Árborg (8200), Seltjarnarnesbær (1100), Mosfellsbær (1604).

## Nearby Cases

Find planning cases near a GPS coordinate:

```bash
curl -s 'https://www.planitor.io/api/cases/nearby?lat=64.1466&lon=-21.9426&radius_m=500&limit=100' | jq .
```

**Params:** `lat`, `lon`, `radius_m` (max 5000), `status`, `council_type`, `updated_after`, `limit` (max 500), `offset`

**Response:** `{items, total, limit, offset}` — each item has:
- `id`, `serial` (e.g. "USK25120153"), `address`, `lat`, `lon`
- `status`: `[code, display_text, color]` — e.g. `["samthykkt", "Samþykkt", "green"]`
- `updated`, `council_type`

## Search Minutes

Full-text search across meeting minutes:

```bash
curl -s 'https://www.planitor.io/api/minutes/search?q=Laugavegur&limit=50' | jq .
```

**Params:** `q`, `lat`, `lon`, `radius_m`, `entity`, `address`, `council_type`, `status`, `after`, `before`, `limit` (max 200), `offset`

**Response:** paginated `{items, total, limit, offset}` — each item:
- `id`, `headline`, `inquiry` (application details), `remarks` (decision)
- `status`: `[code, display_text, color]`
- `meeting_date`, `council`, `case_serial`, `case_address`

## Entity Search

Find companies/individuals involved in planning cases:

```bash
curl -s 'https://www.planitor.io/api/entities/search?q=Byko' | jq .
```

**Params:** `q` (min 1 char), `limit` (max 100)
**Response:** array of `{kennitala, name}`

## Entity Minutes

Get all minutes mentioning an entity:

```bash
curl -s 'https://www.planitor.io/api/entities/KENNITALA/minutes?limit=50' | jq .
```

**Params:** `council_type`, `after`, `before`, `limit` (max 200), `offset`

## Case Detail

```bash
curl -s 'https://www.planitor.io/api/cases/SERIAL' | jq .
```

Returns `ExploreCaseDetail` with full case history.

## Address Lookup

Find cases near a specific address (by hnitnum from Staðfangaskrá):

```bash
curl -s 'https://www.planitor.io/api/addresses/HNITNUM/addresses?radius=300&days=365' | jq .
```

## Web Search

The `/leit` endpoint provides broader search (returns HTML page, not JSON):

```
https://www.planitor.io/leit?q=Laugavegur+22&page=1
```

## Enums

### Council Types
| Code | Name |
|------|------|
| `byggingarfulltrui` | Byggingarfulltrúi |
| `skipulagsfulltrui` | Skipulagsfulltrúi |
| `skipulagsrad` | Skipulagsráð |
| `borgarrad` | Borgarráð |
| `borgarstjorn` | Borgarstjórn |

### Case Statuses
| Code | Color |
|------|-------|
| `samthykkt` | green (approved) |
| `frestad` | yellow (deferred) |
| Other codes | red (rejected), blue (neutral) |

### Permit Types
`nybygging` (new build), `vidbygging` (extension), `breyting_inni` (interior change), `breyting_uti` (exterior change), `nidurrif` (demolition)

### Building Types
`einbylishus`, `fjolbylishus`, `gestahus`, `geymsluskur`, `hotel`, `idnadarhus`, `parhus`, `radhus`, `sumarhus`, `verslun_skrifstofur`

## Caveats

- Only 5 municipalities indexed (Reykjavík, Hafnarfjörður, Árborg, Seltjarnarnesbær, Mosfellsbær)
- `/api/permits` endpoint returns 500 — may be deprecated or require auth
- Entity search returns empty for some queries — index may be partial
- `council_type` often null in nearby-cases responses
- Use `iceaddr` skill to convert street addresses → hnitnum for address lookup

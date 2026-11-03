---
name: utbod-reykjavik
description: Reykjavík útboðsvefur (utbod.reykjavik.is, In-Tend) — every city tender notice since 2017 by project id, current tenders, regex search.
---

# Útboðsvefur Reykjavíkurborgar (In-Tend)

**Requires:** Tier 0 (core).

`utbod.reykjavik.is` redirects to an In-Tend supplier portal at
`https://supplier.in-tend.co.uk/reykjavik`. It is a React SPA, but its JSON
backend answers on the same path without login:

| Endpoint | Method | Gives |
|---|---|---|
| `/Tenders/GetTendersList?list=current&customerId=-1` | POST `{page, orderBy, orderByDescending, pageLength, SearchText}` | Tenders open now (`projectID`, title, description, CPV, docs deadline) |
| `/Tenders/GetProjectFields?summary=false&projectId=N&lng=en-GB` | GET | `[{key, value}]` notice fields for **any** project, open or closed |

Project ids are sequential: 1 is a 2017 test project, and ~1565 was reached in
November 2026. Walking the ids therefore yields the city's whole tender register
(≈1,560 notices), which the portal UI does not show. The `list` values `closed`, `past`
and `future` all return the current list, and `awarded` returns nothing.

```bash
uv run python scripts/utbod_reykjavik.py list            # open tenders
uv run python scripts/utbod_reykjavik.py fetch           # harvest → data/processed/utbod_reykjavik_projects.csv
uv run python scripts/utbod_reykjavik.py search 'ræsting'
```

`fetch` caches one JSON per id in `data/raw/utbod_reykjavik/projects/`. It
re-fetches only uncached ids and projects whose document deadline is still in
the future (`--force` re-fetches everything), and it stops 25 ids past the
highest current project. With 4 workers a full crawl takes about 2 minutes.

## Gotchas

- Use `lng=en-GB`: field labels are the join keys, and the Icelandic labels are
  translations that drift. The English label for the deadline is
  `Date documents can be requested until`.
- `1899-01-01T00:00:00` is In-Tend's null date. `Award` and
  `Extension Clause Date` are almost always that sentinel.
- `Estimated Value` is empty in practice, and so is `OJEU Notice` since about 2022,
  even for tenders that *are* on TED (16209, 16338). Do not read an empty OJEU
  field as "not advertised in the EEA"; check TED (see [tenders](../tenders/SKILL.md)).
- Older `cpv` values are sometimes the CPV *labels* ("Janitorial services")
  rather than codes.
- Documents, bids, award values and winners need a supplier login and are not
  available. For winners and contract values use the TED award notice (`can-standard`):
  the `efac:LotResult`, `efac:TenderingParty` and `cbc:TotalAmount` fields in
  `https://ted.europa.eu/en/notice/{id}/xml`.
- Reykjavík cleaning tenders on TED use CPV 98341130 (janitorial), not only 909*.
- What the city actually pays a supplier is in the Opin Fjármál open accounts
  ([reykjavik](../reykjavik/SKILL.md), vendor-level, A-hluti only).

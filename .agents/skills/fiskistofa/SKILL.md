---
name: fiskistofa
description: Fiskistofa — public WFS layers for fishing closures, regulations and fishing areas; paid REST catch/quota data is excluded.
---

# Fiskistofa — Directorate of Fisheries

**Requires:** Tier 0 (core).

The public Hafsjá GeoServer exposes current fisheries restrictions and areas.

## API

**WFS:** `https://gis.is/geoserver/fiskistofa/wfs`

The primary layer is `virkar_skyndilokanir` (active rapid closures). Other
`virk_*`/`virkar_*` layers include active regulations, spawning areas and
fishing-area restrictions.

## Usage

```bash
uv run python scripts/fiskistofa.py list
uv run python scripts/fiskistofa.py fetch
```

## Caveats

1. These WFS layers are current state, not an event history; snapshot them to
   preserve closure history.
2. Fiskistofa's REST Gagnaveita covers catches, quotas and vessels but requires
   paid OAuth access and restricts redistribution. It is deliberately excluded.
3. Date fields carry `Z` but may be dates rather than instants.

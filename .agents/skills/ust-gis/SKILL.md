---
name: ust-gis
description: Environment Agency of Iceland GIS — open WFS layers for contaminated land, water, protected areas, noise and wastewater.
---

# UST GIS — Umhverfis- og orkustofnun

**Requires:** Tier 0 (core).

The agency's GeoServer is a public spatial catalogue separate from the existing
air-quality API integration.

## API

**WFS:** `https://gis.ust.is/geoserver/ows`

`INSPIRE:mengadur_jardvegur` is the contaminated-land registry, with location,
site name, pollution category and risk classification where known.

## Usage

```bash
uv run python scripts/ust_gis.py list
uv run python scripts/ust_gis.py fetch
```

## Caveats

1. This registry includes confirmed sites, suspected sites and historical
   burial/landfill records; it is not a count of remediated contamination.
2. Coordinates and risk class may be null, including for otherwise valid rows.
3. Keep raw GeoJSON: polygons carry the spatial detail that the tidy table does
   not preserve.

# LMI (Landmælingar Íslands) — National Land Survey

Vector geodata for Iceland mapping via GeoServer WFS. Pre-cached layers in `data/geodata/` for fast map generation.

## API

**Base URL:** `https://gis.lmi.is/geoserver/{workspace}/wfs`

No authentication required. WFS 2.0.0 protocol. Supports GeoJSON, GML, KML, Shapefile, GeoPackage output.

### Workspaces

| Workspace | Description | Scale |
|-----------|-------------|-------|
| `ERM` | EuroRegionalMap — core topographic vectors | 1:250,000 |
| `EBM` | EuroBoundaryMap — administrative boundaries | 1:100,000 |
| `ni` | Náttúrufræðistofnun — geology, nature, vegetation | 1:600,000 |
| `LMI_vektor` | Misc — municipalities, volcanic hazards, contours | varies |
| `LHG` | Landhelgisgæslan — maritime zones, depth contours | varies |

### WFS Request Pattern

```
https://gis.lmi.is/geoserver/{workspace}/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName={layer}&outputFormat=application/json&srsName=EPSG:4326
```

### Example

```bash
curl "https://gis.lmi.is/geoserver/ERM/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName=ERM:Landmask&outputFormat=application/json&srsName=EPSG:4326" > Landmask.geojson
```

## Pre-Cached Core Layers

Downloaded via `uv run python scripts/lmi.py download` into `data/geodata/`:

| Layer | Features | Size | Use |
|-------|----------|------|-----|
| `ERM:Landmask` | 104 | 1.0 MB | Iceland land polygon (base fill) |
| `ERM:CoastalLine` | 123 | 1.0 MB | Coastline outline |
| `EBM:AdministrativeUnit_level2` | 128 | 4.1 MB | Municipalities with names (`namn` field) |
| `ERM:AdministrativeAreas` | 2,713 | 5.6 MB | Small admin zones (code-based, no names) |
| `ERM:RoadLines` | 2,918 | 3.4 MB | Road network (classified by `rtt`) |
| `ERM:WatercourseLine` | 28,536 | 27.2 MB | Rivers and streams |
| `ERM:Lake_Reservoir` | 2,376 | 5.2 MB | Lakes and reservoirs |
| `ERM:LandIceArea` | 188 | 0.8 MB | Glaciers (jöklar) |
| `ERM:BuiltupAreaPoints` | 98 | 0.1 MB | Settlements with population (`ppl` field) |
| `ERM:BuiltupArea` | 22 | 0.0 MB | Urban area polygons |
| `ERM:NamedLocation_gnamel` | 616 | 0.3 MB | Place names |
| `ERM:IslandArea` | 281 | 0.5 MB | Islands |
| `ERM:Airport_Airfield_points` | 61 | 0.0 MB | Airports |
| `ERM:Port` | 11 | 0.0 MB | Harbors |
| `ERM:NatureParkArea` | 40 | 0.7 MB | National parks and reserves |

**Total: ~50 MB cached**

## Key Field Schemas

### EBM Municipalities (`AdministrativeUnit_level2`)
- `namn` — Municipality name (Icelandic, e.g., "Reykjavíkurborg")
- `shn` — Code (e.g., "IS0000")
- `desn` — Type (always "Sveitarfélag")

### ERM Roads (`RoadLines`)
- `namn1` — Road name, `rtn` — Route number
- `rtt` — Route type: 1-3 = major, 4-10 = secondary, >10 = minor
- `rsu` — Surface type, `len` — Length in km

### ERM Settlements (`BuiltupAreaPoints`)
- `namn1` — Settlement name, `ppl` — Population count
- `use` — Classification (2=town, 3=village)

### ERM Named Locations (`NamedLocation_gnamel`)
- `namn1` — Icelandic name, `nama1` — ASCII transliteration

## Extra Layers (Fetch on Demand)

```bash
uv run python scripts/lmi.py fetch ERM:WetlandArea
```

Available extras: WetlandArea, VegetationArea, PowerTransmissionLine, SpringPoint, WaterfallLine, PhysiographyPoint, SeaArea, Building, FerryCrossing, and more. Run `uv run python scripts/lmi.py list` for the full catalog.

### Geology (ni namespace)
- `ni:ni_j600v_berg_2_jardlog_2utg_fl` — Bedrock geology polygons (1:600k)
- `ni:ni_j600v_berg_2_brotalina_1utg_li` — Fault lines
- `ni:ni_j600v_berg_2_gosspr_1utg_li` — Eruptive fissures
- `ni:ni_j600v_berg_2_gigar_1utg_p` — Volcanic craters

### Regions
- `LMI_vektor:landshlutar` — Regions of Iceland (Landshlutar)

## Script Usage

```bash
# List available layers and cache status
uv run python scripts/lmi.py list

# Download all core layers (~50 MB)
uv run python scripts/lmi.py download

# Fetch a specific extra layer
uv run python scripts/lmi.py fetch ERM:WetlandArea

# Generate interactive HTML map
uv run python scripts/kortagerð.py html -o reports/iceland-map.html

# Generate static PNG map
uv run python scripts/kortagerð.py static -o reports/iceland-map.png

# Zoomed map with municipality highlight
uv run python scripts/kortagerð.py static --bounds capital --highlight "Reykjavíkurborg" -o reports/rvk.png
```

## Coordinate Systems

All cached files use **WGS84 (EPSG:4326)**. The native Icelandic CRS is **ISN93 (EPSG:3057)**. Reproject if needed for precise area/distance calculations.

## Caveats

- ERM data is at 1:250,000 scale — good for country/region maps, not street-level detail
- `AdministrativeAreas` (ERM, 2713 zones) has NO name field — use `AdministrativeUnit_level2` (EBM, 128 municipalities) for named boundaries
- `NamedLocation` returns 0 features; use `NamedLocation_gnamel` instead
- WatercourseLine is the largest layer (28k features, 27 MB) — may be slow to render in interactive maps
- Icelandic characters (þ, ð, æ, ö) are preserved in GeoJSON; ensure UTF-8 encoding

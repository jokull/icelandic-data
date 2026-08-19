---
name: natt
description: Náttúrufræðistofnun habitat types, species and geology via GeoServer WCS/WMS/WFS — vistgerðir 1:25k, 5 m raster.
---

# Náttúrufræðistofnun (NÍ) — Open data

Náttúrufræðistofnun Íslands (Icelandic Institute of Natural History) publishes
habitat-type, species-distribution, and geological data as open data.

- Public download portal: https://www.natt.is/is/midlun/opin-gogn/nidurhal-gagna
- Habitat-map viewer: http://vistgerdakort.ni.is/
- Map browser: https://kort.gis.is/mapview/
- Reference monograph (Fjölrit 54, 2018): http://utgafa.ni.is/fjolrit/Fjolrit_54.pdf
- Change-log between 1st and 3rd edition: http://utgafa.ni.is/kort/lysigogn/vg25r_3utg_breytingar.pdf
- License: "Gögnin eru öllum opin" — open, no use restrictions.

## OGC services

NÍ runs a GeoServer at `https://gis.natt.is/geoserver/`. It hosts both NÍ's own
layers and several layers federated from LMI / Hagstofan / Skógræktin.

- WFS GetCapabilities: `https://gis.natt.is/geoserver/wfs?service=WFS&version=2.0.0&request=GetCapabilities`
- WMS GetCapabilities: `https://gis.natt.is/geoserver/wms?service=WMS&version=1.3.0&request=GetCapabilities`
- WCS GetCapabilities: `https://gis.natt.is/geoserver/wcs?service=WCS&version=2.0.1&request=GetCapabilities`
- All layers are published in **EPSG:3057** (ISN93 / LCC Iceland).
- WFS supports `outputFormat=application/json` (GeoJSON) and CQL filters via
  `CQL_FILTER=…`.
- WCS spells the workspace separator `__`, WMS/WFS spell it `:`. The same
  coverage is `vistgerdir__ni_vg25r_3utg_lzw` (WCS) and
  `vistgerdir:ni_vg25r_3utg_lzw` (WMS).

## Vistgerðir á Íslandi (3. útgáfa, 1:25.000) — habitat types

Habitat types ("vistgerðir") are NÍ's national EUNIS-aligned classification.
There are 64 land-, 17 freshwater-, and 24 coastal-shore habitat types,
documented in Fjölrit 54.

**The 3rd edition is a raster.** The polygonised vector edition
`LMI_vektor:vistgerd` was withdrawn in 2026 (see Caveats) — the surviving
national-coverage publication is:

| Service | Name | Notes |
|---|---|---|
| WCS coverage | `vistgerdir__ni_vg25r_3utg_lzw` | GeoTIFF, the fetchable one |
| WMS layer | `vistgerdir:ni_vg25r_3utg_lzw` | styled `vistgerdir:vistgerdakort_3utg` |

Grid (from `DescribeCoverage`):

| property | value |
|---|---|
| CRS | EPSG:3057 (ISN93) |
| resolution | 5 m |
| size | 102928 × 72798 px (7.5 Gpx) |
| envelope | `244069.5 311026.7 758709.5 675016.7` |
| band 1 `GRAY_INDEX` | **habitat-type code** — the old `DN` values, unchanged |
| band 2 | alpha; request `rangeSubset=GRAY_INDEX` to skip it |

### The legend *is* the `DN` → label inventory

`GetLegendGraphic` in JSON returns the raster colormap — 73 entries, each with
a `quantity` (the `DN`) and a `label` (the old `htxt` string, correct UTF-8).
One request replaces streaming 24M vector rows:

```bash
curl -sS "https://gis.natt.is/geoserver/wms?service=WMS&version=1.1.1\
&request=GetLegendGraphic&layer=vistgerdir:ni_vg25r_3utg_lzw\
&format=application/json" | jq -r '
  .Legend[0].rules[0].symbolizers[0].Raster.colormap.entries[]
  | "\(.quantity)\t\(.label)"' | sort -n
```

`scripts/natt.py inventory` does exactly this and writes
`data/raw/natt/vistgerdir/inventory.csv`.

### `DN` → habitat-type mapping (subset of interest)

| DN | Code | Label |
|---:|------|-------|
| 1–5 | L1.1–L1.5 | Melavistir (gravel/sand barrens) |
| 6–8 | L3.1–L3.3 | Skriðuvistir (scree) |
| 9–10 | L4.1–L4.2 | Eyrar / aurar (river plains) |
| 11–13 | L5.1–L5.3 | Mosavistir (moss) |
| 14–17 | L6.1–L6.4 | Hraunavistir (lava fields) |
| 18 | L2.1 | Moldavist (eroded soil) |
| 19–25 | L7.* | Strandvistir (coastal terrestrial) |
| 26–38 | L8.* | Mýrar / flóar (mires / fens) |
| 39–45 | L9.* | Graslendi (grasslands) |
| 46–55 | L10.* | Móar / kjarrlendi (heaths / scrub) |
| 61–64 | L12.1–L12.4 | Hveravistir (geothermal) |
| 95 | **L14.2** | **Tún og akurlendi** (cultivated hayfield + arable) |
| 98 | V1 | Vötn (lakes) |
| 99 | V2 | Ár (rivers) |
| 108 | L13.1 | Jöklar og urðarjöklar (glaciers / rock glaciers) |
| 122 | L1.6 | Landmelhólavist (inland dune) |
| 130 | L8.7 | Rimamýravist (string fen) |
| 150 | L14.1 | Þéttbýli og annað manngert land (urban / man-made) |
| 152 | L11 | Birkiskógur (birch woodland) |
| 153 | L14.3 | Skógrækt (forestry) |
| 160 | L14.4 | Alaskalúpína (Alaska lupine — invasive) |
| 161 | L14.5 | Uppgræðslur (revegetated land) |
| 162 | L14.6 | Skógarkerfill ofl. þéttar tegundir (cow-parsley etc.) |
| 175 | F | Fjöruvistir (intertidal) |
| 176 | FX1.1 | Sjávarlón (coastal lagoons) |

The `DN` values are **not** contiguous and not ordered by code — always take the
full table from `natt.py inventory` rather than assuming a range.

### Fetching one habitat type

Never ask for the whole 5 m grid in one request. `scaleFactor` downsamples
server-side (nearest neighbour) and `subset` tiles it; both compose:

```bash
# whole country at 1 km — 377 KB, <1 s. Good for probes and sanity checks.
curl -sS "https://gis.natt.is/geoserver/wcs?service=WCS&version=2.0.1\
&request=GetCoverage&coverageId=vistgerdir__ni_vg25r_3utg_lzw\
&format=image/tiff&rangeSubset=GRAY_INDEX&scaleFactor=0.005" -o vg_1km.tif

# one 100 km tile at 20 m — 26 MB, 30 s to a couple of minutes depending on
# server load. scaleFactor = 5 / target_metres.
curl -sS "https://gis.natt.is/geoserver/wcs?service=WCS&version=2.0.1\
&request=GetCoverage&coverageId=vistgerdir__ni_vg25r_3utg_lzw\
&format=image/tiff&rangeSubset=GRAY_INDEX&scaleFactor=0.25\
&subset=X(400000,500000)&subset=Y(350000,450000)" -o vg_tile.tif
```

Then mask band 1 to the code you want (`arr == 95`).
`scripts/natt.py habitat --dn 95` does the whole tiled mosaic and writes an
ISN93 uint8 mask GeoTIFF plus a sidecar with the area. Cost is server-bound and
scales with output pixels — measured, national coverage:

| `--res` | tiles | wall time | mask size | L14.2 area |
|---:|---:|---|---:|---:|
| 100 m | 4 | ~1 min | 0.2 MB | 1,807.5 km² |
| 50 m (default) | 6 | ~2 min | 0.6 MB | 1,806.0 km² |
| 20 m | 24 | ~30 min | 2.7 MB | 1,805.8 km² |

Country-scale renders in this repo draw at 120–200 m/px, so even 100 m is
sufficient for a map; 20 m is for detail work.

**Native 5 m — only if you need patch-level geometry.** ~45 min end to end
(582 of 1,924 tiles carry the class, found with a `scaleFactor` sampling pass
first) versus ~2 min for the 50 m mask. Request `compression=Deflate` on
GetCoverage — a tile drops ~18× (8.4 MB → 0.47 MB), which is what makes a
native pass affordable at all. And gis.natt.is has returned a `502` partway
through a long tile sequence, so cache per tile and retry before starting.

**Regression check:** L14.2 (cultivated land) must come out at ≈1,806 km²,
matching the ~1,800 km² on the natt.is habitat page. The three resolutions
agree to within 0.1%, and an independent native-5 m extract lands at exactly
1,806 km² (Guðröður / gudrodur, cross-check on PR #14) — the number is a
property of the data, not of the sampling.

## Other vector layers in the WFS

The WFS exposes ~150 layers. The most useful for nature/agriculture work:

| Layer | What |
|-------|------|
| `vistgerdir:v_vg25v_fl_land` | **Geothermal (L12) habitat polygons only** — 360 rows |
| `vistgerdir:v_vg25v_fl_vatn` | Freshwater habitat polygons (V1.1–V1.8), 54k rows |
| `vistgerdir:v_vg25v_fl_fjorur` | Littoral-shore polygons (F1.*, F2.*, FX.*), 20k rows |
| `ni:ni_vg25v_li` | Running-water lines (rivers) |
| `ni:ni_vg25v_pt` | Cold/thermal-spring points |
| `ni:vistgerdir_punktar` | Field-survey sample points (8k; all L-codes) |
| `ni:Floraisl_dreifing` | Vascular-plant distribution (Flóra Íslands) |
| `ni:Smadyr_dreifing` | Invertebrate distribution |
| `ni:hvitabjorn_a_islandi` | Polar-bear sightings |
| `land_og_skogur:natturulegt_birkilendi` | Natural birch woodland (Skógræktin) |
| `land_og_skogur:raektad_skoglendi` | Cultivated forest (Skógræktin) |
| `land_og_skogur:jardvegsrof` | Soil erosion |
| `CORINE:clc18_is`, `clc12_is`, `clc06_is`, `clc00_is` | CORINE Land Cover for Iceland |

The three `vistgerdir:v_vg25v_fl_*` layers share one schema — string codes, not
`DN`: `id, vg1, vg1_texti, vg1_linkur, vg2 … vg5 (+_texti/_linkur), eunis_1,
eunis_2, geom`. `vg1` is the top level (`L`/`V`/`F`), `vg2`–`vg5` drill down
(`vg2='F2'`, `vg3='F2.3'`). Filter with CQL, e.g. `CQL_FILTER=vg3='F2.3'`.

## Caveats

- **2026-08 — `LMI_vektor:vistgerd` was withdrawn.** The polygonised vector
  edition of the habitat map (schema `DN` int + `htxt` str, ~24M rows) is gone
  from gis.natt.is, gis.lmi.is and ogc.gis.is alike; all three answer
  `InvalidParameterValue: Feature type LMI_vektor:vistgerd unknown`. It is
  **not** coming back under a new vector name — use the WCS raster above.
- **Trap: the new `vistgerdir:v_vg25v_fl_*` layers are NOT the replacement.**
  The naming is actively misleading: `v_vg25v_fl_land` sounds like the land
  habitat map but its capabilities title is *"Vistgerðir: Hverasvæði – Habitat
  types: Geothermal lands"* and every one of its 360 rows is `vg2='L12'`. Its
  siblings cover freshwater (`V*`) and littoral shores (`F*`). **The terrestrial
  habitats L1–L11, L13 and L14 — including L14.2 Tún og akurlendi — have no
  polygon layer on the WFS at all.** Always check `vg1`/`vg2` values with
  `count=1` before assuming a layer covers what its name suggests.
- The text-based GeoServer responses (GML/CSV) come through as **cp1252-mojibake**
  for Icelandic characters. Always request `outputFormat=application/json` for
  clean UTF-8. The legend JSON is already correct UTF-8.
- Edition 3 (2023) reshuffled L-codes vs edition 1 — see `vg25r_3utg_breytingar.pdf`
  before mixing data across editions. The raster's `DN` values match edition 3's
  vector `DN` exactly, so pre-2026 `DN`-based code in this repo ports unchanged.
- WCS `scaleFactor` is served off pyramid overviews and is fast (a full-country
  1 km read is <1 s); a full-resolution national fetch is 7.5 Gpx and must be
  tiled. `scripts/natt.py` tiles at 5000 output px per request.

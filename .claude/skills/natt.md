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
- All layers are published in **EPSG:3057** (ISN93 / LCC Iceland).
- WFS supports `outputFormat=application/json` (GeoJSON) and CQL filters via
  `CQL_FILTER=…`.

## Vistgerðir á Íslandi (3. útgáfa, 1:25.000) — habitat types

Habitat types ("vistgerðir") are NÍ's national EUNIS-aligned classification.
There are 64 land-, 17 freshwater-, and 24 coastal-shore habitat types,
documented in Fjölrit 54.

The 3rd edition (`vg25_3utg`) is published as:
- raster: `ni_vg25r_3utg` (5 m grid; download as GeoTIFF / file-GDB / shapefile)
- vector polygons (one row per habitat patch, derived from the raster):
  `LMI_vektor:vistgerd` on the WFS — title *"Vistgerð 25r v3.0 fyrirspurnir"*

The vector layer's schema is:

| field | type | meaning |
|-------|------|---------|
| `geom` | Polygon (EPSG:3057) | habitat patch geometry |
| `DN`   | int   | habitat-type code (raster cell value) |
| `htxt` | str   | human-readable label, e.g. `"L14.2 Tún og akurlendi"` |

Total polygons: ~24M (most are tiny — the layer is the polygonised raster).

### `DN` → habitat-type mapping (subset of interest)

Codes and labels are sampled from the WFS attributes; spelling matches the
service exactly (Icelandic special chars come back as cp1252 mojibake when
GeoServer is asked for plain text — request `outputFormat=application/json`
to get correct UTF-8).

| DN | Code | Label |
|---:|------|-------|
| 1–5 | L1.1–L1.5 | Melavistir (gravel/sand barrens) |
| 6–8 | L3.1–L3.3 | Skriðuvistir (scree) |
| 9–10 | L4.1–L4.2 | Eyrar / aurar (river plains) |
| 11–13 | L5.1–L5.3 | Mosavistir (moss) |
| 15–17 | L6.1, L6.3, L6.4 | Hraunavistir (lava fields) |
| 19–25 | L7.* | Strandvistir (coastal terrestrial) |
| 26–38 | L8.* | Mýrar / flóar (mires / fens) |
| 39–45 | L9.* | Graslendi (grasslands) |
| 46–55 | L10.* | Móar / kjarrlendi (heaths / scrub) |
| 95 | **L14.2** | **Tún og akurlendi** (cultivated hayfield + arable) |
| 98 | V1 | Vötn (lakes) |
| 99 | V2 | Ár (rivers) |
| 108 | L13.1 | Jöklar og urðarjöklar (glaciers / rock glaciers) |
| 150 | L14.1 | Þéttbýli og annað manngert land (urban / man-made) |
| 152 | L11 | Birkiskógur (birch woodland) |
| 153 | L14.3 | Skógrækt (forestry) |
| 160 | L14.4 | Alaskalúpína (Alaska lupine — invasive) |
| 162 | L14.6 | Skógarkerfill ofl. þéttar tegundir (cow-parsley etc.) |
| 175 | F | Fjöruvistir (intertidal) |
| 176 | FX1.1 | Sjávarlón (coastal lagoons) |

### Counting / fetching one habitat type

Filter on `DN` (CQL `htxt LIKE 'L14.2%'` works too but `DN` is faster):

```bash
# count
curl -sS "https://gis.natt.is/geoserver/wfs?service=WFS&version=2.0.0\
&request=GetFeature&typeNames=LMI_vektor:vistgerd\
&CQL_FILTER=DN=95&resultType=hits"

# download as GeoJSON (EPSG:3057)
curl -sS "https://gis.natt.is/geoserver/wfs?service=WFS&version=2.0.0\
&request=GetFeature&typeNames=LMI_vektor:vistgerd\
&CQL_FILTER=DN=95&outputFormat=application/json&srsName=EPSG:3057" \
  -o data/raw/natt/L14.2_tun_og_akurlendi.geojson
```

For L14.2 (cultivated land) the count is ~16,600 polygons and total area
~1,800 km², matching the figure on the natt.is habitat page.

## Other vector layers in the WFS

The WFS exposes ~150 layers. Beyond `LMI_vektor:vistgerd` the most useful for
nature/agriculture work are:

| Layer | What |
|-------|------|
| `ni:ni_vg25v_fl` | Coastal-shore habitat polygons (24 fjöru-vistir) |
| `ni:ni_vg25v_li` | Running-water lines |
| `ni:ni_vg25v_pt` | Cold/thermal-spring points |
| `ni:vistgerdir_punktar` | Field-survey sample points |
| `ni:Floraisl_dreifing` | Vascular-plant distribution (Flóra Íslands) |
| `ni:Smadyr_dreifing` | Invertebrate distribution |
| `ni:hvitabjorn_a_islandi` | Polar-bear sightings |
| `land_og_skogur:natturulegt_birkilendi` | Natural birch woodland (Skógræktin) |
| `land_og_skogur:raektad_skoglendi` | Cultivated forest (Skógræktin) |
| `land_og_skogur:jardvegsrof` | Soil erosion |
| `CORINE:clc18_is`, `clc12_is`, `clc06_is`, `clc00_is` | CORINE Land Cover for Iceland |

## Caveats

- The text-based GeoServer responses (GML/CSV) come through as **cp1252-mojibake**
  for Icelandic characters. Always request `outputFormat=application/json` for
  clean UTF-8.
- The vector `LMI_vektor:vistgerd` is the polygonised version of the raster
  `ni_vg25r_3utg` — many tiny polygons. For map rendering at country scale,
  dissolve or simplify after filtering.
- Edition 3 (2023) reshuffled L-codes vs edition 1 — see `vg25r_3utg_breytingar.pdf`
  before mixing data across editions.
- The WFS server can be slow on un-indexed CQL filters; filtering on `DN`
  (integer) is much faster than `htxt LIKE …`.

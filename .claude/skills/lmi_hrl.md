# LMI High Resolution Layers (Copernicus HRL Iceland 2015)

Pan-European Copernicus Land Monitoring Service "High Resolution Layers"
clipped to Iceland and re-served by Landmælingar Íslands. Five thematic
binary/percentage rasters, all from the 2015 reference year, all 20 m
native resolution, all in **EPSG:5325** (ETRS89 / LAEA Iceland).

Catalogue UUID: `58e1ed85-df4d-408d-a34f-d0a60628cb34`
[Metadata page](https://gatt.lmi.is/geonetwork/srv/eng/catalog.search#/metadata/58e1ed85-df4d-408d-a34f-d0a60628cb34)

## OGC services

```
WMS:  https://gis.lmi.is/geoserver/High_Resolution_Layer/wms
WCS:  https://gis.lmi.is/geoserver/High_Resolution_Layer/wcs
WMTS: https://gis.lmi.is/geoserver/gwc/service/wmts
```

The same workspace is mirrored at `https://gis.natt.is/geoserver/High_Resolution_Layer/` (Náttúrufræðistofnun) — either host works.

## Layers

| Short name | WMS layer / WCS coverage | What | Pixel coding |
|------------|--------------------------|------|--------------|
| `grassland` | `Grassland` / `High_Resolution_Layer__Grassland` | Managed, semi-natural & natural grassy vegetation | `1` grass · `0` non-grass · `254` no-data inside Iceland · `255` outside |
| `tree_cover` | `Tree_Cover_Density` / `High_Resolution_Layer__Tree_Cover_Density` | Tree canopy density 0-100 % | uint8 percentage; `255` no-data |
| `imperviousness` | `Imperviousness` / `High_Resolution_Layer__Imperviousness` | Sealed surface 0-100 % | uint8 percentage; `255` no-data |
| `water_wetness` | `Water_and_Wetness` / `High_Resolution_Layer__Water_and_Wetness` | Permanent / temporary water & wetness | class codes |
| `dominant_leaf` | `Dominant_Leaf_Type` / `High_Resolution_Layer__Dominant_Leaf_Type` | Broadleaved / coniferous in tree-covered pixels | class codes |

Bounding box (EPSG:5325): `1399300, 53900, 2007200, 609200` (m)
Grid: 30394 × 27764 pixels @ 20 m

## Fetching

```bash
# Full 20 m GeoTIFF — Grassland is ~865 MB uncompressed
uv run python scripts/lmi_hrl.py fetch grassland

# Downsampled (scaleFactor 0.2 → 100 m, ~33 MB)
uv run python scripts/lmi_hrl.py fetch grassland --scale 0.2

# Quick WMS preview — useful for sanity-checking before a big WCS download
curl -o preview.png "https://gis.lmi.is/geoserver/High_Resolution_Layer/wms\
?service=WMS&version=1.3.0&request=GetMap&layers=Grassland&styles=\
&format=image/png&transparent=true&width=800&height=600\
&crs=EPSG:3057&bbox=200000,300000,800000,700000"
```

## Grassland-area sanity check

The Grassland layer marks **~4,036 km² (≈3.9 % of Iceland)** as grassland under
the Copernicus Pan-European definition. This is **much smaller** than the
*Graslendi* polygons (vistgerðir L9.\*) recorded in Náttúrufræðistofnun's
1:25 000 vistgerðir map — the two products use different definitions:

- **Copernicus HRL Grassland** is a Pan-European mask calibrated mainly to
  managed lowland pastures and meadows — agricultural grassland plus
  semi-natural lowland grass. Most of Iceland's tundra-grass and heath is
  classified as "non-grassland".
- **NÍ vistgerðir L9** captures Iceland's full natural-grass habitats
  (mólendi-graslendi, valllendi, snjódældir, sjávarfitjar, etc.).

Use HRL when comparing across European countries; use NÍ vistgerðir when
mapping Iceland's natural ecosystems.

## Caveats

- Native CRS is **EPSG:5325**, not the usual Iceland CRS (EPSG:3057). Reproject
  with `rasterio.warp` or pass `srsName=EPSG:3057` on WMS requests.
- The WCS server returns *uncompressed* GeoTIFFs by default. Expect ~840 MB
  per full-resolution layer; reproject + LZW-compress locally if you need to
  ship them.
- Reference year is 2015 — use Sentinel-derived national products
  (Náttúrufræðistofnun vistgerðir 2023, Skógræktin natural-birch layer) when
  freshness matters.
- `255` is the NoData fill outside Iceland and `254` is the in-mask "could
  not classify" code; mask both before computing area or statistics.

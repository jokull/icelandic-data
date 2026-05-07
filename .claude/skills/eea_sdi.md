# EEA SDI — European Environment Agency geospatial catalogue

European Environment Agency's geospatial-data Spatial Data Infrastructure
(SDI). Front-end at <https://sdi.eea.europa.eu/catalogue/>. The catalogue
is run on **GeoNetwork 4.4** and surfaces ~10 000 datasets covering land
cover, biodiversity, climate, water, soil, air-quality, marine, energy
and transport for the EEA38 (Europe + EFTA + Western Balkans).

Most records are produced by the **Copernicus Land Monitoring Service**
(CLMS) and are mirrored on EEA's **discomap** ArcGIS server at
<https://image.discomap.eea.europa.eu/>. Since LMI's `gis.lmi.is` only
republishes the Iceland clip of a small subset of CLMS layers, going to
the EEA SDI directly opens up many more datasets (CORINE, HRL series,
Natura 2000, Imperviousness change, Tree Cover Change, Water & Wetness
Probability, Small Woody Features, etc.).

## API surface

| Endpoint | Purpose | Format |
|----------|---------|--------|
| `/catalogue/srv/api/site` | Service info / version | JSON |
| `/catalogue/srv/api/search/records/_search` | Elasticsearch search (rich) | JSON |
| `/catalogue/srv/eng/csw` | OGC CSW 2.0.2 GetRecords / GetCapabilities | XML |
| `/catalogue/srv/api/records/{uuid}/formatters/xml` | Full ISO 19115 XML for one record | XML |
| `/catalogue/srv/api/records/{uuid}/formatters/xsl-view` | Rendered HTML view | XML/HTML |
| `/public/catalogue-graphic-overview/{uuid}.png` | Catalogue thumbnail | PNG |
| `/catalogue/srv/eng/catalog.search#/metadata/{uuid}` | Human metadata page | HTML |

> **Tip**: the obvious-looking `GET /catalogue/srv/api/records/{uuid}` returns 404 on this catalogue.
> Use `formatters/xml` for ISO XML or the `_search` endpoint with `{"term":{"uuid":"..."}}` for the
> JSON view.

No authentication is required for any of these. (Some datasets'
`WWW:DOWNLOAD` links point to <https://land.copernicus.eu/> which *does*
require a free Copernicus Land account — see "Download protocols" below.)

## Search via the Elasticsearch endpoint

The richest surface. POST a JSON body in standard ES query DSL.

```bash
curl -sS "https://sdi.eea.europa.eu/catalogue/srv/api/search/records/_search?from=0&size=10" \
  -H "Accept: application/json" -H "Content-Type: application/json" \
  -d '{
    "query":{"bool":{
      "must":[{"match":{"resourceTitleObject.langeng":"grassland"}}],
      "filter":[{"geo_shape":{"geom":{
        "shape":{"type":"envelope","coordinates":[[-25,67],[-13,63]]},
        "relation":"intersects"
      }}}]
    }},
    "_source":["uuid","resourceTitleObject.default","link","publicationYearForResource"]
  }' | jq '.hits.hits[]._source.resourceTitleObject.default'
```

`coordinates` for `envelope` are `[[west,north],[east,south]]` (top-left
then bottom-right) in WGS84.

### Useful `_source` fields

| Field | Meaning |
|-------|---------|
| `uuid` / `metadataIdentifier` | Stable record id |
| `resourceTitleObject.{default,langeng}` | Title (multilingual) |
| `resourceAbstractObject.{default,langeng}` | Abstract |
| `cl_resourceScope[].key` | `dataset`, `series`, `service`, `nonGeographicDataset`, … |
| `cl_topic[].key` | INSPIRE topic — `environment`, `farming`, `imageryBaseMapsEarthCover`, … |
| `inspireTheme[]` | INSPIRE Annex theme codes |
| `OrgForResourceObject.langeng` | Producing organisation |
| `publicationYearForResource` | Year the data was published |
| `geom` | GeoJSON polygon of the spatial footprint |
| `link[]` | List of `{protocol, urlObject, nameObject, descriptionObject}` items |
| `recordLink_children_uuid[]` | UUIDs of child datasets (for series records) |
| `agg_associated[]` | Related-dataset UUIDs |

### Iceland-only filter

Iceland sits between roughly `(-25, -13)` longitude and `(63, 67)` latitude.
Use the `geo_shape` filter shown above. Many EEA datasets are EEA38 in
scope so they intersect Iceland even when the filename doesn't say so.

## CSW (OGC Catalog Service for the Web)

Returns a Dublin-Core summary with `<dc:URI>` link tags. Useful when you
want a quick scan and don't need every metadata field.

```bash
curl -sS -G "https://sdi.eea.europa.eu/catalogue/srv/eng/csw" \
  --data-urlencode "service=CSW" \
  --data-urlencode "version=2.0.2" \
  --data-urlencode "request=GetRecords" \
  --data-urlencode "typeNames=csw:Record" \
  --data-urlencode "resultType=results" \
  --data-urlencode "outputSchema=http://www.opengis.net/cat/csw/2.0.2" \
  --data-urlencode "elementSetName=full" \
  --data-urlencode "constraintLanguage=CQL_TEXT" \
  --data-urlencode "constraint_language_version=1.1.0" \
  --data-urlencode "constraint=AnyText like '%grassland%'" \
  --data-urlencode "maxRecords=20"
```

The `numberOfRecordsMatched` attribute in the response tells you the
total; pass `startPosition=N` to page.

## Following download links

Each record's `link[]` array carries one entry per access mechanism.
The `protocol` field tells you what to do with the URL.

| Protocol | Meaning | Auth? |
|----------|---------|-------|
| `OGC:WMS` | WMS GetCapabilities URL — visualise as tiles | No |
| `OGC:WFS` | WFS GetCapabilities URL — vector download | No |
| `OGC:WCS` | WCS GetCapabilities URL — raster download | No |
| `ESRI:REST` | ArcGIS REST endpoint (Image-/Map-/FeatureServer) | No |
| `WWW:DOWNLOAD` / `WWW:DOWNLOAD-1.0-http--download` | Direct download | usually yes (Copernicus) |
| `WWW:LINK` / `WWW:LINK-1.0-http--link` | Generic web link / docs | No |
| `WWW:URL` | Generic web link | No |
| `DOI` | DOI URL for citation | No |
| `image/png` | Catalogue thumbnail / preview | No |

For *no-auth* programmatic access prefer **OGC** or **ESRI:REST** links;
they almost always go to `image.discomap.eea.europa.eu` or to a JRC /
EUMETSAT GeoServer that does not require credentials. For *bulk*
downloads (full GeoTIFF tiles) the `WWW:DOWNLOAD` link points to
`land.copernicus.eu` which needs a free CLMS account.

## Helpful Iceland-relevant datasets

(Not exhaustive — use search to discover more.)

| UUID | What | Resolution | Year |
|------|------|------------|------|
| `35a036bb-c027-401c-8625-2ecf722e8461` | HRL Grassland mask, Europe | 20 m | 2015 |
| `5ebf3d6e-b148-4d22-b5e5-173a9d8fd661` | HRL Grassland mask, Europe | 100 m | 2018 |
| `0b6254bb-4c7d-41d9-8eae-c43b05ab2965` | HRL Grassland (annual), Europe | 10 m | 2017– |
| `a0925bc0-d3d8-49af-ba9d-c4f1cf2b654d` | HRL Grassland Change | 20 m | 2015–2018 |
| `82d8f687-3ef1-4b84-89ef-5a1e646137f8` | HRL Grasslands (series) | — | — |

For Iceland-only clipped versions of HRL Grassland / Tree Cover /
Imperviousness / Water-and-Wetness / Dominant-Leaf-Type, see the
`lmi_hrl` skill — those are the same data on `gis.lmi.is`.

## Script

```bash
# search by free-text + Iceland bbox
uv run python scripts/eea_sdi.py search grassland --iceland

# search any keyword in any region
uv run python scripts/eea_sdi.py search "tree cover density"

# print one record's metadata, links, and thumbnail URL
uv run python scripts/eea_sdi.py record 35a036bb-c027-401c-8625-2ecf722e8461

# print only the OGC / ESRI links from a record
uv run python scripts/eea_sdi.py links 35a036bb-c027-401c-8625-2ecf722e8461

# download a record's ISO 19115 XML (full metadata)
uv run python scripts/eea_sdi.py xml 35a036bb-c027-401c-8625-2ecf722e8461 \
  -o data/raw/eea_sdi/grassland_2015.xml
```

## Caveats

1. **`/srv/api/records/{uuid}` returns 404** — use the `_search` endpoint with a `term` filter on `uuid`, or `formatters/xml`.
2. **Search hits are paginated** — default page size 10, hard cap 1 000 per page (`size` parameter). Loop with `from` to enumerate.
3. **Series records have empty `link[]`** — you must follow `recordLink_children_uuid[]` to the child dataset records to find the actual download URLs.
4. **The bbox `coordinates` for `geo_shape`/`envelope` are `[[w,n],[e,s]]`** (top-left, bottom-right) — the *opposite* of the usual GIS minx/miny/maxx/maxy ordering. Easy to invert.
5. **`WWW:DOWNLOAD` to land.copernicus.eu requires registration** — for unauthenticated bulk pulls use `image.discomap.eea.europa.eu` ArcGIS REST/WMS instead.
6. **discomap WMS GetMap caps requests at ~10 M output pixels** — even though the GetCapabilities advertises `MaxWidth=4096` and `MaxHeight=4096`, requesting both at once returns HTTP 400. The largest aspect-correct frame is around 3500×2666.
7. **discomap WMS returns *styled* RGB images, not raw raster values.** For raw probability / index pixel values, decode the legend swatch RGB → bin midpoint (see `reports/grassland_probability_heatmap.py` for an example) or use the matching WCS endpoint when available.
8. **discomap MapServer `exportImage` with `pixelType=U8` still returns RGBA PNGs** for MapServers (vs. ImageServers, where raw values do come through). Single-band raw pulls work only when the metadata link is `ESRI:REST → ImageServer`.
9. **Encoding** — all strings are UTF-8 in the JSON/XML responses. Icelandic characters (þ, ð, æ, ö) survive intact.
10. **Native CRS varies per layer** — Pan-European HRL products are EPSG:5325 (LAEA Iceland) or EPSG:3035 (LAEA Europe); WMS endpoints additionally publish EPSG:3857, 4326. Reproject for area-correct stats.

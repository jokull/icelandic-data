"""Health probe — EEA Spatial Data Infrastructure catalogue (sdi.eea.europa.eu).

Contract: the three call shapes `scripts/eea_sdi.py` makes against this
GeoNetwork 4.4 instance still work —

  1. `POST …/search/records/_search` with an Elasticsearch body  (`search()`)
  2. the same endpoint with a `{"term": {"uuid": …}}` filter     (`fetch_record()`)
  3. `GET …/records/{uuid}/formatters/xml`                        (`cmd_xml()`)

Plus the Iceland `geo_shape` filter, whose `[[w,n],[e,s]]` envelope ordering is
the opposite of the usual GIS convention and is caveat #4 in the skill. It is
worth an assertion because inverting it does not error — it silently returns
zero hits, which reads as "no Iceland data" rather than "bug".

The probes go through the `http` fixture rather than calling `search()` /
`fetch_record()` directly, so the timeouts and retry policy are the shared ones.

Payload discipline: `size` is 1–5 and `_source` is trimmed, so each search is a
few KB against a ~10k-record catalogue. The record ISO XML is ~40 KB, which is
the smallest form of that contract — there is no lighter metadata endpoint
(`GET /srv/api/records/{uuid}` 404s here; skill caveat #1).
"""
from __future__ import annotations

from scripts.eea_sdi import BASE, ICELAND_BBOX, RECORD_XML, SEARCH

SITE = f"{BASE}/srv/api/site"

# HRL Grassland 2015, 20 m — the record the skill documents and the Pan-European
# twin of the gis.lmi.is Iceland clip probed by test_lmi_hrl.py.
GRASSLAND_UUID = "35a036bb-c027-401c-8625-2ecf722e8461"


def test_site_reports_a_geonetwork_4_4_platform(http):
    """Cheapest liveness check, and it pins the platform the client assumes.

    GeoNetwork 4 is where the `_search` + `formatters/xml` surface lives; a
    major-version jump would move it.
    """
    r = http.get(SITE, headers={"Accept": "application/json"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("application/json"), (
        r.headers.get("content-type")
    )

    site = r.json()
    assert site, "site info is empty"
    version = site.get("system/platform/version", "")
    assert version.startswith("4."), (
        f"GeoNetwork platform version is {version!r}, expected 4.x — the eea_sdi "
        f"skill's API surface may have moved"
    )


def test_freetext_search_returns_hits(http):
    """The `search()` body shape, bounded to 5 hits."""
    r = http.post(
        SEARCH,
        headers={"Accept": "application/json"},
        json={
            "from": 0,
            "size": 5,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": "grassland",
                                "fields": [
                                    "resourceTitleObject.langeng^3",
                                    "resourceTitleObject.default^3",
                                    "allKeywords",
                                ],
                            }
                        }
                    ],
                    "filter": [],
                }
            },
            "_source": ["uuid", "resourceTitleObject", "link"],
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert "hits" in payload, f"no 'hits' key; got {sorted(payload)}"
    assert payload["hits"]["total"]["value"] > 0, "'grassland' matched zero records"

    hits = payload["hits"]["hits"]
    assert hits, "total > 0 but no hits returned"
    source = hits[0]["_source"]
    assert "uuid" in source, f"unexpected _source shape: {sorted(source)}"


def test_iceland_bbox_filter_matches_records(http):
    """`--iceland` must keep working, and keep its [[w,n],[e,s]] ordering.

    An inverted envelope returns zero hits rather than an error, so assert on
    the hit count.
    """
    r = http.post(
        SEARCH,
        headers={"Accept": "application/json"},
        json={
            "size": 1,
            "query": {
                "bool": {
                    "must": [{"match_all": {}}],
                    "filter": [
                        {
                            "geo_shape": {
                                "geom": {
                                    "shape": {
                                        "type": "envelope",
                                        "coordinates": ICELAND_BBOX,
                                    },
                                    "relation": "intersects",
                                }
                            }
                        }
                    ],
                }
            },
            "_source": ["uuid"],
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    total = r.json()["hits"]["total"]["value"]
    assert total > 0, (
        f"Iceland geo_shape filter matched zero records — envelope ordering or "
        f"the 'geom' field may have changed (ICELAND_BBOX={ICELAND_BBOX})"
    )


def test_record_lookup_by_uuid(http):
    """`fetch_record()`'s term filter, on a record the skill hardcodes."""
    r = http.post(
        SEARCH,
        headers={"Accept": "application/json"},
        json={
            "size": 1,
            "query": {"term": {"uuid": GRASSLAND_UUID}},
            "_source": ["uuid", "resourceTitleObject", "link"],
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    hits = r.json()["hits"]["hits"]
    assert hits, f"uuid {GRASSLAND_UUID} not found — record withdrawn or re-issued?"

    source = hits[0]["_source"]
    assert source["uuid"] == GRASSLAND_UUID, f"got uuid {source['uuid']!r}"

    # cmd_links() filters link[] on these protocols. A record with no
    # OGC/ESRI link is useless for unauthenticated access.
    protocols = {
        link.get("protocol")
        for link in (source.get("link") or [])
        if isinstance(link, dict)
    }
    assert protocols & {"OGC:WMS", "OGC:WFS", "OGC:WCS", "ESRI:REST", "OGC:WMTS"}, (
        f"grassland record exposes no OGC/ESRI links; protocols={sorted(p for p in protocols if p)}"
    )


def test_record_iso_xml_is_served(http):
    """`cmd_xml()` — the ISO 19115 formatter, the only working full-record GET."""
    url = RECORD_XML.format(uuid=GRASSLAND_UUID)
    r = http.get(url, headers={"Accept": "application/xml"})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert "xml" in r.headers.get("content-type", "").lower(), (
        r.headers.get("content-type")
    )

    body = r.text
    assert "MD_Metadata" in body, f"not an ISO 19115 document: {body[:200]}"
    assert GRASSLAND_UUID in body, "XML does not reference the requested uuid"

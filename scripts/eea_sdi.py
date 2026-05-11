"""EEA Spatial Data Infrastructure (SDI) catalogue client.

Reads the European Environment Agency's geospatial-data catalogue at
``https://sdi.eea.europa.eu/catalogue/`` (a GeoNetwork 4.4 instance).
See ``.claude/skills/eea_sdi.md`` for the full API documentation.

Subcommands::

    eea_sdi.py search "grassland" [--iceland] [--size 20]
    eea_sdi.py record <uuid>
    eea_sdi.py links  <uuid>                # only OGC/ESRI links
    eea_sdi.py xml    <uuid> [-o out.xml]   # full ISO 19115 XML
    eea_sdi.py thumbnail <uuid> [-o out.png]

Auth is not required for any of these endpoints.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE = "https://sdi.eea.europa.eu/catalogue"
SEARCH = f"{BASE}/srv/api/search/records/_search"
RECORD_XML = f"{BASE}/srv/api/records/{{uuid}}/formatters/xml"
THUMBNAIL = "https://sdi.eea.europa.eu/public/catalogue-graphic-overview/{uuid}.png"
META_PAGE = f"{BASE}/srv/eng/catalog.search#/metadata/{{uuid}}"

ICELAND_BBOX = [[-25.0, 67.0], [-13.0, 63.0]]  # [[w,n],[e,s]] — note the order!

DEFAULT_SOURCE_FIELDS = [
    "uuid",
    "metadataIdentifier",
    "resourceTitleObject",
    "resourceAbstractObject",
    "OrgForResourceObject",
    "cl_resourceScope",
    "cl_topic",
    "inspireTheme",
    "publicationYearForResource",
    "link",
    "geom",
    "recordLink_children_uuid",
    "agg_associated",
]


# ── HTTP helpers ─────────────────────────────────────────────────────────

def _post(url: str, body: dict, *, timeout: float = 60.0) -> dict:
    r = httpx.post(url, json=body, timeout=timeout, follow_redirects=True,
                   headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def _get(url: str, *, params: dict | None = None, timeout: float = 60.0,
         accept: str = "application/json") -> httpx.Response:
    r = httpx.get(url, params=params, timeout=timeout, follow_redirects=True,
                  headers={"Accept": accept})
    r.raise_for_status()
    return r


# ── search ───────────────────────────────────────────────────────────────

def search(query: str | None, *, iceland: bool = False, size: int = 20,
           offset: int = 0, source_fields: list[str] | None = None) -> dict:
    """Run the Elasticsearch /_search endpoint."""
    must: list[dict] = []
    if query:
        must.append({"multi_match": {
            "query": query,
            "fields": [
                "resourceTitleObject.langeng^3",
                "resourceTitleObject.default^3",
                "resourceAbstractObject.langeng",
                "resourceAbstractObject.default",
                "allKeywords",
            ],
        }})
    filters: list[dict] = []
    if iceland:
        filters.append({"geo_shape": {
            "geom": {
                "shape": {"type": "envelope", "coordinates": ICELAND_BBOX},
                "relation": "intersects",
            },
        }})
    body = {
        "from": offset,
        "size": size,
        "query": {"bool": {"must": must or [{"match_all": {}}],
                          "filter": filters}},
        "_source": source_fields or DEFAULT_SOURCE_FIELDS,
    }
    return _post(SEARCH, body)


def _link_url(ln: dict) -> str:
    if "urlObject" in ln and ln["urlObject"]:
        return ln["urlObject"].get("default") or ""
    return ln.get("url", "") or ""


def _link_name(ln: dict) -> str:
    if "nameObject" in ln and ln["nameObject"]:
        return ln["nameObject"].get("default") or ""
    return ln.get("name", "") or ""


def cmd_search(args: argparse.Namespace) -> None:
    res = search(args.query, iceland=args.iceland, size=args.size,
                 offset=args.offset)
    total = res["hits"]["total"]["value"]
    hits = res["hits"]["hits"]
    print(f"  total matches: {total:,}    showing {len(hits)}",
          file=sys.stderr)
    for h in hits:
        s = h["_source"]
        title = (s.get("resourceTitleObject") or {}).get("default", "—")
        scope_list = s.get("cl_resourceScope") or [{}]
        scope = scope_list[0].get("key", "?") if scope_list else "?"
        year = s.get("publicationYearForResource") or "—"
        link_protocols = sorted({
            ln.get("protocol", "")
            for ln in (s.get("link") or [])
            if isinstance(ln, dict) and ln.get("protocol")
        })
        proto_str = ",".join(link_protocols) if link_protocols else "no-links"
        print(f"  {s.get('uuid'):36}  [{scope:>7}] {year}  {title}")
        print(f"  {'':36}    {proto_str}")


# ── record ───────────────────────────────────────────────────────────────

def fetch_record(uuid: str) -> dict:
    res = search(None, size=1, source_fields=None)  # placeholder
    # Use a term filter on uuid
    body = {
        "size": 1,
        "query": {"term": {"uuid": uuid}},
    }
    res = _post(SEARCH, body)
    hits = res["hits"]["hits"]
    if not hits:
        raise SystemExit(f"no record found with uuid={uuid}")
    return hits[0]["_source"]


def cmd_record(args: argparse.Namespace) -> None:
    s = fetch_record(args.uuid)
    title = (s.get("resourceTitleObject") or {}).get("default", "—")
    abstract = (s.get("resourceAbstractObject") or {}).get("default", "")
    org = (s.get("OrgForResourceObject") or [{}])[0].get("default", "—")
    year = s.get("publicationYearForResource") or "—"
    inspire = ", ".join(s.get("inspireTheme") or [])
    children = s.get("recordLink_children_uuid") or []

    print(f"Title : {title}")
    print(f"UUID  : {s.get('uuid')}")
    print(f"Org   : {org}")
    print(f"Year  : {year}")
    print(f"INSPIRE themes : {inspire}")
    if children:
        print(f"Children ({len(children)}):")
        for c in children:
            print(f"  - {c}")
    print(f"\nAbstract:\n  {abstract}\n")
    print("Links:")
    for ln in s.get("link") or []:
        if not isinstance(ln, dict):
            continue
        proto = ln.get("protocol", "")
        url = _link_url(ln)
        name = _link_name(ln)
        print(f"  [{proto:>22}]  {url}")
        if name:
            print(f"  {'':22}    name: {name}")
    print(f"\nMetadata page : {META_PAGE.format(uuid=s['uuid'])}")
    print(f"Thumbnail     : {THUMBNAIL.format(uuid=s['uuid'])}")


def cmd_links(args: argparse.Namespace) -> None:
    """Print only OGC / ESRI service links — the no-auth programmatic ones."""
    s = fetch_record(args.uuid)
    interesting = ("OGC:WMS", "OGC:WFS", "OGC:WCS", "ESRI:REST", "OGC:WMTS")
    for ln in s.get("link") or []:
        if not isinstance(ln, dict):
            continue
        proto = ln.get("protocol", "")
        if proto not in interesting:
            continue
        print(f"{proto}\t{_link_url(ln)}")


# ── XML / thumbnail ──────────────────────────────────────────────────────

def cmd_xml(args: argparse.Namespace) -> None:
    r = _get(RECORD_XML.format(uuid=args.uuid), accept="application/xml")
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        print(f"Wrote {out}  ({len(r.content) / 1024:.1f} KB)",
              file=sys.stderr)
    else:
        sys.stdout.write(r.text)


def cmd_thumbnail(args: argparse.Namespace) -> None:
    r = _get(THUMBNAIL.format(uuid=args.uuid), accept="image/png")
    out = Path(args.output) if args.output else Path(f"{args.uuid}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"Wrote {out}  ({len(r.content) / 1024:.1f} KB)", file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("search", help="search the catalogue")
    s.add_argument("query", help="free-text query, e.g. 'grassland'")
    s.add_argument("--iceland", action="store_true",
                   help="restrict to records intersecting Iceland's bbox")
    s.add_argument("--size", type=int, default=20,
                   help="page size (default 20, max 1000)")
    s.add_argument("--offset", type=int, default=0,
                   help="result offset (paginate with --size)")
    s.set_defaults(fn=cmd_search)

    r = sp.add_parser("record", help="print one record's full metadata")
    r.add_argument("uuid")
    r.set_defaults(fn=cmd_record)

    l = sp.add_parser("links",
                      help="print only OGC/ESRI service URLs from a record")
    l.add_argument("uuid")
    l.set_defaults(fn=cmd_links)

    x = sp.add_parser("xml", help="download ISO 19115 XML for one record")
    x.add_argument("uuid")
    x.add_argument("-o", "--output", help="output file (default: stdout)")
    x.set_defaults(fn=cmd_xml)

    t = sp.add_parser("thumbnail", help="download a record's preview PNG")
    t.add_argument("uuid")
    t.add_argument("-o", "--output", help="output file (default: <uuid>.png)")
    t.set_defaults(fn=cmd_thumbnail)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

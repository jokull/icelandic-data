"""Náttúrufræðistofnun open-data fetcher.

Pulls habitat-type ("vistgerðir") polygons from NÍ's GeoServer WFS at
``https://gis.natt.is/geoserver/`` and caches them on disk.

The vector layer ``LMI_vektor:vistgerd`` is the polygonised version of the
1:25.000 3rd-edition habitat raster ``ni_vg25r_3utg``. Each row carries an
integer ``DN`` raster code and a human-readable ``htxt`` label, e.g.
``"L14.2 Tún og akurlendi"`` (cultivated hayfield + arable land).

CLI:

    # download a single habitat type by DN code (default: L14.2 = 95)
    uv run python scripts/natt.py habitat --dn 95

    # ...or by L-code
    uv run python scripts/natt.py habitat --code L14.2

    # list all DN codes seen in the layer
    uv run python scripts/natt.py inventory

Output:
    data/raw/natt/vistgerdir/<L-code>__<slug>.geojson   (EPSG:3057)
    data/raw/natt/vistgerdir/inventory.csv              (DN -> htxt map)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

WFS = "https://gis.natt.is/geoserver/wfs"
LAYER = "LMI_vektor:vistgerd"
RAW = Path("data/raw/natt/vistgerdir")


def _wfs_get(params: dict, *, timeout: float = 120.0) -> httpx.Response:
    q = {"service": "WFS", "version": "2.0.0", **params}
    r = httpx.get(WFS, params=q, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r


def hits(cql: str | None = None) -> int:
    p = {"request": "GetFeature", "typeNames": LAYER, "resultType": "hits"}
    if cql:
        p["CQL_FILTER"] = cql
    r = _wfs_get(p, timeout=60)
    m = re.search(r'numberMatched="(\d+)"', r.text)
    if not m:
        raise RuntimeError(f"no numberMatched in WFS response: {r.text[:200]}")
    return int(m.group(1))


def fetch(cql: str, *, srs: str = "EPSG:3057") -> dict:
    """Fetch a (possibly large) GeoJSON FeatureCollection. WFS 2.0 caps results
    so we page with startIndex/count if needed."""
    page = 50000
    total = hits(cql)
    print(f"  WFS reports {total:,} matches for {cql!r}", file=sys.stderr)
    feats: list[dict] = []
    start = 0
    while start < total:
        p = {
            "request": "GetFeature",
            "typeNames": LAYER,
            "outputFormat": "application/json",
            "srsName": srs,
            "CQL_FILTER": cql,
            "count": str(page),
            "startIndex": str(start),
        }
        r = _wfs_get(p, timeout=300)
        chunk = r.json()
        got = chunk.get("features", [])
        feats.extend(got)
        print(f"    page {start:>7,}-{start + len(got):>7,} / {total:,}",
              file=sys.stderr)
        if not got:
            break
        start += len(got)
    return {
        "type": "FeatureCollection",
        "name": LAYER,
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:{srs}"}},
        "features": feats,
    }


def inventory() -> list[tuple[int, str]]:
    """Stream attributes (no geometry) and dedupe DN -> htxt."""
    seen: dict[int, str] = {}
    page = 100000
    start = 0
    while True:
        p = {
            "request": "GetFeature",
            "typeNames": LAYER,
            "propertyName": "DN,htxt",
            "outputFormat": "application/json",
            "count": str(page),
            "startIndex": str(start),
        }
        r = _wfs_get(p, timeout=300)
        chunk = r.json()
        got = chunk.get("features", [])
        if not got:
            break
        for f in got:
            props = f.get("properties") or {}
            dn = props.get("DN")
            ht = props.get("htxt")
            if dn is not None and ht and dn not in seen:
                seen[dn] = ht
        print(f"    inventoried {start + len(got):,} rows, {len(seen)} distinct DN",
              file=sys.stderr)
        if len(got) < page:
            break
        start += len(got)
    return sorted(seen.items())


def _slug(s: str) -> str:
    s = s.lower()
    repl = {"á": "a", "ð": "d", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "ý": "y", "þ": "th", "æ": "ae", "ö": "o"}
    for k, v in repl.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def cmd_habitat(args: argparse.Namespace) -> None:
    if args.code:
        cql = f"htxt LIKE '{args.code}%'"
        label_hint = args.code
    elif args.dn is not None:
        cql = f"DN={args.dn}"
        label_hint = f"DN{args.dn}"
    else:
        raise SystemExit("pass --code (e.g. L14.2) or --dn (e.g. 95)")
    fc = fetch(cql)
    if not fc["features"]:
        raise SystemExit(f"no features matched {cql!r}")
    htxt = fc["features"][0]["properties"].get("htxt") or label_hint
    code = htxt.split()[0]
    rest = htxt[len(code):].strip()
    out = RAW / f"{code}__{_slug(rest)}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(fc['features']):,} features ({htxt}) to {out}",
          file=sys.stderr)


def cmd_inventory(_: argparse.Namespace) -> None:
    pairs = inventory()
    out = RAW / "inventory.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DN", "htxt"])
        w.writerows(pairs)
    print(f"Wrote {len(pairs)} DN→htxt rows to {out}", file=sys.stderr)
    for dn, ht in pairs:
        print(f"  DN={dn:>4}  {ht}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    h = sp.add_parser("habitat", help="download polygons for one habitat type")
    g = h.add_mutually_exclusive_group(required=True)
    g.add_argument("--dn", type=int, help="raster code, e.g. 95 = L14.2")
    g.add_argument("--code", help="L-code prefix, e.g. L14.2")
    h.set_defaults(fn=cmd_habitat)

    inv = sp.add_parser("inventory", help="dump DN→htxt mapping")
    inv.set_defaults(fn=cmd_inventory)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

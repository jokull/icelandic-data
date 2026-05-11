"""LMI High-Resolution Layer fetcher (Copernicus HRL Iceland 2015).

Downloads raster layers (Grassland, Tree Cover Density, Imperviousness,
Water and Wetness, Dominant Leaf Type) from LMI's GeoServer WCS.

Native format is GeoTIFF in EPSG:5325 (LAEA Iceland) at 20 m resolution.
Pixel encoding for the Grassland layer:

    0    = non-grassland (within Iceland mask)
    1    = grassland
    254  = unclassifiable / cloud / no-data inside Iceland
    255  = outside Iceland mask (NoData fill)

Reference metadata (UUID 58e1ed85-df4d-408d-a34f-d0a60628cb34):
    https://gatt.lmi.is/geonetwork/srv/eng/catalog.search#/metadata/58e1ed85-df4d-408d-a34f-d0a60628cb34

CLI:
    # full-resolution 20 m GeoTIFF (~120 MB compressed for grassland)
    uv run python scripts/lmi_hrl.py fetch grassland

    # downsampled to 100 m (faster, ~33 MB)
    uv run python scripts/lmi_hrl.py fetch grassland --scale 0.2

    # list known coverages
    uv run python scripts/lmi_hrl.py list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

WCS = "https://gis.lmi.is/geoserver/High_Resolution_Layer/wcs"
RAW = Path("data/raw/lmi_hrl")

COVERAGES = {
    "grassland": "High_Resolution_Layer__Grassland",
    "tree_cover": "High_Resolution_Layer__Tree_Cover_Density",
    "imperviousness": "High_Resolution_Layer__Imperviousness",
    "water_wetness": "High_Resolution_Layer__Water_and_Wetness",
    "dominant_leaf": "High_Resolution_Layer__Dominant_Leaf_Type",
}


def fetch(coverage: str, *, out: Path, scale: float | None = None) -> None:
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": coverage,
        "format": "image/tiff",
    }
    if scale is not None:
        params["scaleFactor"] = str(scale)
    out.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", WCS, params=params, timeout=600.0,
                      follow_redirects=True) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "tiff" not in ctype.lower():
            body = r.read()
            raise RuntimeError(
                f"unexpected content-type {ctype!r}: {body[:300]!r}")
        total = 0
        with out.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 16):
                f.write(chunk)
                total += len(chunk)
                print(f"\r  ...{total / 1e6:>7.1f} MB",
                      end="", file=sys.stderr)
        print(file=sys.stderr)
    print(f"Wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> None:
    if args.layer not in COVERAGES:
        raise SystemExit(
            f"unknown layer {args.layer!r}; choose from {sorted(COVERAGES)}")
    cov = COVERAGES[args.layer]
    suffix = f"_{int(20 / args.scale)}m" if args.scale else "_20m"
    out = args.output or RAW / f"{args.layer}{suffix}.tif"
    print(f"Fetching {cov} -> {out}", file=sys.stderr)
    fetch(cov, out=Path(out), scale=args.scale)


def cmd_list(_: argparse.Namespace) -> None:
    for name, cov in COVERAGES.items():
        print(f"  {name:>16}  ->  {cov}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    f = sp.add_parser("fetch", help="download one coverage as GeoTIFF")
    f.add_argument("layer", help="short name: " + ", ".join(COVERAGES))
    f.add_argument("--scale", type=float, default=None,
                   help="WCS scaleFactor (e.g. 0.2 -> 100 m, 0.5 -> 40 m)")
    f.add_argument("-o", "--output", help="output path (default: data/raw/lmi_hrl/...)")
    f.set_defaults(fn=cmd_fetch)

    l = sp.add_parser("list", help="list known coverages")
    l.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

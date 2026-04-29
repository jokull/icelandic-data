"""
Landmælingar Íslands geodata — download and cache WFS layers.

Data source: GeoServer WFS at gis.lmi.is
See .claude/skills/lmi.md for full API documentation.

Usage:
    uv run python scripts/lmi.py list              # Show available layers and cache status
    uv run python scripts/lmi.py download           # Download core layer bundle
    uv run python scripts/lmi.py fetch ERM:Landmask # Fetch a specific layer
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

WFS_BASE = "https://gis.lmi.is/geoserver/{workspace}/wfs"

GEODATA_DIR = Path(__file__).parent.parent / "data" / "geodata"

# Core layers to pre-download for mapmaking
CORE_LAYERS = {
    # (namespace:layer, description)
    "ERM:Landmask": "Iceland land polygon (base fill)",
    "ERM:CoastalLine": "Coastline",
    "ERM:AdministrativeAreas": "Admin areas (2713 small zones, code-based)",
    "EBM:AdministrativeUnit_level2": "Municipalities with names (128 sveitarfélög)",
    "ERM:RoadLines": "Road network with classification",
    "ERM:WatercourseLine": "Rivers and streams",
    "ERM:Lake_Reservoir": "Lakes and reservoirs",
    "ERM:LandIceArea": "Glaciers (jöklar)",
    "ERM:BuiltupAreaPoints": "Settlements with population",
    "ERM:BuiltupArea": "Urban area polygons",
    "ERM:NamedLocation_gnamel": "Place names (616 named locations)",
    "ERM:IslandArea": "Islands",
    "ERM:Airport_Airfield_points": "Airports",
    "ERM:Port": "Harbors",
    "ERM:NatureParkArea": "National parks and reserves",
}

# Extended layers available on demand
EXTRA_LAYERS = {
    "ERM:WetlandArea": "Wetlands",
    "ERM:VegetationArea": "Vegetation cover",
    "ERM:AdministrativeBoundaries": "Municipality boundary lines",
    "ERM:PowerTransmissionLine": "Power lines",
    "ERM:PowerTransmissionPoint": "Power stations",
    "ERM:SpringPoint": "Springs and geothermal",
    "ERM:WatercourseArea": "Wide river areas",
    "ERM:WaterfallLine": "Waterfalls",
    "ERM:PhysiographyPoint": "Mountain peaks and landforms",
    "ERM:SeaArea": "Sea areas",
    "ERM:ExtractionFacilities": "Quarries and mines",
    "ERM:HarborLines": "Harbor infrastructure",
    "ERM:Building": "Individual buildings",
    "ERM:FerryCrossing": "Ferry routes",
    "EBM:AdministrativeUnit_level1": "National boundary (EBM)",
    "EBM:AdministrativeUnit_level2": "Municipalities (EBM, alternate)",
    "LMI_vektor:landshlutar": "Regions of Iceland",
    "ni:ni_j600v_berg_2_jardlog_2utg_fl": "Bedrock geology 1:600k",
    "ni:ni_j600v_berg_2_brotalina_1utg_li": "Fault lines",
    "ni:ni_j600v_berg_2_gosspr_1utg_li": "Eruptive fissures",
    "ni:ni_j600v_berg_2_gigar_1utg_p": "Volcanic craters",
}


def layer_filename(layer: str) -> str:
    """Convert 'ERM:RoadLines' to 'RoadLines.geojson'."""
    return layer.split(":")[-1] + ".geojson"


def layer_workspace(layer: str) -> str:
    """Extract workspace from 'ERM:RoadLines' -> 'ERM'."""
    return layer.split(":")[0]


def fetch_layer(layer: str, output_path: Path) -> bool:
    """Download a single WFS layer as GeoJSON."""
    workspace = layer_workspace(layer)
    url = WFS_BASE.format(workspace=workspace)
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }

    try:
        resp = httpx.get(url, params=params, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  ERROR fetching {layer}: {e}")
        return False

    data = resp.json()
    features = data.get("features", [])
    if not features:
        print(f"  WARNING: {layer} returned 0 features")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  {layer:40s} {len(features):>6} features  {size_mb:>6.1f} MB")
    return True


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def cmd_list():
    """Show available layers and their cache status."""
    print("Core layers (pre-downloaded with 'download'):\n")
    print(f"  {'Layer':<42s} {'Cached':>8s}  Description")
    print(f"  {'-' * 42}  {'-' * 8}  {'-' * 40}")

    for layer, desc in CORE_LAYERS.items():
        path = GEODATA_DIR / layer_filename(layer)
        cached = "yes" if path.exists() else "—"
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            cached = f"{size_mb:.1f} MB"
        print(f"  {layer:<42s} {cached:>8s}  {desc}")

    print(f"\nExtra layers (fetch on demand with 'fetch <layer>'):\n")
    for layer, desc in EXTRA_LAYERS.items():
        path = GEODATA_DIR / layer_filename(layer)
        cached = "—"
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            cached = f"{size_mb:.1f} MB"
        print(f"  {layer:<42s} {cached:>8s}  {desc}")

    # Count cached files
    if GEODATA_DIR.exists():
        cached_files = list(GEODATA_DIR.glob("*.geojson"))
        total_size = sum(f.stat().st_size for f in cached_files) / (1024 * 1024)
        print(f"\nCached: {len(cached_files)} layers, {total_size:.1f} MB total")
    else:
        print("\nNo cached data yet. Run: uv run python scripts/lmi.py download")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

def cmd_download():
    """Download all core layers."""
    print(f"Downloading {len(CORE_LAYERS)} core layers to {GEODATA_DIR}/\n")
    GEODATA_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    for layer in CORE_LAYERS:
        path = GEODATA_DIR / layer_filename(layer)
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  {layer:40s} (cached, {size_mb:.1f} MB)")
            success += 1
            continue
        if fetch_layer(layer, path):
            success += 1

    total_size = sum(
        f.stat().st_size for f in GEODATA_DIR.glob("*.geojson")
    ) / (1024 * 1024)
    print(f"\nDone: {success}/{len(CORE_LAYERS)} layers, {total_size:.1f} MB total")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def cmd_fetch(layer: str):
    """Fetch a specific layer by name."""
    all_layers = {**CORE_LAYERS, **EXTRA_LAYERS}

    if layer not in all_layers and ":" not in layer:
        # Try to find by short name
        matches = [k for k in all_layers if k.split(":")[-1].lower() == layer.lower()]
        if matches:
            layer = matches[0]
        else:
            print(f"Unknown layer: {layer}")
            print(f"Use 'list' to see available layers, or pass a full WFS name like 'ERM:Landmask'")
            return

    path = GEODATA_DIR / layer_filename(layer)
    if path.exists():
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"Already cached: {path} ({size_mb:.1f} MB)")
        return

    print(f"Fetching {layer}...")
    GEODATA_DIR.mkdir(parents=True, exist_ok=True)
    fetch_layer(layer, path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Landmælingar Íslands geodata — download and cache WFS layers"
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list", help="Show available layers and cache status")
    sub.add_parser("download", help="Download all core layers")
    fetch_parser = sub.add_parser("fetch", help="Fetch a specific layer")
    fetch_parser.add_argument("layer", help="Layer name (e.g., ERM:WetlandArea)")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list()
    elif args.command == "download":
        cmd_download()
    elif args.command == "fetch":
        cmd_fetch(args.layer)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

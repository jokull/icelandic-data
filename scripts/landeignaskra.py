"""Landeignaskrá — HMS national land-parcel registry.

Downloads the ZIP from HMS, extracts it, and provides a parcel lookup by
landsnúmer.

The human-visible landing page
  https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/landeignaskrazip
is Vercel-guarded, but its download button points at a plain Azure blob which
is world-readable, so we fetch that directly with httpx. If HMS ever moves the
blob, run `landeignaskra.py discover` to re-scrape the landing page.

Crosswalk: Ministry of Agriculture búsnúmer (8 digits) → landsnúmer (7 digits)
by dropping the last digit. See .claude/skills/hms.md and
.claude/skills/maelabord_landbunadarins.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAW_DIR = Path("data/raw/landeignaskra")
ZIP_PATH = RAW_DIR / "landeignaskra.zip"
EXTRACT_DIR = RAW_DIR / "extracted"
PROCESSED = Path("data/processed/landeignaskra.csv")

LANDING_URL = "https://hms.is/gogn-og-maelabord/grunngogntilnidurhals/landeignaskrazip"
BLOB_URL = "https://hmsstgsftpprodweu001.blob.core.windows.net/fasteignaskra/Landeignaskra.zip"


def _download_httpx(url: str, dest: Path) -> None:
    import httpx
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        written = 0
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
                written += len(chunk)
                if total:
                    pct = written * 100 // total
                    print(f"\r  {written:,}/{total:,} bytes ({pct}%)", end="", file=sys.stderr)
        print(file=sys.stderr)


async def _discover_blob_url() -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.goto(LANDING_URL, wait_until="networkidle", timeout=120000)
        hrefs = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a')).map(a => a.href)"
        )
        await b.close()
    for h in hrefs:
        if h.lower().endswith(".zip") and "landeign" in h.lower():
            return h
    raise RuntimeError(f"No .zip link found on {LANDING_URL}; hrefs={hrefs}")


def cmd_download(args: argparse.Namespace) -> None:
    if ZIP_PATH.exists() and not args.force:
        size = ZIP_PATH.stat().st_size
        print(f"Already downloaded: {ZIP_PATH} ({size:,} bytes). Use --force to refresh.")
        return
    print(f"Downloading {BLOB_URL}…", file=sys.stderr)
    _download_httpx(BLOB_URL, ZIP_PATH)
    print(f"  saved: {ZIP_PATH} ({ZIP_PATH.stat().st_size:,} bytes)", file=sys.stderr)


def cmd_discover(args: argparse.Namespace) -> None:
    url = asyncio.run(_discover_blob_url())
    print(url)


def cmd_extract(args: argparse.Namespace) -> None:
    if not ZIP_PATH.exists():
        sys.exit(f"ZIP not found: {ZIP_PATH}. Run `download` first.")
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH) as z:
        print(f"Contents of {ZIP_PATH.name}:")
        for info in z.infolist():
            print(f"  {info.filename:60s} {info.file_size:>12,} bytes")
        z.extractall(EXTRACT_DIR)
    print(f"Extracted to {EXTRACT_DIR}")


def _pick_spatial_file() -> Path:
    """Find the first spatial file in extracted dir (SHP / GPKG / GeoJSON)."""
    if not EXTRACT_DIR.exists():
        sys.exit(f"Not extracted: {EXTRACT_DIR}. Run `extract` first.")
    candidates = sorted(
        [*EXTRACT_DIR.rglob("*.gpkg"),
         *EXTRACT_DIR.rglob("*.shp"),
         *EXTRACT_DIR.rglob("*.geojson"),
         *EXTRACT_DIR.rglob("*.json")]
    )
    if not candidates:
        sys.exit(f"No spatial files found in {EXTRACT_DIR}")
    return candidates[0]


def cmd_info(args: argparse.Namespace) -> None:
    import geopandas as gpd
    path = _pick_spatial_file()
    print(f"Reading: {path}")
    gdf = gpd.read_file(path, rows=5)
    print(f"CRS: {gdf.crs}")
    print(f"Columns: {list(gdf.columns)}")
    print(gdf.drop(columns="geometry", errors="ignore").head().to_string())


def _normalise(gdf):
    """Identify the landsnúmer column and normalise it to a 7-digit string.

    The shapefile uses LANDE_NR (landeigna-númer) — the official landsnúmer.
    """
    lower = {c.lower(): c for c in gdf.columns}
    for key in ("lande_nr", "landnr", "landsnr", "landnumer", "landsnumer",
                "landnúmer", "landsnúmer"):
        if key in lower:
            src = lower[key]
            gdf = gdf.rename(columns={src: "landsnr"})
            break
    else:
        raise SystemExit(f"Could not find landsnúmer column in {list(gdf.columns)}")
    gdf["landsnr"] = gdf["landsnr"].astype("string").str.extract(r"(\d+)", expand=False).str.zfill(7)
    return gdf


def cmd_build(args: argparse.Namespace) -> None:
    """Load full registry, compute parcel centroid, write parquet for fast lookup."""
    import geopandas as gpd
    path = _pick_spatial_file()
    print(f"Reading full registry from {path}…", file=sys.stderr)
    gdf = gpd.read_file(path)
    print(f"  {len(gdf):,} features, CRS={gdf.crs}", file=sys.stderr)
    gdf = _normalise(gdf)

    # Centroid in WGS84 for map plotting
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        c_wgs = gdf.geometry.to_crs(4326).centroid
    else:
        c_wgs = gdf.geometry.centroid
    gdf["lon"] = c_wgs.x
    gdf["lat"] = c_wgs.y

    cols = ["landsnr", "lon", "lat"]
    keep = [c for c in gdf.columns if c not in ("geometry",) and c not in cols]
    out = gdf[cols + keep].drop(columns="geometry", errors="ignore")

    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROCESSED, index=False, encoding="utf-8")
    print(f"Wrote {PROCESSED} ({len(out):,} rows, {len(out.columns)} cols)", file=sys.stderr)


def cmd_lookup(args: argparse.Namespace) -> None:
    import polars as pl
    if not PROCESSED.exists():
        sys.exit(f"Missing {PROCESSED}. Run `build` first.")
    df = pl.read_csv(PROCESSED, schema_overrides={"landsnr": pl.Utf8})
    ids = [str(x).zfill(7) for x in args.landsnr]
    hit = df.filter(pl.col("landsnr").is_in(ids))
    if hit.is_empty():
        sys.exit(f"No rows for {ids}")
    print(hit)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Download ZIP from Azure blob")
    d.add_argument("--force", action="store_true")
    d.set_defaults(func=cmd_download)

    disc = sub.add_parser("discover", help="Re-scrape landing page for current ZIP URL")
    disc.set_defaults(func=cmd_discover)

    e = sub.add_parser("extract", help="Extract ZIP contents")
    e.set_defaults(func=cmd_extract)

    i = sub.add_parser("info", help="Show schema of extracted file")
    i.set_defaults(func=cmd_info)

    b = sub.add_parser("build", help="Build processed parquet with landsnr + lon/lat")
    b.set_defaults(func=cmd_build)

    l = sub.add_parser("lookup", help="Look up one or more landsnúmer")
    l.add_argument("landsnr", nargs="+")
    l.set_defaults(func=cmd_lookup)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

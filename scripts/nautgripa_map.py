"""Map cattle subsidy (Nautgriparæktarsamningur) recipients.

Pipeline (end-to-end smoke test of the búsnúmer → landsnúmer conversion):

  1. Read recipients from data/processed/nautgripa_recipients.csv
     (produced by scripts/maelabord_nautgripa.py fetch).
  2. Convert busnr → landsnr by integer-dividing by 10.
  3. Look up landsnr in iceaddr's Staðfangaskrá (SQLite, bundled with the
     `iceaddr` package) to get WGS84 lat/lon. Staðfangaskrá covers ~138k
     historical landnúmer, whereas HMS Landeignaskrá only has formally
     surveyed parcels (~89k, ~3.4k of which are JÖRÐ), so the HMS registry
     misses many farms — iceaddr is the pragmatic map source.
  4. Render a static PNG over the cached LMI landmask + a single-file HTML
     with Leaflet.

Output: reports/nautgripa-map.png, reports/nautgripa-map.html
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RECIPIENTS_CSV = Path("data/processed/nautgripa_recipients.csv")
GEODATA = Path("data/geodata")

OUT_PNG = Path("reports/nautgripa-map.png")
OUT_HTML = Path("reports/nautgripa-map.html")


# ---------------------------------------------------------------------------
# Geocoding via iceaddr SQLite (búsnúmer // 10 = landsnúmer = stadfong.landnr)
# ---------------------------------------------------------------------------

def _iceaddr_db_path() -> Path:
    import iceaddr
    return Path(iceaddr.__file__).parent / "iceaddr.db"


def geocode(df: pl.DataFrame) -> pl.DataFrame:
    """Join búsnúmer (via landsnúmer) to lat/lon from iceaddr.

    When multiple staðfang rows share a landnr, we take the one whose heiti_nf
    matches the farm's name, else the first. Some landnúmer are unknown to
    iceaddr (e.g. brand-new farms) and come out with null coordinates.
    """
    conn = sqlite3.connect(_iceaddr_db_path())
    cur = conn.cursor()
    matched: list[dict] = []
    misses = 0
    for row in df.iter_rows(named=True):
        landsnr = int(row["landsnr"])
        cur.execute(
            """SELECT landnr, heiti_nf, lat_wgs84, long_wgs84, postnr, svfnr
                 FROM stadfong WHERE landnr = ?""",
            (landsnr,),
        )
        hits = cur.fetchall()
        if not hits:
            misses += 1
            row["lat"] = None
            row["lon"] = None
            row["iceaddr_heiti"] = None
            row["postnr"] = None
            matched.append(row)
            continue
        # Prefer exact name match, then first
        wanted = (row.get("nafn") or "").split()[0].lower()
        best = next(
            (h for h in hits if (h[1] or "").lower().startswith(wanted)),
            hits[0],
        )
        _, heiti, lat, lon, postnr, _svfnr = best
        row["lat"] = lat
        row["lon"] = lon
        row["iceaddr_heiti"] = heiti
        row["postnr"] = postnr
        matched.append(row)
    conn.close()
    print(f"  geocoded {len(matched) - misses}/{len(matched)} ({misses} missing)",
          file=sys.stderr)
    return pl.DataFrame(matched)


# ---------------------------------------------------------------------------
# Static matplotlib map
# ---------------------------------------------------------------------------

def render_static(df: pl.DataFrame, out: Path) -> None:
    import geopandas as gpd
    import matplotlib.pyplot as plt

    land = gpd.read_file(GEODATA / "Landmask.geojson")
    glaciers = gpd.read_file(GEODATA / "LandIceArea.geojson")
    lakes = gpd.read_file(GEODATA / "Lake_Reservoir.geojson")

    hit = df.filter(pl.col("lat").is_not_null())
    lons = hit["lon"].to_list()
    lats = hit["lat"].to_list()
    sizes = hit["nautgripa_upphaed"].to_list()
    # sqrt sizing so a 15M farm isn't 1000× bigger than a 50k one
    max_val = max(sizes) or 1
    point_size = [max(8, 220 * (v / max_val) ** 0.5) for v in sizes]
    total = sum(sizes)
    n = len(hit)

    fig, ax = plt.subplots(figsize=(13, 9), facecolor="#f0f4f8")
    ax.set_facecolor("#c8d6e5")
    land.plot(ax=ax, color="#f5f0e6", edgecolor="#2d3436", linewidth=0.6)
    glaciers.plot(ax=ax, color="#dfe6e9", edgecolor="#b2bec3", linewidth=0.2)
    lakes.plot(ax=ax, color="#74b9ff", edgecolor="#0984e3", linewidth=0.2)
    ax.scatter(lons, lats, s=point_size, c="#c0392b", alpha=0.55,
               edgecolor="#6b1f15", linewidth=0.5, zorder=10)

    ax.set_xlim(-24.7, -13.1)
    ax.set_ylim(63.2, 66.6)
    ax.set_aspect(1 / 0.42)
    ax.set_axis_off()

    ax.set_title(
        f"Nautgriparæktarsamningur — greiðsluár 2026\n"
        f"{n:,} bú • {total:,.0f} kr. samtals • stærð punkts = upphæð",
        fontsize=14, pad=14,
    )

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Interactive Leaflet map (single file, no build step)
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="is"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nautgriparæktarsamningur — greiðsluár 2026</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
  body{{margin:0;background:#0f172a;color:#e2e8f0}}
  #header{{padding:16px 20px;background:#111827;border-bottom:1px solid #1f2937}}
  h1{{margin:0 0 4px;font-size:17px;font-weight:600}}
  #meta{{font-size:13px;color:#94a3b8}}
  #map{{position:absolute;top:72px;bottom:0;left:0;right:0}}
  .legend{{background:rgba(15,23,42,.9);color:#e2e8f0;padding:10px 12px;border-radius:8px;font-size:12px;line-height:1.5}}
  .legend b{{color:#fff}}
</style>
</head><body>
<div id="header">
  <h1>Nautgriparæktarsamningur — þiggjendur greiðslu 2026</h1>
  <div id="meta">{n_farms} bú • {total_isk} kr. samtals • {n_geocoded} staðsett</div>
</div>
<div id="map"></div>
<script>
const data = {points_json};
const map = L.map('map',{{zoomSnap:0.25}}).setView([64.9,-18.5],6.6);
L.tileLayer('https://cartodb-basemaps-{{s}}.global.ssl.fastly.net/light_all/{{z}}/{{x}}/{{y}}.png',{{
  attribution:'&copy; OSM &copy; CARTO',maxZoom:18
}}).addTo(map);
const max = Math.max(...data.map(d=>d.v));
for(const d of data){{
  const r = Math.max(4, 22*Math.sqrt(d.v/max));
  L.circleMarker([d.lat,d.lon],{{
    radius:r,color:'#6b1f15',weight:1,fillColor:'#c0392b',fillOpacity:0.6
  }})
  .bindPopup(
    `<b>${{d.n}}</b><br>bú nr. ${{d.b}} &middot; land nr. ${{d.l}}<br>`+
    `nautgriparækt: <b>${{d.v.toLocaleString('is-IS')}} kr.</b><br>`+
    (d.c?`nautgripir: ${{d.c.toLocaleString('is-IS')}}<br>`:'')+
    `heildarfjárhæð: ${{d.t.toLocaleString('is-IS')}} kr.`
  )
  .addTo(map);
}}
const legend = L.control({{position:'bottomright'}});
legend.onAdd = () => {{
  const div = L.DomUtil.create('div','legend');
  div.innerHTML = '<b>Heimildir</b><br>Mælaborð landbúnaðarins (PBI) · HMS Landeignaskrá · iceaddr';
  return div;
}};
legend.addTo(map);
</script>
</body></html>
"""


def render_html(df: pl.DataFrame, out: Path) -> None:
    hit = df.filter(pl.col("lat").is_not_null())
    points = [
        {
            "b": int(r["busnr"]),
            "l": int(r["landsnr"]),
            "n": r["nafn"],
            "lat": r["lat"],
            "lon": r["lon"],
            "v": int(r["nautgripa_upphaed"] or 0),
            "t": int(r["total_upphaed"] or 0),
            "c": int(r["nautgripir"]) if r.get("nautgripir") else None,
        }
        for r in hit.iter_rows(named=True)
    ]
    n_farms = len(df)
    n_geocoded = len(hit)
    total = int(df["nautgripa_upphaed"].sum() or 0)
    html = HTML_TEMPLATE.format(
        n_farms=f"{n_farms:,}",
        n_geocoded=f"{n_geocoded:,}",
        total_isk=f"{total:,}",
        points_json=json.dumps(points, ensure_ascii=False),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recipients", type=Path, default=RECIPIENTS_CSV)
    ap.add_argument("--png", type=Path, default=OUT_PNG)
    ap.add_argument("--html", type=Path, default=OUT_HTML)
    ap.add_argument("--skip-png", action="store_true")
    ap.add_argument("--skip-html", action="store_true")
    args = ap.parse_args()

    df = pl.read_csv(args.recipients,
                     schema_overrides={"busnr": pl.Utf8, "landsnr": pl.Utf8})
    df = df.with_columns(
        pl.col("landsnr").cast(pl.Int64),
        pl.col("nautgripa_upphaed").cast(pl.Int64, strict=False),
        pl.col("total_upphaed").cast(pl.Int64, strict=False),
    )
    print(f"Loaded {len(df)} recipients from {args.recipients}", file=sys.stderr)

    geo = geocode(df)
    # Report which postnumer cluster has most
    if geo.filter(pl.col("postnr").is_not_null()).height:
        top_post = (
            geo.filter(pl.col("postnr").is_not_null())
            .group_by("postnr")
            .agg(pl.col("nautgripa_upphaed").sum().alias("isk"), pl.len().alias("n"))
            .sort("isk", descending=True)
            .head(5)
        )
        print("Top postnúmer by cattle subsidy:", file=sys.stderr)
        for r in top_post.iter_rows(named=True):
            print(f"  {r['postnr']}: {r['n']} bú · {r['isk']:,} kr.", file=sys.stderr)

    if not args.skip_png:
        render_static(geo, args.png)
    if not args.skip_html:
        render_html(geo, args.html)


if __name__ == "__main__":
    main()

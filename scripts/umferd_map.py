"""
Map of Iceland with Vegagerðin traffic counters — volume visualization.

Counters are colored and sized by daily traffic volume using a log-scale
gradient from cool (low) to hot (high). The road network provides context.
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from matplotlib.cm import ScalarMappable
from pathlib import Path
import numpy as np
import polars as pl

GEODATA = Path(__file__).parent.parent / "data" / "geodata"
PROCESSED = Path(__file__).parent.parent / "data" / "processed"
OUT = Path(__file__).parent.parent / "reports" / "umferd-map.png"

C = {
    "ocean":       "#d6e4f0",
    "land":        "#f7f5f0",
    "land_edge":   "#888880",
    "glacier":     "#eaeef3",
    "glacier_edge":"#c0c8d2",
    "lake":        "#b8d0e4",
    "lake_edge":   "#7aa4c4",
    "road_ring":   "#a09888",
    "road_casing": "#857d72",
    "road_major":  "#c4baa8",
    "road_minor":  "#dad4c8",
    "label":       "#2a2a2a",
    "halo":        "#f7f5f0",
    "frame":       "#3a3a35",
    "grid":        "#dddbd4",
    "town":        "#555550",
}


def halo(color=None, width=2.5):
    c = color or C["halo"]
    return [pe.withStroke(linewidth=width, foreground=c)]


def main():
    # --- Load layers ---
    land     = gpd.read_file(GEODATA / "Landmask.geojson")
    islands  = gpd.read_file(GEODATA / "IslandArea.geojson")
    glaciers = gpd.read_file(GEODATA / "LandIceArea.geojson")
    lakes    = gpd.read_file(GEODATA / "Lake_Reservoir.geojson")
    roads    = gpd.read_file(GEODATA / "RoadLines.geojson")
    towns    = gpd.read_file(GEODATA / "BuiltupAreaPoints.geojson")

    # --- Traffic data: deduplicate to one row per station ---
    df = pl.read_csv(PROCESSED / "umferd_snapshot.csv")

    combined = df.filter(pl.col("stefna").str.contains("(?i)samanlögð|samanlagð|samanlög"))
    directional = df.filter(~pl.col("stefna").str.contains("(?i)samanlögð|samanlagð|samanlög"))
    combined_ids = set(combined["idstod"].to_list())
    dir_extra = (
        directional
        .filter(~pl.col("idstod").is_in(list(combined_ids)))
        .group_by("idstod")
        .agg(
            pl.col("nafn").first(),
            pl.col("umf_i_dag").sum(),
            pl.col("maelistod_tegund").first(),
            pl.col("lon").first(),
            pl.col("lat").first(),
        )
    )
    stations = pl.concat([
        combined.select("idstod", "nafn", "umf_i_dag", "maelistod_tegund", "lon", "lat"),
        dir_extra.select("idstod", "nafn", "umf_i_dag", "maelistod_tegund", "lon", "lat"),
    ])

    # --- Figure ---
    W, S, E, N = -25.2, 63.15, -12.8, 66.65
    LAT_CORR = 1 / 0.42
    fig_w = 20
    fig_h = fig_w / ((E - W) * 0.42 / (N - S))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=C["ocean"])
    ax.set_facecolor(C["ocean"])

    # --- Base map (subdued to let counters pop) ---
    land.plot(ax=ax, color=C["land"], edgecolor=C["land_edge"], linewidth=0.4, zorder=2)
    islands.plot(ax=ax, color=C["land"], edgecolor=C["land_edge"], linewidth=0.3, zorder=2)
    glaciers.plot(ax=ax, color=C["glacier"], edgecolor=C["glacier_edge"], linewidth=0.2, zorder=3)
    lakes.plot(ax=ax, color=C["lake"], edgecolor=C["lake_edge"], linewidth=0.15, zorder=4)

    # Full road network — subdued
    ring_road = roads[roads["rtn"] == "1"]
    major_roads = roads[(roads["rtt"].isin([14])) & (roads["rtn"] != "1")]
    minor_roads = roads[roads["rtt"].isin([15, 984, -32768])]

    minor_roads.plot(ax=ax, color=C["road_minor"], linewidth=0.2, alpha=0.5, zorder=5)
    major_roads.plot(ax=ax, color=C["road_major"], linewidth=0.45, alpha=0.6, zorder=6)
    ring_road.plot(ax=ax, color=C["road_casing"], linewidth=1.3, zorder=7)
    ring_road.plot(ax=ax, color=C["road_ring"], linewidth=0.7, zorder=8)

    # --- Settlements (25 largest) ---
    top_towns = towns.sort_values("ppl", ascending=False).head(25)
    town_pops = top_towns["ppl"].values.astype(float)
    town_sizes = 6 + 40 * np.sqrt(town_pops / town_pops.max())
    top_towns.plot(ax=ax, color=C["town"], markersize=town_sizes,
                   edgecolor="white", linewidth=0.5, zorder=9, marker="s")

    SKIP_LABELS = {"Álftanes", "Seltjarnarnes", "Garðabær"}
    TOWN_NUDGE = {
        "Reykjavík":           (-7,   5,  "right"),
        "Kópavogur":           (5,   -6,  "left"),
        "Hafnarfjörður":       (-6,  -6,  "right"),
        "Keflavík og Njarðvík":(0,   -8,  "center"),
        "Mosfellsbær":         (5,    3,  "left"),
    }
    for _, row in top_towns.iterrows():
        name = row["namn1"]
        if name in SKIP_LABELS:
            continue
        display = "Reykjanesbær" if name == "Keflavík og Njarðvík" else name
        dx, dy, ha = TOWN_NUDGE.get(name, (5, 3, "left"))
        fs = 6.5 if row["ppl"] > 15000 else 5
        ax.annotate(display, xy=(row.geometry.x, row.geometry.y),
                    xytext=(dx, dy), textcoords="offset points",
                    fontsize=fs, color=C["town"], fontweight="bold",
                    ha=ha, va="center",
                    path_effects=halo(width=2), zorder=10)

    # --- Traffic counters: volume heatmap ---
    lons = stations["lon"].to_numpy()
    lats = stations["lat"].to_numpy()
    counts = stations["umf_i_dag"].fill_null(0).to_numpy().astype(float)

    # Log-scale normalization (add 1 to handle zeros)
    log_counts = np.log10(counts + 1)
    vmin, vmax = 0, np.log10(60000)  # 0 to ~60k range
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # Custom colormap: blue → cyan → yellow → orange → red
    cmap_colors = ["#3b5998", "#2980b9", "#1abc9c", "#f1c40f", "#e67e22", "#c0392b", "#8e1a1a"]
    cmap = mcolors.LinearSegmentedColormap.from_list("traffic", cmap_colors, N=256)

    # Size: sqrt scale, generous range
    max_count = max(counts.max(), 1)
    sizes = 18 + 350 * np.sqrt(counts / max_count)

    # Sort by count so large dots are drawn on top
    order = np.argsort(counts)
    lons_s, lats_s = lons[order], lats[order]
    counts_s, log_s, sizes_s = counts[order], log_counts[order], sizes[order]

    # Outer glow
    ax.scatter(lons_s, lats_s, s=sizes_s * 1.8, c=log_s, cmap=cmap, norm=norm,
               alpha=0.10, edgecolors="none", zorder=11)
    # Mid glow
    ax.scatter(lons_s, lats_s, s=sizes_s * 1.25, c=log_s, cmap=cmap, norm=norm,
               alpha=0.20, edgecolors="none", zorder=12)
    # Core dot
    sc = ax.scatter(lons_s, lats_s, s=sizes_s, c=log_s, cmap=cmap, norm=norm,
                    alpha=0.85, edgecolors="white", linewidths=0.4, zorder=13)

    # --- Label busiest stations ---
    top_n = stations.sort("umf_i_dag", descending=True, nulls_last=True).head(15)
    labeled_positions = []
    for row in top_n.iter_rows(named=True):
        x, y = row["lon"], row["lat"]
        count = row["umf_i_dag"] or 0
        name = row["nafn"]

        too_close = any(abs(x - lx) < 0.12 and abs(y - ly) < 0.04
                        for lx, ly in labeled_positions)
        if too_close:
            continue
        labeled_positions.append((x, y))

        if count >= 1000:
            label = f"{name}\n{count/1000:.1f}k vehicles"
        else:
            label = f"{name}\n{count} vehicles"

        ax.annotate(label, xy=(x, y), xytext=(10, 10),
                    textcoords="offset points", fontsize=5.5,
                    color=C["label"], fontweight="medium",
                    path_effects=halo(width=2),
                    arrowprops=dict(arrowstyle="-", color="#888",
                                    lw=0.6, connectionstyle="arc3,rad=0.15"),
                    zorder=14)

    # --- Colorbar ---
    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cax = fig.add_axes([0.72, 0.08, 0.18, 0.018])  # [left, bottom, width, height]
    cbar = fig.colorbar(sm, cax=cax, orientation="horizontal")
    tick_vals = [0, 1, 2, 3, 4, np.log10(50000)]
    tick_labels = ["0", "10", "100", "1k", "10k", "50k"]
    cbar.set_ticks(tick_vals)
    cbar.set_ticklabels(tick_labels)
    cbar.ax.tick_params(labelsize=6, length=3, width=0.5, colors="#666")
    cbar.outline.set_edgecolor("#c4bfb4")
    cbar.outline.set_linewidth(0.5)
    cbar.set_label("Vehicles today", fontsize=7, color="#555", labelpad=3)

    # --- Axes ---
    ax.set_xlim(W, E)
    ax.set_ylim(S, N)
    ax.set_aspect(LAT_CORR)

    for lon in range(-24, -13, 2):
        ax.axvline(lon, color=C["grid"], linewidth=0.3, alpha=0.4, zorder=1)
    for lat in np.arange(63.5, 67, 0.5):
        ax.axhline(lat, color=C["grid"], linewidth=0.3, alpha=0.4, zorder=1)

    ax.tick_params(labelsize=6, colors="#8a8a80", length=3, width=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor(C["frame"])
        spine.set_linewidth(1.2)

    # --- Title ---
    total_today = int(counts.sum())
    n_stations = len(stations)
    ax.text(0.5, 0.975, "Umferð á Íslandi", transform=ax.transAxes,
            fontsize=26, fontweight="bold", color=C["frame"],
            ha="center", va="top", fontfamily="serif",
            path_effects=halo(C["ocean"], 4))
    ax.text(0.5, 0.943,
            f"Daily traffic volume  ·  {n_stations} stations  ·  {total_today:,} vehicles counted today",
            transform=ax.transAxes, fontsize=9.5, color="#5a5a52",
            ha="center", va="top",
            path_effects=halo(C["ocean"], 2.5))

    # --- Legend ---
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=C["town"],
               markeredgecolor="white", markersize=6, linewidth=0,
               label="Settlement"),
        Line2D([0], [0], color=C["road_ring"], linewidth=2, label="Route 1"),
        Line2D([0], [0], color=C["road_major"], linewidth=1.2, label="Regional roads"),
        Line2D([0], [0], color=C["road_minor"], linewidth=0.6, alpha=0.6, label="Local roads"),
    ]
    leg = ax.legend(handles=legend_elements, loc="lower left",
                    fontsize=6.5, frameon=True, fancybox=True,
                    framealpha=0.92, edgecolor="#c4bfb4",
                    borderpad=0.8, labelspacing=0.6,
                    bbox_to_anchor=(0.008, 0.008))
    leg.get_frame().set_facecolor(C["halo"])

    # --- Scale bar ---
    sb_lon, sb_lat = -15.0, 63.35
    km100_deg = 100 / (111.32 * np.cos(np.radians(65)))
    ax.plot([sb_lon, sb_lon + km100_deg], [sb_lat, sb_lat],
            color=C["frame"], linewidth=2, zorder=15)
    ax.plot([sb_lon, sb_lon], [sb_lat - 0.03, sb_lat + 0.03],
            color=C["frame"], linewidth=1.5, zorder=15)
    ax.plot([sb_lon + km100_deg, sb_lon + km100_deg],
            [sb_lat - 0.03, sb_lat + 0.03],
            color=C["frame"], linewidth=1.5, zorder=15)
    ax.text(sb_lon + km100_deg / 2, sb_lat + 0.06, "100 km",
            fontsize=6, ha="center", va="bottom", color=C["frame"],
            fontweight="bold", path_effects=halo(C["ocean"], 2))

    # --- Attribution ---
    ax.text(0.99, 0.005,
            "Base: Landmælingar Íslands (ERM)  ·  Traffic: Vegagerðin  ·  WGS 84",
            transform=ax.transAxes, fontsize=5, color="#8a8a80",
            ha="right", va="bottom",
            path_effects=halo(C["ocean"], 1.5))

    # North arrow
    ax.annotate("", xy=(0.955, 0.925), xytext=(0.955, 0.88),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=C["frame"], lw=1.8))
    ax.text(0.955, 0.937, "N", transform=ax.transAxes, fontsize=9,
            fontweight="bold", color=C["frame"], ha="center", va="bottom",
            path_effects=halo(C["ocean"], 2))

    # --- Save ---
    plt.tight_layout(pad=0.5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"Map saved: {OUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

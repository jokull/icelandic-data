# Kortagerð (Mapmaking) — Iceland Maps

Generate high-quality maps of Iceland using cached LMI geodata. Supports interactive HTML (Leaflet) and static PNG/SVG (geopandas + matplotlib).

## Quick Start

```bash
# Ensure geodata is cached
uv run python scripts/lmi.py download

# Interactive map (full-screen, layer toggles, popups)
uv run python scripts/kortagerð.py html -o reports/map.html

# Static map (publication-quality PNG)
uv run python scripts/kortagerð.py static -o reports/map.png

# Zoomed to capital area with Reykjavík highlighted
uv run python scripts/kortagerð.py static --bounds capital --highlight "Reykjavíkurborg" -o reports/rvk.png

# Overlay custom points from CSV
uv run python scripts/kortagerð.py static --points data/my_locations.csv -o reports/custom.png
```

## Bounding Box Presets

| Name | Area | Bounds [W, S, E, N] |
|------|------|---------------------|
| `iceland` | Full country (default) | -24.7, 63.2, -13.1, 66.6 |
| `capital` / `reykjavik` | Greater Reykjavík | -22.1, 63.95, -21.3, 64.25 |
| `southwest` | Reykjanes to Hekla | -22.5, 63.6, -19.5, 64.5 |
| `north` | Skagafjörður to Húsavík | -20.0, 65.2, -15.0, 66.6 |
| `east` | Eastfjords | -16.0, 64.2, -13.3, 65.8 |
| `westfjords` | Westfjords | -24.7, 65.0, -21.0, 66.6 |
| `south` | South coast | -21.0, 63.2, -17.5, 64.3 |
| `akureyri` | Akureyri area | -18.4, 65.5, -17.7, 65.8 |

## Cached Layers (in `data/geodata/`)

| File | What | When to use |
|------|------|-------------|
| `Landmask.geojson` | Iceland land polygon | Always — base fill for any map |
| `CoastalLine.geojson` | Coastline | Border outline |
| `AdministrativeUnit_level2.geojson` | 128 municipalities | Choropleth, boundaries, `--highlight` |
| `RoadLines.geojson` | Road network | Infrastructure, transport maps |
| `WatercourseLine.geojson` | Rivers (28k features) | Hydrology (skip for perf if not needed) |
| `Lake_Reservoir.geojson` | Lakes | Hydrology, geography |
| `LandIceArea.geojson` | Glaciers | Terrain, geography |
| `BuiltupAreaPoints.geojson` | 98 settlements + pop | City labels, settlement maps |
| `NatureParkArea.geojson` | National parks | Environmental, tourism maps |
| `IslandArea.geojson` | Islands | Offshore geography |
| `Airport_Airfield_points.geojson` | Airports | Transport maps |
| `Port.geojson` | Harbors | Maritime, transport maps |

## Python Code Templates

### Load a layer with geopandas

```python
import geopandas as gpd
from pathlib import Path

GEODATA = Path("data/geodata")
land = gpd.read_file(GEODATA / "Landmask.geojson")
municipalities = gpd.read_file(GEODATA / "AdministrativeUnit_level2.geojson")
```

### Simple choropleth map

```python
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path

GEODATA = Path("data/geodata")
land = gpd.read_file(GEODATA / "Landmask.geojson")
munic = gpd.read_file(GEODATA / "AdministrativeUnit_level2.geojson")

# Merge your data onto municipalities
# munic = munic.merge(your_data, left_on="namn", right_on="municipality")

fig, ax = plt.subplots(figsize=(12, 8), facecolor="#f0f4f8")
ax.set_facecolor("#c8d6e5")
land.plot(ax=ax, color="#f5f0e6", edgecolor="#2d3436", linewidth=0.6)
munic.plot(ax=ax, column="your_metric", cmap="YlOrRd", legend=True,
           edgecolor="#636e72", linewidth=0.3, alpha=0.8)
ax.set_xlim(-24.7, -13.1)
ax.set_ylim(63.2, 66.6)
ax.set_aspect(1 / 0.42)  # latitude correction at 65°N
ax.set_title("Your Title")
plt.tight_layout()
fig.savefig("reports/choropleth.png", dpi=200, bbox_inches="tight")
```

### Overlay custom points

```python
import polars as pl
import geopandas as gpd
import matplotlib.pyplot as plt

GEODATA = Path("data/geodata")
land = gpd.read_file(GEODATA / "Landmask.geojson")

# Your point data
pts = pl.read_csv("data/processed/your_points.csv")

fig, ax = plt.subplots(figsize=(12, 8))
land.plot(ax=ax, color="#f5f0e6", edgecolor="#2d3436", linewidth=0.6)
ax.scatter(pts["lon"], pts["lat"], c="#e74c3c", s=20, zorder=10)
```

### Interactive HTML with custom data overlay

```python
import json
from pathlib import Path

GEODATA = Path("data/geodata")

# Load base layers
with open(GEODATA / "Landmask.geojson") as f:
    landmask = json.load(f)

# Build Leaflet HTML with your data embedded as JSON
# Follow the pattern in scripts/kortagerð.py cmd_html()
```

## R Code Templates

### Load layers with sf

```r
library(sf)
library(ggplot2)

geodata <- "data/geodata"
land <- st_read(file.path(geodata, "Landmask.geojson"))
munic <- st_read(file.path(geodata, "AdministrativeUnit_level2.geojson"))
roads <- st_read(file.path(geodata, "RoadLines.geojson"))
glaciers <- st_read(file.path(geodata, "LandIceArea.geojson"))
lakes <- st_read(file.path(geodata, "Lake_Reservoir.geojson"))
```

### Basic ggplot2 map

```r
ggplot() +
  geom_sf(data = land, fill = "#f5f0e6", color = "#2d3436", linewidth = 0.3) +
  geom_sf(data = glaciers, fill = "#dfe6e9", color = "#b2bec3", linewidth = 0.2) +
  geom_sf(data = lakes, fill = "#74b9ff", color = "#0984e3", linewidth = 0.2) +
  geom_sf(data = roads, color = "#e17055", linewidth = 0.3) +
  coord_sf(xlim = c(-24.7, -13.1), ylim = c(63.2, 66.6)) +
  theme_minimal() +
  labs(title = "Iceland")
```

### Choropleth with municipality data

```r
# Merge your data onto municipalities
munic_data <- munic %>%
  left_join(your_data, by = c("namn" = "municipality"))

ggplot() +
  geom_sf(data = land, fill = "#f5f0e6", color = "#2d3436", linewidth = 0.3) +
  geom_sf(data = munic_data, aes(fill = your_metric), color = "#636e72", linewidth = 0.2) +
  scale_fill_viridis_c() +
  coord_sf(xlim = c(-24.7, -13.1), ylim = c(63.2, 66.6)) +
  theme_minimal()
```

## Color Palette

Standard colors used by `kortagerð.py`:

| Element | Fill | Stroke |
|---------|------|--------|
| Ocean | `#c8d6e5` | — |
| Land | `#f5f0e6` | `#2d3436` |
| Glaciers | `#dfe6e9` | `#b2bec3` |
| Lakes | `#74b9ff` | `#0984e3` |
| Rivers | `#0984e3` | — |
| Major roads | `#d63031` | — |
| Minor roads | `#e17055` | — |
| Nature parks | `#a8e6cf` | `#00b894` |
| Municipalities | `#b2bec3` (dashed) | — |
| Highlight | `#ffeaa7` | `#fdcb6e` |
| Settlements | `#2d3436` | `#fff` |

## Tips

- **Latitude correction**: At 65°N, set `ax.set_aspect(1/0.42)` in matplotlib or the map will appear stretched
- **WatercourseLine** has 28k features — skip for faster rendering on zoomed maps
- **Municipality names** are in the `namn` column of `AdministrativeUnit_level2.geojson`
- **Settlement population** is in the `ppl` column of `BuiltupAreaPoints.geojson`
- **Road classification**: filter by `rtt` field (1-3 = highways, 4-10 = regional, >10 = local)
- For **extra layers** not pre-cached: `uv run python scripts/lmi.py fetch ERM:WetlandArea`

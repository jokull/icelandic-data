# iceaddr - Icelandic Address Geocoding

Python library for Icelandic address lookup, geocoding, and reverse geocoding. Uses a bundled SQLite database from Staðfangaskrá (official address registry).

**Install:** `uv add iceaddr`

## Address Lookup

```python
from iceaddr import iceaddr_lookup

# By street name and number
results = iceaddr_lookup("Laugavegur", number=22, postcode=101)
# Returns: [{'hnitnum': ..., 'lat_wgs84': 64.1455, 'long_wgs84': -21.9291, ...}]

# Fuzzy search (just street name)
results = iceaddr_lookup("Laugavegur", limit=50)

# With letter suffix
results = iceaddr_lookup("Hlíðarhjalli", number=41, letter="E", postcode=200)
```

### Address Fields

| Field | Description |
|-------|-------------|
| `hnitnum` | Unique 8-digit location ID |
| `heiti_nf` | Street name (nominative) |
| `heiti_tgf` | Street name (dative) |
| `husnr` | House number |
| `bokst` | Letter suffix (a, b, etc) |
| `postnr` | Postal code |
| `svfnr` | Municipality code |
| `lat_wgs84` | Latitude |
| `long_wgs84` | Longitude |
| `lysing` | Area description |
| `stadur_nf` | Place name |
| `svfheiti` | Municipality name |

## Address Autocomplete

```python
from iceaddr import iceaddr_suggest

# Autocomplete as user types
suggestions = iceaddr_suggest("Laugav", limit=10)
# Returns matching addresses sorted by relevance
```

## Reverse Geocoding

```python
from iceaddr import nearest_addr, nearest_addr_with_dist

# Find nearest address to coordinates
lat, lng = 64.1466, -21.9426
addresses = nearest_addr(lat, lng, limit=5)
# Returns: [{'heiti_nf': 'Tjarnargata', 'husnr': 10, ...}]

# With distance in km
results = nearest_addr_with_dist(lat, lng, limit=5)
# Returns: [(address_dict, distance_km), ...]
```

## Placenames

```python
from iceaddr import placename_lookup, nearest_placenames

# Lookup placename
places = placename_lookup("Þingvellir")
# Returns: [{'nafn': 'Þingvellir', 'lat_wgs84': 64.26, 'long_wgs84': -21.12, ...}]

# Find nearest placenames to coordinates
places = nearest_placenames(64.1466, -21.9426, limit=5)
```

## Postcodes

```python
from iceaddr import postcode_lookup, POSTCODES, region_for_postcode

# Get info for a postcode
info = postcode_lookup(101)
# Returns: {'lysing': 'Miðborg', 'stadur_nf': 'Reykjavík', 'svaedi_nf': 'Höfuðborgarsvæðið', ...}

# All postcodes
POSTCODES  # dict: {101: {...}, 102: {...}, ...}

# Get region name
region_for_postcode(101)  # 'Höfuðborgarsvæðið'
```

## Municipalities

```python
from iceaddr import MUNICIPALITIES, municipality_for_municipality_code

# All municipalities
MUNICIPALITIES  # dict: {0: 'Reykjavíkurborg', 1000: 'Kópavogsbær', ...}

# Lookup by code
municipality_for_municipality_code(0)  # 'Reykjavíkurborg'
municipality_for_municipality_code(1000)  # 'Kópavogsbær'
```

## Geo Utilities

```python
from iceaddr import in_iceland, distance

# Check if coordinates are in Iceland (within 300km of center)
in_iceland((64.1466, -21.9426))  # True
in_iceland((51.5074, -0.1278))   # False (London)

# Distance between two points (km)
distance((64.15, -21.95), (64.26, -21.12))  # ~45 km
```

## Common Tasks

### Verify an address exists
```python
def verify_address(street, number, postcode):
    results = iceaddr_lookup(street, number=number, postcode=postcode)
    return len(results) > 0
```

### Geocode a full address string
```python
import re

def geocode_address(address_str):
    """Parse and geocode 'Laugavegur 22, 101 Reykjavík'"""
    # Extract components
    match = re.match(r'^([^0-9]+)\s*(\d+)([a-zA-Z]?)(?:,?\s*(\d{3}))?', address_str)
    if not match:
        return None
    street, num, letter, postcode = match.groups()
    results = iceaddr_lookup(
        street.strip(),
        number=int(num),
        letter=letter or None,
        postcode=int(postcode) if postcode else None
    )
    return results[0] if results else None
```

### Find addresses within radius
```python
def addresses_within_radius(lat, lng, radius_km=1):
    """Find all addresses within radius_km of a point"""
    results = nearest_addr_with_dist(lat, lng, limit=1000)
    return [(addr, dist) for addr, dist in results if dist <= radius_km]
```

## Data Source

- **Staðfangaskrá** from Registers Iceland (Þjóðskrá Íslands)
- **IS 50V Örnefni** placename data from National Land Survey
- **Postcodes** from Íslandspóstur

Database is bundled with the package and updated periodically.

## Caveats

- `hnitnum` (8-digit) ≠ `heinum` from HMS kaupskrá (7-digit)
- Some addresses have multiple entries (one per apartment letter)
- Rural addresses may have less precise coordinates

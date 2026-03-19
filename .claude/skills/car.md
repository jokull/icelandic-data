# Island.is Vehicle Lookup

Individual vehicle lookup via the island.is public GraphQL API.

## API

- **Endpoint:** `POST https://island.is/api/graphql`
- **Auth:** None (public)
- **Operation:** `publicVehicleSearch`

## Fields

| Field | Description |
|-------|-------------|
| `permno` | Permanent number (fastanúmer) |
| `regno` | Registration plate |
| `vin` | Vehicle Identification Number |
| `make` | Manufacturer |
| `vehicleCommercialName` | Model name |
| `color` | Color |
| `newRegDate` | Current registration date |
| `firstRegDate` | First registration date |
| `vehicleStatus` | Active/deregistered |
| `nextVehicleMainInspection` | Next inspection due |
| `co2` / `weightedCo2` | CO₂ emissions (NEDC) |
| `co2WLTP` / `weightedCo2WLTP` | CO₂ emissions (WLTP) |
| `massLaden` / `mass` | Vehicle weight |
| `typeNumber` | Type approval number |

## Usage

```bash
# Lookup by plate number
uv run python scripts/car.py AB123

# Lookup by VIN
uv run python scripts/car.py WVWZZZ3CZWE123456
```

## Caveats

- Search is fuzzy — partial plates may return multiple results
- Some fields may be null for older vehicles
- Rate limits unknown — be conservative with batch lookups

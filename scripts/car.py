"""
Vehicle lookup via island.is public GraphQL API.

Usage:
    uv run python scripts/car.py <plate_or_vin>
    uv run python scripts/car.py AB123
"""

import json
import sys

import httpx

GRAPHQL_URL = "https://island.is/api/graphql"

VEHICLE_SEARCH_QUERY = """
query publicVehicleSearch($input: GetPublicVehicleSearchInput!) {
  publicVehicleSearch(input: $input) {
    permno
    regno
    vin
    make
    vehicleCommercialName
    color
    newRegDate
    firstRegDate
    vehicleStatus
    nextVehicleMainInspection
    co2
    weightedCo2
    co2WLTP
    weightedCo2WLTP
    massLaden
    mass
    co
    typeNumber
  }
}
"""


def lookup(search: str) -> list[dict]:
    resp = httpx.post(
        GRAPHQL_URL,
        json={
            "operationName": "publicVehicleSearch",
            "variables": {"input": {"search": search}},
            "query": VEHICLE_SEARCH_QUERY,
        },
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("publicVehicleSearch", [])


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/car.py <plate_or_vin>")
        sys.exit(1)

    results = lookup(sys.argv[1])
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

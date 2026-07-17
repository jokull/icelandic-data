"""Health probe — island.is public vehicle lookup (GraphQL).

Contract: `POST /api/graphql` still accepts the `publicVehicleSearch` query with
every field scripts/car.py selects.

Deliberately probes **no real vehicle**. Two properties make that possible:

  1. GraphQL validates a document against the schema *before* executing it, so
     a search string that matches nothing still proves the whole field
     selection in VEHICLE_SEARCH_QUERY is valid. A dropped or renamed field
     comes back as GRAPHQL_VALIDATION_FAILED rather than as data.
  2. Asking for a nonexistent field makes the server name the return type in
     the error — a schema assertion that needs no lookup at all.

Introspection is disabled on this server (Apollo `introspection: false` in
production), so `__schema` / `__type` queries are not an option here — don't
"fix" this file by reaching for them.
"""
from __future__ import annotations

from scripts.car import GRAPHQL_URL, VEHICLE_SEARCH_QUERY

# Structurally impossible as an Icelandic plate (5 chars) or a VIN (17 chars).
# Matches nothing, so the server validates and then returns null.
NO_SUCH_VEHICLE = "NOT-A-PLATE-000000"

# The type publicVehicleSearch resolves to. Renaming it is a breaking change
# we want to hear about.
RETURN_TYPE = "VehiclesPublicVehicleSearch"


def test_endpoint_serves_graphql(http):
    """A bogus field must be rejected by name — proves we reached a real
    GraphQL server and that `publicVehicleSearch` still exists on Query.

    Apollo answers a rejected document with HTTP 400, so 400 here is the
    *success* path; the payload is what carries the signal.
    """
    r = http.post(
        GRAPHQL_URL,
        json={
            "operationName": "publicVehicleSearch",
            "variables": {"input": {"search": NO_SUCH_VEHICLE}},
            "query": (
                "query publicVehicleSearch($input: GetPublicVehicleSearchInput!) "
                "{ publicVehicleSearch(input: $input) { definitelyNotAField } }"
            ),
        },
    )
    assert r.status_code in (200, 400), f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    errors = r.json().get("errors") or []
    assert errors, "expected a validation error for a bogus field, got none"
    assert RETURN_TYPE in errors[0]["message"], (
        f"{r.request.url} -> 200 but publicVehicleSearch no longer resolves to "
        f"{RETURN_TYPE}: {errors[0]['message']}"
    )


def test_query_fields_still_validate(http):
    """The whole contract in one call: send scripts/car.py's exact query.

    A search that matches nothing returns `{"data": {"publicVehicleSearch": null}}`
    — no vehicle data is touched, but the document was still validated against
    the live schema, so any renamed/removed field surfaces as an error here.
    """
    r = http.post(
        GRAPHQL_URL,
        json={
            "operationName": "publicVehicleSearch",
            "variables": {"input": {"search": NO_SUCH_VEHICLE}},
            "query": VEHICLE_SEARCH_QUERY,
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    payload = r.json()
    assert not payload.get("errors"), (
        f"{r.request.url} -> 200 but VEHICLE_SEARCH_QUERY no longer validates: "
        f"{payload['errors']}"
    )
    assert "data" in payload, f"no 'data' key; got {sorted(payload)}"
    assert "publicVehicleSearch" in payload["data"], (
        f"query field missing from response: {sorted(payload['data'])}"
    )


def test_input_type_is_unchanged(http):
    """`GetPublicVehicleSearchInput` is baked into the query string, so a rename
    would break every call. The server rejects unknown types by name."""
    r = http.post(
        GRAPHQL_URL,
        json={
            "operationName": "publicVehicleSearch",
            "variables": {"input": {"search": NO_SUCH_VEHICLE}},
            "query": (
                "query publicVehicleSearch($input: GetPublicVehicleSearchInput!) "
                "{ publicVehicleSearch(input: $input) { permno } }"
            ),
        },
    )
    # 400 would mean the document was rejected — let the assertion below name
    # why rather than failing on a bare status code.
    assert r.status_code in (200, 400), f"{r.request.url} -> {r.status_code}: {r.text[:200]}"

    errors = r.json().get("errors") or []
    unknown_type = [e for e in errors if "Unknown type" in e.get("message", "")]
    assert not unknown_type, (
        f"{r.request.url} -> 200 but GetPublicVehicleSearchInput is gone: "
        f"{unknown_type[0]['message']}"
    )

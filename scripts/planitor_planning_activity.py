"""Extract Reykjavík planning activity time series from Planitor API.

Filters to Reykjavík-only (three councils: Byggingarfulltrúi, Skipulagsfulltrúi,
Umhverfis- og skipulagsráð) because Hafnarfjörður and Árborg coverage is less
comprehensive. Deduplicates by case_address per year so each physical project
is counted once. Classifies minutes by building type (keyword search) and
planning stage (inquiry/remarks text patterns). Extracts unit counts and area
where available.

Output: data/processed/planitor_reykjavik_planning.csv

Usage: uv run python scripts/planitor_planning_activity.py
"""

import re
import time
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / "data" / "processed" / "planitor_reykjavik_planning.csv"

BASE = "https://www.planitor.io/api/minutes/search"

# Reykjavík has three councils with unique names — filter by council name
# to isolate Reykjavík data from Hafnarfjörður/Árborg (which have less
# comprehensive coverage in Planitor).
REYKJAVIK_COUNCILS = {
    "Byggingarfulltrúi",
    "Skipulagsfulltrúi",
    "Umhverfis- og skipulagsráð",
}

# Building type classification keywords
BUILDING_TYPES = [
    ("apartment", "fjölbýlishús", True),
    ("hotel", "hótel", False),
    ("single_family", "einbýlishús", True),
    ("row_house", "raðhús", True),
    ("semi_detached", "parhús", True),
    ("commercial", "verslunarhúsnæði", False),
    ("guesthouse", "gestahús", False),
]


def fetch_all(q: str, after: str, before: str) -> list[dict]:
    """Paginate through all matching minutes, filtering to Reykjavík councils."""
    items = []
    offset = 0
    while True:
        params = {"q": q, "after": after, "before": before, "limit": 200, "offset": offset}
        resp = httpx.get(BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("items", [])
        # Filter to Reykjavík councils only
        reykjavik_batch = [i for i in batch if i.get("council") in REYKJAVIK_COUNCILS]
        items.extend(reykjavik_batch)
        if len(batch) < 200:
            break
        offset += 200
        time.sleep(0.3)
    return items


def classify_stage(inquiry: str, remarks: str) -> str:
    """Classify the planning stage from inquiry and remarks text."""
    inq = (inquiry or "").lower()
    rem = (remarks or "").lower()

    if "lokaúttekt" in inq:
        return "final_inspection"
    if "áfangaúttekt" in inq:
        return "phase_inspection"
    if "sótt er um leyfi til að byggja" in inq or "byggingaráform" in inq:
        return "new_build_application"
    if "sótt er um leyfi til viðbyggingar" in inq:
        return "extension"
    if "breyta erindi" in inq or "breytingaerindi" in inq:
        return "amendment"
    if "sótt er um leyfi til að breyta" in inq:
        return "modification"
    if "sótt er um leyfi fyrir áður gerðum" in inq:
        return "retroactive"
    if "niðurrif" in inq:
        return "demolition"
    if "deiliskipulag" in inq:
        return "zoning_change"
    if "grenndarkynningu" in inq or "grenndarkynning" in rem:
        return "neighbor_notification"
    return "other"


def classify_outcome(remarks: str) -> str:
    """Classify outcome from remarks text."""
    rem = (remarks or "").lower()[:50]
    if "samþykkt" in rem:
        return "approved"
    if "neikvætt" in rem or "synjað" in rem:
        return "rejected"
    if "frestað" in rem:
        return "postponed"
    if "vísað til" in rem:
        return "referred"
    return "other"


def extract_units(inquiry: str | None) -> int | None:
    """Extract unit count from inquiry text."""
    if not inquiry:
        return None
    matches = re.findall(r"(\d+)\s*íbúð", inquiry)
    if matches:
        return max(int(m) for m in matches)
    return None


def extract_area(inquiry: str | None) -> float | None:
    """Extract total area in m² from inquiry text."""
    if not inquiry:
        return None
    matches = re.findall(r"([\d.]+,?\d*)\s*ferm", inquiry)
    if matches:
        areas = []
        for m in matches:
            cleaned = m.replace(".", "").replace(",", ".")
            try:
                areas.append(float(cleaned))
            except ValueError:
                continue
        if areas:
            return max(areas)
    return None


def deduplicate_by_address(items: list[dict]) -> dict[str, dict]:
    """Group minutes by case_address, keep the most advanced stage per address.

    Returns dict of address -> best minute (with extracted metadata).
    Stage priority: final_inspection > new_build_application > amendment > ...
    """
    STAGE_PRIORITY = {
        "final_inspection": 9,
        "phase_inspection": 8,
        "new_build_application": 7,
        "extension": 6,
        "zoning_change": 5,
        "neighbor_notification": 4,
        "amendment": 3,
        "modification": 2,
        "retroactive": 1,
        "demolition": 1,
        "other": 0,
    }
    OUTCOME_PRIORITY = {"approved": 3, "rejected": 2, "postponed": 1, "referred": 1, "other": 0}

    by_address: dict[str, dict] = {}

    for item in items:
        addr = (item.get("case_address") or "").strip()
        if not addr:
            continue

        inquiry = item.get("inquiry") or ""
        remarks = item.get("remarks") or ""
        stage = classify_stage(inquiry, remarks)
        outcome = classify_outcome(remarks)
        units = extract_units(inquiry)
        area = extract_area(inquiry)

        score = STAGE_PRIORITY.get(stage, 0) * 10 + OUTCOME_PRIORITY.get(outcome, 0)

        if addr not in by_address or score > by_address[addr]["_score"]:
            by_address[addr] = {
                "address": addr,
                "stage": stage,
                "outcome": outcome,
                "units": units,
                "area_m2": area,
                "minute_count": 0,
                "_score": score,
                "is_new_build": stage == "new_build_application",
            }
        # Always accumulate minute count
        by_address[addr]["minute_count"] += 1
        # Keep best unit/area data
        if units and (by_address[addr]["units"] is None or units > by_address[addr]["units"]):
            by_address[addr]["units"] = units
        if area and (by_address[addr]["area_m2"] is None or area > by_address[addr]["area_m2"]):
            by_address[addr]["area_m2"] = area

    return by_address


def main():
    rows = []

    for year in range(2015, 2027):
        after = f"{year}-01-01"
        before = f"{year + 1}-01-01"
        print(f"\n=== {year} ===")

        for label, keyword, is_residential in BUILDING_TYPES:
            items = fetch_all(keyword, after, before)
            total_minutes = len(items)

            # Deduplicate by address
            projects = deduplicate_by_address(items)
            unique_projects = len(projects)

            # Count by stage
            new_builds = {a: p for a, p in projects.items() if p["is_new_build"]}
            approved_new = sum(1 for p in new_builds.values() if p["outcome"] == "approved")
            final_inspections = sum(1 for p in projects.values() if p["stage"] == "final_inspection")
            amendments = sum(1 for p in projects.values() if p["stage"] == "amendment")

            # Unit counts from new builds
            nb_units = [p["units"] for p in new_builds.values() if p["units"]]
            total_units = sum(nb_units) if nb_units else None

            # Area from new builds
            nb_areas = [p["area_m2"] for p in new_builds.values() if p["area_m2"]]
            total_area = sum(nb_areas) if nb_areas else None

            print(
                f"  {label:15s}: {total_minutes:4d} min → {unique_projects:3d} unique addr, "
                f"{len(new_builds):3d} new-build ({approved_new} approved), "
                f"{final_inspections:2d} final insp, "
                f"{len(nb_units):3d} w/units ({total_units or 0} units)"
            )

            rows.append({
                "year": year,
                "building_type": label,
                "is_residential": is_residential,
                "total_minutes": total_minutes,
                "unique_projects": unique_projects,
                "new_build_projects": len(new_builds),
                "new_build_approved": approved_new,
                "final_inspections": final_inspections,
                "amendments": amendments,
                "new_build_units": total_units,
                "new_build_area_m2": round(total_area, 1) if total_area else None,
            })

            time.sleep(0.5)

    df = pl.DataFrame(rows)
    DST.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(DST)
    print(f"\nWrote {len(df)} rows to {DST}")

    # Summary
    print("\n=== UNIQUE NEW-BUILD PROJECTS (address-deduplicated) ===")
    summary = (
        df.group_by("year")
        .agg(
            pl.col("new_build_projects").filter(pl.col("is_residential")).sum().alias("residential"),
            pl.col("new_build_projects").filter(~pl.col("is_residential")).sum().alias("non_residential"),
            pl.col("new_build_units").filter(pl.col("building_type") == "apartment").sum().alias("apt_units"),
            pl.col("final_inspections").filter(pl.col("is_residential")).sum().alias("res_completed"),
        )
        .sort("year")
    )
    print(summary)


if __name__ == "__main__":
    main()

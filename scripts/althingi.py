"""
Alþingi parliamentary records — fetch MPs, votes, bills, committees, speeches.

Data source: XML feeds at www.althingi.is/altext/xml/
See .agents/skills/althingi/SKILL.md for full API documentation.

Usage:
    uv run python scripts/althingi.py list                     # all parliaments
    uv run python scripts/althingi.py list --datasets          # what fetch can pull
    uv run python scripts/althingi.py fetch --dataset members
    uv run python scripts/althingi.py fetch --dataset votes --thing 156
    uv run python scripts/althingi.py fetch --dataset all --thing 150-156
"""

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import polars as pl

BASE_URL = "https://www.althingi.is/altext/xml"

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "althingi"
PROCESSED_DIR = ROOT / "data" / "processed"

# Alþingi refreshes once per 24h, so politeness costs us nothing. The votes
# dataset issues ~300 requests for a single parliament.
REQUEST_DELAY = 0.25
TIMEOUT = 60
LIVE_CACHE_SECONDS = 24 * 60 * 60

# althingi.is 403s httpx's default User-Agent. Any identifying string is
# accepted; sending none is the failure mode.
USER_AGENT = "icelandic-data (+https://github.com/jokull/icelandic-data)"

DATASETS = {
    "members": "MPs with party, constituency and seat, one row per service spell",
    "votes": "Vote events plus the per-MP ballots (two files)",
    "bills": "Matters — bills, resolutions, questions, reports",
    "committees": "Committee membership with start/end dates",
    "sittings": "Sittings of the house",
    "speeches": "Speech metadata — speaker, sitting, timestamps (no text)",
}

# "unknown/none" placeholder ids — empty CDATA name, "-" abbreviation.
# See SKILL.md caveat 7.
SENTINEL_PARTY_IDS = {"26"}
SENTINEL_CONSTITUENCY_IDS = {"1"}

_DMY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")


def iso_date(value: str | None) -> str | None:
    """Normalise Alþingi's mixed date forms to ISO.

    `D.M.YYYY` appears in löggjafarþing, þingseta and þingfundir; ISO already
    in fæðingardagur and the vote timestamps. Alþingi's own To-Do list has
    "Breyta dagsetningum í ISO" pending, so both forms must keep working.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    m = _DMY.match(value)
    if m:
        day, month, year = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return value


def text(node: ET.Element | None, path: str) -> str | None:
    """Text of a child element, stripped; None when absent or blank."""
    if node is None:
        return None
    child = node.find(path)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def cast_dates(df: pl.DataFrame, *columns: str) -> pl.DataFrame:
    """Cast ISO date strings produced by iso_date() to a real Date dtype.

    Non-strict: a value that will not parse becomes null rather than raising.
    iso_date() normalises both upstream forms first, so this is a no-op on
    well-formed input — it is here to absorb the ISO migration Alþingi has
    pending without turning a format change into a crash.
    """
    return df.with_columns(
        pl.col(c).str.to_date("%Y-%m-%d", strict=False) for c in columns if c in df.columns
    )


def cast_datetimes(df: pl.DataFrame, *columns: str) -> pl.DataFrame:
    """Cast Alþingi's ISO timestamp strings to a real Datetime dtype."""
    return df.with_columns(
        pl.col(c).str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False)
        for c in columns
        if c in df.columns
    )


def frame(rows: list[dict], sort_by: list[str] | str) -> pl.DataFrame:
    """Build a sorted DataFrame, tolerating an empty result set.

    Coverage starts at a different parliament per dataset — votes and speeches
    only from þing 20, committees from 74 — so asking an early þing for a
    dataset it predates legitimately yields nothing. Sorting a zero-column
    frame would raise ColumnNotFound.
    """
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort(sort_by)


def _cache_path(path: str, params: dict) -> Path:
    slug = path.strip("/").replace("/", "_")
    if params:
        slug += "_" + "_".join(f"{k}{v}" for k, v in sorted(params.items()))
    return RAW_DIR / f"{slug}.xml"


def get_xml(
    client: httpx.Client,
    path: str,
    params: dict | None = None,
    force: bool = False,
    max_age: float | None = None,
) -> ET.Element:
    """Fetch and parse one XML document, caching the raw bytes.

    Parses from bytes, never text — these documents carry an encoding
    declaration and a decoded str raises ValueError in the XML parser.
    A max_age keeps live feeds fresh; None caches immutable history forever.
    """
    params = params or {}
    cache = _cache_path(path, params)

    cache_is_fresh = cache.exists() and (
        max_age is None or time.time() - cache.stat().st_mtime <= max_age
    )
    if cache_is_fresh and not force:
        return ET.fromstring(cache.read_bytes())

    resp = client.get(f"{BASE_URL}/{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(resp.content)
    time.sleep(REQUEST_DELAY)

    return ET.fromstring(resp.content)


# --------------------------------------------------------------------------
# Parliaments
# --------------------------------------------------------------------------


def current_thing(client: httpx.Client, force: bool = False) -> int:
    """The parliament sitting right now. Never hardcode this."""
    root = get_xml(
        client,
        "loggjafarthing/yfirstandandi/",
        force=force,
        max_age=LIVE_CACHE_SECONDS,
    )
    node = root.find("þing")
    if node is None:
        raise RuntimeError("yfirstandandi returned no <þing> — API shape changed")
    return int(node.attrib["númer"])


def parliaments(client: httpx.Client, force: bool = False) -> pl.DataFrame:
    root = get_xml(
        client,
        "loggjafarthing/",
        force=force,
        max_age=LIVE_CACHE_SECONDS,
    )
    rows = []
    for node in root.findall("þing"):
        rows.append(
            {
                "thing": int(node.attrib["númer"]),
                "timabil": text(node, "tímabil"),
                # The sitting parliament has no <þinglok> — caveat 5.
                "thingsetning": iso_date(text(node, "þingsetning")),
                "thinglok": iso_date(text(node, "þinglok")),
            }
        )
    return pl.DataFrame(rows).sort("thing")


def parse_thing_arg(value: str) -> list[int]:
    """`156`, `150-156` or `150,153,156` -> [int]."""
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


# --------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------


def fetch_members(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    """Roster joined to þingseta — the only route to party and constituency.

    One row per *service spell*, not per MP: an MP who switches party or sits
    as a substitute produces several <þingseta> entries for one parliament.
    """
    wanted = set(things)
    people: dict[str, dict] = {}

    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client, "thingmenn/", {"lthing": thing}, force=force, max_age=max_age
        )
        for node in root.findall("þingmaður"):
            pid = node.attrib["id"]
            people.setdefault(
                pid,
                {
                    "thingmadur_id": int(pid),
                    "nafn": text(node, "nafn"),
                    "faedingardagur": iso_date(text(node, "fæðingardagur")),
                    "skammstofun": text(node, "skammstöfun"),
                },
            )
        print(f"  þing {thing}: {len(root.findall('þingmaður'))} people on the roster")

    print(f"  fetching þingseta for {len(people)} people…")
    rows = []
    for i, (pid, person) in enumerate(sorted(people.items(), key=lambda kv: int(kv[0])), 1):
        if i % 25 == 0:
            print(f"    {i}/{len(people)}")
        max_age = LIVE_CACHE_SECONDS if live_thing in wanted else None
        root = get_xml(
            client,
            "thingmenn/thingmadur/thingseta/",
            {"nr": pid},
            force=force,
            max_age=max_age,
        )

        for seta in root.findall(".//þingseta"):
            seta_thing = text(seta, "þing")
            if seta_thing is None or int(seta_thing) not in wanted:
                continue

            party = seta.find("þingflokkur")
            constituency = seta.find("kjördæmi")
            party_id = party.attrib.get("id") if party is not None else None
            constituency_id = (
                constituency.attrib.get("id") if constituency is not None else None
            )

            rows.append(
                {
                    **person,
                    "thing": int(seta_thing),
                    "tegund": text(seta, "tegund"),
                    "thingflokkur_id": int(party_id) if party_id else None,
                    # Sentinel rows carry an empty name — caveat 7.
                    "thingflokkur": (
                        None
                        if party_id in SENTINEL_PARTY_IDS
                        else (party.text.strip() if party is not None and party.text else None)
                    ),
                    "kjordaemi_id": int(constituency_id) if constituency_id else None,
                    "kjordaemi": (
                        None
                        if constituency_id in SENTINEL_CONSTITUENCY_IDS
                        else (
                            constituency.text.strip()
                            if constituency is not None and constituency.text
                            else None
                        )
                    ),
                    "kjordaemanumer": text(seta, "kjördæmanúmer"),
                    "thingsalssaeti": text(seta, "þingsalssæti"),
                    "inn": iso_date(text(seta, "tímabil/inn")),
                    # Absent while the MP is still serving.
                    "ut": iso_date(text(seta, "tímabil/út")),
                }
            )

    if not rows:
        return {"members": pl.DataFrame()}

    df = pl.DataFrame(rows).with_columns(
        pl.col("kjordaemanumer").cast(pl.Int64, strict=False),
        pl.col("thingsalssaeti").cast(pl.Int64, strict=False),
    )
    df = cast_dates(df, "faedingardagur", "inn", "ut")
    return {"members": df.sort(["thing", "nafn", "inn"])}


def fetch_votes(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    """Vote events, and the per-MP ballot for every vote that recorded one.

    Detail is fetched wherever the list entry carries a <nánar><xml> link —
    NOT by filtering on aðferð. Roll-call votes (nafnakall) also carry a full
    <atkvæðaskrá> and are exactly the contentious ones. See caveat 2.
    """
    votes, ballots = [], []

    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client,
            "atkvaedagreidslur/",
            {"lthing": thing},
            force=force,
            max_age=max_age,
        )
        events = root.findall("atkvæðagreiðsla")
        print(f"  þing {thing}: {len(events)} vote events")

        detail_numbers = []
        for node in events:
            summary = node.find("samantekt")
            number = node.attrib["atkvæðagreiðslunúmer"]
            tegund = node.find("tegund")

            votes.append(
                {
                    "atkvgr_nr": int(number),
                    "thing": int(node.attrib["þingnúmer"]),
                    "malsnumer": int(node.attrib["málsnúmer"]),
                    # Only unique within a málsflokkur — caveat 3.
                    "malsflokkur": node.attrib.get("málsflokkur"),
                    "malsheiti": text(node, "mál/málsheiti"),
                    "timi": text(node, "tími"),
                    "fundur": text(node, "fundur"),
                    "tegund": tegund.text.strip() if tegund is not None and tegund.text else None,
                    "tegund_kodi": tegund.attrib.get("tegund") if tegund is not None else None,
                    "adferd": text(summary, "aðferð"),
                    "ja": text(summary, "já/fjöldi"),
                    "nei": text(summary, "nei/fjöldi"),
                    "greidir_ekki": text(summary, "greiðirekkiatkvæði/fjöldi"),
                    "afgreidsla": text(summary, "afgreiðsla"),
                }
            )

            if node.find("nánar/xml") is not None:
                detail_numbers.append(number)

        print(f"    {len(detail_numbers)} have a recorded ballot — fetching detail")
        for i, number in enumerate(detail_numbers, 1):
            if i % 50 == 0:
                print(f"    {i}/{len(detail_numbers)}")
            detail = get_xml(
                client,
                "atkvaedagreidslur/atkvaedagreidsla/",
                {"numer": number},
                force=force,
                max_age=max_age,
            )
            # Absent for handaupprétting — counts only, no per-MP record.
            for mp in detail.findall("atkvæðaskrá/þingmaður"):
                ballots.append(
                    {
                        "atkvgr_nr": int(number),
                        "thing": int(detail.attrib["þingnúmer"]),
                        "thingmadur_id": int(mp.attrib["id"]),
                        "nafn": text(mp, "nafn"),
                        "atkvaedi": text(mp, "atkvæði"),
                    }
                )

    if not votes:
        return {"votes": pl.DataFrame(), "ballots": frame(ballots, ["atkvgr_nr", "nafn"])}

    votes_df = pl.DataFrame(votes).with_columns(
        pl.col("fundur").cast(pl.Int64, strict=False),
        pl.col("ja").cast(pl.Int64, strict=False),
        pl.col("nei").cast(pl.Int64, strict=False),
        pl.col("greidir_ekki").cast(pl.Int64, strict=False),
        pl.col("timi").str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False),
    )
    return {
        "votes": votes_df.sort("atkvgr_nr"),
        "ballots": frame(ballots, ["atkvgr_nr", "nafn"]),
    }


def fetch_bills(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    rows = []
    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client, "thingmalalisti/", {"lthing": thing}, force=force, max_age=max_age
        )
        nodes = root.findall("mál")
        print(f"  þing {thing}: {len(nodes)} matters")
        for node in nodes:
            kind = node.find("málstegund")
            rows.append(
                {
                    "thing": int(node.attrib["þingnúmer"]),
                    "malsnumer": int(node.attrib["málsnúmer"]),
                    "malsflokkur": node.attrib.get("málsflokkur"),
                    "malsheiti": text(node, "málsheiti"),
                    "malstegund": text(kind, "heiti"),
                    "malstegund_kodi": kind.attrib.get("málstegund") if kind is not None else None,
                    "efnisgreining": text(node, "efnisgreining"),
                }
            )
    return {"bills": frame(rows, ["thing", "malsflokkur", "malsnumer"])}


def fetch_committees(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    rows = []
    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client,
            "nefndir/nefndarmenn/",
            {"lthing": thing},
            force=force,
            max_age=max_age,
        )
        committees = root.findall("nefnd")
        print(f"  þing {thing}: {len(committees)} committees")
        for committee in committees:
            heiti = text(committee, "heiti")
            for member in committee.findall("nefndarmaður"):
                rows.append(
                    {
                        "thing": thing,
                        "nefnd_id": int(committee.attrib["id"]),
                        "nefnd": heiti,
                        "thingmadur_id": int(member.attrib["id"]),
                        "nafn": text(member, "nafn"),
                        "stada": text(member, "staða"),
                        "hofst": iso_date(text(member, "nefndasetahófst")),
                        "lauk": iso_date(text(member, "nefndasetulauk")),
                    }
                )
    df = cast_dates(frame(rows, ["thing", "nefnd", "nafn"]), "hofst", "lauk")
    return {"committees": df}


def fetch_sittings(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    rows = []
    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client, "thingfundir/", {"lthing": thing}, force=force, max_age=max_age
        )
        nodes = root.findall("þingfundur")
        print(f"  þing {thing}: {len(nodes)} sittings")
        for node in nodes:
            # A sitting scheduled relative to another one ("að loknum 37. fundi")
            # carries only <hefst><texti> — no <dagur>, no <dagurtími>. That is
            # ~9% of þing 156, so fall back to when the sitting was actually
            # opened rather than publishing a null date.
            settur = text(node, "fundursettur")
            scheduled_date = iso_date(text(node, "hefst/dagur"))
            rows.append(
                {
                    "thing": thing,
                    "fundur": int(node.attrib["númer"]),
                    "fundarheiti": text(node, "fundarheiti"),
                    "dagur": scheduled_date or (settur.split("T")[0] if settur else None),
                    "dagur_aaetlad": scheduled_date is not None,
                    "hefst_texti": text(node, "hefst/texti"),
                    "hefst": text(node, "hefst/dagurtími"),
                    "fundursettur": settur,
                    "fundarslit": text(node, "fuslit"),
                }
            )
    df = cast_dates(frame(rows, ["thing", "fundur"]), "dagur")
    df = cast_datetimes(df, "hefst", "fundursettur", "fundarslit")
    return {"sittings": df}


def fetch_speeches(
    client: httpx.Client, things: list[int], force: bool, live_thing: int | None = None
) -> dict[str, pl.DataFrame]:
    """Speech metadata. The text is not in this feed — only links to it."""
    rows = []
    for thing in things:
        max_age = LIVE_CACHE_SECONDS if thing == live_thing else None
        root = get_xml(
            client, "raedulisti/", {"lthing": thing}, force=force, max_age=max_age
        )
        nodes = root.findall("ræða")
        print(f"  þing {thing}: {len(nodes)} speeches")
        for node in nodes:
            speaker = node.find("ræðumaður")
            rows.append(
                {
                    "thing": thing,
                    "thingmadur_id": (
                        int(speaker.attrib["id"])
                        if speaker is not None and "id" in speaker.attrib
                        else None
                    ),
                    "nafn": text(speaker, "nafn"),
                    "dagur": iso_date(text(node, "dagur")),
                    "fundur": text(node, "fundur"),
                    "fundarheiti": text(node, "fundarheiti"),
                    "hofst": text(node, "ræðahófst"),
                    "lauk": text(node, "ræðulauk"),
                    "tegund": text(node, "tegundræðu"),
                    "umraeda": text(node, "umræða"),
                    "malsflokkur": text(node, "mál/málsflokkur"),
                    "malsnumer": text(node, "mál/málsnúmer"),
                    "malsheiti": text(node, "mál/málsheiti"),
                }
            )
    if not rows:
        return {"speeches": pl.DataFrame()}

    df = pl.DataFrame(rows).with_columns(
        pl.col("fundur").cast(pl.Int64, strict=False),
        pl.col("malsnumer").cast(pl.Int64, strict=False),
    )
    df = cast_dates(df, "dagur")
    df = cast_datetimes(df, "hofst", "lauk")
    return {"speeches": df.sort(["thing", "hofst"])}


FETCHERS = {
    "members": fetch_members,
    "votes": fetch_votes,
    "bills": fetch_bills,
    "committees": fetch_committees,
    "sittings": fetch_sittings,
    "speeches": fetch_speeches,
}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_list(args) -> None:
    with httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        if args.datasets:
            print("Datasets (uv run python scripts/althingi.py fetch --dataset NAME):\n")
            for name, desc in DATASETS.items():
                print(f"  {name:12s} {desc}")
            return

        current = current_thing(client, force=args.force)
        df = parliaments(client, force=args.force)
        print(f"{len(df)} parliaments — current is {current}\n")
        shown = df if args.limit is None else df.tail(args.limit)
        for row in shown.iter_rows(named=True):
            mark = " <- sitting" if row["thing"] == current else ""
            print(
                f"  {row['thing']:>4}  {row['timabil'] or '':<12}"
                f"  {row['thingsetning'] or '':<12} -> {row['thinglok'] or '(open)':<12}{mark}"
            )


def cmd_fetch(args) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        live_thing = current_thing(client, force=args.force)
        things = parse_thing_arg(args.thing) if args.thing else [live_thing]
        names = list(DATASETS) if args.dataset == "all" else [args.dataset]
        print(f"Parliaments: {things}")

        for name in names:
            print(f"\n{name}:")
            for key, df in FETCHERS[name](client, things, args.force, live_thing).items():
                if df.is_empty():
                    print(f"  no rows for {key} — nothing written")
                    continue
                out = PROCESSED_DIR / f"althingi_{key}.parquet"
                df.write_parquet(out)
                print(f"  {len(df):,} rows -> {out.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list parliaments, or the available datasets")
    p_list.add_argument("--datasets", action="store_true", help="list datasets instead")
    p_list.add_argument("--limit", type=int, help="show only the latest N parliaments")
    p_list.add_argument("--force", action="store_true", help="bypass the raw cache")
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="fetch a dataset")
    p_fetch.add_argument(
        "--dataset", required=True, choices=[*DATASETS, "all"], help="what to fetch"
    )
    p_fetch.add_argument("--thing", help="parliament: 156, 150-156 or 150,153 (default: current)")
    p_fetch.add_argument("--force", action="store_true", help="bypass the raw cache")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())

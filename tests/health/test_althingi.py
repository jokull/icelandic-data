"""Health probe — Alþingi parliamentary XML.

Contract: the endpoints scripts/althingi.py reads still serve XML whose
Icelandic element names are unchanged.

That last part is the point. Alþingi publishes no XSD ("Ekki er til xml-skema
fyrir gögnin") and states the shape may change without notice ("Framsetningin á
gögnunum geta tekið breytingum án fyrirvara"). There is no contract to lean on,
so a silent retag — not an outage — is the likeliest way this breaks. Every
assertion below is therefore about *shape*, never about values.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.althingi import BASE_URL, USER_AGENT

# Þing 156 closed on 2025-09-08. A closed parliament's documents are immutable,
# which makes it a stable fixture — unlike the sitting þing, whose vote and
# speech counts move daily.
CLOSED_THING = 156


def _xml(http, path: str, params: dict | None = None) -> ET.Element:
    """GET one document and parse it. Parses bytes — see SKILL.md caveat 13."""
    url = f"{BASE_URL}/{path}"
    r = http.get(url, params=params or {}, headers={"User-Agent": USER_AGENT})
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/xml"), (
        f"{r.request.url} -> 200 but content-type is {r.headers.get('content-type')!r}"
    )
    return ET.fromstring(r.content)


def test_current_parliament_resolves(http):
    """Everything keys off this — the script never hardcodes a þing number."""
    root = _xml(http, "loggjafarthing/yfirstandandi/")

    assert root.tag == "löggjafarþing", f"root is <{root.tag}>, expected <löggjafarþing>"
    thing = root.find("þing")
    assert thing is not None, f"no <þing> child; got {[c.tag for c in root]}"

    number = thing.attrib.get("númer")
    assert number and number.isdigit(), f"<þing númer> is {number!r}, not a number"
    # 156 sat in 2025; anything below it means we are reading the wrong document.
    assert int(number) >= CLOSED_THING, f"current þing reported as {number} — implausibly old"

    assert thing.find("þingsetning") is not None, "current þing has no <þingsetning>"


def test_member_roster_shape(http):
    root = _xml(http, "thingmenn/", {"lthing": CLOSED_THING})

    assert root.tag == "þingmannalisti", f"root is <{root.tag}>"
    members = root.findall("þingmaður")
    # 63 seats, plus every substitute who sat — never fewer than the seat count.
    assert len(members) >= 63, f"þing {CLOSED_THING} roster has only {len(members)} people"

    first = members[0]
    assert first.attrib.get("id", "").isdigit(), f"<þingmaður id> is {first.attrib.get('id')!r}"
    assert first.findtext("nafn"), "roster entry has no <nafn>"


def test_thingseta_carries_party_and_constituency(http):
    """The only route to party affiliation — no other endpoint exposes it."""
    root = _xml(http, "thingmenn/thingmadur/thingseta/", {"nr": 1261})

    setur = root.findall(".//þingseta")
    assert setur, f"no <þingseta> entries; got {[c.tag for c in root]}"

    # Party may legitimately be absent on an individual spell, so require it
    # somewhere in the MP's history rather than on the first row.
    assert any(s.find("þingflokkur") is not None for s in setur), "no <þingflokkur> in any spell"
    assert any(s.find("kjördæmi") is not None for s in setur), "no <kjördæmi> in any spell"


def test_vote_list_still_marks_recorded_ballots(http):
    """The <nánar><xml> link is how the script decides which votes to fetch.

    Roughly half of a parliament's vote events are the Speaker declaring a
    matter advanced, with no ballot; those carry no detail link. If that link
    ever disappears the script would fetch nothing at all, silently.
    """
    root = _xml(http, "atkvaedagreidslur/", {"lthing": CLOSED_THING})

    assert root.tag == "atkvæðagreiðslur", f"root is <{root.tag}>"
    events = root.findall("atkvæðagreiðsla")
    assert events, f"þing {CLOSED_THING} returned zero vote events"

    with_detail = [e for e in events if e.find("nánar/xml") is not None]
    assert with_detail, "no vote event carries a <nánar><xml> detail link"

    first = events[0]
    for attr in ("atkvæðagreiðslunúmer", "þingnúmer", "málsnúmer", "málsflokkur"):
        assert attr in first.attrib, f"<atkvæðagreiðsla> lost @{attr}; has {sorted(first.attrib)}"


def test_vote_detail_carries_per_mp_ballots(http):
    """The flagship table.

    Vote 67864 is on closed þing 156 (so it is frozen) and is deliberately
    chosen as one with a recorded per-MP ballot. The probe checks the XML
    contract, not a row count that could change after a data correction.
    """
    root = _xml(http, "atkvaedagreidslur/atkvaedagreidsla/", {"numer": 67864})

    assert root.tag == "atkvæðagreiðsla", f"root is <{root.tag}>"

    ballots = root.findall("atkvæðaskrá/þingmaður")
    assert ballots, "no <atkvæðaskrá><þingmaður> — per-MP vote records are gone"

    first = ballots[0]
    assert first.attrib.get("id", "").isdigit(), "ballot <þingmaður> has no numeric @id"
    assert first.findtext("nafn"), "ballot <þingmaður> has no <nafn>"
    assert first.findtext("atkvæði"), "ballot <þingmaður> has no <atkvæði>"

    votes = {b.findtext("atkvæði") for b in ballots}
    # Spaced here — the *element* in <samantekt> is `greiðirekkiatkvæði`, the
    # *value* in <atkvæðaskrá> is `greiðir ekki atkvæði`. See SKILL.md caveat 15.
    known = {"já", "nei", "greiðir ekki atkvæði", "boðaði fjarvist", "fjarverandi"}
    assert votes <= known, f"unknown <atkvæði> value(s): {sorted(votes - known)}"

    # Nested <niðurstaða> inside <niðurstaða> — caveat 8.
    assert root.findtext("niðurstaða/niðurstaða"), "vote result <niðurstaða> missing"


def test_matter_list_shape(http):
    root = _xml(http, "thingmalalisti/", {"lthing": CLOSED_THING})

    assert root.tag == "málaskrá", f"root is <{root.tag}>"
    matters = root.findall("mál")
    assert matters, f"þing {CLOSED_THING} returned zero matters"

    first = matters[0]
    assert first.attrib.get("málsflokkur") in {"A", "B"}, (
        f"málsflokkur is {first.attrib.get('málsflokkur')!r}, expected A or B"
    )
    assert first.findtext("málsheiti"), "matter has no <málsheiti>"


def test_committee_members_shape(http):
    root = _xml(http, "nefndir/nefndarmenn/", {"lthing": CLOSED_THING})

    assert root.tag == "nefndarmenn", f"root is <{root.tag}>, expected <nefndarmenn>"
    committee = root.find("nefnd")
    assert committee is not None, "no <nefnd> child"
    assert committee.attrib.get("id", "").isdigit(), "<nefnd> has no numeric @id"
    assert committee.findtext("heiti"), "<nefnd> has no <heiti>"

    member = committee.find("nefndarmaður")
    assert member is not None, "<nefnd> has no <nefndarmaður>"
    assert member.attrib.get("id", "").isdigit(), "<nefndarmaður> has no numeric @id"
    assert member.findtext("nafn"), "<nefndarmaður> has no <nafn>"


def test_sittings_shape(http):
    root = _xml(http, "thingfundir/", {"lthing": CLOSED_THING})

    assert root.tag == "þingfundir", f"root is <{root.tag}>, expected <þingfundir>"
    sitting = root.find("þingfundur")
    assert sitting is not None, "no <þingfundur> child"
    assert sitting.attrib.get("númer", "").isdigit(), "<þingfundur> has no numeric @númer"
    assert sitting.find("hefst") is not None, "<þingfundur> has no <hefst>"
    assert sitting.findtext("fundursettur"), "<þingfundur> has no <fundursettur>"


def test_speeches_shape(http):
    # A single historical day keeps the payload small and the document stable.
    root = _xml(http, "raedulisti/", {"dagur": "20250218"})

    assert root.tag == "ræðulisti", f"root is <{root.tag}>, expected <ræðulisti>"
    speech = root.find("ræða")
    assert speech is not None, "no <ræða> child"
    assert speech.find("ræðumaður") is not None, "<ræða> has no <ræðumaður>"
    assert speech.findtext("dagur"), "<ræða> has no <dagur>"
    assert speech.findtext("ræðahófst"), "<ræða> has no <ræðahófst>"
    assert speech.findtext("ræðulauk"), "<ræða> has no <ræðulauk>"

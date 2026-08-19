"""Offline unit tests for scripts/skodanakannanir.py.

No network, no Playwright: the module imports playwright lazily inside
`fetch_ruv_article` only, so importing the module is safe. These tests
pin the real, verified behavior of the prose/chart/methodology/topic
parsers — see .agents/skills/skodanakannanir/SKILL.md and its eval/
baseline-round*.json for the evidence trail behind each rule.

Run: uv run pytest tests/test_skodanakannanir.py -q
"""
from __future__ import annotations

from scripts import skodanakannanir as s


# --------------------------------------------------------------------------
# _canonicalize_chart_answer — Highcharts aria-label parsing
# --------------------------------------------------------------------------


def test_canonicalize_chart_answer_known_party():
    """Chart aria-labels carry the party name + percent; the party is
    canonicalized (Samfylkingin → Samfylking) and flagged recognized."""
    assert s._canonicalize_chart_answer("Samfylking, 22.2%.") == ("Samfylking", True)


def test_canonicalize_chart_answer_known_party_full_legal_name():
    """Full legal names used by some charts canonicalize too."""
    assert s._canonicalize_chart_answer("Sjálfstæðisflokkur, 19.3%.") == (
        "Sjálfstæðisflokkur",
        True,
    )


def test_canonicalize_chart_answer_non_party_catchall():
    """'Önnur framboð' is a confirmed non-party catch-all bucket — dropped
    (None) but recognized, never passed through as an unknown party."""
    assert s._canonicalize_chart_answer("Önnur framboð") == (None, True)
    assert s._canonicalize_chart_answer("Aðrir listar") == (None, True)


def test_canonicalize_chart_answer_unknown_label_passthrough():
    """A label matching no known party and no catch-all is kept as-is and
    flagged unrecognized — surface an uncatalogued party, don't drop it."""
    assert s._canonicalize_chart_answer("Nýr Flokkur") == ("Nýr Flokkur", False)


# --------------------------------------------------------------------------
# extract_prose_poll_figures — party-support prose parsing
# --------------------------------------------------------------------------


def test_prose_poll_figures_current_poll_cue():
    """'stendur' is a _POLL_CUE_RE verb; 'nú' marks the current figure;
    'um' is captured as the approx marker."""
    results, skipped = s.extract_prose_poll_figures(
        ["Samfylkingin stendur nú í um 25% fylgi"]
    )
    assert skipped == []
    assert results == [
        {"party": "Samfylking", "pct": 25.0, "approx": True, "source": "prose"}
    ]


def test_prose_poll_figures_historical_sentence_skipped():
    """'fékk' is a _HISTORICAL_CUE_RE verb (simple past, real election
    result) — with no poll cue the sentence is skipped entirely, never
    guessed as a current poll figure."""
    results, skipped = s.extract_prose_poll_figures(
        ["Sjálfstæðisflokkurinn fékk 30% í kosningunum"]
    )
    assert results == []
    assert len(skipped) == 1
    assert skipped[0].startswith("[historical, no poll cue]")


def test_prose_poll_figures_trend_cue_extracts_current_value():
    """'úr X í Y' (_TREND_CUE_RE) stands in for a poll verb; the current
    (second) value wins. The verified real phrasing repeats 'prósent' on
    both numbers — the bare 'fór úr 6,7 í 5,3 prósent' form has only ONE
    _PERCENT_RE match and is skipped as ambiguous (see the module comment
    at _TREND_CUE_RE)."""
    results, skipped = s.extract_prose_poll_figures(
        ["Fylgi Framsóknarflokksins fór úr 6,7 prósentum í 5,3 prósent"]
    )
    assert skipped == []
    assert results == [
        {
            "party": "Framsóknarflokkur",
            "pct": 5.3,
            "approx": False,
            "source": "prose",
        }
    ]


def test_prose_poll_figures_trend_cue_bare_form_ambiguous():
    """The bare trend form is genuinely ambiguous to the parser (documented
    behavior, not a bug): it skips rather than guessing which number is
    current."""
    results, skipped = s.extract_prose_poll_figures(
        ["Fylgi Framsóknarflokksins fór úr 6,7 í 5,3 prósent"]
    )
    assert results == []
    assert skipped[0].startswith("[trend cue but no verb, single number, ambiguous]")


def test_prose_poll_figures_no_poll_cue_skipped():
    """A sentence with a number but no poll/trend cue is logged and
    skipped, never guessed."""
    results, skipped = s.extract_prose_poll_figures(
        ["Samfylkingin hlaut 30% í síðustu könnun"]
    )
    assert results == []
    assert skipped[0].startswith("[no poll cue]")


# --------------------------------------------------------------------------
# extract_esb_prose_figures — EU-membership answer parsing
# --------------------------------------------------------------------------


def test_esb_prose_figures_ja_nei_okvedin():
    """A já/nei/óákveðin sentence with equal answer/percent counts pairs
    positionally; each answer becomes a row."""
    results, skipped = s.extract_esb_prose_figures(
        ["48,5% svarenda segjast já, 48,5% nei og 1% óákveðin"]
    )
    assert skipped == []
    assert [r["party"] for r in results] == ["Já", "Nei", "Óákveðin"]
    assert [r["pct"] for r in results] == [48.5, 48.5, 1.0]


def test_esb_prose_figures_single_answer_with_historical_marker():
    """'í dag' vs 'í fyrra' (visir-20262869821): the current figure (46) is
    picked over the year-ago comparison (39,8) by current-vs-historical
    marker ranking."""
    results, skipped = s.extract_esb_prose_figures(
        [
            "46 prósent segjast vera andvíg aðild í dag en sá fjöldi var "
            "39,8 prósent þegar könnunin var framkvæmd á svipuðum tíma í fyrra."
        ]
    )
    andvigt = [r for r in results if r["party"] == "Andvígt"]
    assert andvigt and andvigt[0]["pct"] == 46.0


def test_esb_prose_figures_a_moti_ballot_phrasing():
    """visir-20262921428 (Gallup þjóðarpúls, 2026-08-15): the ballot pair is
    "greiða atkvæði með" / "á móti", with no já or nei word anywhere. Before
    "á móti" was a recognized Nei phrasing this was one answer term against
    two numbers, and nearest-gap attached the number four characters away
    (48,5 — the Nei figure) to the lone Já match, publishing the poll
    backwards."""
    results, skipped = s.extract_esb_prose_figures(
        [
            "Samkvæmt honum er svo mjótt á munum fylkinganna að hann er ekki "
            "tölfræðilega marktækur en 51,5% þeirra sem tóku afstöðu sögðust "
            "ætla að greiða atkvæði með og 48,5% þeirra á móti."
        ]
    )
    assert [(r["party"], r["pct"]) for r in results] == [("Já", 51.5), ("Nei", 48.5)]


def test_esb_prose_figures_a_moti_connective_not_an_answer():
    """"Á móti kemur að ..." is the discourse connective ("on the other
    hand"), not a ballot answer — it must not create a Nei row."""
    results, _ = s.extract_esb_prose_figures(
        ["Á móti kemur að 30 prósent aðspurðra eru andvíg aðildarviðræðum."]
    )
    assert [(r["party"], r["pct"]) for r in results] == [("Andvígt", 30.0)]


def test_esb_prose_figures_declined_to_answer_singular_verb():
    """A percentage takes a singular verb in Icelandic ("1% vildi ekki
    svara", visir-20262921428). With only the plural "vildu" recognized,
    "óákveðin" stood alone against two numbers and nearest-gap took the 1%
    that FOLLOWS the label over the 7% that precedes it."""
    results, _ = s.extract_esb_prose_figures(
        ["Af þeim sem svöruðu könnuninni voru 7% enn óákveðin og 1% vildi ekki svara."]
    )
    assert [(r["party"], r["pct"]) for r in results] == [("Óákveðin", 7.0)]


def test_esb_prose_figures_nato_excluded():
    """NATO sentences use the same hlynnt/andvíg vocabulary about a
    different question — excluded, not extracted as EU-membership answers."""
    results, skipped = s.extract_esb_prose_figures(
        ["72 prósent aðspurðra eru jákvæð gagnvart aðild að varnarbandalaginu."]
    )
    assert results == []
    assert skipped[0].startswith("[off-topic — NATO or euro-adoption question")


# --------------------------------------------------------------------------
# extract_methodology — sample size, response rate, field dates
# --------------------------------------------------------------------------


def test_methodology_sample_size_and_response_rate():
    """Verified Vísir phrasing (baseline round 4): 'Heildarúrtak var 12.102
    og þátttökuhlutfall 38,5 prósent.' — 12.102 (thousand-separator stripped)
    and 38.5 both extract."""
    meta = s.extract_methodology(
        ["Heildarúrtak var 12.102 og þátttökuhlutfall 38,5 prósent."]
    )
    assert meta["sample_size"] == 12102
    assert meta["response_rate_pct"] == 38.5


def test_methodology_second_verified_phrasing():
    """Verified VB phrasing: 'Í úrtaki voru 3.406 ... en þátttökuhlutfall
    var 44,7%.'"""
    meta = s.extract_methodology(
        ["Í úrtaki voru 3.406 manns en þátttökuhlutfall var 44,7%."]
    )
    assert meta["sample_size"] == 3406
    assert meta["response_rate_pct"] == 44.7


def test_methodology_response_rate_only_phrasing():
    """'svarhlutfall' alone is matched by _RESPONSE_RATE_RE regardless of
    the sample-size phrasing around it; the Maskínu-style 'meðal 1.765 manna
    þjóðgáttarhóps' phrasing is NOT a _SAMPLE_SIZE_RE form, so sample_size
    stays None (real behavior — only heildarúrtak / 'í úrtaki voru' forms
    resolve)."""
    meta = s.extract_methodology(
        ["Framkvæmd af Maskínu meðal 1.765 manna þjóðgáttarhóps, svarhlutfall 38,5%"]
    )
    assert meta["sample_size"] is None
    assert meta["response_rate_pct"] == 38.5


def test_methodology_fielded_note():
    """Field dates are captured as a note (not parsed to dates — documented
    gap); Icelandic ordinal dates must not truncate at the first period."""
    meta = s.extract_methodology(
        ["Könnunin var framkvæmd dagana 5. til 31. janúar 2026."]
    )
    assert meta["sample_size"] is None
    assert meta["response_rate_pct"] is None
    assert meta["fielded_note"] == "5. til 31. janúar 2026"


def test_methodology_fielded_note_without_year():
    """visir-20262920711 (Maskína, 2026-08-13) ends the range at the month:
    "Könnunin var gerð dagana 7. til 11. ágúst og svöruðu 1.205 manns." The
    year-terminated pattern ran past it and matched nothing at all."""
    meta = s.extract_methodology(
        ["Könnunin var gerð dagana 7. til 11. ágúst og svöruðu 1.205 manns."]
    )
    assert meta["fielded_note"] == "7. til 11. ágúst"


def test_methodology_fielded_note_range_crossing_a_month():
    """visir-20262838574: "dagana 21. janúar til 2. febrúar" names two
    months, and a pattern that stops at the first one records half the field
    period — a truncation that looks like a valid answer."""
    meta = s.extract_methodology(
        [
            "Könnunin var gerð dagana 21. janúar til 2. febrúar. "
            "1.672 voru í úrtaki og var þátttökuhlutfallið 48,8%."
        ]
    )
    assert meta["fielded_note"] == "21. janúar til 2. febrúar"
    assert meta["sample_size"] == 1672
    assert meta["response_rate_pct"] == 48.8


def test_methodology_sample_size_bare_urtaksstaerd():
    """visir-20262866089: Gallup writes the bare compound "úrtaksstærð
    2.198"; the heildarúrtak-only stem matched nothing."""
    meta = s.extract_methodology(
        [
            "Könnun Gallup var framkvæmd dagana 19. til 31. mars. Svarendur "
            "voru 817 talsins og úrtaksstærð 2.198. Nam þátttökuhlutfall því "
            "37,2 prósentum."
        ]
    )
    assert meta["sample_size"] == 2198
    assert meta["fielded_note"] == "19. til 31. mars"


def test_methodology_sample_size_not_taken_from_bare_mention():
    """"voru í úrtaki og var þátttökuhlutfallið 48,8%" mentions the sample
    with no size after it — the widened stem must not pull the response rate
    in as a sample size."""
    meta = s.extract_methodology(["Þau voru í úrtaki og var þátttökuhlutfallið 48,8%."])
    assert meta["sample_size"] is None
    assert meta["response_rate_pct"] == 48.8


def test_methodology_fielded_note_subject_is_not_konnunin():
    """ruv-483977 writes the same construction with a different subject:
    "Nýi þjóðarpúlsinn var gerður dagana 1.–13. ágúst." The pattern anchors
    on the verb phrase, not on "Könnunin"."""
    meta = s.extract_methodology(
        [
            "Nýi þjóðarpúlsinn var gerður dagana 1.–13. ágúst.",
            "Í nýjum þjóðarpúlsi var heildarúrtaksstærð 4.128. Þátttökuhlutfall var 41,9%.",
        ]
    )
    assert meta["fielded_note"] == "1.–13. ágúst"
    assert meta["sample_size"] == 4128
    assert meta["response_rate_pct"] == 41.9


# --------------------------------------------------------------------------
# _guess_topic — discovery-time ESB vs party-support classification
# --------------------------------------------------------------------------


def test_guess_topic_esb():
    """Standalone always-EU-specific terms trigger 'esb'."""
    assert s._guess_topic("Meirihluti ætlar að segja já í ESB", "") == "esb"
    assert (
        s._guess_topic("Ný könnun um aðildarviðræður", "stærstur hluti hlynntur")
        == "esb"
    )
    assert s._guess_topic("", "Evrópusambandið og evrusvæðið") == "esb"


def test_guess_topic_parties():
    """Anything without an ESB anchor — including bare 'aðild' (NATO/union
    ambiguity) — defaults to 'parties'."""
    assert s._guess_topic("Samfylkingin stærst í nýrri könnun", "fylgi flokka") == (
        "parties"
    )
    assert s._guess_topic("Meirihluti hlynntur aðild", "") == "parties"
    assert (
        s._guess_topic(
            "Marktækur munur á fylgi Samfylkingar og Sjálfstæðisflokks",
            "Fylgi Samfylkingarinnar hækkar milli mánaða í Þjóðarpúlsi Gallup.",
        )
        == "parties"
    )


def test_guess_topic_referendum_campaign_vocabulary():
    """Once the referendum has a date, coverage stops naming its subject.
    All three headlines are real August 2026 poll articles that the
    EU-noun-only classifier filed as party support and never listed under
    --topic esb."""
    assert (
        s._guess_topic(
            "Hnífjafnt í nýrri könnun",
            "Ný könnun Gallup ... um afstöðu þeirra í komandi þjóðaratkvæðagreiðslu.",
        )
        == "esb"
    )
    assert (
        s._guess_topic(
            "Enginn marktækur munur á jáurum og neiurum",
            "Ögn fleiri eru hlynnt áframhaldandi viðræðum.",
        )
        == "esb"
    )
    assert (
        s._guess_topic(
            "Forskot Já-hliðarinnar mælist minna", "Ný könnun Maskínu."
        )
        == "esb"
    )

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

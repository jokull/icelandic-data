"""RÚV skoðanakannanir (opinion polls) — tag-page aggregator across pollsters.

Two-stage pipeline:
  1. `list`  — plain httpx GET of the tag page, parsed from the embedded
     __NEXT_DATA__ JSON blob (no browser needed; server-rendered).
  2. `fetch` — one article at a time via Playwright. Article bodies are
     client-side rendered (curl/httpx sees an empty shell), and the party
     support numbers live in a Highcharts bar chart whose bars carry a
     real `aria-label="<Party>, <pct>%."` attribute on each SVG <path> —
     that's the extraction target, not OCR or color-matching.

Usage:
    uv run python scripts/skodanakannanir.py list
    uv run python scripts/skodanakannanir.py list --scope reykjavik
    uv run python scripts/skodanakannanir.py fetch 479261
    uv run python scripts/skodanakannanir.py fetch --all --limit 20
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TAG_URL = "https://www.ruv.is/frettir/tag/skodanakonnun"
VISIR_TAG_URL = "https://www.visir.is/t/2296/skodanakannanir/{page}"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "skodanakannanir"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

REYKJAVIK_KEYWORDS = re.compile(r"reykjav[ií]k|borgarst[jó]órn|í borginni", re.IGNORECASE)

# Case-sensitive and stem-based on purpose: "Prósent" is both a pollster's
# proper name and the ordinary Icelandic word for "percent" ("prósent"),
# which appears in nearly every poll subtitle lowercase mid-sentence
# ("...prósentustigi á eftir"). Matching case-sensitively on the
# capitalized stem is what actually distinguishes the two.
_POLLSTER_RE = re.compile(r"\b(Maskín\w*|Prósent\w*|Gallup\w*|Félagsvísindastofnun\w*)\b")
_POLLSTER_CANONICAL = {
    "maskín": "Maskína",
    "prósent": "Prósent",
    "gallup": "Gallup",
    "félagsvísindastofnun": "Félagsvísindastofnun",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

# --- Prose fallback -----------------------------------------------------
# Not every poll article embeds a Highcharts chart (verified: articles
# 451831 and 428434, both Reykjavík polls, have zero chart <path> elements
# despite being full ~5,900-char articles). When there's no chart, the
# numbers only exist in prose, in sentences like:
#   "Sjálfstæðisflokkurinn fengi 29 prósent atkvæða..."          <- poll figure
#   "...og fékk þá 19 prósent atkvæða."                          <- 2022 election result, NOT a poll figure
# The distinguishing signal is verb mood, not proximity: "fengi"/"mælist"/
# "mælast"/"stæði" (conditional/present, hypothetical-if-election-were-now)
# mark a current poll number; "fékk"/"fengu" (simple past) mark a historical
# election result mentioned for comparison. This is a real, reliable
# Icelandic grammar distinction, not a heuristic guess.
_POLL_CUE_RE = re.compile(r"\b(mælist|mælast|fengi|fengju|stæði|stæðu|stendur|(?:er|eru)\s+með)\b")
_HISTORICAL_CUE_RE = re.compile(r"\b(fékk|fengu|(?:var|voru)\s+með)\b")

_PARTY_STEMS = [
    ("Sjálfstæðisflokkur", r"Sjálfstæðisflokk\w*"),
    ("Samfylking", r"Samfylking\w*"),
    ("Framsóknarflokkur", r"Framsókn(?:arflokk\w*)?"),
    ("Viðreisn", r"Viðreisn\w*"),
    # Chart aria-labels (verified: RÚV's Highcharts embeds) sometimes carry
    # the full legal name "Vinstrihreyfingin – grænt framboð" rather than
    # the short form — the dash-separated "hreyfingin ... grænt framboð"
    # span doesn't satisfy the original "Vinstri" + optional-whitespace +
    # "græn" adjacency requirement, so it silently failed to canonicalize
    # (see the Chart Label Canonicalization note further down). Stem is
    # "Vinstrihreyfing" (not "...hreyfingin") — checked the full BÍN
    # declension table (reference/party-inflections-bin.json) after an
    # earlier version of this fix only covered the bare nominative
    # "Vinstrihreyfingin," missing accusative/dative/genitive
    # ("Vinstrihreyfinguna"/"-unni"/"-arinnar") entirely; the shorter stem
    # + \w* covers all four via BÍN's own case suffixes.
    ("Vinstri græn", r"Vinstri\s*g?ræn\w*|\bVG\b|Vinstrihreyfing\w*\s*[-–]\s*grænt\s+framboð"),
    # BÍN (reference/party-inflections-bin.json): "Píratar" undergoes
    # u-umlaut (a→ö) in the dative plural — "Pírötum"/"Pírötunum" don't
    # contain the substring "Píra" at all, so the original "Píra\w*" would
    # silently miss a real, plausible construction like "fylgi hjá
    # Pírötum" ("support among Pirates").
    ("Píratar", r"Pír(?:a|ö)t\w*"),
    ("Miðflokkur", r"Miðflokk\w*"),
    ("Flokkur fólksins", r"Flokk\w*\s+fólksins"),
    ("Sósíalistaflokkur", r"Sósíalist\w*"),
    # Arnar Þór Jónsson's party — verified appearing twice independently in
    # real fetched data: a Prósent-poll RÚV chart (0.2%) and Heimildin's
    # prose text of an older Prósent poll (1.4%). Not a one-off.
    ("Lýðræðisflokkur", r"Lýðræðisflokk\w*"),
    # A distinct 2026 Reykjavík electoral alliance (Vinstri græn + Vor til
    # vinstri, formally named 2026-02-23), NOT a nickname for Vinstri græn —
    # confirmed against Wikipedia before adding this (see
    # reference/party-ontology-2026.json), after an initial wrong guess that
    # it was just VG's colloquial name almost got aliased in. It genuinely
    # polls differently from VG alone once the alliance existed. Verified
    # bug this stem fixes: a real Vísir sentence naming only "Vinstrið" and
    # "Viðreisn" together had its Vinstrið number silently misattributed to
    # Viðreisn (the only *recognized* party in the sentence). Case-sensitive
    # (no re.IGNORECASE on _PARTY_RE) is the only disambiguation from the
    # ordinary lowercase word "vinstrið" ("the left [wing]") — imperfect,
    # since Icelandic capitalizes sentence-initial words too, so a
    # sentence-initial *generic* use of the word carries the same risk. Not
    # as clean a fix as "Prósent" vs "prósent" for that reason; worth
    # rechecking if false positives show up in a Reykjavík-scope skip log.
    # BÍN (reference/party-inflections-bin.json): this word is always
    # definite, with a genuine stem change per case, not just an appended
    # suffix — nf/þf "Vinstrið", þgf "Vinstrinu", ef "Vinstrisins". The
    # original "Vinstrið\w*" only matched the first of those three (dative
    # and genitive contain no "ð" at all) — explicit enumeration instead
    # of a wildcard, word-bounded so it doesn't also match as a prefix of
    # "Vinstrihreyfingin"/"Vinstri græn".
    ("Vinstrið", r"\bVinstri(?:ð|nu|sins)\b"),
]
_PARTY_RE = re.compile("|".join(f"(?P<p{i}>{pat})" for i, (_, pat) in enumerate(_PARTY_STEMS)))
_PARTY_CANONICAL = {i: name for i, (name, _) in enumerate(_PARTY_STEMS)}

_APPROX_RE = re.compile(r"\b(rúm(?:t|lega)?|tæp(?:t|lega)?|um)\s+$")

# A sentence with no explicit party name and no aggregate marker inherits
# current_party (pronoun reference — "Flokkurinn fékk X en fengi nú Y").
# But "Samanlagt fylgi ríkisstjórnarflokkanna mælist 42 prósent" ALSO has no
# explicit single-party match (_PARTY_RE doesn't match "ríkisstjórnarflokkanna"
# or "flokkanna") and a poll-cue verb ("mælist") — verified this exact
# sentence, on a real Vísir article, wrongly inherited a stale current_party
# from two sentences earlier and got recorded as that party's number. Both
# "samanlagt" (combined/aggregate) and "flokkanna" (parties, genitive plural
# — "of the parties") are explicit signals that the number belongs to no
# single party, so the current_party fallback must not apply.
_AGGREGATE_RE = re.compile(r"\b(samanlagt|flokkanna)\b", re.IGNORECASE)

# RÚV's "skoðanakönnun" tag also catches leader-trust / job-approval / policy-
# opinion polls that are NOT party-fylgi polls at all, but phrase themselves
# with the exact same poll-cue verbs ("mælist", "stendur") and often
# reference a party only via its chairperson's title ("formaður
# Framsóknarflokksins") or a voter-subgroup breakdown ("meðal Pírata",
# "þeirra sem kusu Viðreisn") — both of which set/inherit current_party just
# like a genuine party-support sentence would. Verified as three independent
# real false positives, each a different RÚV article that is entirely about
# something other than party support: ruv-458088 ("traust" — trust in
# individual ministers: "Þeim sem bera lítið traust til hennar fjölgar ...
# úr 15 í 24 prósent" inherited a stale current_party from an earlier
# "Ráðherrar Flokks fólksins eru þeir sem flestir vantreysta" sentence);
# ruv-453144 ("ánægja" — satisfaction with the taxi market, broken down by
# which party each respondent voted for: "Minnst mælist hún í röðum
# fylgismanna Vinstri grænna, 61 prósent" and "Mest mælist ánægjan ... meðal
# Pírata" produced two bogus rows); ruv-458497 ("staðið sig vel/illa" — job-
# approval ratings for party leaders, where "Sigurður Ingi stendur sig litlu
# betur, 58 prósent segja hann hafa staðið sig illa" inherited current_party
# from a "formaður Framsóknarflokksins" mention two sentences earlier). None
# of these sentences are about a party's own support level, so a sentence
# whose actual topic is satisfaction/trust/approval must not be treated as a
# poll figure at all, regardless of which cue verb it happens to contain —
# same discipline as _AGGREGATE_RE, just for a different false-attribution
# shape. A second, related false-attribution shape — a genuine poll-cue verb
# ("mælist") firing on a voter-subgroup breakdown rather than the party's
# own figure — needs its own signal: "Minnst mælist hún í röðum fylgismanna
# Vinstri grænna, 61 prósent" (ruv-453144, same taxi-market-satisfaction
# article) still slipped through the topic words above because the pronoun
# "hún" refers back to "ánægjan" without restating it in this sentence —
# only "fylgismanna" (supporters of) marks it. "fylgismenn/kjósendur/kusu/
# kaus X" is never how a party's own support figure is phrased (that's
# always "flokkurinn/fylgi flokksins mælist X", the party as direct
# grammatical subject) — it's specifically the construction for "how does
# the subgroup who voted/supports X feel about topic Y", so it gets the
# same treatment. Checked against every verified real party-support
# sentence in the current regression set (451831, 428434, 467932, 468092,
# visir-20262884571, visir-20262904348) — none of them use any of this
# vocabulary.
# A third instance of the same failure class, found live testing the skill
# (visir-20262884487, a Vísir "kosningaspá" — election-forecast article by a
# named mathematician, Baldur Héðinsson, that models each candidate's
# individual PROBABILITY of winning a council seat from the underlying
# polls, not the party's own vote share). "líkur" (probability/odds) is the
# forecast's native unit, and it rides the exact same cue verbs as a real
# fylgi sentence: "Stefán Pálsson, þriðji maður Vinstrisins er með 53
# prósent líkur..." and "...Einar Þorsteinsson mælist með áttatíu prósent
# líkur..." both matched _POLL_CUE_RE ("er með" / "mælist með") and had an
# in-sentence party name, producing two bogus rows (Vinstrið: 53%,
# Framsóknarflokkur: 80%) for what are actually two individual candidates'
# seat-probabilities, not their parties' support. Two independent real
# occurrences in the same article — same evidence bar as adding a new cue.
#
# A fourth, related shape found in the same article: "Flokkurinn er með
# rúmlega ellefu prósentustiga forskot á Samfylkinguna" ("The party has
# just over an eleven-point LEAD over Samfylking") — "forskot" (lead) means
# the number is the GAP between two parties, belonging to neither party's
# own fylgi. It matched the real "er með" poll-cue verb with Samfylking as
# the only in-sentence party (the leading party is only a pronoun,
# "Flokkurinn"), producing a bogus Samfylking: 11% row (the party's real
# support that week was closer to 19-20%, confirmed by the same day's
# Maskína/Gallup polls). Most "prósentustig" (percentage-point) sentences
# elsewhere in the corpus are harmless — either correctly skipped as
# `[no poll cue]` (a plain fylgisaukning/fylgistap sentence, no poll verb)
# or incidentally deduped by the first-mention-wins rule because the same
# party's real figure was already recorded earlier in the article — but
# this one hit the one ordering where neither protection applied (the
# margin sentence was the party's first and only poll-cue+percent mention).
# Not just this one instance's luck: relying on incidental dedup ordering
# to hide a still-present false-attribution bug isn't something to leave
# in place once spotted. "prósentustig" (percentage point) alone is too
# broad to guard on, though — verified live: it broke a real regression
# article (428434's "Flokkurinn fengi 25,0 prósent, tæplega prósentustigi
# minna en..." is Samfylking's genuine 25% figure, with a harmless
# comparison-to-prior-polls clause in the same sentence). "forskot" (lead)
# is the actually load-bearing word — specific to the margin-between-two-
# parties construction, confirmed recurring (not this one article's
# phrasing): several other real Vísir article titles use the identical
# "mælist með N prósentustiga forskot á X" headline pattern.
_NON_SUPPORT_TOPIC_RE = re.compile(
    r"\b(ánægj\w*|óánægj\w*|traust\w*|vantreyst\w*|staðið\s+sig"
    r"|fylgismann\w*|kjósend\w*|kusu|kaus|líkur\w*|líkum"
    r"|forskot\w*)\b",
    re.IGNORECASE,
)

_ONES = {
    "núll": 0, "eitt": 1, "einn": 1, "tvö": 2, "tveir": 2, "þrjú": 3, "þrír": 3,
    "fjögur": 4, "fjórir": 4, "fimm": 5, "sex": 6, "sjö": 7, "átta": 8, "níu": 9,
    "tíu": 10, "ellefu": 11, "tólf": 12, "þrettán": 13, "fjórtán": 14,
    "fimmtán": 15, "sextán": 16, "sautján": 17, "átján": 18, "nítján": 19,
}
_TENS = {
    "tuttugu": 20, "þrjátíu": 30, "fjörutíu": 40, "fimmtíu": 50,
    "sextíu": 60, "sjötíu": 70, "áttatíu": 80, "níutíu": 90,
}
_NUMBER_WORD_RE = re.compile(
    r"\b(?:(?:" + "|".join(_TENS) + r")(?:\s+og\s+(?:" + "|".join(_ONES) + r"))?"
    r"|(?:" + "|".join(_ONES) + r"))\b(?:\s+og\s+hálf\w*)?",
    re.IGNORECASE,
)
_DIGIT_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# "úr X í Y" ("from X to Y") is a second, independently reliable current-value
# marker — verified on a real Vísir article comparing Gallup's new þjóðarpúls
# against Maskína's prior poll, sentence-by-sentence: "fór úr 6,7 prósentum í
# 5,3 prósent", "eykst ... úr 2,x prósentum í 4,3 prósent". Neither sentence
# contains any _POLL_CUE_RE word ("fór"/"eykst"/"minnkaði" aren't in that
# list) — so on their own they'd be silently skipped as "no poll cue" even
# though Y is unambiguous. Unlike "nú", this pattern also stands in for a
# poll cue by itself (see the has_poll_cue check in extract_prose_poll_figures),
# not just a tie-breaker between two already-cued numbers.
_TREND_CUE_RE = re.compile(
    r"úr\s+(?:\d+(?:[.,]\d+)?|" + "|".join(list(_TENS) + list(_ONES)) + r")"
    r"\s*,?\s*(?:prósent\w*\s+)?í\b"
)
# "NN prósent" or "NN%" — the number-word or digit immediately preceding
# "prósent"/"%", with an optional "rúm/tæp/um" approximation marker before it.
_PERCENT_RE = re.compile(
    r"(?P<approx>(?:rúm(?:t|lega)?|tæp(?:t|lega)?|um)\s+)?"
    r"(?P<num>\d+(?:[.,]\d+)?|(?:" + "|".join(list(_TENS) + list(_ONES)) + r")"
    r"(?:\s+og\s+(?:" + "|".join(_ONES) + r"))?(?:\s+og\s+hálf\w*)?)"
    r"\s*(?:prósent\w*|%)",
    re.IGNORECASE,
)


def _word_to_number(text: str) -> float:
    text = text.strip().lower()
    if re.match(r"^\d", text):
        half = " og hálf" in text
        base = float(_DIGIT_NUMBER_RE.match(text).group().replace(",", "."))
        return base + 0.5 if half else base
    half = "hálf" in text
    text = re.sub(r"\s+og\s+hálf\w*", "", text).strip()
    parts = text.split(" og ")
    if len(parts) == 2:
        value = _TENS[parts[0]] + _ONES[parts[1]]
    else:
        value = _TENS.get(text, _ONES.get(text))
    if value is None:
        raise ValueError(f"unparsed number word: {text!r}")
    return value + 0.5 if half else value


def _sentences(text: str) -> list[str]:
    # Icelandic uses standard sentence-final punctuation; good enough for
    # prose that's already been through a professional editor.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract_prose_poll_figures(paragraphs: list[str]) -> tuple[list[dict], list[str]]:
    """Party/percent pairs from prose, for articles with no chart.

    Verb mood distinguishes a current poll figure ("fengi", "mælist" —
    conditional/present, "if the election were held now") from a historical
    election result mentioned for comparison ("fékk", "fengu" — simple
    past). A sentence with a historical cue and no poll cue is skipped
    entirely, even if it has a percent number — that number belongs to a
    past election, not this poll. `current_party` carries the most recently
    named party across sentences (and paragraphs) so pronoun-only sentences
    ("Flokkurinn fékk X í kosningum en fengi nú Y") still resolve. "úr X í Y"
    (see `_TREND_CUE_RE`) is a second cue class entirely — trend framing
    ("fór úr 6,7 í 5,3 prósent") rather than a verb, and stands in for a poll
    cue on its own when no recognized verb is present.
    """
    results = []
    skipped = []
    current_party = None
    seen_parties: set[str] = set()

    for para in paragraphs:
        for sentence in _sentences(para):
            party_matches = list(_PARTY_RE.finditer(sentence))
            if party_matches:
                last = party_matches[-1]
                idx = next(i for i, g in last.groupdict().items() if g)
                current_party = _PARTY_CANONICAL[int(idx[1:])]

            percent_matches = list(_PERCENT_RE.finditer(sentence))
            if not percent_matches:
                continue

            if _NON_SUPPORT_TOPIC_RE.search(sentence):
                skipped.append(f"[non-support topic (trust/satisfaction/approval), not party fylgi] {sentence}")
                continue

            poll_cue_matches = list(_POLL_CUE_RE.finditer(sentence))
            historical_cue_matches = list(_HISTORICAL_CUE_RE.finditer(sentence))
            trend_cue_matches = list(_TREND_CUE_RE.finditer(sentence))
            if not poll_cue_matches and not trend_cue_matches:
                skipped.append(
                    f"[{'historical, no poll cue' if historical_cue_matches else 'no poll cue'}] {sentence}"
                )
                continue

            # "nú" (now) and "úr X í Y" (see _TREND_CUE_RE) are both more
            # specific and more reliably present markers for the current
            # figure than any fixed verb list — historical baselines and
            # trend framings get phrased too many distinct ways to enumerate
            # as verbs, but these two constructions are unambiguous wherever
            # they appear. When either is present with 2+ numbers, the
            # nearest number to the nearest such marker wins outright; the
            # other numbers in that sentence are not considered at all,
            # regardless of verb-cue proximity. `úr X í Y` always implies 2+
            # numbers by construction, so it's the sole cue for a sentence
            # with no recognized verb at all (e.g. "fór úr 6,7 í 5,3 prósent"
            # — "fór" isn't in _POLL_CUE_RE).
            current_value_markers = [m.start() for m in re.finditer(r"\bnú\b", sentence)]
            current_value_markers += [m.end() for m in trend_cue_matches]
            preferred = None
            if current_value_markers and len(percent_matches) > 1:
                preferred = min(
                    percent_matches,
                    key=lambda m: min(abs(m.start() - p) for p in current_value_markers),
                )

            # A sentence enumerating N parties and N percents in strict
            # left-to-right order ("Party1 með N1%, Party2 með N2%, Party3
            # N3%, ...") pairs each number with whichever party precedes it
            # — but nearest-GAP measurement (below) is fooled by connector-
            # word-length asymmetry: "Samfylking með 21,5%," puts more
            # characters between the number and ITS OWN party (the 5-char
            # " með ") than between the number and the NEXT party name (a
            # 2-char ", "), so nearest-gap silently picks the following
            # party instead. Verified on a real 9-party enumeration
            # (visir-20262884529, RÚV's Þjóðarpúls listing sentence quoted
            # in full) — nearest-gap swapped Samfylking's 21.5% onto
            # Vinstrið, Vinstrið's 11.3% onto Miðflokkur, and
            # Sósíalistaflokkur's 4.8% onto Framsóknarflokkur, and dropped
            # Samfylking and Sósíalistaflokkur from the output entirely.
            # When party-count equals percent-count (and there's more than
            # one of each), strict positional pairing is unambiguous and
            # correct — checked against the original nearest-gap motivating
            # case too (article 451831: "Sjálfstæðisflokkurinn ... 39
            # prósenta fylgi þar, ... Samfylkingin, mælist með 19 prósent"
            # positionally pairs identically to nearest-gap there, so this
            # doesn't trade one bug for another).
            positional_party = None
            if len(party_matches) == len(percent_matches) and len(party_matches) > 1:
                positional_party = dict(zip(percent_matches, party_matches))

            for pm in percent_matches:
                if preferred is not None and pm is not preferred:
                    continue

                if preferred is None:
                    if not poll_cue_matches:
                        # Only reachable via a trend_cue-only sentence
                        # ("fór úr X í Y") where _PERCENT_RE didn't pick up
                        # both numbers (e.g. "prósent" wasn't repeated on the
                        # first one) — so len(percent_matches) never grew
                        # past 1 and `preferred` never got set. There's no
                        # verb to fall back on; without a second number to
                        # rank against, don't guess which lone number this is.
                        skipped.append(f"[trend cue but no verb, single number, ambiguous] {sentence}")
                        continue
                    # A number belongs to a poll figure only if it's nearer a
                    # poll-cue verb ("fengi"/"mælist") than a historical-cue
                    # verb ("fékk"/"fengu") — distinguishes "fékk fimm... en
                    # fengi nú 14" (only 14 counts) from a sentence with no
                    # historical cue at all (every number counts).
                    nearest_poll_dist = min(abs(pm.start() - c.start()) for c in poll_cue_matches)
                    if historical_cue_matches:
                        nearest_hist_dist = min(abs(pm.start() - c.start()) for c in historical_cue_matches)
                        if nearest_hist_dist < nearest_poll_dist:
                            continue

                # Nearest party mention to *this* number, not just the first
                # party named anywhere in the sentence — comparison sentences
                # ("Sjálfstæðisflokkurinn ... 39%, ... Samfylkingin ... 19%")
                # otherwise misattribute the second number to the first party.
                # Gap between spans, not start-to-start: a long party name
                # immediately before the number (e.g. "Sjálfstæðisflokkurinn",
                # 21 chars) must not look farther away than a short one after
                # it just because start-to-start distance ignores span length.
                if party_matches:
                    if positional_party is not None:
                        party_match = positional_party[pm]
                    else:
                        def _gap(pmatch):
                            return max(0, max(pm.start() - pmatch.end(), pmatch.start() - pm.end()))

                        party_match = min(party_matches, key=_gap)
                    idx = next(i for i, g in party_match.groupdict().items() if g)
                    party = _PARTY_CANONICAL[int(idx[1:])]
                elif _AGGREGATE_RE.search(sentence):
                    party = None  # aggregate figure ("samanlagt fylgi flokkanna") — no single party owns it
                elif not poll_cue_matches:
                    # Trend-cue-only sentence (no recognized poll verb) with
                    # no party named in-sentence — pronoun/current_party
                    # carryover is too risky here without a verb anchoring
                    # the sentence to a poll figure at all. Verified false
                    # positive (ruv-458088, a leaders'-trust poll, not a
                    # party-support one): "Þeim sem bera lítið traust til
                    # hennar fjölgar allnokkuð, úr 15 prósentum í 24
                    # prósent" inherited a stale current_party ("Flokkur
                    # fólksins") set two sentences earlier by "Ráðherrar
                    # Flokks fólksins eru þeir sem flestir vantreysta" —
                    # about that party's ministers, not its poll number —
                    # producing a bogus "Flokkur fólksins: 24%" row for an
                    # individual minister's trust rating. Both real verified
                    # trend-cue examples (article 428434: "Fylgi
                    # Framsóknarflokksins fór úr 6,7 í 5,3 prósent",
                    # "Stuðningur við Sósíalistaflokkinn eykst úr 2,4 í 4,3
                    # prósent") name their party in-sentence, so this
                    # restriction costs nothing against evidence seen so far.
                    party = None
                else:
                    party = current_party

                if not party:
                    if _AGGREGATE_RE.search(sentence):
                        reason = "aggregate, no single party"
                    elif not poll_cue_matches:
                        reason = "trend cue, no party in sentence, no poll verb — pronoun fallback too risky"
                    else:
                        reason = "no party in context"
                    skipped.append(f"[{reason}] {sentence}")
                    continue

                if party in seen_parties:
                    # A party's first mention is its topline figure. Later
                    # re-mentions in the same article are sub-group /
                    # geographic breakdowns (verified: a district-level
                    # "39% east of Elliðaá" re-mention of a party whose
                    # citywide topline was already captured earlier) — not a
                    # correction, so don't overwrite.
                    skipped.append(f"[{party} already recorded, later mention ignored] {sentence}")
                    continue

                try:
                    pct = _word_to_number(pm.group("num"))
                except (ValueError, KeyError):
                    skipped.append(f"[unparsed number {pm.group('num')!r}] {sentence}")
                    continue

                results.append(
                    {"party": party, "pct": pct, "approx": bool(pm.group("approx")), "source": "prose"}
                )
                seen_parties.add(party)

    return results, skipped


# Methodology fields (sample size, response rate) — the highest-value gap
# named repeatedly across three eval rounds. Article-level facts, not
# per-party ones, so returned separately rather than folded into the
# party/pct rows. First-pass coverage of the two phrasings verified in real
# fetched articles so far:
#   "Heildarúrtak var 12.102 og þátttökuhlutfall 38,5 prósent."      (Vísir)
#   "Í úrtaki voru 3.406 ... en þátttökuhlutfall var 44,7%."          (VB, read manually this session)
# Not attempted: parsing field dates ("Könnunin var gerð dagana 5. til 31.
# janúar 2026") into structured start/end dates — date-range phrasing varies
# enough (". til ", ".–", month names) that a first pass risks silently
# mis-parsing rather than just missing; left as a documented gap rather than
# a half-built parser, consistent with not shipping something confidently
# wrong. `fielded_note`, if present, is the matched raw sentence fragment.
_SAMPLE_SIZE_RE = re.compile(
    r"(?:heildarúrtak\w*|í\s+úrtaki\s+voru)\s+(?:var\s+)?(\d[\d.,]*\d|\d)", re.IGNORECASE
)
_RESPONSE_RATE_RE = re.compile(
    r"(?:þátttöku|svar)hlutfall\w*\s*(?:\w+\s+){0,3}?(?:var\s+)?"
    r"(?:rétt\s+)?(?:rúm(?:lega)?\s+)?(\d+(?:[.,]\d+)?)\s*(?:prósent\w*|%)",
    re.IGNORECASE,
)
# Bounded word-count capture, not "up to the next period" — Icelandic
# ordinal dates ("5. til 31. janúar") contain periods that are NOT sentence
# boundaries, so "[^.]+\." truncated at "dagana 5." and silently dropped
# the actual date range. Verified live on a real VB sentence before fixing.
_FIELD_DATES_RE = re.compile(
    # Stop at the first 4-digit year, not a fixed token count — the earlier
    # {1,8}-token window over-captured into the *next* sentence on a real
    # article (a short date needs only ~3 tokens, so a generous window
    # swept up "Heildarúrtak var 12.102 og þátttökuhlutfall 38,5" too,
    # since nothing bounded it at the actual sentence end). A poll's field
    # dates always end with a year in every phrasing checked so far.
    r"[Kk]önnunin\s+var\s+(?:framkvæmd|gerð)\s+dagana\s+((?:\S+\s+)*?\d{4})", re.IGNORECASE
)


def extract_methodology(paragraphs: list[str]) -> dict:
    text = " ".join(paragraphs)
    sample_size = None
    m = _SAMPLE_SIZE_RE.search(text)
    if m:
        try:
            sample_size = int(m.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            sample_size = None

    response_rate = None
    m = _RESPONSE_RATE_RE.search(text)
    if m:
        response_rate = float(m.group(1).replace(",", "."))

    fielded_note = None
    m = _FIELD_DATES_RE.search(text)
    if m:
        fielded_note = m.group(1).rstrip(".").strip()

    return {"sample_size": sample_size, "response_rate_pct": response_rate, "fielded_note": fielded_note}


def _article_url(raw_url: str) -> str:
    """Article listing URLs use the nyr.ruv.is staging host; www.ruv.is serves the same content."""
    return raw_url.replace("nyr.ruv.is", "www.ruv.is").rstrip("/")


def _find_articles(node, out: list[dict]) -> list[dict]:
    if isinstance(node, dict):
        if node.get("__typename") == "Article" and "id" in node and node.get("title"):
            out.append(node)
        for v in node.values():
            _find_articles(v, out)
    elif isinstance(node, list):
        for v in node:
            _find_articles(v, out)
    return out


def _guess_scope(title: str, subtitle: str) -> str:
    text = f"{title} {subtitle or ''}"
    return "reykjavik" if REYKJAVIK_KEYWORDS.search(text) else "national"


def _guess_pollster(title: str, subtitle: str) -> str | None:
    text = f"{title} {subtitle or ''}"
    m = _POLLSTER_RE.search(text)
    if not m:
        return None
    for stem, canonical in _POLLSTER_CANONICAL.items():
        if m.group(1).lower().startswith(stem):
            return canonical
    return None


# Chart aria-labels — verified across both RÚV and Vísir Highcharts embeds —
# carry the party name as the chart tool's own label text, completely
# independent of _PARTY_RE: e.g. "Samfylkingin" (not "Samfylking"),
# "Vinstrihreyfingin - grænt framboð" (full legal name) and even
# "Sósíalistaflokkur Íslands" alongside plain "Sósíalistaflokkur" on
# different charts. The prose path always canonicalizes through
# _PARTY_CANONICAL; the chart path did not, at all, until this was added —
# found by inspecting raw fetched JSON across 6 chart-sourced articles and
# noticing party names varied by article for what was obviously the same
# party. Any cross-article aggregation (a trend command, a polling average —
# both already-identified gaps) would have silently split one party into
# several rows keyed on whichever label string that specific chart happened
# to use. "Önnur framboð" ("other lists") is a genuine non-party catch-all
# bucket some charts include — explicitly dropped, not passed through as an
# unknown party. A label that matches no known party AND isn't a recognized
# catch-all is kept as-is (better to surface an uncatalogued party than
# silently drop its data) but flagged, so it doesn't stay invisible forever.
_CHART_NON_PARTY_LABELS = {"önnur framboð", "aðrir", "aðrir listar", "annað"}


def _canonicalize_chart_party(raw_label: str) -> tuple[str | None, bool]:
    """Returns (party_name_or_None, was_recognized). party_name is None
    for confirmed non-party catch-all labels ("Önnur framboð")."""
    if raw_label.strip().lower() in _CHART_NON_PARTY_LABELS:
        return None, True
    m = _PARTY_RE.search(raw_label)
    if m:
        idx = next(i for i, g in m.groupdict().items() if g)
        return _PARTY_CANONICAL[int(idx[1:])], True
    return raw_label, False


def fetch_article_list() -> list[dict]:
    resp = httpx.get(TAG_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    m = _NEXT_DATA_RE.search(resp.text)
    if not m:
        raise RuntimeError(f"__NEXT_DATA__ not found on {TAG_URL} — page structure changed")
    data = json.loads(m.group(1))
    articles = _find_articles(data, [])

    seen = {}
    for a in articles:
        seen[a["id"]] = {
            "id": f"ruv-{a['id']}",
            "source": "ruv",
            "title": a["title"],
            "subtitle": a.get("subtitle"),
            "url": _article_url(a["url"]),
            "published_at": a.get("first_published_at"),
            "scope": _guess_scope(a["title"], a.get("subtitle")),
            "pollster": _guess_pollster(a["title"], a.get("subtitle")),
        }
    return sorted(seen.values(), key=lambda r: r["published_at"] or "", reverse=True)


# --- Vísir ----------------------------------------------------------------
# Unlike RÚV, Vísir's tag page is genuinely paginated — verified by fetching
# pages 1/5/10/20/40 of /t/2296/skodanakannanir/<page> and finding distinct,
# chronologically descending content all the way back to September 2021
# (page 20), with page 40 empty (end of history). No __NEXT_DATA__ blob
# here — this is server-rendered HTML with <article class="article-item">
# cards, so it's regex-parsed, not JSON-walked. The listing's own subtitle
# frequently states the headline poll number directly (e.g. "Sjálfstæðis-
# flokkurinn mælist með 24,9 prósenta fylgi..."), which is often enough for
# a "what's the latest" answer without visiting the article page at all.
_VISIR_ARTICLE_RE = re.compile(r'<article class="article-item[^"]*">(.*?)</article>', re.S)
_VISIR_LINK_RE = re.compile(r'href="(/g/[^"]+)"')
_VISIR_TITLE_RE = re.compile(r'<h2 class="article-item__title"><a[^>]*>([^<]+)</a></h2>')
_VISIR_TEXT_RE = re.compile(r'<p class="article-item__text">\s*([^<]+)')
_VISIR_TIME_RE = re.compile(r'<time[^>]*>([^<]+)</time>')
_VISIR_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})")


def _visir_id(url_path: str) -> str:
    # /g/20262876815d/andar-koldu-... -> visir-20262876815
    m = re.search(r"/g/(\d+)d?/", url_path)
    return f"visir-{m.group(1)}" if m else f"visir-{url_path}"


def _visir_date_to_iso(date_raw: str) -> str | None:
    m = _VISIR_DATE_RE.match(date_raw)
    if not m:
        return None
    day, month, year, hour, minute = (int(g) for g in m.groups())
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"


def fetch_visir_article_list(max_pages: int = 40, stop_before_year: int | None = None) -> list[dict]:
    from html import unescape

    seen = {}
    for page in range(1, max_pages + 1):
        resp = httpx.get(VISIR_TAG_URL.format(page=page), headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        resp.raise_for_status()
        blocks = _VISIR_ARTICLE_RE.findall(resp.text)
        if not blocks:
            break  # end of pagination (verified: page 40 returns 0 <article> blocks)

        page_had_recent_enough = False
        for block in blocks:
            link_m = _VISIR_LINK_RE.search(block)
            title_m = _VISIR_TITLE_RE.search(block)
            time_m = _VISIR_TIME_RE.search(block)
            if not (link_m and title_m and time_m):
                continue  # non-article card (ad slot, gallery, etc.) — skip, don't guess
            text_m = _VISIR_TEXT_RE.search(block)

            published_at = _visir_date_to_iso(time_m.group(1).strip())
            if stop_before_year and published_at and int(published_at[:4]) < stop_before_year:
                continue
            if published_at and (not stop_before_year or int(published_at[:4]) >= stop_before_year):
                page_had_recent_enough = True

            title = unescape(title_m.group(1)).replace("\xad", "").strip()
            subtitle = unescape(text_m.group(1)).replace("\xad", "").strip() if text_m else None
            url = "https://www.visir.is" + link_m.group(1)
            article_id = _visir_id(link_m.group(1))
            seen[article_id] = {
                "id": article_id,
                "source": "visir",
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "published_at": published_at,
                "scope": _guess_scope(title, subtitle),
                "pollster": _guess_pollster(title, subtitle),
            }

        if stop_before_year and not page_had_recent_enough:
            break  # every item on this page is older than the cutoff — pages are date-descending, so done

    return sorted(seen.values(), key=lambda r: r["published_at"] or "", reverse=True)


# Vísir article bodies are server-rendered — verified against a real article
# (visir-20262904348): plain httpx sees the full text, no Playwright needed
# (unlike RÚV, whose article bodies are client-side rendered and need a
# browser). No Highcharts/aria-label chart was found on that article either —
# just thorough, fully-written prose including methodology, so the prose
# path (reused as-is from extract_prose_poll_figures — it's Icelandic-grammar
# logic, not RÚV-specific) is the primary path here, not a fallback. The
# chart check runs first anyway in case some Vísir articles do embed one.
#
# The real content spans two HTML regions that must both be captured: a lead
# <p> right after an "<!-- ARTICLE SUMMARY -->" comment (outside the body
# div — verified this is where the headline number often lives, e.g.
# "Sjálfstæðisflokkurinn mælist með 24,9 prósenta fylgi..."), followed by
# <div itemprop="articleBody">, containing the rest as <p> tags. Both regions
# run up to the first <hr> after the summary marker, which reliably follows
# the last real paragraph (share buttons and the "RELATED NEWS" section come
# after it) — verified against the same article: exactly 10 <p> tags in that
# span, matching a full manual read.
_VISIR_SUMMARY_MARKER_RE = re.compile(r"ARTICLE SUMMARY.{0,20}-->", re.S)
_VISIR_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_VISIR_CHART_RE = re.compile(r'path[^>]*aria-label="([^"]*%[^"]*)"')


def fetch_visir_article(url: str) -> dict:
    from html import unescape

    resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    html = resp.text

    parties = []
    source = "chart"
    skipped: list[str] = []
    for label in _VISIR_CHART_RE.findall(html):
        m = re.match(r"^(.+?),\s*([\d.,]+)\s*%\.?$", label.strip())
        if not m:
            continue
        party, recognized = _canonicalize_chart_party(m.group(1).strip())
        if party is None:
            continue  # confirmed non-party catch-all label ("Önnur framboð")
        if not recognized:
            skipped.append(f"[unrecognized chart party label, kept as-is] {party!r}")
        parties.append({"party": party, "pct": float(m.group(2).replace(",", "."))})

    # Paragraphs are extracted unconditionally, not just on the prose
    # fallback path — methodology fields (sample size, response rate) live
    # in ordinary prose even on chart-sourced articles, which don't
    # otherwise touch the article body text at all.
    start_m = _VISIR_SUMMARY_MARKER_RE.search(html)
    if start_m:
        hr_m = re.search(r"<hr\s*/?>", html[start_m.end():])
        body_html = html[start_m.end():start_m.end() + hr_m.start()] if hr_m else html[start_m.end():]
    else:
        body_html = html  # marker missing (layout changed?) — fall back to whole page, worse but not silent

    paragraphs = []
    for raw_p in _VISIR_PARA_RE.findall(body_html):
        text = re.sub(r"<[^>]+>", " ", raw_p)
        text = unescape(text).replace("\xad", "").strip()
        if text:
            paragraphs.append(text)

    if not parties:
        prose_results, skipped = extract_prose_poll_figures(paragraphs)
        for r in prose_results:
            parties.append({"party": r["party"], "pct": r["pct"], "approx": r["approx"]})
        source = "prose" if prose_results else "none"

    methodology = extract_methodology(paragraphs)

    title_m = re.search(r"<title>([^<]*)</title>", html)
    page_title = unescape(title_m.group(1)).strip() if title_m else url

    return {
        "url": url,
        "page_title": page_title,
        "parties": parties,
        "source": source,
        "prose_skipped": skipped,
        "methodology": methodology,
    }


# --- Heimildin --------------------------------------------------------------
# No tag page — verified no discovery mechanism exists (no equivalent to
# RÚV/Vísir's tag pages). But heimildin.is/leit/ (search) works well as one:
# server-rendered HTML, real <article class="article-item"> cards, genuinely
# paginated via ?page=N. Regular articles need no auth at all — verified on 3
# full articles (2 poll stories + the Samherji investigation) rendering
# complete, comments and all, to a logged-out request. The trailing slash on
# /leit/ matters: the no-slash form 301-redirects there, and query params on
# the redirect target still work.
HEIMILDIN_SEARCH_URL = "https://heimildin.is/leit/"

_HEIMILDIN_ARTICLE_RE = re.compile(r'<article class="article-item[^"]*">(.*?)</article>', re.S)
_HEIMILDIN_LINK_RE = re.compile(r'href="(/grein/\d+/[^"]+)"')
_HEIMILDIN_TITLE_RE = re.compile(r'<h1 class="article-item__headline">([^<]+)</h1>')
_HEIMILDIN_TIME_RE = re.compile(r'<time class="article-item__pubdate" datetime="([^"]+)"')
_HEIMILDIN_SUBHEAD_RE = re.compile(
    r'<div class="article-item__subhead">.*?</time>\s*(.+?)\s*</div>', re.S
)


def _heimildin_id(url_path: str) -> str:
    # /grein/23196/sjalfstaedisflokkurinn-.../ -> heimildin-23196
    m = re.search(r"/grein/(\d+)/", url_path)
    return f"heimildin-{m.group(1)}" if m else f"heimildin-{url_path}"


def fetch_heimildin_article_list(
    query: str = "skoðanakönnun", max_pages: int = 20, stop_before_year: int | None = None
) -> list[dict]:
    from html import unescape

    seen = {}
    for page in range(1, max_pages + 1):
        params = {"q": query, "page": page} if page > 1 else {"q": query}
        resp = httpx.get(HEIMILDIN_SEARCH_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        resp.raise_for_status()
        blocks = _HEIMILDIN_ARTICLE_RE.findall(resp.text)
        if not blocks:
            break  # end of results

        page_had_recent_enough = False
        for block in blocks:
            link_m = _HEIMILDIN_LINK_RE.search(block)
            title_m = _HEIMILDIN_TITLE_RE.search(block)
            time_m = _HEIMILDIN_TIME_RE.search(block)
            if not (link_m and title_m and time_m):
                continue  # non-article card (ad slot, etc.) — skip, don't guess

            published_at = time_m.group(1).strip().replace(" ", "T") + ":00"
            if stop_before_year and int(published_at[:4]) < stop_before_year:
                continue
            if not stop_before_year or int(published_at[:4]) >= stop_before_year:
                page_had_recent_enough = True

            subhead_m = _HEIMILDIN_SUBHEAD_RE.search(block)
            title = unescape(title_m.group(1)).replace("\xad", "").strip()
            subtitle = unescape(subhead_m.group(1)).replace("\xad", "").strip() if subhead_m else None
            url = "https://heimildin.is" + link_m.group(1)
            article_id = _heimildin_id(link_m.group(1))
            seen[article_id] = {
                "id": article_id,
                "source": "heimildin",
                "title": title,
                "subtitle": subtitle,
                "url": url,
                "published_at": published_at,
                "scope": _guess_scope(title, subtitle),
                "pollster": _guess_pollster(title, subtitle),
            }

        if stop_before_year and not page_had_recent_enough:
            break  # pages are date-descending, so a whole stale page means we're done

    return sorted(seen.values(), key=lambda r: r["published_at"] or "", reverse=True)


def _hours_apart(a: str | None, b: str | None) -> float:
    from datetime import datetime

    if not a or not b:
        return float("inf")
    # RÚV timestamps carry a "Z" (UTC) suffix, Vísir's (from _visir_date_to_iso)
    # don't. Iceland has no DST and sits at UTC+0 year-round, so both are the
    # same wall-clock zone numerically — strip tzinfo after parsing rather
    # than reconcile offsets, so a naive/aware mismatch can't raise.
    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    return abs((fmt(a) - fmt(b)).total_seconds()) / 3600


def cross_reference_duplicates(articles: list[dict], window_hours: float = 48) -> list[str]:
    """Flag Vísir/Heimildin articles that almost certainly cover the same poll as a RÚV one.

    Deliberately conservative — the same discipline as the prose parser:
    when a match is ambiguous, leave both records alone rather than guess.
    Matches require *all three* of: same non-null pollster (exact string —
    "Maskína" only matches "Maskína", not a null-pollster article that might
    coincidentally be about the same poll), same scope, and published within
    `window_hours` of each other. A RÚV article with more than one candidate
    (from either other source) in that window is left unmerged and logged,
    not merged onto whichever happens to be closest in time — ambiguity here
    means a real editorial judgment call (which story is actually the RÚV
    twin?), not a `min()` away.

    RÚV is the anchor because it's the only source with actual number
    extraction wired up (see `fetch`) — Vísir and Heimildin are
    discovery-only, so "which article to treat as canonical" isn't a choice
    yet, it's just "the one we can extract from."

    Mutates matched records in place, adding `duplicate_of` (the RÚV
    article's id) and adds `also_reported_by` (a list of {source, id, url})
    on the matched RÚV article. Returns log lines for cases considered but
    not merged.
    """
    ruv_articles = [a for a in articles if a["source"] == "ruv" and a["pollster"]]
    other_articles = [a for a in articles if a["source"] != "ruv" and a["pollster"]]
    skipped = []

    for ruv in ruv_articles:
        candidates = [
            v
            for v in other_articles
            if v["pollster"] == ruv["pollster"]
            and v["scope"] == ruv["scope"]
            and _hours_apart(ruv["published_at"], v["published_at"]) <= window_hours
            and "duplicate_of" not in v  # an article matches at most one RÚV article
        ]
        if len(candidates) == 1:
            other = candidates[0]
            other["duplicate_of"] = ruv["id"]
            ruv.setdefault("also_reported_by", []).append(
                {"source": other["source"], "id": other["id"], "url": other["url"]}
            )
        elif len(candidates) > 1:
            skipped.append(
                f"[ambiguous, {len(candidates)} candidates] {ruv['id']} {ruv['title']!r} "
                f"({ruv['pollster']}, {ruv['published_at']}) matches: "
                + ", ".join(f"{c['source']}:{c['id']} ({c['published_at']})" for c in candidates)
            )

    return skipped


def cmd_list(args):
    articles = []
    if args.source in ("ruv", "all"):
        articles += fetch_article_list()
    if args.source in ("visir", "all"):
        articles += fetch_visir_article_list(stop_before_year=args.since)
    if args.source in ("heimildin", "all"):
        articles += fetch_heimildin_article_list(stop_before_year=args.since)

    dedupe_skipped = []
    if args.source == "all":
        dedupe_skipped = cross_reference_duplicates(articles)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RAW_DIR / "articles.json"
    out_file.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    shown = [
        a for a in articles
        if (not args.scope or a["scope"] == args.scope) and "duplicate_of" not in a
    ]
    n_cross_reported = sum(1 for a in articles if "duplicate_of" in a)
    summary = f"{len(shown)} distinct poll articles"
    if n_cross_reported:
        summary += f" ({n_cross_reported} articles merged as cross-reports of a RÚV poll)"
    if dedupe_skipped:
        summary += f", {len(dedupe_skipped)} ambiguous cross-reference(s) left unmerged (see below)"
    print(f"{summary} ({out_file} holds all {len(articles)})")
    for a in shown[: args.limit]:
        pollster = a["pollster"] or "?"
        also = f" [+{len(a['also_reported_by'])} more]" if a.get("also_reported_by") else ""
        print(f"  [{a['id']}] {(a['published_at'] or '?????????')[:10]} ({a['source']}, {a['scope']}, {pollster}) {a['title']}{also}")
    for line in dedupe_skipped:
        print(f"  {line}")


async def _scrape_article(url: str) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60_000)

        # Chart bars: SVG <path aria-label="Samfylking, 22.2%."> per party
        bars = await page.eval_on_selector_all(
            'path[aria-label*="%"]',
            "els => els.map(e => e.getAttribute('aria-label'))",
        )
        parties = []
        source = "chart"
        skipped: list[str] = []
        for label in bars:
            m = re.match(r"^(.+?),\s*([\d.,]+)\s*%\.?$", label.strip())
            if not m:
                continue
            party, recognized = _canonicalize_chart_party(m.group(1).strip())
            if party is None:
                continue  # confirmed non-party catch-all label ("Önnur framboð")
            if not recognized:
                skipped.append(f"[unrecognized chart party label, kept as-is] {party!r}")
            parties.append({"party": party, "pct": float(m.group(2).replace(",", "."))})

        # Scoped to .article-body, not all of <main>: the page footer/sidebar
        # carries unrelated "most read" and nav content that could
        # coincidentally contain party names. Fetched unconditionally, not
        # just on the prose fallback path — methodology fields (sample
        # size, response rate) live in ordinary prose even on chart-sourced
        # articles, which otherwise never touch the article body text.
        body_text = await page.eval_on_selector(".article-body", "el => el.innerText")
        paragraphs = [p for p in body_text.split("\n") if p.strip()]

        if not parties:
            # No chart on this article — fall back to prose. See
            # extract_prose_poll_figures() for why verb mood, not proximity,
            # decides which numbers are current poll figures — the
            # first-mention-wins dedup there (not the .article-body scoping
            # above) is what actually keeps embedded "related article"
            # teaser excerpts (rendered inline in .article-body, same as
            # real paragraphs) from overwriting this article's own topline
            # numbers.
            prose_results, skipped = extract_prose_poll_figures(paragraphs)
            for r in prose_results:
                parties.append({"party": r["party"], "pct": r["pct"], "approx": r["approx"]})
            source = "prose" if prose_results else "none"

        methodology = extract_methodology(paragraphs)

        title = await page.title()
        await browser.close()

    return {
        "url": url,
        "page_title": title,
        "parties": parties,
        "source": source,
        "prose_skipped": skipped,
        "methodology": methodology,
    }


def cmd_fetch(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    articles = json.loads((RAW_DIR / "articles.json").read_text(encoding="utf-8")) if (
        RAW_DIR / "articles.json"
    ).exists() else fetch_article_list()
    by_id = {a["id"]: a for a in articles}

    if args.all:
        targets = [a for a in articles if a["source"] in ("ruv", "visir")][: args.limit]
    elif args.article_id:
        # Accept a bare RÚV numeric id ("479261") for backwards compatibility
        # with every command documented before Vísir support existed, as
        # well as the explicit prefixed form ("ruv-479261" / "visir-...").
        article_id = args.article_id if "-" in args.article_id else f"ruv-{args.article_id}"
        if article_id not in by_id:
            print(f"Unknown article id {article_id} — run `list` first", file=sys.stderr)
            sys.exit(1)
        source = by_id[article_id]["source"]
        if source not in ("ruv", "visir"):
            print(
                f"{source.capitalize()} article number-extraction isn't implemented yet — "
                "list/discovery only for now. Read the article directly:\n"
                f"  {by_id[article_id]['url']}",
                file=sys.stderr,
            )
            sys.exit(1)
        targets = [by_id[article_id]]
    else:
        print("Provide an article id or --all", file=sys.stderr)
        sys.exit(1)

    rows = []
    failed = []
    for meta in targets:
        print(f"  fetching [{meta['id']}] {meta['title']} ...")
        # Vísir is server-rendered (plain httpx, see fetch_visir_article);
        # RÚV needs a browser (client-side rendered, see _scrape_article).
        # One article's failure (verified: a RÚV Playwright page.goto
        # TimeoutError, on a slow/unresponsive page 9 articles into a real
        # --all --limit 10 run) must not lose every already-fetched article
        # in this batch — before this try/except, an uncaught exception here
        # propagated straight out of cmd_fetch, skipping the CSV write
        # entirely; the individual {id}.json raw files for already-processed
        # articles survived (each is written inside this loop), but the
        # aggregated CSV did not exist at all afterward. Continue past a
        # single failure and still write whatever succeeded.
        try:
            result = (
                fetch_visir_article(meta["url"])
                if meta["source"] == "visir"
                else asyncio.run(_scrape_article(meta["url"]))
            )
        except Exception as exc:
            print(f"    FAILED: {type(exc).__name__}: {exc}")
            failed.append({"id": meta["id"], "url": meta["url"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not result["parties"]:
            print(f"    no chart and no prose figures extracted ({len(result['prose_skipped'])} sentences skipped)")
            continue
        print(f"    {len(result['parties'])} parties via {result['source']}"
              + (f", {len(result['prose_skipped'])} sentences skipped" if result["source"] == "prose" else ""))
        methodology = result.get("methodology") or {}
        for p in result["parties"]:
            rows.append(
                {
                    "article_id": meta["id"],
                    "published_at": meta["published_at"],
                    "scope": meta["scope"],
                    "pollster": meta["pollster"],
                    "title": meta["title"],
                    "party": p["party"],
                    "pct": p["pct"],
                    "approx": p.get("approx", False),
                    "source": result["source"],
                    "sample_size": methodology.get("sample_size"),
                    "response_rate_pct": methodology.get("response_rate_pct"),
                    "fielded_note": methodology.get("fielded_note"),
                }
            )
        (RAW_DIR / f"{meta['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if failed:
        print(f"  {len(failed)} article(s) failed and were skipped: {[f['id'] for f in failed]}")

    if not rows:
        print("No poll data extracted.")
        return

    df = pl.DataFrame(rows)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = PROCESSED_DIR / "skodanakannanir.csv"
    if out_file.exists():
        existing = pl.read_csv(out_file)
        df = pl.concat([existing, df], how="diagonal_relaxed").unique(
            subset=["article_id", "party"], keep="last"
        )
    df = df.sort(["published_at", "article_id", "party"])
    df.write_csv(out_file)
    print(f"{len(rows)} party-support rows written -> {out_file}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List poll articles from RÚV and/or Vísir")
    p_list.add_argument("--scope", choices=["national", "reykjavik"], default=None)
    p_list.add_argument("--source", choices=["ruv", "visir", "heimildin", "all"], default="ruv")
    p_list.add_argument(
        "--since", type=int, default=None,
        help="Earliest year to keep (Vísir only — paginates back through 2021; RÚV's tag window is already short)",
    )
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="Scrape party-support numbers from one or more articles")
    p_fetch.add_argument("article_id", type=str, nargs="?", default=None)
    p_fetch.add_argument("--all", action="store_true", help="Fetch every listed article")
    p_fetch.add_argument("--limit", type=int, default=10)
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

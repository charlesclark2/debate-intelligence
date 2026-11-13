"""The committed topic map, pinned where the LD topic changed (`v1-e32-t06-ld-de-extinction-taxonomy`).

The PM's ruling of 2026-11-05 asked for two pins. Every snapshot up to 2026-10-27 resolves exactly as
it did before the de-extinction topic and its tournament entry were added, whatever tournament a
disclosure names. And the 2026-11-03 snapshot splits by tournament: Florida Blue Key's disclosures,
its round robin among them, are on de-extinction, and every other disclosure is on no topic, as the
whole snapshot was before.

Every expected topic is written by hand from the coach's word, not read from the file. Tournament
names are public; none here is a school's.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from debate_core.domain.landscape import TopicMap
from debate_core.integrations.landscape.yaml_taxonomy_repository import TOPICS_FILE, load_topic_map

CONFIG = Path(__file__).resolve().parents[2] / "config" / "landscape"

NHI = "policy-2026-27-nhi"
SPACE_COLONIZATION = "ld-2026-sep-oct-space-colonization"
DE_EXTINCTION = "ld-2026-nov-dec-de-extinction"
DATA_CENTERS = "pf-2026-sep-oct-data-center-moratorium"

FLORIDA_BLUE_KEY = (
    "Florida Blue Key Speech and Debate Tournament",
    "Florida Blue Key",
    "FloridaBlueKey",
    "Blue Key",
    "FBK",
    "UF FBK",
    "Florida Blue Key Round Robin",
)
OTHER_TOURNAMENTS = ("National Speech and Debate Season Opener", "Ridgeline Cup", "Harbor City Classic")
EVERY_TOURNAMENT = (*FLORIDA_BLUE_KEY, *OTHER_TOURNAMENTS, None, "")


def expected_before_the_change(caselist: str, day: date) -> str | None:
    """What topics.yaml resolved before v1-e32-t06, by hand from its ranges then."""
    if caselist == "hspolicy26":
        return NHI if date(2026, 7, 1) <= day <= date(2027, 6, 30) else None
    if caselist == "hsld26":
        return SPACE_COLONIZATION if date(2026, 9, 1) <= day <= date(2026, 10, 31) else None
    if caselist == "hspf26":
        return DATA_CENTERS if date(2026, 9, 1) <= day <= date(2026, 10, 31) else None
    return None


@pytest.fixture(scope="module")
def topics() -> TopicMap:
    return load_topic_map(CONFIG / TOPICS_FILE)


@pytest.mark.parametrize("caselist", ["hspolicy26", "hsld26", "hspf26"])
def test_every_snapshot_through_2026_10_27_resolves_as_it_did_before(topics: TopicMap, caselist: str) -> None:
    day = date(2026, 6, 1)
    while day <= date(2026, 10, 27):
        expected = expected_before_the_change(caselist, day)
        resolved = topics.resolve(caselist, day)
        assert (
            resolved.topic_id if resolved else None,
            bool(resolved and resolved.tournament_entries_only),
        ) == (
            expected,
            False,
        ), day
        for tournament in EVERY_TOURNAMENT:
            disclosure = topics.resolve_disclosure(caselist, day, tournament, first_seen={})
            assert (disclosure.topic_id if disclosure else None) == expected, (day, tournament)
        day += timedelta(days=1)


@pytest.mark.parametrize("tournament", FLORIDA_BLUE_KEY)
def test_a_florida_blue_key_disclosure_in_the_2026_11_03_snapshot_is_on_de_extinction(
    topics: TopicMap, tournament: str
) -> None:
    resolved = topics.resolve_disclosure("hsld26", date(2026, 11, 3), tournament, first_seen={})
    assert resolved is not None
    assert resolved.topic_id == DE_EXTINCTION


@pytest.mark.parametrize("tournament", [*OTHER_TOURNAMENTS, None, ""])
def test_every_other_disclosure_in_the_2026_11_03_snapshot_is_on_no_topic(
    topics: TopicMap, tournament: str | None
) -> None:
    assert topics.resolve_disclosure("hsld26", date(2026, 11, 3), tournament, first_seen={}) is None


def test_the_2026_11_03_snapshot_is_on_de_extinction_only_through_its_tournament_entry(
    topics: TopicMap,
) -> None:
    resolved = topics.resolve("hsld26", date(2026, 11, 3))
    assert resolved is not None
    assert (resolved.topic_id, resolved.tournament_entries_only) == (DE_EXTINCTION, True)
    assert topics.resolve("hspf26", date(2026, 11, 3)) is None
    policy = topics.resolve("hspolicy26", date(2026, 11, 3))
    assert policy is not None
    assert (policy.topic_id, policy.tournament_entries_only) == (NHI, False)


@pytest.mark.parametrize("tournament", EVERY_TOURNAMENT)
def test_from_2026_11_10_every_hsld26_disclosure_is_on_de_extinction_by_its_range(
    topics: TopicMap, tournament: str | None
) -> None:
    for day in (date(2026, 11, 10), date(2026, 12, 29)):
        resolved = topics.resolve_disclosure("hsld26", day, tournament, first_seen={})
        assert resolved is not None
        assert resolved.topic_id == DE_EXTINCTION
    assert topics.resolve_disclosure("hsld26", date(2027, 1, 5), tournament, first_seen={}) is None


def test_the_tournament_entry_lists_only_the_two_public_spellings(topics: TopicMap) -> None:
    """The PM's ruling of 2026-11-05: bluekey and fbk, never a spelling one school wrote."""
    (entry,) = topics.topic(DE_EXTINCTION).tournaments
    assert (entry.caselist, entry.spellings, entry.effective_from, entry.effective_to) == (
        "hsld26",
        ("bluekey", "fbk"),
        date(2026, 11, 3),
        date(2026, 11, 3),
    )


# ------------------------------------------------------------------------------------------------
# Late disclosures on the earlier topic (`v1-e32-t51`, the PM's Q1 ruling of 2026-11-12)
# ------------------------------------------------------------------------------------------------

SEEN_IN_SEPTEMBER = {"ridgelinecup": date(2026, 9, 15), "harborcityclassic": date(2026, 9, 15)}
"""A spelling history in which every planted tournament was first seen before either LD topic changed."""


def test_only_hsld26s_de_extinction_range_moves_late_disclosures(topics: TopicMap) -> None:
    keyed = [
        (topic.id, one.caselist)
        for topic in topics.topics
        for one in topic.caselists
        if one.late_disclosures_on_earlier_topic
    ]
    assert keyed == [(DE_EXTINCTION, "hsld26")]
    cut = topics.late_cut("hsld26", date(2026, 11, 10))
    assert cut is not None
    assert (cut.earlier.id, cut.earlier.name, cut.range.effective_from) == (
        SPACE_COLONIZATION,
        "Space colonization",
        date(2026, 11, 6),
    )


def test_the_ld_topics_check_words_are_each_topics_own(topics: TopicMap) -> None:
    assert topics.topic(DE_EXTINCTION).check_words == ("de-extinct",)
    assert topics.topic(SPACE_COLONIZATION).check_words == ("space col", "coloniz")
    assert topics.topic(NHI).check_words == ()


@pytest.mark.parametrize("caselist", ["hspolicy26", "hsld26", "hspf26"])
def test_with_a_spelling_history_every_snapshot_before_2026_11_10_resolves_as_without_one(
    topics: TopicMap, caselist: str
) -> None:
    day = date(2026, 7, 7)
    while day < date(2026, 11, 10):
        for tournament in EVERY_TOURNAMENT:
            assert topics.resolve_disclosure(caselist, day, tournament, first_seen=SEEN_IN_SEPTEMBER) == (
                topics.resolve_disclosure(caselist, day, tournament, first_seen={})
            ), (day, tournament)
        day += timedelta(days=7)


def test_from_2026_11_10_a_late_hsld26_disclosure_is_on_space_colonization(topics: TopicMap) -> None:
    for day in (date(2026, 11, 10), date(2026, 12, 29)):
        late = topics.resolve_disclosure("hsld26", day, "Ridgeline Cup", first_seen=SEEN_IN_SEPTEMBER)
        fbk = topics.resolve_disclosure(
            "hsld26", day, "Florida Blue Key", first_seen={"floridabluekey": date(2026, 11, 3)}
        )
        assert late is not None and late.topic_id == SPACE_COLONIZATION
        assert fbk is not None and fbk.topic_id == DE_EXTINCTION


def test_policy_has_no_earlier_topic_and_never_moves(topics: TopicMap) -> None:
    day = date(2026, 7, 7)
    while day <= date(2027, 6, 29):
        assert topics.late_cut("hspolicy26", day) is None
        resolved = topics.resolve_disclosure(
            "hspolicy26", day, "Ridgeline Cup", first_seen={"ridgelinecup": date(2026, 1, 6)}
        )
        assert resolved is not None and resolved.topic_id == NHI
        day += timedelta(days=7)

"""A topic's tournament entries: a disclosure on a topic by its tournament, not its snapshot alone.

`v1-e32-t06-ld-de-extinction-taxonomy`, the PM's ruling of 2026-11-05: a disclosure resolves to (a) the
topic of a tournament entry covering its snapshot whose spelling its tournament text holds, then (b)
the topic of the range covering its snapshot, then (c) no topic. Every tournament name here is
invented; the expected topics are written by hand.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.landscape import TopicMap, tournament_key

OLD = "ld-sample-old-topic"
NEW = "ld-sample-new-topic"


def entry(name: str, spellings: list[str], start: str, end: str, caselist: str = "hsld99") -> dict[str, Any]:
    return {"caselist": caselist, "name": name, "spellings": spellings, "from": start, "to": end}


def ld_topic(topic_id: str, ranges: list[tuple[str, str]], *entries: dict[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": topic_id,
        "event": "LD",
        "caselists": [{"caselist": "hsld99", "from": start, "to": end} for start, end in ranges],
    }
    if entries:
        document["tournaments"] = list(entries)
    return document


HARBOR = entry("Harbor City Classic", ["harborcity", "hcc"], "2026-11-03", "2026-11-03")


def transition_map(*new_entries: dict[str, Any], old_entries: tuple[dict[str, Any], ...] = ()) -> TopicMap:
    return TopicMap.model_validate(
        {
            "schema_version": 1,
            "topics": [
                ld_topic(OLD, [("2026-09-01", "2026-10-31")], *old_entries),
                ld_topic(NEW, [("2026-11-06", "2026-12-31")], *new_entries),
            ],
        }
    )


def refusal(document: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as caught:
        TopicMap.model_validate(document)
    return str(caught.value)


def on(resolved: object) -> str | None:
    return getattr(resolved, "topic_id", None)


@pytest.mark.parametrize(
    ("tournament", "expected"),
    [
        ("Harbor City Classic", NEW),
        ("harbor-city", NEW),
        ("2026 HARBOR CITY Round Robin", NEW),
        ("HCC", NEW),
        ("Lakeside Open", None),
        ("Harbor", None),
        (None, None),
        ("", None),
    ],
)
def test_a_disclosure_in_the_entry_snapshot_is_on_the_entry_topic_only_when_its_text_holds_a_spelling(
    tournament: str | None, expected: str | None
) -> None:
    topics = transition_map(HARBOR)
    assert on(topics.resolve_disclosure("hsld99", date(2026, 11, 3), tournament, first_seen={})) == expected


def test_the_entry_snapshot_as_a_whole_is_on_the_entry_topic_and_says_only_the_entry_put_it_there() -> None:
    topics = transition_map(HARBOR)
    resolved = topics.resolve("hsld99", date(2026, 11, 3))
    assert resolved is not None
    assert resolved.topic_id == NEW
    assert resolved.tournament_entries_only is True
    by_range = topics.resolve("hsld99", date(2026, 11, 10))
    assert by_range is not None
    assert (by_range.topic_id, by_range.tournament_entries_only) == (NEW, False)


@pytest.mark.parametrize("tournament", ["Lakeside Open", "Harbor City Classic", None, ""])
def test_after_the_entry_window_every_disclosure_resolves_by_its_range(tournament: str | None) -> None:
    topics = transition_map(HARBOR)
    assert on(topics.resolve_disclosure("hsld99", date(2026, 11, 10), tournament, first_seen={})) == NEW
    assert on(topics.resolve_disclosure("hsld99", date(2026, 10, 27), tournament, first_seen={})) == OLD
    assert topics.resolve_disclosure("hsld99", date(2026, 8, 25), tournament, first_seen={}) is None


def test_entries_move_no_snapshot_the_ranges_already_resolve() -> None:
    plain = transition_map()
    with_entry = transition_map(HARBOR)
    day = date(2026, 7, 1)
    while day <= date(2027, 1, 31):
        if day != date(2026, 11, 3):
            assert with_entry.resolve("hsld99", day) == plain.resolve("hsld99", day), day
            for tournament in ("Harbor City Classic", "Lakeside Open", None):
                assert on(with_entry.resolve_disclosure("hsld99", day, tournament, first_seen={})) == on(
                    plain.resolve("hsld99", day)
                ), (day, tournament)
        day += timedelta(days=1)


def test_an_entry_of_another_caselist_moves_nothing_here() -> None:
    topics = transition_map(
        entry("Harbor City Classic", ["harborcity"], "2026-11-03", "2026-11-03", "hsld98")
    )
    assert topics.resolve("hsld99", date(2026, 11, 3)) is None
    assert (
        topics.resolve_disclosure("hsld99", date(2026, 11, 3), "Harbor City Classic", first_seen={}) is None
    )
    assert (
        on(topics.resolve_disclosure("hsld98", date(2026, 11, 3), "Harbor City Classic", first_seen={}))
        == NEW
    )


def test_an_older_topic_may_claim_a_late_disclosure_in_the_newer_topic_range() -> None:
    late = entry("Lakeside Open", ["lakeside"], "2026-11-10", "2026-12-31")
    topics = transition_map(HARBOR, old_entries=(late,))
    assert on(topics.resolve_disclosure("hsld99", date(2026, 11, 17), "Lakeside Open", first_seen={})) == OLD
    assert (
        on(topics.resolve_disclosure("hsld99", date(2026, 11, 17), "Harbor City Classic", first_seen={}))
        == NEW
    )
    assert on(topics.resolve("hsld99", date(2026, 11, 17))) == NEW


def test_an_entry_reaching_into_an_older_topic_range_is_refused() -> None:
    reaching = entry("Harbor City Classic", ["harborcity"], "2026-10-27", "2026-11-03")
    message = refusal(
        {
            "schema_version": 1,
            "topics": [
                ld_topic(OLD, [("2026-09-01", "2026-10-31")]),
                ld_topic(NEW, [("2026-11-06", "2026-12-31")], reaching),
            ],
        }
    )
    assert "reaches into ld-sample-old-topic's range" in message


def test_two_topics_entries_covering_one_snapshot_are_refused() -> None:
    late = entry("Lakeside Open", ["lakeside"], "2026-11-03", "2026-11-10")
    message = refusal(
        {
            "schema_version": 1,
            "topics": [
                ld_topic(OLD, [("2026-09-01", "2026-10-31")], late),
                ld_topic(NEW, [("2026-11-06", "2026-12-31")], HARBOR),
            ],
        }
    )
    assert "cover the same snapshots" in message


@pytest.mark.parametrize("spelling", ["Harbor", "harbor city", "harbor-city", ""])
def test_a_spelling_that_is_not_lower_case_letters_and_digits_is_refused(spelling: str) -> None:
    refusal(
        {
            "schema_version": 1,
            "topics": [
                ld_topic(
                    NEW,
                    [("2026-11-06", "2026-12-31")],
                    entry("Harbor", [spelling], "2026-11-03", "2026-11-03"),
                )
            ],
        }
    )


@pytest.mark.parametrize(
    "bad",
    [
        entry("Harbor City Classic", [], "2026-11-03", "2026-11-03"),
        entry("Harbor City Classic", ["harbor", "harbor"], "2026-11-03", "2026-11-03"),
        entry("Harbor City Classic", ["harbor"], "2026-11-10", "2026-11-03"),
        {**HARBOR, "dates": "2026-11-03"},
        {**HARBOR, "name": ""},
    ],
)
def test_a_malformed_entry_is_refused(bad: dict[str, Any]) -> None:
    refusal({"schema_version": 1, "topics": [ld_topic(NEW, [("2026-11-06", "2026-12-31")], bad)]})


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Harbor City Classic", "harborcityclassic"), ("2026-HCC (RR)", "2026hccrr"), (None, ""), ("  ", "")],
)
def test_tournament_text_is_reduced_to_lower_case_letters_and_digits(text: str | None, expected: str) -> None:
    assert tournament_key(text) == expected

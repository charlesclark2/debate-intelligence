"""The late-disclosure rule in the topic map (`v1-e32-t51`, the PM's Q1 ruling of 2026-11-12).

In a snapshot a newer topic's range covers, a disclosure whose tournament spelling was first seen before
that range began, and holds none of the newer topic's entry spellings, is on the earlier topic, when the
range's `late_disclosures_on_earlier_topic` key says so. The map mimics hsld26's: an older topic to
2026-10-31, a newer one from 2026-11-06 with a tournament entry for 2026-11-03 (`Harbor City`, as Florida
Blue Key), and a Policy caselist with one range. Every tournament is invented.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from debate_core.domain.landscape import (
    LateDisclosures,
    TopicMap,
    TopicResolution,
    first_seen_spellings,
)

LD, POLICY = "synthld26", "synthpol26"
OLD, NEW, POLICY_TOPIC, EARLIEST = "ld-old-topic", "ld-new-topic", "policy-topic", "ld-earliest-topic"
OCT_27, NOV_03, NOV_10, NOV_17 = date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 10), date(2026, 11, 17)

HISTORY = {
    "lakesideopen": date(2026, 9, 15),
    "pinecrestinvitational": NOV_03,
    "harborcityclassic": NOV_03,
    "harborcityrr": NOV_03,
    "novemberclassic": NOV_10,
}
"""Each spelling's first snapshot, as `first_seen_spellings` gives it for the store."""


def topics(
    *, key: bool = True, new_entry: dict[str, Any] | None = None, policy_key: bool = False
) -> TopicMap:
    entries = [
        {
            "caselist": LD,
            "name": "Harbor City Classic",
            "spellings": ["harborcity"],
            "from": NOV_03,
            "to": NOV_03,
        }
    ]
    if new_entry is not None:
        entries.append(new_entry)
    return TopicMap.model_validate(
        {
            "schema_version": 1,
            "topics": [
                {
                    "id": EARLIEST,
                    "event": "LD",
                    "caselists": [{"caselist": LD, "from": "2026-07-01", "to": "2026-08-31"}],
                },
                {
                    "id": OLD,
                    "event": "LD",
                    "label": "The old topic",
                    "check_words": ["old word"],
                    "caselists": [{"caselist": LD, "from": "2026-09-01", "to": "2026-10-31"}],
                },
                {
                    "id": NEW,
                    "event": "LD",
                    "check_words": ["new word"],
                    "caselists": [
                        {
                            "caselist": LD,
                            "from": "2026-11-06",
                            "to": "2026-12-31",
                            "late_disclosures_on_earlier_topic": key,
                        }
                    ],
                    "tournaments": entries,
                },
                {
                    "id": POLICY_TOPIC,
                    "event": "POLICY",
                    "caselists": [
                        {
                            "caselist": POLICY,
                            "from": "2026-07-01",
                            "to": "2027-06-30",
                            "late_disclosures_on_earlier_topic": policy_key,
                        }
                    ],
                },
            ],
        }
    )


def on(resolution: TopicResolution | None) -> str | None:
    return resolution.topic_id if resolution is not None else None


def test_in_the_2026_11_10_shape_late_spellings_move_and_an_entry_spelling_stays() -> None:
    map_ = topics()

    assert on(map_.resolve_disclosure(LD, NOV_10, "Lakeside Open", first_seen=HISTORY)) == OLD
    assert on(map_.resolve_disclosure(LD, NOV_10, "Pinecrest Invitational", first_seen=HISTORY)) == OLD
    assert on(map_.resolve_disclosure(LD, NOV_10, "Harbor City Classic", first_seen=HISTORY)) == NEW
    assert on(map_.resolve_disclosure(LD, NOV_10, "Harbor City RR", first_seen=HISTORY)) == NEW
    assert on(map_.resolve_disclosure(LD, NOV_10, "November Classic", first_seen=HISTORY)) == NEW
    assert on(map_.resolve_disclosure(LD, NOV_10, None, first_seen=HISTORY)) == NEW
    assert on(map_.resolve_disclosure(LD, NOV_10, "A spelling never seen", first_seen=HISTORY)) == NEW
    assert on(map_.resolve_disclosure(LD, NOV_17, "Lakeside Open", first_seen=HISTORY)) == OLD


def test_the_earlier_topic_is_the_caselists_range_just_before_not_any_earlier_one() -> None:
    map_ = topics()
    cut = map_.late_cut(LD, NOV_10)

    assert cut is not None
    assert (cut.topic.id, cut.range.effective_from, cut.earlier.id, cut.earlier.name) == (
        NEW,
        date(2026, 11, 6),
        OLD,
        "The old topic",
    )
    assert map_.topic(NEW).name == NEW


def test_no_snapshot_before_the_range_moves() -> None:
    with_key, without = topics(), topics(key=False)
    days = [date(2026, 7, 7), date(2026, 8, 25), date(2026, 9, 1), date(2026, 9, 15), OCT_27, NOV_03]
    texts = ["Lakeside Open", "Pinecrest Invitational", "Harbor City Classic", "November Classic", None]

    for day in days:
        for text in texts:
            assert on(with_key.resolve_disclosure(LD, day, text, first_seen=HISTORY)) == on(
                without.resolve_disclosure(LD, day, text, first_seen=HISTORY)
            ), (day, text)
            assert not with_key.is_late(LD, day, text, HISTORY)


def test_a_newer_topic_entry_always_wins_over_the_rule() -> None:
    entry = {"caselist": LD, "name": "Lakeside Open", "spellings": ["lakeside"], "from": NOV_10, "to": NOV_17}
    map_ = topics(new_entry=entry)

    assert on(map_.resolve_disclosure(LD, NOV_10, "Lakeside Open", first_seen=HISTORY)) == NEW
    assert not map_.is_late(LD, NOV_10, "Lakeside Open", HISTORY)
    assert on(map_.resolve_disclosure(LD, NOV_10, "Pinecrest Invitational", first_seen=HISTORY)) == OLD


def test_with_the_key_off_nothing_moves_but_the_late_disclosure_is_still_known() -> None:
    map_ = topics(key=False)

    for text in ("Lakeside Open", "Pinecrest Invitational", "Harbor City Classic", "November Classic", None):
        assert on(map_.resolve_disclosure(LD, NOV_10, text, first_seen=HISTORY)) == NEW
    assert map_.is_late(LD, NOV_10, "Lakeside Open", HISTORY)
    assert not map_.is_late(LD, NOV_10, "November Classic", HISTORY)


def test_policy_with_no_earlier_topic_never_moves() -> None:
    map_ = topics()
    history = {"lakesideopen": date(2026, 6, 2)}

    assert map_.late_cut(POLICY, NOV_10) is None
    assert not map_.is_late(POLICY, NOV_10, "Lakeside Open", history)
    assert on(map_.resolve_disclosure(POLICY, NOV_10, "Lakeside Open", first_seen=history)) == POLICY_TOPIC


def test_the_key_on_a_range_with_no_earlier_topic_is_refused() -> None:
    with pytest.raises(ValueError, match="no topic has a range of the caselist before it"):
        topics(policy_key=True)


def test_without_a_history_nothing_is_late() -> None:
    assert on(topics().resolve_disclosure(LD, NOV_10, "Lakeside Open", first_seen={})) == NEW


def test_first_seen_spellings_keep_each_spellings_earliest_snapshot() -> None:
    assert first_seen_spellings(
        [(NOV_10, "Lakeside Open"), (date(2026, 9, 15), "lakeside-open"), (OCT_27, None), (NOV_03, "")]
    ) == {"lakesideopen": date(2026, 9, 15)}


def test_a_check_word_needs_a_letter_or_digit() -> None:
    raw = topics().model_dump(by_alias=True)
    raw["topics"][1]["check_words"] = ["--"]

    with pytest.raises(ValueError, match="has no letter or digit"):
        TopicMap.model_validate(raw)


def test_the_reports_value_refuses_counts_that_cannot_be() -> None:
    common: dict[str, Any] = {"snapshot": NOV_10, "range_from": date(2026, 11, 6), "earlier_topic": "Old"}
    LateDisclosures(moved=True, disclosures=10, late=2, late_sources=2, **common)

    with pytest.raises(ValueError, match="some of the snapshot's"):
        LateDisclosures(moved=True, disclosures=1, late=2, late_sources=1, **common)
    with pytest.raises(ValueError, match="both topics' counts, or neither"):
        LateDisclosures(moved=True, disclosures=10, late=2, late_sources=2, this_topic_only=1, **common)

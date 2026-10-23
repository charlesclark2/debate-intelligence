"""The position taxonomy models (`v1-e32-t01-position-taxonomy` ac1, ac2).

A taxonomy is the list of positions a landscape report counts against, one file per topic plus a
shared `generic.yaml` of format-level positions. These tests hold the rules a coach's edit must
keep: unknown keys, duplicate ids, unknown parents, parent cycles, a merge into nothing and an alias
two positions claim are refused, and the topic map refuses two date ranges that overlap for one
caselist, so a snapshot resolves to exactly one topic.

Every position, alias and caselist here is invented for the test.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.caselist import Event
from debate_core.domain.landscape import (
    GENERIC_TOPIC_ID,
    Position,
    PositionKind,
    PositionSide,
    Taxonomy,
    TopicMap,
)


def position(position_id: str, **fields: Any) -> dict[str, Any]:
    """A position document, as a coach would write it in YAML."""
    document: dict[str, Any] = {
        "id": position_id,
        "label": position_id.replace("-", " ").title(),
        "kind": "da",
        "side": "neg",
    }
    document.update(fields)
    return document


def taxonomy(*positions: dict[str, Any], **fields: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": list(positions),
    }
    document.update(fields)
    return document


def generic(*positions: dict[str, Any]) -> dict[str, Any]:
    return taxonomy(*positions, topic_id=GENERIC_TOPIC_ID, event=None)


def load(document: dict[str, Any]) -> Taxonomy:
    return Taxonomy.model_validate(document)


def refusal(document: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as caught:
        load(document)
    return str(caught.value)


# ------------------------------------------------------------------------------------------------
# A taxonomy that keeps the rules loads
# ------------------------------------------------------------------------------------------------


def test_a_taxonomy_that_keeps_every_rule_loads() -> None:
    loaded = load(
        taxonomy(
            position("sample-plan-aff", kind="aff", side="aff", aliases=["sample plan aff"]),
            position(
                "sample-growth-advantage",
                kind="advantage",
                side="aff",
                parent="sample-plan-aff",
                aliases=["growth advantage", "growth adv"],
            ),
            position("sample-spending-da", aliases=["spending da", "spending disad"]),
            position("sample-old-da", deprecated=True, merged_into="sample-spending-da"),
        )
    )
    assert loaded.position("sample-growth-advantage").parent == "sample-plan-aff"
    assert loaded.position("sample-growth-advantage").kind is PositionKind.ADVANTAGE
    assert loaded.position("sample-plan-aff").side is PositionSide.AFF
    assert [one.id for one in loaded.active_positions] == [
        "sample-plan-aff",
        "sample-growth-advantage",
        "sample-spending-da",
    ]


def test_a_retired_position_resolves_to_the_one_it_was_merged_into() -> None:
    loaded = load(
        taxonomy(
            position("sample-current-da"),
            position("sample-renamed-da", deprecated=True, merged_into="sample-current-da"),
            position("sample-first-name-da", deprecated=True, merged_into="sample-renamed-da"),
        )
    )
    assert loaded.resolve("sample-first-name-da").id == "sample-current-da"
    assert loaded.resolve("sample-current-da").id == "sample-current-da"


def test_a_retired_position_with_no_merge_resolves_to_itself() -> None:
    loaded = load(taxonomy(position("sample-retired-cp", kind="cp", deprecated=True)))
    assert loaded.resolve("sample-retired-cp").deprecated


# ------------------------------------------------------------------------------------------------
# ac1: what a taxonomy refuses
# ------------------------------------------------------------------------------------------------


def test_an_unknown_key_on_a_position_is_refused() -> None:
    assert "alias" in refusal(taxonomy(position("sample-spending-da", alias=["spending da"])))


def test_an_unknown_key_on_the_taxonomy_is_refused() -> None:
    assert "topic" in refusal(taxonomy(position("sample-spending-da"), topic="policy-sample-topic"))


def test_a_duplicate_position_id_is_refused() -> None:
    message = refusal(taxonomy(position("sample-spending-da"), position("sample-spending-da", kind="cp")))
    assert "sample-spending-da" in message
    assert "twice" in message


def test_an_unknown_parent_is_refused() -> None:
    message = refusal(
        taxonomy(
            position("sample-growth-advantage", kind="advantage", side="aff", parent="sample-missing-aff")
        )
    )
    assert "sample-missing-aff" in message


def test_a_position_that_is_its_own_parent_is_refused() -> None:
    assert "cycle" in refusal(taxonomy(position("sample-spending-da", parent="sample-spending-da")))


def test_a_parent_cycle_is_refused() -> None:
    message = refusal(
        taxonomy(
            position("sample-first-da", parent="sample-third-da"),
            position("sample-second-da", parent="sample-first-da"),
            position("sample-third-da", parent="sample-second-da"),
        )
    )
    assert "cycle" in message


def test_a_merge_into_a_position_that_does_not_exist_is_refused() -> None:
    message = refusal(taxonomy(position("sample-old-da", deprecated=True, merged_into="sample-missing-da")))
    assert "sample-missing-da" in message


def test_a_merge_cycle_is_refused() -> None:
    message = refusal(
        taxonomy(
            position("sample-first-da", deprecated=True, merged_into="sample-second-da"),
            position("sample-second-da", deprecated=True, merged_into="sample-first-da"),
        )
    )
    assert "cycle" in message


def test_a_merged_position_must_be_retired() -> None:
    message = refusal(
        taxonomy(position("sample-current-da"), position("sample-old-da", merged_into="sample-current-da"))
    )
    assert "deprecated" in message


def test_an_alias_claimed_by_two_positions_is_refused() -> None:
    message = refusal(
        taxonomy(
            position("sample-spending-da", aliases=["spending da"]),
            position("sample-tradeoff-da", aliases=["tradeoff da", "spending da"]),
        )
    )
    assert "spending da" in message
    assert "sample-spending-da" in message
    assert "sample-tradeoff-da" in message


def test_an_alias_a_retired_position_still_claims_is_refused_on_another() -> None:
    message = refusal(
        taxonomy(
            position("sample-current-da", aliases=["spending da"]),
            position(
                "sample-old-da", deprecated=True, merged_into="sample-current-da", aliases=["spending da"]
            ),
        )
    )
    assert "spending da" in message


def test_an_alias_listed_twice_on_one_position_is_refused() -> None:
    assert "spending da" in refusal(
        taxonomy(position("sample-spending-da", aliases=["spending da", "spending da"]))
    )


@pytest.mark.parametrize(
    "alias",
    ["Spending DA", "spending  da", " spending da", "spending-da", "spending da:", ""],
)
def test_an_alias_not_written_as_a_normalized_heading_is_refused(alias: str) -> None:
    refusal(taxonomy(position("sample-spending-da", aliases=[alias])))


@pytest.mark.parametrize(
    "position_id", ["Sample-DA", "sample_da", "sample da", "-sample-da", "sample--da", ""]
)
def test_a_position_id_that_is_not_kebab_case_is_refused(position_id: str) -> None:
    refusal(taxonomy(position(position_id)))


@pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-beta", "01.0.0", "one"])
def test_a_taxonomy_version_that_is_not_semver_is_refused(version: str) -> None:
    refusal(taxonomy(position("sample-spending-da"), taxonomy_version=version))


@pytest.mark.parametrize("kind", ["disad", "DA", "kritik", ""])
def test_an_unknown_kind_is_refused(kind: str) -> None:
    refusal(taxonomy(position("sample-spending-da", kind=kind)))


@pytest.mark.parametrize("side", ["pro", "con", "AFF", "either", ""])
def test_a_side_other_than_aff_neg_or_both_is_refused(side: str) -> None:
    refusal(taxonomy(position("sample-spending-da", side=side)))


def test_an_empty_label_is_refused() -> None:
    refusal(taxonomy(position("sample-spending-da", label="  ")))


# ------------------------------------------------------------------------------------------------
# generic.yaml and the merge by event
# ------------------------------------------------------------------------------------------------


def test_a_generic_position_must_name_the_events_it_applies_to() -> None:
    message = refusal(generic(position("condo-bad", kind="theory", side="aff")))
    assert "events" in message


def test_a_topic_file_may_not_name_a_generic_topic_id_with_an_event() -> None:
    refusal(
        taxonomy(
            position("condo-bad", kind="theory", side="aff", events=["POLICY"]), topic_id=GENERIC_TOPIC_ID
        )
    )


def test_a_topic_position_may_not_apply_to_another_event() -> None:
    message = refusal(taxonomy(position("sample-spending-da", events=["LD"])))
    assert "LD" in message


def test_a_topic_file_must_name_its_event() -> None:
    refusal(taxonomy(position("sample-spending-da"), event=None))


def test_generic_positions_join_a_topic_of_their_event_only() -> None:
    topic = load(taxonomy(position("sample-spending-da", aliases=["spending da"])))
    shared = load(
        generic(
            position("condo-bad", kind="theory", side="aff", events=["POLICY", "LD"], aliases=["condo bad"]),
            position("sample-ld-only-theory", kind="theory", side="both", events=["LD"]),
        )
    )
    merged = topic.with_generic(shared)
    assert [one.id for one in merged.positions] == ["sample-spending-da", "condo-bad"]
    assert merged.topic_id == topic.topic_id
    assert merged.taxonomy_version == topic.taxonomy_version
    assert merged.event is Event.POLICY


def test_a_generic_alias_a_topic_position_also_claims_is_refused_on_merge() -> None:
    topic = load(taxonomy(position("sample-condo-theory", kind="theory", side="aff", aliases=["condo bad"])))
    shared = load(
        generic(position("condo-bad", kind="theory", side="aff", events=["POLICY"], aliases=["condo bad"]))
    )
    with pytest.raises(ValidationError, match="condo bad"):
        topic.with_generic(shared)


def test_a_generic_id_a_topic_also_uses_is_refused_on_merge() -> None:
    topic = load(taxonomy(position("condo-bad", kind="theory", side="aff")))
    shared = load(generic(position("condo-bad", kind="theory", side="aff", events=["POLICY"])))
    with pytest.raises(ValidationError, match="condo-bad"):
        topic.with_generic(shared)


def test_only_the_generic_file_merges_into_a_topic() -> None:
    topic = load(taxonomy(position("sample-spending-da")))
    with pytest.raises(ValueError, match=GENERIC_TOPIC_ID):
        topic.with_generic(topic)


# ------------------------------------------------------------------------------------------------
# ac2: the topic map
# ------------------------------------------------------------------------------------------------


def topic_map(*topics: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "topics": list(topics)}


def topic(topic_id: str, *ranges: tuple[str, str, str], **fields: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": topic_id,
        "event": "POLICY",
        "caselists": [{"caselist": slug, "from": start, "to": end} for slug, start, end in ranges],
    }
    document.update(fields)
    return document


def load_map(document: dict[str, Any]) -> TopicMap:
    return TopicMap.model_validate(document)


def map_refusal(document: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as caught:
        load_map(document)
    return str(caught.value)


def test_a_snapshot_resolves_to_its_topic_and_taxonomy_version() -> None:
    loaded = load_map(
        topic_map(
            topic(
                "policy-sample-topic",
                ("hspolicy99", "2026-07-01", "2027-06-30"),
                taxonomy_version="1.2.0",
                resolution="Resolved: an invented resolution for the test.",
            ),
            topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD"),
        )
    )
    resolved = loaded.resolve("hspolicy99", date(2026, 11, 7))
    assert resolved is not None
    assert resolved.topic_id == "policy-sample-topic"
    assert resolved.taxonomy_version == "1.2.0"
    assert resolved.event is Event.POLICY
    early = loaded.resolve("hsld99", date(2026, 9, 1))
    assert early is not None
    assert early.topic_id == "ld-sample-early"
    assert early.taxonomy_version is None


@pytest.mark.parametrize(
    ("caselist", "snapshot"),
    [
        ("hsld99", date(2026, 8, 31)),
        ("hsld99", date(2026, 11, 1)),
        ("hspf99", date(2026, 10, 1)),
    ],
)
def test_a_snapshot_outside_every_range_resolves_to_nothing(caselist: str, snapshot: date) -> None:
    loaded = load_map(topic_map(topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD")))
    assert loaded.resolve(caselist, snapshot) is None


def test_both_ends_of_a_range_are_in_it() -> None:
    loaded = load_map(topic_map(topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD")))
    assert loaded.resolve("hsld99", date(2026, 9, 1)) is not None
    assert loaded.resolve("hsld99", date(2026, 10, 31)) is not None


def test_overlapping_ranges_for_one_caselist_are_refused() -> None:
    message = map_refusal(
        topic_map(
            topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD"),
            topic("ld-sample-late", ("hsld99", "2026-10-31", "2026-12-31"), event="LD"),
        )
    )
    assert "hsld99" in message
    assert "overlap" in message


def test_overlapping_ranges_inside_one_topic_are_refused() -> None:
    message = map_refusal(
        topic_map(
            topic(
                "ld-sample-early",
                ("hsld99", "2026-09-01", "2026-10-31"),
                ("hsld99", "2026-10-15", "2026-11-30"),
                event="LD",
            )
        )
    )
    assert "overlap" in message


def test_adjacent_ranges_and_ranges_of_different_caselists_are_allowed() -> None:
    loaded = load_map(
        topic_map(
            topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD"),
            topic("ld-sample-late", ("hsld99", "2026-11-01", "2026-12-31"), event="LD"),
            topic("pf-sample-early", ("hspf99", "2026-09-01", "2026-10-31"), event="PF"),
        )
    )
    late = loaded.resolve("hsld99", date(2026, 11, 1))
    assert late is not None
    assert late.topic_id == "ld-sample-late"


def test_a_range_that_ends_before_it_starts_is_refused() -> None:
    map_refusal(topic_map(topic("ld-sample-early", ("hsld99", "2026-10-31", "2026-09-01"), event="LD")))


def test_a_topic_listed_twice_is_refused() -> None:
    message = map_refusal(
        topic_map(
            topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-09-30"), event="LD"),
            topic("ld-sample-early", ("hsld99", "2026-10-01", "2026-10-31"), event="LD"),
        )
    )
    assert "twice" in message


@pytest.mark.parametrize("slug", ["HSLD99", "hs-ld", "", "openev"])
def test_a_caselist_that_is_not_a_slug_is_refused(slug: str) -> None:
    map_refusal(topic_map(topic("ld-sample-early", (slug, "2026-09-01", "2026-10-31"), event="LD")))


def test_an_unknown_key_in_the_topic_map_is_refused() -> None:
    map_refusal(
        topic_map(topic("ld-sample-early", ("hsld99", "2026-09-01", "2026-10-31"), event="LD", wording="x"))
    )


def test_a_topic_with_no_caselist_is_refused() -> None:
    map_refusal(topic_map(topic("ld-sample-early", event="LD")))


def test_the_generic_id_is_not_a_topic() -> None:
    map_refusal(topic_map(topic(GENERIC_TOPIC_ID, ("hsld99", "2026-09-01", "2026-10-31"), event="LD")))


def test_a_topic_version_that_is_not_semver_is_refused() -> None:
    map_refusal(
        topic_map(
            topic("policy-sample-topic", ("hspolicy99", "2026-07-01", "2027-06-30"), taxonomy_version="1.0")
        )
    )


def test_position_kinds_and_sides_cover_the_spec() -> None:
    assert {kind.value for kind in PositionKind} >= {
        "aff",
        "advantage",
        "da",
        "cp",
        "k",
        "t",
        "theory",
        "value",
        "criterion",
        "contention",
        "response",
    }
    assert {side.value for side in PositionSide} == {"aff", "neg", "both"}
    assert Position.model_config.get("extra") == "forbid"

"""The release lock's own rules (`v1-e32-t08-released-position-ids`).

A release lists an id once; the lock lists a (topic, version) once; a release records the merged
taxonomy's every position, retired ones included, as id, kind and side only; and a release is added
only at the version the taxonomy is at, and only once. The rules the lock enforces on the taxonomy
files are checked through the files, in `tests/config/test_landscape_released_ids.py`.

Every topic and id here is invented.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_release import (
    ReleaseFinding,
    ReleaseLock,
    ReleaseRule,
    TaxonomyRelease,
    positions_digest,
)

TOPIC = "policy-sample-topic"


def taxonomy(version: str = "1.0.0") -> Taxonomy:
    topic = Taxonomy.model_validate(
        {
            "topic_id": TOPIC,
            "taxonomy_version": version,
            "event": "POLICY",
            "positions": [
                {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg"},
                {"id": "old-da", "label": "Old DA", "kind": "da", "side": "neg", "deprecated": True},
            ],
        }
    )
    generic = Taxonomy.model_validate(
        {
            "topic_id": "generic",
            "taxonomy_version": "1.0.0",
            "event": None,
            "positions": [
                {
                    "id": "condo-bad",
                    "label": "Condo bad",
                    "kind": "theory",
                    "side": "both",
                    "events": ["POLICY"],
                },
                {"id": "ld-only", "label": "LD only", "kind": "value", "side": "both", "events": ["LD"]},
            ],
        }
    )
    return topic.with_generic(generic)


def release(version: str = "1.0.0", ids: tuple[str, ...] = ("spending-da",)) -> dict[str, Any]:
    return {
        "topic_id": TOPIC,
        "taxonomy_version": version,
        "positions_digest": "0" * 64,
        "positions": [{"id": one, "kind": "da", "side": "neg"} for one in ids],
    }


def test_a_release_records_every_merged_position_as_id_kind_and_side() -> None:
    recorded = TaxonomyRelease.of(taxonomy())
    assert (recorded.topic_id, recorded.taxonomy_version) == (TOPIC, "1.0.0")
    assert [(one.id, one.kind.value, one.side.value) for one in recorded.positions] == [
        ("spending-da", "da", "neg"),
        ("old-da", "da", "neg"),
        ("condo-bad", "theory", "both"),
    ]


CANONICAL_POSITIONS = (
    '[{"id":"spending-da","kind":"da","label":"Spending DA","side":"neg"},'
    '{"deprecated":true,"id":"old-da","kind":"da","label":"Old DA","side":"neg"},'
    '{"events":["POLICY"],"id":"condo-bad","kind":"theory","label":"Condo bad","side":"both"}]'
)
"""The merged fixture's positions as canonical JSON, written by hand: set fields only, keys sorted."""


def test_a_release_records_the_digest_of_every_field_of_every_merged_position() -> None:
    expected = hashlib.sha256(CANONICAL_POSITIONS.encode("utf-8")).hexdigest()
    assert positions_digest(taxonomy()) == expected
    assert TaxonomyRelease.of(taxonomy()).positions_digest == expected


def test_any_field_changes_the_digest_and_a_default_written_out_does_not() -> None:
    def with_spending_da(**fields: Any) -> Taxonomy:
        merged = taxonomy().model_dump()
        merged["positions"][0].update(fields)
        return Taxonomy.model_validate(merged)

    assert positions_digest(with_spending_da(deprecated=False, description="")) == positions_digest(taxonomy())
    for fields in ({"aliases": ("spending da",)}, {"label": "Spending disad"}, {"tag_keywords": ("deficit",)}):
        assert positions_digest(with_spending_da(**fields)) != positions_digest(taxonomy()), fields


def test_a_digest_is_sha256_hex() -> None:
    with pytest.raises(ValidationError, match="positions_digest"):
        TaxonomyRelease.model_validate({**release(), "positions_digest": "not-a-digest"})


def test_a_release_listing_an_id_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match="lists spending-da twice"):
        TaxonomyRelease.model_validate(release(ids=("spending-da", "spending-da")))


def test_a_lock_listing_a_version_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match=f"{TOPIC} 1.0.0 is released twice"):
        ReleaseLock.model_validate({"releases": [release(), release(ids=("states-cp",))]})


def test_a_lock_holds_nothing_but_ids_kinds_and_sides() -> None:
    entry = release()
    entry["positions"][0]["label"] = "Spending DA"
    with pytest.raises(ValidationError, match="label"):
        ReleaseLock.model_validate({"releases": [entry]})


def test_an_empty_lock_is_the_default() -> None:
    assert ReleaseLock.model_validate({"schema_version": 1, "releases": []}) == ReleaseLock()


def test_a_release_is_added_at_the_taxonomy_s_own_version() -> None:
    lock = ReleaseLock().with_release(taxonomy(), "1.0.0").with_release(taxonomy("1.1.0"), "1.1.0")
    assert [(one.topic_id, one.taxonomy_version) for one in lock.releases] == [
        (TOPIC, "1.0.0"),
        (TOPIC, "1.1.0"),
    ]
    assert lock.releases_of(TOPIC) == lock.releases
    assert lock.releases_of("another-topic") == ()


def test_a_release_at_a_version_the_taxonomy_is_not_at_is_refused() -> None:
    with pytest.raises(ValueError, match=f"{TOPIC} is at 1.1.0, not 1.0.0"):
        ReleaseLock().with_release(taxonomy("1.1.0"), "1.0.0")


def test_a_version_already_released_is_not_released_again() -> None:
    lock = ReleaseLock().with_release(taxonomy(), "1.0.0")
    with pytest.raises(ValueError, match=f"{TOPIC} 1.0.0 is already released"):
        lock.with_release(taxonomy(), "1.0.0")


def test_a_finding_names_the_id_and_the_rule() -> None:
    finding = ReleaseFinding(
        topic_id=TOPIC, position_id="states-cp", rule=ReleaseRule.RELEASED_ID_MISSING, detail="is missing"
    )
    assert finding.message == (
        "states-cp is missing. Rule (released-id-missing): "
        "a released id is retired with deprecated or merged_into, never deleted"
    )

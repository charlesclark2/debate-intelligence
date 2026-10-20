"""`CardOccurrence`: one place a card appears, and what it says for a card with no tag (`v1-e31-t14`).

The occurrence table is built in memory by `caselist_card_stats` and is never written to the parsed
store, which keeps its own occurrence record without a tag (`OccurrenceRecord`). What a reader of
`CardOccurrence` gets for a card the file gave no tag is `None`, and `null` in its JSON, the same
as `ParsedCard`. Every value is invented.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from debate_core.domain.card_occurrence import CardFingerprint, CardOccurrence, ClusterMembership
from debate_core.domain.debate_files import CardCompleteness

FINGERPRINT = "f" * 64
SOURCE = "a" * 64


def make_occurrence(**overrides: object) -> CardOccurrence:
    fields: dict[str, object] = {
        "cluster_id": FINGERPRINT,
        "exact_fingerprint": FINGERPRINT,
        "fingerprint_version": "card-fingerprint-v4",
        "completeness": CardCompleteness.FULL,
        "membership": ClusterMembership.NEAR_DUPLICATE,
        "first_seen_snapshot": date(2026, 9, 1),
        "last_seen_snapshot": date(2026, 9, 8),
        "source_sha256": SOURCE,
        "element_index": 4,
        "tag": "Canopy loss kills",
        "short_cite": "Pellam 26",
    }
    fields.update(overrides)
    return CardOccurrence.model_validate(fields)


class TestACardWithNoTag:
    def test_an_occurrence_of_a_card_with_no_tag_has_none(self) -> None:
        assert make_occurrence(tag=None).tag is None

    def test_an_empty_tag_reads_as_none(self) -> None:
        """What every build before `v1-e31-t14` held for a card with no tag."""
        assert make_occurrence(tag="").tag is None

    def test_an_occurrence_left_to_its_default_has_no_tag(self) -> None:
        fields = make_occurrence().model_dump()
        del fields["tag"]

        assert CardOccurrence.model_validate(fields).tag is None

    def test_no_tag_is_null_in_json_never_an_empty_string(self) -> None:
        for tagless in (make_occurrence(tag=None), make_occurrence(tag="")):
            assert tagless.model_dump(mode="json")["tag"] is None
            assert json.loads(tagless.model_dump_json())["tag"] is None
            assert '"tag":""' not in tagless.model_dump_json()

    @pytest.mark.parametrize("spelling", [None, ""])
    def test_either_spelling_of_no_tag_reads_back_as_none(self, spelling: str | None) -> None:
        stored = make_occurrence().model_dump(mode="json") | {"tag": spelling}

        assert CardOccurrence.model_validate(stored).tag is None
        assert CardOccurrence.model_validate_json(json.dumps(stored)).tag is None

    def test_a_tag_is_kept_exactly(self) -> None:
        occurrence = make_occurrence(tag=" Canopy loss kills ")

        assert occurrence.tag == " Canopy loss kills "
        assert occurrence.model_dump(mode="json")["tag"] == " Canopy loss kills "


def test_the_fingerprint_version_description_says_the_digest_is_the_same_in_v1_through_v4() -> None:
    """`v1-e31-t11` Follow-up work 8, and v4 since `v1-e31-t20`: only the clusters changed."""
    description = CardFingerprint.model_fields["fingerprint_version"].description

    assert description is not None
    assert "the digest, is the same in card-fingerprint-v1, v2, v3 and v4" in description

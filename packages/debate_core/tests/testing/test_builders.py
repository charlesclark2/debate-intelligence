"""The builders really do produce valid, consistent, deterministic entities.

The contract suite leans on all three properties. If `build_card` handed out a card whose spans
ran past its evidence, or whose offsets disagreed with its text, every repository contract would
fail for a reason that has nothing to do with repositories; and if `readable_id` minted something
that is not a ULID, the listing-order contracts would be asserting on an order the domain would
never produce.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from debate_core.domain import ULID_PATTERN, ProvenanceMode, VerificationStatus
from debate_core.testing.builders import (
    DEFAULT_EVIDENCE_TEXT,
    DEFAULT_NORMALIZED_TEXT,
    DEFAULT_RAW_BYTES,
    build_article,
    build_card,
    build_card_span,
    build_citation,
    build_search,
    build_search_result,
    build_source_snapshot,
    readable_id,
    sha256_of,
)


class TestReadableId:
    """Deterministic ids that are still genuine ULIDs."""

    def test_it_produces_a_valid_ulid(self) -> None:
        assert re.match(ULID_PATTERN, readable_id("CARD", 7))

    def test_the_label_is_visible_in_the_id(self) -> None:
        assert readable_id("CARD", 7).startswith("0CARD")

    def test_ids_sort_in_the_order_of_their_numbers(self) -> None:
        """The listing-order contracts depend on this: id order is the order a reader expects."""
        assert readable_id("ART", 2) < readable_id("ART", 10)

    def test_it_rejects_a_label_outside_the_crockford_alphabet(self) -> None:
        """`I`, `L`, `O` and `U` are excluded from ULIDs, so `OWNER` is not a usable label."""
        with pytest.raises(ValueError, match="Crockford"):
            readable_id("OWNER")

    def test_it_rejects_a_label_too_long_to_leave_room_for_a_number(self) -> None:
        with pytest.raises(ValueError, match="at most 24 characters"):
            readable_id("A" * 25)

    def test_it_rejects_a_number_that_does_not_fit(self) -> None:
        with pytest.raises(ValueError, match="does not fit"):
            readable_id("A" * 24, 42)


class TestEntityBuilders:
    """Each builder produces a complete entity that satisfies its own model's invariants."""

    def test_the_default_article_is_a_published_scholarly_source(self) -> None:
        article = build_article()

        assert article.identifiers.doi == "10.1038/nature12373"
        assert article.published_at is not None
        assert article.published_at < article.created_at

    def test_the_snapshots_keys_and_digests_really_describe_its_bytes(self) -> None:
        """A snapshot built here can be stored in a `SnapshotStore` under the keys it claims."""
        snapshot = build_source_snapshot()

        assert snapshot.raw_blob_key == hashlib.sha256(DEFAULT_RAW_BYTES).hexdigest()
        assert snapshot.sha256 == snapshot.raw_blob_key
        assert snapshot.normalized_text_hash == sha256_of(DEFAULT_NORMALIZED_TEXT.encode("utf-8"))
        assert snapshot.byte_size == len(DEFAULT_RAW_BYTES)

    def test_the_default_card_carries_traceable_evidence(self) -> None:
        card = build_card()

        assert card.snapshot_id is not None
        assert card.evidence_text == DEFAULT_EVIDENCE_TEXT
        assert card.evidence_end_offset == len(DEFAULT_EVIDENCE_TEXT)
        assert card.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED

    def test_the_default_card_is_unverified(self) -> None:
        """Only the evidence verifier promotes a card; a builder handing out VERIFIED would lie."""
        assert build_card().verification_status is VerificationStatus.UNVERIFIED

    def test_the_default_span_falls_inside_the_default_evidence(self) -> None:
        span = build_card_span()

        assert span.end_offset <= len(DEFAULT_EVIDENCE_TEXT)
        assert build_card().spans == (span,)

    def test_a_card_can_be_evolved_into_a_tag_only_card(self) -> None:
        """The recipe the builder's docstring gives has to actually validate."""
        bare = build_card().evolve(
            snapshot_id=None,
            evidence_text="",
            evidence_start_offset=None,
            evidence_end_offset=None,
            spans=(),
        )

        assert bare.evidence_text == ""
        assert bare.tag

    def test_the_default_citation_is_fully_verified(self) -> None:
        assert build_citation().is_fully_verified is True

    def test_an_unverified_citation_names_every_field_it_could_not_confirm(self) -> None:
        citation = build_citation(verified=False)

        assert citation.is_fully_verified is False
        assert set(citation.unverified_fields) == {
            "authors",
            "title",
            "publication",
            "published_at",
            "canonical_url",
        }

    def test_the_default_search_records_which_providers_answered(self) -> None:
        search = build_search()

        assert search.provider_set == ("openalex", "crossref")
        assert search.filters.max_results == 20

    def test_results_built_by_rank_name_a_different_article_each_time(self) -> None:
        """A ranking built by comprehension must not collide on the article it names."""
        ranking = [build_search_result(rank=rank) for rank in (1, 2, 3)]

        assert len({result.article_id for result in ranking}) == 3

    def test_each_result_gets_its_own_quality_features(self) -> None:
        """The features are the one mutable default, so they must not be shared between results."""
        first, second = build_search_result(rank=1), build_search_result(rank=2)

        assert first.source_quality_features is not second.source_quality_features


class TestDeterminism:
    """Two builds of the same entity are byte-identical, which is what golden files need."""

    def test_two_articles_built_the_same_way_are_equal(self) -> None:
        assert build_article() == build_article()

    def test_two_cards_built_the_same_way_serialize_identically(self) -> None:
        assert build_card().model_dump_json() == build_card().model_dump_json()

    def test_two_snapshots_built_the_same_way_are_equal(self) -> None:
        assert build_source_snapshot() == build_source_snapshot()

    def test_two_searches_built_the_same_way_are_equal(self) -> None:
        assert build_search() == build_search()

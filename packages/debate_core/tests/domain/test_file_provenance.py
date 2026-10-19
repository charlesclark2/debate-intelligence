"""The provenance sidecar's model refuses what a sidecar must never say (`v1-e33-t02`)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.file_provenance import (
    FileProvenanceEntry,
    FileProvenanceManifest,
    formatting_sha256,
    text_sha256,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource

DIGEST = "a" * 64


def entry(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "position": 1,
        "recipe_path": "structure[0].blocks[0].items[0]",
        "section_path": ("Pocket", "Block"),
        "fingerprint": DIGEST,
        "fingerprint_version": "card-fingerprint-v3",
        "resolution": "AUTO",
        "caselist": "hspolicy26",
        "snapshot": "2026-09-15",
        "last_snapshot": "2026-09-22",
        "disclosure_digest": DIGEST,
        "school": "Maple Grove",
        "team_code": "QX",
        "source_sha256": DIGEST,
        "first_element_index": 3,
        "last_element_index": 5,
        "completeness": "FULL",
        "evidence_sha256": DIGEST,
        "cite_sha256": DIGEST,
        "formatting_sha256": DIGEST,
        "tag_overridden": False,
        "provenance_line": "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX]",
        "forbidden_characters_replaced": 0,
    }
    values.update(changes)
    return values


def manifest(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": "File",
        "topic": "topic",
        "format": "POLICY",
        "caselist": "hspolicy26",
        "position": "position",
        "side": "AFF",
        "recipe_hash": DIGEST,
        "builder_version": "builder",
        "parser_version": "parser",
        "style_profile_version": "profile",
        "fingerprint_version": "card-fingerprint-v3",
        "built_at": datetime(2026, 10, 19, tzinfo=UTC),
        "docx_sha256": DIGEST,
        "cards": cards,
    }


def test_a_well_formed_entry_and_manifest_validate() -> None:
    FileProvenanceManifest.model_validate(manifest([entry(), entry(position=2)]))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tag_overridden": True}, "only an overridden one"),
        ({"tag_authored_by": "COACH"}, "only an overridden one"),
        ({"original_tag_sha256": DIGEST}, "only for an overridden tag"),
        ({"school": None}, "with its school"),
        ({"first_element_index": 6}, "precedes"),
        ({"verification_status": "VERIFIED"}, "UNVERIFIED"),
        ({"provenance_mode": "FETCH"}, "FILE_IMPORT"),
    ],
    ids=[
        "override-not-the-coachs",
        "coach-without-override",
        "hash-without-override",
        "team-without-school",
        "range",
        "verified",
        "mode",
    ],
)
def test_an_entry_that_says_what_a_sidecar_must_not_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        FileProvenanceEntry.model_validate(entry(**changes))


def test_an_overridden_tag_is_the_coachs_with_or_without_an_original() -> None:
    FileProvenanceEntry.model_validate(
        entry(tag_overridden=True, tag_authored_by="COACH", original_tag_sha256=DIGEST)
    )
    FileProvenanceEntry.model_validate(entry(tag_overridden=True, tag_authored_by="COACH"))


@pytest.mark.parametrize("positions", [[2], [1, 1], [2, 1], [1, 3]])
def test_card_positions_run_one_two_three_in_file_order(positions: list[int]) -> None:
    with pytest.raises(ValidationError, match="card positions run"):
        FileProvenanceManifest.model_validate(manifest([entry(position=position) for position in positions]))


def _span(
    emphasis: RunEmphasis, start: int, end: int, rule: str, colour: str | None = None
) -> FormattingSpan:
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=start,
        end_offset=end,
        highlight_color=colour,
        rule_id=rule,
        match_source=StyleMatchSource.VERBATIM,
    )


def test_the_formatting_digest_reads_coverage_not_how_spans_were_split_or_found() -> None:
    split = [_span(RunEmphasis.UNDERLINE, 0, 4, "alias"), _span(RunEmphasis.UNDERLINE, 4, 9, "style")]
    whole = [_span(RunEmphasis.UNDERLINE, 0, 9, "style")]
    assert formatting_sha256(split, ()) == formatting_sha256(whole, ())


def test_the_formatting_digest_tells_apart_what_a_reader_would_see_differently() -> None:
    base = formatting_sha256([_span(RunEmphasis.UNDERLINE, 0, 9, "style")], ())
    assert formatting_sha256([_span(RunEmphasis.UNDERLINE, 0, 8, "style")], ()) != base
    assert formatting_sha256([_span(RunEmphasis.EMPHASIS, 0, 9, "style")], ()) != base
    cyan = formatting_sha256([_span(RunEmphasis.HIGHLIGHT, 0, 9, "h", "cyan")], ())
    assert formatting_sha256([_span(RunEmphasis.HIGHLIGHT, 0, 9, "h", "green")], ()) != cyan
    sized = formatting_sha256([], [FontSizeSpan(start_offset=0, end_offset=9, half_points=16)])
    assert formatting_sha256([], [FontSizeSpan(start_offset=0, end_offset=9, half_points=22)]) != sized


def test_text_digests_are_sha256_of_utf8() -> None:
    assert text_sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

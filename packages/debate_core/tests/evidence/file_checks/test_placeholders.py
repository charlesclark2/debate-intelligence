"""The placeholders check (`v1-e33-t15`): a built file still holding the CP text slot is warned.

`files suggest` opens a counterplan's draft with the analytic `CP_TEXT_SLOT` (`v1-e33-t11`). A file
built with it unreplaced is warned, naming the block, and never failed (PM ruling B on t11's question 1).

Each file is built by `v1-e33-t02`'s writer from the conftest's synthetic sources, under one pocket
(`Synthetic pocket`) and one hat (`Synthetic hat`), and every paragraph index below is counted by hand
from the layout (working agreement 6): the header analytic is paragraph 0, the pocket 1, the hat 2, the
first block 3, and a card of `SOURCE_ONE` is three paragraphs (tag, cite, body).

The slot is read from `files suggest`'s own module, as the PM asked: a check holding a copy of the
string would pass these tests only until the constant changed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from debate_core.application.file_suggest_service import CP_TEXT_SLOT
from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.file_checks.identity import SourceCardReading
from debate_core.evidence.file_checks.placeholders import check_placeholders
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck
from debate_core.testing.file_builder import SourceCard

Checked = tuple[BuiltEvidenceFile, ParsedDocument, dict[int, SourceCardReading]]
Blocks = Sequence[tuple[str, Sequence[Mapping[str, Any]]]]

#: What the check says of a slot left in place: the slot's own words are not repeated.
UNREPLACED = (
    "the analytic is still the placeholder for the counterplan's text that `files suggest` drafts: "
    "write the text the team reads in its place, then build again"
)


def known_headings(built: BuiltEvidenceFile) -> frozenset[str]:
    """The coach's headings, as the service takes them from the sidecar."""
    return frozenset(heading for entry in built.manifest.cards for heading in entry.section_path)


def slot_first(cards: Sequence[SourceCard]) -> Blocks:
    """A counterplan's draft as `files suggest` writes it: the first block opens with the slot."""
    one, two, three, four = cards
    return (
        ("Text and solvency", ({"analytic": CP_TEXT_SLOT}, {"fingerprint": one.fingerprint})),
        ("Net benefit", ({"fingerprint": two.fingerprint}, {"fingerprint": three.fingerprint})),
        ("Answers", ({"fingerprint": four.fingerprint},)),
    )


def slot_in_two_blocks(cards: Sequence[SourceCard]) -> Blocks:
    one, two, *_ = cards
    return (
        ("Text and solvency", ({"analytic": CP_TEXT_SLOT}, {"fingerprint": one.fingerprint})),
        ("Second text", ({"analytic": CP_TEXT_SLOT}, {"fingerprint": two.fingerprint})),
    )


def warned(paragraph: int, *path: str) -> CheckResult:
    return CheckResult(
        check=QualityCheck.PLACEHOLDERS_REPLACED,
        status=CheckStatus.WARN,
        section_path=path,
        paragraph_index=paragraph,
        message=UNREPLACED,
    )


PASSED = CheckResult(
    check=QualityCheck.PLACEHOLDERS_REPLACED,
    status=CheckStatus.PASS,
    message="no analytic is a placeholder left to replace",
)


def test_a_block_opening_with_the_cp_text_slot_is_warned_naming_the_block(
    build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]
) -> None:
    built, document, _ = build(source_bytes, slot_first)

    assert check_placeholders(document, known_headings(built)) == [
        warned(4, "Synthetic pocket", "Synthetic hat", "Text and solvency")
    ]


def test_each_slot_left_in_place_is_warned_in_its_own_block(
    build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]
) -> None:
    """Paragraphs 4 and 9: block 3, the slot, card one's three paragraphs, block 8, the slot."""
    built, document, _ = build(source_bytes, slot_in_two_blocks)

    assert check_placeholders(document, known_headings(built)) == [
        warned(4, "Synthetic pocket", "Synthetic hat", "Text and solvency"),
        warned(9, "Synthetic pocket", "Synthetic hat", "Second text"),
    ]


def test_a_file_without_the_slot_has_one_pass_result(standard: Checked) -> None:
    """The conftest's standard file holds an analytic of the coach's own, which is not a placeholder."""
    built, document, _ = standard

    assert check_placeholders(document, known_headings(built)) == [PASSED]


def test_only_an_analytic_that_is_exactly_the_slot_is_warned(
    build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]
) -> None:
    """The coach wrote the counterplan's text after the slot's words, or the slot's words in a sentence."""

    def written_around(cards: Sequence[SourceCard]) -> Blocks:
        one, two, *_ = cards
        return (
            (
                "Text and solvency",
                (
                    {"analytic": f"{CP_TEXT_SLOT} The fifty states should adopt the plan."},
                    {"analytic": f"Our text replaces {CP_TEXT_SLOT}"},
                    {"fingerprint": one.fingerprint},
                    {"fingerprint": two.fingerprint},
                ),
            ),
        )

    built, document, _ = build(source_bytes, written_around)

    assert check_placeholders(document, known_headings(built)) == [PASSED]


def test_a_heading_the_sidecar_does_not_name_is_given_by_its_level_and_paragraph(
    build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]
) -> None:
    """As the heading check names one: a report never carries text the coach did not write."""
    _, document, _ = build(source_bytes, slot_first)

    assert check_placeholders(document, frozenset()) == [
        warned(4, "pocket at paragraph 1", "hat at paragraph 2", "block at paragraph 3")
    ]


def test_the_slot_is_never_a_fail(build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]) -> None:
    _, document, _ = build(source_bytes, slot_in_two_blocks)

    assert {result.status for result in check_placeholders(document, frozenset())} == {CheckStatus.WARN}

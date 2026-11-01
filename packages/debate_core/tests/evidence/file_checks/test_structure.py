"""The structure checks (`v1-e33-t04`, node structure-checks; ac3, ac4, ac6).

Headings are checked on documents built by hand, paragraph by paragraph, so each expected paragraph
index and section path below is read off the document as written (working agreement 6). The other
checks run on a real file from `v1-e33-t02`'s writer, with its cards or sidecar changed as values.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

import pytest
from lxml import etree

from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile
from debate_core.domain.caselist import Event
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.file_provenance import FileProvenanceEntry
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.file_checks.identity import SourceCardReading
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck
from debate_core.evidence.file_checks.structure import (
    SuppressionsInForce,
    card_fingerprints,
    check_alignment,
    check_cites,
    check_duplicates,
    check_headings,
    check_provenance,
    check_sidecar,
    check_suppression,
)
from debate_core.integrations.docx_parser.package import W_NAMESPACE
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import SourceCard

Checked = tuple[BuiltEvidenceFile, ParsedDocument, dict[int, SourceCardReading]]


def _not_passing(results: list[CheckResult]) -> list[tuple[CheckStatus, int | None, str]]:
    return [
        (result.status, result.card_position, result.message)
        for result in results
        if result.status is not CheckStatus.PASS
    ]


# ------------------------------------------------------------------------------------------------
# Sidecar
# ------------------------------------------------------------------------------------------------

DOCX = "ab" * 32

#: The running style profile, and the one a file built before a profile change records (t09's pair).
RUNNING_PROFILE = "2026.09.20-verbatim-1"
OTHER_PROFILE = "2026.11.02-verbatim-2"
SAME_PROFILE: Final = {
    "sidecar_style_profile_version": RUNNING_PROFILE,
    "style_profile_version": RUNNING_PROFILE,
}

#: The WARN for a sidecar of `OTHER_PROFILE` checked under `RUNNING_PROFILE`, written by hand.
OTHER_PROFILE_WARNING = (
    "the sidecar was written under style profile 2026.11.02-verbatim-2; the files were re-read with "
    "2026.09.20-verbatim-1, and a card the two profiles read differently fails evidence-identity"
)


def test_a_valid_sidecar_of_these_bytes_passes() -> None:
    results = check_sidecar(
        problems=(),
        recorded_docx_sha256=DOCX,
        docx_sha256=DOCX,
        sidecar_parser_version="p1",
        parser_version="p1",
        **SAME_PROFILE,
    )
    assert [(result.status, result.check) for result in results] == [(CheckStatus.PASS, QualityCheck.SIDECAR)]


def test_a_sidecar_that_cannot_be_read_fails_with_each_problem() -> None:
    results = check_sidecar(
        problems=(
            "cards.0.source_sha256: Field required",
            "cards.0.provenance_mode: Input should be 'FILE_IMPORT'",
        ),
        recorded_docx_sha256=None,
        docx_sha256=DOCX,
        sidecar_parser_version=None,
        parser_version="p1",
        sidecar_style_profile_version=None,
        style_profile_version=RUNNING_PROFILE,
    )
    assert _not_passing(results) == [
        (CheckStatus.FAIL, None, "the sidecar is not valid: cards.0.source_sha256: Field required"),
        (
            CheckStatus.FAIL,
            None,
            "the sidecar is not valid: cards.0.provenance_mode: Input should be 'FILE_IMPORT'",
        ),
    ]


def test_a_sidecar_of_other_bytes_fails() -> None:
    results = check_sidecar(
        problems=(),
        recorded_docx_sha256="cd" * 32,
        docx_sha256=DOCX,
        sidecar_parser_version="p1",
        parser_version="p1",
        **SAME_PROFILE,
    )
    assert _not_passing(results) == [
        (
            CheckStatus.FAIL,
            None,
            "the sidecar describes a file with SHA-256 cdcdcdcdcdcd…, and this file is abababababab…",
        )
    ]


def test_a_sidecar_from_another_parser_version_is_a_warning() -> None:
    results = check_sidecar(
        problems=(),
        recorded_docx_sha256=DOCX,
        docx_sha256=DOCX,
        sidecar_parser_version="p0",
        parser_version="p1",
        **SAME_PROFILE,
    )
    assert _not_passing(results) == [
        (CheckStatus.WARN, None, "the sidecar was written under parser p0; the files were re-read with p1")
    ]


def test_a_sidecar_from_another_style_profile_is_one_warning_naming_both_profiles() -> None:
    """`v1-e33-t10`: beside the parser's warning, in its words, and a WARN, never a FAIL."""
    results = check_sidecar(
        problems=(),
        recorded_docx_sha256=DOCX,
        docx_sha256=DOCX,
        sidecar_parser_version="p1",
        parser_version="p1",
        sidecar_style_profile_version=OTHER_PROFILE,
        style_profile_version=RUNNING_PROFILE,
    )
    assert _not_passing(results) == [(CheckStatus.WARN, None, OTHER_PROFILE_WARNING)]
    assert [result.check for result in results] == [QualityCheck.SIDECAR]


def test_a_sidecar_from_another_parser_and_another_profile_warns_of_each_parser_first() -> None:
    results = check_sidecar(
        problems=(),
        recorded_docx_sha256=DOCX,
        docx_sha256=DOCX,
        sidecar_parser_version="p0",
        parser_version="p1",
        sidecar_style_profile_version=OTHER_PROFILE,
        style_profile_version=RUNNING_PROFILE,
    )
    assert _not_passing(results) == [
        (CheckStatus.WARN, None, "the sidecar was written under parser p0; the files were re-read with p1"),
        (CheckStatus.WARN, None, OTHER_PROFILE_WARNING),
    ]


def test_a_sidecar_that_cannot_be_read_names_no_profile() -> None:
    """With no valid sidecar there is no recorded profile to compare: the FAIL says why, and nothing else.

    A sidecar with no `style_profile_version` is one: the field has been required since the first
    sidecar (`v1-e33-t02`), so `FileQualityService` reads it as not valid.
    """
    results = check_sidecar(
        problems=("style_profile_version: Field required",),
        recorded_docx_sha256=None,
        docx_sha256=DOCX,
        sidecar_parser_version=None,
        parser_version="p1",
        sidecar_style_profile_version=None,
        style_profile_version=RUNNING_PROFILE,
    )
    assert _not_passing(results) == [
        (CheckStatus.FAIL, None, "the sidecar is not valid: style_profile_version: Field required")
    ]


# ------------------------------------------------------------------------------------------------
# Cites (PM ruling 2026-10-19: a warning, never a failure)
# ------------------------------------------------------------------------------------------------


def test_every_card_of_the_standard_file_has_a_cite_with_a_short_cite(standard: Checked) -> None:
    results = check_cites(standard[1].cards)
    assert [(result.card_position, result.status) for result in results] == [
        (1, CheckStatus.PASS),
        (2, CheckStatus.PASS),
        (3, CheckStatus.PASS),
        (4, CheckStatus.PASS),
    ]
    assert [result.fingerprint for result in results] == [
        entry.fingerprint for entry in standard[0].manifest.cards
    ]


def test_a_card_with_no_cite_or_no_short_cite_is_warned_and_never_failed(standard: Checked) -> None:
    one, two, *rest = standard[1].cards
    cards = [one.evolve(full_cite="", short_cite=None), two.evolve(short_cite=None), *rest]
    assert _not_passing(check_cites(cards)) == [
        (CheckStatus.WARN, 1, "the card has no cite"),
        (CheckStatus.WARN, 2, "the card has no short cite"),
    ]


# ------------------------------------------------------------------------------------------------
# Duplicates
# ------------------------------------------------------------------------------------------------


def test_no_card_of_the_standard_file_is_another(standard: Checked) -> None:
    assert _not_passing(check_duplicates(standard[1].cards)) == []


def test_a_card_that_appears_twice_fails_at_both_places(standard: Checked) -> None:
    cards = [*standard[1].cards, standard[1].cards[0]]
    assert _not_passing(check_duplicates(cards)) == [
        (CheckStatus.FAIL, 1, "the card's fingerprint appears 2 times, at cards 1, 5"),
        (CheckStatus.FAIL, 5, "the card's fingerprint appears 2 times, at cards 1, 5"),
    ]


PROSE = (
    "The reserve margin in every regional market fell below the planning target this year and "
    "operators warned that new data centre load would push it lower still unless new capacity is "
    "built quickly enough to meet the summer peak and the winter peak in the coming three years "
    "while transmission upgrades remain stalled in permitting reviews across the eastern states"
)


def _long_card(tag: str, name_year: str, text: str) -> str:
    return (
        paragraph_xml(run_xml(tag), style="Heading4")
        + paragraph_xml(
            run_xml(name_year, character_style="Style13ptBold") + run_xml(", Analyst, Grid Review, 2026")
        )
        + paragraph_xml(run_xml(text, character_style="StyleUnderline", highlight="cyan"))
    )


def test_near_duplicate_cards_are_warned_and_not_failed(build: Callable[..., Checked]) -> None:
    near = build_docx(
        _long_card("Margins fall", "Brandt 26", PROSE)
        + _long_card("Margins fall again", "Osei 26", PROSE.replace("eastern states", "western states"))
        + _long_card(
            "Something else entirely", "Nakamura 26", "Counties collect new property tax for schools."
        )
    )

    def layout(cards: Sequence[SourceCard]) -> Sequence[tuple[str, Sequence[Mapping[str, Any]]]]:
        return (("Margins", [{"fingerprint": card.fingerprint} for card in cards]),)

    _built, document, _sources = build((near,), layout)
    fingerprints = card_fingerprints(document.cards)
    assert len(set(fingerprints)) == 3, "three exact fingerprints"
    assert _not_passing(check_duplicates(document.cards)) == [
        (CheckStatus.WARN, 1, "the card is a near duplicate of card 2"),
        (CheckStatus.WARN, 2, "the card is a near duplicate of card 1"),
    ]


# ------------------------------------------------------------------------------------------------
# Headings (ac3)
# ------------------------------------------------------------------------------------------------


def _heading(level: int, text: str) -> str:
    return paragraph_xml(run_xml(text), style=f"Heading{level}")


def _card(number: int) -> str:
    """Three paragraphs: a tag, a cite and a body."""
    return (
        _heading(4, f"Synthetic claim {number}")
        + paragraph_xml(
            run_xml(f"Okonkwo 2{number}", character_style="Style13ptBold") + run_xml(", Analyst, Review")
        )
        + paragraph_xml(
            run_xml(f"Synthetic evidence {number} ", half_points=16)
            + run_xml("read", character_style="StyleUnderline")
        )
    )


KNOWN = frozenset({"Pocket A", "Hat A", "Block A", "Pocket B", "Hat B", "Block B"})


def _headings(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile, body: str, known: frozenset[str] = KNOWN
) -> list[CheckResult]:
    return check_headings(read(build_docx(body)), profile, known)


def _violations(results: list[CheckResult]) -> list[tuple[int | None, tuple[str, ...] | None, str]]:
    assert all(result.status in (CheckStatus.PASS, CheckStatus.FAIL) for result in results)
    return [
        (result.paragraph_index, result.section_path, result.message)
        for result in results
        if result.status is CheckStatus.FAIL
    ]


def test_headings_in_order_in_the_profiles_styles_pass(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    body = _heading(1, "Pocket A") + _heading(2, "Hat A") + _heading(3, "Block A") + _card(1) + _card(2)
    results = _headings(read, profile, body)
    assert [(result.status, result.message) for result in results] == [
        (CheckStatus.PASS, "every heading is in place and in its profile style")
    ]


def test_the_standard_built_file_passes_the_heading_checks(standard: Checked, profile: StyleProfile) -> None:
    known = frozenset(heading for entry in standard[0].manifest.cards for heading in entry.section_path)
    assert _violations(check_headings(standard[1], profile, known)) == []


def test_a_tag_outside_any_block_in_a_file_with_blocks_is_named_with_its_place(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    #   0 Pocket A, 1 Hat A, 2 Block A, 3-5 a card, 6 Hat B, 7-9 a card under no block
    body = (
        _heading(1, "Pocket A")
        + _heading(2, "Hat A")
        + _heading(3, "Block A")
        + _card(1)
        + _heading(2, "Hat B")
        + _card(2)
    )
    assert _violations(_headings(read, profile, body)) == [
        (7, ("Pocket A", "Hat B"), "a tag with no block above it, in a file that has blocks")
    ]


def test_a_skipped_level_is_named_once_with_its_place(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    #   0 Pocket A, 1 Hat A, 2 Block A, 3-5 a card, 6 Pocket B, 7 Block B straight under it, 8-10 a card
    body = (
        _heading(1, "Pocket A")
        + _heading(2, "Hat A")
        + _heading(3, "Block A")
        + _card(1)
        + _heading(1, "Pocket B")
        + _heading(3, "Block B")
        + _card(2)
    )
    assert _violations(_headings(read, profile, body)) == [
        (7, ("Pocket B",), "a block with no hat above it, in a file that has hats")
    ]


def test_a_file_without_hats_may_put_its_blocks_straight_in_a_pocket(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    body = _heading(1, "Pocket A") + _heading(3, "Block A") + _card(1) + _heading(3, "Block B") + _card(2)
    assert _violations(_headings(read, profile, body)) == []


def test_a_heading_in_an_alias_of_its_style_is_not_in_the_profiles_style(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    #   0 Pocket A, 1 Hat A, 2 a block styled `Block` (a recorded alias), 3-5 a card
    body = (
        _heading(1, "Pocket A")
        + _heading(2, "Hat A")
        + paragraph_xml(run_xml("Block A"), style="Block")
        + _card(1)
    )
    assert _violations(_headings(read, profile, body)) == [
        (
            2,
            ("Pocket A", "Hat A"),
            "a block heading not in the profile's Heading3 style (verbatim-alias-id:Block)",
        )
    ]


def test_a_misplaced_heading_is_named_under_the_levels_above_it_not_the_one_it_closes(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    #   0 Pocket A, 1 Hat A, 2 Block A, 3-5 a card, 6 a second block styled `Block`, 7-9 a card
    body = (
        _heading(1, "Pocket A")
        + _heading(2, "Hat A")
        + _heading(3, "Block A")
        + _card(1)
        + paragraph_xml(run_xml("Block B"), style="Block")
        + _card(2)
    )
    assert _violations(_headings(read, profile, body)) == [
        (
            6,
            ("Pocket A", "Hat A"),
            "a block heading not in the profile's Heading3 style (verbatim-alias-id:Block)",
        )
    ]


def test_a_tag_found_by_its_outline_level_is_not_in_the_profiles_style(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    #   0 Pocket A, 1 Hat A, 2 Block A, 3 a tag with no style, bold at outline level 3, 4 its cite, 5 its body
    tag = paragraph_xml(run_xml("Synthetic claim 1"), outline_level=3, bold=True, half_points=24)
    cite = paragraph_xml(run_xml("Okonkwo 26", bold=True) + run_xml(", Analyst, Review"))
    evidence = paragraph_xml(
        run_xml("Synthetic evidence ", half_points=16) + run_xml("read", underline="single")
    )
    body = _heading(1, "Pocket A") + _heading(2, "Hat A") + _heading(3, "Block A") + tag + cite + evidence
    assert _violations(_headings(read, profile, body)) == [
        (
            3,
            ("Pocket A", "Hat A", "Block A"),
            "a tag heading not in the profile's Heading4 style (heuristic-outline-level-3)",
        )
    ]


def test_a_heading_the_sidecar_does_not_name_is_given_by_its_level_and_paragraph(
    read: Callable[[bytes], ParsedDocument], profile: StyleProfile
) -> None:
    body = (
        _heading(1, "Pocket A")
        + _heading(2, "Hat A")
        + _heading(3, "Block A")
        + _card(1)
        + _heading(2, "Hat B")
        + _card(2)
    )
    results = _headings(read, profile, body, frozenset({"Pocket A"}))
    assert _violations(results) == [
        (7, ("Pocket A", "hat at paragraph 6"), "a tag with no block above it, in a file that has blocks")
    ]


# ------------------------------------------------------------------------------------------------
# The sidecar against the document (ac4)
# ------------------------------------------------------------------------------------------------


def test_the_standard_file_and_its_sidecar_agree_card_for_card(standard: Checked) -> None:
    results = check_alignment(standard[0].manifest.cards, standard[1].cards)
    assert [(result.card_position, result.status) for result in results] == [
        (1, CheckStatus.PASS),
        (2, CheckStatus.PASS),
        (3, CheckStatus.PASS),
        (4, CheckStatus.PASS),
    ]


def test_a_card_missing_from_the_document_fails(standard: Checked) -> None:
    results = check_alignment(standard[0].manifest.cards, standard[1].cards[:3])
    assert _not_passing(results) == [
        (CheckStatus.FAIL, None, "the sidecar lists 4 cards and the document reads as 3"),
        (CheckStatus.FAIL, 4, "the sidecar's card is not in the document"),
    ]


def test_a_card_missing_from_the_sidecar_fails(standard: Checked) -> None:
    results = check_alignment(standard[0].manifest.cards[:3], standard[1].cards)
    assert _not_passing(results) == [
        (CheckStatus.FAIL, None, "the sidecar lists 3 cards and the document reads as 4"),
        (CheckStatus.FAIL, 4, "the document's card is not in the sidecar"),
    ]


def test_a_card_the_document_holds_more_often_than_the_sidecar_fails_at_the_extra_copy(
    standard: Checked,
) -> None:
    results = check_alignment(standard[0].manifest.cards, [*standard[1].cards, standard[1].cards[0]])
    assert _not_passing(results) == [
        (CheckStatus.FAIL, None, "the sidecar lists 4 cards and the document reads as 5"),
        (CheckStatus.FAIL, 5, "the document holds this card more times than the sidecar lists it"),
    ]


def test_cards_in_the_wrong_order_fail_at_each_place(standard: Checked) -> None:
    one, two, three, four = standard[1].cards
    results = check_alignment(standard[0].manifest.cards, [one, three, two, four])
    assert _not_passing(results) == [
        (
            CheckStatus.FAIL,
            2,
            "the document holds another card of the sidecar here: the cards are out of order",
        ),
        (
            CheckStatus.FAIL,
            3,
            "the document holds another card of the sidecar here: the cards are out of order",
        ),
    ]


def test_a_card_under_other_headings_than_the_sidecar_says_fails(standard: Checked) -> None:
    entries = list(standard[0].manifest.cards)
    entries[0] = entries[0].evolve(section_path=("Synthetic pocket", "Synthetic hat", "Revenue"))
    assert _not_passing(check_alignment(entries, standard[1].cards)) == [
        (CheckStatus.FAIL, 1, "the card is under other headings in the document than the sidecar says")
    ]


# ------------------------------------------------------------------------------------------------
# Provenance (ac4; PM ruling 2026-10-19 on what complete means)
# ------------------------------------------------------------------------------------------------


def _provenance(
    standard: Checked, position: int, **changes: object
) -> list[tuple[CheckStatus, int | None, str]]:
    entries = list(standard[0].manifest.cards)
    entries[position - 1] = entries[position - 1].evolve(**changes)
    return _not_passing(check_provenance(entries, standard[1]))


def test_every_card_of_the_standard_file_has_complete_provenance_and_no_line(standard: Checked) -> None:
    results = check_provenance(standard[0].manifest.cards, standard[1])
    assert [(result.card_position, result.status) for result in results] == [
        (1, CheckStatus.PASS),
        (2, CheckStatus.PASS),
        (3, CheckStatus.PASS),
        (4, CheckStatus.PASS),
    ]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"team_code": None}, "the disclosure on record names a school and no team code"),
        ({"side": None}, "the disclosure on record names no side"),
        ({"disclosure_digest": None}, "a caselist card names no disclosure digest"),
    ],
)
def test_incomplete_provenance_fails(standard: Checked, changes: dict[str, object], message: str) -> None:
    assert _provenance(standard, 2, **changes) == [(CheckStatus.FAIL, 2, message)]


def test_a_disclosure_on_record_with_no_round_or_tournament_is_warned(standard: Checked) -> None:
    assert _provenance(standard, 1, round=None, tournament=None) == [
        (CheckStatus.WARN, 1, "the disclosure on record names no tournament"),
        (CheckStatus.WARN, 1, "the disclosure on record names no round"),
    ]


def test_a_card_with_no_disclosure_on_record_is_complete(
    build: Callable[..., Checked], source_bytes: tuple[bytes, bytes]
) -> None:
    def layout(cards: Sequence[SourceCard]) -> Sequence[tuple[str, Sequence[Mapping[str, Any]]]]:
        return (("Prices", [{"fingerprint": card.fingerprint} for card in cards]),)

    built, document, _sources = build(source_bytes[:1], layout, disclosed=False)
    assert all(entry.school is None and entry.disclosure_digest for entry in built.manifest.cards)
    assert _not_passing(check_provenance(built.manifest.cards, document)) == []


def test_a_provenance_line_not_in_the_policys_form_fails(standard: Checked) -> None:
    line = "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]"
    assert _provenance(standard, 1, provenance_line=line) == [
        (CheckStatus.FAIL, 1, "the provenance line does not name the card's caselist and first snapshot"),
    ]


def test_a_line_that_does_not_name_the_team_on_record_fails(standard: Checked) -> None:
    """PM amendment to ac4, 2026-10-20: a card whose disclosure names a team carries a line naming it."""
    line = "[Disclosed: hspolicy26 2026-09-15 — Cedar Hollow ZaLu, Aff vs. Riverbend Invitational Round 4]"
    assert _provenance(standard, 2, provenance_line=line) == [
        (CheckStatus.FAIL, 2, "the provenance line does not name the school and team code on record"),
    ]


def _with_paragraph(docx: bytes, after: str, paragraph: str) -> bytes:
    """The built file with `paragraph` inserted after the one paragraph whose text starts with `after`."""
    w = f"{{{W_NAMESPACE}}}"
    with zipfile.ZipFile(io.BytesIO(docx)) as package:
        parts = [(info, package.read(info.filename)) for info in package.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        for info, data in parts:
            if info.filename == "word/document.xml":
                root = etree.fromstring(data)
                (anchor,) = [
                    one
                    for one in root.iter(f"{w}p")
                    if "".join(t.text or "" for t in one.iter(f"{w}t")).startswith(after)
                ]
                wrapper = etree.fromstring(f'<w:body xmlns:w="{W_NAMESPACE}">{paragraph}</w:body>')
                anchor.addnext(wrapper[0])
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            package.writestr(info, data)
    return out.getvalue()


def test_a_built_file_whose_card_holds_its_provenance_line_fails(
    standard: Checked, read: Callable[[bytes], ParsedDocument]
) -> None:
    """Data-use policy 1.11, Attribution rule 2: a built file carries no provenance line (`v1-e33-t08`)."""
    entries = standard[0].manifest.cards
    line = paragraph_xml(run_xml(entries[1].provenance_line), style="Undertag")
    document = read(_with_paragraph(standard[0].docx, "Okonkwo 25", line))
    assert [card.provenance.first_element_index for card in document.cards] == [
        card.provenance.first_element_index + (1 if index >= 2 else 0)
        for index, card in enumerate(standard[1].cards)
    ], "the line joins card 2 and moves the cards after it by one paragraph"
    assert _not_passing(check_provenance(entries, document)) == [
        (CheckStatus.FAIL, 2, "the card's text holds a provenance line, which a built file never carries")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "[OpenEv: Cascade Institute 2031 — Policy, Climate Adv CP]",
        "As the card below says, [Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. "
        "Riverbend Invitational Round 4] is who read it.",
    ],
    ids=["the-policys-form", "a-sidecar-line-inside-other-text"],
)
def test_a_provenance_line_outside_any_card_fails_with_its_paragraph(
    standard: Checked, read: Callable[[bytes], ParsedDocument], text: str
) -> None:
    analytic = paragraph_xml(run_xml(text), style="Analytic")
    document = read(_with_paragraph(standard[0].docx, "Disclosed cards (FILE_IMPORT)", analytic))
    results = check_provenance(standard[0].manifest.cards, document)
    failing = [
        (result.card_position, result.paragraph_index, result.message)
        for result in results
        if result.status is CheckStatus.FAIL
    ]
    assert failing == [(None, 1, "the file's text holds a provenance line, which a built file never carries")]


def test_a_card_with_no_sidecar_entry_fails_provenance(standard: Checked) -> None:
    """Attribution rule 5: a card with no provenance on record may not be in a built file."""
    entries = [entry for entry in standard[0].manifest.cards if entry.position != 3]
    assert _not_passing(check_provenance(entries, standard[1])) == [
        (CheckStatus.FAIL, 3, "the document's card has no sidecar entry, so no provenance on record")
    ]


def _camp(entry: FileProvenanceEntry, **changes: object) -> FileProvenanceEntry:
    return FileProvenanceEntry.model_validate(
        {
            **entry.model_dump(),
            "caselist": "openev",
            "snapshot": "2031-policy",
            "last_snapshot": "2031-policy",
            "disclosure_digest": None,
            "school": None,
            "team_code": None,
            "side": None,
            "tournament": None,
            "round": None,
            "camp": "Cascade Institute",
            "camp_year": 2031,
            "camp_event": Event.POLICY,
            "camp_file_title": "Climate Adv CP",
            "provenance_line": "[OpenEv: Cascade Institute 2031 — Policy, Climate Adv CP]",
            **changes,
        }
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"camp_year": None}, "a camp card names no camp year"),
        ({"camp_event": None}, "a camp card names no camp event"),
        (
            {"camp_file_title": None, "provenance_line": "[OpenEv: Cascade Institute 2031 — Policy]"},
            "a camp card names no camp file title",
        ),
    ],
)
def test_a_camp_card_names_its_year_event_and_file_title(
    standard: Checked, changes: dict[str, object], message: str
) -> None:
    entries = list(standard[0].manifest.cards)
    complete = _not_passing(check_provenance([_camp(entries[0])], standard[1]))
    incomplete = _not_passing(check_provenance([_camp(entries[0], **changes)], standard[1]))
    assert (CheckStatus.FAIL, 1, message) in incomplete
    assert (CheckStatus.FAIL, 1, message) not in complete


def test_a_camp_line_must_be_the_policys_openev_form(standard: Checked) -> None:
    entry = _camp(standard[0].manifest.cards[0], provenance_line="[Disclosed: openev 2031-policy]")
    messages = _not_passing(check_provenance([entry], standard[1]))
    assert (CheckStatus.FAIL, 1, "the provenance line does not name the card's camp release") in messages


# ------------------------------------------------------------------------------------------------
# The suppression list (ac6)
# ------------------------------------------------------------------------------------------------


def test_no_suppression_no_flag(standard: Checked) -> None:
    results = check_suppression(standard[0].manifest.cards, SuppressionsInForce())
    assert _not_passing(results) == []
    assert len(results) == 4


def test_a_card_from_a_suppressed_source_is_flagged_by_fingerprint_and_request_id(standard: Checked) -> None:
    entry = standard[0].manifest.cards[2]
    results = check_suppression(
        standard[0].manifest.cards, SuppressionsInForce(sources={entry.source_sha256: "RM-2026-0007"})
    )
    failing = [result for result in results if result.status is CheckStatus.FAIL]
    assert [(result.card_position, result.fingerprint, result.message) for result in failing] == [
        (
            3,
            entry.fingerprint,
            "the card's source is on the suppression list (request RM-2026-0007, the whole source)",
        ),
        (
            4,
            standard[0].manifest.cards[3].fingerprint,
            "the card's source is on the suppression list (request RM-2026-0007, the whole source)",
        ),
    ]


def test_a_card_from_a_suppressed_disclosure_is_flagged_and_another_disclosure_is_not(
    standard: Checked,
) -> None:
    entry = standard[0].manifest.cards[0]
    assert entry.disclosure_digest is not None
    flagged = check_suppression(
        standard[0].manifest.cards,
        SuppressionsInForce(disclosures={(entry.source_sha256, entry.disclosure_digest): "RM-2026-0011"}),
    )
    assert _not_passing(flagged) == [
        (CheckStatus.FAIL, 1, "the card's disclosure is on the suppression list (request RM-2026-0011)"),
        (CheckStatus.FAIL, 2, "the card's disclosure is on the suppression list (request RM-2026-0011)"),
    ]
    elsewhere = check_suppression(
        standard[0].manifest.cards,
        SuppressionsInForce(disclosures={(entry.source_sha256, "ef" * 32): "RM-2026-0012"}),
    )
    assert _not_passing(elsewhere) == []


def test_a_camp_card_whose_source_has_any_disclosure_suppressed_is_flagged(standard: Checked) -> None:
    entry = _camp(standard[0].manifest.cards[0])
    results = check_suppression(
        [entry], SuppressionsInForce(disclosures={(entry.source_sha256, "ef" * 32): "RM-2026-0013"})
    )
    assert _not_passing(results) == [
        (
            CheckStatus.FAIL,
            1,
            "a suppression of one path of the card's source is in force (request RM-2026-0013); the sidecar "
            "records no camp path to say whether it is this card's",
        )
    ]


CAMP_PATH_2031: Final = "a1" * 32
CAMP_PATH_2031_SECOND: Final = "a2" * 32
CAMP_PATH_2032: Final = "b1" * 32


def test_a_camp_card_is_flagged_by_its_own_camp_path_and_the_same_file_from_another_release_is_not(
    standard: Checked,
) -> None:
    """`v1-e33-t07`: the sidecar names each camp card's camp paths, so one release's withdrawal is its own."""
    first = standard[0].manifest.cards[0]
    in_2031 = _camp(first, camp_path_disclosures=(CAMP_PATH_2031,))
    in_2032 = _camp(
        first,
        position=2,
        snapshot="2032-policy",
        last_snapshot="2032-policy",
        camp_year=2032,
        provenance_line="[OpenEv: Cascade Institute 2032 — Policy, Climate Adv CP]",
        camp_path_disclosures=(CAMP_PATH_2032,),
    )
    results = check_suppression(
        [in_2031, in_2032],
        SuppressionsInForce(disclosures={(first.source_sha256, CAMP_PATH_2032): "RM-2026-0014"}),
    )
    assert _not_passing(results) == [
        (CheckStatus.FAIL, 2, "the card's camp path is withdrawn from its release (request RM-2026-0014)")
    ]


def test_a_camp_card_at_two_paths_of_its_release_is_flagged_only_when_both_are_withdrawn(
    standard: Checked,
) -> None:
    entry = _camp(
        standard[0].manifest.cards[0], camp_path_disclosures=(CAMP_PATH_2031, CAMP_PATH_2031_SECOND)
    )
    sha = entry.source_sha256
    one = check_suppression([entry], SuppressionsInForce(disclosures={(sha, CAMP_PATH_2031): "RM-2026-0015"}))
    both = check_suppression(
        [entry],
        SuppressionsInForce(
            disclosures={(sha, CAMP_PATH_2031_SECOND): "RM-2026-0016", (sha, CAMP_PATH_2031): "RM-2026-0015"}
        ),
    )
    assert _not_passing(one) == []
    assert _not_passing(both) == [
        (CheckStatus.FAIL, 1, "the card's camp path is withdrawn from its release (request RM-2026-0015)")
    ]


def test_a_camp_card_with_camp_paths_is_still_flagged_by_its_whole_source(standard: Checked) -> None:
    entry = _camp(standard[0].manifest.cards[0], camp_path_disclosures=(CAMP_PATH_2031,))
    results = check_suppression([entry], SuppressionsInForce(sources={entry.source_sha256: "RM-2026-0017"}))
    assert _not_passing(results) == [
        (
            CheckStatus.FAIL,
            1,
            "the card's source is on the suppression list (request RM-2026-0017, the whole source)",
        )
    ]


def test_a_suppression_flag_names_no_school_team_or_file(standard: Checked) -> None:
    entries = standard[0].manifest.cards
    results = check_suppression(
        entries, SuppressionsInForce(sources={entries[0].source_sha256: "RM-2026-0007"})
    )
    text = " ".join(result.model_dump_json() for result in results)
    for entry in entries:
        for private in (entry.school, entry.team_code, entry.tournament, entry.round, entry.provenance_line):
            assert private is not None
            assert private not in text
    assert ".docx" not in text

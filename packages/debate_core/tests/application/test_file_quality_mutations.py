"""FileQualityService on real built files, and the mutation suite (`v1-e33-t04`, node quality-service).

Every file here is built by `v1-e33-t02`'s writer from synthetic sources (docx_builder, the E31
structural fixtures, t01's example recipes as the t02 script builds them), written to a temporary
directory with its sidecar, and checked from disk as `files check` will check it.

**ac1, the mutation suite.** Each mutation tampers with the built `.docx` at the OOXML level, the
sidecar left as the writer wrote it, and must be caught by the check that owns it:

* one character flipped in a copied `w:t` → evidence-identity;
* one underline run: its underline removed (text kept), or the run removed → evidence-identity;
* one highlight colour changed → evidence-identity;
* one cite paragraph deleted → evidence-identity;
* one card duplicated → duplicate-cards (and manifest-alignment).

Every tampered file also fails the sidecar check, because the sidecar describes the bytes as built;
each test asserts the owning check too, so that is never what catches it.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import importlib.util
import io
import json
import sys
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import jsonschema
import pytest
from lxml import etree

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.file_quality_service import FileQualityService, suppressions_in_force
from debate_core.application.file_recipes import ResolvedRecipe
from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile, FileBuildRequest
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
)
from debate_core.domain.caselist import CampFile, Event
from debate_core.domain.file_provenance import provenance_sidecar_name
from debate_core.evidence.file_checks.report import (
    CHECKER_VERSION,
    FILE_QUALITY_SCHEMA_FILENAME,
    CheckStatus,
    FileQualityReport,
    QualityCheck,
)
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.package import W_NAMESPACE
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.fakes.persistence import InMemorySnapshotStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord, empty_suppression_list
from debate_core.testing.file_builder import FileBuilderWorld, SourceCard, SyntheticDisclosure

REPOSITORY = Path(__file__).resolve().parents[4]
SCHEMA_PATH = REPOSITORY / "docs" / "data" / FILE_QUALITY_SCHEMA_FILENAME
STRUCTURAL = REPOSITORY / "tests" / "fixtures" / "debate_files" / "structural"
EXAMPLE_SCRIPT = REPOSITORY / "scripts" / "build_example_evidence_files.py"
RECIPES = REPOSITORY / "tests" / "fixtures" / "file_builder" / "recipes"

BUILT_AT = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)
W = f"{{{W_NAMESPACE}}}"

Layout = Callable[[Sequence[SourceCard]], Sequence[tuple[str, Sequence[Mapping[str, Any]]]]]


# ------------------------------------------------------------------------------------------------
# Synthetic sources
# ------------------------------------------------------------------------------------------------


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite(name_year: str, rest: str = ", Senior Fellow, Synthetic Energy Review, 2026") -> str:
    return paragraph_xml(run_xml(name_year, character_style="Style13ptBold") + run_xml(rest))


def body(lead: str, read: str, emphasised: str, tail: str, *, colour: str = "cyan") -> str:
    return paragraph_xml(
        run_xml(lead, half_points=16)
        + run_xml(read, character_style="StyleUnderline", highlight=colour)
        + run_xml(", and ", half_points=16)
        + run_xml(emphasised, character_style="Emphasis", bold=True, highlight="green")
        + run_xml(" with ", half_points=16)
        + run_xml("a direct underline", underline="single", highlight="yellow")
        + run_xml(tail, half_points=16)
    )


SOURCE_ONE = build_docx(
    tag("Moratoria raise prices for every ratepayer")
    + cite("Lindqvist 26")
    + body("A moratorium ", "freezes new supply", "demand keeps rising", " in every market.")
    + tag("Reliability falls first in the summer peak")
    + cite("Okonkwo 25", ", Grid Analyst, Synthetic Utility Quarterly, 2025")
    + body(
        "Operators ", "shed load at the peak", "reserves run thin", " across the region.", colour="magenta"
    )
)

SOURCE_TWO = build_docx(
    tag("Data centres bring tax revenue to rural counties")
    + cite("Achterberg 26", ", Economist, Synthetic Fiscal Review, 2026")
    + body("Counties ", "collect new property tax", "schools are funded", " for a decade.")
    + tag("The cite alone, a card disclosed without its text")
    + cite("Marsh 24", ", Professor, Synthetic Law Review, 2024")
)

#: The fictional disclosure every standard source is read under, and its private parts.
DISCLOSURE = SyntheticDisclosure()
PRIVATE = ("Maple Grove", "QX", "Riverbend Invitational", "Round 4", "aff-riverbend-r4")


def numbered_source(number: int) -> bytes:
    """One synthetic card, numbered so that no two bodies are alike, for the timing file."""
    words = " ".join(f"word{number}x{index}" for index in range(12))
    return build_docx(
        tag(f"Synthetic claim number {number}")
        + cite(
            f"Okonkwo {20 + number % 7}", f", Fellow, Synthetic Institute {number}, Synthetic Review, 2026"
        )
        + body(
            f"Synthetic evidence {number} begins {words} ",
            "then the part a debater reads",
            "a warrant",
            f" item {number}.",
        )
    )


def standard_layout(cards: Sequence[SourceCard]) -> Sequence[tuple[str, Sequence[Mapping[str, Any]]]]:
    one, two, three, four = cards
    return (
        (
            "Prices",
            (
                {"fingerprint": one.fingerprint},
                {"analytic": "The coach's own analytic between two cards."},
                {"fingerprint": two.fingerprint},
            ),
        ),
        (
            "Revenue",
            (
                {"fingerprint": three.fingerprint, "tag_override": "The coach's own tag for this card"},
                {"fingerprint": four.fingerprint},
            ),
        ),
    )


def one_block(cards: Sequence[SourceCard]) -> Sequence[tuple[str, Sequence[Mapping[str, Any]]]]:
    unique = list({card.fingerprint: card for card in cards}.values())
    return (("Every card", [{"fingerprint": card.fingerprint} for card in unique]),)


# ------------------------------------------------------------------------------------------------
# Building a file to disk and checking it
# ------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class OnDisk:
    """A built file and its sidecar in a temporary directory, and the blob store its sources are in."""

    path: Path
    snapshots: InMemorySnapshotStore
    built: BuiltEvidenceFile

    @property
    def sidecar(self) -> Path:
        return self.path.with_name(provenance_sidecar_name(self.path.name))


def write(directory: Path, built: BuiltEvidenceFile, snapshots: InMemorySnapshotStore, name: str) -> OnDisk:
    path = directory / name
    path.write_bytes(built.docx)
    path.with_name(provenance_sidecar_name(name)).write_bytes(built.manifest_json)
    return OnDisk(path=path, snapshots=snapshots, built=built)


def build_resolved(
    parser: DebateDocxParser, world: FileBuilderWorld, resolved: ResolvedRecipe
) -> BuiltEvidenceFile:
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser)
    built = asyncio.run(writer.build(FileBuildRequest(resolved, BUILT_AT)))
    assert isinstance(built, BuiltEvidenceFile), built
    return built


def build_to(
    directory: Path,
    parser: DebateDocxParser,
    contents: Sequence[bytes],
    layout: Layout,
    *,
    name: str = "synthetic.docx",
) -> OnDisk:
    world = FileBuilderWorld(parser=parser)
    cards: list[SourceCard] = []
    for content in contents:
        cards.extend(asyncio.run(world.add_source(content, disclosure=DISCLOSURE)))
    recipe = world.recipe(layout(cards))
    resolved = world.resolve(recipe, {card.fingerprint: card for card in cards})
    return write(directory, build_resolved(parser, world, resolved), world.snapshots, name)


def check(
    parser: DebateDocxParser, on_disk: OnDisk, *, suppression: SuppressionList | None = None
) -> FileQualityReport:
    service = FileQualityService(
        parser=parser,
        snapshots=on_disk.snapshots,
        suppression=suppression if suppression is not None else empty_suppression_list(),
    )
    return asyncio.run(service.check(on_disk.path)).report


def failing(report: FileQualityReport) -> set[QualityCheck]:
    return {summary.check for summary in report.checks if summary.status is CheckStatus.FAIL}


def messages(report: FileQualityReport, check: QualityCheck) -> list[str]:
    return [
        result.message
        for result in report.results
        if result.check is check and result.status is not CheckStatus.PASS
    ]


@pytest.fixture(scope="module")
def parser() -> DebateDocxParser:
    return DebateDocxParser()


@pytest.fixture
def standard(tmp_path: Path, parser: DebateDocxParser) -> OnDisk:
    return build_to(tmp_path, parser, (SOURCE_ONE, SOURCE_TWO), standard_layout)


# ------------------------------------------------------------------------------------------------
# OOXML tampering
# ------------------------------------------------------------------------------------------------


def tamper(path: Path, change: Callable[[etree._Element], None]) -> None:  # pyright: ignore[reportPrivateUsage]
    """Rewrite `word/document.xml` of the file at `path` through `change`, every other part kept."""
    with zipfile.ZipFile(path) as package:
        parts = [(info, package.read(info.filename)) for info in package.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        for info, data in parts:
            if info.filename == "word/document.xml":
                root = etree.fromstring(data)
                change(root)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            package.writestr(info, data)
    path.write_bytes(out.getvalue())


def paragraph_text(paragraph: etree._Element) -> str:  # pyright: ignore[reportPrivateUsage]
    return "".join(text.text or "" for text in paragraph.iter(f"{W}t"))


def paragraph_holding(root: etree._Element, text: str) -> etree._Element:  # pyright: ignore[reportPrivateUsage]
    (paragraph,) = [one for one in root.iter(f"{W}p") if text in paragraph_text(one)]
    return paragraph


def run_holding(root: etree._Element, text: str) -> etree._Element:  # pyright: ignore[reportPrivateUsage]
    (run,) = [one for one in root.iter(f"{W}r") if text in "".join(t.text or "" for t in one.iter(f"{W}t"))]
    return run


# ------------------------------------------------------------------------------------------------
# A clean file passes, and its reports are where and what they should be (ac2, ac5)
# ------------------------------------------------------------------------------------------------


def test_a_file_built_by_t02_passes_every_check(parser: DebateDocxParser, standard: OnDisk) -> None:
    report = check(parser, standard)
    assert report.status is CheckStatus.PASS
    assert [(summary.check, summary.status) for summary in report.checks] == [
        (check_name, CheckStatus.PASS) for check_name in QualityCheck
    ]
    assert report.card_count == report.manifest_card_count == 4
    assert report.docx_sha256 == hashlib.sha256(standard.path.read_bytes()).hexdigest()


def test_the_reports_are_written_beside_the_file_and_the_json_validates(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    check(parser, standard)
    json_path = standard.path.with_name("synthetic.docx.quality.json")
    markdown_path = standard.path.with_name("synthetic.docx.quality.md")
    assert sorted(path.name for path in standard.path.parent.iterdir()) == [
        "synthetic.docx",
        "synthetic.docx.provenance.json",
        "synthetic.docx.quality.json",
        "synthetic.docx.quality.md",
    ]
    document = json.loads(json_path.read_bytes())
    jsonschema.validate(document, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    assert document["checker_version"] == CHECKER_VERSION
    assert document["parser_version"] == parser.parser_version
    assert document["style_profile_version"] == parser.profile_version
    assert document["status"] == "PASS"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Built-file quality report\n")


def test_checking_changes_neither_the_built_file_nor_its_sidecar(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    before = (standard.path.read_bytes(), standard.sidecar.read_bytes())
    check(parser, standard)
    assert (standard.path.read_bytes(), standard.sidecar.read_bytes()) == before


def test_the_reports_hold_no_card_text_school_or_team_code(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def removal_and_cite_tampering(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        cite_paragraph = paragraph_holding(root, "Okonkwo 25")
        parent = cite_paragraph.getparent()
        assert parent is not None
        parent.remove(cite_paragraph)

    tamper(standard.path, removal_and_cite_tampering)
    sha = standard.built.manifest.cards[0].source_sha256
    report = check(parser, standard, suppression=suppressed(sha, "RM-2026-0007"))
    assert report.status is CheckStatus.FAIL
    written = standard.path.with_name("synthetic.docx.quality.json").read_text(
        encoding="utf-8"
    ) + standard.path.with_name("synthetic.docx.quality.md").read_text(encoding="utf-8")
    for private in PRIVATE:
        assert private not in written, private
    for card_words in (
        "moratorium",
        "freezes new supply",
        "Lindqvist",
        "Okonkwo",
        "ratepayer",
        "Synthetic Energy",
    ):
        assert card_words not in written, card_words


CHECK_MODULES = [
    REPOSITORY
    / "packages"
    / "debate_core"
    / "src"
    / "debate_core"
    / "application"
    / "file_quality_service.py",
    *sorted(
        (REPOSITORY / "packages" / "debate_core" / "src" / "debate_core" / "evidence" / "file_checks").glob(
            "*.py"
        )
    ),
]


def test_no_check_calls_a_model() -> None:
    """The forbidden list's second item: nothing the checks or the service import or name reaches a model."""
    assert len(CHECK_MODULES) == 5, CHECK_MODULES
    for path in CHECK_MODULES:
        text = path.read_text(encoding="utf-8")
        for word in ("ModelRouter", "model_router", "generate_structured", "bedrock", "integrations.models"):
            assert word not in text, (path.name, word)


# ------------------------------------------------------------------------------------------------
# ac1: the mutation suite
# ------------------------------------------------------------------------------------------------


def test_mutation_one_character_flipped_in_a_copied_run_fails_evidence_identity(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def flip(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        (text,) = run_holding(root, "freezes new supply").iter(f"{W}t")
        assert text.text is not None
        text.text = text.text.replace("freezes", "freezas")

    tamper(standard.path, flip)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert failing(report) == {
        QualityCheck.EVIDENCE_IDENTITY,
        QualityCheck.SIDECAR,
        QualityCheck.MANIFEST_ALIGNMENT,  # the card's fingerprint changed with its text
    }
    assert messages(report, QualityCheck.SIDECAR)[0].startswith("the sidecar describes a file with SHA-256 ")
    found = [
        result
        for result in report.results
        if result.check is QualityCheck.EVIDENCE_IDENTITY and result.status is CheckStatus.FAIL
    ]
    assert {result.card_position for result in found} == {1}
    assert any("evidence text" in result.message for result in found)


def test_mutation_one_run_s_underline_removed_fails_evidence_identity_on_formatting(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def strip_underline(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        run = run_holding(root, "shed load at the peak")
        (style,) = run.iter(f"{W}rStyle")
        assert style.get(f"{W}val") == "StyleUnderline"
        parent = style.getparent()
        assert parent is not None
        parent.remove(style)

    tamper(standard.path, strip_underline)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    found = [
        result
        for result in report.results
        if result.check is QualityCheck.EVIDENCE_IDENTITY and result.status is CheckStatus.FAIL
    ]
    assert [(result.card_position, result.message.split(" (")[0]) for result in found] == [
        (2, "the built card's formatting differs from the source card's")
    ]


def test_mutation_one_underlined_run_removed_fails_evidence_identity(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def remove_run(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        run = run_holding(root, "collect new property tax")
        parent = run.getparent()
        assert parent is not None
        parent.remove(run)

    tamper(standard.path, remove_run)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    found = messages(report, QualityCheck.EVIDENCE_IDENTITY)
    assert any("evidence text" in message for message in found), found
    assert any("formatting" in message for message in found), found


def test_mutation_one_highlight_colour_changed_fails_evidence_identity_on_formatting(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def recolour(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        (highlight,) = run_holding(root, "freezes new supply").iter(f"{W}highlight")
        assert highlight.get(f"{W}val") == "cyan"
        highlight.set(f"{W}val", "magenta")

    tamper(standard.path, recolour)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    found = [
        result
        for result in report.results
        if result.check is QualityCheck.EVIDENCE_IDENTITY and result.status is CheckStatus.FAIL
    ]
    assert [(result.card_position, result.message.split(" (")[0]) for result in found] == [
        (1, "the built card's formatting differs from the source card's")
    ]


def test_mutation_one_cite_paragraph_deleted_fails_evidence_identity_on_the_cite(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def delete_cite(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        paragraph = paragraph_holding(root, "Achterberg 26")
        parent = paragraph.getparent()
        assert parent is not None
        parent.remove(paragraph)

    tamper(standard.path, delete_cite)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    found = [
        result
        for result in report.results
        if result.check is QualityCheck.EVIDENCE_IDENTITY and result.status is CheckStatus.FAIL
    ]
    assert {result.card_position for result in found} == {3}
    assert any(result.message.startswith("the built card's cite differs") for result in found), found


def test_mutation_one_card_duplicated_fails_duplicate_cards(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def duplicate(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        body_element = root.find(f"{W}body")
        assert body_element is not None
        paragraphs = list(body_element.iter(f"{W}p"))
        first = paragraphs.index(paragraph_holding(root, "Moratoria raise prices"))
        last = paragraphs.index(paragraph_holding(root, "freezes new supply"))
        anchor = paragraphs[last]
        for paragraph in reversed(paragraphs[first : last + 1]):
            anchor.addnext(copy.deepcopy(paragraph))

    tamper(standard.path, duplicate)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert {QualityCheck.DUPLICATE_CARDS, QualityCheck.MANIFEST_ALIGNMENT} <= failing(report)
    assert messages(report, QualityCheck.DUPLICATE_CARDS) == [
        "the card's fingerprint appears 2 times, at cards 1, 2",
        "the card's fingerprint appears 2 times, at cards 1, 2",
    ]


def test_mutation_a_provenance_line_moved_above_its_cite_fails_provenance(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def move_line(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        cite_paragraph = paragraph_holding(root, "Lindqvist 26")
        undertag = cite_paragraph.getnext()
        assert undertag is not None and paragraph_text(undertag).startswith("[Disclosed: ")
        cite_paragraph.addprevious(undertag)

    tamper(standard.path, move_line)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert "the card's provenance line is not below its cite in the Undertag style" in messages(
        report, QualityCheck.PROVENANCE_COMPLETE
    )


def test_mutation_a_heading_restyled_as_an_alias_fails_heading_structure(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def restyle(root: etree._Element) -> None:  # pyright: ignore[reportPrivateUsage]
        (style,) = paragraph_holding(root, "Revenue").iter(f"{W}pStyle")
        style.set(f"{W}val", "Block")

    tamper(standard.path, restyle)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    found = [
        result
        for result in report.results
        if result.check is QualityCheck.HEADING_STRUCTURE and result.status is CheckStatus.FAIL
    ]
    assert [(result.section_path, result.message) for result in found] == [
        (
            ("Synthetic pocket", "Synthetic hat"),
            "a block heading not in the profile's Heading3 style (verbatim-alias-id:Block)",
        )
    ]


# ------------------------------------------------------------------------------------------------
# The sidecar (ac4): tampered as JSON, the .docx left as built
# ------------------------------------------------------------------------------------------------


def edit_sidecar(on_disk: OnDisk, change: Callable[[dict[str, Any]], None]) -> None:
    document = json.loads(on_disk.sidecar.read_bytes())
    change(document)
    on_disk.sidecar.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")


#: `(card index or None for the file, key, new value or None to remove it, the problem reported)`.
SCHEMA_BREAKS: Final = {
    "no-source-sha256": (1, "source_sha256", None, "cards.1.source_sha256: Field required"),
    "no-snapshot": (1, "snapshot", None, "cards.1.snapshot: Field required"),
    "card-not-file-import": (
        1,
        "provenance_mode",
        "CASELIST",
        "cards.1.provenance_mode: Input should be <ProvenanceMode.FILE_IMPORT: 'FILE_IMPORT'>",
    ),
    "file-not-file-import": (
        None,
        "provenance_mode",
        "CASELIST",
        "provenance_mode: Input should be <ProvenanceMode.FILE_IMPORT: 'FILE_IMPORT'>",
    ),
}


@pytest.mark.parametrize("name", SCHEMA_BREAKS)
def test_a_sidecar_missing_what_its_schema_requires_fails(
    parser: DebateDocxParser, standard: OnDisk, name: str
) -> None:
    card, key, value, expected = SCHEMA_BREAKS[name]

    def change(document: dict[str, Any]) -> None:
        target: dict[str, Any] = document if card is None else document["cards"][card]
        if value is None:
            del target[key]
        else:
            target[key] = value

    edit_sidecar(standard, change)
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert messages(report, QualityCheck.SIDECAR) == [f"the sidecar is not valid: {expected}"]
    assert report.manifest_card_count is None
    for check_name in (
        QualityCheck.EVIDENCE_IDENTITY,
        QualityCheck.MANIFEST_ALIGNMENT,
        QualityCheck.SUPPRESSION,
    ):
        assert report.failed(check_name), "nothing about a card is established without its sidecar"


def test_a_sidecar_naming_no_team_code_fails_provenance(parser: DebateDocxParser, standard: OnDisk) -> None:
    edit_sidecar(standard, lambda d: d["cards"][0].update(team_code=None))
    report = check(parser, standard)
    assert failing(report) == {QualityCheck.PROVENANCE_COMPLETE}
    assert messages(report, QualityCheck.PROVENANCE_COMPLETE) == [
        "the disclosure on record names a school and no team code"
    ]


def test_a_sidecar_naming_no_round_is_warned(parser: DebateDocxParser, standard: OnDisk) -> None:
    edit_sidecar(standard, lambda d: d["cards"][0].update(round=None))
    report = check(parser, standard)
    assert report.status is CheckStatus.PASS
    assert messages(report, QualityCheck.PROVENANCE_COMPLETE) == ["the disclosure on record names no round"]


def test_a_sidecar_with_its_cards_out_of_order_fails_alignment(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    def swap(document: dict[str, Any]) -> None:
        cards = document["cards"]
        cards[0], cards[1] = cards[1], cards[0]
        cards[0]["position"], cards[1]["position"] = 1, 2

    edit_sidecar(standard, swap)
    report = check(parser, standard)
    assert QualityCheck.MANIFEST_ALIGNMENT in failing(report)
    assert messages(report, QualityCheck.MANIFEST_ALIGNMENT) == [
        "the document holds another card of the sidecar here: the cards are out of order",
        "the document holds another card of the sidecar here: the cards are out of order",
    ]


def test_a_sidecar_missing_a_card_fails_alignment(parser: DebateDocxParser, standard: OnDisk) -> None:
    edit_sidecar(standard, lambda d: d.update(cards=d["cards"][:3]))
    report = check(parser, standard)
    assert messages(report, QualityCheck.MANIFEST_ALIGNMENT) == [
        "the sidecar lists 3 cards and the document reads as 4",
        "the document's card is not in the sidecar",
    ]


def test_a_sidecar_whose_digest_was_rewritten_fails_against_the_source(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    edit_sidecar(standard, lambda d: d["cards"][0].update(evidence_sha256="0" * 64))
    report = check(parser, standard)
    assert failing(report) == {QualityCheck.EVIDENCE_IDENTITY}


def test_a_missing_sidecar_fails(parser: DebateDocxParser, standard: OnDisk) -> None:
    standard.sidecar.unlink()
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert messages(report, QualityCheck.SIDECAR) == [
        "the sidecar is not valid: there is no sidecar beside the built file"
    ]


def test_a_source_missing_from_the_blob_store_fails_its_cards(
    parser: DebateDocxParser, tmp_path: Path
) -> None:
    on_disk = build_to(tmp_path, parser, (SOURCE_ONE, SOURCE_TWO), standard_layout)
    emptied = InMemorySnapshotStore()
    asyncio.run(emptied.put(SOURCE_TWO))
    report = check(parser, dataclasses.replace(on_disk, snapshots=emptied))
    assert failing(report) == {QualityCheck.EVIDENCE_IDENTITY}
    found = [result for result in report.results if result.status is CheckStatus.FAIL]
    assert [(result.card_position, result.message) for result in found] == [
        (1, "the source card cannot be read: the source's bytes are not in the blob store"),
        (2, "the source card cannot be read: the source's bytes are not in the blob store"),
    ]


def test_a_file_that_is_not_a_docx_fails(parser: DebateDocxParser, standard: OnDisk) -> None:
    standard.path.write_bytes(b"not a zip at all")
    report = check(parser, standard)
    assert report.status is CheckStatus.FAIL
    assert report.card_count == 0
    assert any(
        message.startswith("the built file does not parse: ")
        for message in messages(report, QualityCheck.EVIDENCE_IDENTITY)
    )


# ------------------------------------------------------------------------------------------------
# ac6: the suppression list
# ------------------------------------------------------------------------------------------------


def suppressed(
    sha: str, request: str, *, disclosure: str | None = None, lifted: bool = False
) -> RecordedSuppressionList:
    entries = [
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=sha,
            disclosure=disclosure,
            recorded_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id=request,
        )
    ]
    if lifted:
        entries.append(
            SuppressionEntry(
                action=SuppressionAction.UNSUPPRESS,
                sha256=sha,
                recorded_at=datetime(2026, 10, 21, 9, 0, tzinfo=UTC),
                reason=ReasonCode.REMOVED_IN_ERROR,
            )
        )
    return RecordedSuppressionList(InMemoryAppendOnlyRecord(lines=[entry.to_line() for entry in entries]))


def test_a_card_from_a_suppressed_source_is_flagged_by_fingerprint_and_request_id(
    parser: DebateDocxParser, standard: OnDisk
) -> None:
    first = standard.built.manifest.cards[0]
    report = check(parser, standard, suppression=suppressed(first.source_sha256, "RM-2026-0007"))
    assert failing(report) == {QualityCheck.SUPPRESSION}
    found = [result for result in report.results if result.status is CheckStatus.FAIL]
    assert [(result.card_position, result.fingerprint, result.message) for result in found] == [
        (
            1,
            first.fingerprint,
            "the card's source is on the suppression list (request RM-2026-0007, the whole source)",
        ),
        (
            2,
            standard.built.manifest.cards[1].fingerprint,
            "the card's source is on the suppression list (request RM-2026-0007, the whole source)",
        ),
    ]
    markdown = standard.path.with_name("synthetic.docx.quality.md").read_text(encoding="utf-8")
    assert f"card 1 (`{first.fingerprint[:12]}`)" in markdown
    assert "RM-2026-0007" in markdown
    for private in PRIVATE:
        assert private not in markdown


def test_a_card_from_a_suppressed_disclosure_is_flagged(parser: DebateDocxParser, standard: OnDisk) -> None:
    third = standard.built.manifest.cards[2]
    report = check(
        parser,
        standard,
        suppression=suppressed(third.source_sha256, "RM-2026-0011", disclosure=third.disclosure_digest),
    )
    assert messages(report, QualityCheck.SUPPRESSION) == [
        "the card's disclosure is on the suppression list (request RM-2026-0011)",
        "the card's disclosure is on the suppression list (request RM-2026-0011)",
    ]


def test_a_lifted_suppression_flags_nothing(parser: DebateDocxParser, standard: OnDisk) -> None:
    first = standard.built.manifest.cards[0]
    report = check(parser, standard, suppression=suppressed(first.source_sha256, "RM-2026-0007", lifted=True))
    assert report.status is CheckStatus.PASS


def test_the_suppressions_in_force_are_the_suppression_lists_own_state() -> None:
    one, two, three = "a1" * 32, "b2" * 32, "c3" * 32
    digest = "d4" * 32

    def entry(action: SuppressionAction, sha: str, day: int, **extra: Any) -> SuppressionEntry:
        reason = (
            ReasonCode.REQUESTED_BY_TEAM
            if action is SuppressionAction.SUPPRESS
            else ReasonCode.REMOVED_IN_ERROR
        )
        return SuppressionEntry(
            action=action, sha256=sha, recorded_at=datetime(2026, 10, day, tzinfo=UTC), reason=reason, **extra
        )

    entries = [
        entry(SuppressionAction.SUPPRESS, one, 1, request_id="RM-2026-0001"),
        entry(SuppressionAction.SUPPRESS, two, 2, request_id="RM-2026-0002", disclosure=digest),
        entry(SuppressionAction.UNSUPPRESS, three, 4),
        entry(SuppressionAction.SUPPRESS, three, 3, request_id="RM-2026-0003"),
        entry(SuppressionAction.SUPPRESS, one, 5, request_id="RM-2026-0009"),
    ]
    in_force = suppressions_in_force(entries)
    state = SuppressionState.from_entries(entries)
    assert set(in_force.sources) == set(state.sources) == {one}
    assert set(in_force.disclosures) == set(state.disclosures) == {(two, digest)}
    assert in_force.sources[one] == "RM-2026-0001", "the first request that suppressed it"


# ------------------------------------------------------------------------------------------------
# ac2: files t02 builds from the synthetic fixtures pass, quickly
# ------------------------------------------------------------------------------------------------

STRUCTURAL_WITH_CARDS = [
    "analytics-and-undertags.docx",
    "cardmirror-camp-file.docx",
    "cardmirror-caselist-upload.docx",
    "non-verbatim-caselist-upload.docx",
    "pre-2026-direct-formatting.docx",
    "team-verbatim-file.docx",
    "tracked-changes-and-comments.docx",
    "wiki-converted-cite-entries.docx",
]


@pytest.mark.parametrize("name", STRUCTURAL_WITH_CARDS)
def test_a_file_built_from_a_structural_fixture_fails_no_check(
    parser: DebateDocxParser, tmp_path: Path, name: str
) -> None:
    on_disk = build_to(tmp_path, parser, ((STRUCTURAL / name).read_bytes(),), one_block)
    report = check(parser, on_disk)
    assert failing(report) == set(), [
        result for result in report.results if result.status is CheckStatus.FAIL
    ]
    assert report.status is CheckStatus.PASS


@pytest.fixture(scope="module")
def example_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_example_evidence_files_for_t04", EXAMPLE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("recipe", sorted(path.name for path in RECIPES.glob("*.yaml")))
def test_each_example_file_t02_builds_for_the_coach_passes_every_check(
    parser: DebateDocxParser,
    tmp_path: Path,
    example_script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    recipe: str,
) -> None:
    worlds: list[FileBuilderWorld] = []

    def remembered(*args: Any, **kwargs: Any) -> FileBuilderWorld:
        """The script's world, kept so the check can read the sources it stored."""
        world = FileBuilderWorld(*args, **kwargs)
        worlds.append(world)
        return world

    monkeypatch.setattr(example_script, "FileBuilderWorld", remembered)
    _recipe, built = asyncio.run(example_script.build_example(RECIPES / recipe, parser))
    report = check(parser, write(tmp_path, built, worlds[-1].snapshots, recipe.replace(".yaml", ".docx")))
    assert [summary.status for summary in report.checks] == [CheckStatus.PASS] * len(QualityCheck), [
        result for result in report.results if result.status is not CheckStatus.PASS
    ]


CAMP_SOURCE = build_docx(
    tag("Grid upgrades cost less than new plants")
    + cite("Vasquez-Hale 31", ", Engineer, Synthetic Transmission Journal, 2031")
    + body("Reconductoring ", "doubles capacity", "corridors stay in use", " on existing lines.")
)


def test_a_file_of_a_disclosed_card_and_a_camp_card_passes_every_check(
    parser: DebateDocxParser, tmp_path: Path
) -> None:
    world = FileBuilderWorld(parser=parser)
    (disclosed, _other) = asyncio.run(world.add_source(SOURCE_ONE, disclosure=DISCLOSURE))
    (source,) = asyncio.run(world.add_source(CAMP_SOURCE, disclosure=None))
    occurrence = OccurrenceRecord.model_validate(
        {
            **source.occurrence.model_dump(),
            "caselist": "openev",
            "snapshot": "2031-policy",
            "last_snapshot": "2031-policy",
            "disclosure": None,
            "camp": "Lanternfield Institute",
        }
    )
    camp = dataclasses.replace(source, occurrence=occurrence, disclosure=None)
    recipe = world.recipe(
        [("Reliability", [{"fingerprint": disclosed.fingerprint}, {"fingerprint": camp.fingerprint}])]
    )
    resolved = world.resolve(
        recipe, {disclosed.fingerprint: disclosed, camp.fingerprint: camp}, pinned=[camp.fingerprint]
    )
    release = CampFile(
        source_sha256=camp.occurrence.source_sha256,
        camp="Lanternfield Institute",
        year=2031,
        event=Event.POLICY,
        file_title="Synthetic Grid Reliability CP",
        snapshot=date(2026, 7, 30),
    )
    cards = tuple(
        dataclasses.replace(card, camp_file=release if card.fingerprint == camp.fingerprint else None)
        for card in resolved.cards
    )
    versions = {card.occurrence.caselist: card.occurrence.parser_version for card in cards}
    resolved = dataclasses.replace(resolved, cards=cards, versions=versions)
    on_disk = write(tmp_path, build_resolved(parser, world, resolved), world.snapshots, "camp.docx")
    assert on_disk.built.manifest.cards[1].caselist == "openev"
    report = check(parser, on_disk)
    assert [summary.status for summary in report.checks] == [CheckStatus.PASS] * len(QualityCheck), [
        result for result in report.results if result.status is not CheckStatus.PASS
    ]


#: ac2's budget: under 5 s per 100 cards on the CI runner.
SECONDS_PER_HUNDRED_CARDS = 5.0


def test_a_hundred_card_file_passes_every_check_within_the_budget(
    parser: DebateDocxParser, tmp_path: Path
) -> None:
    on_disk = build_to(
        tmp_path, parser, [numbered_source(number) for number in range(100)], one_block, name="hundred.docx"
    )
    assert len(on_disk.built.manifest.cards) == 100
    started = time.perf_counter()
    report = check(parser, on_disk)
    elapsed = time.perf_counter() - started
    assert report.status is CheckStatus.PASS
    assert failing(report) == set()
    assert elapsed < SECONDS_PER_HUNDRED_CARDS, f"{elapsed:.2f} s for 100 cards"

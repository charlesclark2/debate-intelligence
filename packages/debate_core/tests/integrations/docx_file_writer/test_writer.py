"""Whole files behind the EvidenceFileWriter port: assembly, determinism, the sidecar, refusals.

Test names carry the plan node they prove: `assembly` and `deterministic` (node `file-assembly`),
`provenance` (node `provenance-sidecar`) and `refusal` (ac4 for a whole file). Every source is
synthetic and built in memory; the schools and team codes are the repository's fictional ones.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import zipfile
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from lxml import etree

from debate_core.application.file_recipes import ResolvedCard, ResolvedRecipe
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    CardRefusalCode,
    EvidenceFileWriter,
    FileBuildRefusal,
    FileBuildRequest,
    UnsupportedContentKind,
)
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.domain.caselist import Disclosure, Side, SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.enums import ProvenanceMode, VerificationStatus
from debate_core.domain.file_provenance import (
    FILE_PROVENANCE_SCHEMA_FILENAME,
    FileProvenanceManifest,
    formatting_sha256,
    provenance_sidecar_name,
    render_file_provenance_schema,
    text_sha256,
)
from debate_core.domain.file_recipe import TagAuthor
from debate_core.integrations.docx_file_writer.package_writer import FIXED_ZIP_TIMESTAMP
from debate_core.integrations.docx_file_writer.writer import (
    FILE_BUILDER_VERSION,
    DocxEvidenceFileWriter,
    provenance_line,
)
from debate_core.integrations.docx_parser.package import W_NAMESPACE
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import (
    DEFAULT_STYLE_DEFINITIONS,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)
from debate_core.testing.file_builder import FileBuilderWorld, SourceCard, SyntheticDisclosure

W = f"{{{W_NAMESPACE}}}"
SCHEMA_PATH = Path(__file__).resolve().parents[5] / "docs" / "data" / FILE_PROVENANCE_SCHEMA_FILENAME


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite(name_year: str, rest: str = ", Senior Fellow, Synthetic Energy Review, 2026") -> str:
    return paragraph_xml(run_xml(name_year, character_style="Style13ptBold") + run_xml(rest))


def body(lead: str, read: str, tail: str) -> str:
    return paragraph_xml(
        run_xml(lead, half_points=16)
        + run_xml(read, character_style="StyleUnderline", highlight="cyan")
        + run_xml(tail, half_points=16)
    )


SOURCE_ONE = build_docx(
    tag("Moratoria raise prices for every ratepayer")
    + cite("Lindqvist 26")
    + body("A moratorium ", "freezes supply", " while demand rises.")
    + tag("Reliability falls first in the summer peak")
    + cite("Okonkwo 25", ", Grid Analyst, Synthetic Utility Quarterly, 2025")
    + body("Operators ", "shed load", " when reserves run thin.")
)

SOURCE_TWO = build_docx(
    tag("Data centres bring tax revenue")
    + cite("Achterberg 26", ", Economist, Synthetic Fiscal Review, 2026")
    + tag("The cite alone, a card disclosed without its text")
    + cite("Marsh 24", ", Professor, Synthetic Law Review, 2024")
)

ALLOWED_ANALYTIC = "The moratorium trades a small saving for a large risk."


@dataclasses.dataclass
class Built:
    world: FileBuilderWorld
    cards: dict[str, SourceCard]
    resolved: ResolvedRecipe
    result: BuiltEvidenceFile | FileBuildRefusal

    @property
    def file(self) -> BuiltEvidenceFile:
        assert isinstance(self.result, BuiltEvidenceFile), self.result
        return self.result


def _sources(
    parser: DebateDocxParser, *contents: tuple[bytes, SyntheticDisclosure | None]
) -> tuple[FileBuilderWorld, list[SourceCard]]:
    world = FileBuilderWorld(parser=parser)
    cards: list[SourceCard] = []
    for content, disclosure in contents:
        cards.extend(asyncio.run(world.add_source(content, disclosure=disclosure)))
    return world, cards


def _build(
    world: FileBuilderWorld,
    cards: Sequence[SourceCard],
    blocks: Sequence[tuple[str, Sequence[dict[str, Any]]]],
    built_at: datetime,
    *,
    parser: DebateDocxParser | None = None,
) -> Built:
    by_fingerprint = {card.fingerprint: card for card in cards}
    recipe = world.recipe(blocks)
    resolved = world.resolve(recipe, by_fingerprint)
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser)
    result = asyncio.run(writer.build(FileBuildRequest(resolved, built_at)))
    return Built(world, by_fingerprint, resolved, result)


@pytest.fixture
def standard(parser: DebateDocxParser, built_at: datetime) -> Built:
    """Two sources, four cards: one overridden tag, one analytic, a cite-only card, two blocks."""
    world, cards = _sources(
        parser,
        (SOURCE_ONE, SyntheticDisclosure()),
        (
            SOURCE_TWO,
            SyntheticDisclosure(school="Cedar Hollow", team_code="ZaLu", side=Side.NEG, round="Semis"),
        ),
    )
    first, second, third, fourth = cards
    return _build(
        world,
        cards,
        [
            (
                "Prices",
                [
                    {"fingerprint": first.fingerprint, "tag_override": "Prices rise - the coach's own tag"},
                    {"analytic": ALLOWED_ANALYTIC},
                    {"fingerprint": second.fingerprint},
                ],
            ),
            ("Revenue", [{"fingerprint": third.fingerprint}, {"fingerprint": fourth.fingerprint}]),
        ],
        built_at,
    )


def _paragraphs(docx: bytes) -> list[tuple[str | None, str]]:
    """Each body paragraph of a built file as (paragraph style, text)."""
    with zipfile.ZipFile(BytesIO(docx)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    found: list[tuple[str | None, str]] = []
    for paragraph in root.iter(f"{W}p"):
        style = paragraph.find(f"{W}pPr/{W}pStyle")
        text = "".join(t.text or "" for t in paragraph.iter(f"{W}t"))
        found.append((None if style is None else style.get(f"{W}val"), text))
    return found


def _reparse(parser: DebateDocxParser, docx: bytes) -> ParsedDocument:
    world = FileBuilderWorld(parser=parser)
    source = SourceDocument(
        sha256=hashlib.sha256(docx).hexdigest(),
        byte_size=len(docx),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=world.caselist,
        first_seen_snapshot=date(2026, 10, 19),
        last_seen_snapshot=date(2026, 10, 19),
    )
    parsed = parser.parse(docx, source, source_path="built.docx")
    assert isinstance(parsed, ParsedDocument)
    return parsed


# ------------------------------------------------------------------------------------------------
# Assembly (node file-assembly; ac2, ac3)
# ------------------------------------------------------------------------------------------------


def test_assembly_writes_the_recipe_in_order_in_the_profiles_styles(standard: Built) -> None:
    maple = "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]"
    cedar = "[Disclosed: hspolicy26 2026-09-15 — Cedar Hollow ZaLu, Neg vs. Riverbend Invitational Semis]"
    assert _paragraphs(standard.file.docx) == [
        (
            "Analytic",
            "Disclosed cards (FILE_IMPORT) from hspolicy26, each copied from the file that disclosed it "
            "and not verified by this platform. Who disclosed each card is below its cite.",
        ),
        ("Heading1", "Synthetic pocket"),
        ("Heading2", "Synthetic hat"),
        ("Heading3", "Prices"),
        ("Heading4", "Prices rise - the coach's own tag"),
        (None, "Lindqvist 26, Senior Fellow, Synthetic Energy Review, 2026"),
        ("Undertag", maple),
        (None, "A moratorium freezes supply while demand rises."),
        ("Analytic", ALLOWED_ANALYTIC),
        ("Heading4", "Reliability falls first in the summer peak"),
        (None, "Okonkwo 25, Grid Analyst, Synthetic Utility Quarterly, 2025"),
        ("Undertag", maple),
        (None, "Operators shed load when reserves run thin."),
        ("Heading3", "Revenue"),
        ("Heading4", "Data centres bring tax revenue"),
        (None, "Achterberg 26, Economist, Synthetic Fiscal Review, 2026"),
        ("Undertag", cedar),
        ("Heading4", "The cite alone, a card disclosed without its text"),
        (None, "Marsh 24, Professor, Synthetic Law Review, 2024"),
        ("Undertag", cedar),
    ]


def test_assembly_reads_back_as_the_recipe_structure(parser: DebateDocxParser, standard: Built) -> None:
    parsed = _reparse(parser, standard.file.docx)
    assert [card.tag for card in parsed.cards] == [
        "Prices rise - the coach's own tag",
        "Reliability falls first in the summer peak",
        "Data centres bring tax revenue",
        "The cite alone, a card disclosed without its text",
    ]
    assert parsed.cards[0].section_path == ("Synthetic pocket", "Synthetic hat", "Prices")
    assert parsed.cards[2].section_path == ("Synthetic pocket", "Synthetic hat", "Revenue")
    analytics = [section.text for section in parsed.sections if section.unit.value == "ANALYTIC"]
    assert analytics == [_paragraphs(standard.file.docx)[0][1], ALLOWED_ANALYTIC]


def test_assembly_writes_the_policys_provenance_line_below_each_cite(standard: Built) -> None:
    lines = [text for style, text in _paragraphs(standard.file.docx) if style == "Undertag"]
    assert lines == [
        "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]",
        "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]",
        "[Disclosed: hspolicy26 2026-09-15 — Cedar Hollow ZaLu, Neg vs. Riverbend Invitational Semis]",
        "[Disclosed: hspolicy26 2026-09-15 — Cedar Hollow ZaLu, Neg vs. Riverbend Invitational Semis]",
    ]


def test_assembly_writes_the_line_without_a_team_for_a_card_with_no_disclosure_on_record(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    world, cards = _sources(parser, (SOURCE_ONE, None))
    built = _build(world, cards, [("Prices", [{"fingerprint": cards[0].fingerprint}])], built_at)
    assert [text for style, text in _paragraphs(built.file.docx) if style == "Undertag"] == [
        "[Disclosed: hspolicy26 2026-09-15]"
    ]
    entry = built.file.manifest.cards[0]
    assert (entry.school, entry.team_code, entry.side, entry.tournament, entry.round) == (None,) * 5
    assert entry.disclosure_digest is not None


@pytest.mark.parametrize(
    ("disclosure", "line"),
    [
        (
            SyntheticDisclosure(),
            "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]",
        ),
        (
            SyntheticDisclosure(tournament=None, round=None),
            "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff]",
        ),
        (
            SyntheticDisclosure(side=Side.UNKNOWN),
            "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Riverbend Invitational Round 4]",
        ),
        (None, "[Disclosed: hspolicy26 2026-09-15]"),
    ],
    ids=["every-field", "no-tournament-or-round", "side-unknown", "no-disclosure"],
)
def test_assembly_composes_the_provenance_line_from_the_record_alone(
    parser: DebateDocxParser, disclosure: SyntheticDisclosure | None, line: str
) -> None:
    _, cards = _sources(parser, (SOURCE_ONE, disclosure))
    assert provenance_line(cards[0].occurrence, cards[0].disclosure) == line


def test_assembly_adds_no_text_but_headings_overrides_analytics_the_header_and_provenance_lines(
    standard: Built,
) -> None:
    """ac2: every paragraph is either copied from a source or one of the strings the writer may write."""
    recipe = standard.resolved.recipe
    allowed = {recipe.title, "Synthetic pocket", "Synthetic hat", "Prices", "Revenue", ALLOWED_ANALYTIC}
    allowed |= {card.tag_override.text for card in standard.resolved.cards if card.tag_override}
    allowed |= {provenance_line(card.occurrence, card.disclosure) for card in standard.resolved.cards}
    allowed.add(_paragraphs(standard.file.docx)[0][1])
    copied = {text for content in (SOURCE_ONE, SOURCE_TWO) for _, text in _paragraphs(content)}
    for _, text in _paragraphs(standard.file.docx):
        assert text in allowed | copied, text


def test_assembly_says_the_cards_are_disclosed_and_unverified_and_never_verified(standard: Built) -> None:
    header = _paragraphs(standard.file.docx)[0][1]
    assert header == (
        "Disclosed cards (FILE_IMPORT) from hspolicy26, each copied from the file that disclosed it and "
        "not verified by this platform. Who disclosed each card is below its cite."
    )
    with zipfile.ZipFile(BytesIO(standard.file.docx)) as archive:
        everything = b"".join(archive.read(name) for name in archive.namelist())
    assert b"VERIFIED" not in everything


def test_assembly_takes_no_card_text_through_its_api() -> None:
    """ac2: the request is a resolved recipe and a time; nothing reachable from it can hold card text."""
    assert [field.name for field in dataclasses.fields(FileBuildRequest)] == ["resolved", "built_at"]
    assert list(inspect.signature(EvidenceFileWriter.build).parameters) == ["self", "request"]
    assert list(inspect.signature(DocxEvidenceFileWriter.__init__).parameters) == [
        "self",
        "snapshots",
        "parser",
        "base",
        "limits",
    ]
    reachable = (
        {field.name for field in dataclasses.fields(ResolvedRecipe)}
        | {field.name for field in dataclasses.fields(ResolvedCard)}
        | set(OccurrenceRecord.model_fields)
        | set(Disclosure.model_fields)
    )
    for name in reachable:
        assert not any(word in name for word in ("evidence", "cite", "run", "body", "text")), name


def test_assembly_writes_a_hyperlinks_target_into_the_built_files_relationships(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    hyperlink_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        f'<Relationship Id="rId5" Type="{hyperlink_type}"'
        ' Target="https://example.org/a" TargetMode="External"/>'
        "</Relationships>"
    )
    linked = (
        '<w:p xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:r><w:rPr><w:rStyle w:val="Style13ptBold"/></w:rPr><w:t>Lindqvist 26</w:t></w:r>'
        '<w:hyperlink r:id="rId5"><w:r>'
        '<w:t xml:space="preserve"> example.org/a</w:t></w:r></w:hyperlink></w:p>'
    )
    content = build_docx(
        tag("Moratoria raise prices") + linked + body("A ", "freeze", " bites."),
        extra_parts={"word/_rels/document.xml.rels": rels},
    )
    world, cards = _sources(parser, (content, SyntheticDisclosure()))
    built = _build(world, cards, [("Prices", [{"fingerprint": cards[0].fingerprint}])], built_at)
    with zipfile.ZipFile(BytesIO(built.file.docx)) as archive:
        relationships = archive.read("word/_rels/document.xml.rels").decode()
        document = archive.read("word/document.xml").decode()
    assert 'Id="rId3"' in relationships and 'Target="https://example.org/a"' in relationships
    assert 'TargetMode="External"' in relationships
    assert 'r:id="rId3"' in document


# ------------------------------------------------------------------------------------------------
# Determinism (node file-assembly; ac5)
# ------------------------------------------------------------------------------------------------


def test_deterministic_the_same_request_builds_the_same_bytes(
    parser: DebateDocxParser, standard: Built, built_at: datetime
) -> None:
    again = DocxEvidenceFileWriter(snapshots=standard.world.snapshots, parser=parser)
    result = asyncio.run(again.build(FileBuildRequest(standard.resolved, built_at)))
    assert isinstance(result, BuiltEvidenceFile)
    assert result.docx == standard.file.docx
    assert result.manifest_json == standard.file.manifest_json


def test_deterministic_a_later_request_changes_the_sidecars_time_and_nothing_else(
    parser: DebateDocxParser, standard: Built, built_at: datetime
) -> None:
    later = built_at + timedelta(days=3, hours=4)
    result = asyncio.run(
        DocxEvidenceFileWriter(snapshots=standard.world.snapshots, parser=parser).build(
            FileBuildRequest(standard.resolved, later)
        )
    )
    assert isinstance(result, BuiltEvidenceFile)
    assert result.docx == standard.file.docx
    before, after = json.loads(standard.file.manifest_json), json.loads(result.manifest_json)
    assert {key for key in before if before[key] != after[key]} == {"built_at"}
    assert after["built_at"] == "2026-10-22T16:30:00.000000Z"


def test_deterministic_a_time_in_another_zone_is_written_as_the_same_instant(
    parser: DebateDocxParser, standard: Built, built_at: datetime
) -> None:
    elsewhere = built_at.astimezone(timezone(timedelta(hours=-5)))
    result = asyncio.run(
        DocxEvidenceFileWriter(snapshots=standard.world.snapshots, parser=parser).build(
            FileBuildRequest(standard.resolved, elsewhere)
        )
    )
    assert isinstance(result, BuiltEvidenceFile)
    assert result.manifest_json == standard.file.manifest_json


def test_deterministic_a_naive_time_is_refused(standard: Built) -> None:
    with pytest.raises(ValueError, match="zone"):
        FileBuildRequest(standard.resolved, datetime(2026, 10, 19, 12, 30))  # noqa: DTZ001


def test_deterministic_zip_entries_are_in_a_fixed_order_with_fixed_dates(standard: Built) -> None:
    with zipfile.ZipFile(BytesIO(standard.file.docx)) as archive:
        infos = archive.infolist()
    assert [info.filename for info in infos] == [
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
        "word/settings.xml",
        "docProps/core.xml",
    ]
    assert {info.date_time for info in infos} == {FIXED_ZIP_TIMESTAMP}
    assert {info.create_system for info in infos} == {0}


def test_deterministic_the_built_file_holds_no_author_no_time_and_no_source_metadata(
    standard: Built, base: Any
) -> None:
    with zipfile.ZipFile(BytesIO(standard.file.docx)) as archive:
        core = archive.read("docProps/core.xml").decode()
        styles = archive.read("word/styles.xml")
    assert "<dc:title>Synthetic file</dc:title>" in core
    for absent in ("creator", "lastModifiedBy", "created", "modified", "revision"):
        assert absent not in core, absent
    assert styles == base.styles_xml, "the style table is the base's, never a source's"


def test_deterministic_the_order_sources_were_stored_in_changes_nothing(
    parser: DebateDocxParser, standard: Built, built_at: datetime
) -> None:
    world, cards = _sources(
        parser,
        (
            SOURCE_TWO,
            SyntheticDisclosure(school="Cedar Hollow", team_code="ZaLu", side=Side.NEG, round="Semis"),
        ),
        (SOURCE_ONE, SyntheticDisclosure()),
    )
    resolved = world.resolve(standard.resolved.recipe, {card.fingerprint: card for card in cards})
    result = asyncio.run(
        DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser).build(
            FileBuildRequest(resolved, built_at)
        )
    )
    assert isinstance(result, BuiltEvidenceFile)
    assert result.docx == standard.file.docx


# ------------------------------------------------------------------------------------------------
# The provenance sidecar (node provenance-sidecar; ac2, ac5)
# ------------------------------------------------------------------------------------------------


def test_provenance_schema_committed_matches_the_models() -> None:
    assert SCHEMA_PATH.is_file(), "missing; run: uv run scripts/export_file_provenance_schema.py"
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == render_file_provenance_schema(), (
        "stale; run: uv run scripts/export_file_provenance_schema.py"
    )


def test_provenance_sidecar_validates_against_the_committed_schema(standard: Built) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(standard.file.manifest_json), schema)


def test_provenance_the_schema_refuses_a_verified_card(standard: Built) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    document = json.loads(standard.file.manifest_json)
    document["cards"][0]["verification_status"] = "VERIFIED"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema)


def test_provenance_has_one_entry_per_card_in_file_order(standard: Built) -> None:
    manifest = standard.file.manifest
    assert [entry.position for entry in manifest.cards] == [1, 2, 3, 4]
    assert [entry.recipe_path for entry in manifest.cards] == [
        "structure[0].hats[0].blocks[0].items[0]",
        "structure[0].hats[0].blocks[0].items[2]",
        "structure[0].hats[0].blocks[1].items[0]",
        "structure[0].hats[0].blocks[1].items[1]",
    ]
    assert [entry.section_path for entry in manifest.cards] == [
        ("Synthetic pocket", "Synthetic hat", "Prices"),
        ("Synthetic pocket", "Synthetic hat", "Prices"),
        ("Synthetic pocket", "Synthetic hat", "Revenue"),
        ("Synthetic pocket", "Synthetic hat", "Revenue"),
    ]


def test_provenance_records_each_cards_occurrence_and_its_source_hashes(standard: Built) -> None:
    for entry, resolved in zip(standard.file.manifest.cards, standard.resolved.cards, strict=True):
        source = standard.cards[resolved.fingerprint]
        occurrence = source.occurrence
        assert entry.fingerprint == resolved.fingerprint == occurrence.exact_fingerprint
        assert (entry.source_sha256, entry.first_element_index, entry.last_element_index) == (
            occurrence.source_sha256,
            occurrence.first_element_index,
            occurrence.last_element_index,
        )
        assert (entry.caselist, entry.snapshot, entry.last_snapshot) == (
            "hspolicy26",
            "2026-09-15",
            "2026-09-22",
        )
        assert entry.disclosure_digest == occurrence.disclosure
        assert entry.evidence_sha256 == text_sha256(source.card.evidence_text)
        assert entry.cite_sha256 == text_sha256(source.card.full_cite)
        assert entry.formatting_sha256 == formatting_sha256(
            source.card.formatting_spans, source.card.font_size_spans
        )
        assert entry.completeness == source.card.completeness
        assert entry.resolution == "AUTO"
        assert entry.provenance_mode is ProvenanceMode.FILE_IMPORT
        assert entry.verification_status is VerificationStatus.UNVERIFIED
        assert entry.provenance_line == provenance_line(occurrence, source.disclosure)


def test_provenance_names_who_disclosed_each_card_exactly_as_disclosed(standard: Built) -> None:
    entries = standard.file.manifest.cards
    assert [
        (entry.school, entry.team_code, entry.side, entry.tournament, entry.round) for entry in entries
    ] == [
        ("Maple Grove", "QX", "AFF", "Riverbend Invitational", "Round 4"),
        ("Maple Grove", "QX", "AFF", "Riverbend Invitational", "Round 4"),
        ("Cedar Hollow", "ZaLu", "NEG", "Riverbend Invitational", "Semis"),
        ("Cedar Hollow", "ZaLu", "NEG", "Riverbend Invitational", "Semis"),
    ]
    assert "QX" not in repr(entries[0]) and "Maple Grove" not in repr(entries[0])


def test_provenance_marks_an_overridden_tag_as_the_coachs_with_the_original_tags_hash(
    standard: Built,
) -> None:
    overridden, kept = standard.file.manifest.cards[0], standard.file.manifest.cards[1]
    assert (overridden.tag_overridden, overridden.tag_authored_by) == (True, TagAuthor.COACH)
    assert overridden.original_tag_sha256 == text_sha256("Moratoria raise prices for every ratepayer")
    assert (kept.tag_overridden, kept.tag_authored_by, kept.original_tag_sha256) == (False, None, None)


def test_provenance_names_the_versions_that_built_the_file_and_the_files_own_hash(standard: Built) -> None:
    manifest = standard.file.manifest
    assert manifest.builder_version == FILE_BUILDER_VERSION
    assert manifest.parser_version == DOCX_PARSER_VERSION == "2026.10.18-docx-5"
    assert manifest.style_profile_version == "2026.09.20-verbatim-1"
    assert manifest.recipe_hash == standard.resolved.recipe_hash
    assert manifest.docx_sha256 == hashlib.sha256(standard.file.docx).hexdigest()
    assert manifest.built_at == datetime(2026, 10, 19, 12, 30, tzinfo=UTC)
    assert FileProvenanceManifest.model_validate_json(standard.file.manifest_json) == manifest


def test_provenance_sidecar_is_named_after_the_file() -> None:
    assert provenance_sidecar_name("nhi-politics.docx") == "nhi-politics.docx.provenance.json"


def test_provenance_counts_each_cards_forbidden_characters(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    raw = (
        '<w:p><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/><w:highlight w:val="cyan"/></w:rPr>'
        '<w:t xml:space="preserve">Prices\x01 climb￾ everywhere.</w:t></w:r></w:p>'
    )
    content = build_docx(tag("Moratoria raise prices") + cite("Lindqvist 26") + raw + SOURCE_ONE_TAIL)
    world, cards = _sources(parser, (content, SyntheticDisclosure()))
    built = _build(
        world, cards, [("Prices", [{"fingerprint": card.fingerprint} for card in cards])], built_at
    )
    assert [entry.forbidden_characters_replaced for entry in built.file.manifest.cards] == [2, 0]
    assert "Prices� climb� everywhere." in [text for _, text in _paragraphs(built.file.docx)]


SOURCE_ONE_TAIL = (
    tag("Reliability falls first in the summer peak")
    + cite("Okonkwo 25", ", Grid Analyst, Synthetic Utility Quarterly, 2025")
    + body("Operators ", "shed load", " when reserves run thin.")
)


def test_provenance_lists_an_unmapped_style_as_a_warning(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    styles = build_styles_xml((*DEFAULT_STYLE_DEFINITIONS, ("FancyChar", "character", "Fancy Char", None)))
    fancy = paragraph_xml(
        run_xml("A moratorium ", half_points=16)
        + run_xml("freezes supply", character_style="FancyChar", highlight="cyan")
    )
    content = build_docx(tag("Moratoria raise prices") + cite("Lindqvist 26") + fancy, styles_xml=styles)
    world, cards = _sources(parser, (content, SyntheticDisclosure()))
    built = _build(world, cards, [("Prices", [{"fingerprint": cards[0].fingerprint}])], built_at)
    message = (
        "the source's character style 'FancyChar' ('Fancy Char') is not one the style profile maps; "
        "it was removed and the direct formatting kept"
    )
    assert built.file.manifest.cards[0].warnings == (message,)
    assert built.file.warnings == (f"structure[0].hats[0].blocks[0].items[0]: {message}",)


# ------------------------------------------------------------------------------------------------
# Refusals: nothing partial (ac4)
# ------------------------------------------------------------------------------------------------

DRAWING_NAMESPACES = (
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

UNSUPPORTED = {
    UnsupportedContentKind.IMAGE: (
        '<w:drawing><wp:inline><a:graphic><a:graphicData><pic:pic><pic:blipFill><a:blip r:embed="rId9"/>'
        "</pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"
    ),
    UnsupportedContentKind.TEXT_BOX: (
        "<w:drawing><wp:anchor><a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>"
        "<w:p><w:r><w:t>a margin note</w:t></w:r></w:p></w:txbxContent></wps:txbx></wps:wsp></a:graphicData>"
        "</a:graphic></wp:anchor></w:drawing>"
    ),
    UnsupportedContentKind.EMBEDDED_OBJECT: (
        '<w:object><v:shape id="_x0000_i1025"/><o:OLEObject ProgID="Excel.Sheet.12" r:id="rId10"/></w:object>'
    ),
    UnsupportedContentKind.FOOTNOTE: '<w:footnoteReference w:id="1"/>',
}


def _holding(inner: str, words: str = "Prices climb ") -> str:
    return (
        f"<w:p {DRAWING_NAMESPACES}>"
        f'<w:r><w:rPr><w:highlight w:val="cyan"/></w:rPr><w:t xml:space="preserve">{words}</w:t></w:r>'
        f"<w:r>{inner}</w:r></w:p>"
    )


@pytest.mark.parametrize("kind", list(UNSUPPORTED), ids=lambda kind: str(kind).lower())
def test_refusal_a_card_with_content_that_cannot_be_copied_refuses_the_whole_file(
    parser: DebateDocxParser, built_at: datetime, kind: UnsupportedContentKind
) -> None:
    bad = build_docx(tag("Moratoria raise prices") + cite("Lindqvist 26") + _holding(UNSUPPORTED[kind]))
    world, cards = _sources(parser, (SOURCE_ONE, SyntheticDisclosure()), (bad, SyntheticDisclosure()))
    built = _build(
        world, cards, [("Prices", [{"fingerprint": card.fingerprint} for card in cards])], built_at
    )
    assert isinstance(built.result, FileBuildRefusal)
    assert [(refusal.path, refusal.code, refusal.content_kinds) for refusal in built.result.refusals] == [
        ("structure[0].hats[0].blocks[0].items[2]", CardRefusalCode.UNSUPPORTED_CONTENT, (kind,))
    ]
    assert built.result.refusals[0].fingerprint == cards[2].fingerprint


def test_refusal_every_card_that_cannot_be_copied_is_listed(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    bad = build_docx(
        tag("Moratoria raise prices")
        + cite("Lindqvist 26")
        + _holding(UNSUPPORTED[UnsupportedContentKind.IMAGE])
        + tag("Reliability falls")
        + cite("Okonkwo 25")
        + _holding(
            UNSUPPORTED[UnsupportedContentKind.FOOTNOTE] + UNSUPPORTED[UnsupportedContentKind.TEXT_BOX],
            "Reserves run thin ",
        )
    )
    world, cards = _sources(parser, (bad, SyntheticDisclosure()), (SOURCE_TWO, SyntheticDisclosure()))
    built = _build(
        world, cards, [("Prices", [{"fingerprint": card.fingerprint} for card in cards])], built_at
    )
    assert isinstance(built.result, FileBuildRefusal)
    assert [(refusal.path, set(refusal.content_kinds)) for refusal in built.result.refusals] == [
        ("structure[0].hats[0].blocks[0].items[0]", {UnsupportedContentKind.IMAGE}),
        (
            "structure[0].hats[0].blocks[0].items[1]",
            {UnsupportedContentKind.FOOTNOTE, UnsupportedContentKind.TEXT_BOX},
        ),
    ]
    assert not hasattr(built.result, "docx"), "a refused file has no bytes to hand back"


def test_refusal_a_source_missing_from_the_blob_store(parser: DebateDocxParser, built_at: datetime) -> None:
    world, cards = _sources(parser, (SOURCE_ONE, SyntheticDisclosure()))
    recipe = world.recipe([("Prices", [{"fingerprint": cards[0].fingerprint}])])
    resolved = world.resolve(recipe, {cards[0].fingerprint: cards[0]})
    empty = FileBuilderWorld(parser=parser)
    result = asyncio.run(
        DocxEvidenceFileWriter(snapshots=empty.snapshots, parser=parser).build(
            FileBuildRequest(resolved, built_at)
        )
    )
    assert isinstance(result, FileBuildRefusal)
    assert [refusal.code for refusal in result.refusals] == [CardRefusalCode.SOURCE_UNAVAILABLE]


def test_refusal_a_source_whose_stored_bytes_changed(parser: DebateDocxParser, built_at: datetime) -> None:
    world, cards = _sources(parser, (SOURCE_ONE, SyntheticDisclosure()))
    world.snapshots.corrupt(cards[0].occurrence.source_sha256, SOURCE_TWO)
    built = _build(world, cards[:1], [("Prices", [{"fingerprint": cards[0].fingerprint}])], built_at)
    assert isinstance(built.result, FileBuildRefusal)
    assert [refusal.code for refusal in built.result.refusals] == [CardRefusalCode.SOURCE_UNAVAILABLE]


def test_refusal_a_source_the_parser_refuses(parser: DebateDocxParser, built_at: datetime) -> None:
    world, cards = _sources(parser, (SOURCE_ONE, SyntheticDisclosure()))
    not_a_docx = b"%PDF-1.7 a synthetic pdf"
    sha = asyncio.run(world.snapshots.put(not_a_docx))
    moved = dataclasses.replace(
        cards[0], occurrence=cards[0].occurrence.model_copy(update={"source_sha256": sha})
    )
    built = _build(world, [moved], [("Prices", [{"fingerprint": moved.fingerprint}])], built_at)
    assert isinstance(built.result, FileBuildRefusal)
    assert [refusal.code for refusal in built.result.refusals] == [CardRefusalCode.SOURCE_UNREADABLE]


@pytest.mark.parametrize(
    "update",
    [
        {"first_element_index": 1},
        {"last_element_index": 1},
        {"first_element_index": 3, "last_element_index": 5},
    ],
    ids=["first-index", "last-index", "another-card"],
)
def test_refusal_an_occurrence_that_does_not_point_at_its_card(
    parser: DebateDocxParser, built_at: datetime, update: dict[str, int]
) -> None:
    world, cards = _sources(parser, (SOURCE_ONE, SyntheticDisclosure()))
    moved = dataclasses.replace(cards[0], occurrence=cards[0].occurrence.model_copy(update=update))
    built = _build(world, [moved], [("Prices", [{"fingerprint": moved.fingerprint}])], built_at)
    assert isinstance(built.result, FileBuildRefusal)
    assert [refusal.code for refusal in built.result.refusals] == [CardRefusalCode.OCCURRENCE_MISMATCH]


def test_refusal_a_card_that_would_merge_into_the_card_before_it_on_read_back(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    """A card with no tag, placed after a cite-only card, would be read as more of that card's cite."""
    untagged = build_docx(cite("Achterberg 26") + body("Revenue ", "grows", " with every site."))
    world, cards = _sources(parser, (SOURCE_TWO, SyntheticDisclosure()), (untagged, SyntheticDisclosure()))
    cite_only, tagless = cards[1], cards[2]
    assert not tagless.card.has_tag
    built = _build(
        world,
        [cite_only, tagless],
        [("Revenue", [{"fingerprint": cite_only.fingerprint}, {"fingerprint": tagless.fingerprint}])],
        built_at,
    )
    assert isinstance(built.result, FileBuildRefusal)
    assert {refusal.code for refusal in built.result.refusals} == {CardRefusalCode.READBACK_MISMATCH}


def test_refusal_messages_name_no_school_team_or_card_text(
    parser: DebateDocxParser, built_at: datetime
) -> None:
    bad = build_docx(
        tag("Moratoria raise prices")
        + cite("Lindqvist 26")
        + _holding(UNSUPPORTED[UnsupportedContentKind.IMAGE])
    )
    world, cards = _sources(parser, (bad, SyntheticDisclosure()))
    built = _build(world, cards, [("Prices", [{"fingerprint": cards[0].fingerprint}])], built_at)
    assert isinstance(built.result, FileBuildRefusal)
    message = str(built.result.refusals[0])
    for absent in ("Maple Grove", "QX", "Lindqvist", "Moratoria", "Prices climb"):
        assert absent not in message, absent

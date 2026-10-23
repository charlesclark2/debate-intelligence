"""A built file loses its provenance-line paragraphs and nothing else; the sidecar stays (`v1-e33-t08`).

Data-use policy version 1.11 (Attribution rules 2, 3 and 5): a built file carries no provenance line,
and the sidecar keeps every card's provenance, because a removal request is matched against it.

`files_built_with_the_provenance_line/` holds four files and their sidecars as the writer built them
before this task (`2026.10.19-file-writer-2`, at the task's start commit), from the synthetic sources
below: disclosed cards, a camp card with and without its release record, and a card with no
disclosure on record. Each test builds the same request again and compares:

* **the file**, paragraph by paragraph: the recorded file with the paragraphs listed by hand in
  `LINES` taken out is the new file, every other paragraph, run and style byte for byte, and every
  other part of the package too;
* **the sidecar**, byte for byte, but for `docx_sha256`, which is the new file's own hash.

The recorded files are the old writer's output, not this writer's; the paragraphs to take out and
the lines they held are written by hand from the sources (working agreement 6).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import pytest
from lxml import etree

from debate_core.application.file_recipes import ResolvedRecipe
from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile, FileBuildRequest
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.domain.caselist import CampFile, Event, Side
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.package import W_NAMESPACE
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import FileBuilderWorld, SourceCard, SyntheticDisclosure

RECORDED = Path(__file__).resolve().parent / "files_built_with_the_provenance_line"
BUILT_AT: Final = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)
W: Final = f"{{{W_NAMESPACE}}}"
PARSER: Final = DebateDocxParser()


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

CAMP_SOURCE = build_docx(
    tag("Grid upgrades cost less than new plants")
    + cite("Vasquez-Hale 31", ", Engineer, Synthetic Transmission Journal, 2031")
    + body("Reconductoring ", "doubles capacity", " on existing corridors.")
)

#: An invented camp, release and file title, never a real OpenEv file.
CAMP = "Lanternfield Institute"
CAMP_TITLE = "Synthetic Grid Reliability CP"
RELEASE = "2031-policy"

MAPLE = "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]"
CEDAR = "[Disclosed: hspolicy26 2026-09-15 — Cedar Hollow ZaLu, Neg vs. Riverbend Invitational Semis]"
CAMP_LINE = f"[OpenEv: {CAMP} 2031 — Policy, {CAMP_TITLE}]"
CAMP_LINE_WITHOUT_A_RECORD = f"[OpenEv: {CAMP} 2031 — Policy]"
NO_DISCLOSURE = "[Disclosed: hspolicy26 2026-09-15]"

#: For each recorded file, the body paragraphs that held a provenance line and the line each held,
#: counted by hand from the recipe: the header, a pocket, a hat and a block, then each card's tag,
#: cite, line and body (a cite-only card has no body), with the analytic between the first two cards.
LINES: Final[dict[str, dict[int, str]]] = {
    "disclosed-cards": {6: MAPLE, 11: MAPLE, 16: CEDAR, 19: CEDAR},
    "camp-card-with-its-release-record": {6: MAPLE, 10: CAMP_LINE},
    "camp-card-without-a-release-record": {6: MAPLE, 10: CAMP_LINE_WITHOUT_A_RECORD},
    "no-disclosure-on-record": {6: NO_DISCLOSURE},
}


def _world(*contents: tuple[bytes, SyntheticDisclosure | None]) -> tuple[FileBuilderWorld, list[SourceCard]]:
    world = FileBuilderWorld(parser=PARSER)
    cards: list[SourceCard] = []
    for content, disclosure in contents:
        cards.extend(asyncio.run(world.add_source(content, disclosure=disclosure)))
    return world, cards


def _write(world: FileBuilderWorld, resolved: ResolvedRecipe) -> BuiltEvidenceFile:
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=PARSER)
    built = asyncio.run(writer.build(FileBuildRequest(resolved, BUILT_AT)))
    assert isinstance(built, BuiltEvidenceFile), built
    return built


def disclosed_cards() -> BuiltEvidenceFile:
    """Four disclosed cards of two teams, one re-tagged by the coach, an analytic, a cite-only card."""
    world, cards = _world(
        (SOURCE_ONE, SyntheticDisclosure()),
        (
            SOURCE_TWO,
            SyntheticDisclosure(school="Cedar Hollow", team_code="ZaLu", side=Side.NEG, round="Semis"),
        ),
    )
    first, second, third, fourth = cards
    recipe = world.recipe(
        [
            (
                "Prices",
                [
                    {"fingerprint": first.fingerprint, "tag_override": "Prices rise - the coach's own tag"},
                    {"analytic": "The moratorium trades a small saving for a large risk."},
                    {"fingerprint": second.fingerprint},
                ],
            ),
            ("Revenue", [{"fingerprint": third.fingerprint}, {"fingerprint": fourth.fingerprint}]),
        ]
    )
    return _write(world, world.resolve(recipe, {card.fingerprint: card for card in cards}))


def _camp_card(source: SourceCard) -> SourceCard:
    """The card as the parse pipeline records it in a camp release: no disclosure, one release."""
    occurrence = OccurrenceRecord.model_validate(
        {
            **source.occurrence.model_dump(),
            "caselist": "openev",
            "snapshot": RELEASE,
            "last_snapshot": RELEASE,
            "disclosure": None,
            "camp": CAMP,
        }
    )
    return dataclasses.replace(source, occurrence=occurrence, disclosure=None)


def _camp_build(*, with_record: bool) -> BuiltEvidenceFile:
    """A disclosed card, then a camp card pinned by its release, in one block."""
    world, cards = _world((SOURCE_ONE, SyntheticDisclosure()), (CAMP_SOURCE, None))
    disclosed, camp = cards[0], _camp_card(cards[2])
    recipe = world.recipe(
        [("Reliability", [{"fingerprint": disclosed.fingerprint}, {"fingerprint": camp.fingerprint}])]
    )
    resolved = world.resolve(
        recipe, {disclosed.fingerprint: disclosed, camp.fingerprint: camp}, pinned=[camp.fingerprint]
    )
    record = (
        CampFile(
            source_sha256=camp.occurrence.source_sha256,
            camp=CAMP,
            year=2031,
            event=Event.POLICY,
            file_title=CAMP_TITLE,
            snapshot=date(2026, 7, 30),
        )
        if with_record
        else None
    )
    joined = tuple(
        dataclasses.replace(card, camp_file=record if card.fingerprint == camp.fingerprint else None)
        for card in resolved.cards
    )
    versions = {card.occurrence.caselist: card.occurrence.parser_version for card in resolved.cards}
    return _write(world, dataclasses.replace(resolved, cards=joined, versions=versions))


def no_disclosure_on_record() -> BuiltEvidenceFile:
    """One card whose occurrence has no disclosure on record (t01's AUTO falls back to one)."""
    world, cards = _world((SOURCE_ONE, None))
    recipe = world.recipe([("Prices", [{"fingerprint": cards[0].fingerprint}])])
    return _write(world, world.resolve(recipe, {cards[0].fingerprint: cards[0]}))


BUILDS: Final[dict[str, Callable[[], BuiltEvidenceFile]]] = {
    "disclosed-cards": disclosed_cards,
    "camp-card-with-its-release-record": lambda: _camp_build(with_record=True),
    "camp-card-without-a-release-record": lambda: _camp_build(with_record=False),
    "no-disclosure-on-record": no_disclosure_on_record,
}


@dataclasses.dataclass(frozen=True)
class Recorded:
    docx: bytes
    sidecar: bytes


@pytest.fixture(scope="module", params=list(BUILDS))
def case(request: pytest.FixtureRequest) -> tuple[str, Recorded, BuiltEvidenceFile]:
    name: str = request.param
    recorded = Recorded(
        docx=(RECORDED / f"{name}.docx").read_bytes(),
        sidecar=(RECORDED / f"{name}.docx.provenance.json").read_bytes(),
    )
    return name, recorded, BUILDS[name]()


def _parts(docx: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(BytesIO(docx)) as archive:
        return [(info.filename, archive.read(info.filename)) for info in archive.infolist()]


def _document(docx: bytes) -> Any:
    return etree.fromstring(dict(_parts(docx))["word/document.xml"])


def _style_and_text(paragraph: Any) -> tuple[str | None, str]:
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    text = "".join(t.text or "" for t in paragraph.iter(f"{W}t"))
    return (None if style is None else style.get(f"{W}val")), text


def _paragraphs(root: Any) -> list[Any]:
    paragraphs = list(root.find(f"{W}body"))
    assert all(child.tag == f"{W}p" for child in paragraphs), "a built body holds paragraphs alone"
    return paragraphs


def test_the_recorded_files_held_the_line_where_counted(
    case: tuple[str, Recorded, BuiltEvidenceFile],
) -> None:
    """The paragraphs counted by hand are the recorded file's Undertag lines, and the only ones."""
    name, recorded, _ = case
    paragraphs = _paragraphs(_document(recorded.docx))
    lines = {
        index: text
        for index, (style, text) in enumerate(map(_style_and_text, paragraphs))
        if style == "Undertag"
    }
    assert lines == LINES[name]


def test_the_file_is_the_recorded_one_without_its_provenance_line_paragraphs(
    case: tuple[str, Recorded, BuiltEvidenceFile],
) -> None:
    name, recorded, built = case
    before = _document(recorded.docx)
    kept = [
        etree.tostring(paragraph)
        for index, paragraph in enumerate(_paragraphs(before))
        if index not in LINES[name]
    ]
    assert [etree.tostring(paragraph) for paragraph in _paragraphs(_document(built.docx))] == kept
    for index in sorted(LINES[name], reverse=True):
        before.find(f"{W}body").remove(_paragraphs(before)[index])
    document = etree.tostring(before, xml_declaration=True, encoding="UTF-8", standalone=True)
    assert dict(_parts(built.docx))["word/document.xml"] == document
    others = [(part, data) for part, data in _parts(recorded.docx) if part != "word/document.xml"]
    assert [(part, data) for part, data in _parts(built.docx) if part != "word/document.xml"] == others
    assert [part for part, _ in _parts(built.docx)] == [part for part, _ in _parts(recorded.docx)]


def test_the_sidecar_is_the_recorded_one_byte_for_byte_but_the_files_own_hash(
    case: tuple[str, Recorded, BuiltEvidenceFile],
) -> None:
    name, recorded, built = case
    old_hash = hashlib.sha256(recorded.docx).hexdigest()
    new_hash = hashlib.sha256(built.docx).hexdigest()
    assert json.loads(recorded.sidecar)["docx_sha256"] == old_hash
    assert recorded.sidecar.count(old_hash.encode()) == 1
    assert built.manifest_json == recorded.sidecar.replace(old_hash.encode(), new_hash.encode())
    assert [entry.provenance_line for entry in built.manifest.cards] == list(LINES[name].values())


def test_no_paragraph_of_the_built_file_holds_a_provenance_line(
    case: tuple[str, Recorded, BuiltEvidenceFile],
) -> None:
    name, _, built = case
    texts = [_style_and_text(paragraph) for paragraph in _paragraphs(_document(built.docx))]
    assert "Undertag" not in {style for style, _ in texts}
    for _, text in texts:
        assert "[Disclosed: " not in text and "[OpenEv: " not in text, text
        assert not any(line in text for line in LINES[name].values()), text


def _recorded_names() -> Sequence[str]:
    return sorted(path.name for path in RECORDED.iterdir() if path.suffix in {".docx", ".json"})


def test_every_recorded_file_is_one_of_the_four_builds() -> None:
    assert _recorded_names() == sorted(
        name for build in BUILDS for name in (f"{build}.docx", f"{build}.docx.provenance.json")
    )

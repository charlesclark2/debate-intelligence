"""FileBuildService: a recipe to a built file, its sidecar and its quality report (`v1-e33-t03`).

The service runs over an in-memory parsed store, caselist records, suppression list and blob store,
with the real E31 parser, the real lossless writer (`v1-e33-t02`) and the real quality checks
(`v1-e33-t04`). Each source is synthetic, built with `debate_core.testing.docx_builder`, and each
card's occurrence row is made as the parse pipeline makes it
(:class:`~debate_core.testing.file_builder.FileBuilderWorld`). Built files go to `tmp_path`, which is
in no git working tree.

What is tested, in the order a build asks:

* every :class:`~debate_core.application.file_recipes.RecipeError` is listed and nothing is written
  (ac1); a build writes the `.docx`, its sidecar and a PASS report, and counts what it placed (ac1);
* a draft is refused unless allowed, and then says DRAFT (ac2);
* a store of another parser or fingerprint version is refused once, before any card is resolved, with
  both versions and the re-parse named (ac8); so is one whose newest generation was written under
  another style profile, in the same refusal, which names every version that differs (`v1-e33-t09`);
* an output directory inside a git working tree is refused before anything is resolved (ac10);
* a card resolved to an unattributed occurrence is named before any source is read (ac7);
* a missing source fails its card with `SOURCE_MISSING` and `store get`, and no file is built (ac4);
* a quality FAIL names the failing checks and keeps the files (ac5); the build runs the quality
  service it was given (ac10);
* `check` says why a file built by a writer of provenance lines fails `provenance-complete`.

Counts are worked out by hand from the recipe each test writes. Every school and team code is invented.
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

import pytest
import yaml

from debate_core.application.file_build_service import (
    BuildFileRequest,
    BuildRefusalCode,
    BuildStatus,
    FileBuildResult,
    FileBuildService,
    UnattributedCard,
)
from debate_core.application.file_quality_service import CheckedFile, FileQualityService
from debate_core.application.file_recipes import RecipeErrorCode
from debate_core.application.file_suggest_service import CP_TEXT_SLOT
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    FileBuildRefusal,
    FileBuildRequest,
)
from debate_core.application.ports.parsed_store import OccurrenceRecord, version_directory_name
from debate_core.domain.caselist import Side
from debate_core.domain.file_provenance import provenance_sidecar_name
from debate_core.evidence.file_checks.report import CheckStatus, QualityCheck
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.evidence.style_profile_loader import load_style_profile
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore
from debate_core.testing.fakes.persistence import InMemorySnapshotStore
from debate_core.testing.fakes.suppression import empty_suppression_list
from debate_core.testing.file_builder import (
    DEFAULT_DISCLOSURE,
    FileBuilderWorld,
    SourceCard,
    SyntheticDisclosure,
)

PARSER: Final = DebateDocxParser()
BUILT_AT: Final = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
CASELIST: Final = "hspolicy26"
W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
OLD_PARSER: Final = "2026.10.18-docx-4"
OLD_FINGERPRINTS: Final = "card-fingerprint-v3"
OTHER_PROFILE: Final = "2026.11.02-verbatim-2"
#: The same parser version reading through a style profile of another version: what a profile change
#: under one parser version parses a caselist's next generation with.
OTHER_PROFILE_PARSER: Final = DebateDocxParser(
    load_style_profile().model_copy(update={"profile_version": OTHER_PROFILE})
)
SECOND_GENERATION: Final = version_directory_name(PARSER.parser_version, 2)

RECORDED: Final = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "docx_file_writer"
    / "files_built_with_the_provenance_line"
)


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


#: The same bytes as `test_built_files_without_the_line.py`'s first source: the recorded old-writer
#: file `no-disclosure-on-record` was built from it.
SOURCE_ONE: Final = build_docx(
    tag("Moratoria raise prices for every ratepayer")
    + cite("Lindqvist 26")
    + body("A moratorium ", "freezes supply", " while demand rises.")
    + tag("Reliability falls first in the summer peak")
    + cite("Okonkwo 25", ", Grid Analyst, Synthetic Utility Quarterly, 2025")
    + body("Operators ", "shed load", " when reserves run thin.")
)

SOURCE_TWO: Final = build_docx(
    tag("Data centres bring tax revenue")
    + cite("Achterberg 26", ", Economist, Synthetic Fiscal Review, 2026")
    + body("Each campus ", "pays more in property tax", " than the farm it replaced.")
)

CEDAR: Final = SyntheticDisclosure(
    school="Cedar Hollow",
    team_code="ZaLu",
    side=Side.NEG,
    round="Semis",
    path="Cedar Hollow/ZaLu/aff-riverbend-semis.docx",
)


class RecordingQuality:
    """The real quality service, with a record of each file it was asked to check."""

    def __init__(self, inner: FileQualityService) -> None:
        self.inner = inner
        self.checked: list[Path] = []

    async def check(self, built_path: Path) -> CheckedFile:
        self.checked.append(built_path)
        return await self.inner.check(built_path)


class SpyStore(InMemoryParsedStore):
    """The parsed store, counting the reads that resolving a card makes."""

    def __init__(self) -> None:
        super().__init__()
        self.occurrence_reads = 0

    async def read_occurrences(self, caselist: str, version: str) -> tuple[OccurrenceRecord, ...] | None:
        self.occurrence_reads += 1
        return await super().read_occurrences(caselist, version)


class SpyWriter:
    """The real writer, with the order of events recorded by the test's own list."""

    def __init__(self, inner: DocxEvidenceFileWriter, events: list[str]) -> None:
        self.inner = inner
        self.events = events

    async def build(self, request: FileBuildRequest) -> BuiltEvidenceFile | FileBuildRefusal:
        self.events.append("writer")
        return await self.inner.build(request)


@dataclass
class World:
    """One caselist's parsed store, records and blobs, with the build service over them."""

    root: Path
    files: FileBuilderWorld = field(default_factory=lambda: FileBuilderWorld(parser=PARSER))
    store: SpyStore = field(default_factory=SpyStore)
    caselists: InMemoryCaselistRepository = field(default_factory=InMemoryCaselistRepository)
    rows: list[OccurrenceRecord] = field(default_factory=lambda: [])
    events: list[str] = field(default_factory=lambda: [])

    def add(
        self, content: bytes, disclosure: SyntheticDisclosure | None = DEFAULT_DISCLOSURE
    ) -> list[SourceCard]:
        cards = asyncio.run(self.files.add_source(content, disclosure=disclosure))
        for card in cards:
            self.rows.append(card.occurrence)
        if cards and cards[0].disclosure is not None:
            asyncio.run(self.caselists.record_disclosure(cards[0].disclosure))
        self.publish()
        return list(cards)

    def publish(self, *, version: str | None = None, rows: Sequence[OccurrenceRecord] | None = None) -> None:
        asyncio.run(
            self.store.write_aggregates(
                CASELIST,
                version or PARSER.parser_version,
                index=(),
                failures=(),
                occurrences=self.rows if rows is None else rows,
            )
        )

    def service(
        self,
        *,
        blobs: InMemorySnapshotStore | None = None,
        quality_blobs: InMemorySnapshotStore | None = None,
    ) -> tuple[FileBuildService, RecordingQuality]:
        blobs = blobs if blobs is not None else self.files.snapshots
        suppression = empty_suppression_list()
        quality = RecordingQuality(
            FileQualityService(
                parser=PARSER,
                snapshots=quality_blobs if quality_blobs is not None else blobs,
                suppression=suppression,
            )
        )
        writer = SpyWriter(DocxEvidenceFileWriter(snapshots=blobs, parser=PARSER), self.events)
        service = FileBuildService(
            parsed_store=self.store,
            caselists=self.caselists,
            suppression=suppression,
            blobs=blobs,
            writer=writer,
            quality=quality,  # pyright: ignore[reportArgumentType]
            parser_version=PARSER.parser_version,
            profile_version=PARSER.profile_version,
            files_dir=self.root / "files",
            clock=lambda: BUILT_AT,
        )
        return service, quality

    def recipe(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        name: str = "synthetic-file",
        status: str = "ready",
        pins: Mapping[str, Any] | None = None,
    ) -> Path:
        document = {
            "schema_version": 1,
            "title": "Synthetic file",
            "topic": "synthetic-topic",
            "format": "POLICY",
            "caselist": CASELIST,
            "position": "synthetic-position",
            "side": "AFF",
            "fingerprint_version": FINGERPRINT_VERSION,
            "status": status,
            "structure": [
                {"pocket": "Synthetic pocket", "blocks": [{"block": "Synthetic block", "items": list(items)}]}
            ],
        }
        path = self.root / "recipes" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def build(
        self, recipe: Path, *, out_dir: Path | None = None, allow_draft: bool = False, **service: Any
    ) -> FileBuildResult:
        built, _ = self.service(**service)

        def heard(cards: Sequence[UnattributedCard]) -> None:
            self.events.append(f"unattributed:{len(cards)}")

        return asyncio.run(
            built.build(
                BuildFileRequest(recipe, out_dir=out_dir, allow_draft=allow_draft), on_unattributed=heard
            )
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(root=tmp_path)


def written(root: Path) -> list[str]:
    """Every file under `root/files`, relative to it: what a build left behind."""
    files = root / "files"
    return (
        sorted(str(path.relative_to(files)) for path in files.rglob("*") if path.is_file())
        if files.exists()
        else []
    )


# ------------------------------------------------------------------------------------------------
# ac1: a build writes three files and counts what it placed; every RecipeError is listed
# ------------------------------------------------------------------------------------------------


def test_a_build_writes_the_docx_its_sidecar_and_a_pass_report_and_counts_what_it_placed(
    world: World,
) -> None:
    first, second = world.add(SOURCE_ONE)
    (third,) = world.add(SOURCE_TWO, CEDAR)
    recipe = world.recipe(
        [
            {"fingerprint": first.fingerprint, "tag_override": "Prices rise - the coach's own tag"},
            {"analytic": "The moratorium trades a small saving for a large risk."},
            {"fingerprint": second.fingerprint},
            {"fingerprint": third.fingerprint},
        ]
    )
    result = world.build(recipe)

    assert (result.status, result.refusal, result.recipe_errors) == (BuildStatus.BUILT, None, ())
    assert written(world.root) == [
        "built/synthetic-topic/synthetic-file.docx",
        "built/synthetic-topic/synthetic-file.docx.provenance.json",
        "built/synthetic-topic/synthetic-file.docx.quality.json",
        "built/synthetic-topic/synthetic-file.docx.quality.md",
    ]
    assert (
        result.files is not None
        and result.files.docx == world.root / "files" / "built" / "synthetic-topic" / "synthetic-file.docx"
    )
    quality = json.loads(result.files.quality_json.read_text(encoding="utf-8"))
    assert quality["status"] == "PASS"
    assert result.counts is not None
    assert (result.counts.cards_placed, result.counts.sources_used, result.counts.tag_overrides) == (3, 2, 1)
    assert result.counts.analytics == 1
    assert result.unattributed == ()


def test_a_build_writes_the_header_analytic_first_and_the_pocket_after_it(world: World) -> None:
    """`v1-e39-t24` lets the pilot's download leave the header line out; `files build` never does."""
    (first, _) = world.add(SOURCE_ONE)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.files is not None
    with zipfile.ZipFile(result.files.docx) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    texts = ["".join(text.text or "" for text in paragraph.iter(f"{W}t")) for paragraph in root.iter(f"{W}p")]
    assert texts[:3] == [
        f"Disclosed cards (FILE_IMPORT) from {CASELIST}, each copied from the file that disclosed it and "
        "not verified by this platform.",
        "Synthetic pocket",
        "Synthetic block",
    ]


def test_a_ready_recipe_still_holding_the_cp_text_slot_builds_the_placeholder_as_written(
    world: World,
) -> None:
    """`files suggest`'s counterplan slot (`v1-e33-t11`) is an analytic like any other: nothing refuses it."""
    (first, _) = world.add(SOURCE_ONE)
    result = world.build(world.recipe([{"analytic": CP_TEXT_SLOT}, {"fingerprint": first.fingerprint}]))

    assert result.status is BuildStatus.BUILT and result.files is not None
    with zipfile.ZipFile(result.files.docx) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    texts = ["".join(text.text or "" for text in paragraph.iter(f"{W}t")) for paragraph in root.iter(f"{W}p")]
    assert texts[2:4] == ["Synthetic block", CP_TEXT_SLOT]


def test_a_build_with_out_dir_writes_there(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    out = world.root / "elsewhere"
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]), out_dir=out)
    assert result.files is not None and result.files.docx == out / "synthetic-file.docx"
    assert (out / provenance_sidecar_name("synthetic-file.docx")).is_file()


def test_every_resolution_error_is_listed_and_nothing_is_written(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    unknown_one, unknown_two = "e5" * 32, "f6" * 32
    recipe = world.recipe(
        [
            {"fingerprint": unknown_one},
            {"fingerprint": first.fingerprint},
            {"fingerprint": first.fingerprint},
            {"fingerprint": unknown_two},
        ]
    )
    result = world.build(recipe)

    assert result.status is BuildStatus.REFUSED
    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.RECIPE_UNRESOLVED
    assert [(error.code, error.path) for error in result.recipe_errors] == [
        (RecipeErrorCode.UNKNOWN_CARD, "structure[0].blocks[0].items[0].fingerprint"),
        (RecipeErrorCode.DUPLICATE_REF, "structure[0].blocks[0].items[2].fingerprint"),
        (RecipeErrorCode.UNKNOWN_CARD, "structure[0].blocks[0].items[3].fingerprint"),
    ]
    assert all(error.line is not None for error in result.recipe_errors)
    assert written(world.root) == []
    assert "writer" not in world.events


def test_every_load_error_is_listed_and_nothing_is_resolved(world: World) -> None:
    world.add(SOURCE_ONE)
    recipe = world.recipe([{"fingerprint": "not-a-fingerprint"}, {"fingerprint": "E5" * 32}])
    result = world.build(recipe)

    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.RECIPE_INVALID
    assert [(error.code, error.path) for error in result.recipe_errors] == [
        (RecipeErrorCode.INVALID, "structure[0].blocks[0].items[0].fingerprint"),
        (RecipeErrorCode.INVALID, "structure[0].blocks[0].items[1].fingerprint"),
    ]
    assert world.store.occurrence_reads == 0
    assert written(world.root) == []


# ------------------------------------------------------------------------------------------------
# ac2: a draft is refused unless allowed
# ------------------------------------------------------------------------------------------------


def test_a_draft_is_refused_without_allow_draft_and_nothing_is_resolved(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}], status="draft"))

    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.DRAFT_NOT_ALLOWED
    assert result.refusal.hint is not None and "--allow-draft" in result.refusal.hint
    assert world.store.occurrence_reads == 0
    assert written(world.root) == []


def test_a_draft_builds_with_allow_draft(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}], status="draft"), allow_draft=True)
    assert result.status is BuildStatus.BUILT
    assert result.files is not None and result.files.docx.is_file()


# ------------------------------------------------------------------------------------------------
# ac8: a store another build parsed is refused once, before any card is resolved
# ------------------------------------------------------------------------------------------------


def test_a_store_of_another_parser_version_is_refused_once_before_resolving(world: World) -> None:
    first, second = world.add(SOURCE_ONE)
    world.store = SpyStore()
    world.publish(version=OLD_PARSER)
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": second.fingerprint}])
    )

    assert result.status is BuildStatus.REFUSED
    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert OLD_PARSER in result.refusal.message and PARSER.parser_version in result.refusal.message
    assert (
        result.refusal.hint is not None
        and f"debate-research caselist parse --caselist {CASELIST}" in result.refusal.hint
    )
    assert result.recipe_errors == () and result.card_problems == ()
    assert world.store.occurrence_reads == 0
    assert written(world.root) == []


def test_a_store_of_another_fingerprint_version_is_refused_once_before_resolving(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    world.publish(
        rows=[row.model_copy(update={"fingerprint_version": OLD_FINGERPRINTS}) for row in world.rows]
    )
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert OLD_FINGERPRINTS in result.refusal.message and FINGERPRINT_VERSION in result.refusal.message
    assert result.refusal.hint is not None and "caselist parse --caselist hspolicy26" in result.refusal.hint
    assert world.store.occurrence_reads == 0


def test_a_store_parsed_by_a_newer_parser_too_is_refused(world: World) -> None:
    """The newest directory is the store's version: an older build reading its own older one is refused."""
    first, _ = world.add(SOURCE_ONE)
    world.publish(version="2099.01.01-docx-99")
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))
    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert "2099.01.01-docx-99" in result.refusal.message


def test_every_caselist_a_recipe_reads_is_compared_and_named_in_one_refusal(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    asyncio.run(world.store.write_aggregates("hsld26", OLD_PARSER, index=(), failures=(), occurrences=()))
    pin = {"caselist": "hsld26", "source_sha256": "1a" * 32, "element_index": 0}
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": "b1" * 32, "pin": pin}])
    )

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert "hsld26" in result.refusal.message and OLD_PARSER in result.refusal.message
    assert "hspolicy26" not in result.refusal.message
    assert result.refusal.hint is not None and "--caselist hsld26" in result.refusal.hint


def test_a_caselist_with_no_parsed_store_is_refused_before_resolving(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    pin = {"caselist": "hsld26", "source_sha256": "1a" * 32, "element_index": 0}
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": "b1" * 32, "pin": pin}])
    )
    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.STORE_NOT_PARSED
    assert result.refusal.hint is not None and "caselist parse --caselist hsld26" in result.refusal.hint
    assert world.store.occurrence_reads == 0


def test_the_version_refusal_comes_before_the_git_working_tree_refusal(world: World, tmp_path: Path) -> None:
    first, _ = world.add(SOURCE_ONE)
    world.store = SpyStore()
    world.publish(version=OLD_PARSER)
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]), out_dir=checkout / "built")
    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION


def test_a_store_written_under_another_style_profile_is_refused_once_before_resolving(world: World) -> None:
    """The newest generation of this build's own parser version, parsed through another style profile."""
    first, second = world.add(SOURCE_ONE)
    reparsed = asyncio.run(FileBuilderWorld(parser=OTHER_PROFILE_PARSER).add_source(SOURCE_ONE))
    world.publish(version=SECOND_GENERATION, rows=[card.occurrence for card in reparsed])
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": second.fingerprint}])
    )

    assert result.status is BuildStatus.REFUSED
    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    message = result.refusal.message
    assert OTHER_PROFILE in message and PARSER.profile_version in message
    assert "style profile" in message
    assert "fingerprint" not in message and "parser " not in message
    assert (
        result.refusal.hint is not None
        and result.refusal.hint.count(f"debate-research caselist parse --caselist {CASELIST}") == 1
    )
    assert result.recipe_errors == () and result.card_problems == () and result.unattributed == ()
    assert world.store.occurrence_reads == 0
    assert world.events == []
    assert written(world.root) == []


def test_every_version_that_differs_is_named_with_both_values_in_one_refusal(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    world.store = SpyStore()
    world.publish(
        version=OLD_PARSER,
        rows=[
            row.model_copy(update={"fingerprint_version": OLD_FINGERPRINTS, "profile_version": OTHER_PROFILE})
            for row in world.rows
        ],
    )
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    for version in (
        OLD_PARSER,
        PARSER.parser_version,
        OLD_FINGERPRINTS,
        FINGERPRINT_VERSION,
        OTHER_PROFILE,
        PARSER.profile_version,
    ):
        assert version in result.refusal.message, version
    assert result.refusal.hint is not None and result.refusal.hint.count("--caselist hspolicy26") == 1
    assert world.store.occurrence_reads == 0


def test_a_table_holding_rows_of_this_profile_and_another_is_refused(world: World) -> None:
    first, second = world.add(SOURCE_ONE)
    world.publish(
        rows=[first.occurrence, second.occurrence.model_copy(update={"profile_version": OTHER_PROFILE})]
    )
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert OTHER_PROFILE in result.refusal.message
    assert world.store.occurrence_reads == 0


def test_an_occurrence_table_with_no_rows_names_no_profile_and_is_not_refused_for_one(world: World) -> None:
    """A caselist with nothing parsed yet says nothing about a profile; its pin fails to resolve instead."""
    first, _ = world.add(SOURCE_ONE)
    asyncio.run(
        world.store.write_aggregates("hsld26", PARSER.parser_version, index=(), failures=(), occurrences=())
    )
    pin = {"caselist": "hsld26", "source_sha256": "1a" * 32, "element_index": 0}
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": "b1" * 32, "pin": pin}])
    )
    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.RECIPE_UNRESOLVED


# ------------------------------------------------------------------------------------------------
# v1-e41-t01: the hint says which way to go, and only when the versions say it
# ------------------------------------------------------------------------------------------------

#: A parser version that sorts above this build's, as a newer build's would.
NEWER_PARSER: Final = "2099.01.01-docx-99"

REPARSE_HSPOLICY26: Final = (
    "Re-parse with this build: `debate-research caselist parse --caselist hspolicy26`, then build again."
)


def test_a_store_an_older_parser_wrote_keeps_the_reparse_hint(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    world.store = SpyStore()
    world.publish(version=OLD_PARSER)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert result.refusal.hint == REPARSE_HSPOLICY26


def test_a_store_a_newer_parser_wrote_says_to_install_the_newer_build_and_not_to_reparse(
    world: World,
) -> None:
    """A re-parse here would write this build's parser version, which sorts below the newer directory,
    so the build would read the newer one and refuse again."""
    first, _ = world.add(SOURCE_ONE)
    world.publish(version=NEWER_PARSER)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert result.refusal.message == (
        "this machine's parsed store was not built by this build: hspolicy26 was parsed by parser "
        f"{NEWER_PARSER}, and this build's parser is {PARSER.parser_version}"
    )
    assert result.refusal.hint == (
        f"hspolicy26 was parsed by parser {NEWER_PARSER}, which is newer than this build's "
        f"{PARSER.parser_version}: install that newer build and build with it. A re-parse with this build "
        f"would write a directory that sorts below {NEWER_PARSER}, and the build would refuse again."
    )


def test_a_newer_parser_decides_the_hint_whatever_else_differs(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    world.publish(
        version=NEWER_PARSER,
        rows=[
            row.model_copy(update={"fingerprint_version": OLD_FINGERPRINTS, "profile_version": OTHER_PROFILE})
            for row in world.rows
        ],
    )
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None and result.refusal.hint is not None
    assert result.refusal.hint.startswith(f"hspolicy26 was parsed by parser {NEWER_PARSER}, which is newer")
    assert "Re-parse" not in result.refusal.hint and "style profile" not in result.refusal.hint


def test_a_store_under_another_style_profile_names_both_and_asserts_no_direction(world: World) -> None:
    """Style profile versions have no order: the hint gives both ways and says what decides between them."""
    first, _ = world.add(SOURCE_ONE)
    reparsed = asyncio.run(FileBuilderWorld(parser=OTHER_PROFILE_PARSER).add_source(SOURCE_ONE))
    world.publish(version=SECOND_GENERATION, rows=[card.occurrence for card in reparsed])
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None
    assert result.refusal.code is BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION
    assert result.refusal.hint == (
        f"hspolicy26's occurrence table was read through style profile {OTHER_PROFILE}, and this build's "
        f"style profile is {PARSER.profile_version}. Style profile versions have no order, so which way to "
        "go depends on which build is newer: if this one is, re-parse with it "
        "(`debate-research caselist parse --caselist hspolicy26`), then build again; if the build that "
        "parsed it is, build with that one."
    )


def test_a_profile_and_a_fingerprint_that_differ_keep_the_reparse_hint(world: World) -> None:
    """Only a profile alone leaves the direction open; v1-e33-t03's fingerprint refusal re-parses."""
    first, _ = world.add(SOURCE_ONE)
    world.publish(
        rows=[
            row.model_copy(update={"fingerprint_version": OLD_FINGERPRINTS, "profile_version": OTHER_PROFILE})
            for row in world.rows
        ]
    )
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))

    assert result.refusal is not None and result.refusal.hint == REPARSE_HSPOLICY26


def test_caselists_needing_different_fixes_each_get_their_own_in_one_hint(world: World) -> None:
    """hspolicy26 from a newer parser, hsld26 from an older one: one refusal, and each its own way."""
    first, _ = world.add(SOURCE_ONE)
    world.publish(version=NEWER_PARSER)
    asyncio.run(world.store.write_aggregates("hsld26", OLD_PARSER, index=(), failures=(), occurrences=()))
    pin = {"caselist": "hsld26", "source_sha256": "1a" * 32, "element_index": 0}
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": "b1" * 32, "pin": pin}])
    )

    assert result.refusal is not None
    assert result.refusal.hint == (
        "Re-parse with this build: `debate-research caselist parse --caselist hsld26`, then build again. "
        f"hspolicy26 was parsed by parser {NEWER_PARSER}, which is newer than this build's "
        f"{PARSER.parser_version}: install that newer build and build with it. A re-parse with this build "
        f"would write a directory that sorts below {NEWER_PARSER}, and the build would refuse again."
    )


# ------------------------------------------------------------------------------------------------
# ac10: an output directory inside a git working tree is refused
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("git", ["directory", "file"], ids=["a-checkout", "a-worktree"])
def test_an_output_directory_inside_a_git_working_tree_is_refused_before_resolving(
    world: World, tmp_path: Path, git: str
) -> None:
    first, _ = world.add(SOURCE_ONE)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    if git == "directory":
        (checkout / ".git").mkdir()
    else:
        (checkout / ".git").write_text("gitdir: /elsewhere/.git/worktrees/one\n", encoding="utf-8")
    out = checkout / "deep" / "built"
    result = world.build(
        world.recipe([{"fingerprint": "e5" * 32}, {"fingerprint": first.fingerprint}]), out_dir=out
    )

    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.OUTPUT_IN_A_GIT_WORKING_TREE
    assert result.recipe_errors == ()
    assert world.store.occurrence_reads == 0
    assert not out.exists()


# ------------------------------------------------------------------------------------------------
# ac7: every card resolved to an unattributed occurrence is named before anything is built
# ------------------------------------------------------------------------------------------------


def test_cards_resolved_to_unattributed_occurrences_are_named_before_the_writer_runs(world: World) -> None:
    attributed, _ = world.add(SOURCE_ONE)
    (unattributed,) = world.add(SOURCE_TWO, None)
    recipe = world.recipe(
        [{"fingerprint": attributed.fingerprint}, {"fingerprint": unattributed.fingerprint}]
    )
    result = world.build(recipe)

    assert result.unattributed == (
        UnattributedCard(
            path="structure[0].blocks[0].items[1]", fingerprint=unattributed.fingerprint, caselist=CASELIST
        ),
    )
    assert world.events == ["unattributed:1", "writer"]
    assert result.status is BuildStatus.BUILT


def test_no_card_unattributed_says_nothing(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    result = world.build(world.recipe([{"fingerprint": first.fingerprint}]))
    assert (result.unattributed, world.events) == ((), ["writer"])


# ------------------------------------------------------------------------------------------------
# ac4: a missing source fails its card with SOURCE_MISSING, and no file is built
# ------------------------------------------------------------------------------------------------


def test_a_missing_source_fails_its_cards_with_source_missing_and_store_get_and_builds_nothing(
    world: World,
) -> None:
    first, second = world.add(SOURCE_ONE)
    (third,) = world.add(SOURCE_TWO, CEDAR)
    holding_two = InMemorySnapshotStore()
    asyncio.run(holding_two.put(SOURCE_TWO))
    recipe = world.recipe(
        [
            {"fingerprint": first.fingerprint},
            {"fingerprint": third.fingerprint},
            {"fingerprint": second.fingerprint},
        ]
    )
    result = world.build(recipe, blobs=holding_two)

    assert result.status is BuildStatus.REFUSED
    assert result.refusal is not None and result.refusal.code is BuildRefusalCode.SOURCE_MISSING
    sha = first.occurrence.source_sha256
    key = f"raw/caselist/{CASELIST}/sha256/{sha[:2]}/{sha[2:4]}/{sha}"
    assert [(one.path, one.code) for one in result.card_problems] == [
        ("structure[0].blocks[0].items[0]", "SOURCE_MISSING"),
        ("structure[0].blocks[0].items[2]", "SOURCE_MISSING"),
    ]
    assert all(one.hint == f"debate-research store get {key}" for one in result.card_problems)
    assert "writer" not in world.events
    assert written(world.root) == []


# ------------------------------------------------------------------------------------------------
# ac5 and ac10: the build runs the quality service it was given, and a FAIL names its checks
# ------------------------------------------------------------------------------------------------


def test_the_build_runs_the_quality_service_it_was_given_on_the_file_it_wrote(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    service, quality = world.service()
    result = asyncio.run(service.build(BuildFileRequest(world.recipe([{"fingerprint": first.fingerprint}]))))
    assert result.files is not None
    assert quality.checked == [result.files.docx]


def test_a_quality_fail_names_the_failing_checks_and_keeps_the_files(world: World) -> None:
    """The quality check reads sources from a store that lacks them: evidence identity cannot pass."""
    first, _ = world.add(SOURCE_ONE)
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}]), quality_blobs=InMemorySnapshotStore()
    )

    assert result.status is BuildStatus.QUALITY_FAILED
    assert result.failing_checks == (QualityCheck.EVIDENCE_IDENTITY,)
    assert result.files is not None
    for kept in (
        result.files.docx,
        result.files.provenance,
        result.files.quality_json,
        result.files.quality_markdown,
    ):
        assert kept.is_file()
    assert json.loads(result.files.quality_json.read_text(encoding="utf-8"))["status"] == "FAIL"


# ------------------------------------------------------------------------------------------------
# check: a file built by a writer of provenance lines fails provenance-complete, and says why
# ------------------------------------------------------------------------------------------------


def test_check_says_a_file_built_by_file_writer_2_fails_provenance_complete_and_how_to_rebuild_it(
    world: World, tmp_path: Path
) -> None:
    name = "no-disclosure-on-record.docx"
    copy = tmp_path / "old" / name
    copy.parent.mkdir()
    copy.write_bytes((RECORDED / name).read_bytes())
    sidecar = (RECORDED / provenance_sidecar_name(name)).read_bytes()
    copy.with_name(provenance_sidecar_name(name)).write_bytes(sidecar)
    recorded = json.loads(sidecar)
    assert recorded["builder_version"] == "2026.10.19-file-writer-2"
    sources = InMemorySnapshotStore()
    assert asyncio.run(sources.put(SOURCE_ONE)) == recorded["cards"][0]["source_sha256"]
    service, _ = world.service(blobs=sources)

    checked = asyncio.run(service.check(copy))

    report = checked.checked.report
    assert report.status is CheckStatus.FAIL
    assert [one.check for one in report.checks if one.status is CheckStatus.FAIL] == [
        QualityCheck.PROVENANCE_COMPLETE
    ]
    (note,) = checked.notes
    assert "2026.10.19-file-writer-2" in note
    assert "provenance line" in note and "provenance-complete" in note
    assert "debate-research files build" in note and recorded["recipe_hash"][:12] in note


def test_check_adds_no_note_to_a_file_this_writer_built(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    service, _ = world.service()
    result = asyncio.run(service.build(BuildFileRequest(world.recipe([{"fingerprint": first.fingerprint}]))))
    assert result.files is not None
    checked = asyncio.run(service.check(result.files.docx))
    assert (checked.checked.report.status, checked.notes) == (CheckStatus.PASS, ())


def test_nothing_a_result_holds_names_a_school_or_team(world: World) -> None:
    first, _ = world.add(SOURCE_ONE)
    (unattributed,) = world.add(SOURCE_TWO, None)
    result = world.build(
        world.recipe([{"fingerprint": first.fingerprint}, {"fingerprint": unattributed.fingerprint}])
    )
    shown = repr(result)
    for identity in ("Maple Grove", "QX", "Riverbend"):
        assert identity not in shown

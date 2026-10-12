"""Two record shapes in one store: version 1 as the first corpus parse wrote it, and version 2.

`v1-e31-t09` made "no tag" `null` in a stored card, where the first corpus parse wrote `""`. A
record whose `tag` may be null is a new shape, and `schema_version` is how a reader that does not
go through `ParsedCard` learns which it has: a `jq` line, E32's code, a later cloud reader.

* **Version 1**: a card's `tag` is always a string, and `""` means the file gave it none.
* **Version 2**: a card's `tag` is a string or `null`, and is never `""`.

The `2026.09.20-docx-1` directories stay where they are and stay version 1. So every reader takes
both, and that is shown here on bytes a version-1 build wrote
(`tests/fixtures/parsed_store/written_by_schema_version_1`), not on records made up for the test.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import ValidationError

from debate_core.application.ports.parsed_store import (
    PARSED_STORE_SCHEMA_VERSION,
    DocumentRecord,
    SourceEntry,
    SourceOutcome,
    source_object_key,
)
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

STORED: Final = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "parsed_store"
    / "written_by_schema_version_1"
)
CASELIST: Final = "testcl26"
FIRST_VERSION: Final = "2026.09.20-docx-1"
#: A fictional disclosure path, as the manifests would supply one.
PATH: Final = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
TAG: Final = "Data centre demand collapses the reserve margin"
#: The invented file of two cards under one tag, and the invented failure, in the stored fixture.
TWO_CARDS: Final = "75bb719fd45d0f1ca574c8f9b4dad0d910e41d076d0c3ddf6047e197080ee1d0"
FAILED: Final = "f" * 64


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def stored_lines() -> list[dict[str, Any]]:
    """Every record in the stored fixture, as plain JSON."""
    return [
        json.loads(line)
        for path in sorted((STORED / "parsed").rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def two_cards_under_one_tag() -> ParsedDocument:
    """The same invented file the stored fixture holds, read by the running parser."""

    def cite(name: str) -> str:
        return paragraph_xml(
            run_xml(name, bold=True, half_points=26) + run_xml(", Journal of Grid Studies.", half_points=22)
        )

    def body(text: str) -> str:
        return paragraph_xml(run_xml(text, underline="single", highlight="cyan", half_points=22))

    content = build_docx(
        paragraph_xml(run_xml(TAG), style="Heading4")
        + cite("Okonkwo 26")
        + body("Demand rose faster than any other load category last year.")
        + cite("Ferreira 25")
        + body("Load growth outpaced every scenario the utility had planned against.")
    )
    assert hashlib.sha256(content).hexdigest() == TWO_CARDS, "the stored fixture holds this very file"
    source = SourceDocument(
        sha256=TWO_CARDS,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=date(2026, 9, 1),
        last_seen_snapshot=date(2026, 9, 1),
    )
    document = DebateDocxParser().parse(content, source, source_path=PATH)
    assert isinstance(document, ParsedDocument)
    return document


def record_of(document: ParsedDocument) -> DocumentRecord:
    return DocumentRecord.from_parsed_document(
        document,
        caselist=CASELIST,
        snapshot="2026-09-01",
        fingerprint_version="card-fingerprint-v1",
        camp=None,
    )


# ------------------------------------------------------------------------------------------------
# The stored fixture is what it says it is
# ------------------------------------------------------------------------------------------------


def test_the_stored_fixture_is_a_version_1_store(stored_lines: list[dict[str, Any]]) -> None:
    assert len(stored_lines) == 10
    assert {line["schema_version"] for line in stored_lines} == {1}
    assert {line["parser_version"] for line in stored_lines} == {FIRST_VERSION}
    assert sorted({str(line["record"]) for line in stored_lines}) == ["document", "occurrence", "source"]


def test_the_stored_fixture_says_no_tag_as_an_empty_string(stored_lines: list[dict[str, Any]]) -> None:
    document: dict[str, Any]
    (document,) = [
        line["document"]
        for line in stored_lines
        if line["record"] == "document" and line["source_sha256"] == TWO_CARDS
    ]
    assert [card["tag"] for card in document["cards"]] == [TAG, ""]


# ------------------------------------------------------------------------------------------------
# Version 2 is what is written now
# ------------------------------------------------------------------------------------------------


def test_the_store_writes_schema_version_2() -> None:
    assert PARSED_STORE_SCHEMA_VERSION == 2


@pytest.mark.anyio
async def test_every_record_written_now_says_version_2_and_no_tag_is_null(tmp_path: Path) -> None:
    document = two_cards_under_one_tag()
    record = record_of(document)
    entry = SourceEntry(
        caselist=CASELIST,
        snapshot="2026-09-01",
        source_sha256=TWO_CARDS,
        parser_version=DOCX_PARSER_VERSION,
        profile_version=document.profile_version,
        fingerprint_version="card-fingerprint-v1",
        source_format=SourceFormat.DOCX,
        byte_size=100,
        outcome=SourceOutcome.PARSED,
        cards=2,
    )
    store = LocalParsedStore(tmp_path)
    await store.write_source(CASELIST, DOCX_PARSER_VERSION, entry, record)
    await store.write_aggregates(CASELIST, DOCX_PARSER_VERSION, index=[entry], failures=[], occurrences=[])

    written = [
        json.loads(line)
        for path in sorted(store.root.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [line["schema_version"] for line in written] == [2, 2, 2]
    (stored_document,) = [line["document"] for line in written if line["record"] == "document"]
    assert [card["tag"] for card in stored_document["cards"]] == [TAG, None]


def test_a_version_2_document_may_not_say_no_tag_as_an_empty_string() -> None:
    """The one thing version 2 promises a reader that version 1 did not."""
    record = record_of(two_cards_under_one_tag())
    cards = record.document["cards"]
    assert isinstance(cards, list)
    with_an_empty_tag = [{**card, "tag": card["tag"] or ""} for card in cards if isinstance(card, dict)]

    with pytest.raises(ValidationError, match="version 2"):
        DocumentRecord.model_validate(
            record.model_dump(mode="json") | {"document": {**record.document, "cards": with_an_empty_tag}}
        )


def test_a_version_this_build_does_not_know_is_refused() -> None:
    record = record_of(two_cards_under_one_tag())

    with pytest.raises(ValidationError):
        DocumentRecord.model_validate(record.model_dump(mode="json") | {"schema_version": 3})


# ------------------------------------------------------------------------------------------------
# A reader takes both
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_store_reads_every_file_a_version_1_build_wrote() -> None:
    store = LocalParsedStore(STORED)

    assert await store.version_directories(CASELIST) == (FIRST_VERSION,)
    entries = await store.read_entries(CASELIST, FIRST_VERSION)
    assert [(entry.schema_version, entry.outcome) for entry in entries] == [
        (1, SourceOutcome.PARSED),
        (1, SourceOutcome.PARSED),
        (1, SourceOutcome.FAILED),
    ]
    assert await store.read_index(CASELIST, FIRST_VERSION) == entries
    failures = await store.read_failures(CASELIST, FIRST_VERSION)
    assert failures is not None
    assert [(entry.source_sha256, entry.reason) for entry in failures] == [(FAILED, "MALFORMED_XML")]
    occurrences = await store.read_occurrences(CASELIST, FIRST_VERSION)
    assert occurrences is not None
    assert [(row.schema_version, row.source_sha256, row.completeness) for row in occurrences] == [
        (1, TWO_CARDS, CardCompleteness.FULL)
    ]
    assert await store.read_document(CASELIST, FIRST_VERSION, FAILED) is None


@pytest.mark.anyio
async def test_a_version_1_document_reads_back_with_its_empty_tag_as_no_tag() -> None:
    record = await LocalParsedStore(STORED).read_document(CASELIST, FIRST_VERSION, TWO_CARDS)

    assert record is not None
    assert record.schema_version == 1
    document = record.to_parsed_document(PATH)
    assert document.parser_version == FIRST_VERSION
    assert [(card.tag, card.has_tag) for card in document.cards] == [(TAG, True), ("", False)]
    assert [card.short_cite for card in document.cards] == ["Okonkwo 26", "Ferreira 25"]


@pytest.mark.anyio
async def test_a_version_1_record_stays_version_1_when_it_is_carried(tmp_path: Path) -> None:
    """An aggregate is rebuilt from the per-source entries. An old entry is not re-stamped on the way."""
    copy = tmp_path / "copy"
    shutil.copytree(STORED, copy)
    store = LocalParsedStore(copy)
    entries = await store.read_entries(CASELIST, FIRST_VERSION)

    await store.write_aggregates(CASELIST, FIRST_VERSION, index=entries, failures=[], occurrences=[])

    rewritten = (store.root / CASELIST / FIRST_VERSION / "index.jsonl").read_text(encoding="utf-8")
    assert rewritten == (STORED / "parsed" / CASELIST / FIRST_VERSION / "index.jsonl").read_text(
        encoding="utf-8"
    )


@pytest.mark.anyio
async def test_the_same_file_read_by_both_builds_differs_only_where_the_reading_changed() -> None:
    """Version 1 and the running build agree on this file's cards. Only the record's shape moved."""
    old = await LocalParsedStore(STORED).read_document(CASELIST, FIRST_VERSION, TWO_CARDS)
    assert old is not None
    new = record_of(two_cards_under_one_tag())

    assert (old.schema_version, new.schema_version) == (1, 2)
    then, now = old.to_parsed_document(PATH), new.to_parsed_document(PATH)
    assert [(c.tag, c.full_cite, c.evidence_text, c.completeness) for c in then.cards] == [
        (c.tag, c.full_cite, c.evidence_text, c.completeness) for c in now.cards
    ]
    assert (STORED / "parsed" / source_object_key(CASELIST, FIRST_VERSION, TWO_CARDS)).is_file()

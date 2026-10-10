"""The parsed card store's local JSONL adapter, and the in-memory fake held to the same contract.

What the layout promises (`docs/data/parsed-card-store.md`, task spec ac2) is checked on the bytes
the adapter writes: one file per source at a digest-named key, every line carrying the six fields
that say what produced it, and no disclosure path anywhere. The refusals are the task spec's
forbidden overwrite of an earlier parser version, held by the adapter itself.

The documents are real: a structural fixture read by the real parser, so a stored document is
exactly what the pipeline will store.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.ports.parsed_store import (
    AGGREGATE_NAMES,
    DocumentRecord,
    OccurrenceRecord,
    ParsedStore,
    ParsedStoreRefusal,
    PipelineFailureReason,
    SourceEntry,
    SourceOutcome,
    StoreRecord,
    parse_version_directory,
    skip_key,
    source_object_key,
    version_directory_name,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument, ParseFailureReason
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore, UnreadableParsedStore
from debate_core.testing.fakes import InMemoryParsedStore

FIXTURE: Final = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "debate_files"
    / "structural"
    / "team-verbatim-file.docx"
)
PARSER: Final = "2026.09.20-docx-1"
PROFILE: Final = "2026.09.20-verbatim-1"
FINGERPRINTS: Final = "card-fingerprint-v1"
#: A fictional disclosure path, in the shape a real one has: it names a school and a team code.
PATH: Final = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
SIX_FIELDS: Final = (
    "caselist",
    "snapshot",
    "source_sha256",
    "parser_version",
    "profile_version",
    "fingerprint_version",
)

STORES: Final[dict[str, Callable[[Path], ParsedStore]]] = {
    "local": LocalParsedStore,
    "in-memory": lambda _: InMemoryParsedStore(),
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def parsed() -> ParsedDocument:
    content = FIXTURE.read_bytes()
    source = SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="testcl26",
        first_seen_snapshot=date(2026, 9, 1),
        last_seen_snapshot=date(2026, 9, 1),
    )
    document = DebateDocxParser().parse(content, source, source_path=PATH)
    assert isinstance(document, ParsedDocument)
    assert document.cards
    return document


def _entry(
    sha256: str, *, cards: int = 0, outcome: SourceOutcome = SourceOutcome.PARSED, **extra: object
) -> SourceEntry:
    fields: dict[str, object] = {
        "caselist": "testcl26",
        "snapshot": "2026-09-01",
        "source_sha256": sha256,
        "parser_version": PARSER,
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINTS,
        "source_format": SourceFormat.DOCX,
        "byte_size": 100,
        **extra,
    }
    if outcome is SourceOutcome.PARSED:
        return SourceEntry.model_validate({**fields, "outcome": outcome, "cards": cards})
    reason = str(fields.pop("reason"))
    return SourceEntry.for_failure(reason=reason, detail="", **fields)


def _document(parsed: ParsedDocument) -> DocumentRecord:
    return DocumentRecord.from_parsed_document(
        parsed, caselist="testcl26", snapshot="2026-09-01", fingerprint_version=FINGERPRINTS, camp=None
    )


def _occurrence(
    sha256: str,
    *,
    caselist: str = "testcl26",
    snapshot: str = "2026-09-08",
    last_snapshot: str = "2026-09-15",
) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=caselist,
        snapshot=snapshot,
        last_snapshot=last_snapshot,
        source_sha256=sha256,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=FINGERPRINTS,
        disclosure="d" * 64,
        first_element_index=3,
        last_element_index=5,
        exact_fingerprint="e" * 64,
        cluster_id="c" * 64,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


# ------------------------------------------------------------------------------------------------
# The contract both stores keep
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_a_source_reads_back_as_written_and_its_document_gets_its_path_back(
    kind: str, tmp_path: Path, parsed: ParsedDocument
) -> None:
    store = STORES[kind](tmp_path)
    entry = _entry(parsed.source_sha256, cards=len(parsed.cards))
    await store.write_source("testcl26", PARSER, entry, _document(parsed))

    assert await store.read_entries("testcl26", PARSER) == (entry,)
    record = await store.read_document("testcl26", PARSER, parsed.source_sha256)
    assert record is not None
    assert record.card_count == len(parsed.cards)
    assert record.to_parsed_document(PATH) == parsed.model_copy(update={"sections": ()})


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_entries_are_listed_by_digest_and_filtered_by_snapshot(kind: str, tmp_path: Path) -> None:
    store = STORES[kind](tmp_path)
    late = _entry(
        "b" * 64, outcome=SourceOutcome.UNSUPPORTED, reason="UNSUPPORTED_FORMAT", snapshot="2026-09-08"
    )
    early = _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="MALFORMED_XML")
    for entry in (late, early):
        await store.write_source("testcl26", PARSER, entry, None)

    assert await store.read_entries("testcl26", PARSER) == (early, late)
    assert await store.read_entries("testcl26", PARSER, snapshot="2026-09-08") == (late,)
    assert await store.read_document("testcl26", PARSER, "a" * 64) is None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_aggregates_are_absent_until_written_and_then_read_back(kind: str, tmp_path: Path) -> None:
    store = STORES[kind](tmp_path)
    assert await store.read_index("testcl26", PARSER) is None
    assert await store.read_failures("testcl26", PARSER) is None
    assert await store.read_occurrences("testcl26", PARSER) is None

    failed = _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE")
    await store.write_source("testcl26", PARSER, failed, None)
    await store.write_aggregates(
        "testcl26", PARSER, index=[failed], failures=[failed], occurrences=[_occurrence("a" * 64)]
    )

    assert await store.read_index("testcl26", PARSER) == (failed,)
    assert await store.read_failures("testcl26", PARSER) == (failed,)
    assert await store.read_occurrences("testcl26", PARSER) == (_occurrence("a" * 64),)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_an_earlier_generation_is_never_written_to_again(kind: str, tmp_path: Path) -> None:
    """The task spec's forbidden overwrite: a re-parse writes a new version, the old one is left."""
    store = STORES[kind](tmp_path)
    await store.write_source(
        "testcl26", PARSER, _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE"), None
    )
    newer = version_directory_name(PARSER, 2)
    await store.write_source(
        "testcl26", newer, _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE"), None
    )

    with pytest.raises(ParsedStoreRefusal, match="earlier generation|not the newest"):
        await store.write_source(
            "testcl26", PARSER, _entry("b" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE"), None
        )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_an_entry_is_never_filed_under_another_parser_version(kind: str, tmp_path: Path) -> None:
    store = STORES[kind](tmp_path)
    with pytest.raises(ParsedStoreRefusal):
        await store.write_source(
            "testcl26",
            "2026.01.01-docx-0",
            _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE"),
            None,
        )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", STORES)
async def test_a_recorded_source_is_not_replaced_unless_the_next_run_retries_it(
    kind: str, tmp_path: Path
) -> None:
    store = STORES[kind](tmp_path)
    missing = _entry("a" * 64, outcome=SourceOutcome.FAILED, reason=str(PipelineFailureReason.SOURCE_MISSING))
    await store.write_source("testcl26", PARSER, missing, None)
    retried = _entry("a" * 64, outcome=SourceOutcome.FAILED, reason="TOO_LARGE")
    await store.write_source("testcl26", PARSER, retried, None)
    assert await store.read_entries("testcl26", PARSER) == (retried,)

    with pytest.raises(ParsedStoreRefusal, match="already recorded"):
        await store.write_source("testcl26", PARSER, retried, None)


# ------------------------------------------------------------------------------------------------
# The bytes the local adapter writes
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_parsed_source_is_one_digest_named_file_of_two_lines(
    tmp_path: Path, parsed: ParsedDocument
) -> None:
    store = LocalParsedStore(tmp_path)
    sha = parsed.source_sha256
    await store.write_source("testcl26", PARSER, _entry(sha, cards=len(parsed.cards)), _document(parsed))

    path = tmp_path / "parsed" / "testcl26" / PARSER / "sha256" / sha[0:2] / sha[2:4] / f"{sha}.jsonl"
    assert path == store.root / source_object_key("testcl26", PARSER, sha)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["record"] for line in lines] == ["source", "document"]


@pytest.mark.anyio
async def test_every_record_in_every_file_carries_the_six_fields(
    tmp_path: Path, parsed: ParsedDocument
) -> None:
    """ac2: caselist, snapshot, source sha256, parser, profile and fingerprint versions, on every line."""
    store = LocalParsedStore(tmp_path)
    entry = _entry(parsed.source_sha256, cards=len(parsed.cards))
    failed = _entry(
        "a" * 64,
        outcome=SourceOutcome.UNSUPPORTED,
        reason="UNSUPPORTED_FORMAT",
        source_format=SourceFormat.PDF,
    )
    await store.write_source("testcl26", PARSER, entry, _document(parsed))
    await store.write_source("testcl26", PARSER, failed, None)
    await store.write_aggregates(
        "testcl26",
        PARSER,
        index=[failed, entry],
        failures=[failed],
        occurrences=[_occurrence(parsed.source_sha256)],
    )

    files = sorted(path for path in store.root.rglob("*.jsonl"))
    assert {path.name for path in files} >= set(AGGREGATE_NAMES)
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            assert {name: record[name] for name in SIX_FIELDS} == {
                "caselist": "testcl26",
                "snapshot": record["snapshot"],
                "source_sha256": record["source_sha256"],
                "parser_version": PARSER,
                "profile_version": PROFILE,
                "fingerprint_version": FINGERPRINTS,
            }
            assert record["snapshot"] in {"2026-09-01", "2026-09-08"}


@pytest.mark.anyio
async def test_no_file_names_the_disclosure_path_or_anything_in_it(
    tmp_path: Path, parsed: ParsedDocument
) -> None:
    """The bucket's parsed/ prefix may hold no personal data, so neither may anything copied to it."""
    store = LocalParsedStore(tmp_path)
    await store.write_source(
        "testcl26", PARSER, _entry(parsed.source_sha256, cards=len(parsed.cards)), _document(parsed)
    )
    await store.write_aggregates("testcl26", PARSER, index=[], failures=[], occurrences=[])

    written = "".join(path.read_text(encoding="utf-8") for path in store.root.rglob("*.jsonl"))
    for fragment in ("Maple Grove", "QX", "Grove City", "source_path"):
        assert fragment not in written


@pytest.mark.anyio
async def test_the_same_records_always_write_the_same_bytes(tmp_path: Path, parsed: ParsedDocument) -> None:
    """What lets a re-publish compare checksums and upload nothing."""
    first, second = LocalParsedStore(tmp_path / "one"), LocalParsedStore(tmp_path / "two")
    for store in (first, second):
        await store.write_source(
            "testcl26", PARSER, _entry(parsed.source_sha256, cards=len(parsed.cards)), _document(parsed)
        )
        await store.write_aggregates(
            "testcl26", PARSER, index=[], failures=[], occurrences=[_occurrence("a" * 64)]
        )

    def tree(store: LocalParsedStore) -> dict[str, bytes]:
        return {
            path.relative_to(store.root).as_posix(): path.read_bytes()
            for path in store.root.rglob("*")
            if path.is_file()
        }

    assert tree(first) == tree(second)


@pytest.mark.anyio
async def test_an_unreadable_line_names_the_file_and_line_and_never_its_content(tmp_path: Path) -> None:
    store = LocalParsedStore(tmp_path)
    await store.write_aggregates("testcl26", PARSER, index=[], failures=[], occurrences=[])
    (store.root / "testcl26" / PARSER / "index.jsonl").write_text(
        '{"tag": "Maple Grove QX secret"}\n', encoding="utf-8"
    )

    with pytest.raises(UnreadableParsedStore) as raised:
        await store.read_index("testcl26", PARSER)
    assert raised.value.file == f"testcl26/{PARSER}/index.jsonl"
    assert raised.value.line == 1
    assert "Maple Grove" not in str(raised.value)


@pytest.mark.anyio
async def test_version_directories_sort_by_parser_version_then_generation(tmp_path: Path) -> None:
    store = LocalParsedStore(tmp_path)
    for generation in (10, 1, 2):
        (store.root / "testcl26" / version_directory_name(PARSER, generation)).mkdir(parents=True)
    assert await store.version_directories("testcl26") == (
        PARSER,
        f"{PARSER}_reparse-2",
        f"{PARSER}_reparse-10",
    )


# ------------------------------------------------------------------------------------------------
# The records
# ------------------------------------------------------------------------------------------------


def test_a_version_directory_name_round_trips() -> None:
    assert parse_version_directory(version_directory_name(PARSER)) == (PARSER, 1)
    assert parse_version_directory(version_directory_name(PARSER, 3)) == (PARSER, 3)


def test_the_skip_key_is_the_digest_and_both_versions() -> None:
    entry = _entry("a" * 64, cards=1)
    assert entry.skip_key == ("a" * 64, PARSER, PROFILE)
    assert entry.skip_key != skip_key("a" * 64, PARSER, "2026.10.01-verbatim-2")


def test_an_unsupported_format_is_an_outcome_and_everything_else_a_failure() -> None:
    assert (
        _entry(
            "a" * 64, outcome=SourceOutcome.UNSUPPORTED, reason=str(ParseFailureReason.UNSUPPORTED_FORMAT)
        ).outcome
        is SourceOutcome.UNSUPPORTED
    )
    for reason in ("MACRO_ENABLED", "TOO_LARGE", "MALFORMED_XML", "TIMEOUT", "WORKER_CRASHED"):
        assert _entry("a" * 64, outcome=SourceOutcome.FAILED, reason=reason).outcome is SourceOutcome.FAILED


@pytest.mark.parametrize(
    ("caselist", "snapshot"),
    [
        ("testcl26", "2026-9-1"),
        ("testcl26", "2026-policy"),
        ("openev", "2026-09-01x!"),
        ("Maple Grove", "2026-09-01"),
    ],
)
def test_a_record_refuses_a_name_outside_the_layout(caselist: str, snapshot: str) -> None:
    with pytest.raises(ValueError, match="snapshot|caselist"):
        _entry("a" * 64, cards=1, caselist=caselist, snapshot=snapshot)


@pytest.mark.parametrize(
    ("caselist", "snapshot", "last_snapshot", "message"),
    [
        ("testcl26", "2026-09-08", "2026-09-01", "before snapshot"),
        ("testcl26", "2026-09-08", "2026-9-15", "YYYY-MM-DD"),
        ("openev", "2026-policy", "2027-policy", "one release"),
    ],
)
def test_an_occurrence_spans_its_first_to_its_latest_snapshot(
    caselist: str, snapshot: str, last_snapshot: str, message: str
) -> None:
    assert _occurrence("a" * 64).last_snapshot == "2026-09-15"
    with pytest.raises(ValueError, match=message):
        _occurrence("a" * 64, caselist=caselist, snapshot=snapshot, last_snapshot=last_snapshot)


@pytest.mark.parametrize("record", [SourceEntry, DocumentRecord, OccurrenceRecord])
def test_no_record_has_a_field_for_a_path_school_team_tournament_or_round(record: type[StoreRecord]) -> None:
    """The store never gains a field naming who disclosed what; `docs/data/parsed-card-store.md`."""
    named = {
        name
        for name in record.model_fields
        for word in ("path", "school", "team", "tournament", "round", "debater")
        if word in name
    }
    assert named == set()


def test_a_stored_document_refuses_to_carry_its_path(parsed: ParsedDocument) -> None:
    stored = _document(parsed).document
    with pytest.raises(ValueError, match="neither its path"):
        DocumentRecord(
            caselist="testcl26",
            snapshot="2026-09-01",
            source_sha256=parsed.source_sha256,
            parser_version=PARSER,
            profile_version=PROFILE,
            fingerprint_version=FINGERPRINTS,
            document={**stored, "source_path": PATH},
        )

"""VerifyManifest: every card of a manifest, verified against the snapshots the verifier can reach.

The manifests are the committed fixtures in `tests/fixtures/verify/`, verified here against the same
scenario held in memory. Every expected verdict, offset and detail below is written by hand from
the fixture text (`tests/fixtures/verify/manifest_world.py`):

    "Wells across the invented Marrow basin ran dry in 2031."   first sentence, 0-55
    "\\n\\n"                                                       56-57
    "Nobody in the basin had planned for it."                    second paragraph, 57-96

The tampered card changes "had" to "has": in the 39-character paragraph, "Nobody in the basin " is 20
characters, so the "d" is at offset 22, U+0064 in the snapshot and U+0073 ("s") on the card.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.verification.verification_world import run
from tests.fixtures.verify.manifest_world import (
    ALL_VERIFIED,
    MIXED,
    TAMPERED,
    ManifestWorld,
    build_fixture_manifests,
)
from tests.fixtures.verify.published_schemas import RESULT_SCHEMA, committed_schema, violations

from debate_core.application.errors import (
    DomainError,
    StoreCredentialsExpired,
    StoreError,
    StoreUnavailable,
)
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.verify_manifest import (
    InvalidManifest,
    ManifestVerificationReport,
    VerificationCouldNotRun,
    VerifyManifest,
    render_verify_result_schema,
)
from debate_core.domain import Card, SourceSnapshot, VerificationStatus
from debate_core.evidence.verification_types import ReasonCode, VerificationCheck, VerificationResult
from debate_core.testing import InMemoryArticleRepository, InMemorySnapshotStore

VERIFIED = VerificationStatus.VERIFIED
UNVERIFIED = VerificationStatus.UNVERIFIED
EVERY_CHECK = tuple(VerificationCheck)
WELLS_SNAPSHOT = "0SNAP000000000000000000001"
VERIFIER_VERSION = "evidence-verifier-v2"


@pytest.fixture
def world() -> ManifestWorld:
    """The scenario in memory: the WELLS snapshot stored, the FENN one nowhere."""
    world = ManifestWorld.in_memory()
    build_fixture_manifests(world)
    return world


def verdict(
    position: int,
    card_id: str,
    tag: str,
    *,
    status: VerificationStatus = VERIFIED,
    reasons: tuple[tuple[ReasonCode, str, int | None], ...] = (),
    snapshot_id: str | None = WELLS_SNAPSHOT,
    checks_run: tuple[VerificationCheck, ...] = EVERY_CHECK,
    verifier_version: str | None = VERIFIER_VERSION,
) -> dict[str, Any]:
    """One expected row of the report, in the JSON form the report serializes to."""
    return {
        "position": position,
        "card_id": card_id,
        "tag": tag,
        "status": status.value,
        "reasons": [
            {"code": code.value, "detail": detail, "first_differing_offset": offset}
            for code, detail, offset in reasons
        ],
        "snapshot_id": snapshot_id,
        "checks_run": [check.value for check in checks_run],
        "verifier_version": verifier_version,
        "reason_codes": list(dict.fromkeys(code.value for code, _, _ in reasons)),
    }


SENTENCE = verdict(0, "0CARD000000000000000000001", "Marrow basin wells ran dry in 2031")
WITH_CUT = verdict(1, "0CARD000000000000000000002", "Wells ran dry in 2031, with where cut out")
PLANNED = verdict(2, "0CARD000000000000000000003", "Nobody in the basin planned for it")
TAMPERED_PLANNED = verdict(
    2,
    "0CARD000000000000000000003",
    "Nobody in the basin planned for it",
    status=UNVERIFIED,
    reasons=(
        (
            ReasonCode.TEXT_MISMATCH,
            "evidence_text has U+0073 at offset 22 where the snapshot has U+0064; "
            "evidence_text is 39 characters, the snapshot's evidence 39",
            22,
        ),
    ),
)
OVERLONG = verdict(
    3,
    "0CARD000000000000000000004",
    "A card whose text no longer fits its envelope",
    status=UNVERIFIED,
    reasons=(
        (
            ReasonCode.CARD_INVALID,
            "not a valid card at $.cards[3]: Value error, the envelope 0-55 minus 0 omission(s) quotes "
            "55 characters, but evidence_text has 65; it was not checked against its snapshot",
            None,
        ),
    ),
    checks_run=(),
    verifier_version=None,
)
FENN_MISSING = verdict(
    4,
    "0AWAYCARD00000000000000001",
    "Fenn valley reservoirs held water",
    status=UNVERIFIED,
    reasons=((ReasonCode.SNAPSHOT_MISSING, "SourceSnapshot not found: 0AWAYSNAP00000000000000001", None),),
    snapshot_id="0AWAYSNAP00000000000000001",
    checks_run=(
        VerificationCheck.CARD_COMPLETE,
        VerificationCheck.NORMALIZER_VERSION_KNOWN,
        VerificationCheck.CITATION_VERIFIED,
        VerificationCheck.SNAPSHOT_INTEGRITY,
    ),
)


def rows(report: ManifestVerificationReport) -> list[dict[str, Any]]:
    return report.model_dump(mode="json")["cards"]


def test_the_committed_manifests_are_what_the_scenario_builds() -> None:
    """If this fails, run `uv run python -m tests.fixtures.verify.manifest_world` and review the diff."""
    built = build_fixture_manifests(ManifestWorld.in_memory())

    assert ALL_VERIFIED.read_bytes() == built.all_verified
    assert TAMPERED.read_bytes() == built.tampered
    assert MIXED.read_bytes() == built.mixed


def test_every_card_of_the_all_verified_manifest_is_verified(world: ManifestWorld) -> None:
    report = world.verify(ALL_VERIFIED.read_bytes())

    assert rows(report) == [SENTENCE, WITH_CUT, PLANNED]
    assert (report.total, report.verified, report.unverified, report.all_verified) == (3, 3, 0, True)
    assert report.manifest_version == 1
    assert report.generated_at.isoformat() == "2026-10-01T12:00:00+00:00"


def test_one_tampered_card_is_a_text_mismatch_and_the_other_two_still_verify(world: ManifestWorld) -> None:
    report = world.verify(TAMPERED.read_bytes())

    assert rows(report) == [SENTENCE, WITH_CUT, TAMPERED_PLANNED]
    assert (report.total, report.verified, report.unverified, report.all_verified) == (3, 2, 1, False)


def test_the_mixed_manifest_gives_every_card_its_own_verdict(world: ManifestWorld) -> None:
    report = world.verify(MIXED.read_bytes())

    assert rows(report) == [SENTENCE, WITH_CUT, TAMPERED_PLANNED, OVERLONG, FENN_MISSING]
    assert (report.total, report.verified, report.unverified, report.all_verified) == (5, 2, 3, False)


def test_a_card_whose_snapshot_is_not_here_is_unverified_never_skipped(world: ManifestWorld) -> None:
    only_fenn = manifest_with(MIXED, cards=lambda cards: [cards[4]])

    report = world.verify(only_fenn)

    assert rows(report) == [{**FENN_MISSING, "position": 0}]
    assert report.all_verified is False


def test_an_invalid_card_does_not_stop_the_cards_after_it_being_verified(world: ManifestWorld) -> None:
    invalid_first = manifest_with(MIXED, cards=lambda cards: [cards[3], cards[0]])
    verifier = CountingVerifier(world)

    report = run(VerifyManifest(verifier=verifier).verify(invalid_first))

    assert rows(report) == [
        {**OVERLONG, "position": 0, "reasons": [reason_at(OVERLONG, 0)]},
        {**SENTENCE, "position": 1},
    ]
    assert verifier.verified == ["0CARD000000000000000000001"], "only the valid card reaches the verifier"


def test_a_card_invalid_detail_never_quotes_the_cards_text(world: ManifestWorld) -> None:
    """Evidence text that would be easy to spot if it leaked into a reason or anywhere in the report."""
    marker = "QUOTED-EVIDENCE-MUST-NOT-APPEAR"

    def broken(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**cards[0], "evidence_text": marker, "spans": []}]

    report = world.verify(manifest_with(MIXED, cards=broken))

    (only,) = report.cards
    assert only.status is UNVERIFIED
    assert [reason.code for reason in only.reasons] == [ReasonCode.CARD_INVALID]
    assert only.reasons[0].detail == (
        "not a valid card at $.cards[0]: Value error, the envelope 0-55 minus 0 omission(s) quotes 55 "
        "characters, but evidence_text has 31; it was not checked against its snapshot"
    )
    assert marker not in report.model_dump_json()


# --------------------------------------------------------------------------------------------
# A document that is not a manifest
# --------------------------------------------------------------------------------------------

SECRET = "SECRET-EVIDENCE-TEXT"


def edit(path: str, value: object) -> Callable[[dict[str, Any]], None]:
    """Set ``value`` at a dotted path of the all-verified manifest, ``cards.0.spans.0.style`` style."""

    def apply(document: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = document
        for part in parents:
            target = target[int(part)] if part.isdigit() else target[part]
        if value is DELETE:
            del target[int(last) if last.isdigit() else last]
        else:
            target[int(last) if last.isdigit() else last] = value

    return apply


DELETE = object()


@pytest.mark.parametrize(
    ("change", "json_path", "problem"),
    [
        (edit("manifest_version", 2), "$.manifest_version", "must be 1"),
        (edit("generated_at", DELETE), "$", "missing required 'generated_at'"),
        (edit("notes", SECRET), "$", "properties the schema does not allow: 'notes'"),
        (edit("cards", []), "$.cards", "must have at least 1 item(s)"),
        (edit("cards.1.card_id", DELETE), "$.cards[1]", "missing required 'card_id'"),
        (edit("cards.0", SECRET), "$.cards[0]", "must be of type object"),
        (edit("cards.0.evidence_start_offset", -1), "$.cards[0].evidence_start_offset", "must be at least 0"),
        (
            edit("cards.0.evidence_start_offset", SECRET),
            "$.cards[0].evidence_start_offset",
            "matches none of the allowed forms: integer, or null",
        ),
        (edit("cards.2.evidence_text", 7), "$.cards[2].evidence_text", "must be of type string"),
        (
            edit("cards.0.spans.0.style", SECRET),
            "$.cards[0].spans[0].style",
            'must be one of "underline", "highlight"',
        ),
        (edit("cards.0.secret", SECRET), "$.cards[0]", "properties the schema does not allow: 'secret'"),
    ],
    ids=lambda value: value if isinstance(value, str) and value.startswith("$") else None,
)
def test_a_manifest_that_fails_the_schema_names_the_failing_path_and_verifies_nothing(
    world: ManifestWorld, change: Callable[[dict[str, Any]], None], json_path: str, problem: str
) -> None:
    document = json.loads(ALL_VERIFIED.read_bytes())
    change(document)
    verifier = CountingVerifier(world)

    with pytest.raises(InvalidManifest) as refused:
        run(VerifyManifest(verifier=verifier).verify(json.dumps(document).encode()))

    assert (refused.value.json_path, refused.value.problem, refused.value.violations) == (
        json_path,
        problem,
        1,
    )
    assert str(refused.value) == f"the manifest is invalid at {json_path}: {problem}"
    assert SECRET not in str(refused.value)
    assert verifier.verified == []


@pytest.mark.parametrize(
    ("document", "problem"),
    [
        (b"{", "not JSON: Expecting property name enclosed in double quotes at line 1 column 2"),
        (b"", "not JSON: Expecting value at line 1 column 1"),
        (b"\x80\x81", "not JSON: the document is not Unicode text"),
        (
            b'{"manifest_version": 1, "manifest_version": 1}',
            "not strict JSON: an object names the key 'manifest_version' twice",
        ),
        (b'{"manifest_version": NaN}', "not strict JSON: NaN is not a JSON number"),
        (b"[]", "must be of type object"),
    ],
)
def test_a_document_that_is_not_strict_json_is_refused_at_its_root(
    world: ManifestWorld, document: bytes, problem: str
) -> None:
    with pytest.raises(InvalidManifest) as refused:
        world.verify(document)

    assert (refused.value.json_path, refused.value.problem) == ("$", problem)


def test_a_duplicated_key_inside_a_card_is_refused_before_any_card_is_read(world: ManifestWorld) -> None:
    """A viewer of the file could be shown the other value than the one that was verified."""
    text = ALL_VERIFIED.read_text(encoding="utf-8")
    duplicated = text.replace(
        '"evidence_text": "Nobody', '"evidence_text": "Somebody", "evidence_text": "Nobody', 1
    )
    assert duplicated != text

    with pytest.raises(InvalidManifest) as refused:
        world.verify(duplicated.encode())

    assert refused.value.problem == "not strict JSON: an object names the key 'evidence_text' twice"


@pytest.mark.parametrize(
    ("generated_at", "problem"),
    [
        ("2026-10-01T12:00:00", "Input should have timezone info"),
        ("yesterday", "Input should be a valid datetime"),
    ],
)
def test_a_timestamp_that_is_not_an_aware_date_time_is_refused(
    world: ManifestWorld, generated_at: str, problem: str
) -> None:
    """JSON Schema only annotates `format: date-time`; the reader checks it."""
    document = json.loads(ALL_VERIFIED.read_bytes())
    document["generated_at"] = generated_at

    with pytest.raises(InvalidManifest) as refused:
        world.verify(json.dumps(document).encode())

    assert refused.value.json_path == "$.generated_at"
    assert refused.value.problem.startswith(problem), "pydantic's own words after the prefix"


def test_every_violation_is_counted_and_the_most_relevant_is_named(world: ManifestWorld) -> None:
    document = json.loads(ALL_VERIFIED.read_bytes())
    document["manifest_version"] = 2
    document["cards"][1]["evidence_end_offset"] = 0

    with pytest.raises(InvalidManifest) as refused:
        world.verify(json.dumps(document).encode())

    assert refused.value.violations == 2
    assert (
        str(refused.value) == "the manifest is invalid at $.manifest_version: must be 1 (1 more violation(s))"
    )


# --------------------------------------------------------------------------------------------
# Verification that could not run
# --------------------------------------------------------------------------------------------


class UnreachableBlobs(InMemorySnapshotStore):
    """An in-memory blob store that stops answering when told to."""

    def __init__(self) -> None:
        super().__init__()
        self.failure: StoreError | None = None

    async def get(self, key: str) -> bytes:
        if self.failure is not None:
            raise self.failure
        return await super().get(key)


@pytest.mark.parametrize(
    ("failure", "hint"),
    [
        (StoreUnavailable("GetObject", "blobs/sha256", "connection refused"), None),
        (
            StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence"),
            "aws sso login --profile debate-dev-evidence",
        ),
    ],
)
def test_a_store_that_cannot_be_reached_stops_the_run_instead_of_giving_a_verdict(
    failure: StoreError, hint: str | None
) -> None:
    blobs = UnreachableBlobs()
    world = ManifestWorld(blobs=blobs, articles=InMemoryArticleRepository())
    build_fixture_manifests(world)
    blobs.failure = failure

    with pytest.raises(VerificationCouldNotRun) as stopped:
        world.verify(ALL_VERIFIED.read_bytes())

    assert (stopped.value.card_id, stopped.value.position, stopped.value.cause) == (
        "0CARD000000000000000000001",
        0,
        failure,
    )
    assert stopped.value.hint == hint
    assert stopped.value.__cause__ is failure
    assert not isinstance(stopped.value, DomainError), "a DomainError the CLI does not handle exits 1"


class UnreadableRecords(InMemoryArticleRepository):
    """A repository whose snapshot records cannot be read, for a reason that is not 'not found'."""

    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self.failure = failure
        self.reading = False

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        if self.reading:
            raise self.failure
        return await super().get_snapshot(snapshot_id)


class RecordUnreadable(DomainError):
    """Stands in for an adapter's own DomainError, such as SQLite's CorruptRecordError."""


def test_any_domain_error_the_verifier_lets_through_stops_the_run() -> None:
    articles = UnreadableRecords(RecordUnreadable("row 7 is not a SourceSnapshot"))
    world = ManifestWorld(blobs=InMemorySnapshotStore(), articles=articles)
    build_fixture_manifests(world)
    articles.reading = True

    with pytest.raises(VerificationCouldNotRun) as stopped:
        world.verify(MIXED.read_bytes())

    assert isinstance(stopped.value.cause, RecordUnreadable)
    assert str(stopped.value) == (
        "verification could not run: cards[0] (0CARD000000000000000000001) could not be checked against "
        "its snapshot: row 7 is not a SourceSnapshot"
    )


def test_a_bug_is_not_dressed_up_as_a_failure_to_run() -> None:
    articles = UnreadableRecords(RuntimeError("a bug in an adapter"))
    world = ManifestWorld(blobs=InMemorySnapshotStore(), articles=articles)
    build_fixture_manifests(world)
    articles.reading = True

    with pytest.raises(RuntimeError, match="a bug in an adapter"):
        world.verify(ALL_VERIFIED.read_bytes())


# --------------------------------------------------------------------------------------------
# The published result schema
# --------------------------------------------------------------------------------------------


def test_the_committed_result_schema_matches_the_report_model() -> None:
    assert committed_schema(RESULT_SCHEMA) == render_verify_result_schema(), (
        "verify_result.v1.json is stale; run: uv run scripts/export_schemas.py"
    )


def test_a_report_fits_the_result_schema_in_either_envelope(world: ManifestWorld) -> None:
    verified = world.verify(ALL_VERIFIED.read_bytes()).model_dump(mode="json")
    mixed = world.verify(MIXED.read_bytes()).model_dump(mode="json")

    ok = {"schema_version": 1, "status": "ok", "command": "verify", "data": verified, "error": None}
    failed: dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "command": "verify",
        "data": None,
        "error": {"code": "UNVERIFIED", "message": "m", "exit_code": 1, "details": mixed, "hint": None},
    }
    assert violations(RESULT_SCHEMA, ok) == []
    assert violations(RESULT_SCHEMA, failed) == []
    # And the schema has teeth: a report with a card missing its status fits neither outcome.
    del failed["error"]["details"]["cards"][2]["status"]
    assert violations(RESULT_SCHEMA, failed) == [("$", "oneOf")]


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


class CountingVerifier(EvidenceVerifier):
    """The world's verifier, recording which cards reached it."""

    def __init__(self, world: ManifestWorld) -> None:
        super().__init__(articles=world.articles, snapshots=world.snapshots, clock=world.clock)
        self.verified: list[str] = []

    async def verify(self, card: Card) -> VerificationResult:
        self.verified.append(card.card_id)
        return await super().verify(card)


def manifest_with(source: Path, *, cards: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> bytes:
    document = json.loads(source.read_bytes())
    document["cards"] = cards(document["cards"])
    return json.dumps(document).encode()


def reason_at(row: dict[str, Any], position: int) -> dict[str, Any]:
    """``row``'s first reason, its detail rewritten for the card's new ``position``."""
    reason = dict(row["reasons"][0])
    reason["detail"] = reason["detail"].replace(f"$.cards[{row['position']}]", f"$.cards[{position}]")
    return reason

"""`debate-research verify <manifest.json>`, through Typer's runner, the real app and composition root.

The manifests are the committed fixtures in `tests/fixtures/verify/`, and at the end the manifest
the JSON export writes (`v1-e06-t05`) for a card CardService cut. The data directory is the same
scenario written to disk with the real local adapters (SQLite and the filesystem blob store), so
the command reads snapshots exactly as it does on a student's laptop. The expected verdicts are
written by hand from the fixture text; see `tests/fixtures/verify/manifest_world.py` and the use
case's tests, which count the offsets.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import pytest
import typer
from tests.fixtures.card.card_world import CardWorld, news_request
from tests.fixtures.permissions import needs_permissions, refused
from tests.fixtures.verification.verification_world import run
from tests.fixtures.verify.manifest_world import (
    ALL_VERIFIED,
    MIXED,
    TAMPERED,
    ManifestWorld,
    build_fixture_data_dir,
    build_fixture_manifests,
)
from tests.fixtures.verify.published_schemas import RESULT_SCHEMA, committed_schema, violations
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands import verify as verify_command
from debate_cli.context import cli_context
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreError, StoreUnavailable
from debate_core.application.export_service import ExportService
from debate_core.domain import SourceSnapshot, VerificationStatus
from debate_core.integrations.local import (
    BLOB_DIRECTORY,
    FsSnapshotStore,
    SqliteArticleRepository,
    SqliteDatabase,
)
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySnapshotStore

runner = CliRunner()
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

SENTENCE_ID = "0CARD000000000000000000001"
WITH_CUT_ID = "0CARD000000000000000000002"
PLANNED_ID = "0CARD000000000000000000003"
OVERLONG_ID = "0CARD000000000000000000004"
FENN_ID = "0AWAYCARD00000000000000001"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The scenario's snapshots, written to a data directory by the real local adapters."""
    directory = tmp_path_factory.mktemp("verify") / "data"
    build_fixture_data_dir(directory)
    return directory


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> Iterator[None]:
    """The `test` environment, pointed at the fixture data directory and nothing else."""
    for name in list(__import__("os").environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))
    yield


def invoke(*arguments: str, app: typer.Typer | None = None) -> Result:
    return runner.invoke(app or create_app(), list(arguments))


def envelope(result: Result) -> dict[str, Any]:
    """The one JSON object a `--json` run prints, checked against the published result schema."""
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"--json must print exactly one line on stdout, got: {result.stdout!r}"
    document: dict[str, Any] = json.loads(lines[0])
    assert violations(RESULT_SCHEMA, document) == [], "the output does not fit verify_result.v1.json"
    return document


# --------------------------------------------------------------------------------------------
# ac4: the exit codes are documented where a user looks
# --------------------------------------------------------------------------------------------


def test_the_help_documents_every_exit_code() -> None:
    result = invoke("verify", "--help")

    assert result.exit_code == ExitCode.OK
    for line in (
        "0  every card is VERIFIED",
        "1  at least one card is UNVERIFIED (every card is still listed)",
        "2  usage error, or a manifest that fails its JSON Schema",
        "3  verification could not run, for example a store could not be read",
    ):
        assert line in result.stdout


def test_the_cli_readme_documents_every_exit_code() -> None:
    readme = (REPOSITORY_ROOT / "packages" / "debate_cli" / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## `debate-research verify`") :]

    for row in (
        "| `0` | Every card is VERIFIED. |",
        "| `1` | The manifest was read and at least one card is UNVERIFIED. Every card is still listed. |",
        "| `2` | A usage error, or a file that is not a card manifest: not JSON, or not valid against "
        "`card_manifest.v1.json`. The failing JSON path is reported and nothing is verified. |",
        "| `3` | Verification could not run, for example because a store could not be read. No card "
        "has a verdict. |",
    ):
        assert row in section


def test_the_result_schema_uses_the_clis_exit_codes() -> None:
    """The schema writes the numbers down because debate_core cannot import ExitCode."""
    outcomes = committed_schema(RESULT_SCHEMA)["oneOf"]
    codes = {
        outcome["title"]: outcome["properties"]["error"]
        .get("properties", {})
        .get("exit_code", {})
        .get("const")
        for outcome in outcomes
    }

    assert codes == {
        "Every card VERIFIED (exit 0)": None,
        "Some card UNVERIFIED (exit 1)": ExitCode.DOMAIN_FAILURE,
        "Not a manifest (exit 2)": ExitCode.USAGE_ERROR,
        "Usage error (exit 2)": ExitCode.USAGE_ERROR,
        "Verification could not run (exit 3)": ExitCode.RETRIEVAL_FAILURE,
    }


# --------------------------------------------------------------------------------------------
# Exit 0: every card verified
# --------------------------------------------------------------------------------------------


def test_a_manifest_whose_every_card_verifies_exits_zero_with_a_row_per_card() -> None:
    result = invoke("verify", str(ALL_VERIFIED))

    assert result.exit_code == ExitCode.OK, result.output
    assert "3 of 3 card(s) verified" in result.stdout
    for card_id in (SENTENCE_ID, WITH_CUT_ID, PLANNED_ID):
        assert card_id in result.stdout
    assert result.stdout.count("VERIFIED") == 3
    assert result.stderr == ""


def test_json_puts_the_report_under_data_when_every_card_verifies() -> None:
    result = invoke("--json", "verify", str(ALL_VERIFIED))

    assert result.exit_code == ExitCode.OK
    document = envelope(result)
    assert (document["status"], document["command"], document["error"]) == ("ok", "verify", None)
    report = document["data"]
    assert [(card["card_id"], card["status"], card["reason_codes"]) for card in report["cards"]] == [
        (SENTENCE_ID, "VERIFIED", []),
        (WITH_CUT_ID, "VERIFIED", []),
        (PLANNED_ID, "VERIFIED", []),
    ]
    assert (report["total"], report["verified"], report["unverified"]) == (3, 3, 0)


# --------------------------------------------------------------------------------------------
# Exit 1: some card unverified (ac2, ac3)
# --------------------------------------------------------------------------------------------


def test_two_verified_and_one_tampered_card_print_three_rows_with_reasons_and_exit_one() -> None:
    result = invoke("verify", str(TAMPERED))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    table = result.stdout
    assert "2 of 3 card(s) verified" in table
    rows = [line for line in table.splitlines() if line.startswith("│ 0CARD")]
    assert len(rows) == 3, table
    assert "VERIFIED" in rows[0] and "VERIFIED" in rows[1]
    assert "UNVERIFIED" in rows[2] and "TEXT_MISMATCH at" in rows[2]
    assert "offset 22" in table
    assert "UNVERIFIED" in result.stderr and "1 of 3 card(s) could not be verified" in result.stderr


def test_json_reports_every_card_of_the_mixed_manifest_with_its_status_and_reason_codes() -> None:
    result = invoke("--json", "verify", str(MIXED))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    document = envelope(result)
    assert (document["status"], document["data"]) == ("error", None)
    error = document["error"]
    assert (error["code"], error["exit_code"]) == ("UNVERIFIED", 1)
    assert error["message"] == "3 of 5 card(s) could not be verified against their snapshot"
    cards = error["details"]["cards"]
    assert [(card["card_id"], card["status"], card["reason_codes"]) for card in cards] == [
        (SENTENCE_ID, "VERIFIED", []),
        (WITH_CUT_ID, "VERIFIED", []),
        (PLANNED_ID, "UNVERIFIED", ["TEXT_MISMATCH"]),
        (OVERLONG_ID, "UNVERIFIED", ["CARD_INVALID"]),
        (FENN_ID, "UNVERIFIED", ["SNAPSHOT_MISSING"]),
    ]
    assert cards[2]["reasons"][0]["first_differing_offset"] == 22


def test_a_person_sees_a_row_for_every_card_of_the_mixed_manifest() -> None:
    """Including the two that never reached a snapshot comparison: invalid, and snapshot missing."""
    result = invoke("verify", str(MIXED))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    rows = [line for line in result.stdout.splitlines() if line.startswith(("│ 0CARD", "│ 0AWAY"))]
    assert len(rows) == 5, result.stdout
    assert ["UNVERIFIED" in row for row in rows] == [False, False, True, True, True]
    assert "CARD_INVALID" in rows[3]
    assert rows[4].startswith("│ 0AWAYCARD") and "SNAPSHOT_MISSING" in rows[4]


def test_the_output_never_contains_evidence_text() -> None:
    texts = [card["evidence_text"] for card in json.loads(MIXED.read_bytes())["cards"]]

    for arguments in (("--json", "verify", str(MIXED)), ("--verbose", "verify", str(MIXED))):
        result = invoke(*arguments)
        for text in texts:
            assert text not in result.stdout and text not in result.stderr


def test_verbose_gives_each_reasons_detail_on_stderr() -> None:
    result = invoke("--verbose", "verify", str(TAMPERED))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert (
        f"{PLANNED_ID} TEXT_MISMATCH: evidence_text has U+0073 at offset 22 where the snapshot has U+0064"
        in " ".join(result.stderr.split())
    )


# --------------------------------------------------------------------------------------------
# Exit 2: usage errors and documents that are not manifests (ac1)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "value", "json_path", "problem"),
    [
        (("manifest_version",), 0, "$.manifest_version", "must be one of 1, 2"),
        (("cards", 1, "card_id"), None, "$.cards[1]", "missing required 'card_id'"),
        (
            ("cards", 2, "spans", 0, "end_offset"),
            "forty",
            "$.cards[2].spans[0].end_offset",
            "must be of type integer",
        ),
    ],
)
def test_a_manifest_that_fails_its_schema_exits_two_with_the_failing_json_path(
    tmp_path: Path, path: tuple[str | int, ...], value: object, json_path: str, problem: str
) -> None:
    document = json.loads(ALL_VERIFIED.read_bytes())
    *parents, last = path
    target: Any = document
    for part in parents:
        target = target[part]
    if value is None:
        del target[last]
    else:
        target[last] = value
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    as_json = invoke("--json", "verify", str(manifest))
    for_a_person = invoke("verify", str(manifest))

    assert as_json.exit_code == for_a_person.exit_code == ExitCode.USAGE_ERROR
    error = envelope(as_json)["error"]
    assert (error["code"], error["details"]["json_path"], error["details"]["problem"]) == (
        "INVALID_MANIFEST",
        json_path,
        problem,
    )
    assert error["details"]["manifest"] == str(manifest)
    assert f"the manifest is invalid at {json_path}: {problem}" in " ".join(for_a_person.stderr.split())
    assert for_a_person.stdout == "", "nothing was verified, so there is no table"


def test_a_file_that_is_not_json_exits_two_at_the_root(tmp_path: Path) -> None:
    manifest = tmp_path / "notes.txt"
    manifest.write_text("Marrow basin wells, card list\n", encoding="utf-8")

    result = invoke("--json", "verify", str(manifest))

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert envelope(result)["error"]["details"]["json_path"] == "$"


def test_a_manifest_that_does_not_exist_is_a_usage_error() -> None:
    result = invoke("--json", "verify", "no-such-manifest.json")

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert envelope(result)["error"]["code"] == "USAGE_ERROR"


def test_the_manifest_can_come_from_stdin() -> None:
    result = runner.invoke(create_app(), ["--json", "verify", "-"], input=ALL_VERIFIED.read_bytes())

    assert result.exit_code == ExitCode.OK
    assert envelope(result)["data"]["total"] == 3


# --------------------------------------------------------------------------------------------
# Exit 3: verification could not run
# --------------------------------------------------------------------------------------------


class UnreachableBlobs(InMemorySnapshotStore):
    """Holds the scenario's blobs, then stops answering."""

    def __init__(self) -> None:
        super().__init__()
        self.failure: StoreError | None = None

    async def get(self, key: str) -> bytes:
        if self.failure is not None:
            raise self.failure
        return await super().get(key)


def app_with_the_store_down() -> typer.Typer:
    """The real app, with `verify`'s use case built over a blob store that cannot be reached.

    The container's override is the seam: the replacement command sets it and then runs the real
    `verify` command function, so everything after the service lookup is production code.
    """
    blobs = UnreachableBlobs()
    world = ManifestWorld(blobs=blobs, articles=InMemoryArticleRepository())
    build_fixture_manifests(world)
    blobs.failure = StoreUnavailable("GetObject", "blobs/sha256", "connection refused")

    def verify(ctx: typer.Context, manifest: Annotated[typer.FileBinaryRead, typer.Argument()]) -> None:
        cli_context(ctx).services.override("verify_manifest", world.use_case)
        verify_command.verify(ctx, manifest)

    app = create_app()
    app.registered_commands = [command for command in app.registered_commands if command.name != "verify"]
    app.command("verify")(verify)
    return app


def test_a_store_that_cannot_be_read_exits_three_and_gives_no_verdict() -> None:
    result = invoke("--json", "verify", str(ALL_VERIFIED), app=app_with_the_store_down())

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("VERIFICATION_COULD_NOT_RUN", 3)
    assert error["details"] == {"card_id": SENTENCE_ID, "position": 0, "cause": "StoreUnavailable"}
    assert "VERIFIED" not in json.dumps(error), "no card has a verdict"


def test_a_person_is_told_verification_could_not_run() -> None:
    result = invoke("verify", str(ALL_VERIFIED), app=app_with_the_store_down())

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    assert result.stdout == ""
    message = " ".join(result.stderr.split())
    assert "VERIFICATION_COULD_NOT_RUN" in message and "exit 3" in message
    assert "GetObject on blobs/sha256 failed: connection refused" in message


@needs_permissions
def test_an_unreadable_blob_directory_exits_three_and_names_its_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real filesystem store, refused by the operating system: a store that could not be read,
    not a bug (v1-e01-t20 ac2). Before that task the `PermissionError` escaped as exit 70.

    The cause is named by its class, and since v1-e34-t13 the filesystem stores raise the subclass
    that says the refusal was this machine's and not a bucket's."""
    data_dir = tmp_path / "data"
    build_fixture_data_dir(data_dir)
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))

    with refused(data_dir / BLOB_DIRECTORY):
        result = invoke("--json", "verify", str(ALL_VERIFIED))

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["details"]["cause"]) == (
        "VERIFICATION_COULD_NOT_RUN",
        "LocalStoreAccessDenied",
    )
    assert "the blob directory" in error["message"]
    assert str(data_dir) not in result.stdout + result.stderr


# --------------------------------------------------------------------------------------------
# The JSON export's manifest, through the command (v1-e06-t05: ac2, ac3)
# --------------------------------------------------------------------------------------------
#
# t02's VERIFIED news-article card, cut by CardService with the fake router and exported by
# ExportService, verified against a data directory that holds its snapshot. Written by hand from
# the committed answers: the card quotes the envelope [212, 712) less the omission [320, 422), 398
# characters, from a 1,106-character snapshot, and its first span underlines [31, 86).

VERSION_1_MANIFEST = ALL_VERIFIED.parent / "manifest_version_1.json"
EXPORTED_CARD_ID = "0CVT0000000000000000000001"


@dataclass(frozen=True)
class ExportedCard:
    data_dir: Path
    manifest: bytes


def copy_snapshot(world: CardWorld, snapshot: SourceSnapshot, data_dir: Path) -> None:
    """``snapshot``'s record and both its blobs, written into ``data_dir`` by the real local adapters."""
    database = SqliteDatabase.open(data_dir)
    try:
        blobs = FsSnapshotStore(data_dir)
        for key in (snapshot.raw_blob_key, snapshot.normalized_blob_key):
            assert run(blobs.put(run(world.blobs.get(key)))) == key, "both stores key a blob by its SHA-256"
        run(SqliteArticleRepository(database).save_snapshot(snapshot))
    finally:
        database.close()


@pytest.fixture(scope="module")
def exported_card(tmp_path_factory: pytest.TempPathFactory) -> ExportedCard:
    world = CardWorld()
    loaded = run(world.add_page())
    card = run(world.card_service.cut_card(news_request(loaded.snapshot.snapshot_id))).card
    assert (card.card_id, card.verification_status) == (EXPORTED_CARD_ID, VerificationStatus.VERIFIED)
    manifest = run(ExportService(articles=world.articles, clock=world.clock).export_json([card]))
    data_dir = tmp_path_factory.mktemp("exported") / "data"
    copy_snapshot(world, loaded.snapshot, data_dir)
    return ExportedCard(data_dir=data_dir, manifest=manifest)


@pytest.fixture
def exported(monkeypatch: pytest.MonkeyPatch, exported_card: ExportedCard) -> ExportedCard:
    """The exported card, with the command pointed at the data directory holding its snapshot."""
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(exported_card.data_dir))
    return exported_card


def verify_exported(
    tmp_path: Path, exported: ExportedCard, change: Callable[[dict[str, Any]], None] | None = None
) -> tuple[int, dict[str, Any]]:
    """`--json verify` on the exported manifest, ``change`` made to its card: the exit code and the report."""
    document = json.loads(exported.manifest)
    if change is not None:
        change(document["cards"][0])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    result = invoke("--json", "verify", str(manifest))
    output = envelope(result)
    return result.exit_code, output["data"] if result.exit_code == ExitCode.OK else output["error"]["details"]


def verdicts(report: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    return [(card["card_id"], card["status"], card["reason_codes"]) for card in report["cards"]]


def test_an_exported_manifest_of_a_verified_card_verifies_and_exits_zero(
    tmp_path: Path, exported: ExportedCard
) -> None:
    exit_code, report = verify_exported(tmp_path, exported)

    assert exit_code == ExitCode.OK
    assert report["manifest_version"] == 2
    assert verdicts(report) == [(EXPORTED_CARD_ID, "VERIFIED", [])]


def test_a_person_sees_the_exported_manifests_card_verified(tmp_path: Path, exported: ExportedCard) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(exported.manifest)

    result = invoke("verify", str(manifest))

    assert result.exit_code == ExitCode.OK, result.output
    assert "1 of 1 card(s) verified" in result.stdout


def test_an_exported_manifest_with_one_character_of_evidence_changed_exits_one_with_text_mismatch(
    tmp_path: Path, exported: ExportedCard
) -> None:
    def one_character(card: dict[str, Any]) -> None:
        text: str = card["evidence_text"]
        card["evidence_text"] = text[:100] + ("y" if text[100] == "x" else "x") + text[101:]

    exit_code, report = verify_exported(tmp_path, exported, one_character)

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert verdicts(report) == [(EXPORTED_CARD_ID, "UNVERIFIED", ["TEXT_MISMATCH"])]
    assert report["cards"][0]["reasons"][0]["first_differing_offset"] == 100


def moved_by(characters: int) -> Callable[[dict[str, Any]], None]:
    """Move the quotation's whole location in the snapshot, envelope and omission together."""

    def move(card: dict[str, Any]) -> None:
        card["evidence_start_offset"] += characters
        card["evidence_end_offset"] += characters
        for omission in card["omitted_ranges"]:
            omission["start_offset"] += characters
            omission["end_offset"] += characters

    return move


@pytest.mark.parametrize(
    ("change", "code"),
    [(moved_by(1), "TEXT_MISMATCH"), (moved_by(1000), "SPAN_OUT_OF_RANGE")],
    ids=["one character along", "past the snapshot's end"],
)
def test_an_exported_manifest_whose_quotation_moved_exits_one_with_the_verifiers_code(
    tmp_path: Path, exported: ExportedCard, change: Callable[[dict[str, Any]], None], code: str
) -> None:
    exit_code, report = verify_exported(tmp_path, exported, change)

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert verdicts(report) == [(EXPORTED_CARD_ID, "UNVERIFIED", [code])]


def set_offset(*path: str | int, to: int) -> Callable[[dict[str, Any]], None]:
    def change(card: dict[str, Any]) -> None:
        *parents, last = path
        target: Any = card
        for part in parents:
            target = target[part]
        target[last] = to

    return change


@pytest.mark.parametrize(
    "change",
    [
        set_offset("spans", 0, "end_offset", to=399),
        set_offset("evidence_start_offset", to=213),
        set_offset("evidence_end_offset", to=713),
        set_offset("omitted_ranges", 0, "start_offset", to=321),
    ],
    ids=["a span past the evidence", "the envelope's start", "the envelope's end", "an omission's start"],
)
def test_an_exported_manifest_with_one_offset_changed_exits_one_with_card_invalid(
    tmp_path: Path, exported: ExportedCard, change: Callable[[dict[str, Any]], None]
) -> None:
    """One offset alone breaks a rule Card enforces (spans inside the evidence, ADR-0018's length
    invariant), so the card never reaches the verifier: CARD_INVALID, exit 1, as in `mixed.json`."""
    exit_code, report = verify_exported(tmp_path, exported, change)

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert verdicts(report) == [(EXPORTED_CARD_ID, "UNVERIFIED", ["CARD_INVALID"])]


def test_an_exported_manifest_whose_markup_moved_inside_the_evidence_still_verifies(
    tmp_path: Path, exported: ExportedCard
) -> None:
    """Underlining is the debater's to change. Verification is of the quotation, which is untouched."""
    exit_code, report = verify_exported(tmp_path, exported, set_offset("spans", 0, "start_offset", to=30))

    assert exit_code == ExitCode.OK
    assert verdicts(report) == [(EXPORTED_CARD_ID, "VERIFIED", [])]


def test_the_version_1_manifest_v1_e03_t06_wrote_still_verifies_and_exits_zero() -> None:
    result = invoke("--json", "verify", str(VERSION_1_MANIFEST))

    assert result.exit_code == ExitCode.OK, result.output
    report = envelope(result)["data"]
    assert report["manifest_version"] == 1
    assert verdicts(report) == [
        (SENTENCE_ID, "VERIFIED", []),
        (WITH_CUT_ID, "VERIFIED", []),
        (PLANNED_ID, "VERIFIED", []),
    ]


def test_a_manifest_from_a_newer_build_exits_two_and_says_to_install_a_newer_build(tmp_path: Path) -> None:
    document = json.loads(ALL_VERIFIED.read_bytes())
    document["manifest_version"] = 3
    document["provenance"] = {"a": "field this build has never seen"}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    as_json = invoke("--json", "verify", str(manifest))
    for_a_person = invoke("verify", str(manifest))

    assert as_json.exit_code == for_a_person.exit_code == ExitCode.USAGE_ERROR
    error = envelope(as_json)["error"]
    problem = (
        "manifest_version 3 is newer than this build reads (1, 2); "
        "install a newer build of debate-research to verify it"
    )
    assert (error["code"], error["details"]["json_path"], error["details"]["problem"]) == (
        "INVALID_MANIFEST",
        "$.manifest_version",
        problem,
    )
    assert problem in " ".join(for_a_person.stderr.split())

"""`debate-research verify <manifest.json>`, through Typer's runner, the real app and composition root.

The manifests are the committed fixtures in `tests/fixtures/verify/`. The data directory is the same
scenario written to disk with the real local adapters (SQLite and the filesystem blob store), so
the command reads snapshots exactly as it does on a student's laptop. The expected verdicts are
written by hand from the fixture text; see `tests/fixtures/verify/manifest_world.py` and the use
case's tests, which count the offsets.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import pytest
import typer
from tests.fixtures.permissions import needs_permissions, refused
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
from debate_core.integrations.local import BLOB_DIRECTORY
from debate_core.testing import InMemoryArticleRepository, InMemorySnapshotStore

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
        (("manifest_version",), 2, "$.manifest_version", "must be 1"),
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
    not a bug (v1-e01-t20 ac2). Before that task the `PermissionError` escaped as exit 70."""
    data_dir = tmp_path / "data"
    build_fixture_data_dir(data_dir)
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))

    with refused(data_dir / BLOB_DIRECTORY):
        result = invoke("--json", "verify", str(ALL_VERIFIED))

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["details"]["cause"]) == ("VERIFICATION_COULD_NOT_RUN", "StoreAccessDenied")
    assert "the blob directory" in error["message"]
    assert str(data_dir) not in result.stdout + result.stderr

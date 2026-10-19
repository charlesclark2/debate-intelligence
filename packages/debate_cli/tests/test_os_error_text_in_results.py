"""An `OSError` that a run records, rather than ends on, is named by its class and errno (`v1-e29-t09`).

`v1-e01-t25` kept an `OSError`'s text out of what the CLI prints when one ends a command: it quotes
the path it failed on, which carries the home directory and, for a file in the inbox, a camp
file's title. Four routes still carried it, because a service put `str(failure)` into a result or
into a message of its own: `store sync --apply`'s `failed[].message`, `caselist publish`'s
`failed[].message` and `manifest_error`, and the messages of `RemovalIncomplete` and
`RemovalCompletedUnlogged`. (The fourth, `ParsedObjectOutcome.error_message`, which nothing renders
yet, is tested beside the parsed store's publisher.)

Each route is driven to record an `OSError` whose text holds an invented home directory and camp
title, and the probe word is looked for in the panel and in the `--json` envelope with everything
but letters and digits removed, so a line wrap or a box border cannot hide it. The first two run
through the real composition root against moto; the removal errors are raised as the removal
service raises them, from an `OSError`, and printed by the CLI's own handler.

Nothing reaches AWS: moto answers in-process, and sockets are disabled.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import boto3
import pytest
import typer
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.context import cli_context
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.removal_service import (
    RemovalCompletedUnlogged,
    RemovalIncomplete,
    RemovalReport,
)
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-os-error-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"

PROBE_TITLE = "Zqxprobe Lantern Camp Release"
PROBE_PATH = f"/Users/zqxprobe-home/debate-data/inbox/{PROBE_TITLE}.docx"
PROBE_WORD = "zqxprobe"
"""In both the path and the title, and in nothing this project writes. Invented: no such home
directory, camp or file exists."""

NAMED_BY_CLASS_AND_ERRNO = "PermissionError (errno 13)"
"""What each route says of the `OSError` instead of its text, written out by hand."""

WIDE = {"COLUMNS": "200"}


def refused_at_the_probe() -> PermissionError:
    """The operating system refusing a file whose path holds a home directory and a camp's title."""
    return PermissionError(13, "Permission denied", PROBE_PATH)


def letters_and_digits(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def holds_probe(text: str) -> bool:
    return PROBE_WORD in letters_and_digits(text)


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a moto bucket and an evidence profile, and one data directory."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    config.write_text(f"[profile {AWS_PROFILE_NAME}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{AWS_PROFILE_NAME}]\naws_access_key_id = testing\naws_secret_access_key = testing\n",
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    data_dir = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data_dir}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        f'[caselist]\nnotifier = "none"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data_dir


@pytest.fixture
def bucket() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield client


def uploads_refused_by_the_os(monkeypatch: pytest.MonkeyPatch, *, only: str = "") -> None:
    """Every upload under `only` meets a `PermissionError` reading its file, as an unreadable one does."""
    real_put = S3EvidenceObjectStore.put_file

    async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
        if key.startswith(only):
            raise refused_at_the_probe()
        return await real_put(self, key, source)

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)


def both_outputs(*arguments: str) -> tuple[Result, Result]:
    """The command as a person sees it, then with `--json`."""
    app = create_app()
    return (
        runner.invoke(app, list(arguments), env=WIDE),
        runner.invoke(create_app(), ["--json", *arguments], env=WIDE),
    )


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    parsed: dict[str, Any] = json.loads(lines[0])
    return parsed


def import_the_first_week(tmp_path: Path) -> None:
    week = SNAPSHOTS[0]
    archive = build_snapshot_zips(tmp_path / "downloads")[week.snapshot]
    imported = runner.invoke(
        create_app(),
        ["--json", "caselist", "import", str(archive), "--caselist", SYNTHETIC_CASELIST,
         "--snapshot", week.snapshot.isoformat()],
    )  # fmt: skip
    assert imported.exit_code == ExitCode.OK, imported.stdout


# ------------------------------------------------------------------------------------------------
# store sync --apply: data.failed[].message
# ------------------------------------------------------------------------------------------------


def test_store_sync_names_an_os_error_by_its_class_and_errno(
    installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = installation / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-01.jsonl"
    path.parent.mkdir(parents=True)
    # A manifest a publish could read, which a push asks about before it sends it (v1-e30-t25).
    path.write_bytes(b'{"kind": "summary"}\n')
    uploads_refused_by_the_os(monkeypatch)

    shown, envelope = both_outputs("store", "sync", "--apply")

    assert shown.exit_code == envelope.exit_code == ExitCode.DOMAIN_FAILURE
    [failed] = envelope_of(envelope)["error"]["details"]["failed"]
    assert (failed["code"], failed["message"]) == ("PERMISSION_ERROR", NAMED_BY_CLASS_AND_ERRNO)
    assert not holds_probe(shown.stdout + shown.stderr), shown.stderr
    assert not holds_probe(envelope.stdout + envelope.stderr), envelope.stdout


# ------------------------------------------------------------------------------------------------
# caselist publish: failed[].message and manifest_error
# ------------------------------------------------------------------------------------------------


def test_caselist_publish_names_a_sources_os_error_by_its_class_and_errno(
    tmp_path: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_the_first_week(tmp_path)
    uploads_refused_by_the_os(monkeypatch, only="raw/")

    shown, envelope = both_outputs("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)

    assert shown.exit_code == envelope.exit_code == ExitCode.DOMAIN_FAILURE
    snapshots = envelope_of(envelope)["error"]["details"]["snapshots"]
    failed = [entry for snapshot in snapshots for entry in snapshot["failed"]]
    assert failed, "every source's upload was refused"
    assert {(entry["code"], entry["message"]) for entry in failed} == {
        ("PERMISSION_ERROR", NAMED_BY_CLASS_AND_ERRNO)
    }
    assert not holds_probe(shown.stdout + shown.stderr), shown.stderr
    assert not holds_probe(envelope.stdout + envelope.stderr), envelope.stdout


def test_caselist_publish_names_a_manifests_os_error_by_its_class_and_errno(
    tmp_path: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_the_first_week(tmp_path)
    uploads_refused_by_the_os(monkeypatch, only="manifests/")

    shown, envelope = both_outputs("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)

    assert shown.exit_code == envelope.exit_code == ExitCode.DOMAIN_FAILURE
    [snapshot] = envelope_of(envelope)["error"]["details"]["snapshots"]
    assert snapshot["manifest"] == "failed"
    assert (snapshot["manifest_error_code"], snapshot["manifest_error"]) == (
        "PERMISSION_ERROR",
        NAMED_BY_CLASS_AND_ERRNO,
    )
    assert not holds_probe(shown.stdout + shown.stderr), shown.stderr
    assert not holds_probe(envelope.stdout + envelope.stderr), envelope.stdout


# ------------------------------------------------------------------------------------------------
# caselist remove: the messages of RemovalIncomplete and RemovalCompletedUnlogged
# ------------------------------------------------------------------------------------------------

COUNTS = SimpleNamespace(
    local_records_deleted=1, local_files_deleted=2, s3_versions_deleted=3, manifests_rewritten=1,
    manifest_rows_dropped=4, inbox_files_deleted=0, inbox_files_rewritten=0,
)  # fmt: skip
"""What a removal did, as the two errors read it from its report."""


def stopped_part_way() -> RemovalIncomplete:
    """A removal stopped by an `OSError`, whose log entry the same `OSError` kept out."""
    return RemovalIncomplete(
        cast("RemovalReport", COUNTS),
        refused_at_the_probe(),
        suppressed=True,
        unlogged=refused_at_the_probe(),
    )


def completed_unlogged() -> RemovalCompletedUnlogged:
    """A removal that completed and could not write its log entry to this machine's copy."""
    return RemovalCompletedUnlogged(
        cast("RemovalReport", COUNTS), refused_at_the_probe(), holding=(), missing=("the local removal log",)
    )


def app_raising(build: Callable[[], Exception]) -> typer.Typer:
    def remove(ctx: typer.Context) -> None:
        cli_context(ctx)
        raise build()

    app = create_app()
    app.command("remove")(remove)
    return app


@pytest.mark.parametrize(
    ("build", "code"),
    [
        pytest.param(stopped_part_way, "REMOVAL_INCOMPLETE", id="a removal stopped part-way"),
        pytest.param(completed_unlogged, "REMOVAL_COMPLETED_UNLOGGED", id="a removal completed unlogged"),
    ],
)
def test_a_removals_message_names_an_os_error_by_its_class_and_errno(
    build: Callable[[], Exception], code: str
) -> None:
    shown = runner.invoke(app_raising(build), ["remove"], env=WIDE)
    envelope = runner.invoke(app_raising(build), ["--json", "remove"], env=WIDE)

    assert shown.exit_code == envelope.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(envelope)["error"]
    assert error["code"] == code
    assert NAMED_BY_CLASS_AND_ERRNO in error["message"]
    assert not holds_probe(shown.stdout + shown.stderr), shown.stderr
    assert not holds_probe(envelope.stdout + envelope.stderr), envelope.stdout

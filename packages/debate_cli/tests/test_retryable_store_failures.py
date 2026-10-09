"""A failure a retry may cure exits 3 in every command family, and a verdict keeps 1 (`v1-e01-t20`).

Two failures, command family by command family, through the real application and composition
root:

* **An expired SSO session.** botocore is made to answer every call the way it does once the
  operator's session has expired (`UnauthorizedSSOTokenError`), so the real S3 adapter does the
  translating to `StoreCredentialsExpired`, exactly as on a laptop the morning after.
* **An unreadable blob directory.** The data directory's `blobs/sha256` is `chmod 000`, so the real
  filesystem store meets a real `PermissionError` and has to say `StoreAccessDenied` itself.

A family whose commands cannot meet one of the two has no test for it: `caselist import` never
reads the bucket, and the blob directory that `store`, `caselist publish` and `caselist remove`
read goes through stores this task leaves alone (the session report's Deviations). `caselist pull`
is in `tests/smoke/test_caselist_pull.py`, beside the site it needs; `verify` is in
`test_verify_command.py`.

Nothing reaches AWS: moto answers botocore in-process, or nothing answers at all, and sockets are
disabled.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.permissions import needs_permissions, refused
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.integrations.local import BLOB_DIRECTORY
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-retry-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
BLOB_PREFIX = f"raw/caselist/{SYNTHETIC_CASELIST}"
EXPIRED_HINT = f"aws sso login --profile {AWS_PROFILE_NAME}"


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a moto bucket and an SSO profile, one data directory, fake AWS."""
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
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
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


def expire_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every AWS call answers as it does once the operator's SSO session has expired."""

    def no_session(*_: object, **__: object) -> None:
        from botocore.exceptions import UnauthorizedSSOTokenError

        raise UnauthorizedSSOTokenError

    monkeypatch.setattr("botocore.client.BaseClient._make_api_call", no_session)


def uploads_answer_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every upload to the bucket fails as S3 does when it is throttling: a store that did not answer."""

    async def unavailable(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
        raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", unavailable)


def write_local_object(data_dir: Path, key: str, body: bytes) -> None:
    path = data_dir / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def write_local_blob(data_dir: Path, body: bytes) -> str:
    """Store `body` where the blob store would, and return its key relative to `blobs/`."""
    digest = hashlib.sha256(body).hexdigest()
    path = data_dir / BLOB_DIRECTORY / digest[0:2] / digest[2:4] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return f"sha256/{digest[0:2]}/{digest[2:4]}/{digest}"


def run(*arguments: str) -> tuple[int, dict[str, Any]]:
    """Run one command with `--json`; return its exit code and its one envelope."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    assert envelope["error"] is None or envelope["error"]["exit_code"] == result.exit_code
    return result.exit_code, envelope


def import_the_first_week(tmp_path: Path) -> tuple[int, dict[str, Any]]:
    week = SNAPSHOTS[0]
    archive = build_snapshot_zips(tmp_path / "downloads")[week.snapshot]
    return run(
        "caselist", "import", str(archive),
        "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
    )  # fmt: skip


def assert_expired_session(exit_code: int, envelope: dict[str, Any]) -> None:
    """3, reported as the store failure it is, with the line that fixes it."""
    assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
    assert envelope["error"]["code"] == "STORE_CREDENTIALS_EXPIRED"
    assert envelope["error"]["hint"] == EXPIRED_HINT


# ------------------------------------------------------------------------------------------------
# store sync | ls | get
# ------------------------------------------------------------------------------------------------


class TestStoreFamily:
    @pytest.mark.parametrize(
        "command",
        [("store", "sync"), ("store", "ls"), ("store", "get", "manifests/testcl26/2026-09-01.jsonl")],
        ids=" ".join,
    )
    def test_an_expired_session_exits_three(
        self, monkeypatch: pytest.MonkeyPatch, command: tuple[str, ...]
    ) -> None:
        expire_the_session(monkeypatch)

        assert_expired_session(*run(*command))

    def test_an_apply_whose_every_failure_is_the_store_not_answering_exits_three(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each object fails on its own and the run carries on; then the run is a 3, not a 1."""
        write_local_object(installation, "manifests/testcl26/2026-09-01.jsonl", b"week one\n")
        write_local_object(installation, "manifests/testcl26/2026-09-08.jsonl", b"week two\n")
        uploads_answer_503(monkeypatch)

        exit_code, envelope = run("store", "sync", "--apply")

        assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
        assert envelope["error"]["code"] == "STORE_UNAVAILABLE"
        assert len(envelope["error"]["details"]["failed"]) == 2

    def test_a_mismatch_among_the_failures_keeps_the_run_a_one(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key whose two sides disagree is a verdict; a store that also stuttered does not hide it."""
        blob_key = write_local_blob(installation, b"a disclosed file")
        bucket.put_object(Bucket=BUCKET, Key=f"{BLOB_PREFIX}/{blob_key}", Body=b"something else entirely")
        write_local_object(installation, "manifests/testcl26/2026-09-01.jsonl", b"week one\n")
        uploads_answer_503(monkeypatch)

        exit_code, envelope = run("store", "sync", "--blob-prefix", BLOB_PREFIX, "--apply")

        assert exit_code == ExitCode.DOMAIN_FAILURE, envelope
        assert envelope["error"]["details"]["mismatched"] == [f"{BLOB_PREFIX}/{blob_key}"]
        assert [failed["code"] for failed in envelope["error"]["details"]["failed"]] == ["STORE_UNAVAILABLE"]


# ------------------------------------------------------------------------------------------------
# caselist import | import-openev
# ------------------------------------------------------------------------------------------------


class TestImportFamily:
    @needs_permissions
    def test_an_unreadable_blob_directory_exits_three_naming_its_role(
        self, installation: Path, tmp_path: Path
    ) -> None:
        blobs = installation / BLOB_DIRECTORY
        blobs.mkdir(parents=True)

        with refused(blobs):
            exit_code, envelope = import_the_first_week(tmp_path)

        assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
        assert envelope["error"]["code"] == "STORE_ACCESS_DENIED"
        assert envelope["error"]["details"]["resource"] == "the blob directory"
        assert str(installation) not in json.dumps(envelope)


# ------------------------------------------------------------------------------------------------
# caselist publish | status
# ------------------------------------------------------------------------------------------------


class TestPublishFamily:
    def test_publish_with_an_expired_session_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert import_the_first_week(tmp_path)[0] == ExitCode.OK
        expire_the_session(monkeypatch)

        assert_expired_session(*run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST))

    def test_publish_whose_only_failures_are_manifests_the_store_did_not_take_exits_three(
        self, tmp_path: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every source uploads and verifies; each manifest upload answers 503. The manifest's own
        failure is what decides the exit code here, since no source failed."""
        assert import_the_first_week(tmp_path)[0] == ExitCode.OK
        real_put = S3EvidenceObjectStore.put_file

        async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
            if key.startswith("manifests/"):
                raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
            return await real_put(self, key, source)

        monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)

        exit_code, envelope = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)

        assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
        assert envelope["error"]["code"] == "PUBLISH_INCOMPLETE"
        assert envelope["error"]["details"]["failed_sha256"] == []
        assert {entry["manifest"] for entry in envelope["error"]["details"]["snapshots"]} == {"failed"}

    def test_status_with_an_expired_session_exits_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        expire_the_session(monkeypatch)

        assert_expired_session(*run("caselist", "status"))


# ------------------------------------------------------------------------------------------------
# caselist runs
# ------------------------------------------------------------------------------------------------


class TestRunsFamily:
    def test_reading_the_buckets_run_records_with_an_expired_session_exits_three(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expire_the_session(monkeypatch)

        assert_expired_session(*run("caselist", "runs", "--remote"))


# ------------------------------------------------------------------------------------------------
# caselist remove | unsuppress
# ------------------------------------------------------------------------------------------------


class TestRemovalFamily:
    def test_planning_a_removal_with_an_expired_session_exits_three(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expire_the_session(monkeypatch)

        assert_expired_session(
            *run(
                "caselist",
                "remove",
                "--source",
                "0" * 64,
                "--request",
                "RM-2026-01",
                "--reason",
                "REQUESTED_BY_TEAM",
            )  # fmt: skip
        )

    def test_planning_an_unsuppress_with_an_expired_session_exits_three(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expire_the_session(monkeypatch)

        assert_expired_session(
            *run("caselist", "unsuppress", "--sha256", "0" * 64, "--reason", "REMOVED_IN_ERROR")
        )

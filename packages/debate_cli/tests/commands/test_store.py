"""`debate-research store sync | ls | get`, run the way an operator runs them.

Through Typer's `CliRunner` against the real application and the real composition root, so these
exercise the parsing, the guards, the envelope and the exit codes an installed `debate-research`
produces — and, underneath, the real S3 adapter against a moto bucket.

The environments are the point of several of these, so the fixture writes its own profile
directory with a `dev.toml` and a `prod.toml` that name *different* moto buckets and different
SSO profile names, exactly as the committed profiles name different real ones. That is how the
dev/prod split is tested without an AWS account, and it is why no test here reads
`config/profiles/` (those values are checked in
`packages/debate_core/tests/application/test_settings.py`).

Nothing here reaches AWS: moto answers botocore in-process and the workspace's pytest options
disable sockets.
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
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.integrations.s3 import SHA256_METADATA_NAME

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

DEV_BUCKET = "debate-dev-evidence-moto"
PROD_BUCKET = "debate-prod-evidence-moto"
DEV_PROFILE = "debate-dev-evidence"
PROD_PROFILE = "debate-prod-evidence"
MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
MANIFEST_BODY = b'{"sha256":"5e88489","bytes":48213}\n'
BLOB_PREFIX = "raw/caselist/hsld26"


@pytest.fixture(autouse=True)
def fake_aws_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An AWS config of this test's own, holding the two evidence profiles and nothing real.

    A real config file rather than `AWS_CONFIG_FILE=/dev/null`, because the profile is not a label
    the CLI carries around: `boto3.session.Session(profile_name=…)` resolves it when the client is
    built and raises `ProfileNotFound` if it is not there. Writing the profiles out is what makes
    these tests exercise the same resolution an operator's laptop does, on credentials that are
    the literal string `testing` and cannot reach an account.

    `AWS_PROFILE` is deleted rather than set: an operator running this suite with a live
    `debate-prod-evidence` session in their own environment must not have it consulted.
    """
    config = tmp_path / "aws-config"
    config.write_text(
        "\n".join(f"[profile {profile}]\nregion = us-east-1\n" for profile in (DEV_PROFILE, PROD_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "\n".join(
            f"[{profile}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for profile in (DEV_PROFILE, PROD_PROFILE)
        ),
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    return config


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A profile directory this test owns, with dev and prod naming different buckets."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment, bucket, profile in (
        ("dev", DEV_BUCKET, DEV_PROFILE),
        ("prod", PROD_BUCKET, PROD_PROFILE),
    ):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{tmp_path / environment}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            f'aws_profile = "{profile}"\n'
            f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[providers]\nenabled = []\n[storage]\ndata_dir = "{tmp_path / "test"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield profiles


@pytest.fixture
def buckets() -> Iterator[S3Client]:
    """An empty, versioned dev and prod bucket in moto, for the whole of one test."""
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        yield client


@pytest.fixture
def dev_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "dev"


def write_local_object(data_dir: Path, key: str, body: bytes) -> str:
    path = data_dir / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def write_local_blob(data_dir: Path, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    path = data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return f"sha256/{digest[0:2]}/{digest[2:4]}/{digest}"


def put_remote_object(client: S3Client, bucket: str, key: str, body: bytes) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        Metadata={SHA256_METADATA_NAME: hashlib.sha256(body).hexdigest()},
    )


def remote_keys(client: S3Client, bucket: str) -> list[str]:
    listing = client.list_objects_v2(Bucket=bucket)
    return sorted(str(stored.get("Key", "")) for stored in listing.get("Contents", []))


def envelope_of(result: Result) -> dict[str, Any]:
    """Parse the result's stdout, asserting it is exactly one JSON object."""
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


# ------------------------------------------------------------------------------------------------
# store sync: the dry run, and what an apply actually moves (acceptance criterion 1)
# ------------------------------------------------------------------------------------------------


class TestSyncPlansByDefault:
    def test_a_bare_sync_prints_the_counts_and_moves_nothing(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("store", "sync")

        assert result.exit_code == ExitCode.OK
        assert "new" in result.stdout
        assert "Planned only" in result.stdout
        assert remote_keys(buckets, DEV_BUCKET) == []

    def test_the_dry_run_payload_carries_every_count_and_byte_total(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)
        put_remote_object(buckets, DEV_BUCKET, "reports/sync/old.json", b"{}")

        data = envelope_of(invoke("--json", "store", "sync"))["data"]

        assert data["applied"] is False
        assert data["direction"] == "push"
        assert data["bucket"] == DEV_BUCKET
        assert data["counts"] == {
            "new": 1,
            "changed": 0,
            "skipped": 0,
            "would_delete": 1,
            "mismatched": 0,
        }
        assert data["bytes"]["new"] == len(MANIFEST_BODY)
        assert data["transferred"] == 0

    def test_dry_run_is_the_default_and_apply_is_what_transfers(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        assert remote_keys(buckets, DEV_BUCKET) == []
        assert invoke("store", "sync", "--dry-run").exit_code == ExitCode.OK
        assert remote_keys(buckets, DEV_BUCKET) == []

        assert invoke("store", "sync", "--apply").exit_code == ExitCode.OK
        assert remote_keys(buckets, DEV_BUCKET) == [MANIFEST_KEY]

    def test_an_apply_uploads_exactly_what_was_planned_and_a_repeat_does_nothing(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        """Acceptance criterion 1, end to end through the command."""
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)
        planned = envelope_of(invoke("--json", "store", "sync"))["data"]

        applied = envelope_of(invoke("--json", "store", "sync", "--apply"))["data"]
        repeated = envelope_of(invoke("--json", "store", "sync"))["data"]

        assert planned["counts"]["new"] == 1
        assert applied["applied"] is True
        assert applied["transferred"] == 1
        assert repeated["counts"]["new"] == 0
        assert repeated["counts"]["changed"] == 0
        assert repeated["counts"]["skipped"] == 1
        assert remote_keys(buckets, DEV_BUCKET) == [MANIFEST_KEY]

    def test_the_prefix_filter_narrows_the_run(self, buckets: S3Client, dev_data_dir: Path) -> None:
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)
        write_local_object(dev_data_dir, "reports/sync/run.json", b"{}")

        invoke("store", "sync", "--prefix", "manifests/", "--apply")

        assert remote_keys(buckets, DEV_BUCKET) == [MANIFEST_KEY]

    def test_blobs_need_the_corpus_prefix_that_says_where_they_belong(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        write_local_blob(dev_data_dir, b"a disclosed file")

        refused = invoke("--json", "store", "sync")

        assert refused.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(refused)["error"]
        assert error["code"] == "UNSYNCABLE_KEYSPACE"
        assert "raw/caselist/hsld26" in error["message"]

    def test_the_corpus_syncs_under_the_prefix_it_is_given(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        key = write_local_blob(dev_data_dir, b"a disclosed file")

        result = invoke("store", "sync", "--blob-prefix", BLOB_PREFIX, "--apply")

        assert result.exit_code == ExitCode.OK
        assert remote_keys(buckets, DEV_BUCKET) == [f"{BLOB_PREFIX}/{key}"]

    def test_a_pull_brings_the_bucket_down(self, buckets: S3Client, dev_data_dir: Path) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("store", "sync", "--pull", "--apply")

        assert result.exit_code == ExitCode.OK
        assert (dev_data_dir / "objects" / MANIFEST_KEY).read_bytes() == MANIFEST_BODY

    def test_the_journal_path_is_reported_so_an_operator_can_find_it(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        data = envelope_of(invoke("--json", "store", "sync", "--apply"))["data"]

        assert data["journal"] == str(dev_data_dir / "sync-journal" / "dev.jsonl")
        assert Path(data["journal"]).is_file()


# ------------------------------------------------------------------------------------------------
# The environments and the production guard (acceptance criterion 4)
# ------------------------------------------------------------------------------------------------


class TestEnvironments:
    def test_dev_and_prod_resolve_to_different_buckets_and_profiles(
        self, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        development = envelope_of(invoke("--json", "config", "show"))["data"]
        monkeypatch.setenv("DEBATE_ENV", "prod")
        production = envelope_of(invoke("--json", "config", "show"))["data"]

        assert development["settings"]["storage.s3.bucket"] == DEV_BUCKET
        assert production["settings"]["storage.s3.bucket"] == PROD_BUCKET
        assert development["settings"]["storage.s3.aws_profile"] == DEV_PROFILE
        assert production["settings"]["storage.s3.aws_profile"] == PROD_PROFILE

    def test_a_sync_writes_to_the_bucket_its_environment_names(
        self, buckets: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_local_object(tmp_path / "dev", MANIFEST_KEY, MANIFEST_BODY)
        write_local_object(tmp_path / "prod", "manifests/hsld26/prod.jsonl", b"{}")

        invoke("store", "sync", "--apply")
        monkeypatch.setenv("DEBATE_ENV", "prod")
        invoke("store", "sync", "--apply", "--confirm-prod")

        assert remote_keys(buckets, DEV_BUCKET) == [MANIFEST_KEY]
        assert remote_keys(buckets, PROD_BUCKET) == ["manifests/hsld26/prod.jsonl"]

    def test_pushing_to_prod_without_confirm_prod_is_refused(
        self, buckets: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_local_object(tmp_path / "prod", MANIFEST_KEY, MANIFEST_BODY)
        monkeypatch.setenv("DEBATE_ENV", "prod")

        refused = invoke("--json", "store", "sync", "--apply")

        assert refused.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(refused)["error"]
        assert error["code"] == "CONFIRMATION_REQUIRED"
        assert "--confirm-prod" in error["message"]
        assert remote_keys(buckets, PROD_BUCKET) == []

    def test_a_prod_dry_run_needs_no_confirmation(
        self, buckets: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reading what would change is how an operator decides whether to confirm."""
        write_local_object(tmp_path / "prod", MANIFEST_KEY, MANIFEST_BODY)
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = invoke("--json", "store", "sync")

        assert result.exit_code == ExitCode.OK
        assert envelope_of(result)["data"]["counts"]["new"] == 1
        assert remote_keys(buckets, PROD_BUCKET) == []

    def test_a_prod_pull_needs_no_confirmation(
        self, buckets: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        put_remote_object(buckets, PROD_BUCKET, MANIFEST_KEY, MANIFEST_BODY)
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = invoke("store", "sync", "--pull", "--apply")

        assert result.exit_code == ExitCode.OK
        assert (tmp_path / "prod" / "objects" / MANIFEST_KEY).read_bytes() == MANIFEST_BODY

    def test_the_test_environment_names_no_bucket_and_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "test")

        refused = invoke("--json", "store", "sync")

        assert refused.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(refused)["error"]
        assert error["code"] == "EVIDENCE_STORE_NOT_CONFIGURED"
        assert "names no evidence bucket" in error["message"]

    def test_applying_under_the_test_environment_is_refused_before_anything_is_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "test")

        refused = invoke("--json", "store", "sync", "--apply")

        assert envelope_of(refused)["error"]["code"] == "ENVIRONMENT_NOT_SYNCABLE"

    def test_an_environment_that_is_not_one_of_the_three_fails_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "staging")

        refused = invoke("--json", "store", "sync")

        assert refused.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(refused)["error"]["code"] == "CONFIGURATION_ERROR"


# ------------------------------------------------------------------------------------------------
# Failures the operator has to act on (acceptance criteria 2 and 4)
# ------------------------------------------------------------------------------------------------


class TestFailures:
    def test_a_blob_that_differs_from_the_bucket_fails_the_command(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        """Acceptance criterion 2: a mismatch exits non-zero, and nothing is overwritten."""
        key = write_local_blob(dev_data_dir, b"a disclosed file")
        put_remote_object(buckets, DEV_BUCKET, f"{BLOB_PREFIX}/{key}", b"something else entirely")

        result = invoke("--json", "store", "sync", "--blob-prefix", BLOB_PREFIX, "--apply")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(result)["error"]
        assert error["code"] == "BLOB_INTEGRITY_ERROR"
        assert error["details"]["counts"]["mismatched"] == 1
        assert error["details"]["first_key"] == f"{BLOB_PREFIX}/{key}"
        stored = buckets.get_object(Bucket=DEV_BUCKET, Key=f"{BLOB_PREFIX}/{key}")
        assert stored["Body"].read() == b"something else entirely"

    def test_a_failed_run_still_reports_every_count_for_the_scheduled_consumer(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        key = write_local_blob(dev_data_dir, b"a disclosed file")
        put_remote_object(buckets, DEV_BUCKET, f"{BLOB_PREFIX}/{key}", b"something else entirely")
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("--json", "store", "sync", "--blob-prefix", BLOB_PREFIX, "--apply")

        envelope = envelope_of(result)
        assert envelope["status"] == "error"
        assert envelope["error"]["exit_code"] == result.exit_code
        assert envelope["error"]["details"]["transferred"] == 1
        assert envelope["error"]["details"]["journal"] is not None

    def test_a_person_still_sees_the_table_when_the_run_failed(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        key = write_local_blob(dev_data_dir, b"a disclosed file")
        put_remote_object(buckets, DEV_BUCKET, f"{BLOB_PREFIX}/{key}", b"something else entirely")

        result = invoke("store", "sync", "--blob-prefix", BLOB_PREFIX, "--apply")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert "mismatched" in result.stdout
        assert "BLOB_INTEGRITY_ERROR" in result.stderr

    def test_an_expired_sso_session_is_one_line_and_not_a_traceback(
        self, dev_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance criterion 4. There is no moto here: nothing answers, as nothing would."""
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        def no_session(*_: object, **__: object) -> None:
            from botocore.exceptions import UnauthorizedSSOTokenError

            raise UnauthorizedSSOTokenError

        monkeypatch.setattr("botocore.client.BaseClient._make_api_call", no_session)

        result = invoke("store", "sync")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert "aws sso login --profile debate-dev-evidence" in result.stderr
        assert "Traceback" not in result.stderr
        assert "STORE_CREDENTIALS_EXPIRED" in result.stderr

    def test_an_expired_sso_session_reports_the_hint_as_a_field_for_a_program(
        self, dev_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def no_session(*_: object, **__: object) -> None:
            from botocore.exceptions import UnauthorizedSSOTokenError

            raise UnauthorizedSSOTokenError

        monkeypatch.setattr("botocore.client.BaseClient._make_api_call", no_session)

        error = envelope_of(invoke("--json", "store", "sync"))["error"]

        assert error["code"] == "STORE_CREDENTIALS_EXPIRED"
        assert error["hint"] == "aws sso login --profile debate-dev-evidence"


# ------------------------------------------------------------------------------------------------
# store ls and store get
# ------------------------------------------------------------------------------------------------


class TestListing:
    def test_ls_lists_the_bucket(self, buckets: S3Client) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("store", "ls")

        assert result.exit_code == ExitCode.OK
        assert MANIFEST_KEY in result.stdout

    def test_ls_reports_each_object_as_json(self, buckets: S3Client) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)

        data = envelope_of(invoke("--json", "store", "ls"))["data"]

        assert data["bucket"] == DEV_BUCKET
        assert data["count"] == 1
        assert data["objects"] == [{"key": MANIFEST_KEY, "size": len(MANIFEST_BODY)}]

    def test_ls_takes_a_prefix(self, buckets: S3Client) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)
        put_remote_object(buckets, DEV_BUCKET, "reports/sync/run.json", b"{}")

        data = envelope_of(invoke("--json", "store", "ls", "manifests/"))["data"]

        assert [entry["key"] for entry in data["objects"]] == [MANIFEST_KEY]

    def test_ls_reports_each_object_once(self, buckets: S3Client) -> None:
        """Two keyspaces over one bucket must not make one object look like two."""
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)

        data = envelope_of(invoke("--json", "store", "ls"))["data"]

        assert data["count"] == 1


class TestGetting:
    def test_get_writes_the_object_into_the_local_store(self, buckets: S3Client, dev_data_dir: Path) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("store", "get", MANIFEST_KEY)

        assert result.exit_code == ExitCode.OK
        assert (dev_data_dir / "objects" / MANIFEST_KEY).read_bytes() == MANIFEST_BODY

    def test_get_writes_where_it_is_told(self, buckets: S3Client, tmp_path: Path) -> None:
        put_remote_object(buckets, DEV_BUCKET, MANIFEST_KEY, MANIFEST_BODY)
        destination = tmp_path / "out" / "manifest.jsonl"

        data = envelope_of(invoke("--json", "store", "get", MANIFEST_KEY, "-o", str(destination)))["data"]

        assert destination.read_bytes() == MANIFEST_BODY
        assert data["sha256"] == hashlib.sha256(MANIFEST_BODY).hexdigest()
        assert data["destination"] == str(destination)

    def test_get_puts_a_blob_where_the_local_blob_store_keeps_it(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        body = b"a disclosed file"
        digest = hashlib.sha256(body).hexdigest()
        key = f"{BLOB_PREFIX}/sha256/{digest[0:2]}/{digest[2:4]}/{digest}"
        put_remote_object(buckets, DEV_BUCKET, key, body)

        result = invoke("store", "get", key)

        assert result.exit_code == ExitCode.OK
        assert (dev_data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest).read_bytes() == body

    def test_getting_an_object_that_is_not_there_says_so(self, buckets: S3Client) -> None:
        result = invoke("--json", "store", "get", MANIFEST_KEY)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "NOT_FOUND"


# ------------------------------------------------------------------------------------------------
# The surface itself
# ------------------------------------------------------------------------------------------------


class TestTheCommandSurface:
    @pytest.mark.parametrize("subcommand", ["sync", "ls", "get"])
    def test_every_subcommand_renders_its_help(self, subcommand: str) -> None:
        result = invoke("store", subcommand, "--help")

        assert result.exit_code == ExitCode.OK
        assert "Usage" in result.stdout

    def test_store_with_no_subcommand_lists_what_it_can_do(self) -> None:
        result = invoke("store")

        assert "sync" in result.stdout
        assert "ls" in result.stdout
        assert "get" in result.stdout

    def test_an_unknown_subcommand_is_a_usage_error(self) -> None:
        assert invoke("store", "upload").exit_code == ExitCode.USAGE_ERROR

    def test_nothing_prints_a_credential_or_an_objects_contents(
        self, buckets: S3Client, dev_data_dir: Path
    ) -> None:
        """A sync summary counts objects; it never quotes one, and never names a secret."""
        write_local_object(dev_data_dir, MANIFEST_KEY, MANIFEST_BODY)

        result = invoke("--verbose", "store", "sync", "--apply")
        written = result.stdout + result.stderr

        assert MANIFEST_BODY.decode().strip() not in written
        assert "testing" not in written
        assert "AWS_SECRET_ACCESS_KEY" not in written

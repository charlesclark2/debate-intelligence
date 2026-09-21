"""`debate-research caselist publish` and `caselist status`, run the way an operator runs them.

Through Typer's `CliRunner` against the real application and composition root, the real importer
and the real S3 adapter over moto. The profile directory is this test's own: dev and prod name
*different* moto buckets, which is how ac5 — `DEBATE_ENV` selects the bucket — is checked without
an AWS account. Expected keys and counts come from the hand-written
`tests/fixtures/caselist/expected_publish.json`.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

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
from tests.fixtures.caselist.publish_expectations import (
    FICTIONAL_IDENTIFIERS,
    digest_of_body,
    expected_publish,
    expected_source_key,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

DEV_BUCKET = "debate-dev-evidence-moto"
PROD_BUCKET = "debate-prod-evidence-moto"
PROFILES = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}
EXPECTED = expected_publish()
EVERY_BODY = sorted({name for week in EXPECTED["snapshots"] for name in week["sources"]})
EXPECTED_KEYS = {expected_source_key(name) for name in EVERY_BODY} | {
    f"manifests/{SYNTHETIC_CASELIST}/{week['snapshot']}.jsonl" for week in EXPECTED["snapshots"]
}


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming different buckets and one shared data directory, fake AWS."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    config.write_text(
        "".join(f"[profile {p}]\nregion = us-east-1\n" for p in PROFILES.values()), encoding="utf-8"
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{p}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for p in PROFILES.values()
        ),
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
    for environment, bucket in (("dev", DEV_BUCKET), ("prod", PROD_BUCKET)):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{data_dir}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            f'aws_profile = "{PROFILES[environment]}"\n'
            f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[providers]\nenabled = []\n[storage]\ndata_dir = "{data_dir}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data_dir


@pytest.fixture
def buckets() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        yield client


@pytest.fixture
def imported(tmp_path: Path, installation: Path) -> Path:
    """The three synthetic weeks, imported through the command an operator runs."""
    zips = build_snapshot_zips(tmp_path / "downloads")
    for week in SNAPSHOTS:
        result = invoke(
            "--json", "caselist", "import", str(zips[week.snapshot]),
            "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
        )  # fmt: skip
        assert result.exit_code == ExitCode.OK, result.stdout
    return installation


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def keys_in(client: S3Client, bucket: str) -> set[str]:
    return {str(item.get("Key")) for item in client.list_objects_v2(Bucket=bucket).get("Contents", [])}


def publish(*extra: str) -> Result:
    return invoke("--json", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST, *extra)


# ------------------------------------------------------------------------------------------------
# ac5: DEBATE_ENV selects the bucket; prod needs --confirm-prod; --dry-run writes nothing
# ------------------------------------------------------------------------------------------------


class TestEnvironments:
    def test_dev_publishes_to_the_dev_bucket_only(self, buckets: S3Client, imported: Path) -> None:
        result = publish()

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["environment"] == "dev"
        assert data["bucket"] == DEV_BUCKET
        assert keys_in(buckets, DEV_BUCKET) == EXPECTED_KEYS
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_prod_is_refused_without_confirm_prod_and_nothing_is_written(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_prod_with_confirm_prod_publishes_to_the_prod_bucket_only(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish("--confirm-prod")

        assert result.exit_code == ExitCode.OK, result.stdout
        assert keys_in(buckets, PROD_BUCKET) == EXPECTED_KEYS
        assert keys_in(buckets, DEV_BUCKET) == set()

    def test_a_prod_dry_run_needs_no_confirmation_and_writes_nothing(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish("--dry-run")

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["applied"] is False
        assert data["planned_uploads"] == EXPECTED["totals"]["source_objects"]
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_the_dry_run_lists_every_planned_upload_per_snapshot(
        self, buckets: S3Client, imported: Path
    ) -> None:
        result = publish("--dry-run")

        data = envelope_of(result)["data"]
        planned = {entry["snapshot"]: entry for entry in data["snapshots"]}
        for week in EXPECTED["snapshots"]:
            entry = planned[week["snapshot"]]
            assert entry["planned"]["upload"] == week["first_publish"]["upload"]
            assert entry["planned"]["uploaded_earlier"] == week["first_publish"]["uploaded_earlier"]
            assert entry["manifest"] == "upload"
        assert keys_in(buckets, DEV_BUCKET) == set()

    def test_the_test_environment_names_no_bucket_and_is_refused(
        self, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "test")

        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "ENVIRONMENT_NOT_SYNCABLE"

    @pytest.mark.parametrize(
        "arguments",
        [("--caselist", "Maple Grove"), ("--caselist", SYNTHETIC_CASELIST, "--snapshot", "0915")],
    )
    def test_names_with_no_place_in_the_layout_are_refused(
        self, buckets: S3Client, arguments: tuple[str, ...]
    ) -> None:
        result = invoke("--json", "caselist", "publish", *arguments)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "INVALID_PUBLISH_TARGET"


# ------------------------------------------------------------------------------------------------
# ac2 and ac3 through the command
# ------------------------------------------------------------------------------------------------


class TestPublishOutcomes:
    def test_a_second_publish_reports_everything_skipped(self, buckets: S3Client, imported: Path) -> None:
        publish()

        result = publish()

        assert result.exit_code == ExitCode.OK
        data = envelope_of(result)["data"]
        assert data["counts"] == {
            "uploaded": 0,
            "skipped": EXPECTED["totals"]["source_objects"],
            "suppressed": 0,
            "failed": 0,
        }
        assert {entry["manifest"] for entry in data["snapshots"]} == {"skipped"}

    def test_a_failed_upload_exits_non_zero_naming_the_sha256_and_withholds_the_manifest(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failing = digest_of_body("ridgeline-round-3-neg")
        real_put = S3EvidenceObjectStore.put_file

        async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
            if key.endswith(failing):
                raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
            return await real_put(self, key, source)

        monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)

        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(result)["error"]
        assert error["code"] == "PUBLISH_INCOMPLETE"
        assert failing in error["message"]
        assert error["details"]["failed_sha256"] == [failing]
        landed = keys_in(buckets, DEV_BUCKET)
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl" not in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" not in landed

    def test_publishing_with_nothing_imported_is_refused(self, buckets: S3Client) -> None:
        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "NOTHING_TO_PUBLISH"


# ------------------------------------------------------------------------------------------------
# ac4: caselist status
# ------------------------------------------------------------------------------------------------


class TestStatus:
    def test_status_before_a_publish_exits_non_zero_with_every_snapshot_reported(
        self, buckets: S3Client, imported: Path
    ) -> None:
        result = invoke("--json", "caselist", "status", "--caselist", SYNTHETIC_CASELIST)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(result)["error"]
        assert error["code"] == "CASELIST_DRIFT"
        reported = {entry["snapshot"]: entry for entry in error["details"]["snapshots"]}
        for week in EXPECTED["snapshots"]:
            entry = reported[week["snapshot"]]
            assert entry["manifest_present"] is False
            assert entry["local_files"] == len(week["sources"])
            assert entry["published_sources"] == 0
            assert sorted(entry["missing_sources"]) == sorted(
                digest_of_body(name) for name in week["sources"]
            )

    def test_status_after_a_publish_exits_zero(self, buckets: S3Client, imported: Path) -> None:
        publish()

        result = invoke("--json", "caselist", "status")

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["in_sync"] is True
        assert [entry["snapshot"] for entry in data["snapshots"]] == [
            week["snapshot"] for week in EXPECTED["snapshots"]
        ]
        for entry in data["snapshots"]:
            assert set(entry) == {
                "caselist", "snapshot", "manifest_key", "in_sync", "local_manifest", "manifest_present",
                "sources", "local_files", "published_sources", "missing_sources", "missing_local",
                "checksum_mismatches", "suppressed",
            }  # fmt: skip

    def test_status_reads_the_bucket_of_its_own_environment(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        publish()
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = invoke("--json", "caselist", "status")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["details"]["bucket"] == PROD_BUCKET

    def test_a_snapshot_without_a_caselist_is_refused(self, buckets: S3Client) -> None:
        result = invoke("--json", "caselist", "status", "--snapshot", "2026-09-15")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE


# ------------------------------------------------------------------------------------------------
# What a person sees
# ------------------------------------------------------------------------------------------------


def test_the_rendered_output_names_nothing_identifying(
    buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Personal-data rule 4, for the text a terminal, a CI log or a scheduled job's log keeps."""
    failing = digest_of_body("bayview-semis-neg")
    real_put = S3EvidenceObjectStore.put_file

    async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
        if key.endswith(failing):
            raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
        return await real_put(self, key, source)

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)
    outputs = [
        invoke("--verbose", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST, "--dry-run"),
        invoke("--verbose", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST),
        invoke("--verbose", "caselist", "status"),
        publish(),
        invoke("--json", "caselist", "status"),
    ]

    text = "\n".join(result.output for result in outputs)
    assert failing in text
    for identifier in FICTIONAL_IDENTIFIERS:
        assert identifier not in text, identifier

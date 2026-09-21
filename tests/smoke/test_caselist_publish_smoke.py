"""`debate-research caselist publish` and `caselist status` end to end, against moto.

The operator's whole path in one check: three synthetic weekly archives imported through the
installed command into a fresh data directory, published to the dev environment's bucket, and then
`caselist status` expected to report every snapshot in agreement. A second publish is expected to
upload nothing. Keys and counts are held to `tests/fixtures/caselist/expected_publish.json`, which
was written by hand from the fixture's tables.

**This check is not marked `live`, and must not be.** It needs no deployed environment: the bucket
is moto's, in-process, and sockets stay disabled. A `live` marker would make the default
`-m "not slow and not live"` run collect it and skip it, so the check that covers publishing the
archive of record would look green in CI while never running. It is marked by what it needs, which
is nothing (tests/smoke/README.md).

Publishing the real September windows to dev and prod is operator-run (`v1-e30-t06`); no real
caselist file enters this repository (`docs/policies/caselist-data-use.md`).
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
from tests.fixtures.caselist.publish_expectations import expected_publish, expected_source_key
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-smoke-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a moto bucket, a fresh data directory, and fake AWS credentials."""
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

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield tmp_path


@pytest.fixture
def bucket(installation: Path) -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield client


def run(*arguments: str) -> dict[str, Any]:
    """Run one command asking for JSON, and return its envelope."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope = json.loads(lines[0])
    assert isinstance(envelope, dict)
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


def test_imported_weeks_publish_to_the_bucket_and_report_a_clean_status(
    installation: Path, bucket: S3Client
) -> None:
    expected = expected_publish()
    zips = build_snapshot_zips(installation / "downloads")
    for week in SNAPSHOTS:
        imported = run(
            "caselist", "import", str(zips[week.snapshot]),
            "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
        )  # fmt: skip
        assert imported["exit_code"] == ExitCode.OK, imported

    before = run("caselist", "status", "--caselist", SYNTHETIC_CASELIST)
    assert before["exit_code"] == ExitCode.DOMAIN_FAILURE, "an unpublished store reported itself in sync"

    published = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)
    assert published["exit_code"] == ExitCode.OK, published
    assert published["data"]["counts"]["uploaded"] == expected["totals"]["source_objects"]
    assert published["data"]["failed_sha256"] == []

    every_body = {name for week in expected["snapshots"] for name in week["sources"]}
    listing = bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    assert {str(item.get("Key")) for item in listing} == {
        expected_source_key(name) for name in every_body
    } | {f"manifests/{SYNTHETIC_CASELIST}/{week['snapshot']}.jsonl" for week in expected["snapshots"]}

    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["in_sync"] is True
    assert len(status["data"]["snapshots"]) == len(expected["snapshots"])

    again = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)
    assert again["exit_code"] == ExitCode.OK
    assert again["data"]["counts"]["uploaded"] == 0
    assert again["data"]["counts"]["skipped"] == expected["totals"]["source_objects"]

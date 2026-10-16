"""`debate-research caselist publish` and `caselist status` end to end, against moto's server.

The operator's whole path in one check, through the installed build: three synthetic weekly
archives imported into a fresh data directory, published to the dev environment's bucket, and then
`caselist status` expected to report every snapshot in agreement. A second publish is expected to
upload nothing. Keys and counts are held to `tests/fixtures/caselist/expected_publish.json`, which
was written by hand from the fixture's tables.

The bucket is moto in server mode, a stand-in the build reaches over loopback through
`storage.s3.endpoint_url` (`v1-e01-t21`, tests/smoke/stand_ins/). Until then this check ran in
pytest's own process under `mock_aws()`, which the installed build could not see; it now runs in
validate-dev's recorded tier against the pre-release. Not marked `live`, and must not be: it needs
no deployed environment, and the build's network guard allows the stand-in and nothing else.

Publishing the real September windows to dev and prod is operator-run (`v1-e30-t06`); no real
caselist file enters this repository (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.caselist.publish_expectations import expected_publish, expected_source_key
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import NETWORK_LOG, InstalledCli
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3StandIn

from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUCKET = "debate-dev-evidence-smoke-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"


@pytest.fixture
def installation(installed_cli: InstalledCli, s3_stand_in: S3StandIn, tmp_path: Path) -> Path:
    """A dev profile naming the stand-in's bucket, and moto's test credentials under its profile."""
    config = tmp_path / "aws-config"
    config.write_text(f"[profile {AWS_PROFILE_NAME}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{AWS_PROFILE_NAME}]\naws_access_key_id = {MOTO_TEST_CREDENTIALS['aws_access_key_id']}\n"
        f"aws_secret_access_key = {MOTO_TEST_CREDENTIALS['aws_secret_access_key']}\n",
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(credentials),
    )
    return tmp_path


@pytest.fixture
def bucket(installation: Path, s3_stand_in: S3StandIn) -> S3Client:
    return s3_stand_in.versioned_bucket(BUCKET)


@pytest.fixture
def run(installed_cli: InstalledCli) -> Any:
    def run(*arguments: str) -> dict[str, Any]:
        """Run one command asking for JSON, and return its envelope with the exit code on it."""
        result = installed_cli.run("--json", *arguments)
        envelope = result.envelope()
        envelope["exit_code"] = result.exit_code
        return envelope

    return run


def test_imported_weeks_publish_to_the_bucket_and_report_a_clean_status(
    installation: Path, bucket: S3Client, run: Any
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


def test_prod_sends_the_evidence_store_to_aws_whatever_endpoint_botocore_is_given(
    installed_cli: InstalledCli, installation: Path, bucket: S3Client, s3_stand_in: S3StandIn, tmp_path: Path
) -> None:
    """`v1-e01-t21`, ac3: no endpoint override reaches prod by a route this project does not control.

    botocore honours `AWS_ENDPOINT_URL`, `AWS_ENDPOINT_URL_S3` and `AWS_ENDPOINT_URL_STS` of its own
    accord. Here all three point at the stand-in, a prod profile names its bucket, and
    `storage.s3.endpoint_url`, which prod would refuse, is unset. A prod installation builds its
    clients with those variables ignored, so the stand-in hears nothing from it, and the request
    goes to AWS instead, where the network guard refuses it and says so in the log.
    """
    (installation / "profiles" / "prod.toml").write_text(
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    provoked = tmp_path / "provoked.log"
    mark = len(s3_stand_in.requests())

    installed_cli.run(
        "--json",
        "caselist",
        "status",
        env={
            "DEBATE_ENV": "prod",
            "DEBATE_STORAGE__S3__ENDPOINT_URL": None,
            "DEBATE_STORAGE__DATA_DIR": str(tmp_path / "prod-data"),
            "AWS_ENDPOINT_URL": s3_stand_in.endpoint,
            "AWS_ENDPOINT_URL_S3": s3_stand_in.endpoint,
            "AWS_ENDPOINT_URL_STS": s3_stand_in.endpoint,
            "AWS_MAX_ATTEMPTS": "1",
            NETWORK_LOG: str(provoked),
        },
    )

    assert s3_stand_in.requests_since(mark) == [], (
        "a prod installation reached the endpoint botocore was given"
    )
    attempts = [json.loads(line) for line in provoked.read_text(encoding="utf-8").splitlines()]
    assert attempts, "the request went nowhere at all"
    assert all("amazonaws.com" in attempt["target"] for attempt in attempts), attempts

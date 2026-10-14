"""`debate-research caselist runs` end to end, against the installed build (`v1-e34-t03`).

A weekly `caselist pull` wired up the way an installation wires it — console script, composition
root, a `dev` settings profile, the real client, importers, manifests and publisher — followed by
`caselist runs`, from the local log and from the bucket. Two stand-ins answer for the world, each a
server the build reaches over loopback (`v1-e01-t21`, tests/smoke/stand_ins/): moto in server mode
for S3, and a local OpenCaselist API and file host serving synthetic responses over https. The
profile names the null notifier, so nothing appears on a screen.

Unmarked, like `test_caselist_pull.py` and for the same reason: a `live` marker would make the
default run collect this and skip it (`tests/smoke/README.md`).

The archives are the invented ones from `tests/fixtures/caselist/`; nothing here is real caselist
content (`docs/policies/caselist-data-use.md`). Three weeklies, a fresh installation: three wanted,
three downloaded, none deferred.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.smoke.installed_build import InstalledCli
from tests.smoke.stand_ins.opencaselist import OpenCaselistStandIn
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3StandIn

from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUCKET = "debate-dev-evidence-runs-moto"

INSTALLED_BUILDS_RECORD = (
    Path(__file__).resolve().parents[2]
    / "packages/debate_core/tests/application/caselist/stored_run_records"
    / "record_schema_of_the_installed_build.json"
)
"""The run record's schema as the build installed for the weekly agent (0.1.0.dev60) printed it."""
AWS_PROFILE_NAME = "debate-dev-evidence"


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


@pytest.fixture
def installation(
    installed_cli: InstalledCli,
    s3_stand_in: S3StandIn,
    opencaselist_stand_in: OpenCaselistStandIn,
    tmp_path: Path,
) -> Path:
    """A dev profile naming the stand-in's bucket and the null notifier, with a token in the environment."""
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
        "allow_network = true\n"
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        "[caselist]\n"
        "api_enabled = true\n"
        'notifier = "none"\n'
        f'sync_caselists = ["{SYNTHETIC_CASELIST}"]\n'
        "min_request_interval_seconds = 0.5\n"
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
        DEBATE_PROVIDERS__CASELIST_TOKEN="fixture-token-not-a-real-one",
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(credentials),
    )
    return tmp_path


@pytest.fixture
def bucket(installation: Path, s3_stand_in: S3StandIn) -> S3Client:
    return s3_stand_in.versioned_bucket(BUCKET)


@pytest.fixture
def site(installation: Path, opencaselist_stand_in: OpenCaselistStandIn) -> OpenCaselistStandIn:
    """Three weekly archives on the file host, listed by the API, and no OpenEv file."""
    zips = build_snapshot_zips(installation / "published")
    listing = [
        {
            "name": weekly_name(week.snapshot),
            "url": opencaselist_stand_in.serve_file(weekly_name(week.snapshot), zips[week.snapshot]),
        }
        for week in SNAPSHOTS
    ]
    opencaselist_stand_in.serve_json(f"/caselists/{SYNTHETIC_CASELIST}/downloads", listing)
    opencaselist_stand_in.serve_json("/openev", [])
    return opencaselist_stand_in


@pytest.fixture
def run(installed_cli: InstalledCli) -> Any:
    def run(*arguments: str) -> dict[str, Any]:
        result = installed_cli.run("--json", *arguments)
        envelope = result.envelope()
        envelope["exit_code"] = result.exit_code
        return envelope

    return run


def test_a_pull_is_listed_by_caselist_runs_locally_and_from_the_bucket(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn, run: Any, installed_cli: InstalledCli
) -> None:
    pulled = run("caselist", "pull")
    assert pulled["exit_code"] == ExitCode.OK
    run_id = pulled["data"]["run_id"]

    local = run("caselist", "runs", "--last", "5")
    remote = run("caselist", "runs", "--last", "5", "--remote")

    for listed in (local, remote):
        assert listed["exit_code"] == ExitCode.OK
        [record] = listed["data"]["runs"]
        assert record["run_id"] == run_id
        assert record["outcome"] == "completed"
        assert (record["archives_wanted"], record["archives_downloaded"], record["archives_deferred"]) == (
            3,
            3,
            0,
        )
        assert record["pending_publish"] == []
    assert remote["data"]["source"] == "bucket"
    key = f"reports/sync-runs/{run_id[:4]}/{run_id}.json"
    assert bucket.head_object(Bucket=BUCKET, Key=key)["ContentLength"] > 0

    # What the record cannot hold is beside it, on this machine and in the bucket, and both
    # listings give it with the run: the parse stage's counts, the same nine the pull printed
    # (v1-e34-t19). The record in the bucket is still one a build installed before that reads.
    counted = pulled["data"]["parse"]
    assert sorted(counted) == [
        "attempted",
        "cards",
        "caselists",
        "failed",
        "full_parses",
        "not_published",
        "skipped",
        "unsupported",
        "uploaded",
    ]
    assert counted["attempted"] > 0
    for listed in (local, remote):
        [record] = listed["data"]["runs"]
        assert record["details"]["run_id"] == run_id
        assert record["details"]["parse"] == counted
        assert record["details"]["failure_codes"] == []
    beside = f"reports/sync-run-details/{run_id[:4]}/{run_id}.json"
    assert json.loads(bucket.get_object(Bucket=BUCKET, Key=beside)["Body"].read())["parse"] == counted
    stored = json.loads(bucket.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    jsonschema.Draft202012Validator(json.loads(INSTALLED_BUILDS_RECORD.read_text("utf-8"))).validate(stored)  # pyright: ignore[reportUnknownMemberType]
    under_the_records = bucket.list_objects_v2(Bucket=BUCKET, Prefix="reports/sync-runs/")["Contents"]
    assert [one["Key"] for one in under_the_records] == [key], "an older build lists this prefix"

    rendered = installed_cli.run("caselist", "runs", env={"COLUMNS": "200"})
    table = " ".join(rendered.stdout.split())
    assert "Parse stage" in table
    assert f"{counted['caselists']} caselist(s), {counted['full_parses']} in full" in table
    assert f"{counted['cards']} card(s)" in table

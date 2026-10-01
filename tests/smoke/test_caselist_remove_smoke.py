"""`debate-research caselist remove` and `unsuppress` end to end, against moto.

The operator's whole takedown in one check, through the installed command: three synthetic weeks
imported and published to the dev bucket, a team's removal planned (and shown to change nothing),
refused without the takedown profile, executed with it, checked with `caselist status`, and then
attacked the way the world will attack it — next Monday's cumulative archive imported and published
— without the team's files coming back. Then a mistaken removal reversed with `unsuppress`.

**Not marked `live`, and must not be.** It needs no deployed environment: the bucket is moto's,
in-process, with sockets disabled (tests/smoke/README.md). Exercising the runbook against the real
dev bucket is an operator step (session report, Operator follow-ups).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-smoke-moto"
OPERATOR_PROFILE = "debate-dev-evidence"
REMOVAL_PROFILE = "debate-dev-evidence-removal"
TEAM = f"{SYNTHETIC_CASELIST}/Maple Grove/QX"
REMOVE = ("caselist", "remove", "--team", TEAM, "--request", "RM-2026-01", "--reason", "REQUESTED_BY_TEAM")
EXCLUSIVE = {
    hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()
    for body in ("grove-round-2-neg-first", "grove-round-2-neg-revised", "bayview-semis-neg")
}
BAYVIEW = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming a moto bucket, both SSO profiles, and fake AWS credentials."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    credentials = tmp_path / "aws-credentials"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)
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

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment in ("dev", "prod"):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{tmp_path / environment}"\n'
            f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{OPERATOR_PROFILE}"\n'
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
    """Run one command asking for JSON, and return its envelope with the exit code."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope = json.loads(lines[0])
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


def versions(client: S3Client) -> list[tuple[str, str]]:
    listed = client.list_object_versions(Bucket=BUCKET)
    return sorted((str(v.get("Key")), str(v.get("VersionId"))) for v in listed.get("Versions", []))


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "sqlite3" not in path.name
    }


@pytest.fixture
def published(installation: Path, bucket: S3Client) -> dict[date, Path]:
    zips = build_snapshot_zips(installation / "downloads")
    for week in SNAPSHOTS:
        imported = run(
            "caselist", "import", str(zips[week.snapshot]),
            "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
        )  # fmt: skip
        assert imported["exit_code"] == ExitCode.OK, imported
    assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK
    assert run("caselist", "status")["exit_code"] == ExitCode.OK
    return zips


def test_a_team_is_removed_and_next_weeks_archive_does_not_bring_it_back(
    installation: Path,
    bucket: S3Client,
    published: dict[date, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = installation / "dev"

    # The dry run: the whole plan, and nothing changed anywhere.
    before = (tree(data_dir), versions(bucket))
    planned = run(*REMOVE)
    assert planned["exit_code"] == ExitCode.OK, planned
    assert planned["data"]["applied"] is False
    assert planned["data"]["counts"] == {"remove": 3, "withdraw": 1, "skip_shared": 0, "local_records": 12}
    assert len(planned["data"]["suppression_entries"]) == 5
    assert (tree(data_dir), versions(bucket)) == before

    # --execute without the takedown profile: refused before anything changes.
    refused = run(*REMOVE, "--execute")
    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert "DEBATE_REMOVAL_PROFILE" in refused["error"]["message"]
    assert (tree(data_dir), versions(bucket)) == before

    # With it: done, and `caselist status` agrees with the bucket.
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    done = run(*REMOVE, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert done["data"]["outcome"] == "COMPLETED"
    keys = {key for key, _ in versions(bucket)}
    for sha in EXCLUSIVE:
        assert not any(sha in key for key in keys)
    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status

    # Next Monday: the same cumulative archive, in order. Nothing of the team's comes back.
    reimported = run(
        "caselist", "import", str(published[SNAPSHOTS[-1].snapshot]),
        "--caselist", SYNTHETIC_CASELIST, "--snapshot", "2026-09-22",
    )  # fmt: skip
    assert reimported["exit_code"] == ExitCode.OK, reimported
    assert reimported["data"]["counts"]["SUPPRESSED"] == 4
    manifest = (data_dir / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-22.jsonl").read_text()
    assert "Maple Grove" not in manifest
    published_again = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)
    assert published_again["exit_code"] == ExitCode.OK, published_again
    keys = {key for key, _ in versions(bucket)}
    for sha in EXCLUSIVE:
        assert not any(sha in key for key in keys)
    assert run("caselist", "status")["exit_code"] == ExitCode.OK

    # The list and the log, in both copies, name no one.
    bucket_list = bucket.get_object(Bucket=BUCKET, Key="manifests/_suppression/suppression-list.jsonl")[
        "Body"
    ].read()
    bucket_log = bucket.get_object(Bucket=BUCKET, Key="manifests/_suppression/removal-log.jsonl")[
        "Body"
    ].read()
    for text in (
        bucket_list.decode(),
        bucket_log.decode(),
        (data_dir / "suppression" / "removal-log.jsonl").read_text(),
    ):
        for name in ("Maple Grove", "QX", "Cedar Hollow", "ZaLu", "Grove City"):
            assert name not in text
    assert len(bucket_log.decode().splitlines()) == 1


def test_the_dry_run_reads_as_a_plan_for_a_person(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    result = runner.invoke(create_app(), list(REMOVE))

    assert result.exit_code == ExitCode.OK, result.stdout
    for heading in (
        "DRY RUN: nothing was changed.",
        "WILL BE REMOVED, everywhere, and suppressed: 3 file(s)",
        "SHARED, KEPT: 1 file(s)",
        "MANIFESTS REWRITTEN",
        "SUPPRESSION ENTRIES appended to the list, here and in the bucket: 5",
        "FOR THE CONFIRMATION TO THE REQUESTER",
        "TO CARRY IT OUT",
        "DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal",
    ):
        assert heading in result.stdout, heading


def test_prod_is_refused_without_confirm_prod(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-prod-evidence-removal")

    refused = run(*REMOVE, "--execute")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_a_mistaken_removal_is_reversed_and_the_file_is_imported_again(
    installation: Path, bucket: S3Client, published: dict[date, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    removed = run(
        "caselist",
        "remove",
        "--source",
        BAYVIEW,
        "--request",
        "RM-2026-02",
        "--reason",
        "POLICY",
        "--execute",
    )
    assert removed["exit_code"] == ExitCode.OK, removed
    listed = installation / "dev" / "suppression" / "suppression-list.jsonl"
    before = listed.read_bytes()

    planned = run("caselist", "unsuppress", "--sha256", BAYVIEW, "--reason", "REMOVED_IN_ERROR")
    assert planned["exit_code"] == ExitCode.OK and planned["data"]["applied"] is False
    assert listed.read_bytes() == before
    lifted = run("caselist", "unsuppress", "--sha256", BAYVIEW, "--reason", "REMOVED_IN_ERROR", "--execute")
    assert lifted["exit_code"] == ExitCode.OK, lifted
    assert listed.read_bytes().startswith(before) and listed.read_bytes() != before

    reimported = run(
        "caselist", "import", str(published[SNAPSHOTS[-1].snapshot]),
        "--caselist", SYNTHETIC_CASELIST, "--snapshot", "2026-09-22",
    )  # fmt: skip
    assert reimported["data"]["counts"]["SUPPRESSED"] == 0
    assert (installation / "dev" / "blobs" / "sha256" / BAYVIEW[0:2] / BAYVIEW[2:4] / BAYVIEW).exists()


def test_a_sha256_held_nowhere_is_planned_as_a_suppression_only(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """The runbook's manual-procedure backfill: hashes recorded before this command existed."""
    unknown = "0" * 64
    result = runner.invoke(
        create_app(),
        ["caselist", "remove", "--source", unknown, "--request", "RM-2026-04", "--reason", "POLICY"],
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    assert "held nowhere in this environment: it is only suppressed" in result.stdout
    assert "SUPPRESSION ENTRIES appended to the list, here and in the bucket: 1" in result.stdout

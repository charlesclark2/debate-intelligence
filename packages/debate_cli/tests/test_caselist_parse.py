"""`debate-research caselist parse`, through the real application, composition root and process pool.

The fictional caselist of `tests/fixtures/parse_pipeline/build_parse_world.py` is imported through
`caselist import`, as an operator imports a week, and parsed with one worker so each run starts one
process. Expected counts are the fixture's hand-written :data:`EXPECTED`. The bucket is moto's.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import (
    CASELIST,
    EXPECTED,
    WEEKS,
    build_week_zips,
    digest_of,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

DEV_BUCKET: Final = "debate-dev-evidence-moto"
PROD_BUCKET: Final = "debate-prod-evidence-moto"
PROFILES: Final = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming different buckets and one data directory, fake AWS, one worker."""
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
    monkeypatch.setenv("DEBATE_PARSE__WORKERS", "1")
    monkeypatch.setenv("DEBATE_PARSE__FAILURE_RATE_THRESHOLD", "0.3")
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
    """09-01 and 09-08, imported through the command an operator runs."""
    zips = build_week_zips(tmp_path / "downloads")
    for week in WEEKS[:2]:
        result = invoke(
            "--json", "caselist", "import", str(zips[week.snapshot]),
            "--caselist", CASELIST, "--snapshot", week.snapshot.isoformat(),
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


def test_a_run_reports_the_hand_derived_counts_and_exits_zero_under_the_threshold(imported: Path) -> None:
    result = invoke("caselist", "parse", "--caselist", CASELIST, "--json")

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    expected = EXPECTED["after_0908"]
    assert (data["sources"], data["parsed"], data["cards"]) == (
        expected["sources"],
        expected["parsed"],
        expected["cards"],
    )
    assert (data["unsupported"], data["failed"], data["failure_rate"]) == (
        expected["unsupported"],
        expected["failed"],
        expected["failure_rate"],
    )
    assert data["store"]["occurrences"] == expected["occurrences"]
    assert data["version"] == DOCX_PARSER_VERSION
    assert data["workers"] == 1
    assert data["publish"] is None


def test_a_second_run_parses_nothing_and_reports_every_source_skipped(imported: Path) -> None:
    invoke("caselist", "parse", "--caselist", CASELIST)
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    assert (data["attempted"], data["parsed"], data["skipped"]) == (0, 0, EXPECTED["after_0908"]["sources"])


def test_a_failure_rate_above_the_threshold_exits_non_zero_with_the_counts(
    imported: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PARSE__FAILURE_RATE_THRESHOLD", "0.2")
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSE_FAILURE_RATE_EXCEEDED"
    assert error["details"]["failure_rate"] == 0.25
    assert error["details"]["parsed"] == EXPECTED["after_0908"]["parsed"]


def test_a_dry_run_counts_and_writes_nothing(imported: Path) -> None:
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--dry-run")

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    assert (data["applied"], data["to_parse"], data["attempted"]) == (
        False,
        EXPECTED["after_0908"]["sources"],
        0,
    )
    assert not (imported / "parsed").exists()


def test_reparse_writes_a_new_version_directory(imported: Path) -> None:
    invoke("caselist", "parse", "--caselist", CASELIST)
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--reparse")

    data = envelope_of(result)["data"]
    assert (data["version"], data["new_version"], data["superseded"]) == (
        f"{DOCX_PARSER_VERSION}_reparse-2",
        True,
        DOCX_PARSER_VERSION,
    )
    assert data["parsed"] == EXPECTED["after_0908"]["parsed"]


def test_failures_lists_each_source_by_digest_prefix_and_path_and_says_it_holds_paths(imported: Path) -> None:
    invoke("caselist", "parse", "--caselist", CASELIST)

    shown = invoke("caselist", "parse", "--caselist", CASELIST, "--failures")
    listed = envelope_of(invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--failures"))["data"]

    assert shown.exit_code == ExitCode.OK
    paths = {body: path for week in WEEKS[:2] for path, body in week.members}
    for body in ("broken", "pdf", "doc"):
        assert digest_of(body)[:12] in shown.stdout
    assert {(row["sha256"], row["path"], row["reason"]) for row in listed["failures"]} == {
        (digest_of("broken"), paths["broken"], "NOT_A_ZIP"),
        (digest_of("pdf"), paths["pdf"], "UNSUPPORTED_FORMAT"),
        (digest_of("doc"), paths["doc"], "UNSUPPORTED_FORMAT"),
    }
    assert listed["contains_disclosure_paths"] is True
    assert "school" in listed["notice"]


def test_nothing_but_failures_prints_a_school_a_team_or_a_path(imported: Path) -> None:
    outputs = [
        invoke("caselist", "parse", "--caselist", CASELIST).stdout,
        invoke("--verbose", "caselist", "parse", "--caselist", CASELIST).stdout,
        invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--reparse").stdout,
        invoke("caselist", "parse", "--caselist", CASELIST, "--dry-run").stdout,
    ]
    for output in outputs:
        for identifier in FICTIONAL_IDENTIFIERS:
            assert identifier not in output


def test_publish_uploads_the_store_and_a_rerun_uploads_nothing(imported: Path, buckets: S3Client) -> None:
    first = envelope_of(invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish"))["data"][
        "publish"
    ]
    second = envelope_of(invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish"))["data"][
        "publish"
    ]

    files = sorted(path for path in (imported / "parsed").rglob("*") if path.is_file())
    keys = {str(item.get("Key")) for item in buckets.list_objects_v2(Bucket=DEV_BUCKET).get("Contents", [])}
    assert keys == {f"parsed/{path.relative_to(imported / 'parsed').as_posix()}" for path in files}
    assert first["counts"]["uploaded"] == len(files)
    assert (second["counts"]["uploaded"], second["counts"]["skipped"]) == (0, len(files))
    assert first["prefix"] == f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/"
    assert "Contents" not in buckets.list_objects_v2(Bucket=PROD_BUCKET)


def test_publishing_to_prod_needs_confirm_prod_and_writes_nothing_without_it(
    imported: Path, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    refused = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish")

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(refused)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert "Contents" not in buckets.list_objects_v2(Bucket=PROD_BUCKET)
    assert not (imported / "parsed").exists()

    confirmed = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish", "--confirm-prod")
    assert confirmed.exit_code == ExitCode.OK, confirmed.stdout
    assert buckets.list_objects_v2(Bucket=PROD_BUCKET)["KeyCount"] > 0


def test_publishing_from_test_is_refused(imported: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_ENV", "test")
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(result)["error"]["code"] == "ENVIRONMENT_NOT_SYNCABLE"


def test_a_caselist_that_is_not_a_slug_is_refused(imported: Path) -> None:
    result = invoke("--json", "caselist", "parse", "--caselist", "Maple Grove")
    assert result.exit_code != ExitCode.OK

"""`debate-research caselist parse --publish-only`, through the real application and composition root.

`v1-e31-t30`. The installation of `test_caselist_parse.py`: dev and prod profiles naming two moto
buckets over one data directory, as the operator publishes prod from dev's store. What each test
holds the command to:

* ac1: after `--publish` to dev, `--publish-only` to prod sends the same objects, byte for byte,
  reports them under the same `publish` object, and rewrites nothing on this machine; again to dev,
  it uploads nothing.
* ac2: a directory it may not publish is refused with its code and a hint naming `--publish`, and
  nothing reaches the bucket.
* ac4: dev's store sent to prod, whose bucket's suppression list holds a removal or a path hold
  dev's lacks, is refused, and nothing reaches prod's `parsed/`.
* `--publish` and every option that only shapes a rebuild are refused beside it, before anything
  is read or written; so is `--failures`. `--publish`'s guards are its guards.
* An incomplete publish, either way, says to retry with `--publish-only`.
* Nothing it prints names a school, a team code or a path.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS, build_week_zips, digest_of
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.suppression import PATH_HOLDS_KEY, SUPPRESSION_LIST_KEY
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.s3 import S3EvidenceObjectStore

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
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[providers]\nenabled = []\n[storage]\ndata_dir = "{data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 0.0\n',
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


@pytest.fixture
def published_to_dev(imported: Path, buckets: S3Client) -> dict[str, Any]:
    """`caselist parse --publish` to dev: the rebuild, and its publish's `publish` object."""
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish")
    assert result.exit_code == ExitCode.OK, result.stdout
    return envelope_of(result)["data"]["publish"]


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def publish_only(*extra: str) -> Result:
    return invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish-only", *extra)


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def bucket_objects(client: S3Client, bucket: str) -> dict[str, bytes]:
    listed = client.list_objects_v2(Bucket=bucket).get("Contents", [])
    return {
        str(item.get("Key")): client.get_object(Bucket=bucket, Key=str(item.get("Key")))["Body"].read()
        for item in listed
    }


def written(data_dir: Path) -> dict[str, tuple[bytes, int]]:
    """Every file of the parsed store, with when it was last written: a rebuild rewrites the aggregates."""
    root = data_dir / "parsed"
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def without_bucket(publish: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in publish.items() if name != "bucket"}


# ------------------------------------------------------------------------------------------------
# ac1: the same objects as `--publish`, without the rebuild
# ------------------------------------------------------------------------------------------------


def test_publish_only_to_prod_sends_what_publish_sent_to_dev_and_reports_it_alike(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = written(imported)
    monkeypatch.setenv("DEBATE_ENV", "prod")

    result = publish_only("--confirm-prod")

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    assert bucket_objects(buckets, PROD_BUCKET) == bucket_objects(buckets, DEV_BUCKET)
    assert without_bucket(data["publish"]) == without_bucket(published_to_dev)
    assert (data["publish"]["bucket"], published_to_dev["bucket"]) == (PROD_BUCKET, DEV_BUCKET)
    assert data["publish_only"] is True
    assert (data["caselist"], data["version"]) == (CASELIST, DOCX_PARSER_VERSION)
    assert written(imported) == before


def test_publish_only_over_what_dev_already_holds_uploads_nothing(
    imported: Path, published_to_dev: dict[str, Any]
) -> None:
    """The operator's after-merge check: `--publish-only` over the current version, 0 uploaded."""
    result = publish_only()

    assert result.exit_code == ExitCode.OK, result.stdout
    counts = envelope_of(result)["data"]["publish"]["counts"]
    assert (counts["uploaded"], counts["skipped"]) == (0, published_to_dev["counts"]["uploaded"])


def test_the_table_says_nothing_was_rebuilt_and_names_no_school_team_or_path(
    imported: Path, published_to_dev: dict[str, Any]
) -> None:
    result = invoke("caselist", "parse", "--caselist", CASELIST, "--publish-only")

    assert result.exit_code == ExitCode.OK, result.output
    flat = " ".join(result.output.split())
    assert "Nothing was parsed or rebuilt" in flat
    assert "0 uploaded" in flat
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in result.output


# ------------------------------------------------------------------------------------------------
# ac2: refused, with its code and reason, before any upload
# ------------------------------------------------------------------------------------------------


def test_a_caselist_never_parsed_is_refused_and_nothing_is_uploaded(
    imported: Path, buckets: S3Client
) -> None:
    result = publish_only()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSED_VERSION_DIRECTORY_MISSING"
    assert error["hint"] == (
        f"`debate-research caselist parse --caselist {CASELIST} --publish` rebuilds the directory, "
        "then publishes it."
    )
    assert "Contents" not in buckets.list_objects_v2(Bucket=DEV_BUCKET)


def test_a_directory_a_removal_left_without_aggregates_is_refused_and_nothing_is_uploaded(
    imported: Path, buckets: S3Client
) -> None:
    assert invoke("--json", "caselist", "parse", "--caselist", CASELIST).exit_code == ExitCode.OK
    for name in ("index.jsonl", "failures.jsonl", "occurrences.jsonl"):
        (imported / "parsed" / CASELIST / DOCX_PARSER_VERSION / name).unlink()

    result = publish_only()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSED_AGGREGATES_MISSING"
    assert (error["details"]["caselist"], error["details"]["version"]) == (CASELIST, DOCX_PARSER_VERSION)
    assert "Contents" not in buckets.list_objects_v2(Bucket=DEV_BUCKET)
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in result.stdout


# ------------------------------------------------------------------------------------------------
# The options it refuses beside it, and the guards it shares
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "beside",
    [("--publish",), ("--reparse",), ("--snapshot", "2026-09-01"), ("--dry-run",), ("--failures",)],
    ids=["publish", "reparse", "snapshot", "dry-run", "failures"],
)
def test_an_option_publish_only_has_no_use_for_is_refused_before_anything_runs(
    imported: Path, buckets: S3Client, beside: tuple[str, ...]
) -> None:
    result = publish_only(*beside)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.stdout
    error = envelope_of(result)["error"]
    assert error["code"] == "USAGE_ERROR"
    assert (
        "--publish-only publishes the directory the last rebuild left, so it cannot be combined with "
        f"{beside[0]}: {beside[0]} "
    ) in error["message"]
    assert error["message"].endswith("; pass one or the other")
    assert not (imported / "parsed").exists()
    assert "Contents" not in buckets.list_objects_v2(Bucket=DEV_BUCKET)


def test_publish_only_to_prod_needs_confirm_prod(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")

    result = publish_only()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(result)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert "Contents" not in buckets.list_objects_v2(Bucket=PROD_BUCKET)


def test_publish_only_from_test_is_refused(imported: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_ENV", "test")

    result = publish_only()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(result)["error"]["code"] == "ENVIRONMENT_NOT_SYNCABLE"


# ------------------------------------------------------------------------------------------------
# An incomplete publish names the retry that does not rebuild
# ------------------------------------------------------------------------------------------------


def unavailable_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
        raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", unavailable)


RETRY_HINT: Final = (
    f"`debate-research caselist parse --caselist {CASELIST} --publish-only` retries the publish "
    "without rebuilding; a checksum mismatch needs a person."
)


def test_a_publish_that_failed_after_its_rebuild_says_to_retry_with_publish_only(
    imported: Path, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    unavailable_bucket(monkeypatch)

    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert (error["code"], error["hint"]) == ("PARSED_PUBLISH_INCOMPLETE", RETRY_HINT)


def test_an_incomplete_publish_only_reports_as_an_incomplete_publish_does(
    imported: Path, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert invoke("--json", "caselist", "parse", "--caselist", CASELIST).exit_code == ExitCode.OK
    unavailable_bucket(monkeypatch)

    result = publish_only()

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert (error["code"], error["hint"]) == ("PARSED_PUBLISH_INCOMPLETE", RETRY_HINT)
    publish = error["details"]["publish"]
    assert (publish["aggregates"], publish["failure_codes"]) == ("withheld", ["STORE_UNAVAILABLE"])
    assert "Contents" not in buckets.list_objects_v2(Bucket=DEV_BUCKET)


# ------------------------------------------------------------------------------------------------
# ac4: prod's list holds what dev's aggregates were rebuilt without
# ------------------------------------------------------------------------------------------------

RECORDED: Final = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
REMOVED: Final = hashlib.sha256(b"a removed file no snapshot of this store holds").hexdigest()


def plant(client: S3Client, key: str, *lines: str) -> None:
    """Record `lines` in prod's bucket alone, as a removal made against prod leaves them."""
    client.put_object(Bucket=PROD_BUCKET, Key=key, Body="".join(f"{line}\n" for line in lines).encode())


def parsed_in_prod(client: S3Client) -> list[str]:
    listed = client.list_objects_v2(Bucket=PROD_BUCKET, Prefix="parsed/").get("Contents", [])
    return [str(item.get("Key")) for item in listed]


def test_a_removal_only_prods_list_holds_is_refused_and_prod_gets_nothing(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    removal = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest_of("wiki"),
        recorded_at=RECORDED,
        reason=ReasonCode.POLICY,
        request_id="RM-2026-91",
    )
    plant(buckets, SUPPRESSION_LIST_KEY, removal.to_line())
    monkeypatch.setenv("DEBATE_ENV", "prod")

    result = publish_only("--confirm-prod")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS"
    assert f"(sha256 {digest_of('wiki')[:12]})" in error["message"]
    assert error["hint"] == (
        f"`debate-research caselist parse --caselist {CASELIST} --publish` rebuilds the aggregates "
        "from this environment's suppression list, then publishes them."
    )
    assert parsed_in_prod(buckets) == []
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in result.stdout


def test_a_path_hold_only_prods_list_holds_is_refused_and_prod_gets_nothing(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    held_path = next(path for path, body in WEEKS[1].members if body == "cardmirror")
    removal = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=REMOVED,
        recorded_at=RECORDED,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-72",
    )
    hold = PathHoldEntry(
        caselist=CASELIST,
        disclosure=disclosure_digest(CASELIST, held_path),
        sha256=REMOVED,
        after_snapshot=date(2026, 9, 1),
        recorded_at=RECORDED,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-72",
    )
    plant(buckets, SUPPRESSION_LIST_KEY, removal.to_line())
    plant(buckets, PATH_HOLDS_KEY, hold.to_line())
    monkeypatch.setenv("DEBATE_ENV", "prod")

    result = publish_only("--confirm-prod")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS"
    assert "(1 of the sources only at a path a removal holds)" in error["message"]
    assert parsed_in_prod(buckets) == []
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in result.stdout

"""`debate-research caselist retire`, through the real composition root (`v1-e31-t16`).

The data directory and moto's buckets are filled by hand with version directories named for parser
versions around the build's own (:data:`DOCX_PARSER_VERSION`), so the current directory is the
one the installed parser writes. No file holds anything from a real store.
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
CASELIST: Final = "testcl26"
OLDER: Final = "2026.01.01-docx-0"
NEWER: Final = "2099.01.01-docx-99"
FILES: Final = {"sha256/ab/cd/abcd01.jsonl": b'{"record":"source"}\n', "index.jsonl": b"{}\n"}


@pytest.fixture(autouse=True)
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles over one data directory and moto-named buckets, with fake AWS."""
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
    data = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment, bucket in (("dev", DEV_BUCKET), ("prod", PROD_BUCKET)):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{data}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            f'aws_profile = "{PROFILES[environment]}"\n'
            f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    for version in (OLDER, DOCX_PARSER_VERSION):
        for name, content in FILES.items():
            path = data / "parsed" / CASELIST / version / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    yield data


@pytest.fixture
def buckets() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
            for version in (OLDER, DOCX_PARSER_VERSION):
                for name, content in FILES.items():
                    client.put_object(Bucket=bucket, Key=f"parsed/{CASELIST}/{version}/{name}", Body=content)
        yield client


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def tree(data_dir: Path) -> list[str]:
    root = data_dir / "parsed"
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def tags(client: S3Client, bucket: str) -> dict[str, list[tuple[str, str]]]:
    keys = [
        item.get("Key", "")
        for item in client.list_objects_v2(Bucket=bucket, Prefix="parsed/").get("Contents", [])
    ]
    return {
        key: [
            (tag["Key"], tag["Value"]) for tag in client.get_object_tagging(Bucket=bucket, Key=key)["TagSet"]
        ]
        for key in keys
    }


def test_the_dry_run_lists_each_directory_with_its_standing_and_changes_nothing(data_dir: Path) -> None:
    before = tree(data_dir)

    result = invoke("--json", "caselist", "retire")

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    assert (data["location"], data["method"], data["applied"]) == ("this machine", "delete", False)
    assert [
        (row["version"], row["standing"], row["objects"], row["selected"]) for row in data["directories"]
    ] == [
        (OLDER, "superseded", len(FILES), True),
        (DOCX_PARSER_VERSION, "current", len(FILES), False),
    ]
    assert tree(data_dir) == before


def test_a_named_dry_run_prints_the_command_that_carries_it_out(data_dir: Path) -> None:
    shown = invoke("caselist", "retire", "--version", OLDER)
    code = envelope_of(invoke("--json", "caselist", "retire", "--version", OLDER))["data"]["confirmation"]

    assert shown.exit_code == ExitCode.OK, shown.stdout
    assert f"--execute --confirm {code}" in " ".join(shown.stdout.split())


def test_execute_with_the_dry_runs_code_deletes_the_superseded_directory_and_keeps_the_current(
    data_dir: Path,
) -> None:
    code = envelope_of(invoke("--json", "caselist", "retire", "--version", OLDER))["data"]["confirmation"]

    result = invoke("--json", "caselist", "retire", "--version", OLDER, "--execute", "--confirm", code)

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    assert data["acted_on"] == [{"caselist": CASELIST, "version": OLDER, "objects": len(FILES)}]
    assert tree(data_dir) == sorted(f"{CASELIST}/{DOCX_PARSER_VERSION}/{name}" for name in FILES)


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (("--version", OLDER, "--execute"), "CONFIRMATION_MISMATCH"),
        (("--version", OLDER, "--execute", "--confirm", "0123456789ab"), "CONFIRMATION_MISMATCH"),
        (("--execute", "--confirm", "0123456789ab"), "VERSION_NOT_NAMED"),
        (("--version", DOCX_PARSER_VERSION), "CURRENT_VERSION_DIRECTORY"),
        (("--version", NEWER), "NO_SUCH_VERSION_DIRECTORY"),
    ],
)
def test_a_refused_plan_exits_one_with_its_reason_and_changes_nothing(
    data_dir: Path, arguments: tuple[str, ...], code: str
) -> None:
    before = tree(data_dir)

    result = invoke("--json", "caselist", "retire", *arguments)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    assert envelope_of(result)["error"]["code"] == code
    assert tree(data_dir) == before


def test_the_current_directory_is_refused_whatever_code_is_given(data_dir: Path) -> None:
    before = tree(data_dir)

    result = invoke(
        "--json", "caselist", "retire", "--version", DOCX_PARSER_VERSION,
        "--execute", "--confirm", "0123456789ab",
    )  # fmt: skip

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert (error["code"], error["details"]["refusals"]) == (
        "CURRENT_VERSION_DIRECTORY",
        ["CURRENT_VERSION_DIRECTORY"],
    )
    assert tree(data_dir) == before


def test_in_the_bucket_retiring_tags_the_superseded_directory_and_restoring_undoes_it(
    buckets: S3Client,
) -> None:
    code = envelope_of(invoke("--json", "caselist", "retire", "--bucket", "--version", OLDER))["data"][
        "confirmation"
    ]

    retired = invoke(
        "--json", "caselist", "retire", "--bucket", "--version", OLDER, "--execute", "--confirm", code
    )

    assert retired.exit_code == ExitCode.OK, retired.stdout
    assert envelope_of(retired)["data"]["location"] == f"s3://{DEV_BUCKET}"
    assert tags(buckets, DEV_BUCKET) == {
        f"parsed/{CASELIST}/{version}/{name}": (
            [("debate-retention", "superseded")] if version == OLDER else []
        )
        for version in (OLDER, DOCX_PARSER_VERSION)
        for name in FILES
    }
    assert all(not tagged for tagged in tags(buckets, PROD_BUCKET).values())

    undo = envelope_of(invoke("--json", "caselist", "retire", "--bucket", "--version", OLDER, "--restore"))
    restored = invoke(
        "--json", "caselist", "retire", "--bucket", "--version", OLDER, "--restore",
        "--execute", "--confirm", undo["data"]["confirmation"],
    )  # fmt: skip

    assert restored.exit_code == ExitCode.OK, restored.stdout
    assert {key: value for key, value in tags(buckets, DEV_BUCKET).items() if f"/{OLDER}/" in key} == {
        f"parsed/{CASELIST}/{OLDER}/{name}": [("debate-retention", "restored")] for name in FILES
    }


def test_changing_prod_needs_confirm_prod(buckets: S3Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    code = envelope_of(invoke("--json", "caselist", "retire", "--bucket", "--version", OLDER))["data"][
        "confirmation"
    ]

    refused = invoke(
        "--json", "caselist", "retire", "--bucket", "--version", OLDER, "--execute", "--confirm", code
    )
    confirmed = invoke(
        "--json", "caselist", "retire", "--bucket", "--version", OLDER,
        "--execute", "--confirm", code, "--confirm-prod",
    )  # fmt: skip

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(refused)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert confirmed.exit_code == ExitCode.OK, confirmed.stdout
    assert envelope_of(confirmed)["data"]["location"] == f"s3://{PROD_BUCKET}"

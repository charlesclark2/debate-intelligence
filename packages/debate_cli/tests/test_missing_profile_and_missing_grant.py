"""Two bucket failures no login fixes, command family by command family (`v1-e29-t07`).

* **A profile the AWS config does not define.** The environment's profile setting, or
  `DEBATE_REMOVAL_PROFILE`, names a profile this machine's AWS config lacks, so boto3 refuses to
  build a session. That used to be reported as an expired session: exit 3, "a retry may succeed",
  with a command to run. It is a configuration error: exit 1, under its own code, and what it
  names is the setting that holds the profile's name.
* **A bucket that refuses the profile.** The session is signed in and the bucket answers
  `AccessDenied`. That keeps its code and its exit 3; what changes is that every command says
  what it means, a grant the profile lacks, where only `caselist pull` did.

Both go through the real application, composition root and S3 adapter. boto3 reads an AWS config
written for the test, which is how the missing profile is met for real, and botocore is made to
answer `AccessDenied` the way S3 does. Nothing reads the config of the machine the suite runs on,
and nothing reaches AWS. `caselist pull` is in `tests/smoke/test_caselist_pull.py`, beside the site
it needs, and an expired session's exit 3 is in `test_retryable_store_failures.py`, unchanged.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-profile-moto"
EVERYDAY_PROFILE = "debate-dev-evidence"
TAKEDOWN_PROFILE = "debate-dev-evidence-removal"
MISSPELT_PROFILE = "debate-dev-evidence-typo"
EVERYDAY_SETTING = "storage.s3.aws_profile"
TAKEDOWN_SETTING = "DEBATE_REMOVAL_PROFILE"
RUNBOOK = "docs/runbooks/evidence-store.md"
AWS_CONFIG_NAME = "an-aws-config-written-for-this-test"

REMOVE = (
    "caselist", "remove", "--source", "0" * 64,
    "--request", "RM-2026-01", "--reason", "REQUESTED_BY_TEAM",
)  # fmt: skip


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a moto bucket, and an AWS config that defines both evidence profiles."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / AWS_CONFIG_NAME
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (EVERYDAY_PROFILE, TAKEDOWN_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for name in (EVERYDAY_PROFILE, TAKEDOWN_PROFILE)
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
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{EVERYDAY_PROFILE}"\n'
        f'[caselist]\nnotifier = "none"\n'
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
        # Each profile is the role its name says: a takedown asks before it does anything (v1-e29-t08).
        sign_in(
            installation / "aws-credentials",
            {EVERYDAY_PROFILE: EVERYDAY_ROLE, TAKEDOWN_PROFILE: TAKEDOWN_ROLE},
        )
        yield client


def run(*arguments: str) -> tuple[int, dict[str, Any]]:
    """Run one command with `--json`; return its exit code and its one envelope."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    assert envelope["error"] is None or envelope["error"]["exit_code"] == result.exit_code
    return result.exit_code, envelope


def import_the_first_week(installation: Path) -> None:
    week = SNAPSHOTS[0]
    archive = build_snapshot_zips(installation / "downloads")[week.snapshot]
    exit_code, envelope = run(
        "caselist", "import", str(archive),
        "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
    )  # fmt: skip
    assert exit_code == ExitCode.OK, envelope


def every_version_in(client: S3Client) -> list[tuple[str, str]]:
    """Every (key, version id) in the bucket, delete markers included."""
    listed = client.list_object_versions(Bucket=BUCKET)
    return sorted(
        (str(entry.get("Key")), str(entry.get("VersionId")))
        for entry in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
    )


def everything_under(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "sqlite3" not in path.name
    }


# ------------------------------------------------------------------------------------------------
# A profile the AWS config does not define
# ------------------------------------------------------------------------------------------------


def assert_a_profile_that_is_not_configured(
    exit_code: int, envelope: dict[str, Any], *, setting: str, installation: Path
) -> None:
    """1, under its own code, naming the profile and the setting it came from, and no way to the
    AWS config: not its path, and not a command that would write to it or log in to it."""
    assert exit_code == ExitCode.DOMAIN_FAILURE, envelope
    error = envelope["error"]
    assert error["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert error["message"].startswith(
        f"AWS profile {MISSPELT_PROFILE!r}, named by {setting}, is not defined"
    )
    assert setting in error["hint"]
    assert RUNBOOK in error["hint"]
    assert error["details"] == {"profile": MISSPELT_PROFILE, "setting": setting}
    said = json.dumps(envelope)
    assert "aws sso login" not in said
    assert "aws configure" not in said
    assert str(installation) not in said
    assert AWS_CONFIG_NAME not in said
    assert str(Path.home()) not in said


class TestAProfileTheAwsConfigLacks:
    @pytest.mark.parametrize(
        "command",
        [
            ("store", "sync"),
            ("store", "sync", "--apply"),
            ("store", "ls"),
            ("store", "get", "manifests/testcl26/2026-09-01.jsonl"),
            ("caselist", "publish", "--caselist", SYNTHETIC_CASELIST),
            ("caselist", "status"),
            ("caselist", "runs", "--remote"),
            REMOVE,
            ("caselist", "unsuppress", "--sha256", "0" * 64, "--reason", "REMOVED_IN_ERROR"),
        ],
        ids=lambda command: " ".join(command[:3]),
    )
    def test_the_environments_profile_setting_naming_one_exits_one_and_names_the_setting(
        self, installation: Path, monkeypatch: pytest.MonkeyPatch, command: tuple[str, ...]
    ) -> None:
        """Every command that builds the bucket's adapter with the everyday profile."""
        monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)

        exit_code, envelope = run(*command)

        assert_a_profile_that_is_not_configured(
            exit_code, envelope, setting=EVERYDAY_SETTING, installation=installation
        )

    def test_the_removal_profile_naming_one_exits_one_names_its_variable_and_changes_nothing(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A takedown reads with the everyday profile and deletes with the one
        `DEBATE_REMOVAL_PROFILE` names. That variable is the one to correct, and the error must not
        send the operator to the everyday profile's setting instead.

        It is the takedown's own refusal, as an expired session is (`v1-e29-t08`): what an operator
        who has just typed `--execute` needs to read first is that nothing was deleted. The
        adapter's error, bare, said nothing of the removal. Still a configuration error, so still 1.
        """
        import_the_first_week(installation)
        assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)[0] == ExitCode.OK
        monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", MISSPELT_PROFILE)
        before = (
            everything_under(installation / "data"),
            bucket.list_object_versions(Bucket=BUCKET).get("Versions"),
        )

        exit_code, envelope = run(*REMOVE, "--execute")

        assert exit_code == ExitCode.DOMAIN_FAILURE, envelope
        error = envelope["error"]
        assert error["code"] == "TAKEDOWN_PREFLIGHT_FAILED"
        assert "nothing was deleted" in error["message"]
        assert "STORE_PROFILE_NOT_CONFIGURED" in error["message"]
        assert MISSPELT_PROFILE in error["message"] and TAKEDOWN_SETTING in error["message"]
        assert TAKEDOWN_SETTING in error["hint"] and RUNBOOK in error["hint"]
        assert error["details"] == {"profile": MISSPELT_PROFILE, "step": "start an AWS session"}
        said = json.dumps(envelope)
        assert EVERYDAY_SETTING not in said
        assert "aws sso login" not in said and "signed in" not in said, "no login cures it"
        assert "aws configure" not in said
        assert str(installation) not in said and AWS_CONFIG_NAME not in said
        assert str(Path.home()) not in said
        after = (
            everything_under(installation / "data"),
            bucket.list_object_versions(Bucket=BUCKET).get("Versions"),
        )
        assert after == before, "nothing was deleted, here or in the bucket"

    def test_a_person_reads_the_setting_and_the_exit_code_and_no_traceback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)

        result = runner.invoke(create_app(), ["store", "sync"], terminal_width=200)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        shown = " ".join(result.stderr.split())
        assert "STORE_PROFILE_NOT_CONFIGURED" in shown
        assert f"named by {EVERYDAY_SETTING}" in shown
        assert "exit 1" in shown
        assert "Traceback" not in shown
        assert "aws sso login" not in shown

    def test_a_profile_that_is_defined_is_no_error(self, bucket: S3Client) -> None:
        """The control for everything above: the same commands, the profile the config defines."""
        exit_code, envelope = run("store", "sync")

        assert exit_code == ExitCode.OK, envelope


# ------------------------------------------------------------------------------------------------
# A takedown that names the everyday profile
# ------------------------------------------------------------------------------------------------


class TestATakedownThatNamesTheEverydayProfile:
    """`DEBATE_REMOVAL_PROFILE` set to the everyday profile, by mistake (`v1-e29-t08`).

    Through the real composition root and the real STS adapter: moto answers `GetCallerIdentity`
    with the role each profile assumed in the `bucket` fixture. Moto enforces no grant, so its
    bucket would let the everyday profile carry out the whole removal. What stops it is who it is.
    """

    def test_it_is_refused_before_anything_is_written_and_told_which_profile_to_name(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import_the_first_week(installation)
        assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)[0] == ExitCode.OK
        monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", EVERYDAY_PROFILE)
        before = (everything_under(installation / "data"), every_version_in(bucket))

        exit_code, envelope = run(*REMOVE, "--execute")

        assert exit_code == ExitCode.DOMAIN_FAILURE, envelope
        error = envelope["error"]
        assert error["code"] == "TAKEDOWN_PREFLIGHT_FAILED"
        assert "NOT_THE_TAKEDOWN_ROLE" in error["message"]
        assert "nothing was deleted" in error["message"]
        assert "DebateDevEvidenceOperator" in error["message"], "what the profile is signed in as"
        assert "DebateDevEvidenceRemoval" in error["message"], "what a takedown runs as"
        assert TAKEDOWN_SETTING in error["hint"] and TAKEDOWN_PROFILE in error["hint"]
        assert "aws sso login" not in json.dumps(envelope), "it is signed in; a login changes nothing"
        assert (everything_under(installation / "data"), every_version_in(bucket)) == before, (
            "nothing written here or in the bucket: no probe, no suppression entry"
        )

    def test_the_refusal_carries_nothing_of_the_account_but_the_roles_names(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STS answers with the account and the caller's full identifier. Neither is passed on."""
        import_the_first_week(installation)
        monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", EVERYDAY_PROFILE)

        result = runner.invoke(create_app(), ["--json", *REMOVE, "--execute"])

        said = result.stdout + result.stderr
        assert "TAKEDOWN_PREFLIGHT_FAILED" in said
        assert "arn:" not in said and "assumed-role" not in said
        assert re.search(r"\d{12}", said) is None, "no account"
        assert EVERYDAY_ROLE not in said, "the permission set's name is enough; the suffix is the account's"

    def test_the_takedown_profile_is_not_refused(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The control: the same command with the profile that is the takedown role."""
        import_the_first_week(installation)
        assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)[0] == ExitCode.OK
        monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", TAKEDOWN_PROFILE)

        exit_code, envelope = run(*REMOVE, "--execute")

        assert exit_code == ExitCode.OK, envelope
        assert [key for key, _ in every_version_in(bucket) if "/preflight/" in key] == []


# ------------------------------------------------------------------------------------------------
# A bucket that refuses the profile
# ------------------------------------------------------------------------------------------------


def the_bucket_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request to the bucket is answered `AccessDenied`, as S3 answers a missing grant."""

    def access_denied(_: object, operation_name: str, __: object) -> None:
        response: Any = {
            "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }
        raise ClientError(response, operation_name)

    monkeypatch.setattr("botocore.client.BaseClient._make_api_call", access_denied)


def assert_a_missing_grant(exit_code: int, envelope: dict[str, Any], *, profile: str) -> None:
    """3 and `STORE_ACCESS_DENIED`, as before, and now the hint that says what it means: a grant
    this profile lacks, where the grants are listed, and no login."""
    assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
    error = envelope["error"]
    assert error["code"] == "STORE_ACCESS_DENIED"
    assert error["hint"] is not None, "a refusal with nothing to do about it"
    assert "grant" in error["hint"]
    assert profile in error["hint"]
    assert RUNBOOK in error["hint"]
    assert "aws sso login" not in json.dumps(envelope)


class TestABucketThatRefusesTheProfile:
    def test_caselist_publish_says_the_profile_lacks_a_grant(
        self, installation: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import_the_first_week(installation)
        the_bucket_refuses(monkeypatch)

        exit_code, envelope = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)

        assert_a_missing_grant(exit_code, envelope, profile=EVERYDAY_PROFILE)
        assert "lacks a grant" in envelope["error"]["hint"]

    @pytest.mark.parametrize("command", [("store", "sync"), ("store", "sync", "--apply")], ids=" ".join)
    def test_store_sync_says_a_grant_is_missing(
        self, installation: Path, monkeypatch: pytest.MonkeyPatch, command: tuple[str, ...]
    ) -> None:
        """`store sync` begins by listing the bucket from its root, which no profile is granted, so
        its hint is the one about prefixes. It points at the grants all the same."""
        manifest = installation / "data" / "objects" / "manifests" / "testcl26" / "2026-09-01.jsonl"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(b"week one\n")
        the_bucket_refuses(monkeypatch)

        exit_code, envelope = run(*command)

        assert_a_missing_grant(exit_code, envelope, profile=EVERYDAY_PROFILE)

    def test_store_get_says_the_profile_lacks_a_grant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        the_bucket_refuses(monkeypatch)

        exit_code, envelope = run("store", "get", "manifests/testcl26/2026-09-01.jsonl")

        assert_a_missing_grant(exit_code, envelope, profile=EVERYDAY_PROFILE)
        assert "lacks a grant" in envelope["error"]["hint"]

    def test_caselist_status_says_the_profile_lacks_a_grant(
        self, installation: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import_the_first_week(installation)
        the_bucket_refuses(monkeypatch)

        exit_code, envelope = run("caselist", "status", "--caselist", SYNTHETIC_CASELIST)

        assert_a_missing_grant(exit_code, envelope, profile=EVERYDAY_PROFILE)

    def test_planning_a_removal_says_the_profile_lacks_a_grant(
        self, installation: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import_the_first_week(installation)
        the_bucket_refuses(monkeypatch)

        exit_code, envelope = run(*REMOVE)

        assert_a_missing_grant(exit_code, envelope, profile=EVERYDAY_PROFILE)

    def test_a_takedown_the_bucket_refuses_names_the_takedown_profile(
        self, installation: Path, bucket: S3Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The plan reads with the everyday profile and is allowed; the takedown profile's first
        write is refused. The hint has to name the profile that lacks the grant, since two are in
        play, and the removal's own wrapper carries the adapter's hint out."""
        import_the_first_week(installation)
        assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)[0] == ExitCode.OK
        monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", TAKEDOWN_PROFILE)
        make_api_call: Any = vars(BaseClient)["_make_api_call"]

        def refuse_writes(self: Any, operation_name: str, api_params: Any) -> Any:
            if operation_name in {"PutObject", "DeleteObject", "CreateMultipartUpload"}:
                response: Any = {
                    "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                }
                raise ClientError(response, operation_name)
            return make_api_call(self, operation_name, api_params)

        monkeypatch.setattr(BaseClient, "_make_api_call", refuse_writes)

        exit_code, envelope = run(*REMOVE, "--execute")

        assert exit_code == ExitCode.RETRIEVAL_FAILURE, envelope
        assert envelope["error"]["code"] == "TAKEDOWN_PREFLIGHT_FAILED"
        assert "STORE_ACCESS_DENIED" in envelope["error"]["message"]
        assert TAKEDOWN_PROFILE in envelope["error"]["hint"]
        assert "lacks a grant" in envelope["error"]["hint"]
        assert RUNBOOK in envelope["error"]["hint"]
        assert "aws sso login" not in json.dumps(envelope)

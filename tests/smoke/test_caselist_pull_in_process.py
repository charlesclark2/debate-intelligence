"""`debate-research caselist pull`, where a check has to stand in for part of the build itself.

These checks run in pytest's own process, with respx answering OpenCaselist and moto answering S3,
because each replaces something inside the CLI and not only the world around it: an S3 adapter
whose session expires part-way through a run, botocore raising its own `ProfileNotFound` or
`UnauthorizedSSOTokenError` before any request is sent, a status service that is refused, the
notifier the run monitor speaks through, the clock, or the OpenCaselist client's download. None of
that can be done to an installed build from outside it, and patching the build's code from the
test side is what `v1-e01-t21` forbids. So `ci` runs them on every PR, and validate-dev's recorded
tier does not.

The weekly pull's own smoke checks, against the installed build with loopback stand-ins for
OpenCaselist and S3, are `test_caselist_pull.py` (`v1-e01-t21`). These were part of that module
until then. There is a live check here too, marked and opt-in: it lists one caselist against the
real API with the operator's own token and downloads nothing.

The archives are the invented ones from `tests/fixtures/caselist/` and the camp file is from
`tests/fixtures/openev/`; no real caselist content enters this repository
(`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import httpx
import pytest
import respx
from botocore.client import BaseClient
from botocore.exceptions import ClientError, ProfileNotFound, UnauthorizedSSOTokenError
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.caselist.publish_expectations import digest_of_body
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES
from tests.fixtures.permissions import needs_permissions, refused
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired, StoreUnavailable
from debate_core.application.ports.caselist_source import ArchiveListing, DownloadedFile
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.integrations.opencaselist import OpenCaselistClient
from debate_core.integrations.s3 import S3Call, S3EvidenceObjectStore, translate_s3_error

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

# Runs in pytest's own process, where respx answers OpenCaselist and moto answers S3, so it cannot
# run against an installed build: `ci` runs it, and validate-dev's recorded tier deselects it
# (README.md, and this module's docstring for why each check is here).
pytestmark = pytest.mark.in_process

BUCKET = "debate-dev-evidence-pull-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
REMOVAL_PROFILE = "debate-dev-evidence-removal"
API = "https://api.opencaselist.example.invalid/v1"
FILE_HOST = "https://files.opencaselist.example.invalid"
OPENEV_FILE_ID = 512
OPENEV_YEAR = 2026
OPENEV_FILENAME = "TSF-Estuary Solvency Advocate.docx"


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a moto bucket and the test API, with a token in the environment."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    # The takedown profile too, for the check that removes the camp file (v1-e34-t07).
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (AWS_PROFILE_NAME, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for name in (AWS_PROFILE_NAME, REMOVAL_PROFILE)
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
        "allow_network = true\n"
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        "[caselist]\n"
        "api_enabled = true\n"
        # A dev profile would pick the macOS notifier on a Mac; no check may notify (v1-e34-t03).
        'notifier = "none"\n'
        f'api_base_url = "{API}"\n'
        f'sync_caselists = ["{SYNTHETIC_CASELIST}"]\n'
        # The floor the settings allow. What this check is about is the run, not the pacing, and
        # six paced requests at the 1s default would put it over five seconds for nothing.
        "min_request_interval_seconds = 0.5\n"
        # The parse stage is on, as it is for the agent (`v1-e34-t17`). One worker, so that each
        # pull here starts one process and not the machine's cores less one.
        "[parse]\nworkers = 1\n"
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "fixture-token-not-a-real-one")
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
            {AWS_PROFILE_NAME: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE},
        )
        yield client


def camp_file(openev_id: int, camp: str, filename: str) -> dict[str, Any]:
    """One OpenEv file as `GET /openev` lists it."""
    return {
        "openev_id": openev_id,
        "path": f"/openev/{OPENEV_YEAR}/{camp}/{filename}",
        "filename": filename,
        "year": OPENEV_YEAR,
        "camp": camp,
        "tags": {"policy": True},
    }


@pytest.fixture
def camp_files() -> dict[str, tuple[dict[str, Any], bytes]]:
    """What OpenEv lists, by upstream path: the listing entry and the bytes `/download` serves.

    A test adds to it to have the next run list a new camp file.
    """
    listed = camp_file(OPENEV_FILE_ID, "Tamarack", OPENEV_FILENAME)
    return {str(listed["path"]): (listed, DOCUMENT_BODIES["estuary-solvency"])}


@pytest.fixture
def site(
    installation: Path, camp_files: dict[str, tuple[dict[str, Any], bytes]]
) -> Iterator[respx.MockRouter]:
    """OpenCaselist: three weekly archives, one full archive, and the OpenEv files in `camp_files`.

    The complete archive is served as the 09-15 weekly's bytes: the synthetic weeklies are
    cumulative, so the newest one holds what a complete archive of that date would.
    """
    zips = build_snapshot_zips(installation / "published")
    listing = [
        {"name": weekly_name(week.snapshot), "url": f"{FILE_HOST}/{weekly_name(week.snapshot)}"}
        for week in SNAPSHOTS
    ]
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    listing.append({"name": full, "url": f"{FILE_HOST}/{full}"})

    def download(request: httpx.Request) -> httpx.Response:
        # The client takes the leading `/` off a listed path before asking for it.
        return httpx.Response(200, content=camp_files["/" + request.url.params["path"]][1])

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=listing)
        router.get(f"{API}/openev").mock(
            side_effect=lambda _: httpx.Response(200, json=[listed for listed, _ in camp_files.values()])
        )
        router.get(f"{API}/download").mock(side_effect=download)
        for week in SNAPSHOTS:
            router.get(f"{FILE_HOST}/{weekly_name(week.snapshot)}").respond(
                200, content=zips[week.snapshot].read_bytes()
            )
        router.get(f"{FILE_HOST}/{full}").respond(200, content=zips[SNAPSHOTS[-1].snapshot].read_bytes())
        yield router


def run(*arguments: str) -> dict[str, Any]:
    """Run one command asking for JSON, and return its envelope with the exit code on it."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope = json.loads(lines[0])
    assert isinstance(envelope, dict)
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


# ------------------------------------------------------------------------------------------------
# The AWS session behind the bucket's copy of the suppression list (v1-e34-t07, after PM review)
# ------------------------------------------------------------------------------------------------

SUPPRESSION_LIST_KEY = "manifests/_suppression/suppression-list.jsonl"


def expire_the_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    only: str | None = None,
    error: type[Exception] = StoreCredentialsExpired,
    while_set: dict[str, bool] | None = None,
) -> None:
    """Make the S3 adapter refuse as it does once the operator's SSO session has expired.

    With `only`, just a read of that key refuses (and with `error`, refuses that way: a missing
    grant, or a bucket that does not answer); everything else still reaches moto. With `while_set`,
    it refuses only while `while_set["expired"]` is true, so a test can log back in.
    """

    def refuse(*_: object) -> None:
        if while_set is not None and not while_set["expired"]:
            return
        if error is StoreAccessDenied:
            raise access_denied_by_the_bucket("GetObject", only or "")
        if error is StoreUnavailable:
            raise StoreUnavailable("GetObject", only or "the bucket", "simulated 503 SlowDown")
        raise StoreCredentialsExpired(hint=f"aws sso login --profile {AWS_PROFILE_NAME}")

    original = S3EvidenceObjectStore.get_file

    async def get_file(self: S3EvidenceObjectStore, key: str, destination: Path) -> Any:
        if only is None or key == only:
            refuse()
        return await original(self, key, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(S3EvidenceObjectStore, "get_file", get_file)
    if only is None:
        for name in ("list_objects", "head", "put_file"):
            monkeypatch.setattr(
                S3EvidenceObjectStore, name, _refusing(getattr(S3EvidenceObjectStore, name), refuse)
            )


def access_denied_by_the_bucket(operation: str, key: str) -> StoreAccessDenied:
    """What the real S3 adapter raises when the bucket answers `AccessDenied`, its hint included.

    Built by the adapter's own translation and not by hand, because the hint a stage shows for a
    refusal is the adapter's (`v1-e29-t07`): a stub that wrote its own would test the stub.
    """
    response: Any = {
        "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
        "ResponseMetadata": {"HTTPStatusCode": 403},
    }
    refused = translate_s3_error(
        ClientError(response, operation),
        S3Call(
            operation=operation,
            bucket=BUCKET,
            entity="evidence object",
            key=key,
            s3_key=key or None,
            profile=AWS_PROFILE_NAME,
        ),
    )
    assert isinstance(refused, StoreAccessDenied)
    return refused


def _refusing(original: Any, refuse: Any) -> Any:
    """`original`, a method of the S3 adapter, behind `refuse`, which raises when the session is out."""

    async def method(self: S3EvidenceObjectStore, *arguments: object) -> Any:
        refuse()
        return await original(self, *arguments)

    return method


def list_two_new_camp_files(camp_files: dict[str, tuple[dict[str, Any], bytes]]) -> None:
    """513 holds the removed camp file's bytes under another camp's path; 514 is new material."""
    for listed, body in (
        (camp_file(513, "Brightwater", "BWW-Estuary Copy.docx"), DOCUMENT_BODIES["estuary-solvency"]),
        (camp_file(514, "Brightwater", "BWW-Orchard Kritik.docx"), DOCUMENT_BODIES["orchard-kritik"]),
    ):
        camp_files[str(listed["path"])] = (listed, body)


def run_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """The run summary, from `data` on success or the failure's `details` (`CASELIST_PULL_INCOMPLETE`)."""
    return envelope["data"] if envelope["data"] is not None else envelope["error"]["details"]


def release_manifest(installation: Path) -> list[dict[str, Any]]:
    path = installation / "data" / "objects" / "manifests" / "openev" / f"{OPENEV_YEAR}-policy.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_an_expired_session_still_imports_and_what_was_removed_here_stays_out(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    camp_files: dict[str, tuple[dict[str, Any], bytes]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The weekly run as launchd will usually make it: the SSO session has expired.

    `v1-e34-t02` built the run so the local stages need no session and publish pends. The pull's
    suppression list falls back to this machine's copy when the bucket's cannot be read for want of
    credentials, and says so. The camp file removed on this machine is still skipped, its bytes
    under another id are still refused, and the new file is imported.
    """
    assert run("caselist", "pull")["exit_code"] == ExitCode.OK
    removed = hashlib.sha256(DOCUMENT_BODIES["estuary-solvency"]).hexdigest()
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    remove = (
        "caselist",
        "remove",
        "--source",
        removed,
        "--request",
        "RM-2026-01",
        "--reason",
        "REQUESTED_BY_CAMP",
    )
    assert run(*remove, "--execute")["exit_code"] == ExitCode.OK
    monkeypatch.delenv("DEBATE_REMOVAL_PROFILE")
    list_two_new_camp_files(camp_files)
    expire_the_session(monkeypatch)

    again = run("caselist", "pull")

    data = run_summary(again)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "completed", stages["import"]
    assert again["exit_code"] == ExitCode.OK, again
    decisions = {one["openev_id"]: one["decision"] for one in data["openev_selections"]}
    assert decisions == {OPENEV_FILE_ID: "skipped_as_removed", 513: "download", 514: "download"}
    assert data["blobs_stored"] == 1, "only 514's bytes are new and not removed"
    # 513 is the removed bytes under another camp's path: refused, so no row and nothing imported.
    # (The release summary's SUPPRESSED count describes only the latest import, which was 514's.)
    assert data["files_imported"] == 1
    rows = [row for row in release_manifest(installation) if row["kind"] == "member"]
    assert not any(row["sha256"] == removed or "openev-513-" in row["path"] for row in rows)
    assert any("openev-514-" in row["path"] for row in rows)
    assert stages["publish"]["outcome"] == "pending"
    # Pending is not failed: no error code, and the exit code above is 0 (v1-e34-t13).
    assert stages["publish"]["error_codes"] == []
    assert "aws sso login" in stages["publish"]["reason"]
    assert "aws sso login" in data["suppression_list_local_copy_only"]
    assert "this machine's copy of the suppression list alone" in stages["import"]["reason"]


@pytest.mark.live
@pytest.mark.enable_socket
def test_a_live_dry_run_lists_the_operators_own_caselist() -> None:
    """Opt-in, against the real API, with the operator's own token. Lists; downloads nothing.

    ```
    DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true CASELIST_LIVE_SLUG=hsld26 \
        uv run pytest tests/smoke/test_caselist_pull.py -m live
    ```

    A `--dry-run` because a real download would spend one of the site's five bulk downloads a day
    (`docs/policies/caselist-data-use.md`, E34 gate 4), and because the first real pull is an
    operator step taken deliberately, not something a test suite does.
    """
    slug = os.environ.get("CASELIST_LIVE_SLUG")
    if not slug:
        pytest.skip("set CASELIST_LIVE_SLUG to the caselist to list, e.g. hsld26")

    envelope = run("caselist", "pull", "--caselist", slug, "--dry-run")

    assert envelope["exit_code"] == ExitCode.OK, envelope
    assert envelope["data"]["archives_downloaded"] == 0
    assert envelope["data"]["archives_seen"] > 0


# ------------------------------------------------------------------------------------------------
# A refusal is not an expired login (v1-e34-t13)
# ------------------------------------------------------------------------------------------------


def stage_text(envelope: dict[str, Any]) -> str:
    """Everything the stages and the command's own hint say, as one string to search."""
    error = envelope["error"] or {}
    return json.dumps([run_summary(envelope)["stages"], error.get("message"), error.get("hint")])


@needs_permissions
def test_a_local_refusal_in_publish_fails_it_with_the_data_directory_fix_and_is_never_pending(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The weekly run imports with the session expired, so its publish is owed. The operator logs
    in and drains it, and this machine's blob directory cannot be read. That used to be reported as
    sources missing from this machine, and after a translation would have been "waiting for an AWS
    login". It is a failed publish whose fix is a permission on this machine."""
    session = {"expired": True}
    expire_the_session(monkeypatch, while_set=session)
    first = run("caselist", "pull")
    assert first["exit_code"] == ExitCode.OK, first
    owed = run_summary(first)["pending_publish"]
    assert len(owed) == 5

    session["expired"] = False
    with refused(installation / "data" / "blobs"):
        drained = run("caselist", "pull", "--publish-pending")

    assert drained["exit_code"] == ExitCode.RETRIEVAL_FAILURE, drained
    data = run_summary(drained)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "failed"
    assert stages["publish"]["error_codes"] == ["STORE_ACCESS_DENIED"]
    assert "the blob directory" in stages["publish"]["hint"]
    assert "storage.data_dir" in stages["publish"]["hint"]
    assert drained["error"]["hint"].startswith(stages["publish"]["hint"])
    assert stages["report"]["outcome"] == "skipped"
    assert sorted(data["pending_publish"]) == sorted(owed), "still owed, for the run after the fix"
    assert data["run_record"]["outcome"] == "failed"
    assert "aws sso login" not in stage_text(drained)
    assert str(installation) not in stage_text(drained)
    assert str(Path.home()) not in stage_text(drained)

    fixed = run("caselist", "pull", "--publish-pending")

    assert fixed["exit_code"] == ExitCode.OK, fixed
    assert run_summary(fixed)["pending_publish"] == []


def test_a_missing_grant_in_report_fails_it_with_the_grant_fix_and_is_never_pending(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything publishes, and the comparison that confirms it is refused: the profile is signed
    in and lacks a grant. The report stage fails and names that. Nothing waits for a login, and the
    run's exit code is still the `0` of a run whose bytes all reached the bucket: the report stage
    is not one of the stages that decide it."""

    async def refuse(
        self: CaselistStatusService, caselist: str | None = None, snapshot: str | None = None
    ) -> Any:
        raise access_denied_by_the_bucket("HeadObject", f"manifests/{caselist}/{snapshot}.jsonl")

    monkeypatch.setattr(CaselistStatusService, "status", refuse)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "completed"
    assert stages["report"]["outcome"] == "failed"
    assert stages["report"]["error_codes"] == ["STORE_ACCESS_DENIED"]
    assert "lacks a grant" in stages["report"]["hint"]
    assert "docs/runbooks/evidence-store.md" in stages["report"]["hint"]
    # The adapter's own sentence, which names the profile: the sync writes none (v1-e29-t07).
    assert f"the AWS profile {AWS_PROFILE_NAME} is signed in" in stages["report"]["hint"]
    assert data["pending_publish"] == []
    assert data["run_record"]["outcome"] == "incomplete"
    assert "aws sso login" not in stage_text(pulled)
    assert str(installation) not in stage_text(pulled)


# ------------------------------------------------------------------------------------------------
# What a publish did not finish is owed, whatever ended it (v1-e34-t18)
# ------------------------------------------------------------------------------------------------

PENDING_WORK_FILE = "caselist-sync-pending.json"
"""The pending-work file's name under the data directory, as the runbook gives it."""


def owed_in_the_file(installation: Path) -> list[str]:
    """The snapshots the pending-work file names, read as JSON; none when there is no file."""
    path = installation / "data" / PENDING_WORK_FILE
    if not path.exists():
        return []
    return [f"{one['caselist']} {one['snapshot']}" for one in json.loads(path.read_text())["publish"]]


def test_a_session_that_expires_part_way_through_publish_owes_every_snapshot_it_did_not_finish(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first week's publish ends incomplete, because the bucket answers one of its uploads with
    a 503, and the session then expires on the second week's manifest. The run used to write down
    only the snapshots it had not reached, so nothing owed the first week and no later run
    published it. All five are owed now, and `--publish-pending` after a login publishes them."""
    week_one_only = digest_of_body("grove-round-2-neg-first")
    session = {"expired": False, "logged_in": False}
    expire_the_session(monkeypatch, while_set=session)
    put_file = S3EvidenceObjectStore.put_file

    async def put(self: S3EvidenceObjectStore, key: str, source: Path) -> Any:
        if not session["logged_in"]:
            if key == f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl":
                session["expired"] = True
            elif key.endswith(week_one_only):
                raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
        return await put_file(self, key, source)  # type: ignore[arg-type]

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "pending", stages["publish"]
    assert len(data["snapshots_imported"]) == 5
    assert sorted(data["pending_publish"]) == sorted(data["snapshots_imported"])
    assert sorted(owed_in_the_file(installation)) == sorted(data["snapshots_imported"])
    assert not bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/testcl26/").get("Contents")

    session.update(expired=False, logged_in=True)
    drained = run("caselist", "pull", "--publish-pending")

    assert drained["exit_code"] == ExitCode.OK, drained
    data = run_summary(drained)
    assert {one["stage"]: one["outcome"] for one in data["stages"]}["publish"] == "completed"
    assert data["pending_publish"] == []
    assert not (installation / "data" / PENDING_WORK_FILE).exists()
    published = {one["Key"] for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/")["Contents"]}
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" in published
    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["in_sync"] is True


# ------------------------------------------------------------------------------------------------
# A profile the AWS config does not define is a configuration error, not a login (v1-e29-t07)
# ------------------------------------------------------------------------------------------------

PROFILE_SETTING = "storage.s3.aws_profile"
"""The setting that holds the everyday profile's name, which the error names instead of a path."""

MISSPELT_PROFILE = "debate-dev-evidence-typo"


def botocore_raises(monkeypatch: pytest.MonkeyPatch, error: Exception) -> dict[str, bool]:
    """Every call botocore makes to the bucket raises `error`, except reads of the suppression list.

    The real S3 adapter then does the translating, as it does on the operator's machine. The
    suppression list is spared so that the import stage reads every copy and the failure arrives
    where this section is about: the publish stage. Clear `["on"]` to let the calls through again.
    """
    raising = {"on": True}
    make_api_call: Any = vars(BaseClient)["_make_api_call"]

    def api_call(self: BaseClient, operation_name: str, api_params: dict[str, Any]) -> Any:
        named = str(api_params.get("Key") or api_params.get("Prefix") or "")
        if raising["on"] and not named.startswith("manifests/_suppression/"):
            raise error
        return make_api_call(self, operation_name, api_params)

    monkeypatch.setattr(BaseClient, "_make_api_call", api_call)
    return raising


def assert_names_the_setting_and_nothing_of_this_machine(text: str, installation: Path) -> None:
    """The fix is the setting that holds the profile's name: never a login, never a path."""
    assert "aws sso login" not in text
    assert "aws configure" not in text
    assert str(installation) not in text, "the AWS config's path is under the installation here"
    assert str(Path.home()) not in text
    assert "aws-config" not in text and "/.aws" not in text


def test_a_profile_the_aws_config_lacks_fails_publish_with_one_and_everything_imported_stays_owed(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """botocore answers the publish with its own `ProfileNotFound`. The adapter used to call that
    an expired session, so the publish stage was *pending*, the run exited 0, and the weekly agent
    asked for a login that fixes nothing. It is the publish stage failing on a configuration
    error: exit `1`, with the setting to correct, and every snapshot imported still owed
    (`v1-e34-t18`), so the run after the fix publishes them without fetching anything again."""
    raising = botocore_raises(monkeypatch, ProfileNotFound(profile=AWS_PROFILE_NAME))

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.DOMAIN_FAILURE, pulled
    assert pulled["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "completed", stages["import"]
    assert (stages["publish"]["outcome"], stages["publish"]["error_codes"]) == (
        "failed",
        ["STORE_PROFILE_NOT_CONFIGURED"],
    )
    assert PROFILE_SETTING in stages["publish"]["hint"]
    assert pulled["error"]["hint"].startswith(stages["publish"]["hint"])
    assert stages["report"]["outcome"] == "skipped"
    assert len(data["snapshots_imported"]) == 5
    assert sorted(data["pending_publish"]) == sorted(data["snapshots_imported"])
    assert sorted(owed_in_the_file(installation)) == sorted(data["snapshots_imported"])
    assert_names_the_setting_and_nothing_of_this_machine(stage_text(pulled), installation)
    downloads = len(site.calls)

    raising["on"] = False
    assert not bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/testcl26/").get("Contents")
    drained = run("caselist", "pull", "--publish-pending")

    assert drained["exit_code"] == ExitCode.OK, drained
    assert run_summary(drained)["pending_publish"] == []
    assert not (installation / "data" / PENDING_WORK_FILE).exists()
    assert len(site.calls) == downloads, "nothing is fetched again"


def test_an_expired_session_answered_by_botocore_still_leaves_publish_pending_with_the_login(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same run, with botocore's own answer for an expired SSO session instead. Unchanged: the
    publish is pending and owed, the run exits `0`, no failure code is recorded, and the stage
    names the login that completes it."""
    botocore_raises(monkeypatch, UnauthorizedSSOTokenError())

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "completed", stages["import"]
    assert (stages["publish"]["outcome"], stages["publish"]["error_codes"]) == ("pending", [])
    assert f"aws sso login --profile {AWS_PROFILE_NAME}" in stages["publish"]["reason"]
    assert PROFILE_SETTING not in json.dumps(data["stages"])
    assert stages["report"]["outcome"] == "pending"
    assert sorted(owed_in_the_file(installation)) == sorted(data["snapshots_imported"])
    assert data["run_record"]["outcome"] == "publish_pending"


def test_a_profile_setting_that_names_no_profile_in_the_aws_config_ends_the_pull_with_one(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a misspelt profile does on a real installation: boto3 refuses to build a session for a
    profile the AWS config does not define, so the bucket's adapter cannot be built at all. That
    used to exit `3`, "a retry may succeed", under the code of an expired session. It is a
    configuration error: exit `1`, under its own code, naming the setting to correct.

    And it is no longer silent (`v1-e34-t22`). The run used to end before its monitor could be
    built, with no record and no notification. It is recorded on this machine as a failed run, its
    details name the code and the setting, one banner says a person should look, and its record is
    owed to the bucket."""
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.DOMAIN_FAILURE, pulled
    assert pulled["error"]["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert MISSPELT_PROFILE in pulled["error"]["message"]
    assert PROFILE_SETTING in pulled["error"]["message"]
    assert PROFILE_SETTING in pulled["error"]["hint"]
    assert_names_the_setting_and_nothing_of_this_machine(json.dumps(pulled["error"]), installation)
    assert not bucket.list_objects_v2(Bucket=BUCKET).get("Contents"), "nothing reached the bucket"
    assert owed_in_the_file(installation) == []
    assert len(site.calls) == 0, "nothing is fetched"

    [record] = run_log_of(installation)
    assert (record["outcome"], record["error_class"]) == ("failed", "StoreProfileNotConfigured")
    assert record["stages"] == []
    [details] = run_details_of(installation)
    assert details["run_id"] == record["run_id"]
    assert details["failure_codes"] == ["STORE_PROFILE_NOT_CONFIGURED"]
    assert PROFILE_SETTING in details["hint"]
    [banner] = notified.sent
    assert banner.title == PERSON_TITLE
    assert banner.hint == details["hint"]
    assert records_owed_to_the_bucket(installation) == [record["run_id"]]
    assert_names_the_setting_and_nothing_of_this_machine(
        json.dumps([record, details, banner.title, banner.text]), installation
    )


def test_the_week_after_a_refused_run_the_pull_imports_publishes_and_publishes_the_refused_runs_record(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`v1-e34-t22` ac2, as the weekly agent meets it: one week the setting is wrong and the run is
    refused, and the setting is corrected before the next. That run fetches, imports and publishes
    as usual, and the refused run's record and details reach the bucket with its own."""
    times = iter([datetime(2026, 9, 16, 6, 0, tzinfo=UTC), datetime(2026, 9, 23, 6, 0, tzinfo=UTC)])
    now = {"at": next(times)}
    monkeypatch.setattr(ServiceContainer, "clock", lambda _: lambda: now["at"])
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)
    refused = run("caselist", "pull")
    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused

    monkeypatch.delenv("DEBATE_STORAGE__S3__AWS_PROFILE")
    now["at"] = next(times)
    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    assert run_summary(pulled)["objects_published"] > 0
    listed = [
        str(one.get("Key")) for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="reports/")["Contents"]
    ]
    assert sorted(key for key in listed if key.startswith("reports/sync-runs/")) == [
        "reports/sync-runs/2026/20260916T060000Z.json",
        "reports/sync-runs/2026/20260923T060000Z.json",
    ]
    assert sorted(key for key in listed if key.startswith("reports/sync-run-details/")) == [
        "reports/sync-run-details/2026/20260916T060000Z.json",
        "reports/sync-run-details/2026/20260923T060000Z.json",
    ]
    in_the_bucket = json.loads(
        bucket.get_object(Bucket=BUCKET, Key="reports/sync-runs/2026/20260916T060000Z.json")["Body"].read()
    )
    assert in_the_bucket == run_log_of(installation)[0]
    assert in_the_bucket["error_class"] == "StoreProfileNotConfigured"
    assert records_owed_to_the_bucket(installation) == []
    assert [one.title for one in notified.sent] == [PERSON_TITLE], "the second run had nothing to say"


def run_log_of(installation: Path) -> list[dict[str, Any]]:
    log = installation / "data" / "caselist-sync-runs.jsonl"
    return [json.loads(line) for line in log.read_text("utf-8").splitlines()] if log.exists() else []


def run_details_of(installation: Path) -> list[dict[str, Any]]:
    kept = installation / "data" / "caselist-sync-run-details.jsonl"
    return [json.loads(line) for line in kept.read_text("utf-8").splitlines()] if kept.exists() else []


def records_owed_to_the_bucket(installation: Path) -> list[str]:
    """The run ids whose record the bucket does not have yet; none when the file is gone."""
    owed = installation / "data" / "caselist-sync-records-pending.json"
    if not owed.exists():
        return []
    listed: list[str] = json.loads(owed.read_text("utf-8"))["run_ids"]
    return listed


# ------------------------------------------------------------------------------------------------
# Unreadable local files, and what the notification says (v1-e34-t19)
# ------------------------------------------------------------------------------------------------

RETRY_TITLE = "caselist pull failed: will be retried"
PERSON_TITLE = "caselist pull failed: needs a person"
"""The two banners of a failed run, by hand, as `docs/runbooks/caselist-scheduled-sync.md` gives them."""


@pytest.fixture
def notified(monkeypatch: pytest.MonkeyPatch) -> RecordingNotifier:
    """What the run monitor would have shown: the profile here says `none`, so nothing is shown."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(ServiceContainer, "sync_notifier", lambda _: notifier)
    return notifier


def everything_said(envelope: dict[str, Any], notified: RecordingNotifier) -> str:
    """The stages, the command's own error and every notification, as one string to search."""
    return stage_text(envelope) + json.dumps(
        [[one.title, one.message, one.hint, one.fix_command] for one in notified.sent]
    )


@needs_permissions
def test_a_manifest_this_mac_will_not_let_be_written_fails_the_import_with_three_and_the_fix(
    installation: Path, bucket: S3Client, site: respx.MockRouter, notified: RecordingNotifier
) -> None:
    """The caselist's manifest folder can be read and not written. Each week's import and the
    complete archive's reach the point of writing a manifest and are refused. That was a
    `PermissionError` and exit 70, "a bug", with no summary. It is the import stage failing on a
    refusal by this Mac: exit `3`, the data-directory fix in the stage's hint and on the banner,
    and the camp file, whose manifest is in another folder, imported and published all the same."""
    manifests = installation / "data" / "objects" / "manifests" / SYNTHETIC_CASELIST
    manifests.mkdir(parents=True)
    manifests.chmod(0o500)
    try:
        pulled = run("caselist", "pull")
    finally:
        manifests.chmod(0o700)

    assert pulled["exit_code"] == ExitCode.RETRIEVAL_FAILURE, pulled
    assert pulled["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "failed"
    assert stages["import"]["error_codes"] == ["STORE_ACCESS_DENIED"]
    assert "not allowed to write the manifest directory" in stages["import"]["reason"]
    assert "the manifest directory" in stages["import"]["hint"]
    assert "storage.data_dir" in stages["import"]["hint"]
    assert pulled["error"]["hint"].startswith(stages["import"]["hint"])
    assert data["snapshots_imported"] == [f"openev {OPENEV_YEAR}-policy"]
    assert stages["publish"]["outcome"] == "completed"
    [notification] = notified.sent
    assert notification.title == RETRY_TITLE
    assert notification.hint == stages["import"]["hint"]
    assert "aws sso login" not in everything_said(pulled, notified)
    assert str(installation) not in everything_said(pulled, notified)
    assert str(Path.home()) not in everything_said(pulled, notified)

    fixed = run("caselist", "pull")

    assert fixed["exit_code"] == ExitCode.OK, fixed
    assert len(run_summary(fixed)["snapshots_imported"]) == 4, "three weeks and the complete archive"
    assert run_summary(fixed)["archives_downloaded"] == 0, "imported from the inbox, not fetched again"


@needs_permissions
def test_a_manifest_file_this_mac_will_not_open_stops_the_run_with_three_and_never_seventy(
    installation: Path, bucket: S3Client, site: respx.MockRouter, notified: RecordingNotifier
) -> None:
    """After a good run, one week's manifest file cannot be opened. The selection reads it to know
    what this Mac holds, so the run stops before fetching anything, as it does for a manifest
    folder it cannot list (v1-e34-t13). The command's exit is `3` with the store's own code, not
    the `70` of a `PermissionError`, and the banner says the next run retries it and what to fix."""
    assert run("caselist", "pull")["exit_code"] == ExitCode.OK
    downloads = len(site.calls)
    manifest = installation / "data" / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-08.jsonl"
    manifest.chmod(0)
    notified.sent.clear()

    stopped = run("caselist", "pull")

    assert stopped["exit_code"] == ExitCode.RETRIEVAL_FAILURE, stopped
    assert stopped["error"]["code"] == "STORE_ACCESS_DENIED"
    assert "not allowed to read the manifest directory" in stopped["error"]["message"]
    assert "storage.data_dir" in stopped["error"]["message"]
    assert not any(
        call.request.url.host == "files.opencaselist.example.invalid" for call in site.calls[downloads:]
    )
    [notification] = notified.sent
    assert notification.title == RETRY_TITLE
    assert "stopped with LocalStoreAccessDenied" in notification.message
    assert notification.hint is not None and "the manifest directory" in notification.hint
    said = json.dumps([stopped["error"], notification.title, notification.message, notification.hint])
    assert str(installation) not in said
    assert str(Path.home()) not in said


@needs_permissions
def test_a_weekly_archive_this_mac_cannot_read_fails_its_own_import_with_one_and_the_rest_import(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first week lands in the inbox and cannot be opened. That ended the run on a
    `PermissionError`, exit 70. It now fails that archive's import, as an archive that cannot be
    read: exit `1` by v1-e34-t13's rule, the two newer weeks waiting behind it, and the camp file
    and the complete archive imported and published. Readable again, the next run imports all
    three weeks from the inbox without a download."""
    unreadable = weekly_name(SNAPSHOTS[0].snapshot)
    download_archive = OpenCaselistClient.download_archive

    async def lands_unreadable(
        self: OpenCaselistClient, archive: ArchiveListing, inbox: Path
    ) -> DownloadedFile:
        downloaded = await download_archive(self, archive, inbox)
        if archive.name == unreadable:
            downloaded.path.chmod(0)
        return downloaded

    monkeypatch.setattr(OpenCaselistClient, "download_archive", lands_unreadable)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.DOMAIN_FAILURE, pulled
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "failed"
    assert stages["import"]["error_codes"] == ["UNREADABLE_ARCHIVE"]
    assert f"{unreadable} cannot be read as an archive" in stages["import"]["reason"]
    assert "2 archive(s) in the inbox held back for a later run" in stages["import"]["reason"]
    assert sorted(data["snapshots_imported"]) == [
        f"openev {OPENEV_YEAR}-policy",
        f"{SYNTHETIC_CASELIST} full/2026-09-15",
    ]
    assert stages["publish"]["outcome"] == "completed"
    [notification] = notified.sent
    assert notification.title == PERSON_TITLE
    assert "the import stage failed on UNREADABLE_ARCHIVE" in notification.message
    assert str(installation) not in everything_said(pulled, notified)
    assert str(Path.home()) not in everything_said(pulled, notified)

    (installation / "data" / "inbox" / unreadable).chmod(0o600)
    again = run("caselist", "pull")

    assert again["exit_code"] == ExitCode.OK, again
    assert run_summary(again)["snapshots_imported"] == [
        f"{SYNTHETIC_CASELIST} {week.snapshot.isoformat()}" for week in SNAPSHOTS
    ]
    assert run_summary(again)["archives_downloaded"] == 0


def test_a_manifest_the_publisher_cannot_read_fails_publish_with_one_and_the_run_still_reports(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five snapshots are owed from a run whose session had expired, and one week's manifest then
    gains a line nobody can read. `--publish-pending` used to end on `UnreadableManifest` with no
    summary and nothing published. It is the publish stage failing on that code: exit `1`, the
    summary written, the run recorded, the other four published, and the file holding the one."""
    session = {"expired": True}
    expire_the_session(monkeypatch, while_set=session)
    assert run("caselist", "pull")["exit_code"] == ExitCode.OK
    assert len(owed_in_the_file(installation)) == 5
    torn = installation / "data" / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-01.jsonl"
    with torn.open("a", encoding="utf-8") as stream:
        stream.write('{"kind": "member", "classification": "NEW", "sha2\n')
    session["expired"] = False
    notified.sent.clear()

    drained = run("caselist", "pull", "--publish-pending")

    assert drained["exit_code"] == ExitCode.DOMAIN_FAILURE, drained
    assert drained["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(drained)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "failed"
    assert stages["publish"]["error_codes"] == ["UNREADABLE_MANIFEST"]
    assert data["pending_publish"] == [f"{SYNTHETIC_CASELIST} 2026-09-01"]
    assert owed_in_the_file(installation) == [f"{SYNTHETIC_CASELIST} 2026-09-01"]
    assert Path(data["summary_written_to"]).is_file()
    assert data["run_record"]["outcome"] == "failed"
    assert data["run_record"]["error_class"] is None
    assert stages["report"]["outcome"] == "completed"
    published = {one["Key"] for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/")["Contents"]}
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl" in published
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" not in published
    assert [one.title for one in notified.sent] == [PERSON_TITLE]


def test_a_mismatch_and_then_an_expired_session_exits_zero_and_says_a_person_is_needed_too(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1-e34-t18's shape, with a verdict in place of its 503: the bucket already holds other bytes
    under one of the first week's keys, and the session expires on the second week's manifest.
    Publish is pending and the exit is `0`, exactly as before: a pending stage carries no code for
    the exit. What changed is that the mismatch is no longer invisible until the retry: it is on
    the stage as an earlier finding, and the login banner says a person has to look as well."""
    week_one_only = digest_of_body("grove-round-2-neg-first")
    key = f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{week_one_only[:2]}/{week_one_only[2:4]}/{week_one_only}"
    bucket.put_object(Bucket=BUCKET, Key=key, Body=b"other bytes")
    session = {"expired": False}
    expire_the_session(monkeypatch, while_set=session)
    put_file = S3EvidenceObjectStore.put_file

    async def put(self: S3EvidenceObjectStore, key: str, source: Path) -> Any:
        if key == f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl":
            session["expired"] = True
        return await put_file(self, key, source)  # type: ignore[arg-type]

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "pending", stages["publish"]
    assert stages["publish"]["error_codes"] == []
    assert stages["publish"]["earlier_findings"] == ["CHECKSUM_MISMATCH"]
    assert data["run_details"]["failure_codes"] == []
    assert data["run_details"]["stages"] == [
        {"stage": "publish", "error_codes": [], "hint": None, "earlier_findings": ["CHECKSUM_MISMATCH"]}
    ]
    [notification] = notified.sent
    assert notification.title == "caselist publish waiting for an AWS login"
    assert (
        "A person should look as well: before the session expired a snapshot ended incomplete on "
        "CHECKSUM_MISMATCH, which the login will not fix." in notification.message
    )

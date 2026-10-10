"""`debate-research caselist pull` end to end, as `validate-dev` runs it and as launchd will.

The weekly run in one check, wired up the way an installation wires it: the console script, the
composition root, a `dev` settings profile, the real OpenCaselist client, the real importers, the
real manifests, and a real publish to a bucket. Two things stand in for the world and nothing
else does — respx answers OpenCaselist, and moto answers S3, both in-process, with sockets
disabled.

**This check is not marked `live`, and must not be.** A `live` marker would make the default
`-m "not slow and not live"` run collect it and skip it, so the one check covering the command the
schedule runs every week would look green in CI while never running (`tests/smoke/README.md`).
There *is* a live check here as well, marked and opt-in: it lists one caselist against the real
API with the operator's own token and downloads nothing, because a download would spend one of
the site's five bulk downloads a day for nothing a respx test does not already prove.

The archives are the invented ones from `tests/fixtures/caselist/` and the camp file is from
`tests/fixtures/openev/`; no real caselist content enters this repository
(`docs/policies/caselist-data-use.md`).
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
import httpx
import pytest
import respx
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.caselist.publish_expectations import digest_of_body, expected_publish
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES
from tests.fixtures.permissions import needs_permissions, refused
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired, StoreUnavailable
from debate_core.integrations.local import BLOB_DIRECTORY
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

# Runs in pytest's own process, where respx answers OpenCaselist and moto answers S3, so it cannot
# run against an installed build: `ci` runs it, and validate-dev's recorded tier deselects it
# (README.md).
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


def test_a_weekly_pull_downloads_imports_publishes_and_then_finds_nothing_new(
    installation: Path, bucket: S3Client, site: respx.MockRouter
) -> None:
    """Goal criterion ac1, through the installed command.

    The publish count is the fixture's own hand-written total — `expected_publish.json` says the
    three synthetic weeks come to 14 distinct source objects — plus one for the camp file, whose
    bytes no archive holds. The complete archive the rotation fetches after the weeklies
    (`v1-e34-t04`, on by default) holds the 09-15 week's bytes, every one of which the weeklies
    already uploaded, so it adds a manifest and no source.
    """
    expected = expected_publish()

    dry = run("caselist", "pull", "--dry-run")
    assert dry["exit_code"] == ExitCode.OK, dry
    assert dry["data"]["archives_downloaded"] == 0
    assert bucket.list_objects_v2(Bucket=BUCKET).get("Contents", []) == []
    assert not (installation / "data" / "inbox").exists()

    pulled = run("caselist", "pull")
    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = pulled["data"]
    assert data["archives_downloaded"] == 3 + 1
    assert data["openev_downloaded"] == 1
    assert data["objects_published"] == expected["totals"]["source_objects"] + 1
    assert data["snapshots_imported"] == [
        *(f"{SYNTHETIC_CASELIST} {week.snapshot.isoformat()}" for week in SNAPSHOTS),
        "openev 2026-policy",
        f"{SYNTHETIC_CASELIST} full/2026-09-15",
    ]

    # The report confirmed every week in the bucket, so retention took them out of the inbox
    # (v1-e34-t11), and the summary names each by caselist and date.
    weeks = [f"{SYNTHETIC_CASELIST} {week.snapshot.isoformat()}" for week in SNAPSHOTS]
    inbox = installation / "data" / "inbox"
    assert sorted(path.name for path in inbox.glob("*-weekly-*.zip")) == [], "a confirmed week stayed"
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["retention"]["outcome"] == "completed", stages.get("retention")
    removed = [one["name"] for one in data["inbox_retention"]["removed"] if one["kind"] == "weekly_archive"]
    assert removed == weeks
    assert [one["name"] for one in data["inbox_retention"]["removed"] if one["kind"] == "full_archive"] == [
        f"{SYNTHETIC_CASELIST} full/2026-09-15"
    ]

    assert stages["publish"]["outcome"] == "completed"
    assert stages["report"]["outcome"] == "completed"
    assert stages["parse"]["outcome"] == "skipped", "v1-e31-t06 has not shipped; it must skip, not fail"
    assert stages["landscape"]["outcome"] == "skipped"

    keys = {str(item.get("Key")) for item in bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])}
    for week in SNAPSHOTS:
        assert f"manifests/{SYNTHETIC_CASELIST}/{week.snapshot.isoformat()}.jsonl" in keys
    assert "manifests/openev/2026-policy.jsonl" in keys
    assert f"manifests/{SYNTHETIC_CASELIST}/full/2026-09-15.jsonl" in keys

    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["in_sync"] is True

    again = run("caselist", "pull")
    assert again["exit_code"] == ExitCode.OK, again
    assert again["data"]["nothing_new"] is True
    assert again["data"]["archives_downloaded"] == 0
    assert again["data"]["openev_downloaded"] == 0


def test_a_weekly_run_fetches_one_complete_archive_after_its_weeklies_and_says_why(
    installation: Path, bucket: S3Client, site: respx.MockRouter
) -> None:
    """v1-e34-t04: the rotation's decision, the fetch order, and its own manifest key."""
    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = pulled["data"]
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    decisions = {one["archive"]: one["decision"] for one in data["selections"]}
    assert decisions[full] == "download"
    fetched = [
        call.request.url.path.rsplit("/", 1)[-1]
        for call in site.calls
        if call.request.url.host == FILE_HOST[8:]
    ]
    assert fetched == [*(weekly_name(week.snapshot) for week in SNAPSHOTS), full]
    assert data["full_archive"]["fetch"] == SYNTHETIC_CASELIST
    assert "complete archive:" in {one["stage"]: one for one in data["stages"]}["select"]["reason"]
    # By hand, from the fixture's own tables: of what 09-01 and 09-08 held, the Harbor Classic
    # octafinals negative is gone with its path (taken down before 09-15): withdrawn 1. The Round 2
    # negative's first version is gone and its path holds the revision: superseded 1.
    imported = data["full_archive"]["imported"]
    assert [(one["snapshot"], one["withdrawn"], one["superseded"]) for one in imported] == [
        ("full/2026-09-15", 1, 1)
    ]

    again = run("caselist", "pull", "--dry-run")
    assert {one["archive"]: one["decision"] for one in again["data"]["selections"]}[
        full
    ] == "already_imported"


def test_a_camp_file_removed_from_another_machine_is_not_requested_again(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1-e34-t07 ac1, through the installed commands and the real composition root.

    The camp file is pulled, then removed with `caselist remove --execute`. The next pull runs as a
    machine that did not make the removal would: its own copy of the suppression list has no entry,
    and its inbox no longer holds the file. Only the bucket's copy of the list can keep the request
    away from OpenCaselist, so this fails if the pull's skip reads anything less than the union.
    """
    data = installation / "data"
    assert run("caselist", "pull")["exit_code"] == ExitCode.OK
    removed_file = hashlib.sha256(DOCUMENT_BODIES["estuary-solvency"]).hexdigest()
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    removed = run(
        "caselist",
        "remove",
        "--source",
        removed_file,
        "--request",
        "RM-2026-01",
        "--reason",
        "REQUESTED_BY_CAMP",
        "--execute",
    )
    assert removed["exit_code"] == ExitCode.OK, removed
    monkeypatch.delenv("DEBATE_REMOVAL_PROFILE")
    (data / "suppression" / "suppression-list.jsonl").unlink()
    for copy in (data / "inbox").glob(f"openev-{OPENEV_FILE_ID}-*"):
        copy.unlink()
    requested = sum(1 for call in site.calls if call.request.url.path.endswith("/download"))
    assert requested == 1

    again = run("caselist", "pull")

    assert again["exit_code"] == ExitCode.OK, again
    assert [one["decision"] for one in again["data"]["openev_selections"]] == ["skipped_as_removed"]
    assert again["data"]["openev_skipped_as_removed"] == 1
    assert sum(1 for call in site.calls if call.request.url.path.endswith("/download")) == requested


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
            raise StoreAccessDenied("GetObject", only or "the bucket", hint="a grant is missing")
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


@pytest.mark.parametrize(
    ("failure", "exit_code", "error_code"),
    [
        # A grant is not a login, and neither is an outage: both fail the import, on the store.
        ("access_denied", ExitCode.RETRIEVAL_FAILURE, "STORE_ACCESS_DENIED"),
        ("unavailable", ExitCode.RETRIEVAL_FAILURE, "STORE_UNAVAILABLE"),
        # A line nobody can read is the same line next week: a verdict.
        ("torn_line", ExitCode.DOMAIN_FAILURE, "UNREADABLE_APPEND_ONLY_RECORD"),
    ],
)
def test_a_bucket_copy_that_is_refused_unavailable_or_torn_still_fails_the_import_closed(
    installation: Path,
    bucket: S3Client,
    site: respx.MockRouter,
    camp_files: dict[str, tuple[dict[str, Any], bytes]],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    exit_code: ExitCode,
    error_code: str,
) -> None:
    """Only missing or expired credentials fall back. A denial, an outage or an unreadable list is
    not a login that timed out, and importing past it could bring a removed file back.

    The import stage records what stopped it, and the exit code follows (v1-e34-t13): `3` when the
    bucket refused or did not answer, which a later run may not meet, and `1` for the torn line.
    """
    assert run("caselist", "pull")["exit_code"] == ExitCode.OK
    list_two_new_camp_files(camp_files)
    if failure == "access_denied":
        expire_the_session(monkeypatch, only=SUPPRESSION_LIST_KEY, error=StoreAccessDenied)
    elif failure == "unavailable":
        expire_the_session(monkeypatch, only=SUPPRESSION_LIST_KEY, error=StoreUnavailable)
    else:
        bucket.put_object(Bucket=BUCKET, Key=SUPPRESSION_LIST_KEY, Body=b'{"schema_version":1,"act')

    again = run("caselist", "pull")

    assert again["exit_code"] == exit_code, again
    assert again["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(again)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "failed", stages["import"]
    assert stages["import"]["error_codes"] == [error_code]
    assert data["blobs_stored"] == 0
    assert data.get("suppression_list_local_copy_only") is None
    if failure == "access_denied":
        assert "docs/runbooks/evidence-store.md" in again["error"]["hint"]
        assert "aws sso login" not in json.dumps(again["error"])


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
# Failures a retry may cure, and the exit code each ends with (v1-e01-t20)
# ------------------------------------------------------------------------------------------------


def test_a_bucket_listing_that_does_not_answer_fails_publish_with_three_and_the_next_run_publishes(
    installation: Path, bucket: S3Client, site: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publish stage's plan lists the bucket first, and it answers 503.

    v1-e01-t20 let that escape the run as a `3`, with no summary, and nothing recorded the snapshots
    it had imported as owed: no later pull would have published them. It is now the publish stage
    failing on a store that did not answer. Still a `3`, with every week imported and owed, and the
    next run, once the bucket answers, publishes them without fetching anything again.
    """
    outage = {"on": True}
    list_objects = S3EvidenceObjectStore.list_objects

    async def unavailable(self: S3EvidenceObjectStore, prefix: str) -> Any:
        if outage["on"]:
            raise StoreUnavailable("ListObjectsV2", prefix, "simulated 503 SlowDown")
        return await list_objects(self, prefix)

    monkeypatch.setattr(S3EvidenceObjectStore, "list_objects", unavailable)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.RETRIEVAL_FAILURE, pulled
    assert pulled["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["import"]["outcome"] == "completed"
    assert (stages["publish"]["outcome"], stages["publish"]["error_codes"]) == (
        "failed",
        ["STORE_UNAVAILABLE"],
    )
    assert stages["report"]["outcome"] == "skipped"
    # Three weeklies, the complete archive and the camp release: all five imported, all five owed.
    assert len(data["snapshots_imported"]) == 5
    assert sorted(data["pending_publish"]) == sorted(data["snapshots_imported"])
    assert not bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/").get("Contents")
    downloads = len(site.calls)

    outage["on"] = False
    again = run("caselist", "pull")

    assert again["exit_code"] == ExitCode.OK, again
    data = run_summary(again)
    assert {one["stage"]: one["outcome"] for one in data["stages"]}["publish"] == "completed"
    assert data["pending_publish"] == []
    assert data["archives_downloaded"] == 0 and data["openev_downloaded"] == 0
    assert not any(
        call.request.url.host == "files.opencaselist.example.invalid" for call in site.calls[downloads:]
    )
    published = {one["Key"] for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/")["Contents"]}
    assert f"manifests/{SYNTHETIC_CASELIST}/{SNAPSHOTS[-1].snapshot.isoformat()}.jsonl" in published


@needs_permissions
def test_an_unreadable_blob_directory_fails_the_import_stage_with_three_and_names_its_role(
    installation: Path, bucket: S3Client, site: respx.MockRouter
) -> None:
    """The import stage folds the refusal into its own outcome and records what it was: a store
    that refused, which is the `3` it is in every other command. Before v1-e01-t20 it escaped as
    exit 70, "a bug"; from then until v1-e34-t13 it was a `1`, like a refused archive."""
    blobs = installation / "data" / BLOB_DIRECTORY
    blobs.mkdir(parents=True)

    with refused(blobs):
        pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.RETRIEVAL_FAILURE, pulled
    stages = {one["stage"]: one for one in run_summary(pulled)["stages"]}
    assert stages["import"]["outcome"] == "failed"
    assert stages["import"]["error_codes"] == ["STORE_ACCESS_DENIED"]
    assert "not allowed to read the blob directory" in stages["import"]["reason"]
    assert "the blob directory" in stages["import"]["hint"]
    assert "storage.data_dir" in pulled["error"]["hint"]
    assert str(installation) not in json.dumps([stages["import"], pulled["error"]["hint"]])


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
        raise StoreAccessDenied("HeadObject", f"s3://{BUCKET}/manifests/{caselist}/{snapshot}.jsonl")

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


def test_a_pending_work_file_that_cannot_be_read_fails_publish_with_one_and_is_left_for_a_person(
    installation: Path, bucket: S3Client, site: respx.MockRouter
) -> None:
    """The file was cut short by something other than the sync. The run cannot know what it owed, so
    it does not write over it: exit `1`, a verdict someone has to look at, with a hint that names
    the file by what it is for and never by where it is. What this run imported needs nothing from
    the file and is published all the same."""
    cut_short = b'{"publish": [{"caselist": "testcl26", "snap'
    (installation / "data").mkdir()
    (installation / "data" / PENDING_WORK_FILE).write_bytes(cut_short)

    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.DOMAIN_FAILURE, pulled
    assert pulled["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    data = run_summary(pulled)
    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "failed"
    assert stages["publish"]["error_codes"] == ["PENDING_WORK_UNREADABLE"]
    assert "the pending-work file under storage.data_dir" in stages["publish"]["hint"]
    assert pulled["error"]["hint"].startswith(stages["publish"]["hint"])
    assert (installation / "data" / PENDING_WORK_FILE).read_bytes() == cut_short
    assert stages["report"]["outcome"] == "completed"
    published = {one["Key"] for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/")["Contents"]}
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" in published
    assert "aws sso login" not in stage_text(pulled)
    assert str(installation) not in stage_text(pulled)
    assert str(Path.home()) not in stage_text(pulled)

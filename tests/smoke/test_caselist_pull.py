"""`debate-research caselist pull` end to end, as `validate-dev` runs it and as launchd will.

The weekly run in one check, against the installed build: the console script, the composition
root, a `dev` settings profile, the real OpenCaselist client, the real importers, the real
manifests, and a real publish to a bucket. Two things stand in for the world and nothing else does,
each a server the build reaches over loopback (`v1-e01-t21`, tests/smoke/stand_ins/): a local
OpenCaselist API and file host over https, serving synthetic responses, and moto in server mode for
S3. A bucket that refuses or fails a request does so from the server's side, with the error S3
would send; the build is never patched.

**This check is not marked `live`, and must not be.** A `live` marker would make the default
`-m "not slow and not live"` run collect it and skip it, so the one check covering the command the
schedule runs every week would look green in CI while never running (`tests/smoke/README.md`).

Until `v1-e01-t21` this module ran in pytest's own process, with respx and moto patching it. The
checks that replace part of the CLI itself (an adapter whose session expires part-way through a run,
botocore's own exceptions, the notifier, the clock) cannot reach an installed build, and are kept,
in-process, in `test_caselist_pull_in_process.py`, with the opt-in live check.

The archives are the invented ones from `tests/fixtures/caselist/` and the camp file is from
`tests/fixtures/openev/`; no real caselist content enters this repository
(`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.caselist.publish_expectations import expected_publish
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES
from tests.fixtures.permissions import needs_permissions, refused
from tests.smoke.installed_build import InstalledCli
from tests.smoke.stand_ins.opencaselist import OpenCaselistStandIn
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3StandIn

from debate_cli.exit_codes import ExitCode
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.local import BLOB_DIRECTORY

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUCKET = "debate-dev-evidence-pull-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
REMOVAL_PROFILE = "debate-dev-evidence-removal"
OPENEV_FILE_ID = 512
OPENEV_YEAR = 2026
OPENEV_FILENAME = "TSF-Estuary Solvency Advocate.docx"
SUPPRESSION_LIST_KEY = "manifests/_suppression/suppression-list.jsonl"

#: What S3 answers a call the permission set does not grant, and a bucket that has stopped answering.
DENIED = {"status": 403, "code": "AccessDenied", "message": "Access Denied"}
UNAVAILABLE = {"status": 503, "code": "SlowDown", "message": "Please reduce your request rate."}

THE_BUILD: list[InstalledCli] = []
"""The installed build the check in progress runs. `installation` puts it here, for the helpers
below, and takes it out again; a pytest process runs one check at a time, so there is only one."""


def build() -> InstalledCli:
    return THE_BUILD[-1]


def environment(**variables: str | None) -> None:
    """Set variables, or with `None` unset them, for every later command of the check in progress."""
    build().configure(**variables)


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


@pytest.fixture
def installation(
    installed_cli: InstalledCli,
    s3_stand_in: S3StandIn,
    opencaselist_stand_in: OpenCaselistStandIn,
    tmp_path: Path,
) -> Iterator[Path]:
    """A dev profile naming the stand-in's bucket and the stand-in API, with a token in the environment."""
    config = tmp_path / "aws-config"
    # The takedown profile too, for the check that removes the camp file (v1-e34-t07).
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (AWS_PROFILE_NAME, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = {MOTO_TEST_CREDENTIALS['aws_access_key_id']}\n"
            f"aws_secret_access_key = {MOTO_TEST_CREDENTIALS['aws_secret_access_key']}\n"
            for name in (AWS_PROFILE_NAME, REMOVAL_PROFILE)
        ),
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
        # A dev profile would pick the macOS notifier on a Mac; no check may notify (v1-e34-t03).
        'notifier = "none"\n'
        f'sync_caselists = ["{SYNTHETIC_CASELIST}"]\n'
        # The floor the settings allow. What this check is about is the run, not the pacing, and
        # six paced requests at the 1s default would put it over five seconds for nothing.
        "min_request_interval_seconds = 0.5\n"
        # The parse stage is on, as it is for the agent (`v1-e34-t17`). One worker, so that each
        # pull here starts one process and not the machine's cores less one.
        "[parse]\nworkers = 1\n"
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
        DEBATE_PROVIDERS__CASELIST_TOKEN="fixture-token-not-a-real-one",
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(credentials),
    )
    THE_BUILD.append(installed_cli)
    try:
        yield tmp_path
    finally:
        THE_BUILD.remove(installed_cli)


@pytest.fixture
def bucket(installation: Path, s3_stand_in: S3StandIn) -> S3Client:
    client = s3_stand_in.versioned_bucket(BUCKET)
    # Each profile is the role its name says: a takedown asks before it does anything (v1-e29-t08).
    sign_in(
        installation / "aws-credentials",
        {AWS_PROFILE_NAME: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE},
        iam=s3_stand_in.client("iam"),
        sts=s3_stand_in.client("sts"),
    )
    return client


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


class CampFiles(dict[str, tuple[dict[str, Any], bytes]]):
    """What OpenEv lists, by upstream path: the listing entry and the bytes `/download` serves.

    Served by the stand-in as it is changed: a check adds to it to have the next run list a new camp
    file. The client takes the leading `/` off a listed path before asking `/download` for it.
    """

    def __init__(self, stand_in: OpenCaselistStandIn, directory: Path) -> None:
        super().__init__()
        self.stand_in = stand_in
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        stand_in.serve_json("/openev", [])

    def __setitem__(self, path: str, entry: tuple[dict[str, Any], bytes]) -> None:
        super().__setitem__(path, entry)
        listed, body = entry
        served = self.directory / f"{listed['openev_id']}.docx"
        served.write_bytes(body)
        self.stand_in.serve_api_file("/download", served, query={"path": path.lstrip("/")})
        self.stand_in.serve_json("/openev", [one for one, _ in self.values()])


@pytest.fixture
def camp_files(installation: Path, opencaselist_stand_in: OpenCaselistStandIn) -> CampFiles:
    served = CampFiles(opencaselist_stand_in, installation / "camp-files")
    listed = camp_file(OPENEV_FILE_ID, "Tamarack", OPENEV_FILENAME)
    served[str(listed["path"])] = (listed, DOCUMENT_BODIES["estuary-solvency"])
    return served


@pytest.fixture
def site(
    installation: Path, camp_files: CampFiles, opencaselist_stand_in: OpenCaselistStandIn
) -> OpenCaselistStandIn:
    """OpenCaselist: three weekly archives, one full archive, and the OpenEv files in `camp_files`.

    The complete archive is served as the 09-15 weekly's bytes: the synthetic weeklies are
    cumulative, so the newest one holds what a complete archive of that date would.
    """
    zips = build_snapshot_zips(installation / "published")
    listing = [
        {
            "name": weekly_name(week.snapshot),
            "url": opencaselist_stand_in.serve_file(weekly_name(week.snapshot), zips[week.snapshot]),
        }
        for week in SNAPSHOTS
    ]
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    listing.append(
        {"name": full, "url": opencaselist_stand_in.serve_file(full, zips[SNAPSHOTS[-1].snapshot])}
    )
    opencaselist_stand_in.serve_json(f"/caselists/{SYNTHETIC_CASELIST}/downloads", listing)
    return opencaselist_stand_in


def keys_in(bucket: S3Client) -> set[str]:
    """Every key the stand-in's bucket holds."""
    return {str(item.get("Key")) for item in bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])}


def run(*arguments: str) -> dict[str, Any]:
    """Run one command asking for JSON, and return its envelope with the exit code on it."""
    result = build().run("--json", *arguments)
    envelope = result.envelope()
    envelope["exit_code"] = result.exit_code
    return envelope


def list_two_new_camp_files(camp_files: CampFiles) -> None:
    """513 holds the removed camp file's bytes under another camp's path; 514 is new material."""
    for listed, body in (
        (camp_file(513, "Brightwater", "BWW-Estuary Copy.docx"), DOCUMENT_BODIES["estuary-solvency"]),
        (camp_file(514, "Brightwater", "BWW-Orchard Kritik.docx"), DOCUMENT_BODIES["orchard-kritik"]),
    ):
        camp_files[str(listed["path"])] = (listed, body)


def run_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """The run summary, from `data` on success or the failure's `details` (`CASELIST_PULL_INCOMPLETE`)."""
    return envelope["data"] if envelope["data"] is not None else envelope["error"]["details"]


def stage_text(envelope: dict[str, Any]) -> str:
    """Everything the stages and the command's own hint say, as one string to search."""
    error = envelope["error"] or {}
    return json.dumps([run_summary(envelope)["stages"], error.get("message"), error.get("hint")])


PENDING_WORK_FILE = "caselist-sync-pending.json"
"""The pending-work file's name under the data directory, as the runbook gives it."""


def test_a_weekly_pull_downloads_imports_publishes_and_then_finds_nothing_new(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn
) -> None:
    """Goal criterion ac1, through the installed command.

    The publish count is the fixture's own hand-written total — `expected_publish.json` says the
    three synthetic weeks come to 14 distinct source objects — plus one for the camp file, whose
    bytes no archive holds. The complete archive the rotation fetches after the weeklies
    (`v1-e34-t04`, on by default) holds the 09-15 week's bytes, every one of which the weeklies
    already uploaded, so it adds a manifest and no source. The count includes the manifests since
    `v1-e34-t28`: one for each of the five snapshots imported, the three weeks, the camp release and
    the complete archive.
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
    assert data["objects_published"] == expected["totals"]["source_objects"] + 1 + 5
    assert data["manifests_published"] == 5
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
    assert stages["landscape"]["outcome"] == "skipped"

    # The parse stage (`v1-e34-t17`), by hand from the fixtures. Two caselists are parsed: the
    # weeklies', and `openev` for the camp file; the complete archive names none. The synthetic
    # weeks hold fourteen distinct bodies, of which one is a PDF and one a legacy `.doc`, and the
    # camp file is a fifteenth source. Nothing was parsed before, so both are full parses. The
    # documents are plain paragraphs, which hold no cards. The parsed store is one file per source
    # and three aggregates per caselist: (14 + 3) + (1 + 3) objects.
    assert stages["parse"]["outcome"] == "completed", stages["parse"]
    assert data["parse"] == {
        "caselists": 2,
        "full_parses": 2,
        "attempted": 15,
        "skipped": 0,
        "unsupported": 2,
        "failed": 0,
        "cards": 0,
        "uploaded": 21,
        "not_published": 0,
    }
    parsed = {key for key in keys_in(bucket) if key.startswith("parsed/")}
    assert len(parsed) == 21
    for caselist in (SYNTHETIC_CASELIST, "openev"):
        assert f"parsed/{caselist}/{DOCX_PARSER_VERSION}/index.jsonl" in parsed

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
    # A pull that imports nothing parses nothing, and sends nothing more to the bucket.
    assert again["data"]["parse"] is None
    assert {one["stage"]: one for one in again["data"]["stages"]}["parse"]["outcome"] == "skipped"
    assert {key for key in keys_in(bucket) if key.startswith("parsed/")} == parsed


def test_a_weekly_run_fetches_one_complete_archive_after_its_weeklies_and_says_why(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn
) -> None:
    """v1-e34-t04: the rotation's decision, the fetch order, and its own manifest key."""
    pulled = run("caselist", "pull")

    assert pulled["exit_code"] == ExitCode.OK, pulled
    data = pulled["data"]
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    decisions = {one["archive"]: one["decision"] for one in data["selections"]}
    assert decisions[full] == "download"
    fetched = [one.path.rsplit("/", 1)[-1] for one in site.requests() if one.server == "files"]
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
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn
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
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
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
    environment(DEBATE_REMOVAL_PROFILE=None)
    (data / "suppression" / "suppression-list.jsonl").unlink()
    for copy in (data / "inbox").glob(f"openev-{OPENEV_FILE_ID}-*"):
        copy.unlink()
    requested = sum(1 for one in site.requests() if one.path.endswith("/download"))
    assert requested == 1

    again = run("caselist", "pull")

    assert again["exit_code"] == ExitCode.OK, again
    assert [one["decision"] for one in again["data"]["openev_selections"]] == ["skipped_as_removed"]
    assert again["data"]["openev_skipped_as_removed"] == 1
    assert sum(1 for one in site.requests() if one.path.endswith("/download")) == requested


# ------------------------------------------------------------------------------------------------
# The AWS session behind the bucket's copy of the suppression list (v1-e34-t07, after PM review)
# ------------------------------------------------------------------------------------------------


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
    site: OpenCaselistStandIn,
    camp_files: CampFiles,
    s3_stand_in: S3StandIn,
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
    # The bucket's copy of the list, and only it, is refused, or not answered: one attempt each.
    # Reading it starts with a HEAD, which a list the bucket does not hold yet answers 404.
    if failure == "access_denied":
        s3_stand_in.refuse("HeadObject", "GetObject", key=SUPPRESSION_LIST_KEY, **DENIED)
    elif failure == "unavailable":
        environment(AWS_MAX_ATTEMPTS="1")
        s3_stand_in.refuse("HeadObject", "GetObject", key=SUPPRESSION_LIST_KEY, **UNAVAILABLE)
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


# ------------------------------------------------------------------------------------------------
# Failures a retry may cure, and the exit code each ends with (v1-e01-t20)
# ------------------------------------------------------------------------------------------------


def test_a_bucket_listing_that_does_not_answer_fails_publish_with_three_and_the_next_run_publishes(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn, s3_stand_in: S3StandIn
) -> None:
    """The publish stage's plan lists the bucket first, and it answers 503.

    v1-e01-t20 let that escape the run as a `3`, with no summary, and nothing recorded the snapshots
    it had imported as owed: no later pull would have published them. It is now the publish stage
    failing on a store that did not answer. Still a `3`, with every week imported and owed, and the
    next run, once the bucket answers, publishes them without fetching anything again.
    """
    # Every listing the build asks for is answered 503, once: a retry would meet the same.
    environment(AWS_MAX_ATTEMPTS="1")
    s3_stand_in.refuse("ListObjectsV2", **UNAVAILABLE)

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
    downloads = len(site.requests())

    s3_stand_in.stop_refusing()
    environment(AWS_MAX_ATTEMPTS=None)
    again = run("caselist", "pull")

    assert again["exit_code"] == ExitCode.OK, again
    data = run_summary(again)
    assert {one["stage"]: one["outcome"] for one in data["stages"]}["publish"] == "completed"
    assert data["pending_publish"] == []
    assert data["archives_downloaded"] == 0 and data["openev_downloaded"] == 0
    assert not any(one.server == "files" for one in site.requests()[downloads:])
    published = {
        str(one.get("Key"))
        for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/").get("Contents", [])
    }
    assert f"manifests/{SYNTHETIC_CASELIST}/{SNAPSHOTS[-1].snapshot.isoformat()}.jsonl" in published


@needs_permissions
def test_an_unreadable_blob_directory_fails_the_import_stage_with_three_and_names_its_role(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn
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
# What a publish did not finish is owed, whatever ended it (v1-e34-t18)
# ------------------------------------------------------------------------------------------------


def test_a_pending_work_file_that_cannot_be_read_fails_publish_with_one_and_is_left_for_a_person(
    installation: Path, bucket: S3Client, site: OpenCaselistStandIn
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
    published = {
        str(one.get("Key"))
        for one in bucket.list_objects_v2(Bucket=BUCKET, Prefix="manifests/").get("Contents", [])
    }
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" in published
    assert "aws sso login" not in stage_text(pulled)
    assert str(installation) not in stage_text(pulled)
    assert str(Path.home()) not in stage_text(pulled)

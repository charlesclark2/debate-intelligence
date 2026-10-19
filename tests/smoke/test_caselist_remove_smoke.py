"""`debate-research caselist remove` and `unsuppress` end to end, against the installed build.

The operator's whole takedown in one check, through the installed command: three synthetic weeks
imported and published to the dev bucket, a team's removal planned (and shown to change nothing),
refused without the takedown profile, executed with it, checked with `caselist status`, and then
attacked the way the world will attack it — a later archive that still holds the team's files,
imported and published as next Monday's — without the team's files coming back. Then a mistaken
removal reversed with `unsuppress`.

The bucket, and the STS that says which role a profile is signed in as, are moto in server mode: a
stand-in the build reaches over loopback through `storage.s3.endpoint_url` (`v1-e01-t21`,
tests/smoke/stand_ins/). Until then these checks ran in pytest's own process under `mock_aws()`,
which the installed build could not see. Where a check used to patch the S3 adapter, to refuse a
version listing, to watch what `caselist status` asked for, or to lose the bucket part-way through a
takedown, the stand-in now does it from the server's side: it refuses the request with the error S3
would send, or records the request (tests/smoke/stand_ins/s3.py). The build is never patched.

**Not marked `live`, and must not be.** It needs no deployed environment, and the build's network
guard allows the stand-in and nothing else (tests/smoke/README.md). Exercising the runbook against
the real dev bucket is an operator step (session report, Operator follow-ups).
"""

from __future__ import annotations

import configparser
import hashlib
import json
import stat
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import ANY

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    _docx,  # pyright: ignore[reportPrivateUsage]
    build_snapshot_zips,
)
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH, build_download_zips
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS
from tests.smoke.installed_build import CliRun, InstalledCli
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3Request, S3StandIn

from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

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

THE_BUILD: list[InstalledCli] = []
"""The installed build the check in progress runs. `installation` puts it here, for the helpers
below, and takes it out again; a pytest process runs one check at a time, so there is only one."""


def build() -> InstalledCli:
    return THE_BUILD[-1]


def environment(**variables: str | None) -> None:
    """Set variables, or with `None` unset them, for every later command of the check in progress."""
    build().configure(**variables)


def invoke(*arguments: str, width: int = 80) -> CliRun:
    """One command as a person reads it: no `--json`, on a terminal `width` columns wide."""
    return build().run(*arguments, env={"COLUMNS": str(width)})


@pytest.fixture
def installation(installed_cli: InstalledCli, s3_stand_in: S3StandIn, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming the stand-in's bucket, and both SSO profiles in an AWS config."""
    config = tmp_path / "aws-config"
    credentials = tmp_path / "aws-credentials"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = {MOTO_TEST_CREDENTIALS['aws_access_key_id']}\n"
            f"aws_secret_access_key = {MOTO_TEST_CREDENTIALS['aws_secret_access_key']}\n"
            for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)
        ),
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment_name in ("dev", "prod"):
        (profiles / f"{environment_name}.toml").write_text(
            f'[storage]\ndata_dir = "{tmp_path / environment_name}"\n'
            f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{OPERATOR_PROFILE}"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    # Each environment's own data directory, as its profile names it, rather than the harness's one.
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
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
        {OPERATOR_PROFILE: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE},
        iam=s3_stand_in.client("iam"),
        sts=s3_stand_in.client("sts"),
    )
    return client


def access_key_of(installation: Path, profile: str) -> str:
    """The access key `sign_in` wrote for `profile`: how the stand-in's record says who signed."""
    signed_in = configparser.ConfigParser()
    signed_in.read(installation / "aws-credentials", encoding="utf-8")
    return signed_in[profile]["aws_access_key_id"]


def run(*arguments: str) -> dict[str, Any]:
    """Run one command asking for JSON, and return its envelope with the exit code."""
    result = build().run("--json", *arguments)
    envelope = result.envelope()
    envelope["exit_code"] = result.exit_code
    return envelope


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
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert done["data"]["outcome"] == "COMPLETED"
    assert done["data"]["inbox_exists"] is False and not (data_dir / "inbox").exists(), "none created"
    keys = {key for key, _ in versions(bucket)}
    for sha in EXCLUSIVE:
        assert not any(sha in key for key in keys)
    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status

    # Next Monday: an archive that still holds the team's files, in order. Nothing of theirs comes back.
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
    result = invoke(*REMOVE)

    assert result.exit_code == ExitCode.OK, result.output
    for heading in (
        "DRY RUN: nothing was changed.",
        "WILL BE REMOVED, everywhere, and suppressed: 3 file(s)",
        "SHARED, KEPT: 1 file(s)",
        "MANIFESTS REWRITTEN",
        "SUPPRESSION ENTRIES appended to the list, here and in the bucket: 5",
        "FOR THE CONFIRMATION TO THE REQUESTER",
        "TO CARRY IT OUT",
        "DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal",
        "): does not exist, so there is nothing to check or change",
    ):
        assert heading in result.stdout, heading


def test_prod_is_refused_without_confirm_prod(installation: Path, bucket: S3Client, published: Any) -> None:
    # A prod installation reaches no stand-in: the endpoint is the one setting it would refuse. The
    # refusal under test comes before anything is built, so nothing is reached at all.
    environment(DEBATE_ENV="prod", DEBATE_STORAGE__S3__ENDPOINT_URL=None)
    environment(DEBATE_REMOVAL_PROFILE="debate-prod-evidence-removal")

    refused = run(*REMOVE, "--execute")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_a_mistaken_removal_is_reversed_and_the_file_is_imported_again(
    installation: Path, bucket: S3Client, published: dict[date, Path]
) -> None:
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
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
    result = invoke(
        "caselist", "remove", "--source", unknown, "--request", "RM-2026-04", "--reason", "POLICY"
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert "held nowhere in this environment: it is only suppressed" in result.stdout
    assert "SUPPRESSION ENTRIES appended to the list, here and in the bucket: 1" in result.stdout


def test_a_removal_profile_missing_from_the_aws_config_is_refused_with_nothing_changed(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    environment(DEBATE_REMOVAL_PROFILE="debate-dev-evidence-removal-typo")
    before = (tree(installation / "dev"), versions(bucket))

    refused = run(*REMOVE, "--execute")

    # A configuration error, not an expired session: exit 1, and what it names is the variable to
    # correct (v1-e29-t07). Until then the adapter called it StoreCredentialsExpired, the run ended
    # 3, "a retry may succeed", and the hint was a command that wrote to the AWS config. It is the
    # takedown's own refusal, so that it says nothing was deleted (v1-e29-t08).
    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE
    assert refused["error"]["code"] == "TAKEDOWN_PREFLIGHT_FAILED"
    assert "STORE_PROFILE_NOT_CONFIGURED" in refused["error"]["message"]
    assert "debate-dev-evidence-removal-typo" in refused["error"]["message"]
    assert "DEBATE_REMOVAL_PROFILE" in refused["error"]["message"]
    assert "nothing was deleted" in refused["error"]["message"]
    assert "DEBATE_REMOVAL_PROFILE" in refused["error"]["hint"]
    assert "aws sso login" not in json.dumps(refused["error"])
    assert "aws configure" not in json.dumps(refused["error"])
    assert str(installation) not in json.dumps(refused["error"])
    assert (tree(installation / "dev"), versions(bucket)) == before, "nothing was deleted"


def test_the_everyday_profile_named_for_a_takedown_is_refused_before_anything_is_written(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """`DEBATE_REMOVAL_PROFILE` naming the everyday profile, which is easy to do: one suffix apart.

    The takedown asks the account which role the profile is signed in as before it lists or writes
    (v1-e29-t08). Moto's bucket would let this profile run the whole removal, so the unchanged
    bucket below is the command's doing and not a refused request's.
    """
    environment(DEBATE_REMOVAL_PROFILE=OPERATOR_PROFILE)
    before = (tree(installation / "dev"), versions(bucket))

    refused = run(*REMOVE, "--execute")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, "a setting to correct, not something to retry"
    assert refused["error"]["code"] == "TAKEDOWN_PREFLIGHT_FAILED"
    assert "NOT_THE_TAKEDOWN_ROLE" in refused["error"]["message"]
    assert "DebateDevEvidenceOperator" in refused["error"]["message"]
    assert "nothing was deleted" in refused["error"]["message"]
    assert REMOVAL_PROFILE in refused["error"]["hint"]
    assert "aws sso login" not in json.dumps(refused["error"])
    assert (tree(installation / "dev"), versions(bucket)) == before, "no probe, no entry, nothing deleted"


def test_a_removal_that_completes_but_cannot_be_logged_says_it_completed(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """This machine's removal log refuses the append after every deletion has succeeded."""
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    local_log = installation / "dev" / "suppression" / "removal-log.jsonl"
    local_log.parent.mkdir(parents=True, exist_ok=True)
    local_log.touch(mode=0o400)

    result = invoke(*REMOVE, "--execute", width=100)

    text = " ".join(result.output.replace("│", " ").split())
    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert "REMOVAL_COMPLETED_UNLOGGED" in text
    assert "the removal completed: 12 record(s), 3 local file(s)" in text
    assert "record these counts in the register" in text.lower()
    assert "failed" not in text.lower() and "stopped part-way" not in text
    keys = {key for key, _ in versions(bucket)}
    for sha in EXCLUSIVE:
        assert not any(sha in key for key in keys), "the deletes happened"


def test_the_download_inbox_is_listed_by_the_dry_run_and_purged_by_the_execution(
    installation: Path, bucket: S3Client, published: dict[date, Path]
) -> None:
    """`v1-e30-t09`: the inbox `caselist pull` downloads into, where the composition root puts it.

    The three weeks the store imported, as the pull names them, and next Monday's archive (the 09-15
    bytes again) downloaded but not yet imported. The imported weeks go; next Monday's is rewritten
    without the team's files, never deleted, because the next pull imports it from there.
    """
    inbox = installation / "dev" / "inbox"
    inbox.mkdir(parents=True)
    for week in SNAPSHOTS:
        (inbox / f"{SYNTHETIC_CASELIST}-weekly-{week.snapshot}.zip").write_bytes(
            published[week.snapshot].read_bytes()
        )
    waiting = inbox / f"{SYNTHETIC_CASELIST}-weekly-2026-09-22.zip"
    waiting.write_bytes(published[SNAPSHOTS[-1].snapshot].read_bytes())
    before = tree(inbox)

    planned = run(*REMOVE)
    shown = invoke(*REMOVE)

    assert planned["exit_code"] == ExitCode.OK, planned
    assert [(one["name"], one["action"]) for one in planned["data"]["inbox"]] == [
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-01.zip", "delete"),
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-08.zip", "delete"),
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-15.zip", "delete"),
        (waiting.name, "rewrite"),
    ]
    assert "DOWNLOAD INBOX (inbox in the data directory): 4 file(s) hold removed files." in shown.stdout
    assert tree(inbox) == before, "the dry run changed the inbox"

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    entry = json.loads(done["data"]["log_entry"])
    assert (entry["inbox_files_deleted"], entry["inbox_files_rewritten"]) == (3, 1)
    assert sorted(path.name for path in inbox.iterdir()) == [waiting.name]
    with zipfile.ZipFile(waiting) as archive:
        held = {hashlib.sha256(archive.read(info)).hexdigest() for info in archive.infolist()}
        names = archive.namelist()
    assert not held & EXCLUSIVE and not any("Maple Grove/QX/" in name for name in names)
    assert any("Cedar Hollow/ZaLu/" in name for name in names), "another team's files are kept"


# ------------------------------------------------------------------------------------------------
# Later uploads at the removed path (v1-e30-t11)
# ------------------------------------------------------------------------------------------------

#: The synthetic caselist's Round 2 negative: one path, first disclosed on 09-01 and revised in place
#: the week after (`tests/fixtures/caselist/build_synthetic_archives.py`), so the 09-01 weekly holds
#: the first version and the 09-08 and 09-15 weeklies hold the revision.
FIRST_VERSION = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-first"]).hexdigest()
REVISION = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-revised"]).hexdigest()
LATER_UPLOADS_REQUEST = ("--request", "RM-2026-03", "--reason", "REQUESTED_BY_TEAM")
REMOVE_FIRST_VERSION = ("caselist", "remove", "--source", FIRST_VERSION, *LATER_UPLOADS_REQUEST)
REMOVE_REVISION = ("caselist", "remove", "--source", REVISION, *LATER_UPLOADS_REQUEST)
#: What the plan's JSON may not carry: a school, a team code, a tournament, a round, a file name.
IDENTIFYING = ("Maple Grove", "QX", "Cedar Hollow", "ZaLu", "Grove City", "Bayview", "Round", ".docx")


def raw_json(*arguments: str) -> str:
    result = build().run("--json", *arguments)
    assert result.exit_code == ExitCode.OK, result.output
    return result.stdout


def bucket_holds(client: S3Client, sha: str) -> bool:
    return any(sha in key for key, _ in versions(client))


def test_the_dry_run_lists_a_later_upload_by_digest_caselist_and_snapshot_and_execute_removes_both(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    planned = run(*REMOVE_FIRST_VERSION)

    assert planned["exit_code"] == ExitCode.OK, planned
    assert planned["data"]["later_uploads"] == [
        {
            "sha256": REVISION,
            "sha256_prefix": REVISION[:12],
            "relation": "later",
            "of_sha256": FIRST_VERSION,
            "caselist": SYNTHETIC_CASELIST,
            "snapshots": ["2026-09-08", "2026-09-15"],
            "inbox_snapshots": [],
            "openev_ids": [],
            "same_path_by": "caselist_path",
            "outcome": "removed",
        }
    ]
    assert planned["data"]["later_uploads_added"] == 1 and planned["data"]["only_named"] is False
    assert [(one["sha256"], one["inclusion"]) for one in planned["data"]["sources"]] == [
        (FIRST_VERSION, "named"),
        (REVISION, "later_upload"),
    ]
    assert bucket_holds(bucket, FIRST_VERSION) and bucket_holds(bucket, REVISION), "a dry run"

    shown = invoke(*REMOVE_FIRST_VERSION).stdout
    assert "LATER UPLOADS AT A REMOVED PATH, ADDED TO THIS PLAN: 1 file(s)" in shown
    assert (
        f"later upload of sha256 {FIRST_VERSION[:12]} in {SYNTHETIC_CASELIST}, held in 2026-09-08, "
        "2026-09-15: removed everywhere"
    ) in shown
    confirm = shown[shown.index("TO CARRY IT OUT") :]
    assert (
        "This plan covers the 1 file(s) named, and adds 1 later upload(s) at the removed path(s)." in confirm
    )
    assert "--only-named" in confirm and "--only-named --execute" not in confirm

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert json.loads(done["data"]["log_entry"])["removed_sha256"] == sorted([FIRST_VERSION, REVISION])
    assert not bucket_holds(bucket, FIRST_VERSION) and not bucket_holds(bucket, REVISION)
    blobs = installation / "dev" / "blobs" / "sha256"
    for sha in (FIRST_VERSION, REVISION):
        assert not (blobs / sha[0:2] / sha[2:4] / sha).exists()
    assert run("caselist", "status")["exit_code"] == ExitCode.OK


def test_only_named_removes_the_named_version_and_leaves_the_later_upload(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    shown = invoke(*REMOVE_FIRST_VERSION, "--only-named").stdout
    assert "LATER UPLOADS AT A REMOVED PATH, LEFT IN PLACE (--only-named): 1 file(s)" in shown
    confirm = shown[shown.index("TO CARRY IT OUT") :]
    assert "the 1 file(s) named only; 1 later upload(s) at the removed path(s) are left in place" in confirm
    assert "--only-named --execute" in confirm, "the printed command carries the flag"

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--only-named", "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert done["data"]["only_named"] is True and done["data"]["later_uploads_added"] == 0
    assert [one["outcome"] for one in done["data"]["later_uploads"]] == ["left_in_place"]
    assert json.loads(done["data"]["log_entry"])["removed_sha256"] == [FIRST_VERSION]
    assert not bucket_holds(bucket, FIRST_VERSION)
    assert bucket_holds(bucket, REVISION)
    assert (installation / "dev" / "blobs" / "sha256" / REVISION[0:2] / REVISION[2:4] / REVISION).exists()
    assert run("caselist", "status")["exit_code"] == ExitCode.OK


def test_an_earlier_version_is_listed_and_not_removed(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    shown = invoke(*REMOVE_REVISION).stdout
    assert "EARLIER VERSIONS AT A REMOVED PATH, NOT REMOVED: 1 file(s)" in shown
    assert "LATER UPLOADS AT A REMOVED PATH" not in shown
    assert "This plan covers the 1 file(s) named, and adds 0 later upload(s)" in shown

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_REVISION, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert [
        (one["sha256"], one["relation"], one["snapshots"]) for one in done["data"]["earlier_versions"]
    ] == [(FIRST_VERSION, "earlier", ["2026-09-01"])]
    assert bucket_holds(bucket, FIRST_VERSION) and not bucket_holds(bucket, REVISION)


def test_the_plans_json_names_no_school_team_path_or_file(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """`--source` with a later upload, `--team` with a withdrawn file, and an executed removal.

    The text of the same plans names them, as it always has: that is the operator's terminal.
    """
    assert "Maple Grove/QX/" in invoke(*REMOVE_FIRST_VERSION).stdout

    for arguments in (REMOVE_FIRST_VERSION, REMOVE, (*REMOVE, "--include-shared")):
        emitted = raw_json(*arguments)
        assert json.loads(emitted)["data"]["sources"], "a plan with something in it"
        assert not [name for name in IDENTIFYING if name in emitted], arguments

    team = json.loads(raw_json(*REMOVE))["data"]
    assert team["selector"] == {"kind": "TEAM", "caselist": SYNTHETIC_CASELIST}
    assert sum(len(source["disclosures"]) for source in team["sources"]) == 9
    assert sum(len(source["withdrawn_disclosures"]) for source in team["sources"]) == 2

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    executed = raw_json(*REMOVE_FIRST_VERSION, "--execute")
    assert json.loads(executed)["data"]["applied"] is True
    assert not [name for name in IDENTIFYING if name in executed]


# ------------------------------------------------------------------------------------------------
# A --source plan counts only the other teams (v1-e30-t10)
# ------------------------------------------------------------------------------------------------

#: The Round 1 affirmative: Maple Grove/QX discloses it and, from 09-08, so does Cedar Hollow/ZaLu.
#: Two holding teams, so one other than the one whose file is removed.
HELD_BY_TWO_TEAMS = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()
#: The keys of one source in the plan's JSON, as `v1-e30-t11` settled them.
SOURCE_KEYS = {
    "sha256", "inclusion", "disposition", "byte_size", "format", "other_teams", "camp_file_holders",
    "kept_in", "already_suppressed", "disclosures", "camp_files", "withdrawn_disclosures", "local_blob",
    "deletes_source_record",
}  # fmt: skip


def test_a_source_plan_for_a_file_one_team_holds_says_nothing_about_other_teams(
    installation: Path, bucket: S3Client, published: dict[date, Path]
) -> None:
    remove = ("caselist", "remove", "--source", BAYVIEW, *LATER_UPLOADS_REQUEST)

    shown = invoke(*remove).stdout
    planned = run(*remove)

    (line,) = [line for line in shown.splitlines() if BAYVIEW in line and line.lstrip().startswith("1.")]
    assert "other team" not in line and "also held" not in line, line
    assert "other team" not in shown
    (source,) = planned["data"]["sources"]
    assert source["other_teams"] == 0
    assert set(source) == SOURCE_KEYS


def test_a_source_plan_for_a_file_two_teams_hold_counts_one_other_team(
    installation: Path, bucket: S3Client, published: dict[date, Path]
) -> None:
    remove = ("caselist", "remove", "--source", HELD_BY_TWO_TEAMS, *LATER_UPLOADS_REQUEST)

    shown = invoke(*remove).stdout
    planned = run(*remove)

    (line,) = [
        line for line in shown.splitlines() if HELD_BY_TWO_TEAMS in line and line.lstrip().startswith("1.")
    ]
    assert line.endswith("; also held by 1 other team(s))"), line
    (source,) = planned["data"]["sources"]
    assert source["disposition"] == "skip_shared"
    assert source["other_teams"] == 1
    assert set(source) == SOURCE_KEYS


# ------------------------------------------------------------------------------------------------
# What a removal left behind, in `caselist status` (v1-e30-t10)
# ------------------------------------------------------------------------------------------------

#: `caselist status` with the everyday profile only. The takedown profile names nothing that exists,
#: so a status that built a client with it would fail instead of reporting.
NO_SUCH_PROFILE = "debate-no-such-profile"
#: After the removal under `RM-2026-03`, which touched the caselist (`v1-e30-t15`). Its completion is
#: this machine's clock at the time the test runs: the tests that need it read it from the log.
COMPLETED_BY_THE_REMOVAL = {"request_id": "RM-2026-03", "completed_at": ANY}
NOTHING_LEFT = {
    "caselist": SYNTHETIC_CASELIST,
    "checked": True,
    "not_checked_reason": None,
    "current_objects": 0,
    "noncurrent_versions": 0,
    "delete_markers": 0,
    "files": [],
    "older_versions": [],
    "older_than": COMPLETED_BY_THE_REMOVAL,
}


def raw_key(sha: str) -> str:
    return f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}"


def every_version(client: S3Client) -> list[tuple[str, str, str]]:
    """Every data version and delete marker in the bucket."""
    listed = client.list_object_versions(Bucket=BUCKET)
    return sorted(
        [(str(v.get("Key")), str(v.get("VersionId")), "version") for v in listed.get("Versions", [])]
        + [(str(m.get("Key")), str(m.get("VersionId")), "marker") for m in listed.get("DeleteMarkers", [])]
    )


def deletes_or_version_reads(asked: list[S3Request]) -> list[S3Request]:
    """The requests that deleted anything or fetched a version by its id: none of `status`'s business."""
    return [
        one
        for one in asked
        if one.operation in {"DeleteObject", "DeleteObjects"}
        or (one.operation == "GetObject" and one.version_id)
    ]


def status_as_a_person_reads_it() -> str:
    result = invoke("caselist", "status", width=200)
    return " ".join((result.stdout + result.stderr).split())


@pytest.fixture
def removed_with_its_later_upload(installation: Path, bucket: S3Client, published: Any) -> None:
    """The first version removed by `--source`, and the revision with it as a later upload."""
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert json.loads(done["data"]["log_entry"])["removed_sha256"] == sorted([FIRST_VERSION, REVISION])
    environment(DEBATE_REMOVAL_PROFILE=NO_SUCH_PROFILE)


@pytest.fixture
def versions_left_under_a_delete_marker(removed_with_its_later_upload: None, bucket: S3Client) -> None:
    """Two versions of the later upload put back at its key, then hidden by a delete with no version id.

    What a delete that is not the takedown's leaves: no plain listing shows the key, and both
    versions can be restored.
    """
    for body in (b"one version", b"another version"):
        bucket.put_object(Bucket=BUCKET, Key=raw_key(REVISION), Body=body)
    bucket.delete_object(Bucket=BUCKET, Key=raw_key(REVISION))


def test_status_after_a_complete_removal_says_it_checked_and_nothing_is_left(
    installation: Path, bucket: S3Client, removed_with_its_later_upload: None
) -> None:
    status = run("caselist", "status")

    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["removal_residue"] == [NOTHING_LEFT]
    assert status["data"]["removals_not_checked"] == []
    shown = status_as_a_person_reads_it()
    assert (
        "No version of a removed file is left under raw/ or parsed/, and no manifest or aggregate version "
        "is older than a removal that touched its caselist (1 caselist(s) checked)."
    ) in shown
    assert "noncurrent manifest versions are not read" not in shown


def test_versions_of_a_later_upload_left_under_a_delete_marker_fail_status_by_prefix_and_count(
    installation: Path, bucket: S3Client, versions_left_under_a_delete_marker: None
) -> None:
    """The later upload, not the file the request named: the report works from the suppression list."""
    before = every_version(bucket)

    status = run("caselist", "status")
    shown = status_as_a_person_reads_it()

    assert status["exit_code"] == ExitCode.DOMAIN_FAILURE, status
    error = status["error"]
    assert error["code"] == "REMOVAL_RESIDUE"
    assert all(entry["in_sync"] for entry in error["details"]["snapshots"]), "no snapshot differs"
    assert error["details"]["in_sync"] is False
    assert error["details"]["removal_residue"] == [
        {
            "caselist": SYNTHETIC_CASELIST,
            "checked": True,
            "not_checked_reason": None,
            "current_objects": 0,
            "noncurrent_versions": 2,
            "delete_markers": 1,
            "files": [
                {
                    "sha256_prefix": REVISION[:12],
                    "current_objects": 0,
                    "noncurrent_versions": 2,
                    "delete_markers": 1,
                }
            ],
            "older_versions": [],
            "older_than": COMPLETED_BY_THE_REMOVAL,
        }
    ]
    assert error["message"] == (
        f"the bucket still holds versions of 1 removed file(s): {SYNTHETIC_CASELIST}: 0 current object(s), "
        f"2 noncurrent version(s) and 1 delete marker(s) of 1 file(s) (sha256 {REVISION[:12]})"
    )
    assert "docs/runbooks/caselist-removal.md" in error["hint"]
    assert f"sha256 {REVISION[:12]}" in shown and "2 noncurrent version(s)" in shown
    # Digest prefixes and counts only: no whole digest, and nothing a manifest row holds.
    reported = json.dumps([error["details"]["removal_residue"], error["message"], error["hint"]]) + shown
    assert REVISION not in reported and FIRST_VERSION not in reported
    for identifying in IDENTIFYING:
        assert identifying not in reported, identifying
    assert every_version(bucket) == before, "status changed the bucket"


def test_a_refused_version_listing_says_not_checked_and_never_that_nothing_is_left(
    installation: Path,
    bucket: S3Client,
    versions_left_under_a_delete_marker: None,
    s3_stand_in: S3StandIn,
) -> None:
    """The versions are there. A profile without the grant cannot see them, and says so.

    The bucket refuses the listing as S3 refuses a call the permission set does not grant.
    """
    s3_stand_in.refuse("ListObjectVersions", status=403, code="AccessDenied", message="Access Denied")

    status = run("caselist", "status")
    shown = status_as_a_person_reads_it()

    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["removal_residue"] == [
        {
            "caselist": SYNTHETIC_CASELIST,
            "checked": False,
            "not_checked_reason": "STORE_ACCESS_DENIED",
            "current_objects": None,
            "noncurrent_versions": None,
            "delete_markers": None,
            "files": None,
            "older_versions": None,
            "older_than": None,
        }
    ]
    assert f"Removal residue NOT CHECKED for {SYNTHETIC_CASELIST}" in shown
    assert "No version of a removed file is left" not in shown


def test_status_reports_residue_with_the_everyday_profile_and_never_deletes_or_downloads_a_version(
    installation: Path,
    bucket: S3Client,
    versions_left_under_a_delete_marker: None,
    s3_stand_in: S3StandIn,
) -> None:
    """Who signed each listing, and that nothing deleted or fetched a version, from the bucket's side."""
    assert build().environment()["DEBATE_REMOVAL_PROFILE"] == NO_SUCH_PROFILE
    mark = len(s3_stand_in.requests())

    status = run("caselist", "status")

    assert status["exit_code"] == ExitCode.DOMAIN_FAILURE, status
    assert status["error"]["code"] == "REMOVAL_RESIDUE"
    asked = s3_stand_in.requests_since(mark)
    listings = {one.access_key for one in asked if one.operation == "ListObjectVersions"}
    assert listings == {access_key_of(installation, OPERATOR_PROFILE)}, listings
    assert deletes_or_version_reads(asked) == [], "caselist status deleted or downloaded an object version"


def test_a_takedown_stopped_among_a_later_uploads_versions_shows_in_status_until_the_rerun(
    installation: Path, bucket: S3Client, published: Any, s3_stand_in: S3StandIn
) -> None:
    """The runbook's loop: a run stops, `caselist status` says what is left, the same command finishes it.

    The later upload's object has three versions. The run deletes the named file's object, then the
    first, current, version of the later upload's, and loses the bucket. S3 makes the next version
    current, so one current object and one noncurrent version are left, of the later upload alone.
    """
    for body in (b"a second version", b"a third version"):
        bucket.put_object(Bucket=BUCKET, Key=raw_key(REVISION), Body=body)

    # The first delete of a later-upload version goes through, and every one after it is answered
    # 503, as a bucket that has stopped answering is. One attempt each: a retry would meet the same.
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE, AWS_MAX_ATTEMPTS="1")
    with s3_stand_in.refusing(
        "DeleteObject",
        key_contains=REVISION,
        after=1,
        status=503,
        code="SlowDown",
        message="Reduce your request rate.",
    ):
        incomplete = run(*REMOVE_FIRST_VERSION, "--execute")
    environment(AWS_MAX_ATTEMPTS=None)
    assert incomplete["exit_code"] == ExitCode.RETRIEVAL_FAILURE, incomplete

    left = run("caselist", "status")

    assert left["exit_code"] == ExitCode.DOMAIN_FAILURE
    # The run stopped before any manifest was rewritten, so the snapshots differ too, and that is
    # the code. The residue is in the details beside them.
    assert left["error"]["code"] == "CASELIST_DRIFT"
    (residue,) = left["error"]["details"]["removal_residue"]
    assert residue["files"] == [
        {"sha256_prefix": REVISION[:12], "current_objects": 1, "noncurrent_versions": 1, "delete_markers": 0}
    ]

    finished = run(*REMOVE_FIRST_VERSION, "--execute")
    assert finished["exit_code"] == ExitCode.OK, finished

    clean = run("caselist", "status")
    assert clean["exit_code"] == ExitCode.OK, clean
    assert clean["data"]["removal_residue"] == [NOTHING_LEFT]


def test_residue_a_completed_removal_left_is_cleared_by_naming_the_file_under_the_same_request(
    installation: Path,
    bucket: S3Client,
    versions_left_under_a_delete_marker: None,
) -> None:
    """The runbook's other loop: every snapshot agrees, and the version listing still shows a file.

    The original command finds nothing left to do, because nothing shows the later upload at the
    removed path any more. Naming the file by its own sha256, under the same request, plans its
    three versions (two data versions and the delete marker) and removes them.
    """
    assert "Nothing is left to remove" in invoke(*REMOVE_FIRST_VERSION).stdout
    name_it = ("caselist", "remove", "--source", REVISION, *LATER_UPLOADS_REQUEST)

    shown = invoke(*name_it, width=200).stdout

    assert "already suppressed by this request: finishing what a previous run left" in shown
    assert f"{raw_key(REVISION)}  (3 version(s))" in shown

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*name_it, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert not bucket_holds(bucket, REVISION)
    assert not any(REVISION in key for key, _, _ in every_version(bucket)), "the delete marker went too"

    clean = run("caselist", "status")
    assert clean["exit_code"] == ExitCode.OK, clean
    assert clean["data"]["removal_residue"] == [NOTHING_LEFT]


# ------------------------------------------------------------------------------------------------
# Manifest and aggregate versions older than a removal (v1-e30-t15)
# ------------------------------------------------------------------------------------------------

AGGREGATE = f"parsed/{SYNTHETIC_CASELIST}/2026.10.10-docx-2/index.jsonl"
REMOVAL_LOG = "manifests/_suppression/removal-log.jsonl"
SCOPES = "manifests/_suppression/removal-scopes.jsonl"


def body_of(client: S3Client, key: str) -> str:
    return client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()


def completion_of_the_removal(client: S3Client) -> datetime:
    """When `RM-2026-03` completed, from the bucket's removal log: what the tests set times against."""
    entries = [json.loads(line) for line in body_of(client, REMOVAL_LOG).splitlines()]
    return max(
        datetime.fromisoformat(entry["recorded_at"])
        for entry in entries
        if entry["request_id"] == "RM-2026-03" and entry["outcome"] == "COMPLETED"
    )


def a_manifest_the_removal_rewrote(client: S3Client) -> str:
    (scope,) = [json.loads(line) for line in body_of(client, SCOPES).splitlines()]
    return str(scope["manifest_rewrites"][0]["key"])


def put_older(client: S3Client, stand_in: S3StandIn, key: str, body: bytes, written: datetime) -> None:
    """Put a version beneath the current one, as if written at `written`. S3 lets no client set a
    version's time; the stand-in sets it in moto's store, and keeps the versions in that order."""
    version_id = client.put_object(Bucket=BUCKET, Key=key, Body=body)["VersionId"]
    stand_in.backdate(BUCKET, key, version_id, written.astimezone(UTC))


def a_member_row_of(sha: str) -> bytes:
    return (json.dumps({"kind": "member", "path": "a path", "sha256": sha}) + "\n").encode()


@pytest.fixture
def an_old_manifest_version(
    removed_with_its_later_upload: None, bucket: S3Client, s3_stand_in: S3StandIn
) -> str:
    """A day before the removal, a version of a manifest it rewrote, naming the file it removed.

    What a purge that did not happen leaves: a build from before the purge, or a run that stopped.
    Returns the manifest's key.
    """
    manifest = a_manifest_the_removal_rewrote(bucket)
    put_older(
        bucket,
        s3_stand_in,
        manifest,
        a_member_row_of(FIRST_VERSION),
        completion_of_the_removal(bucket) - timedelta(days=1),
    )
    return manifest


@pytest.fixture
def an_old_index_too(an_old_manifest_version: str, bucket: S3Client, s3_stand_in: S3StandIn) -> str:
    """And the caselist's parsed index, a day older than the removal, which no rebuild replaced."""
    put_older(
        bucket,
        s3_stand_in,
        AGGREGATE,
        b"a removed card's row\n",
        completion_of_the_removal(bucket) - timedelta(days=1),
    )
    return an_old_manifest_version


def test_a_manifest_and_an_aggregate_version_older_than_the_removal_fail_status_by_role_and_count(
    installation: Path, bucket: S3Client, an_old_index_too: str, s3_stand_in: S3StandIn
) -> None:
    """Listing only, with the everyday profile: the only objects read are the takedown's records."""
    before = every_version(bucket)
    completed = completion_of_the_removal(bucket)
    mark = len(s3_stand_in.requests())

    status = run("caselist", "status")
    shown = status_as_a_person_reads_it()
    asked = s3_stand_in.requests_since(mark)

    assert status["exit_code"] == ExitCode.DOMAIN_FAILURE, status
    error = status["error"]
    assert error["code"] == "REMOVAL_RESIDUE"
    assert all(entry["in_sync"] for entry in error["details"]["snapshots"]), "no snapshot differs"
    assert error["details"]["removal_residue"] == [
        {
            **NOTHING_LEFT,
            "older_versions": [{"role": "manifest", "versions": 1}, {"role": "index.jsonl", "versions": 1}],
        }
    ]
    assert error["details"]["removal_residue"][0]["older_than"][
        "completed_at"
    ] == completed.isoformat().replace("+00:00", "Z")
    found = (
        f"{SYNTHETIC_CASELIST}: 1 manifest version(s) and 1 index.jsonl version(s) older than RM-2026-03, "
        f"completed {completed:%Y-%m-%d %H:%M} UTC"
    )
    assert error["message"] == f"the bucket still holds versions older than a removal: {found}"
    assert f"REMOVAL RESIDUE in {found}." in shown
    assert "docs/runbooks/caselist-removal.md" in error["hint"]
    reported = json.dumps([error["details"]["removal_residue"], error["message"], error["hint"]]) + shown
    assert FIRST_VERSION not in reported, "no whole digest"
    for identifying in IDENTIFYING:
        assert identifying not in reported, identifying
    assert every_version(bucket) == before, "status changed the bucket"
    read = [str(one.key) for one in asked if one.operation == "GetObject"]
    assert read and all(key.startswith("manifests/_suppression/") for key in read), read
    listings = {one.access_key for one in asked if one.operation == "ListObjectVersions"}
    assert listings == {access_key_of(installation, OPERATOR_PROFILE)}, listings
    assert deletes_or_version_reads(asked) == [], "caselist status deleted or downloaded an object version"


def test_versions_older_than_a_removal_are_cleared_by_running_it_again_under_the_same_request(
    installation: Path, bucket: S3Client, an_old_index_too: str
) -> None:
    """The runbook's instruction: name a file the request removed, same request and reason, execute.

    The plan lists the old index with every aggregate, and the execution's sweep reads the manifest
    version, finds the removed row and deletes it.
    """
    shown = invoke(*REMOVE_FIRST_VERSION, width=200).stdout
    assert AGGREGATE in shown

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    environment(DEBATE_REMOVAL_PROFILE=NO_SUCH_PROFILE)

    clean = run("caselist", "status")
    assert clean["exit_code"] == ExitCode.OK, clean
    assert clean["data"]["removal_residue"] == [NOTHING_LEFT]


def test_an_old_manifest_version_alone_is_counted_by_the_dry_run_and_cleared_by_its_execution(
    installation: Path, bucket: S3Client, an_old_manifest_version: str
) -> None:
    """The sweep the execution will make is planned too (`v1-e30-t19`): the dry run counts the one
    version, prints the command to carry it out, and never says nothing is left. Until then it read
    current manifests only and said *Nothing is left to remove*, and the runbook said to execute
    anyway."""
    assert run("caselist", "status")["error"]["code"] == "REMOVAL_RESIDUE"
    planned = invoke(*REMOVE_FIRST_VERSION, width=200).stdout
    assert "Nothing is left to remove" not in planned
    lines = planned.splitlines()
    assert (
        "MANIFEST VERSIONS SWEPT from the bucket by --execute: 1 noncurrent version(s) of 1 manifest(s)."
        in lines
    )
    assert f"  bucket {an_old_manifest_version}  (1 version(s))" in lines
    assert "TO CARRY IT OUT" in lines

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    environment(DEBATE_REMOVAL_PROFILE=NO_SUCH_PROFILE)

    clean = run("caselist", "status")
    assert clean["exit_code"] == ExitCode.OK, clean
    assert clean["data"]["removal_residue"] == [NOTHING_LEFT]


def test_a_removal_an_older_build_made_is_named_as_not_checked_and_never_as_none(
    installation: Path, bucket: S3Client, removed_with_its_later_upload: None
) -> None:
    """A completed removal in this machine's log with no scope beside it, as builds before this one wrote."""
    log = installation / "dev" / "suppression" / "removal-log.jsonl"
    (line,) = log.read_text(encoding="utf-8").splitlines()
    older = {**json.loads(line), "request_id": "RM-2026-90", "recorded_at": "2026-10-01T12:00:00Z"}
    log.write_text(
        line + "\n" + json.dumps(older, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    status = run("caselist", "status")
    shown = status_as_a_person_reads_it()

    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["removals_not_checked"] == ["RM-2026-90"]
    assert (
        "Manifest and aggregate versions NOT CHECKED against RM-2026-90: the build that made that removal "
        "did not record which caselists it touched. That is not a finding of none."
    ) in shown


# ------------------------------------------------------------------------------------------------
# A removed path holds what is uploaded there afterwards (v1-e30-t13)
# ------------------------------------------------------------------------------------------------

#: The Round 2 negative's path, which the 09-08 weekly is the first to hold the revision at.
HELD_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"
UPLOADED_AFTER_THE_REMOVAL = _docx(("Grove City Invitational, round two, negative.", "Uploaded again."))
UPLOADED_AFTER = hashlib.sha256(UPLOADED_AFTER_THE_REMOVAL).hexdigest()
NEXT_WEEK = f"{SYNTHETIC_CASELIST}-weekly-2026-09-22.zip"


def next_weeks_archive(inbox: Path) -> Path:
    """The weekly of 2026-09-22 as `caselist pull` leaves one in the inbox: a new upload at the held
    path, and another team's file."""
    inbox.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(inbox / NEXT_WEEK, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(HELD_PATH, UPLOADED_AFTER_THE_REMOVAL)
        archive.writestr(
            "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx", DOCUMENT_BODIES["harbor-aff"]
        )
    return inbox / NEXT_WEEK


def import_next_week(archive: Path) -> dict[str, Any]:
    return run(
        "caselist", "import", str(archive), "--caselist", SYNTHETIC_CASELIST, "--snapshot", "2026-09-22"
    )  # fmt: skip


def test_a_removed_path_holds_next_weeks_upload_and_the_same_removal_run_again_finishes_it(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    data_dir = installation / "dev"
    local_path_holds = data_dir / "suppression" / "path-holds.jsonl"
    the_path_entry = {
        "schema_version": 1,
        "caselist": SYNTHETIC_CASELIST,
        "disclosure": hashlib.sha256(f"{SYNTHETIC_CASELIST}/{HELD_PATH}".encode()).hexdigest(),
        "sha256": REVISION,
        "after_snapshot": "2026-09-08",
        "reason": "REQUESTED_BY_TEAM",
        "request_id": "RM-2026-03",
    }

    # The dry run prints the path entry, names no one in its JSON, and writes nothing.
    planned = raw_json(*REMOVE_REVISION)
    (entry,) = [json.loads(line) for line in json.loads(planned)["data"]["path_holds"]]
    assert {key: value for key, value in entry.items() if key != "recorded_at"} == the_path_entry
    assert not [name for name in IDENTIFYING if name in planned]
    assert "PATH ENTRIES appended beside the list, here and in the bucket: 1" in (
        invoke(*REMOVE_REVISION).stdout
    )
    assert not local_path_holds.exists()

    # Executed: the entry is beside the list on this machine and in the bucket, the same line.
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    assert run(*REMOVE_REVISION, "--execute")["exit_code"] == ExitCode.OK
    written = local_path_holds.read_text(encoding="utf-8")
    assert {
        key: value for key, value in json.loads(written).items() if key != "recorded_at"
    } == the_path_entry
    in_the_bucket = bucket.get_object(Bucket=BUCKET, Key="manifests/_suppression/path-holds.jsonl")
    assert in_the_bucket["Body"].read().decode("utf-8") == written
    assert not [name for name in IDENTIFYING if name in written]
    environment(DEBATE_REMOVAL_PROFILE=None)

    # Next week's archive holds a new upload at that path. The import refuses it under the request.
    archive = next_weeks_archive(data_dir / "inbox")
    imported = import_next_week(archive)
    assert imported["exit_code"] == ExitCode.OK, imported
    assert imported["data"]["counts"]["SUPPRESSED"] == 1
    assert imported["data"]["held_at_removed_paths"] == {"RM-2026-03": 1}
    assert not (
        data_dir / "blobs" / "sha256" / UPLOADED_AFTER[0:2] / UPLOADED_AFTER[2:4] / UPLOADED_AFTER
    ).exists()
    manifest = (data_dir / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-22.jsonl").read_text()
    assert UPLOADED_AFTER not in manifest and HELD_PATH not in manifest
    assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK
    assert not bucket_holds(bucket, UPLOADED_AFTER)

    # Status says the removal is owed again: the upload waits in the inbox archive (v1-e30-t21). It
    # names it by prefix and request, never by path or archive, and still exits 0: nothing differs.
    owed = raw_json("caselist", "status")
    data = json.loads(owed)["data"]
    assert (data["in_sync"], data["removals_owed"]) == (True, ["RM-2026-03"])
    assert data["held_in_inbox"] == [
        {
            "caselist": SYNTHETIC_CASELIST,
            "uploads": 1,
            "sha256_prefixes": [UPLOADED_AFTER[:12]],
            "requests": ["RM-2026-03"],
        }
    ]
    told = invoke("caselist", "status", width=200).stdout
    assert (
        f"for {SYNTHETIC_CASELIST}: 1 upload(s) at a path a removal holds (sha256 {UPLOADED_AFTER[:12]}"
        in told
    )
    assert "RM-2026-03 is owed again" in told
    assert not [name for name in (*IDENTIFYING, NEXT_WEEK, HELD_PATH) if name in owed + told]

    # The same removal, run again, finds it in the inbox archive, and takes the archive out.
    again = run(*REMOVE_REVISION)
    assert [
        (one["sha256"], one["snapshots"], one["inbox_snapshots"], one["outcome"])
        for one in again["data"]["later_uploads"]
    ] == [(UPLOADED_AFTER, [], ["2026-09-22"], "removed")]
    assert [(one["name"], one["action"]) for one in again["data"]["inbox"]] == [(NEXT_WEEK, "delete")]
    assert again["data"]["path_holds"] == [], "the path is held already"
    assert archive.exists(), "a dry run"

    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_REVISION, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert not archive.exists()
    listed = (data_dir / "suppression" / "suppression-list.jsonl").read_text(encoding="utf-8")
    assert UPLOADED_AFTER in [json.loads(line)["sha256"] for line in listed.splitlines()]
    assert {json.loads(line)["request_id"] for line in listed.splitlines()} == {"RM-2026-03"}
    finished = run("caselist", "status")
    assert finished["exit_code"] == ExitCode.OK
    assert finished["data"]["removals_owed"] == [], "the re-run finished what status said was owed"

    # Letting the removed file back in would release the path.
    lifted = run("caselist", "unsuppress", "--sha256", REVISION, "--reason", "REMOVED_IN_ERROR")
    assert lifted["data"]["path_holds_released"] == 1 and lifted["data"]["applied"] is False


def test_after_only_named_no_path_is_held_and_next_weeks_upload_is_imported(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    data_dir = installation / "dev"
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)

    done = run(*REMOVE_REVISION, "--only-named", "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert done["data"]["path_holds"] == []
    assert not (data_dir / "suppression" / "path-holds.jsonl").exists()
    assert not any(key.endswith("path-holds.jsonl") for key, _ in versions(bucket))

    imported = import_next_week(next_weeks_archive(installation / "next-week"))

    assert imported["exit_code"] == ExitCode.OK, imported
    assert imported["data"]["counts"]["SUPPRESSED"] == 0
    assert imported["data"]["held_at_removed_paths"] == {}
    assert (
        data_dir / "blobs" / "sha256" / UPLOADED_AFTER[0:2] / UPLOADED_AFTER[2:4] / UPLOADED_AFTER
    ).exists()


def test_a_link_at_a_held_path_imports_with_no_row_and_nothing_is_owed_for_it(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """`v1-e30-t22`. After the `--source` removal, next week's archive holds a symbolic link at the
    held path, whose body is the removed file's name, beside another team's file. The import still
    counts it as skipped, and gives it no row; the publish completes, and status owes nothing."""
    data_dir = installation / "dev"
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    assert run(*REMOVE_REVISION, "--execute")["exit_code"] == ExitCode.OK
    environment(DEBATE_REMOVAL_PROFILE=None)
    archive = installation / "next-week" / NEXT_WEEK
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "w") as written:
        link = zipfile.ZipInfo(HELD_PATH, date_time=(1980, 1, 1, 0, 0, 0))
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        written.writestr(link, HELD_PATH.rsplit("/", 1)[1].encode())
        written.writestr(
            "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx", DOCUMENT_BODIES["harbor-aff"]
        )

    imported = import_next_week(archive)

    assert imported["exit_code"] == ExitCode.OK, imported
    assert imported["data"]["skipped"] == {"SYMLINK": 1}
    manifest = (data_dir / "objects" / "manifests" / SYNTHETIC_CASELIST / "2026-09-22.jsonl").read_text()
    assert HELD_PATH not in manifest
    assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK
    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["removals_owed"] == []
    assert {
        (one["held_skipped_rows"], tuple(one["held_skipped_row_requests"]))
        for one in status["data"]["snapshots"]
    } == {(0, ())}


def test_junk_beside_a_held_link_has_no_row_and_a_push_sends_no_manifest_the_publisher_withholds(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """`v1-e30-t25`. As above, with the AppleDouble junk macOS writes beside the link: it is skipped
    and given no row either. Then a manifest an older build wrote for 2026-09-29, with the link's row
    at the held path, which `caselist publish` withholds: `store sync --apply` leaves it on this
    machine, pushes the week beside it, and prints no path."""
    data_dir = installation / "dev"
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    assert run(*REMOVE_REVISION, "--execute")["exit_code"] == ExitCode.OK
    environment(DEBATE_REMOVAL_PROFILE=None)
    directory, name = HELD_PATH.rsplit("/", 1)
    junk = f"__MACOSX/{directory}/._{name}"
    archive = installation / "next-week" / NEXT_WEEK
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "w") as written:
        link = zipfile.ZipInfo(HELD_PATH, date_time=(1980, 1, 1, 0, 0, 0))
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        written.writestr(link, name.encode())
        written.writestr(junk, b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        ")
        written.writestr(
            "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx", DOCUMENT_BODIES["harbor-aff"]
        )

    imported = import_next_week(archive)

    assert imported["exit_code"] == ExitCode.OK, imported
    assert imported["data"]["skipped"] == {"SYMLINK": 1, "MACOS_METADATA": 1}
    manifests = data_dir / "objects" / "manifests" / SYNTHETIC_CASELIST
    assert name not in (manifests / "2026-09-22.jsonl").read_text(), "a row names the held path"

    withheld = f"manifests/{SYNTHETIC_CASELIST}/2026-09-29.jsonl"
    (manifests / "2026-09-29.jsonl").write_text(
        json.dumps({"kind": "member", "path": HELD_PATH, "skip_reason": "SYMLINK"}) + "\n"
    )
    pushed = f"manifests/{SYNTHETIC_CASELIST}/2026-09-22.jsonl"
    synced = run("store", "sync", "--prefix", f"manifests/{SYNTHETIC_CASELIST}/", "--apply")

    assert synced["exit_code"] == ExitCode.OK, synced
    assert synced["data"]["counts"]["new"] == 1
    listed = bucket.list_objects_v2(Bucket=BUCKET, Prefix=f"manifests/{SYNTHETIC_CASELIST}/")
    keys = {str(item.get("Key")) for item in listed.get("Contents", [])}
    assert pushed in keys
    assert withheld not in keys, "the push sent a manifest the publisher withholds"
    assert name not in json.dumps(synced)


# ------------------------------------------------------------------------------------------------
# A --source plan names only holders other than the one removed, and no team as "this team"
# (v1-e30-t16)
# ------------------------------------------------------------------------------------------------

BAYVIEW_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"
#: The same team's second path, where it uploaded the revision again.
BAYVIEW_SECOND_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis (1).docx"
BAYVIEW_REVISED = _docx(("Bayview Open, semifinals, negative.", "Revised the week after, twice uploaded."))
BAYVIEW_REVISION = hashlib.sha256(BAYVIEW_REVISED).hexdigest()
REMOVE_BAYVIEW = (
    "caselist",
    "remove",
    "--source",
    BAYVIEW,
    "--request",
    "RM-2026-07",
    "--reason",
    "REQUESTED_BY_TEAM",
)
#: A camp file of the synthetic 2026 Policy download that no team discloses.
CAMP_ONLY = hashlib.sha256(CAMP_BODIES["orchard-kritik"]).hexdigest()
REMOVE_CAMP_ONLY = (
    "caselist", "remove", "--source", CAMP_ONLY, "--request", "RM-2026-07", "--reason", "REQUESTED_BY_CAMP",
)  # fmt: skip


@pytest.fixture
def revised_at_two_of_the_teams_paths(installation: Path, published: Any) -> None:
    """The weekly window of 2026-09-22: the Bayview negative revised, at its path and the team's second.

    `caselist remove --source <bayview-semis-neg>` removes the named file whole and withdraws the
    revision from the named file's path only: the team's second path still holds it.
    """
    archive = installation / "downloads" / f"{SYNTHETIC_CASELIST}-weekly-2026-09-22.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        written.writestr(BAYVIEW_PATH, BAYVIEW_REVISED)
        written.writestr(BAYVIEW_SECOND_PATH, BAYVIEW_REVISED)
    imported = run(
        "caselist", "import", str(archive), "--caselist", SYNTHETIC_CASELIST, "--snapshot", "2026-09-22"
    )  # fmt: skip
    assert imported["exit_code"] == ExitCode.OK, imported
    assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK


def import_the_camp_download(installation: Path, *, event: str) -> None:
    """The first synthetic OpenEv download, as the release of `event`, imported and published."""
    download = build_download_zips(installation / f"openev-{event}")[OPENEV_DOWNLOADS[0].name]
    imported = run(
        "caselist", "import-openev", str(download), "--year", "2026", "--event", event,
        "--snapshot", "2026-09-14", "--camp-aliases", str(CAMP_ALIASES_PATH),
    )  # fmt: skip
    assert imported["exit_code"] == ExitCode.OK, imported
    assert run("caselist", "publish", "--caselist", "openev")["exit_code"] == ExitCode.OK


def shown(*arguments: str) -> str:
    """What the command prints for a person."""
    result = invoke(*arguments)
    assert result.exit_code == ExitCode.OK, result.output
    return result.stdout


def numbered_line(text: str, sha: str) -> str:
    (line,) = [line for line in text.splitlines() if sha in line and line.lstrip()[:1].isdigit()]
    return line


def strings_in(value: Any) -> list[str]:
    """Every string anywhere in a JSON value: keys and values, however deeply nested."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in (key, *strings_in(item))]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [text for item in value for text in strings_in(item)]  # pyright: ignore[reportUnknownVariableType]
    return []


def test_a_later_upload_the_team_also_holds_at_a_second_path_names_no_other_team(
    installation: Path, bucket: S3Client, revised_at_two_of_the_teams_paths: None
) -> None:
    text = shown(*REMOVE_BAYVIEW)
    planned = run(*REMOVE_BAYVIEW)

    assert "also held" not in numbered_line(text, BAYVIEW_REVISION)
    assert "other team" not in text and "another team" not in text
    assert f"     kept in  {SYNTHETIC_CASELIST} (another path there still holds it)" in text.splitlines()
    sources = {source["sha256"]: source for source in planned["data"]["sources"]}
    revision = sources[BAYVIEW_REVISION]
    assert (revision["disposition"], revision["other_teams"], revision["camp_file_holders"]) == (
        "withdraw",
        0,
        0,
    )
    assert revision["kept_in"] == [SYNTHETIC_CASELIST]
    assert (sources[BAYVIEW]["other_teams"], sources[BAYVIEW]["camp_file_holders"]) == (0, 0)
    assert all(set(source) == SOURCE_KEYS for source in planned["data"]["sources"])


def test_no_line_of_a_source_plan_says_this_team_in_the_dry_run_the_execution_or_a_rerun(
    installation: Path,
    bucket: S3Client,
    revised_at_two_of_the_teams_paths: None,
) -> None:
    """Every line printed and every string in the JSON, the confirmation to the requester included.

    The plan removes one file whole and withdraws one later upload from the named file's path, so
    every section that once said "this team's" is printed: the suppression entries' count, the
    confirmation's first line, and the line on what the list stops.
    """
    dry_run = shown(*REMOVE_BAYVIEW)
    dry_run_json = raw_json(*REMOVE_BAYVIEW)
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    executed = shown(*REMOVE_BAYVIEW, "--execute")
    rerun = shown(*REMOVE_BAYVIEW)
    rerun_json = raw_json(*REMOVE_BAYVIEW)

    for text in (dry_run, executed):
        lines = text.splitlines()
        assert "  1 whole file(s), and 1 path(s) a shared file is withdrawn from. Each" in lines
        assert "  - Removed from this environment: 1 file(s)." in lines
        assert "  - Also removed, as later uploads at the same path(s): 1 file(s)." in lines
        assert (
            "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or the "
            "copy of a shared file at the path it was withdrawn from."
        ) in lines
    assert "Nothing is left to remove" in rerun
    printed = [line for text in (dry_run, executed, rerun) for line in text.splitlines()]
    assert len(printed) > 100
    assert [line for line in printed if "this team" in line] == []
    for document in (dry_run_json, rerun_json):
        assert [text for text in strings_in(json.loads(document)) if "this team" in text] == []


def test_a_camp_file_only_one_camp_file_holds_names_no_other_holder(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    import_the_camp_download(installation, event="policy")

    text = shown(*REMOVE_CAMP_ONLY)
    planned = run(*REMOVE_CAMP_ONLY)

    line = numbered_line(text, CAMP_ONLY)
    assert "also held" not in line and "camp file(s)" not in line, line
    (source,) = planned["data"]["sources"]
    assert (source["disposition"], source["other_teams"], source["camp_file_holders"]) == ("remove", 0, 0)
    assert set(source) == SOURCE_KEYS


def test_a_camp_file_two_releases_hold_names_one_other_camp_file(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    import_the_camp_download(installation, event="policy")
    import_the_camp_download(installation, event="ld")

    text = shown(*REMOVE_CAMP_ONLY)
    planned = run(*REMOVE_CAMP_ONLY)

    assert numbered_line(text, CAMP_ONLY).endswith("; also held by 1 camp file(s))")
    (source,) = planned["data"]["sources"]
    assert (source["disposition"], source["other_teams"], source["camp_file_holders"]) == (
        "skip_shared",
        0,
        1,
    )


# ------------------------------------------------------------------------------------------------
# Loose ends in what a removal plan prints (v1-e30-t20)
# ------------------------------------------------------------------------------------------------

#: Cedar Hollow/ZaLu's path of the Round 1 affirmative, which Maple Grove/QX discloses too, from 09-08.
ANOTHER_TEAMS_PATH = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx"
#: The other team's second path, where it uploaded the revision again.
ANOTHER_TEAMS_SECOND_PATH = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3 (1).docx"
ROUND_1_REVISED = _docx(("Grove City Invitational, round 3, affirmative.", "Revised by the other team."))
ROUND_1_REVISION = hashlib.sha256(ROUND_1_REVISED).hexdigest()
REMOVE_SHARED_TOO = (*REMOVE, "--include-shared")
NOTHING_REMOVED = "  - Removed from this environment: nothing; this run found nothing left to remove."


def disclosure_of(path: str) -> str:
    """The digest the suppression list and the withdrawal record hold for a path: of `<caselist>/<path>`."""
    return hashlib.sha256(f"{SYNTHETIC_CASELIST}/{path}".encode()).hexdigest()


def suppression_count_line(text: str) -> str:
    """The line under *SUPPRESSION ENTRIES* that counts them by kind."""
    lines = text.splitlines()
    heading = next(index for index, line in enumerate(lines) if line.startswith("SUPPRESSION ENTRIES"))
    return lines[heading + 1]


def confirmation_lines(text: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index("FOR THE CONFIRMATION TO THE REQUESTER")
    end = next((index for index in range(start, len(lines)) if not lines[index]), len(lines))
    return lines[start:end]


@pytest.fixture
def revised_at_another_teams_paths(installation: Path, published: Any) -> None:
    """The weekly window of 2026-09-22: the other team's copy of the shared affirmative revised, at
    its path and at its second.

    `caselist remove --team <Maple Grove/QX> --include-shared` removes the shared file whole, from
    the other team's path as well, so the revision is a later upload there. The other team's second
    path still holds it, so it is withdrawn from the other team's path only.
    """
    archive = installation / "downloads" / f"{SYNTHETIC_CASELIST}-weekly-2026-09-22.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        written.writestr(ANOTHER_TEAMS_PATH, ROUND_1_REVISED)
        written.writestr(ANOTHER_TEAMS_SECOND_PATH, ROUND_1_REVISED)
    imported = run(
        "caselist", "import", str(archive), "--caselist", SYNTHETIC_CASELIST, "--snapshot", "2026-09-22"
    )  # fmt: skip
    assert imported["exit_code"] == ExitCode.OK, imported
    assert run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)["exit_code"] == ExitCode.OK


def test_a_team_removal_including_shared_files_calls_another_teams_path_none_of_this_teams(
    installation: Path, bucket: S3Client, revised_at_another_teams_paths: None
) -> None:
    """The suppression count and the line on what the list stops, in the dry run and the execution."""
    dry_run = shown(*REMOVE_SHARED_TOO)
    planned = run(*REMOVE_SHARED_TOO)
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    executed = shown(*REMOVE_SHARED_TOO, "--execute")

    revision = {source["sha256"]: source for source in planned["data"]["sources"]}[ROUND_1_REVISION]
    assert (revision["inclusion"], revision["disposition"]) == ("later_upload", "withdraw")
    assert revision["withdrawn_disclosures"] == [
        {"caselist": SYNTHETIC_CASELIST, "disclosure": disclosure_of(ANOTHER_TEAMS_PATH)}
    ]
    whole = sum(
        1 for line in planned["data"]["suppression_entries"] if json.loads(line)["disclosure"] is None
    )
    for text in (dry_run, executed):
        lines = text.splitlines()
        assert suppression_count_line(text) == (
            f"  {whole} whole file(s), and 1 path(s) of another holder a later upload is withdrawn from. Each"
        )
        assert (
            "  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or "
            "another holder's copy of a later upload at the path it was withdrawn from."
        ) in lines
        assert [line for line in lines if "this team's path" in line or "this team's copy" in line] == []


def test_a_rerun_that_removes_nothing_says_so_in_its_dry_run_and_its_execution(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """A team removal with a shared file withdrawn, executed, then the same command again, both ways.

    The re-run plans the team's files again, finds each gone and suppressed, and removes nothing.
    """
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    first = shown(*REMOVE, "--execute")
    rerun = shown(*REMOVE)
    rerun_executed = shown(*REMOVE, "--execute")

    told = confirmation_lines(first)
    assert told[1].startswith("  - Removed from this environment: ") and told[1] != NOTHING_REMOVED
    for text in (rerun, rerun_executed):
        assert "Nothing is left to remove" in text
        told = confirmation_lines(text)
        assert told[1] == NOTHING_REMOVED, told
        assert [line for line in told if "removed" in line.casefold() and "file(s)" in line] == [], told


def test_the_jsons_withdrawals_are_the_plans_lines_and_what_the_execution_records(
    installation: Path, bucket: S3Client, published: Any
) -> None:
    """The team's two paths of the shared affirmative: in the text, in the JSON, and in the record."""
    text = shown(*REMOVE)
    planned = run(*REMOVE)
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE, "--execute")
    rerun = run(*REMOVE)

    expected = [
        {"sha256": HELD_BY_TWO_TEAMS, "disclosure": disclosure_of(path), "caselist": SYNTHETIC_CASELIST}
        for path in sorted(
            (
                "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
                "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
            )
        )
    ]
    assert sorted(planned["data"].get("withdrawals", []), key=lambda one: one["disclosure"]) == sorted(
        expected, key=lambda one: one["disclosure"]
    )
    lines = text.splitlines()
    heading = next(index for index, line in enumerate(lines) if line.startswith("WITHDRAWALS"))
    printed = [json.loads(line) for line in lines[heading + 4 : heading + 4 + len(expected)]]
    assert [{key: one[key] for key in ("sha256", "disclosure", "caselist")} for one in printed] == (
        planned["data"]["withdrawals"]
    )
    assert done["exit_code"] == ExitCode.OK, done
    assert done["data"]["withdrawals"] == planned["data"]["withdrawals"]
    record = installation / "dev" / "suppression" / "withdrawals.jsonl"
    recorded = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
    assert sorted((one["sha256"], one["disclosure"], one["caselist"]) for one in recorded) == sorted(
        (one["sha256"], one["disclosure"], one["caselist"]) for one in expected
    )
    assert rerun["data"]["withdrawals"] == [], "the re-run appends nothing"


def manifest_versions(client: S3Client, key: str) -> set[str]:
    listed = client.list_object_versions(Bucket=BUCKET, Prefix=key)
    return {str(one.get("VersionId")) for one in listed.get("Versions", []) if one.get("Key") == key}


def test_the_jsons_sweep_count_is_the_plan_lines_and_what_the_execution_deletes(
    installation: Path, bucket: S3Client, an_old_manifest_version: str
) -> None:
    text = invoke(*REMOVE_FIRST_VERSION, width=200).stdout
    planned = run(*REMOVE_FIRST_VERSION)
    before = manifest_versions(bucket, an_old_manifest_version)
    environment(DEBATE_REMOVAL_PROFILE=REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")
    after = manifest_versions(bucket, an_old_manifest_version)

    assert planned["data"].get("manifest_versions_swept") == {
        "total": 1,
        "by_manifest": {an_old_manifest_version: 1},
    }
    assert (
        "MANIFEST VERSIONS SWEPT from the bucket by --execute: 1 noncurrent version(s) of 1 manifest(s)."
        in text.splitlines()
    )
    assert f"  bucket {an_old_manifest_version}  (1 version(s))" in text.splitlines()
    assert done["exit_code"] == ExitCode.OK, done
    assert len(before - after) == planned["data"]["manifest_versions_swept"]["total"]
    assert after <= before, "the sweep put nothing new at the key"


def test_a_plan_that_may_not_list_versions_says_the_sweep_was_not_counted(
    installation: Path, bucket: S3Client, removed_with_its_later_upload: None, s3_stand_in: S3StandIn
) -> None:
    """The bucket refuses the listing as S3 refuses a call the permission set does not grant."""
    s3_stand_in.refuse("ListObjectVersions", status=403, code="AccessDenied", message="Access Denied")

    text = invoke(*REMOVE_FIRST_VERSION, width=200).stdout
    planned = run(*REMOVE_FIRST_VERSION)

    assert planned["data"].get("manifest_versions_swept") == "not counted"
    assert "MANIFEST VERSIONS SWEPT from the bucket by --execute: not counted." in text.splitlines()

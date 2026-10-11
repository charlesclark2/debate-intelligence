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
import zipfile
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

# Runs in pytest's own process, where moto answers S3, so it cannot run against an installed
# build: `ci` runs it, and validate-dev's recorded tier deselects it (README.md).
pytestmark = pytest.mark.in_process

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
    assert done["data"]["inbox_exists"] is False and not (data_dir / "inbox").exists(), "none created"
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
        "): does not exist, so there is nothing to check or change",
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


def test_a_removal_profile_missing_from_the_aws_config_is_refused_with_nothing_changed(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal-typo")
    before = (tree(installation / "dev"), versions(bucket))

    refused = run(*REMOVE, "--execute")

    # The S3 adapter reports a profile missing from the AWS config as StoreCredentialsExpired, so the
    # preflight failure it causes ends the run as a store failure, 3 (v1-e01-t20).
    assert refused["exit_code"] == ExitCode.RETRIEVAL_FAILURE
    assert "debate-dev-evidence-removal-typo" in refused["error"]["message"] + str(refused["error"]["hint"])
    assert "nothing was deleted" in refused["error"]["message"]
    assert (tree(installation / "dev"), versions(bucket)) == before


def test_a_removal_that_completes_but_cannot_be_logged_says_it_completed(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This machine's removal log refuses the append after every deletion has succeeded."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    local_log = installation / "dev" / "suppression" / "removal-log.jsonl"
    local_log.parent.mkdir(parents=True, exist_ok=True)
    local_log.touch(mode=0o400)

    result = runner.invoke(create_app(), [*REMOVE, "--execute"], terminal_width=100)

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
    installation: Path, bucket: S3Client, published: dict[date, Path], monkeypatch: pytest.MonkeyPatch
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
    shown = runner.invoke(create_app(), list(REMOVE))

    assert planned["exit_code"] == ExitCode.OK, planned
    assert [(one["name"], one["action"]) for one in planned["data"]["inbox"]] == [
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-01.zip", "delete"),
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-08.zip", "delete"),
        (f"{SYNTHETIC_CASELIST}-weekly-2026-09-15.zip", "delete"),
        (waiting.name, "rewrite"),
    ]
    assert f"DOWNLOAD INBOX ({inbox}): 4 file(s) hold removed files." in shown.stdout
    assert tree(inbox) == before, "the dry run changed the inbox"

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
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
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    assert result.exit_code == ExitCode.OK, result.stdout
    return result.stdout


def bucket_holds(client: S3Client, sha: str) -> bool:
    return any(sha in key for key, _ in versions(client))


def test_the_dry_run_lists_a_later_upload_by_digest_caselist_and_snapshot_and_execute_removes_both(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
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

    shown = runner.invoke(create_app(), list(REMOVE_FIRST_VERSION)).stdout
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

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert json.loads(done["data"]["log_entry"])["removed_sha256"] == sorted([FIRST_VERSION, REVISION])
    assert not bucket_holds(bucket, FIRST_VERSION) and not bucket_holds(bucket, REVISION)
    blobs = installation / "dev" / "blobs" / "sha256"
    for sha in (FIRST_VERSION, REVISION):
        assert not (blobs / sha[0:2] / sha[2:4] / sha).exists()
    assert run("caselist", "status")["exit_code"] == ExitCode.OK


def test_only_named_removes_the_named_version_and_leaves_the_later_upload(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = runner.invoke(create_app(), [*REMOVE_FIRST_VERSION, "--only-named"]).stdout
    assert "LATER UPLOADS AT A REMOVED PATH, LEFT IN PLACE (--only-named): 1 file(s)" in shown
    confirm = shown[shown.index("TO CARRY IT OUT") :]
    assert "the 1 file(s) named only; 1 later upload(s) at the removed path(s) are left in place" in confirm
    assert "--only-named --execute" in confirm, "the printed command carries the flag"

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
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
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = runner.invoke(create_app(), list(REMOVE_REVISION)).stdout
    assert "EARLIER VERSIONS AT A REMOVED PATH, NOT REMOVED: 1 file(s)" in shown
    assert "LATER UPLOADS AT A REMOVED PATH" not in shown
    assert "This plan covers the 1 file(s) named, and adds 0 later upload(s)" in shown

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    done = run(*REMOVE_REVISION, "--execute")

    assert done["exit_code"] == ExitCode.OK, done
    assert [
        (one["sha256"], one["relation"], one["snapshots"]) for one in done["data"]["earlier_versions"]
    ] == [(FIRST_VERSION, "earlier", ["2026-09-01"])]
    assert bucket_holds(bucket, FIRST_VERSION) and not bucket_holds(bucket, REVISION)


def test_the_plans_json_names_no_school_team_path_or_file(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--source` with a later upload, `--team` with a withdrawn file, and an executed removal.

    The text of the same plans names them, as it always has: that is the operator's terminal.
    """
    assert "Maple Grove/QX/" in runner.invoke(create_app(), list(REMOVE_FIRST_VERSION)).stdout

    for arguments in (REMOVE_FIRST_VERSION, REMOVE, (*REMOVE, "--include-shared")):
        emitted = raw_json(*arguments)
        assert json.loads(emitted)["data"]["sources"], "a plan with something in it"
        assert not [name for name in IDENTIFYING if name in emitted], arguments

    team = json.loads(raw_json(*REMOVE))["data"]
    assert team["selector"] == {"kind": "TEAM", "caselist": SYNTHETIC_CASELIST}
    assert sum(len(source["disclosures"]) for source in team["sources"]) == 9
    assert sum(len(source["withdrawn_disclosures"]) for source in team["sources"]) == 2

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
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

    shown = runner.invoke(create_app(), list(remove)).stdout
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

    shown = runner.invoke(create_app(), list(remove)).stdout
    planned = run(*remove)

    (line,) = [
        line for line in shown.splitlines() if HELD_BY_TWO_TEAMS in line and line.lstrip().startswith("1.")
    ]
    assert line.endswith("; also held by 1 other team(s))"), line
    (source,) = planned["data"]["sources"]
    assert source["disposition"] == "skip_shared"
    assert source["other_teams"] == 1
    assert set(source) == SOURCE_KEYS

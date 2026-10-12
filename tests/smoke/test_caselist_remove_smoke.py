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
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
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
        # Each profile is the role its name says: a takedown asks before it does anything (v1-e29-t08).
        sign_in(
            installation / "aws-credentials",
            {OPERATOR_PROFILE: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE},
        )
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
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`DEBATE_REMOVAL_PROFILE` naming the everyday profile, which is easy to do: one suffix apart.

    The takedown asks the account which role the profile is signed in as before it lists or writes
    (v1-e29-t08). Moto's bucket would let this profile run the whole removal, so the unchanged
    bucket below is the command's doing and not a refused request's.
    """
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", OPERATOR_PROFILE)
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


# ------------------------------------------------------------------------------------------------
# What a removal left behind, in `caselist status` (v1-e30-t10)
# ------------------------------------------------------------------------------------------------

#: `caselist status` with the everyday profile only. The takedown profile names nothing that exists,
#: so a status that built a client with it would fail instead of reporting.
NO_SUCH_PROFILE = "debate-no-such-profile"
NOTHING_LEFT = {
    "caselist": SYNTHETIC_CASELIST,
    "checked": True,
    "not_checked_reason": None,
    "current_objects": 0,
    "noncurrent_versions": 0,
    "delete_markers": 0,
    "files": [],
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


def status_as_a_person_reads_it() -> str:
    result = runner.invoke(create_app(), ["caselist", "status"], terminal_width=200)
    return " ".join((result.stdout + result.stderr).split())


@pytest.fixture
def removed_with_its_later_upload(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first version removed by `--source`, and the revision with it as a later upload."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    done = run(*REMOVE_FIRST_VERSION, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert json.loads(done["data"]["log_entry"])["removed_sha256"] == sorted([FIRST_VERSION, REVISION])
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", NO_SUCH_PROFILE)


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
    assert "No version of a removed file is left under raw/ or parsed/" in status_as_a_person_reads_it()


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The versions are there. A profile without the grant cannot see them, and says so."""
    from debate_core.application.errors import StoreAccessDenied
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    async def refused(self: S3EvidenceVersionStore, prefix: str) -> tuple[Any, ...]:
        raise StoreAccessDenied("ListObjectVersions", f"s3://{BUCKET}/{prefix}")

    monkeypatch.setattr(S3EvidenceVersionStore, "list_versions", refused)

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
        }
    ]
    assert f"Removal residue NOT CHECKED for {SYNTHETIC_CASELIST}" in shown
    assert "No version of a removed file is left" not in shown


def test_status_reports_residue_with_the_everyday_profile_and_never_deletes_or_downloads_a_version(
    installation: Path,
    bucket: S3Client,
    versions_left_under_a_delete_marker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    profiles: list[str | None] = []
    listing = S3EvidenceVersionStore.list_versions

    async def recorded(self: S3EvidenceVersionStore, prefix: str) -> tuple[Any, ...]:
        profiles.append(self.profile)
        return await listing(self, prefix)

    async def forbidden(self: S3EvidenceVersionStore, *_: Any) -> Any:
        raise AssertionError("caselist status deleted or downloaded an object version")

    monkeypatch.setattr(S3EvidenceVersionStore, "list_versions", recorded)
    monkeypatch.setattr(S3EvidenceVersionStore, "delete_versions", forbidden)
    monkeypatch.setattr(S3EvidenceVersionStore, "get_version_file", forbidden)
    assert os.environ["DEBATE_REMOVAL_PROFILE"] == NO_SUCH_PROFILE

    status = run("caselist", "status")

    assert status["exit_code"] == ExitCode.DOMAIN_FAILURE, status
    assert status["error"]["code"] == "REMOVAL_RESIDUE"
    assert profiles and set(profiles) == {OPERATOR_PROFILE}


def test_a_takedown_stopped_among_a_later_uploads_versions_shows_in_status_until_the_rerun(
    installation: Path, bucket: S3Client, published: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runbook's loop: a run stops, `caselist status` says what is left, the same command finishes it.

    The later upload's object has three versions. The run deletes the named file's object, then the
    first, current, version of the later upload's, and loses the bucket. S3 makes the next version
    current, so one current object and one noncurrent version are left, of the later upload alone.
    """
    from debate_core.application.errors import StoreUnavailable
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    for body in (b"a second version", b"a third version"):
        bucket.put_object(Bucket=BUCKET, Key=raw_key(REVISION), Body=body)
    deleting = S3EvidenceVersionStore.delete_versions

    async def loses_the_bucket(self: S3EvidenceVersionStore, versions: Any) -> int:
        if not any(REVISION in version.key for version in versions):
            return await deleting(self, versions)
        await deleting(self, versions[:1])
        raise StoreUnavailable("DeleteObject", f"s3://{BUCKET}/{versions[0].key}", "the connection dropped")

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    with monkeypatch.context() as stopped:
        stopped.setattr(S3EvidenceVersionStore, "delete_versions", loses_the_bucket)
        incomplete = run(*REMOVE_FIRST_VERSION, "--execute")
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runbook's other loop: every snapshot agrees, and the version listing still shows a file.

    The original command finds nothing left to do, because nothing shows the later upload at the
    removed path any more. Naming the file by its own sha256, under the same request, plans its
    three versions (two data versions and the delete marker) and removes them.
    """
    assert "Nothing is left to remove" in runner.invoke(create_app(), list(REMOVE_FIRST_VERSION)).stdout
    name_it = ("caselist", "remove", "--source", REVISION, *LATER_UPLOADS_REQUEST)

    shown = runner.invoke(create_app(), list(name_it), terminal_width=200).stdout

    assert "already suppressed by this request: finishing what a previous run left" in shown
    assert f"{raw_key(REVISION)}  (3 version(s))" in shown

    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    done = run(*name_it, "--execute")
    assert done["exit_code"] == ExitCode.OK, done
    assert not bucket_holds(bucket, REVISION)
    assert not any(REVISION in key for key, _, _ in every_version(bucket)), "the delete marker went too"

    clean = run("caselist", "status")
    assert clean["exit_code"] == ExitCode.OK, clean
    assert clean["data"]["removal_residue"] == [NOTHING_LEFT]

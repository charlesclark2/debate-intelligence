"""`debate-research caselist publish` and `caselist status`, run the way an operator runs them.

Through Typer's `CliRunner` against the real application and composition root, the real importer
and the real S3 adapter over moto. The profile directory is this test's own: dev and prod name
*different* moto buckets, which is how ac5 — `DEBATE_ENV` selects the bucket — is checked without
an AWS account. Expected keys and counts come from the hand-written
`tests/fixtures/caselist/expected_publish.json`.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
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
from tests.fixtures.caselist.publish_expectations import (
    FICTIONAL_IDENTIFIERS,
    digest_of_body,
    expected_publish,
    expected_source_key,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.suppression import PathHoldEntry, ReasonCode, disclosure_digest
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

DEV_BUCKET = "debate-dev-evidence-moto"
PROD_BUCKET = "debate-prod-evidence-moto"
PROFILES = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}
EXPECTED = expected_publish()
EVERY_BODY = sorted({name for week in EXPECTED["snapshots"] for name in week["sources"]})
EXPECTED_KEYS = {expected_source_key(name) for name in EVERY_BODY} | {
    f"manifests/{SYNTHETIC_CASELIST}/{week['snapshot']}.jsonl" for week in EXPECTED["snapshots"]
}


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming different buckets and one shared data directory, fake AWS."""
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
    """The three synthetic weeks, imported through the command an operator runs."""
    zips = build_snapshot_zips(tmp_path / "downloads")
    for week in SNAPSHOTS:
        result = invoke(
            "--json", "caselist", "import", str(zips[week.snapshot]),
            "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
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


def keys_in(client: S3Client, bucket: str) -> set[str]:
    return {str(item.get("Key")) for item in client.list_objects_v2(Bucket=bucket).get("Contents", [])}


def publish(*extra: str) -> Result:
    return invoke("--json", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST, *extra)


# ------------------------------------------------------------------------------------------------
# ac5: DEBATE_ENV selects the bucket; prod needs --confirm-prod; --dry-run writes nothing
# ------------------------------------------------------------------------------------------------


class TestEnvironments:
    def test_dev_publishes_to_the_dev_bucket_only(self, buckets: S3Client, imported: Path) -> None:
        result = publish()

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["environment"] == "dev"
        assert data["bucket"] == DEV_BUCKET
        assert keys_in(buckets, DEV_BUCKET) == EXPECTED_KEYS
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_prod_is_refused_without_confirm_prod_and_nothing_is_written(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_prod_with_confirm_prod_publishes_to_the_prod_bucket_only(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish("--confirm-prod")

        assert result.exit_code == ExitCode.OK, result.stdout
        assert keys_in(buckets, PROD_BUCKET) == EXPECTED_KEYS
        assert keys_in(buckets, DEV_BUCKET) == set()

    def test_a_prod_dry_run_needs_no_confirmation_and_writes_nothing(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = publish("--dry-run")

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["applied"] is False
        assert data["planned_uploads"] == EXPECTED["totals"]["source_objects"]
        assert keys_in(buckets, PROD_BUCKET) == set()

    def test_the_dry_run_lists_every_planned_upload_per_snapshot(
        self, buckets: S3Client, imported: Path
    ) -> None:
        result = publish("--dry-run")

        data = envelope_of(result)["data"]
        planned = {entry["snapshot"]: entry for entry in data["snapshots"]}
        for week in EXPECTED["snapshots"]:
            entry = planned[week["snapshot"]]
            assert entry["planned"]["upload"] == week["first_publish"]["upload"]
            assert entry["planned"]["uploaded_earlier"] == week["first_publish"]["uploaded_earlier"]
            assert entry["manifest"] == "upload"
        assert keys_in(buckets, DEV_BUCKET) == set()

    def test_the_test_environment_names_no_bucket_and_is_refused(
        self, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEBATE_ENV", "test")

        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "ENVIRONMENT_NOT_SYNCABLE"

    @pytest.mark.parametrize(
        "arguments",
        [("--caselist", "Maple Grove"), ("--caselist", SYNTHETIC_CASELIST, "--snapshot", "0915")],
    )
    def test_names_with_no_place_in_the_layout_are_refused(
        self, buckets: S3Client, arguments: tuple[str, ...]
    ) -> None:
        result = invoke("--json", "caselist", "publish", *arguments)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "INVALID_PUBLISH_TARGET"


# ------------------------------------------------------------------------------------------------
# ac2 and ac3 through the command
# ------------------------------------------------------------------------------------------------


class TestPublishOutcomes:
    def test_a_second_publish_reports_everything_skipped(self, buckets: S3Client, imported: Path) -> None:
        publish()

        result = publish()

        assert result.exit_code == ExitCode.OK
        data = envelope_of(result)["data"]
        assert data["counts"] == {
            "uploaded": 0,
            "skipped": EXPECTED["totals"]["source_objects"],
            "suppressed": 0,
            "failed": 0,
        }
        assert {entry["manifest"] for entry in data["snapshots"]} == {"skipped"}

    def test_a_failed_upload_exits_non_zero_naming_the_sha256_and_withholds_the_manifest(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failing = digest_of_body("ridgeline-round-3-neg")
        real_put = S3EvidenceObjectStore.put_file

        async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
            if key.endswith(failing):
                raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
            return await real_put(self, key, source)

        monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)

        result = publish()

        # The only failure is a 503 from the store, which a re-run may get past: 3 (v1-e01-t20).
        assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
        error = envelope_of(result)["error"]
        assert error["code"] == "PUBLISH_INCOMPLETE"
        assert failing in error["message"]
        assert error["details"]["failed_sha256"] == [failing]
        landed = keys_in(buckets, DEV_BUCKET)
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl" not in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" not in landed

    def test_publishing_with_nothing_imported_is_refused(self, buckets: S3Client) -> None:
        result = publish()

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["code"] == "NOTHING_TO_PUBLISH"


# ------------------------------------------------------------------------------------------------
# ac4: caselist status
# ------------------------------------------------------------------------------------------------


class TestStatus:
    def test_status_before_a_publish_exits_non_zero_with_every_snapshot_reported(
        self, buckets: S3Client, imported: Path
    ) -> None:
        result = invoke("--json", "caselist", "status", "--caselist", SYNTHETIC_CASELIST)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        error = envelope_of(result)["error"]
        assert error["code"] == "CASELIST_DRIFT"
        reported = {entry["snapshot"]: entry for entry in error["details"]["snapshots"]}
        for week in EXPECTED["snapshots"]:
            entry = reported[week["snapshot"]]
            assert entry["manifest_present"] is False
            assert entry["local_files"] == len(week["sources"])
            assert entry["published_sources"] == 0
            assert sorted(entry["missing_sources"]) == sorted(
                digest_of_body(name) for name in week["sources"]
            )

    def test_status_after_a_publish_exits_zero(self, buckets: S3Client, imported: Path) -> None:
        publish()

        result = invoke("--json", "caselist", "status")

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["in_sync"] is True
        assert [entry["snapshot"] for entry in data["snapshots"]] == [
            week["snapshot"] for week in EXPECTED["snapshots"]
        ]
        for entry in data["snapshots"]:
            # Every field from before v1-e30-t12 is still here; `mismatches` and the two
            # suppressed-row fields were added beside them, and the three held-row fields
            # beside those (v1-e30-t21).
            assert set(entry) == {
                "caselist", "snapshot", "manifest_key", "in_sync", "local_manifest", "manifest_present",
                "sources", "local_files", "published_sources", "missing_sources", "missing_local",
                "checksum_mismatches", "suppressed", "mismatches", "suppressed_rows",
                "suppressed_row_prefixes", "held_rows", "held_row_prefixes", "held_row_requests",
            }  # fmt: skip
            assert (entry["mismatches"], entry["suppressed_rows"], entry["suppressed_row_prefixes"]) == (
                [],
                0,
                [],
            )
            assert (entry["held_rows"], entry["held_row_prefixes"], entry["held_row_requests"]) == (0, [], [])
        assert data["suppressed_objects"] == [
            {"caselist": SYNTHETIC_CASELIST, "objects": 0, "sha256_prefixes": []}
        ]

    def test_status_reads_the_bucket_of_its_own_environment(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        publish()
        monkeypatch.setenv("DEBATE_ENV", "prod")

        result = invoke("--json", "caselist", "status")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE
        assert envelope_of(result)["error"]["details"]["bucket"] == PROD_BUCKET

    def test_a_snapshot_without_a_caselist_is_refused(self, buckets: S3Client) -> None:
        result = invoke("--json", "caselist", "status", "--snapshot", "2026-09-15")

        assert result.exit_code == ExitCode.DOMAIN_FAILURE


# ------------------------------------------------------------------------------------------------
# v1-e30-t21: caselist status says when a removal's hold is owed again, and exits as before
# ------------------------------------------------------------------------------------------------

HELD_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"
FIRST = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-first"]).hexdigest()
REVISED = hashlib.sha256(DOCUMENT_BODIES["grove-round-2-neg-revised"]).hexdigest()
NEXT_WEEKS_UPLOAD = b"invented bytes of a later upload at the held path"
NEXT_WEEKS = hashlib.sha256(NEXT_WEEKS_UPLOAD).hexdigest()
REQUEST = "RM-2026-09"
#: Every word of the held path, and the inbox archive's own name.
IDENTIFYING = ("Maple Grove", "QX", "Grove City", "Round 2", ".docx", "weekly-2026-09-22")


def the_removal_holds_the_path(data_dir: Path) -> None:
    """The path entry, as `caselist remove --source <first version>` appends it on this machine."""
    entry = PathHoldEntry(
        caselist=SYNTHETIC_CASELIST,
        disclosure=disclosure_digest(SYNTHETIC_CASELIST, HELD_PATH),
        sha256=FIRST,
        after_snapshot=date(2026, 9, 1),
        recorded_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id=REQUEST,
    )
    record = data_dir / "suppression" / "path-holds.jsonl"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(entry.to_line() + "\n", encoding="utf-8")


def next_week_waits_in_the_inbox(data_dir: Path) -> None:
    inbox = data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(inbox / f"{SYNTHETIC_CASELIST}-weekly-2026-09-22.zip", "w") as archive:
        archive.writestr(f"testcl26-0922/{HELD_PATH}", NEXT_WEEKS_UPLOAD)


class TestStatusOfAHeldPath:
    """`caselist status` says when a removal's hold is owed again (`v1-e30-t21`).

    After the three weeks are published, the state an older build leaves after a `--source`
    removal: the path entry the removal of the round-two negative's first version writes, holding
    its path after `2026-09-01`; the revision at that path in `2026-09-08` and `2026-09-15`, which
    stands for what a build from before `v1-e30-t13` imports there, reading no path entry; and next
    week's archive in the download inbox with another upload at the path. Nothing here needs a name
    this task added, so it runs against the build at the start commit too, which exits 0 and says
    nothing of the hold.
    """

    def test_status_names_the_held_rows_and_the_held_upload_and_still_exits_zero(
        self, buckets: S3Client, imported: Path
    ) -> None:
        assert publish().exit_code == ExitCode.OK
        the_removal_holds_the_path(imported)
        next_week_waits_in_the_inbox(imported)

        result = invoke("--json", "caselist", "status", "--caselist", SYNTHETIC_CASELIST)

        assert result.exit_code == ExitCode.OK, result.stdout
        data = envelope_of(result)["data"]
        assert data["in_sync"] is True
        held = {
            entry["snapshot"]: (
                entry.get("held_rows"),
                entry.get("held_row_prefixes"),
                entry.get("held_row_requests"),
            )
            for entry in data["snapshots"]
        }
        assert held == {
            "2026-09-01": (0, [], []),
            "2026-09-08": (1, [REVISED[:12]], [REQUEST]),
            "2026-09-15": (1, [REVISED[:12]], [REQUEST]),
        }
        assert data.get("held_in_inbox") == [
            {
                "caselist": SYNTHETIC_CASELIST,
                "uploads": 1,
                "sha256_prefixes": [NEXT_WEEKS[:12]],
                "requests": [REQUEST],
            }
        ]
        assert data.get("removals_owed") == [REQUEST]
        assert not [word for word in IDENTIFYING if word in result.stdout]

    def test_the_table_tells_a_person_what_is_held_and_to_run_the_removal_again(
        self, buckets: S3Client, imported: Path
    ) -> None:
        assert publish().exit_code == ExitCode.OK
        the_removal_holds_the_path(imported)
        next_week_waits_in_the_inbox(imported)

        result = invoke("caselist", "status", "--caselist", SYNTHETIC_CASELIST)

        assert result.exit_code == ExitCode.OK, result.stdout
        told = " ".join(result.stdout.split())
        assert f"HELD PATH ROWS in {SYNTHETIC_CASELIST} 2026-09-08: 1 row(s)" in told
        assert f"HELD UPLOADS IN THE DOWNLOAD INBOX for {SYNTHETIC_CASELIST}: 1 upload(s)" in told
        assert f"{REQUEST} is owed again" in told
        assert not [word for word in IDENTIFYING if word in result.stdout]

    def test_without_a_hold_the_json_says_nothing_is_owed(self, buckets: S3Client, imported: Path) -> None:
        assert publish().exit_code == ExitCode.OK

        data = envelope_of(invoke("--json", "caselist", "status"))["data"]

        assert data.get("removals_owed") == []
        assert json.dumps(data.get("held_in_inbox")) == json.dumps(
            [{"caselist": SYNTHETIC_CASELIST, "uploads": 0, "sha256_prefixes": [], "requests": []}]
        )


# ------------------------------------------------------------------------------------------------
# v1-e30-t12: caselist status tells a manifest mismatch from a source mismatch, and shows what a
# removal left (suppressed rows per snapshot, suppressed objects per caselist)
# ------------------------------------------------------------------------------------------------

SECOND_CASELIST = "testcl27"
"""A second invented caselist slug, holding the first synthetic week, for "each caselist affected"."""

COMPLETE_ARCHIVE = "full/2026-09-20"
PUBLISH_HINT = "caselist publish --caselist {}"
PERSON_HINT = "needs a person"


def manifest_path(data_dir: Path, caselist: str, snapshot: str) -> Path:
    return data_dir / "objects" / "manifests" / caselist / f"{snapshot}.jsonl"


def rewrite_local_manifest(data_dir: Path, caselist: str, snapshot: str) -> None:
    """Change this machine's manifest bytes and none of its sources, as a re-import or a removal does.

    The summary row is written again with other separators: the same facts, other bytes.
    """
    path = manifest_path(data_dir, caselist, snapshot)
    before = path.read_bytes()
    lines = before.decode("utf-8").splitlines()
    lines[-1] = json.dumps(json.loads(lines[-1]), separators=(", ", ": "), sort_keys=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    assert path.read_bytes() != before


def replace_in_bucket(client: S3Client, key: str) -> None:
    """Other bytes of the same size under `key`, with some other digest recorded."""
    size = client.head_object(Bucket=DEV_BUCKET, Key=key)["ContentLength"]
    client.put_object(Bucket=DEV_BUCKET, Key=key, Body=b"x" * size, Metadata={SHA256_METADATA_NAME: "0" * 64})


def suppress(data_dir: Path, sha256: str) -> None:
    """Put `sha256` on this machine's copy of the suppression list, whole, as a removal does."""
    from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
    from debate_core.integrations.local.suppression_list import local_suppression_list_file

    path = local_suppression_list_file(data_dir).path
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha256,
        recorded_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(entry.to_line() + "\n")


def refuse_version_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile without the version-listing grant: the residue is then *not checked*."""
    from debate_core.application.errors import StoreAccessDenied
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    async def refused(self: S3EvidenceVersionStore, prefix: str) -> tuple[Any, ...]:
        raise StoreAccessDenied("ListObjectVersions", f"s3://{DEV_BUCKET}/{prefix}")

    monkeypatch.setattr(S3EvidenceVersionStore, "list_versions", refused)


def status_as_a_person_reads_it() -> str:
    result = runner.invoke(create_app(), ["caselist", "status"], terminal_width=200)
    return " ".join(result.output.split())


def status_error() -> dict[str, Any]:
    result = invoke("--json", "caselist", "status")
    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    error = envelope_of(result)["error"]
    assert isinstance(error, dict)
    return error


def reported(error: dict[str, Any], caselist: str, snapshot: str) -> dict[str, Any]:
    (entry,) = [
        one
        for one in error["details"]["snapshots"]
        if (one["caselist"], one["snapshot"]) == (caselist, snapshot)
    ]
    return entry


@pytest.fixture
def second_caselist(tmp_path: Path, imported: Path) -> Path:
    """The first synthetic week imported again as a second caselist, so two caselists are held."""
    zips = build_snapshot_zips(tmp_path / "second-downloads")
    first = SNAPSHOTS[0].snapshot
    result = invoke(
        "--json", "caselist", "import", str(zips[first]),
        "--caselist", SECOND_CASELIST, "--snapshot", first.isoformat(),
    )  # fmt: skip
    assert result.exit_code == ExitCode.OK, result.stdout
    return imported


class TestStatusNamesManifestMismatches:
    """ac1: a manifest mismatch is named as one, and its hint is a publish of each caselist affected."""

    def test_status_with_only_manifest_mismatches_hints_a_publish_of_each_caselist_and_no_person(
        self, buckets: S3Client, second_caselist: Path
    ) -> None:
        for caselist in (SYNTHETIC_CASELIST, SECOND_CASELIST):
            assert invoke("--json", "caselist", "publish", "--caselist", caselist).exit_code == ExitCode.OK
        rewrite_local_manifest(second_caselist, SYNTHETIC_CASELIST, "2026-09-01")
        rewrite_local_manifest(second_caselist, SYNTHETIC_CASELIST, "2026-09-08")
        rewrite_local_manifest(second_caselist, SECOND_CASELIST, "2026-09-01")

        error = status_error()

        assert error["code"] == "CASELIST_DRIFT"
        assert error["exit_code"] == ExitCode.DOMAIN_FAILURE
        assert error["message"] == (
            "3 snapshot(s) differ between this machine and the bucket: "
            f"{SYNTHETIC_CASELIST} 2026-09-01 (manifest mismatch), "
            f"{SYNTHETIC_CASELIST} 2026-09-08 (manifest mismatch), "
            f"{SECOND_CASELIST} 2026-09-01 (manifest mismatch)"
        )
        assert PUBLISH_HINT.format(SYNTHETIC_CASELIST) in error["hint"]
        assert PUBLISH_HINT.format(SECOND_CASELIST) in error["hint"]
        assert PERSON_HINT not in error["hint"]
        assert "completes what is missing" not in error["hint"]
        key = f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl"
        entry = reported(error, SYNTHETIC_CASELIST, "2026-09-01")
        assert entry["checksum_mismatches"] == [key]
        assert entry["mismatches"] == [{"key": key, "kind": "manifest"}]
        assert reported(error, SYNTHETIC_CASELIST, "2026-09-15")["mismatches"] == []

    def test_the_publish_the_hint_names_clears_it(self, buckets: S3Client, imported: Path) -> None:
        publish()
        rewrite_local_manifest(imported, SYNTHETIC_CASELIST, "2026-09-08")
        assert PUBLISH_HINT.format(SYNTHETIC_CASELIST) in status_error()["hint"]

        assert publish().exit_code == ExitCode.OK

        assert invoke("--json", "caselist", "status").exit_code == ExitCode.OK

    def test_a_complete_archive_manifest_mismatch_is_a_manifest_mismatch_the_same_publish_clears(
        self, buckets: S3Client, imported: Path
    ) -> None:
        """`manifests/<caselist>/full/<date>.jsonl` is a manifest one level down, published with its
        caselist by `caselist publish --caselist <slug>` like every weekly."""
        complete = manifest_path(imported, SYNTHETIC_CASELIST, COMPLETE_ARCHIVE)
        complete.parent.mkdir(parents=True)
        complete.write_bytes(manifest_path(imported, SYNTHETIC_CASELIST, "2026-09-15").read_bytes())
        publish()
        rewrite_local_manifest(imported, SYNTHETIC_CASELIST, COMPLETE_ARCHIVE)

        error = status_error()

        key = f"manifests/{SYNTHETIC_CASELIST}/{COMPLETE_ARCHIVE}.jsonl"
        assert reported(error, SYNTHETIC_CASELIST, COMPLETE_ARCHIVE)["mismatches"] == [
            {"key": key, "kind": "manifest"}
        ]
        assert f"{SYNTHETIC_CASELIST} {COMPLETE_ARCHIVE} (manifest mismatch)" in error["message"]
        assert PUBLISH_HINT.format(SYNTHETIC_CASELIST) in error["hint"]
        assert PERSON_HINT not in error["hint"]
        assert publish().exit_code == ExitCode.OK
        assert invoke("--json", "caselist", "status").exit_code == ExitCode.OK

    def test_the_table_and_the_hint_say_manifest_mismatch_to_a_person(
        self, buckets: S3Client, imported: Path
    ) -> None:
        publish()
        rewrite_local_manifest(imported, SYNTHETIC_CASELIST, "2026-09-08")

        shown = status_as_a_person_reads_it()

        assert f"{SYNTHETIC_CASELIST} 2026-09-08 (manifest mismatch)" in shown
        assert PUBLISH_HINT.format(SYNTHETIC_CASELIST) in shown
        assert PERSON_HINT not in shown
        assert "Source mismatches" in shown
        assert "differs" in shown


class TestStatusKeepsTheSourceMismatchHint:
    """ac2: a source mismatch still needs a person; both kinds at once print both hints."""

    def test_status_with_only_a_source_mismatch_keeps_the_hint_that_a_person_must_investigate(
        self, buckets: S3Client, imported: Path
    ) -> None:
        publish()
        key = expected_source_key("bayview-semis-neg")
        replace_in_bucket(buckets, key)

        error = status_error()

        assert error["code"] == "CASELIST_DRIFT"
        assert error["message"] == (
            "1 snapshot(s) differ between this machine and the bucket: "
            f"{SYNTHETIC_CASELIST} 2026-09-15 (1 source mismatch(es))"
        )
        assert PERSON_HINT in error["hint"]
        assert "caselist publish --caselist" not in error["hint"]
        assert reported(error, SYNTHETIC_CASELIST, "2026-09-15")["mismatches"] == [
            {"key": key, "kind": "source"}
        ]

    def test_status_with_both_kinds_prints_both_hints(self, buckets: S3Client, imported: Path) -> None:
        publish()
        key = expected_source_key("bayview-semis-neg")
        replace_in_bucket(buckets, key)
        rewrite_local_manifest(imported, SYNTHETIC_CASELIST, "2026-09-15")
        rewrite_local_manifest(imported, SYNTHETIC_CASELIST, "2026-09-01")

        error = status_error()

        assert error["message"] == (
            "2 snapshot(s) differ between this machine and the bucket: "
            f"{SYNTHETIC_CASELIST} 2026-09-01 (manifest mismatch), "
            f"{SYNTHETIC_CASELIST} 2026-09-15 (manifest mismatch, 1 source mismatch(es))"
        )
        assert PUBLISH_HINT.format(SYNTHETIC_CASELIST) in error["hint"]
        assert PERSON_HINT in error["hint"]
        manifest_key = f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl"
        assert reported(error, SYNTHETIC_CASELIST, "2026-09-15")["mismatches"] == [
            {"key": manifest_key, "kind": "manifest"},
            {"key": key, "kind": "source"},
        ]

    def test_status_with_something_missing_keeps_the_publish_completes_it_hint(
        self, buckets: S3Client, imported: Path
    ) -> None:
        error = status_error()

        assert error["hint"] == "`caselist publish` completes what is missing here."


class TestStatusShowsSuppressedRowsAndObjects:
    """ac4: suppressed rows per snapshot and suppressed objects per caselist, in the table and JSON."""

    def test_status_shows_each_snapshots_suppressed_rows_and_each_caselists_suppressed_objects(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        publish()
        removed = digest_of_body("harbor-octas-neg")
        suppress(imported, removed)
        refuse_version_listing(monkeypatch)

        error = status_error()
        shown = status_as_a_person_reads_it()

        # expected_publish.json: the first two weeks hold it, the third does not.
        counts = {
            entry["snapshot"]: (entry["suppressed_rows"], entry["suppressed_row_prefixes"])
            for entry in error["details"]["snapshots"]
        }
        assert counts == {
            "2026-09-01": (1, [removed[:12]]),
            "2026-09-08": (1, [removed[:12]]),
            "2026-09-15": (0, []),
        }
        assert error["details"]["suppressed_objects"] == [
            {"caselist": SYNTHETIC_CASELIST, "objects": 1, "sha256_prefixes": [removed[:12]]}
        ]
        assert error["message"] == (
            "2 snapshot(s) differ between this machine and the bucket: "
            f"{SYNTHETIC_CASELIST} 2026-09-01 (1 suppressed row(s)), "
            f"{SYNTHETIC_CASELIST} 2026-09-08 (1 suppressed row(s)); and the bucket still holds "
            f"1 current object(s) of suppressed sources: {SYNTHETIC_CASELIST} 1"
        )
        assert "caselist-removal.md" in error["hint"]
        assert "Suppressed rows" in shown
        assert (
            f"SUPPRESSED SOURCE OBJECTS in {SYNTHETIC_CASELIST}: 1 current object(s) "
            f"(sha256 {removed[:12]})" in shown
        )
        # A removed file is named by twelve characters, as the residue report names one.
        assert removed not in json.dumps(error) + shown

    def test_status_whose_only_difference_is_a_suppressed_object_says_so_not_zero_snapshots_differ(
        self, buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        publish()
        leftover = hashlib.sha256(b"a synthetic later upload nobody's manifest names").hexdigest()
        key = f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{leftover[0:2]}/{leftover[2:4]}/{leftover}"
        buckets.put_object(Bucket=DEV_BUCKET, Key=key, Body=b"leftover")
        suppress(imported, leftover)
        refuse_version_listing(monkeypatch)

        error = status_error()
        shown = status_as_a_person_reads_it()

        assert error["code"] == "CASELIST_DRIFT"
        assert error["exit_code"] == ExitCode.DOMAIN_FAILURE
        assert error["message"] == (
            "every snapshot agrees, and the bucket still holds 1 current object(s) of suppressed "
            f"sources: {SYNTHETIC_CASELIST} 1"
        )
        assert "0 snapshot(s)" not in shown
        assert "caselist-removal.md" in error["hint"]
        assert "caselist publish" not in error["hint"]
        assert f"SUPPRESSED SOURCE OBJECTS in {SYNTHETIC_CASELIST}: 1 current object(s)" in shown


# ------------------------------------------------------------------------------------------------
# What a person sees
# ------------------------------------------------------------------------------------------------


def test_the_rendered_output_names_nothing_identifying(
    buckets: S3Client, imported: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Personal-data rule 4, for the text a terminal, a CI log or a scheduled job's log keeps."""
    failing = digest_of_body("bayview-semis-neg")
    real_put = S3EvidenceObjectStore.put_file

    async def put_file(self: S3EvidenceObjectStore, key: str, source: Path) -> ObjectInfo:
        if key.endswith(failing):
            raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")
        return await real_put(self, key, source)

    monkeypatch.setattr(S3EvidenceObjectStore, "put_file", put_file)
    outputs = [
        invoke("--verbose", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST, "--dry-run"),
        invoke("--verbose", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST),
        invoke("--verbose", "caselist", "status"),
        publish(),
        invoke("--json", "caselist", "status"),
    ]

    text = "\n".join(result.output for result in outputs)
    assert failing in text
    for identifier in FICTIONAL_IDENTIFIERS:
        assert identifier not in text, identifier

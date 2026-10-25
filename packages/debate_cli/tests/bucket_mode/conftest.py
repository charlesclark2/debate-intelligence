"""A dev installation in bucket mode, over moto's S3 and a fake OpenCaselist (`v1-e40-t04`).

Through Typer's `CliRunner` against the real application and composition root, as
`commands/test_caselist_pull_parses.py` runs a pull: the real OpenCaselist client answered by respx,
the real importers, parse pipeline, publishers and search index stage. The bucket is moto's, versioned
like the real ones, with conditional writes. Two things are replaced, both to keep a test in this
process: the parse pool is the in-process runner, and each test's clock is one it moves, so that a
lease can expire without waiting half an hour.

The archives are the fictional caselist of `tests/fixtures/parse_pipeline/build_parse_world.py`
(`docs/policies/caselist-data-use.md`): nothing here is real. No test here opens a socket.

Each run names its data directory by `DEBATE_STORAGE__DATA_DIR`, so one test can run on a full
directory and on an empty one against the same bucket.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
import respx
from moto import mock_aws
from tests.fixtures.parse_pipeline.build_parse_world import BODIES, CASELIST, WEEKS, build_week_zips
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_core.application.caselist.parse_workers import InProcessParseRunner

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

API: Final = "https://api.opencaselist.example.invalid/v1"
FILE_HOST: Final = "https://files.opencaselist.example.invalid"
BUCKET: Final = "debate-dev-evidence-moto"
PROFILE: Final = "debate-dev-evidence"
WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
START: Final = datetime(2026, 10, 14, 11, 0, 5, tzinfo=UTC)

CAMP_FILE: Final = {
    "openev_id": 512,
    "path": "/openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx",
    "filename": "TSF-Estuary Solvency Advocate.docx",
    "year": 2026,
    "camp": "Tamarack",
    "tags": {"policy": True},
}
"""One invented camp file, holding the parse world's `cardmirror` body, so that the `openev` store the
search index reads has a card of its own."""

runner = CliRunner()


def weekly_name(day: date) -> str:
    return f"{CASELIST}-weekly-{day.isoformat()}.zip"


@dataclass
class TestClock:
    """The clock every command in a test reads: `caselist pull`'s, and the run lock's."""

    now: datetime = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


@dataclass
class World:
    """One test's installation: where its data directories are, its bucket and its clock."""

    root: Path
    client: S3Client
    clock: TestClock
    site: respx.MockRouter
    monkeypatch: pytest.MonkeyPatch
    data_dir: Path = field(init=False)
    bucket: str = BUCKET

    def __post_init__(self) -> None:
        self.data_dir = self.root / "data"

    def use_bucket(self, name: str) -> None:
        """Point the next command at bucket `name`, which is created, versioned, if it is not there."""
        self._create(name)
        self.bucket = name
        self.monkeypatch.setenv("DEBATE_STORAGE__S3__BUCKET", name)

    def copy_bucket(self, to: str) -> None:
        """Copy every current object of this bucket, with its metadata, into bucket `to`."""
        self._create(to)
        for key in sorted(self.keys()):
            self.client.copy_object(Bucket=to, Key=key, CopySource={"Bucket": self.bucket, "Key": key})

    def use(self, data_dir: Path) -> Path:
        """Point the next command at `data_dir`."""
        self.data_dir = data_dir
        self.monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))
        return data_dir

    def mode(self, run_state: str) -> None:
        self.monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", run_state)

    def listing(self, *weeks: date) -> None:
        """Make the site list exactly `weeks`."""
        self.site.get(f"{API}/caselists/{CASELIST}/downloads").respond(
            200,
            json=[{"name": weekly_name(day), "url": f"{FILE_HOST}/{weekly_name(day)}"} for day in weeks],
        )

    def invoke(self, *arguments: str) -> Result:
        return runner.invoke(create_app(), list(arguments))

    def run(self, *arguments: str) -> dict[str, Any]:
        """Run a command asking for JSON; its envelope, with the exit code on it."""
        result = self.invoke("--json", *arguments)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert lines, f"no JSON on stdout: {result.output!r} {result.exception!r}"
        envelope = json.loads(lines[-1])
        assert isinstance(envelope, dict)
        envelope["exit_code"] = result.exit_code
        return envelope  # pyright: ignore[reportUnknownVariableType]

    def pull(self, *arguments: str) -> dict[str, Any]:
        return self.run("caselist", "pull", "--caselist", CASELIST, *arguments)

    def seed(self) -> dict[str, Any]:
        """Seed the bucket from the data directory in use, as the cutover does: bucket mode, `--execute`."""
        self.mode("bucket")
        seeded = self.run("caselist", "seed-run-state", "--execute")
        assert seeded["exit_code"] == 0, seeded
        return seeded

    # -- reading the bucket ---------------------------------------------------------------------

    def keys(self, prefix: str = "") -> set[str]:
        found: set[str] = set()
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            found.update(str(item.get("Key")) for item in page.get("Contents", []))
        return found

    def body(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def lock(self) -> dict[str, Any]:
        return json.loads(self.body("reports/sync/run-lock.json"))

    def versions(self, prefix: str) -> list[dict[str, Any]]:
        listed = self.client.list_object_versions(Bucket=self.bucket, Prefix=prefix)
        return [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]  # pyright: ignore[reportReturnType]

    def last_record(self, data_dir: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """This machine's newest run record and its details, as the run log keeps them."""
        directory = data_dir or self.data_dir
        records = (directory / "caselist-sync-runs.jsonl").read_text(encoding="utf-8").splitlines()
        details = (directory / "caselist-sync-run-details.jsonl").read_text(encoding="utf-8").splitlines()
        return json.loads(records[-1]), json.loads(details[-1])

    def _create(self, name: str) -> None:
        if name not in {one["Name"] for one in self.client.list_buckets().get("Buckets", [])}:
            self.client.create_bucket(Bucket=name)
            self.client.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})

    def parsed_digests(self, data_dir: Path | None = None) -> dict[str, str]:
        """Every parsed-store file under a data directory with its SHA-256: what two parses are compared by."""
        root = (data_dir or self.data_dir) / "parsed"
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def published_index(self) -> dict[str, Any]:
        """The published search index's manifest, read as the pilot reads it: through current.json."""
        pointer = json.loads(self.body("reports/tub/search/current.json"))
        return json.loads(self.body(pointer["manifest_key"]))

    def everything(self) -> dict[str, str]:
        """Every current object's key and ETag: what a refused runner must leave as it was."""
        found: dict[str, str] = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket):
            found.update({str(item.get("Key")): str(item.get("ETag")) for item in page.get("Contents", [])})
        return found


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """A dev installation in local mode, over an empty versioned moto bucket and the fictional site."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    config.write_text(f"[profile {PROFILE}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{PROFILE}]\naws_access_key_id = testing\naws_secret_access_key = testing\n", encoding="utf-8"
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{PROFILE}"\n',
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
        "DEBATE_PROFILE_DIR": str(profiles),
        "DEBATE_ENV": "dev",
        "DEBATE_STORAGE__DATA_DIR": str(tmp_path / "data"),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__MIN_REQUEST_INTERVAL_SECONDS": "0.5",
        "DEBATE_CASELIST__NOTIFIER": "none",
        "DEBATE_PROVIDERS__CASELIST_TOKEN": f"fixture-token-{secrets.token_hex(8)}",
        "DEBATE_CASELIST__FULL_ARCHIVE_ROTATION": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("debate_cli.container.ProcessPoolParseRunner", lambda **_: InProcessParseRunner())
    clock = TestClock()
    monkeypatch.setattr("debate_cli.container._utc_now", clock)
    zips = build_week_zips(tmp_path / "published")
    with mock_aws(), respx.mock(assert_all_called=False) as site:
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        site.get(f"{API}/openev").respond(200, json=[CAMP_FILE])
        site.get(f"{API}/download").respond(200, content=BODIES["cardmirror"])
        for week in WEEKS:
            site.get(f"{FILE_HOST}/{weekly_name(week.snapshot)}").respond(
                200, content=zips[week.snapshot].read_bytes()
            )
        yield World(root=tmp_path, client=client, clock=clock, site=site, monkeypatch=monkeypatch)

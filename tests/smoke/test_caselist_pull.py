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

import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
import respx
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.caselist.publish_expectations import expected_publish
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-pull-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
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
    config.write_text(f"[profile {AWS_PROFILE_NAME}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{AWS_PROFILE_NAME}]\naws_access_key_id = testing\naws_secret_access_key = testing\n",
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


@pytest.fixture
def site(installation: Path) -> Iterator[respx.MockRouter]:
    """OpenCaselist: three weekly archives, one full archive, and one new OpenEv camp file."""
    zips = build_snapshot_zips(installation / "published")
    listing = [
        {"name": weekly_name(week.snapshot), "url": f"{FILE_HOST}/{weekly_name(week.snapshot)}"}
        for week in SNAPSHOTS
    ]
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    listing.append({"name": full, "url": f"{FILE_HOST}/{full}"})
    camp_file = {
        "openev_id": OPENEV_FILE_ID,
        "path": f"/openev/{OPENEV_YEAR}/Tamarack/{OPENEV_FILENAME}",
        "filename": OPENEV_FILENAME,
        "year": OPENEV_YEAR,
        "camp": "Tamarack Summer Forum",
        "tags": {"policy": True},
    }
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=listing)
        router.get(f"{API}/openev").respond(200, json=[camp_file])
        router.get(f"{API}/download").respond(200, content=DOCUMENT_BODIES["estuary-solvency"])
        for week in SNAPSHOTS:
            router.get(f"{FILE_HOST}/{weekly_name(week.snapshot)}").respond(
                200, content=zips[week.snapshot].read_bytes()
            )
        router.get(f"{FILE_HOST}/{full}").respond(200, content=b"never pulled by a weekly run")
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
    bytes no archive holds.
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
    assert data["archives_downloaded"] == 3
    assert data["openev_downloaded"] == 1
    assert data["objects_published"] == expected["totals"]["source_objects"] + 1
    assert data["snapshots_imported"] == [
        *(f"{SYNTHETIC_CASELIST} {week.snapshot.isoformat()}" for week in SNAPSHOTS),
        "openev 2026-policy",
    ]

    stages = {one["stage"]: one for one in data["stages"]}
    assert stages["publish"]["outcome"] == "completed"
    assert stages["report"]["outcome"] == "completed"
    assert stages["parse"]["outcome"] == "skipped", "v1-e31-t06 has not shipped; it must skip, not fail"
    assert stages["landscape"]["outcome"] == "skipped"

    keys = {str(item.get("Key")) for item in bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])}
    for week in SNAPSHOTS:
        assert f"manifests/{SYNTHETIC_CASELIST}/{week.snapshot.isoformat()}.jsonl" in keys
    assert "manifests/openev/2026-policy.jsonl" in keys

    status = run("caselist", "status")
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["in_sync"] is True

    again = run("caselist", "pull")
    assert again["exit_code"] == ExitCode.OK, again
    assert again["data"]["nothing_new"] is True
    assert again["data"]["archives_downloaded"] == 0
    assert again["data"]["openev_downloaded"] == 0


def test_the_full_archive_is_listed_and_never_fetched_by_a_weekly_run(
    installation: Path, bucket: S3Client, site: respx.MockRouter
) -> None:
    """The open question this task raises: today a weekly run pulls weeklies and nothing else."""
    pulled = run("caselist", "pull")

    decisions = {one["archive"]: one["decision"] for one in pulled["data"]["selections"]}
    full = f"{SYNTHETIC_CASELIST}-all-{SNAPSHOTS[-1].snapshot.isoformat()}.zip"
    assert decisions[full] == "full_archive_not_pulled_weekly"
    assert not any(call.request.url.path.endswith(full) for call in site.calls)


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

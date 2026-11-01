"""What `caselist runs` and `caselist status` say of the parses owed, on the installed build (`v1-e40-t26`).

`v1-e40-t08` gave both commands the parse-owed file's entries as `parses_owed` in `--json`, and a
sentence at the end of each table's caption. Thursday's read of a Wednesday run that owes a full
parse under a new parser version is these two commands, `caselist runs --remote` reading the
bucket's copy, the cloud run's. Here a data directory, and a bucket, hold a parse-owed file, and
then hold none.

The file is written by t08's own writer, `ParseOwed.owe`, at the name the build reads,
`caselist-sync-parse-owed.json`, so a change to its name or shape fails this check rather than
leaving a hand-copied body behind it. What the commands print is written by hand (working
agreement 6).

The bucket is moto in server mode, a stand-in the build reaches over loopback (`v1-e01-t21`,
tests/smoke/stand_ins/): `caselist status` refuses an environment that names no bucket, and one
whose store holds no manifest on either side, so two of the invented weeks from
`tests/fixtures/caselist/` are imported and published first, and `status` reports them in
agreement. `--remote` reads the bucket. Not marked `live`: nothing leaves the machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import InstalledCli
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3StandIn

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_sync import (
    PARSE_OWED_FILENAME,
    FullParseOwed,
    ParseOwed,
    PendingSnapshot,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUCKET = "debate-dev-evidence-parses-owed-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
NEW_PARSER_VERSION = "2026.10.27-docx-7"

STATE_KEY = "reports/sync/state/caselist-sync-parse-owed.json"
"""Where the cloud run saves the file, and `caselist runs --remote` reads it (`v1-e40-t04`, `v1-e40-t08`)."""

NOTHING_OWED = {"full_parses": [], "snapshots": []}


@pytest.fixture
def installation(installed_cli: InstalledCli, s3_stand_in: S3StandIn, tmp_path: Path) -> Path:
    """A dev profile naming the stand-in's bucket, and moto's test credentials under its profile."""
    config = tmp_path / "aws-config"
    config.write_text(f"[profile {AWS_PROFILE_NAME}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{AWS_PROFILE_NAME}]\naws_access_key_id = {MOTO_TEST_CREDENTIALS['aws_access_key_id']}\n"
        f"aws_secret_access_key = {MOTO_TEST_CREDENTIALS['aws_secret_access_key']}\n",
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(credentials),
    )
    return tmp_path


@pytest.fixture
def bucket(installation: Path, s3_stand_in: S3StandIn) -> S3Client:
    return s3_stand_in.versioned_bucket(BUCKET)


@pytest.fixture
def run(installed_cli: InstalledCli) -> Any:
    def run(*arguments: str) -> dict[str, Any]:
        """Run one command asking for JSON, and return its envelope with the exit code on it."""
        result = installed_cli.run("--json", *arguments)
        envelope = result.envelope()
        envelope["exit_code"] = result.exit_code
        return envelope

    return run


@pytest.fixture
def published(installation: Path, bucket: S3Client, run: Any) -> tuple[str, ...]:
    """The first two synthetic weeks imported here and published: a store `caselist status` reports
    in agreement. Their names."""
    zips = build_snapshot_zips(installation / "downloads")
    weeks = tuple(week.snapshot for week in SNAPSHOTS[:2])
    for week in weeks:
        imported = run(
            "caselist",
            "import",
            str(zips[week]),
            "--caselist",
            SYNTHETIC_CASELIST,
            "--snapshot",
            week.isoformat(),
        )
        assert imported["exit_code"] == ExitCode.OK, imported
    publish = run("caselist", "publish", "--caselist", SYNTHETIC_CASELIST)
    assert publish["exit_code"] == ExitCode.OK, publish
    return tuple(week.isoformat() for week in weeks)


@pytest.fixture
def shown(installed_cli: InstalledCli) -> Any:
    def shown(*arguments: str) -> str:
        """One command's table, its words alone: Rich wraps a caption at the table's width."""
        result = installed_cli.run(*arguments, env={"COLUMNS": "200"})
        assert result.exit_code == ExitCode.OK, result.stdout
        return " ".join(result.stdout.split())

    return shown


def owed_file(directory: Path, *, snapshots: tuple[str, ...] = (), full_parses: tuple[str, ...] = ()) -> Path:
    """The parse-owed file in `directory`, written by t08's writer: `snapshots` of the synthetic
    caselist, and a full parse of each of `full_parses` under the new parser version."""
    assert PARSE_OWED_FILENAME == "caselist-sync-parse-owed.json"
    path = directory / PARSE_OWED_FILENAME
    ParseOwed(path).owe(
        snapshots=[PendingSnapshot(caselist=SYNTHETIC_CASELIST, snapshot=one) for one in snapshots],
        full_parses=[FullParseOwed(caselist=one, parser_version=NEW_PARSER_VERSION) for one in full_parses],
    )
    assert path.is_file()
    return path


def test_parses_owed_in_the_data_directory_are_shown_by_caselist_runs_and_caselist_status(
    installation: Path, published: tuple[str, ...], run: Any, shown: Any
) -> None:
    """The two weeks published and not parsed, and a full parse owed of two caselists: both commands
    give every entry in `--json` and say each in the caption."""
    assert published == ("2026-09-01", "2026-09-08")
    owed_file(
        installation / "data",
        snapshots=published,
        full_parses=(SYNTHETIC_CASELIST, "openev"),
    )
    expected = {
        "full_parses": [
            {"caselist": "testcl26", "parser_version": "2026.10.27-docx-7"},
            {"caselist": "openev", "parser_version": "2026.10.27-docx-7"},
        ],
        "snapshots": [
            {"caselist": "testcl26", "snapshot": "2026-09-01"},
            {"caselist": "testcl26", "snapshot": "2026-09-08"},
        ],
    }
    said = (
        "Parse owed: testcl26 2026-09-01, testcl26 2026-09-08. The next caselist pull parses and "
        "publishes them, whether or not it imports anything. Full parse owed under parser version "
        "2026.10.27-docx-7: testcl26, openev. The next caselist pull parses and publishes it before "
        "it builds the search index."
    )

    runs = run("caselist", "runs")
    status = run("caselist", "status")

    assert runs["exit_code"] == ExitCode.OK, runs
    assert runs["data"]["parses_owed"] == expected
    assert status["exit_code"] == ExitCode.OK, status
    assert status["data"]["parses_owed"] == expected
    assert said in shown("caselist", "runs")
    assert said in shown("caselist", "status")


def test_parses_owed_in_the_bucket_are_shown_by_caselist_runs_remote_and_not_by_this_machine(
    installation: Path, bucket: S3Client, run: Any, shown: Any
) -> None:
    """Thursday's read of Wednesday's run: the cloud run owes a full parse under the parser version its
    image brought, and only the bucket's copy says so."""
    cloud_run = installation / "cloud-run"
    cloud_run.mkdir()
    written = owed_file(cloud_run, full_parses=(SYNTHETIC_CASELIST, "openev"))
    bucket.put_object(Bucket=BUCKET, Key=STATE_KEY, Body=written.read_bytes())
    expected = {
        "full_parses": [
            {"caselist": "testcl26", "parser_version": "2026.10.27-docx-7"},
            {"caselist": "openev", "parser_version": "2026.10.27-docx-7"},
        ],
        "snapshots": [],
    }
    said = (
        "Full parse owed under parser version 2026.10.27-docx-7: testcl26, openev. The next caselist "
        "pull parses and publishes it before it builds the search index."
    )

    remote = run("caselist", "runs", "--remote")
    local = run("caselist", "runs")

    assert remote["exit_code"] == ExitCode.OK, remote
    assert remote["data"]["source"] == "bucket"
    assert remote["data"]["parses_owed"] == expected
    assert said in shown("caselist", "runs", "--remote")
    assert local["data"]["parses_owed"] == NOTHING_OWED, "this machine owes nothing"
    assert "parse owed" not in shown("caselist", "runs").lower()


def test_no_parses_owed_is_shown_as_nothing_by_caselist_runs_and_caselist_status(
    installation: Path, bucket: S3Client, published: tuple[str, ...], run: Any, shown: Any
) -> None:
    """No file here and none in the bucket, then the empty object a run saves for a file it removed
    (`RunState`'s save, `v1-e40-t04`): `parses_owed` holds two empty lists, the key present, and no
    caption says a parse is owed. `caselist publish` owes no parse: only a pull's publish stage does."""
    assert not (installation / "data" / PARSE_OWED_FILENAME).exists()

    for arguments in (("caselist", "runs"), ("caselist", "runs", "--remote"), ("caselist", "status")):
        envelope = run(*arguments)
        assert envelope["exit_code"] == ExitCode.OK, envelope
        assert envelope["data"]["parses_owed"] == NOTHING_OWED, arguments
        assert "parse owed" not in shown(*arguments).lower(), arguments

    bucket.put_object(Bucket=BUCKET, Key=STATE_KEY, Body=b"")
    assert run("caselist", "runs", "--remote")["data"]["parses_owed"] == NOTHING_OWED
    assert "parse owed" not in shown("caselist", "runs", "--remote").lower()

"""`debate-research landscape report`, run the way an operator runs it (`v1-e32-t05`).

Through Typer's `CliRunner` against the real application and composition root, over `synthetic26`
(:mod:`debate_core.testing.landscape_run`), with the real S3 adapter over moto for `--publish`. Dev
and prod name different moto buckets, so a publish that went to the wrong one shows. The counts are
the fixture table's, worked out by hand in that module's docstring.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

import debate_cli.container as container_module
from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.landscape_run import LandscapeRunService, PositionClassifier
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.classification_store import ClassificationStore
from debate_core.application.position_classification import ClassificationRun, PositionClassificationService
from debate_core.integrations.landscape.classification_store import review_queue_path
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.testing.landscape_run import (
    SYNTHETIC_RUN_CASELIST,
    SYNTHETIC_RUN_TODAY,
    SYNTHETIC_RUN_TOPIC,
    SyntheticRun,
    plant_synthetic_run,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

CASELIST = SYNTHETIC_RUN_CASELIST
DEV_BUCKET = "debate-dev-evidence-moto"
PROD_BUCKET = "debate-prod-evidence-moto"
PROFILES = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}
BUNDLE = ("positions.csv", "top_cards.csv", "impact_cards.csv", "report.md")
KEYS = [f"reports/landscape/{CASELIST}/2026-09-15/{name}" for name in BUNDLE]
PLANTED_CODE = {("neg-two", 0): "As PX argued, new spending triggers a crowd-out"}


def _installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, world: SyntheticRun) -> None:
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
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment, bucket in (("dev", DEV_BUCKET), ("prod", PROD_BUCKET)):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{world.data_dir}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            f'aws_profile = "{PROFILES[environment]}"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[providers]\nenabled = []\n[storage]\ndata_dir = "{world.data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SyntheticRun:
    planted = plant_synthetic_run(tmp_path / "world")
    _installation(monkeypatch, tmp_path, planted)
    return planted


@pytest.fixture
def planted_world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SyntheticRun:
    """`synthetic26` with Harrowgate Prep's code `PX` in a tag every report lists."""
    planted = plant_synthetic_run(tmp_path / "world", planted_tags=PLANTED_CODE)
    _installation(monkeypatch, tmp_path, planted)
    return planted


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two days after the newest snapshot, so the report is current."""
    moment = datetime(
        SYNTHETIC_RUN_TODAY.year, SYNTHETIC_RUN_TODAY.month, SYNTHETIC_RUN_TODAY.day, 9, tzinfo=UTC
    )
    monkeypatch.setattr(container_module, "_utc_now", lambda: moment)


@pytest.fixture
def buckets() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
        yield client


def _keys(client: S3Client, bucket: str) -> list[str]:
    listed = client.list_objects_v2(Bucket=bucket)
    return sorted(item["Key"] for item in listed.get("Contents", []))  # pyright: ignore[reportTypedDictNotRequiredAccess]


def landscape(world: SyntheticRun, *arguments: str, json_output: bool = True) -> Result:
    command = ["--json"] if json_output else []
    command += ["landscape", "report", "--config-dir", str(world.config_dir), *arguments]
    return runner.invoke(create_app(), command)


def _data(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout)["data"]


def _error(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout)["error"]


# ------------------------------------------------------------------------------------------------
# ac1: the bundle and the JSON
# ------------------------------------------------------------------------------------------------


def test_report_writes_the_bundle_and_json_names_paths_counts_methods_and_model_calls(
    world: SyntheticRun,
) -> None:
    result = landscape(world, "--caselist", CASELIST, "--no-publish", "--model-mode", "none")

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    directory = world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15"
    assert data["paths"] == {
        "directory": str(directory),
        "files": [str(directory / name) for name in BUNDLE],
    }
    assert all(Path(path).is_file() for path in data["paths"]["files"])
    assert (data["snapshot"], data["topic_id"], data["model_mode"], data["model_calls"]) == (
        "2026-09-15",
        SYNTHETIC_RUN_TOPIC,
        "none",
        0,
    )
    assert data["classification"]["cards_by_method"] == {"ALIAS": 7, "UNPLACED": 2}
    counts = data["counts"]
    assert (counts["sources"], counts["cards"], counts["cards_counted"], counts["positions"]) == (4, 9, 7, 4)
    assert (counts["rounds"], counts["teams"], counts["aff_rounds"], counts["aff_rounds_unidentified"]) == (
        4,
        3,
        2,
        0,
    )
    assert data["staleness"]["stale"] is False
    assert data["publish"] is None
    assert data["scan"] == {
        "hits": [],
        "not_yet_accepted": 0,
        "digest": data["scan"]["digest"],
        "accepted_now": False,
        "acceptance_log": None,
    }
    assert data["notice"] is None


def test_the_command_identifies_each_aff_round_through_t09s_plan_texts(world: SyntheticRun) -> None:
    """`aff-two` names single payer only in its plan text; `aff-one` places a card under it."""
    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert data["aff_assignments"] == 1
    assert data["aff_identification"] == {"PLACED_CARD": 1, "PLAN_TEXT": 1}
    assert (world.data_dir / "landscape" / "plan_texts" / f"{CASELIST}.jsonl").is_file()


def test_report_prints_counts_and_where_it_wrote_for_a_person(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    assert "Sources 4; cards 9, 7 counted (77.8%); by method: ALIAS 7, UNPLACED 2." in result.stdout
    assert "Scan: 0 hit(s), 0 not yet accepted." in result.stdout


def test_a_model_mode_other_than_none_is_a_usage_error(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--model-mode", "replay")

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert not (world.data_dir / "reports").exists()


def test_out_inside_a_checkout_is_refused(world: SyntheticRun) -> None:
    inside = Path(__file__).resolve().parent / "landscape-out"
    result = landscape(world, "--caselist", CASELIST, "--out", str(inside))

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert not inside.exists()


# ------------------------------------------------------------------------------------------------
# ac2: refusals
# ------------------------------------------------------------------------------------------------


def test_an_unknown_caselist_exits_2_with_the_known_caselists(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", "hsnope26")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    error = _error(result)
    assert (error["code"], error["details"]["known"]) == ("UNKNOWN_CASELIST", [CASELIST])


def test_an_unknown_snapshot_exits_2_with_the_known_snapshots(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--snapshot", "2026-09-09")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    error = _error(result)
    assert (error["code"], error["details"]["known"]) == ("UNKNOWN_SNAPSHOT", ["2026-09-08", "2026-09-15"])


def test_a_caselist_topics_yaml_does_not_map_exits_2_naming_the_file(world: SyntheticRun) -> None:
    topics = world.config_dir / "topics.yaml"
    topics.write_text(topics.read_text(encoding="utf-8").replace("from: 2026-09-01", "from: 2026-10-01"))

    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    error = _error(result)
    assert (error["code"], error["details"]["file_to_edit"]) == ("NO_TOPIC_MAPPING", str(topics))
    assert error["hint"] == f"Edit {topics}."


class _SendsToTheModel:
    def __init__(self, inner: PositionClassifier) -> None:
        self._inner = inner

    async def classify(self, reading: SeedReading) -> ClassificationRun:
        import dataclasses

        run = await self._inner.classify(reading)
        return dataclasses.replace(run, counts=dataclasses.replace(run.counts, model_items=3, model_calls=1))


def test_publish_over_the_model_budget_exits_1_after_the_review_queue_without_publishing(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    taxonomies = YamlTaxonomyRepository.load(world.config_dir)

    def classifier(store: ClassificationStore) -> PositionClassifier:
        return _SendsToTheModel(PositionClassificationService(taxonomies=taxonomies, store=store))

    monkeypatch.setattr(
        container_module, "LandscapeRunService", functools.partial(LandscapeRunService, classifier=classifier)
    )

    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = _error(result)
    assert (error["code"], error["details"]["sent"], error["details"]["allowed"]) == (
        "MODEL_BUDGET_EXCEEDED",
        3,
        0,
    )
    assert review_queue_path(world.data_dir, CASELIST, SYNTHETIC_RUN_TOPIC).is_file()
    assert not (world.data_dir / "reports").exists()
    assert _keys(buckets, DEV_BUCKET) == []


# ------------------------------------------------------------------------------------------------
# ac3: publishing against moto
# ------------------------------------------------------------------------------------------------


def test_publish_puts_the_bundle_under_reports_landscape_in_the_dev_bucket(
    world: SyntheticRun, buckets: S3Client
) -> None:
    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.OK, result.output
    assert _keys(buckets, DEV_BUCKET) == sorted(KEYS)
    assert _keys(buckets, PROD_BUCKET) == []
    data = _data(result)
    assert data["publish"]["uploaded"] == KEYS
    assert data["publish"]["bucket"] == DEV_BUCKET
    local = Path(data["paths"]["directory"]) / "report.md"
    stored = buckets.get_object(Bucket=DEV_BUCKET, Key=KEYS[BUNDLE.index("report.md")])["Body"].read()
    assert stored == local.read_bytes()
    assert "presign" not in result.stdout.casefold() and "X-Amz-Signature" not in result.stdout


def test_publish_a_second_identical_run_uploads_nothing(world: SyntheticRun, buckets: S3Client) -> None:
    assert landscape(world, "--caselist", CASELIST, "--publish").exit_code == ExitCode.OK
    second = landscape(world, "--caselist", CASELIST, "--publish")

    assert second.exit_code == ExitCode.OK, second.output
    publish = _data(second)["publish"]
    assert (publish["uploaded"], publish["unchanged"]) == ([], KEYS)
    assert {one["action"] for one in publish["planned"]} == {"UNCHANGED"}


def test_publish_dry_run_lists_the_planned_uploads_and_writes_nothing(
    world: SyntheticRun, buckets: S3Client
) -> None:
    result = landscape(world, "--caselist", CASELIST, "--publish", "--dry-run")

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert [(one["key"], one["action"]) for one in data["publish"]["planned"]] == [
        (key, "UPLOAD") for key in KEYS
    ]
    assert data["publish"]["uploaded"] == [] and data["written"] is False
    assert _keys(buckets, DEV_BUCKET) == []
    assert not (world.data_dir / "reports").exists()
    assert not (world.data_dir / "landscape").exists()


def test_publish_with_debate_env_unset_goes_to_dev_never_prod(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEBATE_ENV")
    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.OK, result.output
    assert (_data(result)["environment"], _keys(buckets, PROD_BUCKET)) == ("dev", [])


def test_publish_to_prod_without_confirm_prod_is_refused_before_anything_is_built(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert _error(result)["code"] == "CONFIRMATION_REQUIRED"
    assert _keys(buckets, PROD_BUCKET) == []
    assert not (world.data_dir / "reports").exists()


def test_publish_in_the_test_environment_is_refused(
    world: SyntheticRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "test")
    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert _error(result)["code"] == "ENVIRONMENT_NOT_SYNCABLE"


# ------------------------------------------------------------------------------------------------
# The scan before sharing, through the command
# ------------------------------------------------------------------------------------------------


def test_publish_with_a_planted_team_code_is_refused_printing_the_hit_and_its_digest(
    planted_world: SyntheticRun, buckets: S3Client
) -> None:
    result = landscape(planted_world, "--caselist", CASELIST, "--publish", json_output=False)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert "Scan: 1 hit(s), 1 not yet accepted (digest " in result.stdout
    assert "top_cards.csv:" in result.stdout and "team_code 'PX'" in result.stdout
    assert "As PX argued" in result.stdout
    assert "SCAN_HITS_NOT_ACCEPTED" in result.output and "--accept-scan-hits" in result.output
    assert _keys(buckets, DEV_BUCKET) == []
    assert (
        planted_world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15" / "report.md"
    ).is_file()


def test_publish_with_the_printed_digest_goes_ahead_and_a_stale_one_is_refused(
    planted_world: SyntheticRun, buckets: S3Client
) -> None:
    refused = landscape(planted_world, "--caselist", CASELIST, "--publish")
    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    error = _error(refused)
    assert error["code"] == "SCAN_HITS_NOT_ACCEPTED"
    digest = error["details"]["scan"]["digest"]
    assert error["details"]["notice"] is not None

    stale = landscape(planted_world, "--caselist", CASELIST, "--publish", "--accept-scan-hits", "0" * 12)
    assert stale.exit_code == ExitCode.DOMAIN_FAILURE
    assert _error(stale)["code"] == "SCAN_DIGEST_STALE"
    assert _keys(buckets, DEV_BUCKET) == []

    accepted = landscape(planted_world, "--caselist", CASELIST, "--publish", "--accept-scan-hits", digest)
    assert accepted.exit_code == ExitCode.OK, accepted.output
    scan = _data(accepted)["scan"]
    assert scan["accepted_now"] is True and scan["digest"] == digest
    assert _keys(buckets, DEV_BUCKET) == sorted(KEYS)

    later = landscape(planted_world, "--caselist", CASELIST, "--publish")
    assert later.exit_code == ExitCode.OK, later.output
    assert _data(later)["scan"]["not_yet_accepted"] == 0

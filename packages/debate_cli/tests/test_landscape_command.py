"""`debate-research landscape report`, run the way an operator runs it (`v1-e32-t05`).

Through Typer's `CliRunner` against the real application and composition root, over `synthetic26`
(:mod:`debate_core.testing.landscape_run`), with the real S3 adapter over moto for `--publish`. Dev
and prod name different moto buckets, so a publish that went to the wrong one shows. The counts are
the fixture table's, worked out by hand in that module's docstring.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from pydantic import BaseModel
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

import debate_cli.commands.landscape as landscape_module
import debate_cli.container as container_module
from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.landscape_model_evaluation import FormatEvaluation
from debate_core.application.landscape_model_stage import ModelClassificationStage, ParsedStoreCardTexts
from debate_core.application.landscape_report import CIRCUIT_WIDE_FILES, SCHOOL_VIEW_FILES
from debate_core.application.landscape_run import BUNDLE_FILES, LandscapeRunService, PositionClassifier
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.classification_store import ClassificationStore
from debate_core.application.position_classification import ClassificationRun, PositionClassificationService
from debate_core.application.settings import load_settings
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    StageEntry,
    SyncRunLog,
    SyncRunOutcome,
    SyncRunRecord,
)
from debate_core.arguments.landscape.model_stage import NameScan
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.classification_store import review_queue_path
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.landscape_run import (
    SYNTHETIC_RUN_CASELIST,
    SYNTHETIC_RUN_TODAY,
    SYNTHETIC_RUN_TOPIC,
    SyntheticRun,
    plant_synthetic_run,
)
from debate_core.testing.landscape_store import PARSER_VERSION

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

CASELIST = SYNTHETIC_RUN_CASELIST
DEV_BUCKET = "debate-dev-evidence-moto"
PROD_BUCKET = "debate-prod-evidence-moto"
PROFILES = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}
BUNDLE = (
    "positions.csv",
    "top_cards.csv",
    "impact_cards.csv",
    "trends.csv",
    "schools.csv",
    "schools.md",
    "report.md",
)
KEYS = [f"reports/landscape/{CASELIST}/2026-09-15/{name}" for name in BUNDLE]
PLANTED_TOURNAMENT = {("neg-two", 0): "At Thistle Open, new spending triggers a crowd-out"}


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
    """`synthetic26` with the tournament `Thistle Open` in a tag every report lists.

    Since `v1-e32-t28` the report withholds a tag holding a team code, and quotes one holding a
    tournament's words, which the scan before sharing looks for.
    """
    planted = plant_synthetic_run(tmp_path / "world", planted_tags=PLANTED_TOURNAMENT)
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
    assert data["staleness"]["failed_run"] is None
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


def test_the_command_reads_the_analytic_texts_into_report_md(world: SyntheticRun) -> None:
    """`v1-e32-t11`'s seam is wired: the files are read into their own cache, and report.md has the sections.

    Only `aff-two` has bytes in the blob store, and it holds a plan text and no CP text, alternative or
    overview, so each section says it found none.
    """
    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    assert (world.data_dir / "landscape" / "analytic_texts" / f"{CASELIST}.jsonl").is_file()
    report = (world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15" / "report.md").read_text(
        encoding="utf-8"
    )
    assert "## Counterplan texts, alternatives and roles of the ballot" in report
    assert "No CP text was placed under a CP the team reads." in report
    assert "No overview was placed under a position the team reads." in report


def test_report_prints_counts_and_where_it_wrote_for_a_person(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    assert "Sources 4; cards 9, 7 counted (77.8%); by method: ALIAS 7, UNPLACED 2." in result.stdout
    assert "Scan: 0 hit(s), 0 not yet accepted." in result.stdout


def test_a_model_mode_the_command_does_not_offer_is_a_usage_error(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--model-mode", "record")

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert not (world.data_dir / "reports").exists()


# ------------------------------------------------------------------------------------------------
# v1-e32-t07: the model stage
#
# synthetic26 leaves 2 of its 9 cards unplaced (the run above), each its own fingerprint. The stage is
# built over a scripted router that places every card it is asked about under spending-da at 0.8.
# ------------------------------------------------------------------------------------------------


class _PlacesEverything(ScriptedModelRouter):
    parsed_dirs: list[Path | None]
    """The parsed store each stage this router was built into reads card texts from (`v1-e40-t17`)."""

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        items = json.loads(str(prompt.variables["items"]))
        self.enqueue(
            {
                "answers": [
                    {
                        "item": item["item"],
                        "position_id": "spending-da",
                        "confidence": 0.8,
                        "rationale": "a reason",
                    }
                    for item in items
                ]
            }
        )
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.fixture
def model_router(monkeypatch: pytest.MonkeyPatch) -> _PlacesEverything:
    router = _PlacesEverything(model_id="fake-model")
    router.parsed_dirs = []
    registry = PromptRegistry.load(Path(__file__).resolve().parents[3] / "prompts")

    def stage(
        self: container_module.ServiceContainer,
        mode: ModelMode,
        max_items: int,
        *,
        parsed_dir: Path | None = None,
        **_: object,
    ) -> ModelClassificationStage:
        assert mode is ModelMode.REPLAY
        router.parsed_dirs.append(parsed_dir)
        return ModelClassificationStage(
            StructuredOutputGuard(router, registry),
            ParsedStoreCardTexts(LocalParsedStore(parsed_dir or self.settings.storage.data_dir)),
            max_items=max_items,
        )

    monkeypatch.setattr(container_module.ServiceContainer, "landscape_model_stage", stage)
    return router


def test_replay_runs_the_model_stage_on_the_unplaced_cards_and_counts_it(
    world: SyntheticRun, model_router: _PlacesEverything
) -> None:
    result = landscape(world, "--caselist", CASELIST, "--no-publish", "--model-mode", "replay")

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert (data["model_mode"], data["model_calls"]) == ("replay", 1)
    assert data["classification"]["cards_by_method"] == {"ALIAS": 7, "MODEL": 2}
    model = data["classification"]["model"]
    assert (model["prompt_version"], model["asked"], model["held_back"], model["refused"]) == (
        "1.0.0",
        2,
        0,
        {},
    )
    assert len(model_router.calls) == 1


def test_replay_over_its_card_limit_exits_1_after_caching_what_it_asked(
    world: SyntheticRun, model_router: _PlacesEverything
) -> None:
    result = landscape(
        world, "--caselist", CASELIST, "--no-publish", "--model-mode", "replay", "--max-model-items", "1"
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = _error(result)
    assert (
        error["code"],
        error["details"]["sent"],
        error["details"]["allowed"],
        error["details"]["held_back"],
    ) == (
        "MODEL_BUDGET_EXCEEDED",
        1,
        1,
        1,
    )
    assert review_queue_path(world.data_dir, CASELIST, SYNTHETIC_RUN_TOPIC).is_file()
    assert not (world.data_dir / "reports").exists()

    again = landscape(
        world, "--caselist", CASELIST, "--no-publish", "--model-mode", "replay", "--max-model-items", "1"
    )
    assert again.exit_code == ExitCode.OK, again.output
    model = _data(again)["classification"]["model"]
    assert (model["asked"], model["cached"], model["held_back"]) == (1, 1, 0)
    assert len(model_router.calls) == 2


def test_a_dry_run_in_replay_asks_nothing_and_counts_what_it_would(
    world: SyntheticRun, model_router: _PlacesEverything
) -> None:
    result = landscape(
        world, "--caselist", CASELIST, "--dry-run", "--model-mode", "replay", "--max-model-items", "1"
    )

    assert result.exit_code == ExitCode.OK, result.output
    model = _data(result)["classification"]["model"]
    assert (model["asked"], model["held_back"], model["calls"]) == (1, 1, 0)
    assert model_router.calls == []


def test_live_is_refused_while_the_policy_leaves_question_four_open(
    world: SyntheticRun, model_router: _PlacesEverything, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "docs" / "policies").mkdir(parents=True)
    (checkout / "docs" / "policies" / "caselist-data-use.md").write_text(
        "| 4 | The provider's no-retention terms | **Open** | Operator | E32 gate |\n", encoding="utf-8"
    )
    monkeypatch.setattr(landscape_module, "find_repository_root", lambda *_: checkout)

    result = landscape(world, "--caselist", CASELIST, "--no-publish", "--model-mode", "live")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = _error(result)
    assert (error["code"], error["details"]["open_question"]) == ("MODEL_USE_NOT_YET_ALLOWED", 4)
    assert model_router.calls == []
    assert not (world.data_dir / "landscape").exists()


def test_the_container_builds_the_model_stage_from_the_committed_prompt(world: SyntheticRun) -> None:
    container = container_module.ServiceContainer(settings_loader=lambda: load_settings(environment="test"))
    built = container.landscape_model_stage(ModelMode.REPLAY, 7)

    assert (built.prompt_id, built.prompt_version, built.max_items) == (
        "landscape.classify_position",
        "1.0.0",
        7,
    )


def test_out_inside_a_checkout_is_refused(world: SyntheticRun) -> None:
    inside = Path(__file__).resolve().parent / "landscape-out"
    result = landscape(world, "--caselist", CASELIST, "--out", str(inside))

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert not inside.exists()


# ------------------------------------------------------------------------------------------------
# v1-e32-t12: the seven files, the trends and the school view
#
# Worked by hand from the fixture table in `debate_core.testing.landscape_run`. The 2026-09-15
# window's rounds are `neg-two` and `aff-two`, both Harrowgate Prep's; the 2026-09-08 window's are
# `aff-one` and `neg-one`. So each window has one team disclosing on each side, and:
#
# * single payer: aff-one's placed card before, aff-two's plan text now: 1 of 1 both weeks, STEADY;
# * costs advantage: aff-one before, aff-two now: 1 of 1 both weeks, STEADY;
# * spending DA: neg-one before, neg-two now: 1 of 1 both weeks, STEADY;
# * states CP: neg-one before, nobody now: down 100 points, but one team is under the floor of
#   three, so STEADY and held back.
#
# The school view is a row per team, side and position: Quillmere's aff single payer and costs
# advantage, Brindle Valley's neg spending DA and states CP, Harrowgate's aff single payer and costs
# advantage and neg spending DA. Seven rows, three schools, three team codes.
# ------------------------------------------------------------------------------------------------

SEVEN_FILES = [
    ("positions.csv", "circuit_wide"),
    ("top_cards.csv", "circuit_wide"),
    ("impact_cards.csv", "circuit_wide"),
    ("trends.csv", "circuit_wide"),
    ("schools.csv", "school_view"),
    ("schools.md", "school_view"),
    ("report.md", "circuit_wide"),
]
FICTIONAL_IDENTITIES = (
    "Quillmere",
    "Brindle",
    "Harrowgate",
    "Lantern Classic",
    "Thistle Open",
    '"QW"',
    '"PX"',
)


def _flat(text: str) -> str:
    """`text` with Rich's panel borders gone and its whitespace run together, as a person reads it."""
    return " ".join(text.replace("│", " ").split())


def test_json_marks_each_of_the_seven_files_circuit_wide_or_school_view(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    directory = world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15"
    assert _data(result)["bundle"] == [
        {"name": name, "path": str(directory / name), "view": view} for name, view in SEVEN_FILES
    ]


def test_the_seven_files_are_t04s_constants_not_a_copy() -> None:
    """The hand-written list above is the bundle t04 made, split as t04 splits it."""
    assert [name for name, _ in SEVEN_FILES] == list(BUNDLE_FILES)
    assert {name for name, view in SEVEN_FILES if view == "circuit_wide"} == set(CIRCUIT_WIDE_FILES)
    assert {name for name, view in SEVEN_FILES if view == "school_view"} == set(SCHOOL_VIEW_FILES)


def test_json_counts_the_trend_rows_by_label_and_the_rows_the_team_floor_held_back(
    world: SyntheticRun,
) -> None:
    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    assert _data(result)["trends"] == {
        "rows_by_label": {"NEW": 0, "RISING": 0, "FALLING": 0, "STEADY": 4},
        "held_back_by_team_floor": 1,
    }


def test_json_counts_the_school_view_and_names_no_school(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    assert _data(result)["school_view"] == {"schools": 3, "team_codes": 3, "rows": 7}
    for identity in FICTIONAL_IDENTITIES:
        assert identity not in result.stdout, identity


def test_the_first_window_on_a_topic_is_all_new_and_holds_nothing_back(world: SyntheticRun) -> None:
    """At 2026-09-08 there is no earlier window: its four positions are NEW (single payer, costs
    advantage, spending DA, states CP), and the school view is Quillmere's two rows and Brindle
    Valley's two."""
    result = landscape(world, "--caselist", CASELIST, "--snapshot", "2026-09-08")

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert data["trends"] == {
        "rows_by_label": {"NEW": 4, "RISING": 0, "FALLING": 0, "STEADY": 0},
        "held_back_by_team_floor": 0,
    }
    assert data["school_view"] == {"schools": 2, "team_codes": 2, "rows": 4}


def test_report_tells_a_person_which_files_name_schools_and_counts_trends_and_schools(
    world: SyntheticRun,
) -> None:
    result = landscape(world, "--caselist", CASELIST, json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    directory = world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15"
    lines = result.stdout.splitlines()
    assert "Trends: NEW 0, RISING 0, FALLING 0, STEADY 4; 1 held back by the team floor." in lines
    assert "School view: 3 school(s), 3 team code(s), 7 row(s)." in lines
    wrote = lines.index(f"Wrote 7 files to {directory}:")
    assert lines[wrote + 1 : wrote + 3] == [
        "  circuit-wide: positions.csv, top_cards.csv, impact_cards.csv, trends.csv, report.md",
        "  school view, naming schools and team codes: schools.csv, schools.md",
    ]
    for identity in ("Quillmere", "Brindle", "Harrowgate"):
        assert identity not in result.stdout, identity


def test_a_dry_run_tells_a_person_the_seven_files_it_would_write(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--dry-run", json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    directory = world.data_dir / "reports" / "landscape" / CASELIST / "2026-09-15"
    lines = result.stdout.splitlines()
    would = lines.index(f"Dry run: nothing written; the bundle's 7 files would go to {directory}:")
    assert lines[would + 1 : would + 3] == [
        "  circuit-wide: positions.csv, top_cards.csv, impact_cards.csv, trends.csv, report.md",
        "  school view, naming schools and team codes: schools.csv, schools.md",
    ]
    assert not (world.data_dir / "reports").exists()


def test_help_names_the_seven_files_and_which_name_schools() -> None:
    result = runner.invoke(create_app(), ["landscape", "report", "--help"])

    assert result.exit_code == ExitCode.OK, result.output
    shown = _flat(result.stdout)
    assert (
        "Circuit-wide: report.md, positions.csv, top_cards.csv, impact_cards.csv, trends.csv. "
        "School view, naming schools and team codes: schools.csv, schools.md."
    ) in shown


def test_the_module_docstring_names_the_seven_files() -> None:
    documented = _flat(landscape_module.__doc__ or "")

    assert "seven files" in documented
    for name in BUNDLE_FILES:
        assert f"`{name}`" in documented, name
    assert "`report.md`, `positions.csv`, `top_cards.csv` and `impact_cards.csv`, under" not in documented


# ------------------------------------------------------------------------------------------------
# v1-e32-t12 ac3 (the PM's amendment from v1-e34-t32's ruling 4): a failed latest run
#
# Synthetic run logs in the installation's data directory, as `caselist pull` writes them. Each
# record's reason or message names the fixture's fictional school and a disclosure path, which must
# not reach the output; the hook's sentence, which the command prints as it is, holds neither.
# ------------------------------------------------------------------------------------------------

FAILED_RUN_ID = "20260916T060000Z"
LEAKY = "HTTP 403 for Harrowgate Prep/PX/Harrowgate Prep-PX-Neg-Thistle Open-Round 2.docx"


def _logged(world: SyntheticRun, record: SyncRunRecord) -> None:
    SyncRunLog(world.data_dir / SYNC_RUN_LOG_FILENAME).append(record)


def _failed_run(**fields: Any) -> SyncRunRecord:
    started = datetime(2026, 9, 16, 6, tzinfo=UTC)
    return SyncRunRecord(
        run_id=FAILED_RUN_ID,
        environment="dev",
        mode="run",
        started_at=started,
        finished_at=started,
        outcome=SyncRunOutcome.FAILED,
        caselists=(CASELIST,),
        **fields,
    )


def test_a_run_that_failed_at_a_stage_prints_the_hooks_sentence_on_the_status_line(
    world: SyntheticRun,
) -> None:
    _logged(
        world,
        _failed_run(
            deferred_by_caselist={CASELIST: 0},
            stages=(
                StageEntry(stage="download", outcome="failed", reason=LEAKY),
                StageEntry(stage="import", outcome="skipped"),
            ),
        ),
    )

    shown = landscape(world, "--caselist", CASELIST, json_output=False)
    machine = landscape(world, "--caselist", CASELIST)

    assert shown.exit_code == ExitCode.OK, shown.output
    assert (
        "STALE: newest snapshot 2026-09-15, 2 day(s) old, 0 archive(s) awaiting download. "
        "The latest sync run of this caselist, 20260916T060000Z, failed at its download stage."
    ) in shown.stdout.splitlines()
    assert machine.exit_code == ExitCode.OK, machine.output
    staleness = _data(machine)["staleness"]
    assert staleness["stale"] is True
    assert staleness["failed_run"] == {
        "run_id": FAILED_RUN_ID,
        "stages": ["download"],
        "stopped_before_stages": False,
        "error_class": None,
    }
    for result in (shown, machine):
        for part in ("Harrowgate", ".docx", "HTTP 403"):
            assert part not in result.stdout, part


def test_a_run_that_stopped_before_its_stages_names_its_error_class_and_never_its_message(
    world: SyntheticRun,
) -> None:
    _logged(world, _failed_run(error_class="CaselistAuthExpired", error_message=LEAKY))

    shown = landscape(world, "--caselist", CASELIST, json_output=False)
    machine = landscape(world, "--caselist", CASELIST)

    assert shown.exit_code == ExitCode.OK, shown.output
    assert (
        "STALE: newest snapshot 2026-09-15, 2 day(s) old, 0 archive(s) awaiting download. "
        "The latest sync run of this caselist, 20260916T060000Z, stopped before its stages "
        "(CaselistAuthExpired)."
    ) in shown.stdout.splitlines()
    assert machine.exit_code == ExitCode.OK, machine.output
    assert _data(machine)["staleness"]["failed_run"] == {
        "run_id": FAILED_RUN_ID,
        "stages": [],
        "stopped_before_stages": True,
        "error_class": "CaselistAuthExpired",
    }
    for result in (shown, machine):
        for part in ("Harrowgate", ".docx", "HTTP 403"):
            assert part not in result.stdout, part


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


def test_publish_with_a_planted_tournament_is_refused_printing_the_hit_and_its_digest(
    planted_world: SyntheticRun, buckets: S3Client
) -> None:
    result = landscape(planted_world, "--caselist", CASELIST, "--publish", json_output=False)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert "Scan: 1 hit(s), 1 not yet accepted (digest " in result.stdout
    assert "top_cards.csv:" in result.stdout and "tournament 'Thistle Open'" in result.stdout
    assert "At Thistle Open" in result.stdout
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


# ------------------------------------------------------------------------------------------------
# v1-e40-t04: in bucket mode `--publish` holds the bucket's run lock (the PM's ruling 2, 2026-10-24)
# ------------------------------------------------------------------------------------------------

RUN_LOCK = "reports/sync/run-lock.json"


def _place_the_lock(client: S3Client, *, held_until: datetime | None) -> None:
    """The seeded lock object: free, or held by another runner until `held_until`."""
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    holder = {"kind": "cloud", "run_id": "20260917T110005Z", "task": None, "command": "caselist pull"}
    body = {
        "format_version": 1,
        "home_environment": "dev",
        "state": "held" if held_until is not None else "free",
        "holder": holder if held_until is not None else None,
        "acquired_at": None,
        "renewed_at": None,
        "lease_expires_at": held_until.strftime(stamp) if held_until is not None else None,
        "took_over_from": None,
    }
    client.put_bucket_versioning(Bucket=DEV_BUCKET, VersioningConfiguration={"Status": "Enabled"})
    client.put_object(Bucket=DEV_BUCKET, Key=RUN_LOCK, Body=json.dumps(body).encode())


def _lock_commands(client: S3Client) -> list[str]:
    commands: list[str] = []
    for version in client.list_object_versions(Bucket=DEV_BUCKET, Prefix=RUN_LOCK).get("Versions", []):
        body = json.loads(
            client.get_object(Bucket=DEV_BUCKET, Key=RUN_LOCK, VersionId=version["VersionId"])["Body"].read()  # pyright: ignore[reportTypedDictNotRequiredAccess]
        )
        if body.get("holder"):
            commands.append(body["holder"]["command"])
    return commands


def test_publish_in_bucket_mode_takes_the_run_lock_and_releases_it(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", "bucket")
    _place_the_lock(buckets, held_until=None)
    copy = _restored_copy(tmp_path / "copy-root")

    result = landscape(world, "--caselist", CASELIST, "--publish", "--restored-copy", str(copy))

    assert result.exit_code == ExitCode.OK, result.stdout
    assert set(KEYS) <= set(_keys(buckets, DEV_BUCKET))
    assert "landscape report --publish" in _lock_commands(buckets)
    assert json.loads(buckets.get_object(Bucket=DEV_BUCKET, Key=RUN_LOCK)["Body"].read())["state"] == "free"


def test_publish_in_bucket_mode_is_refused_while_another_runner_holds_the_lock(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", "bucket")
    today = SYNTHETIC_RUN_TODAY
    _place_the_lock(buckets, held_until=datetime(today.year, today.month, today.day, 9, 20, tzinfo=UTC))
    copy = _restored_copy(tmp_path / "copy-root")

    result = landscape(world, "--caselist", CASELIST, "--publish", "--restored-copy", str(copy))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    assert _error(result)["code"] == "RUN_LOCK_HELD"
    assert _keys(buckets, DEV_BUCKET) == [RUN_LOCK], "nothing published"


# ------------------------------------------------------------------------------------------------
# v1-e40-t17: a report over a copy restored from the bucket (the PM's ruling of 2026-10-30)
#
# The data directory is `synthetic26` as the Mac's last pull left it: through 2026-09-08 only, and its
# raw sources gone, since the PM ruled the bytes are read from the copy alone. The copy is the whole
# caselist through 2026-09-15, its parsed directory this build's, as `caselist restore-run-state
# --with-sources` and then `caselist parse` into it leave one. So, by hand from the fixture table: a
# report over the copy counts 2026-09-15, four sources and nine cards, seven placed by an alias, and
# identifies `aff-two` by its plan text, whose bytes only the copy holds. Every piece of the
# landscape's own state is written in the data directory, and none in the copy.
# ------------------------------------------------------------------------------------------------

THIS_BUILD = DebateDocxParser().parser_version
LANDSCAPE_STATE = (
    Path("landscape") / "classifications" / f"{CASELIST}.jsonl",
    Path("landscape") / "review" / CASELIST / f"{SYNTHETIC_RUN_TOPIC}-review-queue.csv",
    Path("landscape") / "plan_texts" / f"{CASELIST}.jsonl",
    Path("landscape") / "analytic_texts" / f"{CASELIST}.jsonl",
    Path("reports") / "landscape" / CASELIST / "2026-09-15" / "report.md",
)
RUNBOOK = "docs/runbooks/landscape-report-from-the-cloud-run.md"


def _restored_copy(root: Path, *, planted_tags: dict[tuple[str, int], str] | None = None) -> Path:
    """`synthetic26` through 2026-09-15 under `root/data`, parsed by this build: a copy to report from."""
    copy = plant_synthetic_run(root, planted_tags=planted_tags).data_dir
    parsed = copy / "parsed" / CASELIST
    (parsed / PARSER_VERSION).rename(parsed / THIS_BUILD)
    return copy.resolve()


@pytest.fixture
def stale_world(world: SyntheticRun) -> SyntheticRun:
    """The data directory through 2026-09-08 only, with no raw source: the Mac's, after the cutover."""
    (world.data_dir / "objects" / "manifests" / CASELIST / "2026-09-15.jsonl").unlink()
    shutil.rmtree(world.data_dir / "blobs")
    return world


def _nothing_written(data_dir: Path) -> bool:
    return not (data_dir / "landscape").exists() and not (data_dir / "reports").exists()


def test_a_report_over_a_restored_copy_counts_its_newest_snapshot_and_keeps_the_state_here(
    stale_world: SyntheticRun, tmp_path: Path
) -> None:
    alone = landscape(stale_world, "--caselist", CASELIST, "--dry-run")
    assert alone.exit_code == ExitCode.OK, alone.output
    assert _data(alone)["snapshot"] == "2026-09-08"
    copy = _restored_copy(tmp_path / "copy-root")

    result = landscape(stale_world, "--caselist", CASELIST, "--no-publish", "--restored-copy", str(copy))

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert (data["snapshot"], data["parsed_version"], data["restored_copy"]) == (
        "2026-09-15",
        THIS_BUILD,
        str(copy),
    )
    assert data["classification"]["cards_by_method"] == {"ALIAS": 7, "UNPLACED": 2}
    assert (data["counts"]["sources"], data["counts"]["cards"]) == (4, 9)
    assert data["aff_identification"] == {"PLACED_CARD": 1, "PLAN_TEXT": 1}
    assert [str(path) for path in LANDSCAPE_STATE if not (stale_world.data_dir / path).is_file()] == []
    assert not (copy / "landscape").exists()
    assert not (copy / "reports").exists()


def test_a_report_from_the_data_directory_says_it_read_no_copy(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--dry-run")

    assert result.exit_code == ExitCode.OK, result.output
    assert _data(result)["restored_copy"] is None


def test_a_second_report_over_a_fresh_copy_classifies_nothing_already_classified(
    stale_world: SyntheticRun, tmp_path: Path, model_router: _PlacesEverything
) -> None:
    first_copy = _restored_copy(tmp_path / "first-copy")
    first = landscape(
        stale_world, "--caselist", CASELIST, "--no-publish", "--model-mode", "replay",
        "--restored-copy", str(first_copy),
    )  # fmt: skip
    assert first.exit_code == ExitCode.OK, first.output
    asked = _data(first)["classification"]["model"]
    assert (asked["asked"], asked["calls"]) == (2, 1)
    shutil.rmtree(first_copy.parent)

    second_copy = _restored_copy(tmp_path / "second-copy")
    second = landscape(
        stale_world, "--caselist", CASELIST, "--no-publish", "--model-mode", "replay",
        "--restored-copy", str(second_copy),
    )  # fmt: skip

    assert second.exit_code == ExitCode.OK, second.output
    data = _data(second)
    model = data["classification"]["model"]
    assert (model["asked"], model["cached"], model["calls"]) == (0, 2, 0)
    cache = data["classification"]["cache"]
    assert (cache["misses"], cache["hits"] == cache["lookups"] > 0) == (0, True)
    assert data["classification"]["cards_by_method"] == {"ALIAS": 7, "MODEL": 2}
    assert len(model_router.calls) == 1
    assert model_router.parsed_dirs == [first_copy, second_copy]


def test_the_container_reads_the_model_stages_card_texts_from_the_directory_it_is_given(
    world: SyntheticRun, tmp_path: Path
) -> None:
    copy = _restored_copy(tmp_path / "copy-root")
    source = next((copy / "parsed" / CASELIST / THIS_BUILD).glob("sha256/*/*/*.jsonl"))
    lines = source.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["document"]["cards"][0]["evidence_text"] = "An invented card body, only in the copy."
    source.write_text("\n".join([lines[0], json.dumps(record)]) + "\n", encoding="utf-8")
    sha = record["source_sha256"]
    container = container_module.ServiceContainer(settings_loader=lambda: load_settings(environment="test"))

    built = container.landscape_model_stage(ModelMode.REPLAY, 7, parsed_dir=copy)
    texts = asyncio.run(built._texts.evidence_texts(CASELIST, THIS_BUILD, {sha: {0}}))  # pyright: ignore[reportPrivateUsage]

    assert texts == {(sha, 0): "An invented card body, only in the copy."}


def test_every_dry_run_says_how_many_cards_it_would_ask_the_model_about(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--dry-run")
    shown = landscape(world, "--caselist", CASELIST, "--dry-run", json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    assert _data(result)["classification"]["model"]["would_ask"] == 0
    assert "Dry run: would ask the model about 0 card(s); --model-mode none asks it nothing." in _flat(
        shown.stdout
    )


def test_a_replay_dry_run_says_what_it_would_ask_and_hold_back_and_asks_nothing(
    world: SyntheticRun, model_router: _PlacesEverything
) -> None:
    arguments = ("--caselist", CASELIST, "--dry-run", "--model-mode", "replay", "--max-model-items", "1")
    result = landscape(world, *arguments)
    shown = landscape(world, *arguments, json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    model = _data(result)["classification"]["model"]
    assert (model["would_ask"], model["held_back"], model["calls"]) == (1, 1, 0)
    assert "Dry run: would ask the model about 1 card(s), and hold 1 more back for a later run." in _flat(
        shown.stdout
    )
    assert model_router.calls == []


def test_a_run_that_writes_has_no_would_ask_count(world: SyntheticRun) -> None:
    result = landscape(world, "--caselist", CASELIST, "--no-publish")
    shown = landscape(world, "--caselist", CASELIST, "--no-publish", json_output=False)

    assert result.exit_code == ExitCode.OK, result.output
    assert _data(result)["classification"]["model"]["would_ask"] is None
    assert "would ask the model" not in _flat(shown.stdout)


def _not_a_copy(where: str, data_dir: Path, tmp_path: Path) -> Path:
    """A directory `--restored-copy` must refuse, by what it is."""
    if where == "the data directory":
        return data_dir
    if where == "inside it":
        (data_dir / "copy").mkdir()
        return data_dir / "copy"
    if where == "holding it":
        return data_dir.parent
    if where == "inside a checkout":
        checkout = tmp_path / "checkout"
        (checkout / "config" / "profiles").mkdir(parents=True)
        (checkout / "copy").mkdir()
        return checkout / "copy"
    return tmp_path / "never-restored"


@pytest.mark.parametrize(
    "where", ["the data directory", "inside it", "holding it", "inside a checkout", "no directory at all"]
)
def test_a_copy_that_is_not_one_is_refused_with_exit_2_and_nothing_is_written(
    stale_world: SyntheticRun, tmp_path: Path, where: str
) -> None:
    copy = _not_a_copy(where, stale_world.data_dir, tmp_path)

    result = landscape(stale_world, "--caselist", CASELIST, "--restored-copy", str(copy))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert _error(result)["code"] == "RESTORED_COPY_REFUSED"
    assert _nothing_written(stale_world.data_dir)


def test_a_copy_without_the_caselist_is_refused_with_exit_2(
    stale_world: SyntheticRun, tmp_path: Path
) -> None:
    empty = tmp_path / "empty-copy"
    empty.mkdir()

    result = landscape(stale_world, "--caselist", CASELIST, "--restored-copy", str(empty))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert _error(result)["code"] == "UNKNOWN_CASELIST"
    assert _nothing_written(stale_world.data_dir)


def test_a_copy_no_build_of_this_version_parsed_is_refused_naming_caselist_parse(
    stale_world: SyntheticRun, tmp_path: Path
) -> None:
    copy = plant_synthetic_run(tmp_path / "copy-root").data_dir

    result = landscape(stale_world, "--caselist", CASELIST, "--restored-copy", str(copy))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    error = _error(result)
    assert (error["code"], error["details"]["known"]) == ("PARSED_VERSION_NOT_IN_STORE", [PARSER_VERSION])
    assert THIS_BUILD in error["message"]
    assert "caselist parse" in error["message"]
    assert _nothing_written(stale_world.data_dir)


def test_a_publish_in_bucket_mode_without_a_copy_is_refused_naming_the_runbook(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", "bucket")
    _place_the_lock(buckets, held_until=None)

    result = landscape(world, "--caselist", CASELIST, "--publish")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = _error(result)
    assert error["code"] == "PUBLISH_NEEDS_A_RESTORED_COPY"
    assert RUNBOOK in error["hint"]
    assert _keys(buckets, DEV_BUCKET) == [RUN_LOCK], "nothing published"
    assert _lock_commands(buckets) == [], "the lock was never taken"
    assert _nothing_written(world.data_dir)


@pytest.mark.parametrize(
    "arguments",
    [pytest.param(("--publish", "--dry-run"), id="a publish's dry run"), pytest.param((), id="no publish")],
)
def test_in_bucket_mode_a_dry_run_or_a_report_kept_here_needs_no_copy(
    world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch, arguments: tuple[str, ...]
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", "bucket")
    _place_the_lock(buckets, held_until=None)

    result = landscape(world, "--caselist", CASELIST, *arguments)

    assert result.exit_code == ExitCode.OK, result.output
    assert _keys(buckets, DEV_BUCKET) == [RUN_LOCK]


def test_scan_acceptances_from_a_copys_publish_are_kept_in_the_data_directory(
    stale_world: SyntheticRun, buckets: S3Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__RUN_STATE", "bucket")
    _place_the_lock(buckets, held_until=None)
    copy = _restored_copy(tmp_path / "copy-root", planted_tags=PLANTED_TOURNAMENT)
    publish = ("--caselist", CASELIST, "--publish", "--restored-copy", str(copy))

    refused = landscape(stale_world, *publish)
    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    digest = _data_of_failure(refused)["scan"]["digest"]
    accepted = landscape(stale_world, *publish, "--accept-scan-hits", digest)

    assert accepted.exit_code == ExitCode.OK, accepted.output
    log = Path(_data(accepted)["scan"]["acceptance_log"])
    assert log.is_relative_to(stale_world.data_dir / "landscape" / "scan-acceptances")
    assert log.is_file()
    assert not (copy / "landscape").exists()
    assert set(KEYS) <= set(_keys(buckets, DEV_BUCKET))


def _data_of_failure(result: Result) -> dict[str, Any]:
    return _error(result)["details"]


# ------------------------------------------------------------------------------------------------
# v1-e32-t07: `landscape evaluate` (ac4), over a stub evaluation: the service is tested in
# debate_core's test_landscape_model_stage.py; this is the handler's gate, exit codes and JSON.
# ------------------------------------------------------------------------------------------------


def _evaluated(**changes: Any) -> FormatEvaluation:
    base = FormatEvaluation(
        caselist=CASELIST,
        event="POLICY",
        topic_id=SYNTHETIC_RUN_TOPIC,
        taxonomy_version="1.0.0",
        prompt_version="1.0.0",
        snapshot=None,
        labelled=30,
        found=30,
        asked=30,
        calls=2,
        counted=20,
        correct=18,
        placed_below_threshold=6,
        placed_labelled_none=1,
        sent=NameScan(texts=2),
        cassettes=NameScan(texts=2),
    )
    return dataclasses.replace(base, **changes)


@pytest.fixture
def sample_files(tmp_path: Path) -> tuple[Path, Path]:
    sample = tmp_path / "coach-sample.csv"
    sample.write_text("sample_row,position\n1,spending-da\n", encoding="utf-8")
    rows = tmp_path / "coach-sample.jsonl"
    rows.write_text('{"schema": "local-classifier-sample-1"}\n', encoding="utf-8")
    return sample, rows


def _stub_evaluation(monkeypatch: pytest.MonkeyPatch, result: FormatEvaluation) -> list[bool]:
    asked: list[bool] = []

    class Stub:
        async def evaluate(
            self, caselist: str, sample: Any, rows: Any, *, snapshot: Any = None
        ) -> FormatEvaluation:
            return result

    def build(self: container_module.ServiceContainer, *, config_dir: Path, record: bool) -> Stub:
        asked.append(record)
        return Stub()

    monkeypatch.setattr(container_module.ServiceContainer, "landscape_evaluation", build)
    return asked


def evaluate(world: SyntheticRun, sample_files: tuple[Path, Path], *arguments: str) -> Result:
    sample, rows = sample_files
    command = [
        "--json",
        "landscape",
        "evaluate",
        "--config-dir",
        str(world.config_dir),
        "--caselist",
        CASELIST,
    ]
    return runner.invoke(
        create_app(), [*command, "--sample", str(sample), "--sample-rows", str(rows), *arguments]
    )


def test_evaluate_meeting_the_bar_with_clean_scans_exits_0_and_counts_it(
    world: SyntheticRun, sample_files: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _stub_evaluation(monkeypatch, _evaluated())

    result = evaluate(world, sample_files)

    assert result.exit_code == ExitCode.OK, result.output
    data = _data(result)
    assert (data["counted"], data["correct"], data["accuracy"], data["meets_target"]) == (20, 18, 0.9, True)
    assert data["scan"]["cassettes"] == {
        "texts": 2,
        "schools": 0,
        "team_codes": 0,
        "other_names": 0,
        "clean": True,
    }
    assert asked == [False]


@pytest.mark.parametrize(
    "changes", [{"correct": 16}, {"counted": 0, "correct": 0}, {"cassettes": NameScan(texts=2, team_codes=1)}]
)
def test_evaluate_under_the_bar_or_with_a_name_in_a_cassette_exits_1(
    world: SyntheticRun,
    sample_files: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, Any],
) -> None:
    _stub_evaluation(monkeypatch, _evaluated(**changes))

    result = evaluate(world, sample_files)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert _error(result)["code"] == "EVALUATION_BELOW_BAR"


def test_evaluate_record_is_refused_while_the_policy_leaves_question_four_open(
    world: SyntheticRun, sample_files: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked = _stub_evaluation(monkeypatch, _evaluated())
    checkout = tmp_path / "checkout"
    (checkout / "docs" / "policies").mkdir(parents=True)
    (checkout / "docs" / "policies" / "caselist-data-use.md").write_text(
        "| 4 | The provider's no-retention terms | **Open** | Operator | E32 gate |\n", encoding="utf-8"
    )
    monkeypatch.setattr(landscape_module, "find_repository_root", lambda *_: checkout)

    result = evaluate(world, sample_files, "--model-mode", "record")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert _error(result)["code"] == "MODEL_USE_NOT_YET_ALLOWED"
    assert asked == []

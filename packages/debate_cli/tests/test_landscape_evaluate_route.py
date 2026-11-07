"""`landscape evaluate --route` and `landscape cassettes --route`, through the container (`v1-e32-t43`).

An evaluation on another route of the routing file records to `<data dir>/landscape/model-cassettes-<route>/`,
never to the default directory, so it cannot replace the default route's cassettes or be served as theirs.
`synthetic26` (:mod:`debate_core.testing.landscape_run`) is planted with two cards labelled by hand: its
`Costs Advantage` card costs-advantage, which its alias heading places, and its `Framing` card spending-da,
which the model is asked about. The Bedrock router is replaced by a scripted one that answers both rightly and
keeps the routing policy it was built with; nothing reaches AWS. The example routing file routes high_volume
to Claude Haiku 5.5 and deep_audit to Claude Opus 5.5.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import BaseModel
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.coach_sample_labels_file import digest_line, digest_path, labels_digest
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX
from debate_core.domain.landscape_classification import ModelStancedPositionAnswers, card_item_id
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations import bedrock
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.routing_policy import RoutingPolicy
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.landscape_run import SYNTHETIC_RUN_CASELIST, SyntheticRun, plant_synthetic_run
from debate_core.testing.landscape_store import PARSER_VERSION

runner = CliRunner()

SNAPSHOT: Final = "2026-09-15"
CLASSIFY: Final = "landscape.classify_position"
# (tag, short cite, the coach's label)
LABELLED: Final = (
    ("Premiums are rising fast", "Delacroix 25", "costs-advantage"),
    ("Probability first", "Szabo 24", "spending-da"),
)
ANSWERS: Final = {"premiums are rising fast": "costs-advantage", "probability first": "spending-da"}


class AnswersByTag(ScriptedModelRouter):
    def __init__(self) -> None:
        super().__init__(model_id="anthropic.claude-opus-5-5")

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        items: list[dict[str, Any]] = json.loads(str(prompt.variables["items"]))
        answers = [
            {
                "item": item["item"],
                "position_id": ANSWERS[item["tag"]],
                "confidence": 0.9,
                "rationale": "the tag states the argument",
                **({"stance": "reads"} if issubclass(schema, ModelStancedPositionAnswers) else {}),
            }
            for item in items
        ]
        self.enqueue({"answers": answers})
        return await super().generate_structured(task_class, prompt, schema, params)


class BedrockStandIn:
    """`bedrock_router_factory`'s stand-in: keeps each policy it is given, and answers by tag."""

    def __init__(self) -> None:
        self.policies: list[RoutingPolicy] = []

    def __call__(self, registry: PromptRegistry) -> Any:
        def factory(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
            self.policies.append(policy)
            return AnswersByTag()

        return factory


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SyntheticRun]:
    """`synthetic26` under a dev profile of its own, with no CI flag to refuse a recording."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CI", raising=False)
    planted = plant_synthetic_run(tmp_path / "world")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{planted.data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 5.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield planted


@pytest.fixture
def bedrock_stand_in(monkeypatch: pytest.MonkeyPatch) -> BedrockStandIn:
    stand_in = BedrockStandIn()
    monkeypatch.setattr(bedrock, "bedrock_router_factory", stand_in)
    return stand_in


@pytest.fixture
def sample(world: SyntheticRun, tmp_path: Path) -> tuple[Path, Path]:
    """The coach's CSV and the rows file beside it, each card found by its tag and cite."""
    table = world.data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    item_ids: dict[str, str] = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        item_ids[record["exact_fingerprint"]] = card_item_id(
            record["source_sha256"], record["first_element_index"]
        )
    labels = ["sample_row,position"]
    rows = [json.dumps({"schema": "local-classifier-sample-1"})]
    for row, (tag, cite, label) in enumerate(LABELLED, start=1):
        labels.append(f"{row},{label}")
        fingerprint = hashlib.sha256(f"{tag}|{cite}".encode()).hexdigest()
        rows.append(json.dumps({"sample_row": row, "item_id": item_ids[fingerprint]}))
    csv_file, rows_file = tmp_path / "coach-sample.csv", tmp_path / "coach-sample.jsonl"
    csv_file.write_text("\n".join(labels) + "\n", encoding="utf-8")
    digest_path(csv_file).write_text(
        digest_line(labels_digest(csv_file.read_bytes()), csv_file), encoding="ascii"
    )
    rows_file.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return csv_file, rows_file


def evaluate(world: SyntheticRun, sample: tuple[Path, Path], *arguments: str) -> Result:
    labels, rows = sample
    command = ["--json", "landscape", "evaluate", "--config-dir", str(world.config_dir)]
    command += ["--caselist", SYNTHETIC_RUN_CASELIST, "--snapshot", SNAPSHOT]
    return runner.invoke(
        create_app(), [*command, "--sample", str(labels), "--sample-rows", str(rows), *arguments]
    )


def payload(result: Result) -> dict[str, Any]:
    document = json.loads(result.stdout)
    return document["data"] if document["status"] == "ok" else document["error"]["details"]


def files_under(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*.json"))


def test_evaluate_record_on_a_route_writes_only_that_routes_directory(
    world: SyntheticRun, sample: tuple[Path, Path], bedrock_stand_in: BedrockStandIn
) -> None:
    landscape = world.data_dir / "landscape"

    result = evaluate(world, sample, "--model-mode", "record", "--route", "deep_audit")

    assert result.exit_code == ExitCode.OK, result.output
    data = payload(result)
    assert (data["route"], data["asked"], data["calls"]) == ("deep_audit", 2, 1)
    assert (data["pipeline"]["counted"], data["pipeline"]["correct"]) == (2, 2)
    assert (data["scan"]["cassettes"]["texts"], data["scan"]["cassettes"]["clean"]) == (1, True)
    assert not (landscape / "model-cassettes").exists()
    recorded = files_under(landscape / "model-cassettes-deep_audit")
    assert len(recorded) == 1 and recorded[0].startswith(f"{CLASSIFY}/")
    (policy,) = bedrock_stand_in.policies
    example = RoutingPolicy.load(EXAMPLE_ROUTING_FILE)
    assert policy.route_for(TaskClass.HIGH_VOLUME) == example.route_for(TaskClass.DEEP_AUDIT)


def test_evaluate_on_a_route_replays_its_own_cassettes_and_the_default_route_finds_none(
    world: SyntheticRun, sample: tuple[Path, Path], bedrock_stand_in: BedrockStandIn
) -> None:
    recorded = evaluate(world, sample, "--model-mode", "record", "--route", "deep_audit")
    replayed = evaluate(world, sample, "--route", "deep_audit")
    default = evaluate(world, sample)

    assert (recorded.exit_code, replayed.exit_code) == (ExitCode.OK, ExitCode.OK), replayed.output
    counts = ("counted", "correct", "input_tokens", "output_tokens")
    assert [payload(replayed)[key] for key in counts] == [payload(recorded)[key] for key in counts]
    assert len(bedrock_stand_in.policies) == 1, "replay builds no real router"
    assert default.exit_code != ExitCode.OK
    assert json.loads(default.stdout)["error"]["code"] == "MISSING_FIXTURE_ERROR"


def test_landscape_cassettes_on_a_route_counts_that_directorys_cassettes(
    world: SyntheticRun, sample: tuple[Path, Path], bedrock_stand_in: BedrockStandIn
) -> None:
    evaluate(world, sample, "--model-mode", "record", "--route", "deep_audit")
    command = ["--json", "landscape", "cassettes", "--caselist", SYNTHETIC_RUN_CASELIST]

    on_route = json.loads(runner.invoke(create_app(), [*command, "--route", "deep_audit"]).stdout)["data"]
    default = json.loads(runner.invoke(create_app(), command).stdout)["data"]

    assert (on_route["directory"], on_route["directory_found"]) == (
        "<data dir>/landscape/model-cassettes-deep_audit/",
        True,
    )
    assert on_route["cassettes"]["sole"] == 1
    assert (default["directory"], default["directory_found"]) == (
        "<data dir>/landscape/model-cassettes/",
        False,
    )


@pytest.mark.parametrize("route", ["embeddings", "rerank"])
def test_evaluate_refuses_a_route_that_answers_no_prompt(
    world: SyntheticRun, sample: tuple[Path, Path], bedrock_stand_in: BedrockStandIn, route: str
) -> None:
    result = evaluate(world, sample, "--model-mode", "record", "--route", route)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert json.loads(result.stdout)["error"]["code"] == "ROUTE_NOT_GENERATIVE"
    assert bedrock_stand_in.policies == []
    assert not (world.data_dir / "landscape" / f"model-cassettes-{route}").exists()


def test_evaluate_check_sample_takes_no_route(world: SyntheticRun, sample: tuple[Path, Path]) -> None:
    result = evaluate(world, sample, "--check-sample", "--route", "deep_audit")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert json.loads(result.stdout)["error"]["code"] == "CHECK_SAMPLE_ASKS_NO_MODEL"

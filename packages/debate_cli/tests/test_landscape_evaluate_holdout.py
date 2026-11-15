"""`landscape evaluate` with the held-out sample (`v1-e32-t50`), through the container.

`synthetic26` (:mod:`debate_core.testing.landscape_run`) is planted; the first sample is `aff-one`'s costs
card, labelled costs-advantage, and the holdout `neg-two`'s framing card, labelled spending-da, its rows file
marked a holdout. The Bedrock router is replaced by a scripted one that answers both rightly; nothing
reaches AWS. Each sample is recorded alone, then the two are replayed side by side. The holdout is reported as
counts and scores only: `--breakdown` refuses it, given either way. Its own scan hits are listed, for a
terminal only, by `--holdout-scan-hits` (the PM's ruling of 2026-11-14). Every school, tag and cite here is
invented.
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
from debate_cli.commands import landscape as landscape_module
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
FIRST: Final = (("Premiums are rising fast", "Delacroix 25", "costs-advantage"),)
HOLDOUT: Final = (("Probability first", "Szabo 24", "spending-da"),)
ANSWERS: Final = {"premiums are rising fast": "costs-advantage", "probability first": "spending-da"}
DRAWN_FROM: Final = {
    "snapshot": SNAPSHOT,
    "version": "2026.09.01-docx-1",
    "parser_version": "2026.09.01-docx",
}


class AnswersByTag(ScriptedModelRouter):
    rationales: dict[str, str] = {}
    """A rationale by tag, in place of the plain one: how a test plants a school in one sample's cassette."""

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
                "rationale": self.rationales.get(item["tag"], "the tag states the argument"),
                **({"stance": "reads"} if issubclass(schema, ModelStancedPositionAnswers) else {}),
            }
            for item in items
        ]
        self.enqueue({"answers": answers})
        return await super().generate_structured(task_class, prompt, schema, params)


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

    def factory(registry: PromptRegistry) -> Any:
        def build(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
            return AnswersByTag()

        return build

    monkeypatch.setattr(bedrock, "bedrock_router_factory", factory)
    yield planted


def _write(
    world: SyntheticRun, directory: Path, labelled: tuple[tuple[str, str, str], ...], *, holdout: bool
) -> tuple[Path, Path]:
    table = world.data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    item_ids: dict[str, str] = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        item_ids.setdefault(
            record["exact_fingerprint"], card_item_id(record["source_sha256"], record["first_element_index"])
        )
    labels = ["sample_row,position"]
    header: dict[str, Any] = {"schema": "local-classifier-sample-1"}
    if holdout:
        header |= {"holdout": True, "seed": 20261114, "drawn_from": DRAWN_FROM}
    rows = [json.dumps(header)]
    for row, (tag, cite, label) in enumerate(labelled, start=1):
        labels.append(f"{row},{label}")
        fingerprint = hashlib.sha256(f"{tag}|{cite}".encode()).hexdigest()
        rows.append(json.dumps({"sample_row": row, "item_id": item_ids[fingerprint]}))
    directory.mkdir()
    csv_file, rows_file = directory / "sample.csv", directory / "sample.jsonl"
    csv_file.write_text("\n".join(labels) + "\n", encoding="utf-8")
    digest_path(csv_file).write_text(
        digest_line(labels_digest(csv_file.read_bytes()), csv_file), encoding="ascii"
    )
    rows_file.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return csv_file, rows_file


@pytest.fixture
def samples(world: SyntheticRun, tmp_path: Path) -> tuple[tuple[Path, Path], tuple[Path, Path]]:
    return (
        _write(world, tmp_path / "first", FIRST, holdout=False),
        _write(world, tmp_path / "holdout", HOLDOUT, holdout=True),
    )


def evaluate(world: SyntheticRun, sample: tuple[Path, Path], *arguments: str) -> Result:
    labels, rows = sample
    command = ["--json", "landscape", "evaluate", "--config-dir", str(world.config_dir)]
    command += ["--caselist", SYNTHETIC_RUN_CASELIST, "--snapshot", SNAPSHOT]
    return runner.invoke(
        create_app(), [*command, "--sample", str(labels), "--sample-rows", str(rows), *arguments]
    )


def beside(holdout: tuple[Path, Path], *, snapshot: str | None = SNAPSHOT) -> list[str]:
    return [
        "--holdout-sample",
        str(holdout[0]),
        "--holdout-sample-rows",
        str(holdout[1]),
        *(("--holdout-snapshot", snapshot) if snapshot is not None else ()),
    ]


def error(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout)["error"]


def test_the_holdout_is_reported_beside_the_first_sample_and_the_bar_reads_the_holdout(
    world: SyntheticRun, samples: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    first, holdout = samples
    for one in (first, holdout):
        recorded = evaluate(world, one, "--model-mode", "record")
        assert recorded.exit_code == ExitCode.OK, recorded.output

    result = evaluate(world, first, *beside(holdout))

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert set(data) == {"bar_reads_sample", "first_sample", "holdout"}
    assert data["bar_reads_sample"] == "holdout"
    assert (data["first_sample"]["labelled"], data["holdout"]["labelled"]) == (1, 1)
    assert data["holdout"]["pipeline"]["counted"] == data["holdout"]["pipeline"]["correct"] == 1
    assert data["holdout"]["drawn_from"] == DRAWN_FROM
    assert set(data["holdout"]) - {"drawn_from"} == set(data["first_sample"])
    assert "Probability" not in result.stdout and "Premiums" not in result.stdout


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        (("--breakdown",), "HOLDOUT_COUNTS_ONLY"),
        (("--model-mode", "record"), "HOLDOUT_RECORDS_ALONE"),
        (("--route", "embeddings"), "ROUTE_NOT_GENERATIVE"),
    ],
)
def test_the_holdout_beside_the_first_takes_no_breakdown_and_no_recording(
    world: SyntheticRun,
    samples: tuple[tuple[Path, Path], tuple[Path, Path]],
    extra: tuple[str, ...],
    code: str,
) -> None:
    first, holdout = samples

    result = evaluate(world, first, *beside(holdout), *extra)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert error(result)["code"] == code


def test_the_holdout_needs_its_three_options_together(
    world: SyntheticRun, samples: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    first, holdout = samples

    result = evaluate(world, first, *beside(holdout, snapshot=None))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert error(result)["code"] == "HOLDOUT_NEEDS_ITS_FILES"


def test_a_holdout_given_as_the_sample_is_never_broken_down(
    world: SyntheticRun, samples: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    _, holdout = samples

    result = evaluate(world, holdout, "--breakdown")

    assert result.exit_code != ExitCode.OK
    assert error(result)["code"] == "EVALUATION_REFUSED"
    assert "never broken down card by card" in error(result)["message"]


def test_check_sample_reads_the_holdout_alone_and_says_so(
    world: SyntheticRun, samples: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    first, holdout = samples

    held_out = evaluate(world, holdout, "--check-sample")
    plain = evaluate(world, first, "--check-sample")
    both = evaluate(world, first, "--check-sample", *beside(holdout))

    assert held_out.exit_code == ExitCode.OK, held_out.output
    data = json.loads(held_out.stdout)["data"]
    assert (data.get("holdout"), data["labelled"], data["by_label_kind"]) == (True, 1, {"da": 1})
    assert "holdout" not in json.loads(plain.stdout)["data"]
    assert both.exit_code == ExitCode.USAGE_ERROR
    assert error(both)["code"] == "CHECK_SAMPLE_ASKS_NO_MODEL"


PLANTED: Final = {
    "probability first": "as Brindle Valley reads it",
    "premiums are rising fast": "as Quillmere Academy reads it",
}


@pytest.fixture
def recorded(
    world: SyntheticRun,
    samples: tuple[tuple[Path, Path], tuple[Path, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[tuple[Path, Path], tuple[Path, Path]]:
    """Both samples recorded alone, each card's rationale naming a school: the holdout's one, the first's
    another. The scan reads both samples' cassettes; the listing keeps the holdout's."""
    monkeypatch.setattr(AnswersByTag, "rationales", PLANTED)
    for one in samples:
        recorded = evaluate(world, one, "--model-mode", "record")
        assert recorded.exit_code != ExitCode.OK, recorded.output
        assert error(recorded)["details"]["scan"]["cassettes"]["clean"] is False
    return samples


def hits(world: SyntheticRun, sample: tuple[Path, Path], *arguments: str) -> Result:
    labels, rows = sample
    command = [
        "landscape",
        "evaluate",
        "--config-dir",
        str(world.config_dir),
        "--caselist",
        SYNTHETIC_RUN_CASELIST,
    ]
    command += ["--snapshot", SNAPSHOT, "--sample", str(labels), "--sample-rows", str(rows)]
    return runner.invoke(create_app(), [*arguments, *command, "--holdout-scan-hits"])


def _item_id_shas(rows: Path) -> list[str]:
    return [
        json.loads(line)["item_id"].split(":", 1)[0]
        for line in rows.read_text(encoding="utf-8").splitlines()[1:]
    ]


def test_the_holdouts_own_hits_are_listed_by_number_in_the_terminal_and_the_first_samples_are_not(
    world: SyntheticRun,
    recorded: tuple[tuple[Path, Path], tuple[Path, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, holdout = recorded
    monkeypatch.setattr(landscape_module, "_stdout_is_a_terminal", lambda: True)

    result = hits(world, holdout)

    assert result.exit_code == ExitCode.OK, result.output
    assert "1 input batch(es), 1 cassette(s), 0 repair cassette(s)" in result.output
    assert landscape_module.HITS_NOTICE in result.output
    listed = [line for line in result.output.splitlines() if line.startswith("  1. ")]
    assert listed == [
        "  1. cassette 1 | model rationale | school (no mark sets it aside) | "
        "... as [brindle valley] reads it ..."
    ]
    assert "  2. " not in result.output
    assert "1 scan hit(s), 1 with no mark that sets a hit aside" in result.output
    assert "quillmere" not in result.output.casefold()
    for absent in ("spending-da", "costs-advantage", "row ", "correct", *_item_id_shas(holdout[1])):
        assert absent not in result.output, absent


def test_the_holdouts_hits_are_withheld_when_stdout_is_not_a_terminal(
    world: SyntheticRun, recorded: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    _, holdout = recorded

    result = hits(world, holdout)

    assert result.exit_code == ExitCode.OK, result.output
    assert "1 scan hit(s) withheld: stdout is not a terminal" in result.output
    assert "brindle" not in result.output.casefold()


@pytest.mark.parametrize(
    "extra",
    [("--breakdown",), ("--check-sample",), ("--model-mode", "record"), ("--holdout-snapshot", SNAPSHOT)],
)
def test_the_holdouts_hits_take_no_other_mode(
    world: SyntheticRun,
    recorded: tuple[tuple[Path, Path], tuple[Path, Path]],
    monkeypatch: pytest.MonkeyPatch,
    extra: tuple[str, ...],
) -> None:
    _, holdout = recorded
    monkeypatch.setattr(landscape_module, "_stdout_is_a_terminal", lambda: True)
    labels, rows = holdout
    command = [
        "landscape",
        "evaluate",
        "--config-dir",
        str(world.config_dir),
        "--caselist",
        SYNTHETIC_RUN_CASELIST,
    ]
    command += ["--snapshot", SNAPSHOT, "--sample", str(labels), "--sample-rows", str(rows)]

    result = runner.invoke(create_app(), [*command, "--holdout-scan-hits", *extra])

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert "HOLDOUT_HITS_TERMINAL_ONLY" in result.output
    assert "brindle" not in result.output.casefold()


def test_the_holdouts_hits_are_never_written_as_json(
    world: SyntheticRun,
    recorded: tuple[tuple[Path, Path], tuple[Path, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, holdout = recorded
    monkeypatch.setattr(landscape_module, "_stdout_is_a_terminal", lambda: True)

    result = hits(world, holdout, "--json")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert error(result)["code"] == "HOLDOUT_HITS_TERMINAL_ONLY"
    assert "brindle" not in result.output.casefold()


def test_the_first_samples_rows_file_is_refused_its_hits_are_the_breakdowns(
    world: SyntheticRun, recorded: tuple[tuple[Path, Path], tuple[Path, Path]]
) -> None:
    first, _ = recorded

    result = hits(world, first)

    assert result.exit_code != ExitCode.OK
    assert "not marked a holdout" in result.output
    assert "quillmere" not in result.output.casefold()


def test_a_listing_that_finds_fewer_cassettes_than_batches_is_refused(
    world: SyntheticRun,
    recorded: tuple[tuple[Path, Path], tuple[Path, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, holdout = recorded
    monkeypatch.setattr(landscape_module, "_stdout_is_a_terminal", lambda: True)
    monkeypatch.setattr(
        "debate_core.arguments.landscape.holdout_scan.own_cassettes", lambda cassettes, sent: []
    )

    result = hits(world, holdout)

    assert result.exit_code != ExitCode.OK
    assert "0 of the held-out sample's 1 batch(es) have a cassette" in result.output
    assert "brindle" not in result.output.casefold()

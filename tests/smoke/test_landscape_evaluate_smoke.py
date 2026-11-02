"""`debate-research landscape evaluate` end to end, offline, replaying synthetic cassettes (`v1-e32-t40` ac4).

`synthetic26` (:mod:`debate_core.testing.landscape_run`) is planted with four of its cards labelled by
hand, one per position of its taxonomy. One of them, aff-one's `Solvency` card, has a tag naming another
team's tournament (Thistle Open, where Harrowgate Prep disclosed), which the scrub must take out of what
the model is sent: the scan's third list holds it, so a name left in fails the scan.

The cassettes are recorded in this process, by the checkout's evaluation over a scripted model that
answers every card rightly, after its first answer to the batch names an item the batch does not have,
so the structured-output guard repairs it once. The build under test then replays them with no model
behind it: a request it builds differently from the recording fails as `MISSING_FIXTURE`, and a name it
sends fails the scan. By hand: four labelled, four found, four asked in one batch and two calls, all four
counted and correct (100%, over the 85% bar), and one prompt input, one cassette and one repair cassette
scanned, each clean, so the command exits 0.

The model stage reads its prompt from a source checkout's `prompts/`, so the build runs in a scratch
directory holding a copy of this checkout's `prompts/` beside a `config/profiles/`, which is what marks
a checkout. Every school, team code, tournament, tag and answer is invented, and none may appear in what
the command prints.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import REPO_ROOT, InstalledCli

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_model_evaluation import LandscapeModelEvaluationService
from debate_core.application.landscape_model_stage import ModelClassificationStage, ParsedStoreCardTexts
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX
from debate_core.application.structured_output import REPAIR_PROMPT_ID, StructuredOutputGuard
from debate_core.domain.landscape_classification import card_item_id
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.landscape_run import SYNTHETIC_RUN_CASELIST, SyntheticRun, plant_synthetic_run
from debate_core.testing.landscape_store import PARSER_VERSION

SNAPSHOT = "2026-09-15"
PLANTED_TAG = "Thistle Open: public financing is cheaper"

# (the card's tag and short cite as planted, the coach's label, the tag as the model is sent it)
LABELLED: tuple[tuple[str, str, str, str], ...] = (
    (PLANTED_TAG, "Varga 26", "single-payer-aff", "public financing is cheaper"),
    ("Premiums are rising fast", "Delacroix 25", "costs-advantage", "premiums are rising fast"),
    ("The states should establish it", "Pryce 26", "states-cp", "the states should establish it"),
    ("Probability first", "Szabo 24", "spending-da", "probability first"),
)
ANSWERS = {
    **{sent: label for _, _, label, sent in LABELLED},
    "thistle open public financing is cheaper": "single-payer-aff",
}
"""What the model answers, by the tag as sent; the planted tag unscrubbed too, so a name the scrub leaves in
fails the build's scan, not this router."""

IDENTITIES = (
    "Quillmere",
    "Brindle",
    "Harrowgate",
    "Lantern Classic",
    "Thistle Open",
    "thistle open",
    '"QW"',
    '"ZT"',
    '"PX"',
)


class AnswersRightAfterARepair(ScriptedModelRouter):
    """Names an item the batch lacks in its first answer; answers every card by its tag after the repair."""

    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        repair = prompt.prompt_id == REPAIR_PROMPT_ID
        if repair:
            user = str(prompt.variables["failed_user"])
            items: list[dict[str, Any]] = json.loads(user[user.index("\n[") :])
        else:
            items = json.loads(str(prompt.variables["items"]))
        answers = [
            {
                "item": item["item"] if repair or index else "item-99",
                "position_id": ANSWERS.get(item["tag"]),
                "confidence": 0.9,
                "rationale": "the tag states the argument",
            }
            for index, item in enumerate(items)
        ]
        self.enqueue({"answers": answers})
        return await super().generate_structured(task_class, prompt, schema, params)


def write_sample(world: SyntheticRun, directory: Path) -> tuple[Path, Path]:
    """The coach's filled CSV and the rows file beside it, each card found by its tag and cite."""
    table = world.data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    by_card = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        by_card[record["exact_fingerprint"]] = card_item_id(
            record["source_sha256"], record["first_element_index"]
        )
    sample = directory / "coach-sample-labelled.csv"
    rows = directory / "coach-sample.jsonl"
    lines = [json.dumps({"schema": "local-classifier-sample-1", "populations": {"all": 9}})]
    with sample.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_row", "position"])
        for row, (tag, cite, label, _) in enumerate(LABELLED, start=1):
            writer.writerow([row, label])
            fingerprint = hashlib.sha256(f"{tag}|{cite}".encode()).hexdigest()
            lines.append(json.dumps({"sample_row": row, "item_id": by_card[fingerprint], "stratum": "all"}))
    rows.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sample, rows


def record_cassettes(world: SyntheticRun, sample: Path, rows: Path) -> Path:
    """The evaluation recorded once, in this process, as the operator's `--model-mode record` would."""
    data_dir = world.data_dir
    cassettes = data_dir / "landscape" / "model-cassettes"
    registry = PromptRegistry.load(REPO_ROOT / "prompts")
    router = RecordReplayModelRouter(
        AnswersRightAfterARepair(), mode=ModelMode.RECORD, cassette_dir=cassettes, environ={}
    )
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    service = LandscapeModelEvaluationService(
        taxonomies=YamlTaxonomyRepository.load(world.config_dir),
        parsed_store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        objects=objects,
        stage=lambda max_items: ModelClassificationStage(
            StructuredOutputGuard(router, registry),
            ParsedStoreCardTexts(LocalParsedStore(data_dir)),
            max_items=max_items,
        ),
        cassette_texts=lambda: (),
    )
    with sample.open(encoding="utf-8", newline="") as labels, rows.open(encoding="utf-8") as lines:
        recorded = asyncio.run(
            service.evaluate(SYNTHETIC_RUN_CASELIST, labels, lines, snapshot=date.fromisoformat(SNAPSHOT))
        )
    assert (recorded.counted, recorded.correct, recorded.calls) == (4, 4, 2)
    return cassettes


@pytest.fixture
def evaluation(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[tuple[SyntheticRun, Path, Path]]:
    """`synthetic26` planted with its sample and recorded cassettes, and a scratch checkout to run in."""
    world = plant_synthetic_run(tmp_path / "world", planted_tags={("aff-one", 2): PLANTED_TAG})
    sample, rows = write_sample(world, tmp_path)
    cassettes = record_cassettes(world, sample, rows)
    assert len(list((cassettes / REPAIR_PROMPT_ID).glob("*.json"))) == 1
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{world.data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    shutil.copytree(REPO_ROOT / "prompts", installed_cli.workdir / "prompts")
    (installed_cli.workdir / "config" / "profiles").mkdir(parents=True)
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    yield world, sample, rows


def evaluate(installed_cli: InstalledCli, world: SyntheticRun, sample: Path, rows: Path, *extra: str) -> Any:
    return installed_cli.run(
        "--json",
        "landscape",
        "evaluate",
        "--caselist",
        SYNTHETIC_RUN_CASELIST,
        "--snapshot",
        SNAPSHOT,
        "--sample",
        str(sample),
        "--sample-rows",
        str(rows),
        "--config-dir",
        str(world.config_dir),
        *extra,
    )


CLEAN = {"schools": 0, "team_codes": 0, "other_names": 0, "clean": True}


def test_landscape_evaluate_replays_the_recorded_sample_with_clean_scans(
    installed_cli: InstalledCli, evaluation: tuple[SyntheticRun, Path, Path]
) -> None:
    world, sample, rows = evaluation

    result = evaluate(installed_cli, world, sample, rows)

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert (data["prompt_version"], data["taxonomy_version"], data["event"]) == ("1.1.0", "1.0.0", "POLICY")
    assert (data["labelled"], data["found"], data["asked"], data["calls"]) == (4, 4, 4, 2)
    assert (data["counted"], data["correct"], data["accuracy"], data["meets_target"]) == (4, 4, 1.0, True)
    assert (data["placed_below_threshold"], data["placed_labelled_none"], data["refused"]) == (0, 0, {})
    assert data["scan"] == {
        "prompt_inputs": {"texts": 1, **CLEAN},
        "cassettes": {"texts": 1, **CLEAN},
        "repair_cassettes": {"texts": 1, **CLEAN},
    }
    for identity in IDENTITIES:
        assert identity not in result.output


def test_landscape_evaluate_breakdown_counts_each_card_and_the_repaired_batch(
    installed_cli: InstalledCli, evaluation: tuple[SyntheticRun, Path, Path]
) -> None:
    world, sample, rows = evaluation

    result = evaluate(installed_cli, world, sample, rows, "--breakdown")

    assert result.exit_code == ExitCode.OK, result.output
    breakdown = json.loads(result.stdout)["data"]["breakdown"]
    assert breakdown["outcomes"]["correct"] == 4
    assert sum(breakdown["outcomes"].values()) == 4
    assert [(one["cards"], one["calls"], one["outcome"]) for one in breakdown["batches"]] == [
        (4, 2, "repaired")
    ]
    hits = breakdown["scan_hits"]
    assert (hits["prompt_inputs"]["hits"], hits["cassettes"]["hits"]) == (0, 0)
    assert (hits["repair_cassettes"]["texts"], hits["repair_cassettes"]["hits"]) == (1, 0)
    for identity in IDENTITIES:
        assert identity not in result.output

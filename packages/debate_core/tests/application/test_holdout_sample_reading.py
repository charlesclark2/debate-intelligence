"""The held-out sample read from a store (`v1-e32-t50`): card identities, and the evaluation reading it.

`synthetic26` (:mod:`debate_core.testing.landscape_run`) is the store: four invented sources, nine cards. By
hand: the first spending card of `neg-one` and the one of `neg-two` are one card in two teams' files (one
cluster, one body, one reading), and so are the two costs cards of `aff-one` and `aff-two`. The first sample
here is `aff-one`'s costs card; the holdout is `neg-two`'s framing card, in a document and cluster of its own.
The evaluation reads the holdout beside the first sample, refuses a pair that shares a card or a document, and
never breaks the holdout down card by card. Every school, tag and cite is invented.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.holdout_sample_draw import card_identities, drawn_from
from debate_core.application.landscape_model_evaluation import (
    EvaluationRefused,
    LandscapeModelEvaluationService,
    SampleFiles,
)
from debate_core.application.landscape_model_stage import ModelClassificationStage, ParsedStoreCardTexts
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX, OccurrenceRecord
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain.landscape_classification import ModelStancedPositionAnswers, card_item_id
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.landscape_run import SYNTHETIC_RUN_CASELIST, SyntheticRun, plant_synthetic_run
from debate_core.testing.landscape_store import PARSER_VERSION

SNAPSHOT = date(2026, 9, 15)
REPO = Path(__file__).resolve().parents[4]
# (tag, short cite) of each card the tests name
COSTS = ("Premiums are rising fast", "Delacroix 25")
FRAMING = ("Probability first", "Szabo 24")
SPENDING = ("New spending triggers a crowd-out", "Halvorsen 26")
SOLVENCY = ("Public financing is cheaper", "Varga 26")
BONDS = ("Crowd-out tanks the bond market", "Mbeki 25")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(tmp_path: Path) -> SyntheticRun:
    return plant_synthetic_run(tmp_path / "world")


def occurrences(world: SyntheticRun) -> list[OccurrenceRecord]:
    table = world.data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    return [
        OccurrenceRecord.model_validate_json(line) for line in table.read_text(encoding="utf-8").splitlines()
    ]


def item_ids(world: SyntheticRun, card: tuple[str, str], *, disclosed: str | None = None) -> list[str]:
    """Every item id of the card with this tag and cite, in the table's order; with `disclosed`, only the
    copy first disclosed that week (`aff-one`'s costs card is 2026-09-08's, `aff-two`'s 2026-09-15's)."""
    exact = hashlib.sha256(f"{card[0]}|{card[1]}".encode()).hexdigest()
    return [
        card_item_id(row.source_sha256, row.first_element_index)
        for row in occurrences(world)
        if row.exact_fingerprint == exact and disclosed in (None, row.snapshot)
    ]


def _local(world: SyntheticRun) -> tuple[LocalEvidence, FsEvidenceObjectStore]:
    objects = FsEvidenceObjectStore(world.data_dir)
    blobs = FsEvidenceObjectStore(world.data_dir, subdirectory=BLOB_DIRECTORY.parent)
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    return local, objects


async def reading(world: SyntheticRun) -> SeedReading:
    repository = YamlTaxonomyRepository.load(world.config_dir)
    resolved = repository.resolve(SYNTHETIC_RUN_CASELIST, SNAPSHOT)
    assert resolved is not None
    local, _ = _local(world)
    return await read_seed_sources(
        store=LocalParsedStore(world.data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
        topic=resolved.topic,
        caselist=SYNTHETIC_RUN_CASELIST,
        through=SNAPSHOT,
        topic_map=repository.topic_map(),
    )


# ------------------------------------------------------------------------------------------------
# Card identities
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_every_card_is_named_by_its_cluster_body_and_reading_from_the_same_table(
    world: SyntheticRun,
) -> None:
    rows = occurrences(world)

    identities = card_identities(await reading(world), rows)

    assert len(identities) == 9
    for row in rows:
        one = identities[card_item_id(row.source_sha256, row.first_element_index)]
        assert (one.source_sha256, one.exact_fingerprint, one.cluster_id) == (
            row.source_sha256,
            row.exact_fingerprint,
            row.cluster_id,
        )
    for card in (SPENDING, COSTS):
        first, second = (identities[item_id] for item_id in item_ids(world, card))
        assert first.source_sha256 != second.source_sha256
        assert (first.cluster_id, first.exact_fingerprint, first.read_fingerprint) == (
            second.cluster_id,
            second.exact_fingerprint,
            second.read_fingerprint,
        )
    (framing,) = item_ids(world, FRAMING)
    (bonds,) = item_ids(world, BONDS)
    assert identities[framing].cluster_id != identities[bonds].cluster_id
    assert identities[framing].read_fingerprint != identities[bonds].read_fingerprint


@pytest.mark.anyio
async def test_a_card_the_table_holds_no_row_for_has_no_cluster_or_body(world: SyntheticRun) -> None:
    (framing,) = item_ids(world, FRAMING)
    kept = [
        row
        for row in occurrences(world)
        if card_item_id(row.source_sha256, row.first_element_index) != framing
    ]

    identities = card_identities(await reading(world), kept)

    assert framing in identities, "every card the reading holds is named"
    assert (identities[framing].cluster_id, identities[framing].exact_fingerprint) == (None, None)
    assert identities[framing].read_fingerprint


@pytest.mark.anyio
async def test_the_holdout_names_its_snapshot_version_and_parser(world: SyntheticRun) -> None:
    read = await reading(world)

    assert drawn_from(read, occurrences(world), snapshot="2026-09-15") == {
        "caselist": SYNTHETIC_RUN_CASELIST,
        "topic_id": "policy-synthetic-topic",
        "snapshot": "2026-09-15",
        "version": read.version,
        "parser_version": PARSER_VERSION,
        "fingerprint_versions": ["card-fingerprint-v4"],
    }


# ------------------------------------------------------------------------------------------------
# The evaluation
# ------------------------------------------------------------------------------------------------

ANSWERS = {"premiums are rising fast": "costs-advantage", "probability first": "spending-da"}


class AnswersByTag(ScriptedModelRouter):
    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")

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


def service(world: SyntheticRun, *, asks: bool) -> LandscapeModelEvaluationService:
    local, objects = _local(world)
    registry = PromptRegistry.load(REPO / "prompts")

    def stage(max_items: int) -> ModelClassificationStage:
        if not asks:
            raise AssertionError("no model is asked before the samples are checked")
        return ModelClassificationStage(
            StructuredOutputGuard(AnswersByTag(), registry),
            ParsedStoreCardTexts(LocalParsedStore(world.data_dir)),
            max_items=max_items,
        )

    return LandscapeModelEvaluationService(
        taxonomies=YamlTaxonomyRepository.load(world.config_dir),
        parsed_store=LocalParsedStore(world.data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
        objects=objects,
        stage=stage,
        cassette_texts=lambda: (),
    )


HOLDOUT_HEADER = {
    "schema": "local-classifier-sample-1",
    "holdout": True,
    "seed": 20261114,
    "drawn_from": {
        "snapshot": "2026-09-15",
        "version": "2026.09.01-docx-1",
        "parser_version": "2026.09.01-docx",
    },
}


def rows_file(item_ids: Sequence[str], *, holdout: bool) -> list[str]:
    header = HOLDOUT_HEADER if holdout else {"schema": "local-classifier-sample-1"}
    return [
        json.dumps(header),
        *(json.dumps({"sample_row": row, "item_id": one}) for row, one in enumerate(item_ids, 1)),
    ]


def labels(*labels: str) -> io.StringIO:
    return io.StringIO(
        "sample_row,position\n" + "".join(f"{row},{one}\n" for row, one in enumerate(labels, 1))
    )


@pytest.mark.anyio
async def test_the_holdout_is_evaluated_beside_the_first_sample_each_at_its_own_snapshot(
    world: SyntheticRun,
) -> None:
    first = item_ids(world, COSTS, disclosed="2026-09-08")
    holdout = item_ids(world, FRAMING)

    beside = await service(world, asks=True).evaluate_beside(
        SYNTHETIC_RUN_CASELIST,
        SampleFiles(labels("costs-advantage"), rows_file(first, holdout=False), date(2026, 9, 8)),
        SampleFiles(labels("spending-da"), rows_file(holdout, holdout=True), SNAPSHOT),
    )

    assert (beside.first_sample.snapshot, beside.holdout.snapshot) == (date(2026, 9, 8), SNAPSHOT)
    assert (beside.first_sample.labelled, beside.first_sample.found) == (1, 1)
    assert (beside.first_sample.pipeline.counted, beside.first_sample.pipeline.by_headings) == (1, 1)
    assert (beside.holdout.labelled, beside.holdout.found, beside.holdout.asked) == (1, 1, 1)
    assert (beside.holdout.pipeline.counted, beside.holdout.pipeline.correct) == (1, 1)
    assert beside.drawn_from == HOLDOUT_HEADER["drawn_from"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "refusal"),
    [
        ("shared card", "shares 1 card(s) and 1 document(s)"),
        ("shared document", "shares 0 card(s) and 1 document(s)"),
        ("holdout unmarked", "is not marked a holdout"),
        ("first marked", "first sample's rows file is marked a holdout"),
    ],
)
async def test_a_pair_that_shares_a_card_or_document_or_is_mixed_up_is_refused_before_any_model_is_asked(
    world: SyntheticRun, case: str, refusal: str
) -> None:
    costs, solvency, framing = (
        item_ids(world, COSTS, disclosed="2026-09-08")[0],
        item_ids(world, SOLVENCY)[0],
        item_ids(world, FRAMING)[0],
    )
    first, held_out, first_marked, held_out_marked = {
        "shared card": ([costs], [framing, costs], False, True),
        "shared document": ([costs], [solvency], False, True),
        "holdout unmarked": ([costs], [framing], False, False),
        "first marked": ([costs], [framing], True, True),
    }[case]

    with pytest.raises(EvaluationRefused, match=re.escape(refusal)) as refused:
        await service(world, asks=False).evaluate_beside(
            SYNTHETIC_RUN_CASELIST,
            SampleFiles(labels("costs-advantage"), rows_file(first, holdout=first_marked), SNAPSHOT),
            SampleFiles(
                labels(*("none" for _ in held_out)), rows_file(held_out, holdout=held_out_marked), SNAPSHOT
            ),
        )

    assert costs not in str(refused.value) and "Premiums" not in str(refused.value)


@pytest.mark.anyio
async def test_the_holdout_is_never_broken_down_card_by_card(world: SyntheticRun) -> None:
    with pytest.raises(EvaluationRefused, match="never broken down card by card"):
        await service(world, asks=False).break_down(
            SYNTHETIC_RUN_CASELIST,
            labels("none"),
            rows_file(item_ids(world, FRAMING), holdout=True),
            snapshot=SNAPSHOT,
        )


@pytest.mark.anyio
async def test_the_first_sample_is_still_broken_down(world: SyntheticRun) -> None:
    broken_down = await service(world, asks=True).break_down(
        SYNTHETIC_RUN_CASELIST,
        labels("spending-da"),
        rows_file(item_ids(world, FRAMING), holdout=False),
        snapshot=SNAPSHOT,
    )

    assert broken_down.evaluation.pipeline.counted == 1


@pytest.mark.anyio
async def test_check_sample_reads_the_holdout_and_says_it_is_one(world: SyntheticRun) -> None:
    held_out = await service(world, asks=False).check_sample(
        SYNTHETIC_RUN_CASELIST,
        labels("spending-da"),
        rows_file(item_ids(world, FRAMING), holdout=True),
        snapshot=SNAPSHOT,
    )
    first = await service(world, asks=False).check_sample(
        SYNTHETIC_RUN_CASELIST,
        labels("spending-da"),
        rows_file(item_ids(world, FRAMING), holdout=False),
        snapshot=SNAPSHOT,
    )

    assert (held_out.holdout, held_out.labelled, held_out.by_label_kind) == (True, 1, {"da": 1})
    assert first.holdout is False


@pytest.mark.anyio
async def test_every_row_gets_its_files_sides_labelled_or_not(world: SyntheticRun) -> None:
    rows = rows_file(
        [
            item_ids(world, COSTS, disclosed="2026-09-08")[0],
            item_ids(world, FRAMING)[0],
            f"{'0' * 64}:card:0",
        ],
        holdout=True,
    )

    sides = await service(world, asks=False).sides_by_row(SYNTHETIC_RUN_CASELIST, rows, snapshot=SNAPSHOT)

    assert sides == {1: frozenset({"AFF"}), 2: frozenset({"NEG"}), 3: frozenset()}

"""The model stage's application half (`v1-e32-t07`): its evidence, the gate, and the evaluation (ac4).

The stage's batches, cap and refusals are tested through the service in `test_position_classification.py`.
The evaluation's scores here are worked out by hand from `LABELLED` and the scripted answers. Every
school, team, heading, tag and text is invented.
"""

from __future__ import annotations

import dataclasses
import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.errors import ProviderError, ProviderRateLimited
from debate_core.application.landscape_model_evaluation import (
    EvaluationRefused,
    LabelledCard,
    evaluate_labelled_cards,
    read_coach_sample,
)
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    ModelClassificationStage,
    ParsedStoreCardTexts,
    model_use_gate,
)
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import card_item_id
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

SHA = "a" * 64
VERSION = "2026.10.20-docx-6"
COMMON = {
    "caselist": "hspolicy99",
    "snapshot": "2026-10-20",
    "source_sha256": SHA,
    "parser_version": VERSION,
    "profile_version": "2026.09.20-verbatim-1",
    "fingerprint_version": "card-fingerprint-v4",
}


def card(first: int, evidence: str | None) -> dict[str, object]:
    return {
        "tag": "An invented claim",
        "section_path": [],
        **({"evidence_text": evidence} if evidence is not None else {}),
        "provenance": {"first_element_index": first, "last_element_index": first + 2},
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_evidence_is_read_for_the_wanted_cards_only() -> None:
    store = InMemoryParsedStore()
    entry = SourceEntry.model_validate(
        {**COMMON, "source_format": "DOCX", "byte_size": 10, "outcome": "PARSED", "reason": None, "cards": 4}
    )
    document = DocumentRecord.model_validate(
        {
            **COMMON,
            "document": {
                "source_sha256": SHA,
                "parser_version": VERSION,
                "profile_version": "2026.09.20-verbatim-1",
                "cards": [
                    card(0, "first card's words"),
                    card(3, "second card's words"),
                    card(6, "  "),
                    card(9, None),
                ],
                "warnings": [],
            },
        }
    )
    await store.write_source("hspolicy99", VERSION, entry, document)

    found = await ParsedStoreCardTexts(store).evidence_texts(
        "hspolicy99", VERSION, {SHA: {3, 6, 9}, "b" * 64: {0}}
    )

    assert found == {(SHA, 3): "second card's words"}


# ------------------------------------------------------------------------------------------------
# v1-e32-t37: the gate reads question 4 from the table under `## Open questions`
#
# The real policy has three rows numbered 4: the clause register's (rate limits), the permitted uses'
# (parsing and indexing), and open question 4. Before this task the gate read the first, so it allowed
# a live run while question 4 was open. `policy_shaped` copies the real file's tables in its order.
# ------------------------------------------------------------------------------------------------

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
REAL_POLICY = REPOSITORY_ROOT / "docs" / "policies" / "caselist-data-use.md"

OPEN_QUESTIONS_HEADER = (
    "| # | Question | Status | Who resolves it | What it blocks |\n|---|---|---|---|---|\n"
)
QUESTION_FOUR_OPEN = "**Open**"
QUESTION_FOUR_RESOLVED = (
    "**Resolved** 2026-11-01 (version 1.20), by the coach's decision: zero retention and no invocation "
    "logging are recorded"
)


def policy_shaped(question_four_status: str) -> str:
    """A policy with the real file's tables in order: a clause register, permitted uses, open questions."""
    return (
        "# Caselist and OpenEv data-use policy\n\n"
        "## Sources and terms\n\n### Clause register\n\n"
        "| # | Clause | What it says | What it means for us |\n|---|---|---|---|\n"
        "| 3 | Our Stuff | No rights in the Services are granted | There is no implied licence |\n"
        "| 4 | Acceptable Use — rate limits | No downloading beyond set rate limits | The maintainer set "
        "a rate (clause 12) |\n"
        "| 5 | Acceptable Use — security | No circumventing security | The operator's own login |\n\n"
        "## Permitted uses\n\n| # | Use | Conditions |\n|---|---|---|\n"
        "| 4 | **Parsing, hashing, fingerprinting** of the corpus | Derived artefacts inherit the rules |\n\n"
        "## Open questions\n\n"
        "**Accepted** means the coach approved the policy without the answer; **open** means the answer "
        "is still needed before the thing it gates.\n\n"
        f"{OPEN_QUESTIONS_HEADER}"
        "| 3 | **OpenEv's distribution terms** | **Accepted as a known gap**, 2026-09-19 | The coach | "
        "Nothing today |\n"
        "| 4 | Confirmation that the model provider does not retain or train on our inputs | "
        f"{question_four_status} | Operator | [E32 gate](#e32--model-classification-of-the-corpus) |\n"
        "| 5 | The removal contact address | **Resolved** 2026-09-19 | The coach | — |\n\n"
        "## Review and change control\n\n- Reviewed each season.\n"
    )


def test_the_gate_refuses_while_the_open_questions_table_leaves_question_four_open() -> None:
    refusal = model_use_gate(policy_shaped(QUESTION_FOUR_OPEN))
    assert refusal is not None
    assert "open question 4" in refusal
    assert "still open" in refusal


def test_the_gate_allows_once_the_open_questions_table_resolves_question_four() -> None:
    assert model_use_gate(policy_shaped(QUESTION_FOUR_RESOLVED)) is None


def test_the_gate_allows_under_the_policy_in_this_checkout() -> None:
    """Version 1.20 resolved question 4 (2026-11-01). Reopening it fails this test, as it should."""
    assert model_use_gate(REAL_POLICY.read_text(encoding="utf-8")) is None


def test_the_gate_ignores_an_open_status_in_an_earlier_row_four() -> None:
    """A row 4 before the heading whose third cell says open does not refuse a resolved question 4."""
    earlier = "| 4 | Acceptable Use | Still **Open** | x |\n\n"
    assert model_use_gate(earlier + policy_shaped(QUESTION_FOUR_RESOLVED)) is None


OPEN = (
    "| 4 | Confirmation that the model provider does not retain inputs | **Open** | Operator | E32 gate |\n"
)
ANSWERED = (
    "| 4 | Confirmation that the model provider does not retain inputs | **Answered** (2026-11-02) "
    "| Operator | E32 gate |\n"
)
OTHER = "| 3 | OpenEv terms | **Open** | x | y |\n"


def under_the_heading(rows: str) -> str:
    """The synthetic rows, as the open-questions table they stand for."""
    return f"## Open questions\n\n{OPEN_QUESTIONS_HEADER}{rows}"


def test_the_gate_refuses_while_question_four_is_open() -> None:
    refusal = model_use_gate(under_the_heading(OTHER + OPEN))
    assert refusal is not None
    assert "open question 4" in refusal


def test_the_gate_opens_once_question_four_is_answered() -> None:
    assert model_use_gate(under_the_heading(OTHER + ANSWERED)) is None


def test_the_gate_refuses_with_no_policy_no_row_or_no_status() -> None:
    assert model_use_gate(None) is not None
    assert model_use_gate(under_the_heading("| 3 | OpenEv terms | **Answered** | x | y |\n")) is not None
    assert model_use_gate(under_the_heading("| 4 | the question | | x | y |\n")) is not None
    assert model_use_gate(under_the_heading("| 4 | the question |   | x | y |\n")) is not None


@pytest.mark.parametrize(
    ("policy", "missing"),
    [
        pytest.param(OPEN_QUESTIONS_HEADER + ANSWERED, "no `## Open questions` heading", id="no-heading"),
        pytest.param(
            "## Open Questions to come\n\n" + OPEN_QUESTIONS_HEADER + ANSWERED, "heading", id="other-heading"
        ),
        pytest.param(
            "## Open questions\n\nNone yet.\n\n## Approval\n\n" + OPEN_QUESTIONS_HEADER + ANSWERED,
            "no table",
            id="table-after-the-next-heading",
        ),
        pytest.param("## Open questions\n\nNone yet.\n", "no table", id="no-table"),
        pytest.param(under_the_heading(OTHER), "no question 4", id="no-row"),
        pytest.param(
            "## Open questions\n\n| # | Question | Answer |\n|---|---|---|\n"
            "| 4 | the question | **Answered** |\n",
            "no Status column",
            id="no-status-column",
        ),
    ],
)
def test_the_gate_refuses_and_names_what_it_could_not_find(policy: str, missing: str) -> None:
    refusal = model_use_gate(policy)
    assert refusal is not None
    assert missing in refusal


def test_the_gate_reads_the_status_column_by_its_header() -> None:
    """Columns in another order: the Status cell is found by name, not as the third cell."""
    policy = (
        "## Open questions\n\n| # | Status | Question |\n|---|---|---|\n"
        "| 4 | **Resolved** 2026-11-01 | Is the provider's no-retention term recorded? |\n"
    )
    assert model_use_gate(policy) is None
    assert model_use_gate(policy.replace("**Resolved** 2026-11-01", "**Open**")) is not None


@pytest.mark.parametrize(
    "status",
    [
        "**Open**",
        "Open",
        "OPEN — waiting on the AWS documentation",
        "Still open.",
        "_open_",
        "**Reopened** 2026-12-01",
        "Re-opened when the terms changed",
        "Opened 2026-11-05",
        "**Resolved** for the pilot; open for the V2 tub",
    ],
)
def test_open_as_a_word_refuses(status: str) -> None:
    assert model_use_gate(policy_shaped(status)) is not None


@pytest.mark.parametrize(
    "status",
    [
        "**Resolved** 2026-11-01, recorded in the open-questions table",
        "**Resolved** 2026-11-01; read beside OpenEv's and OpenCaselist's terms",
        "**Resolved** 2026-11-01 for the open-source archives",
        "**Answered** (2026-11-02)",
        "**Accepted as a known gap**, 2026-09-19",
    ],
)
def test_a_word_containing_open_does_not_refuse(status: str) -> None:
    assert model_use_gate(policy_shaped(status)) is None


# ------------------------------------------------------------------------------------------------
# The evaluation (ac4)
#
# One source of four cards. The coach labels them states-cp, spending-da, spending-da and none. The
# scripted model answers the first two right, the third wrong (election-da), and places the fourth,
# which the coach said argues no position: 4 counted, 2 correct, 50%, under the bar. The second set
# of answers gets the third right and names no position for the fourth: 3 counted, 3 correct.
# ------------------------------------------------------------------------------------------------

REPOSITORY = Path(__file__).resolve().parents[4]
TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "spending-da",
                "label": "Spending DA",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
            {"id": "election-da", "label": "Election DA", "kind": "da", "side": "neg"},
        ],
    }
)
SOURCE = SeedSource(
    sha256="c" * 64,
    teams=(
        SeedTeam(identity="maple/ab", side=Side.NEG, names=("Maple Grove", "AB", "Lakeside Invitational")),
    ),
    cards=(
        SeedCard(tag="Federal action key", section_path=("1NC", "Fed Key"), first_element_index=0),
        SeedCard(tag="Cliff nears", section_path=("Cliff",), first_element_index=3),
        SeedCard(tag="Recession", section_path=("Impacts",), first_element_index=6),
        SeedCard(tag="Util good", section_path=("Framing",), first_element_index=9),
    ),
)
READING = SeedReading(
    caselist="hspolicy99",
    version=VERSION,
    topic_id="policy-sample-topic",
    entries=1,
    parsed=1,
    parsed_off_topic=0,
    sources=(SOURCE,),
    caselist_names={"Maple Grove": ("AB",), "Cedar Ridge": ("KL",)},
)
LABELLED = (
    LabelledCard(card_item_id("c" * 64, 0), "states-cp"),
    LabelledCard(card_item_id("c" * 64, 3), "spending-da"),
    LabelledCard(card_item_id("c" * 64, 6), "spending-da"),
    LabelledCard(card_item_id("c" * 64, 9), "none"),
)
FIRST_ANSWERS: dict[str, tuple[str | None, float]] = {
    "federal action key": ("states-cp", 0.8),
    "cliff nears": ("spending-da", 0.9),
    "recession": ("election-da", 0.7),
    "util good": ("spending-da", 0.65),
}
BETTER_ANSWERS: dict[str, tuple[str | None, float]] = {
    **FIRST_ANSWERS,
    "recession": ("spending-da", 0.7),
    "util good": (None, 0.9),
}


class ByTag(ScriptedModelRouter):
    def __init__(self, answers: Mapping[str, tuple[str | None, float]]) -> None:
        super().__init__(model_id="recorded-model")
        self.answers = dict(answers)

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        items: list[dict[str, Any]] = json.loads(str(prompt.variables["items"]))
        self.enqueue(
            {
                "answers": [
                    {
                        "item": item["item"],
                        "position_id": self.answers[item["tag"]][0],
                        "confidence": self.answers[item["tag"]][1],
                        "rationale": "a reason in the model's words",
                    }
                    for item in items
                ]
            }
        )
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(REPOSITORY / "prompts")


def stage_over(router: Any, registry: PromptRegistry) -> ModelClassificationStage:
    return ModelClassificationStage(
        StructuredOutputGuard(router, registry), ParsedStoreCardTexts(InMemoryParsedStore())
    )


def texts_under(directory: Path) -> list[str]:
    return [
        path.read_text(encoding="utf-8")
        for path in sorted((directory / CLASSIFY_POSITION_PROMPT_ID).glob("*.json"))
    ]


@pytest.mark.anyio
async def test_a_recorded_evaluation_replays_to_the_same_score_with_no_model_behind_it(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    recording = RecordReplayModelRouter(
        ByTag(FIRST_ANSWERS), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    recorded = await evaluate_labelled_cards(
        READING,
        TAXONOMY,
        LABELLED,
        stage_over(recording, prompts),
        cassette_texts=lambda: texts_under(tmp_path),
    )
    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    replayed = await evaluate_labelled_cards(
        READING,
        TAXONOMY,
        LABELLED,
        stage_over(replaying, prompts),
        cassette_texts=lambda: texts_under(tmp_path),
    )

    for result in (recorded, replayed):
        assert (result.event, result.labelled, result.found, result.asked, result.calls) == (
            "POLICY",
            4,
            4,
            4,
            1,
        )
        assert (result.counted, result.correct, result.placed_labelled_none) == (4, 2, 1)
        assert result.accuracy == 0.5
        assert not result.meets_target
        assert (result.sent.texts, result.cassettes.texts) == (1, 1)
        assert result.sent.clean and result.cassettes.clean


@pytest.mark.anyio
async def test_the_cassettes_a_stage_records_and_replays_name_each_caselist_it_ran_for(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    """`v1-e32-t31`: the stage files its calls under the caselist it runs on, and the scan stays clean."""
    recording = RecordReplayModelRouter(
        ByTag(FIRST_ANSWERS), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    recorded = await evaluate_labelled_cards(
        READING,
        TAXONOMY,
        LABELLED,
        stage_over(recording, prompts),
        cassette_texts=lambda: texts_under(tmp_path),
    )
    [cassette] = sorted((tmp_path / CLASSIFY_POSITION_PROMPT_ID).glob("*.json"))
    assert json.loads(cassette.read_text(encoding="utf-8"))["caselists"] == ["hspolicy99"]
    assert recorded.cassettes.clean

    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    another = dataclasses.replace(READING, caselist="hspolicy98")
    replayed = await evaluate_labelled_cards(
        another,
        TAXONOMY,
        LABELLED,
        stage_over(replaying, prompts),
        cassette_texts=lambda: texts_under(tmp_path),
    )
    assert json.loads(cassette.read_text(encoding="utf-8"))["caselists"] == ["hspolicy98", "hspolicy99"]
    assert (replayed.correct, replayed.cassettes.texts, replayed.cassettes.clean) == (2, 1, True)


@pytest.mark.anyio
async def test_an_evaluation_meets_the_bar_when_the_counted_cards_name_the_coachs_positions(
    prompts: PromptRegistry,
) -> None:
    result = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(ByTag(BETTER_ANSWERS), prompts)
    )

    assert (result.counted, result.correct, result.placed_labelled_none) == (3, 3, 0)
    assert result.refused == {"NO_POSITION": 1}
    assert result.accuracy == 1.0
    assert result.meets_target


@pytest.mark.anyio
async def test_a_card_placed_below_the_threshold_is_not_counted(prompts: PromptRegistry) -> None:
    unsure = {**BETTER_ANSWERS, "cliff nears": ("spending-da", 0.5)}
    result = await evaluate_labelled_cards(READING, TAXONOMY, LABELLED, stage_over(ByTag(unsure), prompts))

    assert (result.counted, result.correct, result.placed_below_threshold) == (2, 2, 1)


@pytest.mark.anyio
async def test_the_scan_finds_a_school_a_team_code_and_a_tournament_in_a_cassette(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    planted = [
        '{"rationale": "as Cedar Ridge reads it"}',
        '{"rationale": "the KL team"}',
        '{"rationale": "read at the Lakeside Invitational"}',
        '{"rationale": "nothing named"}',
    ]
    result = await evaluate_labelled_cards(
        READING,
        TAXONOMY,
        LABELLED,
        stage_over(ByTag(BETTER_ANSWERS), prompts),
        cassette_texts=lambda: planted,
    )

    assert (result.cassettes.texts, result.cassettes.schools, result.cassettes.team_codes) == (4, 1, 1)
    assert result.cassettes.other_names == 1
    assert not result.cassettes.clean
    assert result.sent.clean


@pytest.mark.anyio
async def test_a_labelled_card_the_store_no_longer_holds_is_not_found(prompts: PromptRegistry) -> None:
    gone = (*LABELLED, LabelledCard(card_item_id("d" * 64, 0), "states-cp"))
    result = await evaluate_labelled_cards(
        READING, TAXONOMY, gone, stage_over(ByTag(BETTER_ANSWERS), prompts)
    )

    assert (result.labelled, result.found) == (5, 4)


class StopsAfterTheFirstCall(ByTag):
    def __init__(self, answers: Mapping[str, tuple[str | None, float]], stop: ProviderError) -> None:
        super().__init__(answers)
        self.stop = stop

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if self.calls:
            raise self.stop
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.mark.anyio
async def test_an_evaluation_the_model_stopped_keeps_the_error_and_the_cards_not_asked(
    prompts: PromptRegistry,
) -> None:
    """`v1-e32-t33`: one card a call, so the first card is answered and the throttle stops the other three."""
    stop = ProviderRateLimited("bedrock", "recorded-model: ThrottlingException", retry_after_seconds=20.0)
    stage = ModelClassificationStage(
        StructuredOutputGuard(StopsAfterTheFirstCall(BETTER_ANSWERS, stop), prompts),
        ParsedStoreCardTexts(InMemoryParsedStore()),
        batch_size=1,
    )

    result = await evaluate_labelled_cards(READING, TAXONOMY, LABELLED, stage)

    assert (result.interrupted_by, result.interrupted) == (stop, "ProviderRateLimited")
    assert (result.asked, result.unanswered) == (1, 3)
    stopped = result.stopped
    assert stopped is not None
    assert (stopped.cause, stopped.sent, stopped.unanswered) == (stop, 1, 3)
    assert (stopped.cause_code, stopped.retry_after_seconds) == ("PROVIDER_RATE_LIMITED", 20.0)


@pytest.mark.anyio
async def test_an_evaluation_that_ran_to_the_end_has_no_stop(prompts: PromptRegistry) -> None:
    result = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(ByTag(BETTER_ANSWERS), prompts)
    )

    assert (result.interrupted_by, result.unanswered, result.stopped) == (None, 0, None)


ROWS = [
    '{"schema": "local-classifier-sample-1", "thresholds": {}}\n',
    *(
        f'{{"sample_row": {row}, "item_id": "{card_item_id("c" * 64, index)}"}}\n'
        for row, index in ((1, 0), (2, 3), (3, 6), (4, 9), (5, 0))
    ),
]


def test_the_coach_sample_is_joined_to_its_cards_by_row() -> None:
    sample = io.StringIO(
        "sample_row,tag,headings,position,note\n"
        "1,a,b,states-cp,\n2,a,b,spending-da,\n3,a,b,,\n4,a,b,None,\n5,a,b,unsure,\n"
    )

    assert read_coach_sample(sample, ROWS, TAXONOMY) == (
        LabelledCard(card_item_id("c" * 64, 0), "states-cp", sample_row=1),
        LabelledCard(card_item_id("c" * 64, 3), "spending-da", sample_row=2),
        LabelledCard(card_item_id("c" * 64, 9), "none", sample_row=4),
    )


@pytest.mark.parametrize(
    ("csv_text", "refused"),
    [
        ("sample_row,position\n1,made-up-da\n", "row 1 names a position"),
        ("sample_row,position\n9,states-cp\n", "row 9 of the coach's sample is not in its rows file"),
        ("row,label\n1,states-cp\n", "sample_row and position columns"),
    ],
)
def test_a_coach_sample_that_cannot_be_scored_is_refused_by_row(csv_text: str, refused: str) -> None:
    with pytest.raises(EvaluationRefused, match=refused):
        read_coach_sample(io.StringIO(csv_text), ROWS, TAXONOMY)

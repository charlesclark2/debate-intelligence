"""The structured-output guard: strict validation, one repair, a typed failure (v1-e05-t05).

Every router here is offline: `ScriptedModelRouter` for answers a test writes inline,
`FakeModelRouter` over `tests/fixtures/model_outputs/malformed/`, and `RecordReplayModelRouter` in
replay mode over `tests/fixtures/model_cassettes/`. Expected values are written by hand from the
fixtures and the schema, never taken from a run.

The schema is `ContractPassage` (three integers) and the prompt is the worked example,
`example.select-passage@1.0.0`, which declares that schema and the `high_volume` task class.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from debate_core.application.errors import (
    InvalidModelOutput,
    ModelAccessDenied,
    ModelRequestRejected,
    ModelUnavailableError,
    OutputProblem,
    ProviderRateLimited,
    error_code_of,
)
from debate_core.application.model_errors import (
    MAX_LOCATION_PART_LENGTH,
    MAX_MESSAGE_LENGTH,
    MAX_REPORTED_PROBLEMS,
    WITHHELD_MESSAGE,
    ModelOutputError,
    PromptMismatchError,
    ValidationPolicy,
    describe_problems,
)
from debate_core.application.structured_output import (
    REPAIR_PROMPT_ID,
    StructuredOutputGuard,
    validate_model_output,
)
from debate_core.domain.model_contracts import (
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelResponse,
    TaskClass,
)
from debate_core.integrations.models.errors import MissingFixtureError, UnknownPromptError
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry, load_prompt_file
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.contracts.model_router import ContractPassage
from debate_core.testing.fakes.model_router import ScriptedModelResponse, ScriptedModelRouter

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"
MALFORMED_FIXTURES = FIXTURES / "model_outputs" / "malformed"
CASSETTES = FIXTURES / "model_cassettes"

TASK = TaskClass.HIGH_VOLUME
"""The task class `example.select-passage` declares."""

VALID: Mapping[str, JsonValue] = {"paragraph_id": 3, "start_offset": 0, "end_offset": 42}
INVALID: Mapping[str, JsonValue] = {"paragraph_id": "the third", "start_offset": 0, "end_offset": 42}

FAIL_CLOSED = ValidationPolicy(fail_closed=True)
NOT_FAIL_CLOSED = ValidationPolicy(fail_closed=False)

SENTINEL = "sentinel-0b7e-standing-in-for-card-text"
"""Invented text a malformed answer carries; no request, error or log record may repeat it."""

CALL_SENTINEL = "sentinel-41d2-standing-in-for-snapshot-text"
"""Invented text a call's variables carry; the repair request carries it once, no error or log record ever."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    """The committed prompts, `model.repair` among them, plus the worked example."""
    committed = PromptRegistry.load(REPOSITORY_ROOT / "prompts")
    example = load_prompt_file(FIXTURES / "prompts" / "example" / "select-passage.md")
    return PromptRegistry([*committed.prompts, example])


def example_prompt(tag: str = "Warming kills") -> ModelPrompt:
    return ModelPrompt(prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": tag})


class KeepingRouter(ScriptedModelRouter):
    """A scripted router that also keeps every response it returned, to check what the guard hands back."""

    def __init__(self, responses: Sequence[ScriptedModelResponse]) -> None:
        super().__init__(responses)
        self.responses: list[ModelResponse[Any]] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        response = await super().generate_structured(task_class, prompt, schema, params)
        self.responses.append(response)
        return response


def guarded(router: KeepingRouter | ScriptedModelRouter, registry: PromptRegistry) -> StructuredOutputGuard:
    return StructuredOutputGuard(router, registry)


def located(problems: Sequence[OutputProblem]) -> list[tuple[tuple[str | int, ...], str]]:
    return [(problem.loc, problem.type) for problem in problems]


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------


async def test_validate_valid_output_passes_through_unchanged_in_one_model_call(
    registry: PromptRegistry,
) -> None:
    router = KeepingRouter([VALID])

    result = await guarded(router, registry).generate(
        TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED
    )

    assert len(router.calls) == 1
    assert result.response is router.responses[0]
    assert result.output is router.responses[0].output
    assert result.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)
    assert result.repair_attempted is False
    assert [(a.number, a.prompt_id, a.valid) for a in result.attempts] == [
        (1, "example.select-passage", True)
    ]
    assert result.metadata == router.responses[0].metadata
    assert result.metadata.repair_attempted is False


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param({**VALID, "paragraph_id": "3"}, [(("paragraph_id",), "int_type")], id="numeric string"),
        pytest.param({**VALID, "paragraph_id": 3.0}, [(("paragraph_id",), "int_type")], id="whole float"),
        pytest.param({**VALID, "paragraph_id": True}, [(("paragraph_id",), "int_type")], id="boolean"),
        pytest.param({**VALID, "quote": "x"}, [(("quote",), "extra_forbidden")], id="extra key"),
    ],
)
def test_validate_model_output_refuses_what_lax_validation_would_accept(
    answer: Mapping[str, JsonValue], expected: list[tuple[tuple[str, ...], str]]
) -> None:
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(ContractPassage, answer, prompt=example_prompt(), model_id="m")

    assert located(raised.value.problems) == expected
    assert (raised.value.prompt_id, raised.value.prompt_version, raised.value.model_id) == (
        "example.select-passage",
        "1.0.0",
        "m",
    )


class LaxInner(BaseModel):
    """A nested model whose own configuration would ignore extra keys and coerce values."""

    count: int


class LaxOuter(BaseModel):
    inner: LaxInner
    items: tuple[LaxInner, ...] = ()


def test_validate_model_output_is_strict_at_every_depth_whatever_the_schema_configures() -> None:
    answer = {"inner": {"count": "2", "note": "x"}, "items": [{"count": 1, "also": 2}], "top": 0}

    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(LaxOuter, answer, prompt=example_prompt(), model_id=None)

    assert sorted(located(raised.value.problems)) == [
        (("inner", "count"), "int_type"),
        (("inner", "note"), "extra_forbidden"),
        (("items", 0, "also"), "extra_forbidden"),
        (("top",), "extra_forbidden"),
    ]


class Stance(StrEnum):
    AFF = "aff"
    NEG = "neg"


class JsonShaped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: Stance
    at: datetime
    offsets: tuple[int, ...]
    weight: float


def test_validate_model_output_accepts_json_shaped_enums_datetimes_tuples_and_whole_floats() -> None:
    """Strict is JSON's strict: what a model can send for these types is accepted, nothing looser."""
    answer = {"stance": "neg", "at": "2026-10-24T09:30:00Z", "offsets": [3, 9], "weight": 1}

    output = validate_model_output(JsonShaped, answer, prompt=example_prompt(), model_id=None)

    assert output.stance is Stance.NEG
    assert output.offsets == (3, 9)
    assert output.at.isoformat() == "2026-10-24T09:30:00+00:00"
    assert output.weight == 1.0


def test_validate_model_output_reads_none_as_an_answer_that_never_called_the_tool() -> None:
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(ContractPassage, None, prompt=example_prompt(), model_id=None)

    assert located(raised.value.problems) == [((), "missing_tool_call")]


def test_validate_model_output_refuses_an_answer_that_is_not_json() -> None:
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(
            ContractPassage, {"paragraph_id": object()}, prompt=example_prompt(), model_id=None
        )

    assert located(raised.value.problems) == [((), "not_json")]


def test_validate_error_carries_no_part_of_the_answer() -> None:
    answer = {"paragraph_id": SENTINEL, "start_offset": [SENTINEL], "end_offset": 1, SENTINEL[:12]: 0}

    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(ContractPassage, answer, prompt=example_prompt(), model_id=None)

    error = raised.value
    assert SENTINEL not in "".join(traceback.format_exception(error))
    assert SENTINEL not in repr(error.args) + repr(error.problems)
    assert error.__cause__ is None
    assert error.__context__ is None


class QuotingValidator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str

    @field_validator("label")
    @classmethod
    def _refuse_long_labels(cls, label: str) -> str:
        if len(label) > 10:
            raise ValueError(f"label {label!r} is longer than ten characters")
        if label.startswith("quote:"):
            raise ValueError("a label may not quote evidence text")
        if label == "long":
            raise ValueError("a label explained at " + "great " * 60 + "length")
        return label


def test_validate_withholds_a_schema_authors_message_that_quotes_the_refused_value() -> None:
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(QuotingValidator, {"label": SENTINEL}, prompt=example_prompt(), model_id=None)

    assert [(p.loc, p.type, p.msg) for p in raised.value.problems] == [
        (("label",), "value_error", WITHHELD_MESSAGE)
    ]


def test_validate_keeps_a_schema_authors_message_that_does_not_quote_the_value() -> None:
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(QuotingValidator, {"label": "quote:"}, prompt=example_prompt(), model_id=None)

    assert [p.msg for p in raised.value.problems] == ["Value error, a label may not quote evidence text"]


class LongNames(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


def test_validate_bounds_the_length_of_messages_and_location_parts() -> None:
    long_key = "k" * 100
    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(LongNames, {"count": 1, long_key: 1}, prompt=example_prompt(), model_id=None)

    [problem] = raised.value.problems
    assert problem.loc == ("k" * (MAX_LOCATION_PART_LENGTH - 1) + "…",)

    with pytest.raises(InvalidModelOutput) as raised:
        validate_model_output(QuotingValidator, {"label": "long"}, prompt=example_prompt(), model_id=None)

    [problem] = raised.value.problems
    assert len(problem.msg) == MAX_MESSAGE_LENGTH
    assert problem.msg.startswith("Value error, a label explained at great great")
    assert problem.msg.endswith("…")


def test_describe_problems_lists_at_most_ten_and_counts_the_rest() -> None:
    problems = [OutputProblem(loc=(f"f{n}",), type="missing", msg="Field required") for n in range(12)]

    text = describe_problems(problems)

    assert text.startswith("12 problems: f0: Field required [missing]; f1: ")
    assert "f9: Field required [missing]; and 2 more" in text
    assert "f10" not in text
    assert MAX_REPORTED_PROBLEMS == 10


# --------------------------------------------------------------------------------------------
# The registry check (ac6), before any model call
# --------------------------------------------------------------------------------------------


class SomeOtherSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph_id: int


async def test_a_call_whose_schema_differs_from_its_registry_entry_is_refused_before_any_model_call(
    registry: PromptRegistry,
) -> None:
    router = ScriptedModelRouter([VALID])

    with pytest.raises(PromptMismatchError) as raised:
        await guarded(router, registry).generate(TASK, example_prompt(), SomeOtherSchema, policy=FAIL_CLOSED)

    assert router.calls == []
    assert raised.value.field == "output_schema"
    assert raised.value.registered == "debate_core.testing.contracts.model_router.ContractPassage"
    assert raised.value.requested.endswith("SomeOtherSchema")


async def test_a_call_whose_task_class_differs_from_its_registry_entry_is_refused_before_any_model_call(
    registry: PromptRegistry,
) -> None:
    router = ScriptedModelRouter([VALID])

    with pytest.raises(PromptMismatchError) as raised:
        await guarded(router, registry).generate(
            TaskClass.COMPLEX_REASONING, example_prompt(), ContractPassage, policy=FAIL_CLOSED
        )

    assert router.calls == []
    assert (raised.value.field, raised.value.registered, raised.value.requested) == (
        "task_class",
        "high_volume",
        "complex_reasoning",
    )


async def test_a_call_naming_an_unregistered_prompt_version_is_refused_before_any_model_call(
    registry: PromptRegistry,
) -> None:
    router = ScriptedModelRouter([VALID])
    unregistered = ModelPrompt(
        prompt_id="example.select-passage", prompt_version="9.9.9", variables={"tag": "x"}
    )

    with pytest.raises(UnknownPromptError):
        await guarded(router, registry).generate(TASK, unregistered, ContractPassage, policy=FAIL_CLOSED)

    assert router.calls == []


def test_a_guard_cannot_be_built_without_the_repair_prompt() -> None:
    only_the_example = PromptRegistry(
        [load_prompt_file(FIXTURES / "prompts" / "example" / "select-passage.md")]
    )

    with pytest.raises(UnknownPromptError):
        StructuredOutputGuard(ScriptedModelRouter(), only_the_example)


def test_a_guard_refuses_a_repair_prompt_that_names_a_schema_of_its_own(registry: PromptRegistry) -> None:
    repair = registry.get(REPAIR_PROMPT_ID, "1.0.0")
    misdeclared = PromptRegistry([dataclasses.replace(repair, schema=ContractPassage)])

    with pytest.raises(PromptMismatchError) as raised:
        StructuredOutputGuard(ScriptedModelRouter(), misdeclared)

    assert raised.value.field == "output_schema"


# --------------------------------------------------------------------------------------------
# What is not invalid output
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimited("bedrock", "ThrottlingException", retry_after_seconds=2.0),
        ModelRequestRejected("bedrock", "example-model", "ValidationException", "refused"),
        ModelAccessDenied("bedrock", "example-model", "not allowed"),
        ModelUnavailableError("bedrock", "example-model"),
    ],
    ids=["throttled", "refused", "denied", "unavailable"],
)
async def test_a_refused_or_throttled_call_passes_through_unchanged_and_is_not_repaired(
    error: Exception, registry: PromptRegistry
) -> None:
    router = ScriptedModelRouter([error, VALID])

    with pytest.raises(type(error)) as raised:
        await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    assert raised.value is error
    assert len(router.calls) == 1


async def test_repair_a_provider_error_on_the_repair_call_passes_through_unchanged(
    registry: PromptRegistry,
) -> None:
    throttled = ProviderRateLimited("bedrock", "ThrottlingException")
    router = ScriptedModelRouter([INVALID, throttled, VALID])

    with pytest.raises(ProviderRateLimited) as raised:
        await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    assert raised.value is throttled
    assert len(router.calls) == 2


# --------------------------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------------------------


async def test_repair_invalid_then_valid_succeeds_after_exactly_two_calls_and_says_so_in_the_metadata(
    registry: PromptRegistry,
) -> None:
    router = KeepingRouter([INVALID, VALID])

    result = await guarded(router, registry).generate(
        TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED
    )

    assert len(router.calls) == 2
    assert result.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)
    assert result.response is router.responses[0]
    assert result.repair_attempted is True
    assert [(a.number, a.prompt_id, a.prompt_version, a.valid) for a in result.attempts] == [
        (1, "example.select-passage", "1.0.0", False),
        (2, "model.repair", "1.0.0", True),
    ]
    assert located(result.attempts[0].problems) == [(("paragraph_id",), "int_type")]
    metadata = result.metadata
    assert (metadata.prompt_id, metadata.prompt_version) == ("example.select-passage", "1.0.0")
    assert (metadata.repair_attempted, metadata.repair_prompt_version) == (True, "1.0.0")
    assert metadata.route == router.responses[0].route


async def test_repair_still_invalid_raises_model_output_error_with_attempts_two(
    registry: PromptRegistry,
) -> None:
    """A third answer is queued and valid: a guard that tried a second repair would return it."""
    router = ScriptedModelRouter([INVALID, {"paragraph_id": 3}, VALID])

    with pytest.raises(ModelOutputError) as raised:
        await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    error = raised.value
    assert len(router.calls) == 2
    assert error.attempts == 2
    assert (error.prompt_id, error.prompt_version) == ("example.select-passage", "1.0.0")
    assert error.fail_closed is True
    assert error.error_count == 2
    assert located(error.problems) == [(("start_offset",), "missing"), (("end_offset",), "missing")]
    assert [(a.number, a.prompt_id, a.error_count) for a in error.attempt_records] == [
        (1, "example.select-passage", 1),
        (2, "model.repair", 2),
    ]
    assert isinstance(error, InvalidModelOutput)
    assert error_code_of(error) == "INVALID_MODEL_OUTPUT"
    assert str(error) == (
        "invalid output from fake-model for prompt example.select-passage@1.0.0: still invalid after 2 "
        "attempts, the last with model.repair@1.0.0: 2 problems: start_offset: Field required [missing]; "
        "end_offset: Field required [missing]"
    )


async def test_repair_error_lists_at_most_ten_problems_and_counts_them_all(registry: PromptRegistry) -> None:
    many_extras = {**VALID, **{f"extra_{n:02}": n for n in range(12)}}
    router = ScriptedModelRouter([many_extras, many_extras])

    with pytest.raises(ModelOutputError) as raised:
        await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    assert raised.value.error_count == 12
    assert len(raised.value.problems) == 10
    assert str(raised.value).endswith("; and 2 more")
    repair_problems = router.calls[1].prompt.variables["problems"]
    assert isinstance(repair_problems, list) and len(repair_problems) == 10


async def test_repair_call_runs_the_registered_repair_prompt_on_the_original_route(
    registry: PromptRegistry,
) -> None:
    router = ScriptedModelRouter([INVALID, VALID])
    params = ModelParams(max_tokens=300, timeout_seconds=20.0)

    await guarded(router, registry).generate(
        TASK, example_prompt(), ContractPassage, params, policy=FAIL_CLOSED
    )

    call, repair = router.calls
    assert (repair.prompt.prompt_id, repair.prompt.prompt_version) == ("model.repair", "1.0.0")
    registered = registry.get("model.repair", "1.0.0")
    assert registered.spec.version == "1.0.0"
    assert registered.spec.is_released
    assert repair.task_class is call.task_class is TASK
    assert repair.params == call.params == params
    assert repair.output_schema == call.output_schema


EXAMPLE_SYSTEM = (
    "You choose one passage from a numbered list of paragraphs.\n"
    "Answer with the paragraph's number and the character offsets where the passage starts and ends.\n"
    "Never copy any of the paragraph's words into your answer."
)
"""`select-passage.md`'s system turn, copied by hand from the file."""

EXAMPLE_USER = "Choose the passage that best supports this tag: Warming kills"
"""`select-passage.md`'s user turn with the tag `Warming kills`, written by hand."""


async def test_repair_request_carries_the_call_and_the_problems_and_nothing_the_model_said(
    registry: PromptRegistry,
) -> None:
    router = ScriptedModelRouter([INVALID, VALID])

    await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    variables = router.calls[1].prompt.variables
    assert set(variables) == {
        "failed_prompt",
        "failed_system",
        "failed_user",
        "schema_name",
        "json_schema",
        "problems",
    }
    assert variables["failed_prompt"] == "example.select-passage@1.0.0"
    assert variables["failed_system"] == EXAMPLE_SYSTEM
    assert variables["failed_user"] == EXAMPLE_USER
    assert variables["schema_name"] == "ContractPassage"
    assert isinstance(variables["json_schema"], str)
    assert json.loads(variables["json_schema"]) == ContractPassage.model_json_schema()
    assert variables["problems"] == [
        {
            "loc": ["paragraph_id"],
            "type": "int_type",
            "msg": "Input should be a valid integer",
        }
    ]
    assert "the third" not in router.calls[1].model_dump_json()


async def test_repair_request_carries_the_calls_own_rendered_prompt_byte_for_byte(
    registry: PromptRegistry,
) -> None:
    """The call's turns open the repair's turns unchanged, then come model.repair's instructions."""
    router = ScriptedModelRouter([{}, VALID])

    await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    call, repair = router.calls
    sent_first = registry.render(call.prompt)
    sent_again = registry.render(repair.prompt)
    assert (sent_first.system, sent_first.user) == (EXAMPLE_SYSTEM, EXAMPLE_USER)
    assert sent_again.system is not None
    assert sent_again.system.startswith(
        EXAMPLE_SYSTEM + "\n\nA previous answer to the request below did not fit"
    )
    assert sent_again.user.startswith(
        EXAMPLE_USER + "\n\nThe previous answer to this request (prompt example.select-passage@1.0.0) "
        "did not fit the schema ContractPassage.\n"
    )
    assert sent_again.system.count(EXAMPLE_SYSTEM) == 1
    assert sent_again.user.count(EXAMPLE_USER) == 1
    assert "- at paragraph_id: Field required (missing)" in sent_again.user
    assert '"additionalProperties": false' in sent_again.user
    assert "calling the tool once" in sent_again.system


async def test_repair_of_a_prompt_with_no_system_turn_opens_with_the_repair_instructions(
    registry: PromptRegistry, tmp_path: Path
) -> None:
    source = (FIXTURES / "prompts" / "example" / "select-passage.md").read_text(encoding="utf-8")
    front_matter, _, _ = source.partition("<!-- system -->")
    no_system = tmp_path / "no-system.md"
    no_system.write_text(
        front_matter.replace("example.select-passage", "example.no-system") + "Tag to support: {{ tag }}\n",
        encoding="utf-8",
    )
    registry = PromptRegistry([*registry.prompts, load_prompt_file(no_system)])
    prompt = ModelPrompt(
        prompt_id="example.no-system", prompt_version="1.0.0", variables={"tag": "Warming kills"}
    )
    router = ScriptedModelRouter([{}, VALID])

    await guarded(router, registry).generate(TASK, prompt, ContractPassage, policy=FAIL_CLOSED)

    repair = router.calls[1].prompt
    assert repair.variables["failed_system"] is None
    sent_again = registry.render(repair)
    assert sent_again.system is not None
    assert sent_again.system.startswith("A previous answer to the request below did not fit")
    assert sent_again.user.startswith("Tag to support: Warming kills\n\nThe previous answer to this request")


async def test_repair_requests_of_two_calls_that_fail_alike_differ(registry: PromptRegistry) -> None:
    """Two calls, one failure: each repair still names its own call, so their cassettes cannot collide."""
    router = ScriptedModelRouter([INVALID, VALID, INVALID, VALID])
    guard = guarded(router, registry)

    await guard.generate(TASK, example_prompt("Warming kills"), ContractPassage, policy=FAIL_CLOSED)
    await guard.generate(TASK, example_prompt("Tariffs help"), ContractPassage, policy=FAIL_CLOSED)

    first_repair, second_repair = router.calls[1], router.calls[3]
    assert first_repair.prompt.variables["problems"] == second_repair.prompt.variables["problems"]
    assert first_repair.prompt.variables != second_repair.prompt.variables


async def test_repair_sentinels_the_answers_reaches_nothing_and_the_calls_reaches_only_the_repair(
    registry: PromptRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """SENTINEL is in the model's answer; CALL_SENTINEL is in the call's variables."""
    caplog.set_level(logging.DEBUG)
    malformed = {"paragraph_id": SENTINEL, "start_offset": 0, "end_offset": [SENTINEL], "note": SENTINEL}
    router = ScriptedModelRouter([malformed, malformed])

    with pytest.raises(ModelOutputError) as raised:
        await guarded(router, registry).generate(
            TASK, example_prompt(f"Warming kills {CALL_SENTINEL}"), ContractPassage, policy=FAIL_CLOSED
        )

    repair = router.calls[1]
    rendered = registry.render(repair.prompt)
    sent = (rendered.system or "") + rendered.user
    assert SENTINEL not in repair.model_dump_json()
    assert SENTINEL not in sent
    assert repair.model_dump_json().count(CALL_SENTINEL) == 1
    assert sent.count(CALL_SENTINEL) == 1
    error = raised.value
    reported = "".join(traceback.format_exception(error))
    reported += repr(error.args) + repr(error.problems) + repr(error.attempt_records)
    for sentinel in (SENTINEL, CALL_SENTINEL):
        assert sentinel not in reported
    assert error.__cause__ is None
    assert error.__context__ is None
    assert caplog.records, "the guard logs each failed attempt"
    for record in caplog.records:
        for sentinel in (SENTINEL, CALL_SENTINEL):
            assert sentinel not in record.getMessage()
            assert sentinel not in repr(vars(record))


async def test_repair_logs_the_prompt_attempts_and_error_counts_only(
    registry: PromptRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="debate_core.application.structured_output")
    router = ScriptedModelRouter([INVALID, VALID])

    await guarded(router, registry).generate(TASK, example_prompt(), ContractPassage, policy=FAIL_CLOSED)

    records = [r for r in caplog.records if r.name == "debate_core.application.structured_output"]
    standard = set(vars(logging.LogRecord("name", logging.INFO, "path", 1, "message", None, None)))
    extra = ("prompt_id", "prompt_version", "attempt", "attempts", "error_count")
    logged = [(r.getMessage(), r.levelno, *(vars(r)[key] for key in extra)) for r in records]
    assert logged == [
        ("structured output failed validation", logging.WARNING, "example.select-passage", "1.0.0", 1, 1, 1),
        ("structured output repaired", logging.INFO, "example.select-passage", "1.0.0", 2, 2, 0),
    ]
    for record in records:
        assert set(vars(record)) - standard - {"message", "asctime"} == set(extra)


def test_repair_policy_allows_exactly_one_repair() -> None:
    assert ValidationPolicy(fail_closed=True).max_repairs == 1
    with pytest.raises(ValueError, match="exactly one repair attempt"):
        ValidationPolicy(fail_closed=True, max_repairs=2)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="exactly one repair attempt"):
        ValidationPolicy(fail_closed=False, max_repairs=0)  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------------------------
# An answer that never calls the tool, under replay (ac5)
# --------------------------------------------------------------------------------------------


async def test_repair_an_answer_that_never_called_the_tool_gets_the_one_repair_under_replay(
    registry: PromptRegistry,
) -> None:
    """tests/fixtures/model_cassettes/example.select-passage/d3356117...json records `"output": null`;
    model.repair/3015d1c9...json is the repair's own cassette, answering paragraph 2, 12 to 57."""
    router = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=CASSETTES)
    guard = StructuredOutputGuard(router, registry)

    result = await guard.generate(
        TASK, example_prompt("An answer that never calls the tool"), ContractPassage, policy=FAIL_CLOSED
    )

    assert result.output == ContractPassage(paragraph_id=2, start_offset=12, end_offset=57)
    assert located(result.attempts[0].problems) == [((), "missing_tool_call")]
    assert result.metadata.repair_attempted is True
    assert result.metadata.provider_request_id == "example-request-0102"
    assert result.metadata.route.provider is ModelProvider.FAKE


async def test_repair_under_replay_needs_a_cassette_of_its_own(registry: PromptRegistry) -> None:
    """example.select-passage/885bdb54...json records `{}`; no repair cassette was recorded for it."""
    router = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=CASSETTES)
    guard = StructuredOutputGuard(router, registry)

    with pytest.raises(MissingFixtureError) as raised:
        await guard.generate(
            TASK,
            example_prompt("An empty tool call whose repair was never recorded"),
            ContractPassage,
            policy=FAIL_CLOSED,
        )

    assert (raised.value.prompt_id, raised.value.prompt_version) == ("model.repair", "1.0.0")


# --------------------------------------------------------------------------------------------
# Fail closed (ac3): every malformed fixture raises
# --------------------------------------------------------------------------------------------

MALFORMED_CASES: Mapping[str, list[tuple[tuple[str | int, ...], str]]] = {
    "missing fields": [(("start_offset",), "missing"), (("end_offset",), "missing")],
    "wrong types": [
        (("paragraph_id",), "int_type"),
        (("start_offset",), "int_type"),
        (("end_offset",), "int_type"),
    ],
    "coercible values": [
        (("paragraph_id",), "int_type"),
        (("start_offset",), "int_type"),
        (("end_offset",), "int_type"),
    ],
    "extra keys": [(("passage_text",), "extra_forbidden")],
    "empty tool output": [
        (("paragraph_id",), "missing"),
        (("start_offset",), "missing"),
        (("end_offset",), "missing"),
    ],
    "no tool call": [((), "missing_tool_call")],
}
"""Each case in tests/fixtures/model_outputs/malformed/README.md, with its problems written by hand."""


@pytest.mark.parametrize("policy", [FAIL_CLOSED, NOT_FAIL_CLOSED], ids=["fail closed", "not fail closed"])
@pytest.mark.parametrize("case", list(MALFORMED_CASES))
async def test_every_malformed_fixture_raises_and_returns_nothing(
    case: str, policy: ValidationPolicy, registry: PromptRegistry
) -> None:
    """The same for both policies: validation is strict for every call (the PM's ruling of 2026-10-24)."""
    guard = StructuredOutputGuard(FakeModelRouter(MALFORMED_FIXTURES), registry)

    with pytest.raises(ModelOutputError) as raised:
        await guard.generate(
            TASK, example_prompt(f"Malformed answer: {case}"), ContractPassage, policy=policy
        )

    error = raised.value
    assert error.attempts == 2
    assert error.fail_closed is policy.fail_closed
    assert located(error.attempt_records[0].problems) == MALFORMED_CASES[case]
    assert not error.attempt_records[1].valid


def test_the_malformed_fixture_directory_holds_exactly_the_listed_cases() -> None:
    """A fixture added without a case, or a case whose fixture went missing, fails here."""
    answers = sorted(
        json.loads(path.read_text(encoding="utf-8"))["variables"]["tag"]
        for path in (MALFORMED_FIXTURES / "example.select-passage").glob("*.json")
    )

    assert answers == sorted(f"Malformed answer: {case}" for case in MALFORMED_CASES)

"""The structured-output guard: strict validation, one repair, and a typed failure (v1-e05-t05).

Application services do not call a :class:`~debate_core.application.ports.model_router.ModelRouter`
directly for structured output. They call :meth:`StructuredOutputGuard.generate`, which sits between
them and whichever router the composition root built (Bedrock, the fixture fake, replay), and does
four things in this order:

1. **Checks the call against the prompt's registry entry** before any model call: the schema and
   the task class the call names must be the ones the prompt's front matter declares, or the call
   is refused with :class:`~debate_core.application.model_errors.PromptMismatchError` (ac6).
2. **Makes the call.** Every router validates the answer with :func:`validate_model_output`, so an
   invalid answer arrives as :class:`~debate_core.application.errors.InvalidModelOutput` carrying
   its problems and none of its values, whichever router produced it.
3. **Repairs an invalid answer exactly once** with the registered `model.repair` prompt, on the same
   task class route and parameters (ac4). The repair request carries the failed call's own prompt,
   rendered by the registry exactly as the call was (same id, version and variables, unchanged and
   never re-authored), followed by `model.repair`'s instructions with the schema and the filtered
   problems (the PM's review of 2026-10-24). It never holds anything from the answer that failed.
   An answer that never called the schema's tool is invalid output like any other and gets the
   same one repair (ac5). So does a schema-valid answer that the call's `check` refuses: the
   checks that need more than the schema, such as card selection offsets against their snapshot
   (v1-e05-t06-card-selection-contract). Its problems are the check's, and like every problem
   they hold no part of the answer.
4. **Raises** :class:`~debate_core.application.model_errors.ModelOutputError` with `attempts=2`
   when the repair is invalid too (ac2). There is no default, partial or best-effort result on any
   path, whatever the policy says (ac3).

A refused, throttled or unreachable model call is not invalid output: the router's error passes
through unchanged and nothing is repaired. Whether a refusal may be retried is v1-e05-t09's.

## Strict, for every call

:func:`validate_model_output` validates in pydantic's strict mode with extra keys forbidden, at every
depth, whatever the schema's own configuration says: `"3"` is not an integer, `3.0` is not one
either, and a key the schema does not declare is refused. The answer is validated as JSON, so a
JSON string is a valid enum member, datetime or tuple, as it is when a model sends one. The rule is
the same for every call, fail-closed or not, so no coerced object can reach a fail-closed caller by
another path (the PM's ruling of 2026-10-24).

## Logs

The guard logs the prompt id and version, the attempt number and the error count, never anything
the model said and never a problem's message.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import pydantic_core
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_core import PydanticSerializationError

from debate_core.application.errors import InvalidModelOutput, OutputProblem
from debate_core.application.model_errors import (
    MAX_REPORTED_PROBLEMS,
    MISSING_TOOL_CALL,
    NOT_JSON,
    UNDESCRIBED_OUTPUT,
    ModelOutputError,
    OutputAttempt,
    PromptMismatchError,
    ValidationPolicy,
    describe_problems,
    output_problems,
)
from debate_core.application.ports.model_router import ModelRouter
from debate_core.domain.model_contracts import (
    ModelParams,
    ModelPrompt,
    ModelResponse,
    ModelUsage,
    RenderedPrompt,
    TaskClass,
)
from debate_core.domain.prompt_spec import PromptSpec
from debate_core.domain.provenance import GeneratedArtifactMetadata

__all__ = [
    "REPAIR_PROMPT_ID",
    "REPAIR_PROMPT_VERSION",
    "CatalogedPrompt",
    "OutputCheck",
    "PromptCatalog",
    "RepairedSchema",
    "StructuredOutputGuard",
    "StructuredResult",
    "missing_tool_call",
    "repair_prompt",
    "validate_model_output",
]

logger = logging.getLogger(__name__)

REPAIR_PROMPT_ID: Final = "model.repair"
"""The registered prompt a repair attempt runs (`prompts/model/repair.md`)."""

REPAIR_PROMPT_VERSION: Final = "1.0.0"
"""The version of :data:`REPAIR_PROMPT_ID` the guard runs unless it is built with another."""


class RepairedSchema(BaseModel):
    """What `model.repair`'s front matter names as its output schema: the schema of the call it repairs.

    A prompt file must name one schema, and the repair prompt answers in whichever schema the
    failed call asked for. So its file names this class, the guard checks that it does, and the
    repair call itself is made with the failed call's schema. Nothing is ever validated as this.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


type OutputCheck[OutputT: BaseModel] = Callable[[OutputT], Sequence[OutputProblem]]
"""What else a schema-valid answer must satisfy: its problems, empty when it may be used.

A check sees the validated output and whatever its caller closed over (a card selection's check
holds the snapshot). Its problems are treated as validation problems: the answer is repaired once,
then refused. A problem's message must not quote the answer, as pydantic's never do.
"""


class CatalogedPrompt(Protocol):
    """What the guard reads of a registered prompt: its front matter and the schema it answers."""

    @property
    def spec(self) -> PromptSpec:
        """The prompt's validated front matter."""
        ...

    @property
    def schema(self) -> type[BaseModel]:
        """The Pydantic model the front matter's `output_schema` names."""
        ...


class PromptCatalog(Protocol):
    """Where the guard looks prompts up: the prompt registry (v1-e05-t04-prompt-registry).

    :class:`~debate_core.integrations.models.prompt_registry.PromptRegistry` is the implementation.
    It raises its `UnknownPromptError` for a prompt or version that is not registered, and the
    guard lets it through, so an unregistered prompt is refused before any model call too.
    """

    def get(self, prompt_id: str, version: str) -> CatalogedPrompt:
        """`prompt_id` at exactly `version`."""
        ...

    def render(self, prompt: ModelPrompt) -> RenderedPrompt:
        """The text `prompt` sends, as a real router renders it; `PromptRenderError` if it does not fit."""
        ...


@dataclass(frozen=True, slots=True)
class StructuredResult[OutputT: BaseModel]:
    """A strictly valid structured output, the response it came in, and the attempts it took."""

    prompt: ModelPrompt
    """The prompt the call ran: the caller's, never the repair prompt."""
    response: ModelResponse[OutputT]
    """The router's response whose output validated: the call's own, or its repair's."""
    attempts: tuple[OutputAttempt, ...]
    """Every model call made, in order; two when a repair was needed."""
    policy: ValidationPolicy
    """The policy the call was made under."""

    @property
    def output(self) -> OutputT:
        """The validated answer, exactly as the router returned it."""
        return self.response.output

    @property
    def repair_attempted(self) -> bool:
        """Whether the first answer was invalid and this output came from the repair."""
        return len(self.attempts) > 1

    @property
    def metadata(self) -> GeneratedArtifactMetadata:
        """The provenance anything made from this output is persisted with.

        The route, request id and time are those of the call that produced the output. The prompt is
        the caller's; after a repair, `repair_attempted` is true and `repair_prompt_version` names
        the `model.repair` version that answered.
        """
        produced_by = self.response.metadata
        if not self.repair_attempted:
            return produced_by
        return produced_by.evolve(
            prompt_id=self.prompt.prompt_id,
            prompt_version=self.prompt.prompt_version,
            repair_attempted=True,
            repair_prompt_version=self.response.prompt_version,
        )


class StructuredOutputGuard:
    """Validates, repairs once, and fails typed: the only way application code asks for structured output."""

    def __init__(
        self,
        router: ModelRouter,
        prompts: PromptCatalog,
        *,
        repair_prompt_version: str = REPAIR_PROMPT_VERSION,
    ) -> None:
        """Guard `router`, checking calls against `prompts`.

        Looks the repair prompt up now, so a registry without it fails when the guard is built
        rather than on the first invalid answer. Raises `PromptMismatchError` when the registered
        `model.repair` does not name :class:`RepairedSchema`.
        """
        repair = prompts.get(REPAIR_PROMPT_ID, repair_prompt_version)
        if repair.schema is not RepairedSchema:
            raise PromptMismatchError(
                REPAIR_PROMPT_ID,
                repair_prompt_version,
                field="output_schema",
                registered=_schema_path(repair.schema),
                requested=_schema_path(RepairedSchema),
            )
        self._router = router
        self._prompts = prompts
        self._repair_version = repair.spec.version

    async def generate[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
        *,
        policy: ValidationPolicy,
        check: OutputCheck[OutputT] | None = None,
    ) -> StructuredResult[OutputT]:
        """Run `prompt` as `task_class` and return a strictly valid instance of `schema`.

        With `check`, the instance must also pass it: an answer it finds problems with is repaired
        and refused exactly as one that does not fit `schema`.

        Raises `PromptMismatchError` before any model call when `schema` or `task_class` is not
        what the prompt's registry entry declares, and the registry's `UnknownPromptError` when the
        prompt is not registered, and its `PromptRenderError` when the variables do not fit the
        prompt, all before any model call. Raises :class:`ModelOutputError` when the answer and its one
        repair are both invalid. Every other router error passes through unchanged.
        """
        rendered = self._check_registration(task_class, prompt, schema)
        attempts: list[OutputAttempt] = []
        attempt_prompt = prompt
        problems: tuple[OutputProblem, ...] = ()
        model_id: str | None = None
        for number in range(1, 2 + policy.max_repairs):
            if number > 1:
                attempt_prompt = repair_prompt(
                    prompt, rendered, schema, problems, version=self._repair_version
                )
            try:
                response = await self._router.generate_structured(task_class, attempt_prompt, schema, params)
            except InvalidModelOutput as invalid:
                problems = _described(invalid.problems)
                model_id = invalid.model_id
                usage = invalid.usage
            else:
                problems = tuple(check(response.output)) if check is not None else ()
                usage = response.usage
                if not problems:
                    attempts.append(
                        OutputAttempt(
                            number, attempt_prompt.prompt_id, attempt_prompt.prompt_version, usage=usage
                        )
                    )
                    if number > 1:
                        _log(logging.INFO, "structured output repaired", prompt, attempts)
                    return StructuredResult(
                        prompt=prompt, response=response, attempts=tuple(attempts), policy=policy
                    )
                model_id = response.route.model_id
            attempts.append(
                OutputAttempt.refused(
                    number, attempt_prompt.prompt_id, attempt_prompt.prompt_version, problems, usage=usage
                )
            )
            _log(logging.WARNING, "structured output failed validation", prompt, attempts)
        raise ModelOutputError(
            prompt.prompt_id,
            prompt.prompt_version,
            attempt_records=attempts,
            fail_closed=policy.fail_closed,
            model_id=model_id,
        )

    def _check_registration(
        self, task_class: TaskClass, prompt: ModelPrompt, schema: type[BaseModel]
    ) -> RenderedPrompt:
        """Refuse a call its registry entry does not declare, and return the text the call sends."""
        entry = self._prompts.get(prompt.prompt_id, prompt.prompt_version)
        if entry.schema is not schema:
            raise PromptMismatchError(
                prompt.prompt_id,
                prompt.prompt_version,
                field="output_schema",
                registered=_schema_path(entry.schema),
                requested=_schema_path(schema),
            )
        if entry.spec.task_class is not task_class:
            raise PromptMismatchError(
                prompt.prompt_id,
                prompt.prompt_version,
                field="task_class",
                registered=entry.spec.task_class.value,
                requested=task_class.value,
            )
        return self._prompts.render(prompt)


def repair_prompt(
    failed: ModelPrompt,
    rendered: RenderedPrompt,
    schema: type[BaseModel],
    problems: Sequence[OutputProblem],
    *,
    version: str = REPAIR_PROMPT_VERSION,
) -> ModelPrompt:
    """The `model.repair` call for an answer to `failed` that did not fit `schema` for `problems`.

    `rendered` is `failed` as the prompt registry renders it, the text the failed call sent. The
    repair carries it unchanged, so the model gets the task again (the PM's review of 2026-10-24),
    then the schema, at most :data:`MAX_REPORTED_PROBLEMS` problems and the failed prompt's id and
    version. Nothing the model said in the failed answer is in it.
    """
    listed = _described(problems)[:MAX_REPORTED_PROBLEMS]
    return ModelPrompt(
        prompt_id=REPAIR_PROMPT_ID,
        prompt_version=version,
        variables={
            "failed_prompt": f"{failed.prompt_id}@{failed.prompt_version}",
            "failed_system": rendered.system,
            "failed_user": rendered.user,
            "schema_name": schema.__name__,
            "json_schema": json.dumps(schema.model_json_schema(), indent=2, sort_keys=True),
            "problems": [
                {"loc": list(problem.loc), "type": problem.type, "msg": problem.msg} for problem in listed
            ],
        },
    )


def validate_model_output[OutputT: BaseModel](
    schema: type[OutputT],
    answer: object,
    *,
    prompt: ModelPrompt,
    model_id: str | None,
    usage: ModelUsage | None = None,
) -> OutputT:
    """`answer` as an instance of `schema`, validated strictly, or `InvalidModelOutput` without its values.

    The one validation every router applies to a structured answer. `answer` is what the model
    gave: the input of its tool call, or `None` when it never called the tool. It is validated as
    JSON in strict mode with extra keys forbidden at every depth.

    `usage` is what the call that produced the answer used. A refused answer was still a billed
    call, so the error carries it, for usage telemetry and the budget guard (v1-e05-t07).

    The error is raised outside the `except`, so it carries no chained `ValidationError`, whose
    text quotes the answer.
    """
    if answer is None:
        problems: tuple[OutputProblem, ...] = (missing_tool_call(),)
    else:
        try:
            document = pydantic_core.to_json(answer)
        except PydanticSerializationError:
            problems = (OutputProblem(loc=(), type=NOT_JSON, msg="the answer is not a JSON value"),)
        else:
            try:
                return schema.model_validate_json(document, strict=True, extra="forbid")
            except ValidationError as error:
                problems = output_problems(error)
    raise InvalidModelOutput(
        prompt.prompt_id,
        prompt.prompt_version,
        describe_problems(problems),
        model_id=model_id,
        problems=problems,
        usage=usage,
    )


def missing_tool_call(detail: str = "the answer did not call the schema's tool") -> OutputProblem:
    """The problem of an answer that never called the schema's tool, which `toolChoice` `auto` allows."""
    return OutputProblem(loc=(), type=MISSING_TOOL_CALL, msg=detail)


def _described(problems: Sequence[OutputProblem]) -> tuple[OutputProblem, ...]:
    """`problems`, or one generic problem when a router gave none; never the refusal's message."""
    if problems:
        return tuple(problems)
    return (
        OutputProblem(
            loc=(), type=UNDESCRIBED_OUTPUT, msg="the answer is not a valid instance of the schema"
        ),
    )


def _schema_path(schema: type[BaseModel]) -> str:
    return f"{schema.__module__}.{schema.__qualname__}"


def _log(level: int, message: str, prompt: ModelPrompt, attempts: Sequence[OutputAttempt]) -> None:
    last = attempts[-1]
    logger.log(
        level,
        message,
        extra={
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.prompt_version,
            "attempt": last.number,
            "attempts": len(attempts),
            "error_count": last.error_count,
        },
    )

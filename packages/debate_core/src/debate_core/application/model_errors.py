"""What the structured-output guard decides with, and what it raises when an answer cannot be used.

:class:`~debate_core.application.structured_output.StructuredOutputGuard` validates every
structured answer strictly, repairs an invalid one exactly once, and raises
:class:`ModelOutputError` if the repair is invalid too (v1-e05-t05-structured-output-validation).
This module holds the values it works with:

* :class:`ValidationPolicy`, given on every call: `fail_closed` for evidence-integrity actions,
  and the one repair the spec allows.
* :class:`OutputAttempt`, one per model call the guard made, kept on the result and on the error.
* :func:`output_problems`, which turns a pydantic `ValidationError` into
  :class:`~debate_core.application.errors.OutputProblem` values.
* :class:`ModelOutputError` and :class:`PromptMismatchError`.

## What an error may carry

A model's answer may hold card or source text, and pydantic puts the answer into its errors:
`ValidationError.errors()` has an `input` for each one, and `str(ValidationError)` prints it. So a
problem keeps each error's location, type and message only, built from
`errors(include_input=False, include_url=False, include_context=False)`, and never from `str()`
(the PM's ruling of 2026-10-24). Two more limits hold the same line:

* **A message the schema's author wrote** (a `value_error` or `assertion_error` raised by a
  validator, or a custom error type) can quote the value it refused. Pydantic's own messages are
  written from the schema, never from the answer. So an author's message is kept only when no
  string in the refused value appears in it, and is replaced by :data:`WITHHELD_MESSAGE` otherwise.
* **Lengths are bounded.** A location part is cut to :data:`MAX_LOCATION_PART_LENGTH` characters (an
  extra key's name is the model's own text), a message to :data:`MAX_MESSAGE_LENGTH`, and an error
  or a repair prompt lists at most :data:`MAX_REPORTED_PROBLEMS` problems with the total beside them.
"""

from __future__ import annotations

import typing
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Literal

from pydantic import ValidationError
from pydantic_core import core_schema

from debate_core.application.errors import InvalidModelOutput, OutputProblem

__all__ = [
    "MAX_LOCATION_PART_LENGTH",
    "MAX_MESSAGE_LENGTH",
    "MAX_REPORTED_PROBLEMS",
    "MISSING_TOOL_CALL",
    "NOT_JSON",
    "UNDESCRIBED_OUTPUT",
    "WITHHELD_MESSAGE",
    "ModelOutputError",
    "OutputAttempt",
    "PromptMismatchError",
    "ValidationPolicy",
    "describe_problems",
    "output_problems",
]

MAX_REPORTED_PROBLEMS: Final = 10
"""Most problems an error message, an attempt record or a repair prompt lists; the count is always whole."""

MAX_MESSAGE_LENGTH: Final = 200
"""Longest message a problem keeps, in characters."""

MAX_LOCATION_PART_LENGTH: Final = 64
"""Longest string part of a problem's location, in characters."""

MISSING_TOOL_CALL: Final = "missing_tool_call"
"""The problem type of an answer that never called the schema's tool (v1-e05-t05, ac5)."""

NOT_JSON: Final = "not_json"
"""The problem type of an answer that is not a JSON value, so it cannot be validated at all."""

UNDESCRIBED_OUTPUT: Final = "invalid_output"
"""The problem type the guard records for an `InvalidModelOutput` whose router gave no problems."""

WITHHELD_MESSAGE: Final = "the schema refused this value; its message quoted the value, so it is withheld"
"""What replaces a schema author's message that quotes the value it refused."""

_AUTHOR_WRITTEN: Final = frozenset({"value_error", "assertion_error"})
"""Pydantic error types whose message is a validator's own text rather than pydantic's."""

_BUILT_IN: Final = frozenset[str](typing.get_args(core_schema.ErrorType))
"""Every error type pydantic itself raises; any other type is a schema author's custom error."""

_ELLIPSIS: Final = "…"


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """How strictly one structured call is held: given on every call, so no call site can forget it.

    `fail_closed` is true for evidence-integrity actions such as card selection and markup. Such a
    call never gets a default, partial or coerced object: either a strictly valid instance of its
    schema or a :class:`ModelOutputError`, on which the caller marks the card UNVERIFIED rather
    than proceeding. Validation itself is equally strict for every call (the PM's ruling of
    2026-10-24), so no coerced object reaches a fail-closed caller by another path; the flag is
    carried to the result and the error so the caller's handling can rest on it.

    `max_repairs` is one, and only one: the spec forbids a second repair retry, and the PM ruled
    exactly one repair attempt per call.
    """

    fail_closed: bool
    """Whether the call is an evidence-integrity action, which must fail rather than degrade."""
    max_repairs: Literal[1] = 1
    """Repair attempts after an invalid first answer: always exactly one."""

    def __post_init__(self) -> None:
        if self.max_repairs != 1:
            raise ValueError(f"a structured call gets exactly one repair attempt, not {self.max_repairs!r}")


@dataclass(frozen=True, slots=True)
class OutputAttempt:
    """One model call the guard made for a structured result: which prompt, and whether it validated."""

    number: int
    """1 for the call itself, 2 for its repair."""
    prompt_id: str
    """The prompt this attempt ran: the call's own, or `model.repair` for the repair."""
    prompt_version: str
    """That prompt's version."""
    error_count: int = 0
    """How many problems the answer had; 0 when it validated."""
    problems: tuple[OutputProblem, ...] = ()
    """The first :data:`MAX_REPORTED_PROBLEMS` of them, without the answer's values."""

    @property
    def valid(self) -> bool:
        """Whether this attempt's answer validated."""
        return self.error_count == 0

    @classmethod
    def refused(
        cls, number: int, prompt_id: str, prompt_version: str, problems: Sequence[OutputProblem]
    ) -> OutputAttempt:
        """An attempt whose answer failed validation for `problems`."""
        return cls(
            number=number,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            error_count=max(len(problems), 1),
            problems=tuple(problems[:MAX_REPORTED_PROBLEMS]),
        )


class ModelOutputError(InvalidModelOutput):
    """A structured answer was still invalid after its one repair attempt (v1-e05-t05, ac2).

    Names the prompt the call ran, not the repair prompt, so a failing prompt version is found
    from the error alone. `attempts` is the number of model calls made, always 2 when a repair was
    tried; `problems` are the last attempt's, truncated, and `error_count` is how many there were.
    Like its parent it never quotes the answer. To a program it is the same failure as
    :class:`~debate_core.application.errors.InvalidModelOutput`, so it keeps that error code.
    """

    ERROR_CODE: ClassVar[str] = "INVALID_MODEL_OUTPUT"

    def __init__(
        self,
        prompt_id: str,
        prompt_version: str,
        *,
        attempt_records: Sequence[OutputAttempt],
        fail_closed: bool,
        model_id: str | None = None,
    ) -> None:
        if not attempt_records:
            raise ValueError("a ModelOutputError records at least one attempt")
        last = attempt_records[-1]
        self.attempt_records = tuple(attempt_records)
        """Every model call made, in order: the call, then its repair."""
        self.attempts = len(attempt_records)
        """How many model calls were made."""
        self.error_count = last.error_count
        """How many problems the last answer had."""
        self.fail_closed = fail_closed
        """Whether the call was an evidence-integrity action: the caller marks its card UNVERIFIED."""
        summary = describe_problems(last.problems, total=last.error_count)
        super().__init__(
            prompt_id,
            prompt_version,
            f"still invalid after {self.attempts} attempts, the last with "
            f"{last.prompt_id}@{last.prompt_version}: {summary}",
            model_id=model_id,
            problems=last.problems,
        )


class PromptMismatchError(ValueError):
    """A call names a schema or task class its prompt's registry entry does not declare (v1-e05-t05, ac6).

    Raised by the guard before any model call. A caller mistake, like the port's other `ValueError`:
    the call site and the prompt file disagree, and one of them is wrong.
    """

    def __init__(
        self,
        prompt_id: str,
        prompt_version: str,
        *,
        field: Literal["output_schema", "task_class"],
        registered: str,
        requested: str,
    ) -> None:
        self.prompt_id = prompt_id
        """The prompt the call named."""
        self.prompt_version = prompt_version
        """Its version."""
        self.field = field
        """The front matter key that disagrees: `output_schema` or `task_class`."""
        self.registered = registered
        """What the prompt file declares."""
        self.requested = requested
        """What the call asked for."""
        super().__init__(
            f"prompt {prompt_id}@{prompt_version} declares {field} {registered}, but the call asked "
            f"for {requested}; nothing was sent"
        )


def output_problems(error: ValidationError) -> tuple[OutputProblem, ...]:
    """Every error in `error` as an :class:`OutputProblem`: location, type and message, never the input.

    The problems come from `errors(include_input=False, include_url=False, include_context=False)`.
    The input is read once more, beside them, for one purpose only: to withhold a schema author's
    message that quotes the value it refused.
    """
    filtered = error.errors(include_input=False, include_url=False, include_context=False)
    refused_values = (
        details.get("input") for details in error.errors(include_url=False, include_context=False)
    )
    return tuple(
        OutputProblem(
            loc=tuple(_bounded_part(part) for part in details["loc"]),
            type=details["type"],
            msg=_bounded(_message(details["type"], details["msg"], refused)),
        )
        for details, refused in zip(filtered, refused_values, strict=True)
    )


def describe_problems(problems: Sequence[OutputProblem], *, total: int | None = None) -> str:
    """One line naming at most :data:`MAX_REPORTED_PROBLEMS` problems, and how many there were in all."""
    count = len(problems) if total is None else total
    shown = [
        f"{'.'.join(str(part) for part in problem.loc) or '(answer)'}: {problem.msg} [{problem.type}]"
        for problem in problems[:MAX_REPORTED_PROBLEMS]
    ]
    hidden = count - len(shown)
    more = f"; and {hidden} more" if hidden > 0 else ""
    noun = "problem" if count == 1 else "problems"
    return f"{count} {noun}: " + "; ".join(shown) + more


def _message(error_type: str, message: str, refused: object) -> str:
    if error_type in _BUILT_IN and error_type not in _AUTHOR_WRITTEN:
        return message
    if any(text in message for text in _strings_in(refused)):
        return WITHHELD_MESSAGE
    return message


def _strings_in(value: object) -> Iterator[str]:
    """Every non-empty string in `value`, at any depth, mapping keys included."""
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, Mapping):
        for key, item in typing.cast("Mapping[object, object]", value).items():
            yield from _strings_in(key)
            yield from _strings_in(item)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in typing.cast("Sequence[object]", value):
            yield from _strings_in(item)


def _bounded(text: str, limit: int = MAX_MESSAGE_LENGTH) -> str:
    return text if len(text) <= limit else text[: limit - 1] + _ELLIPSIS


def _bounded_part(part: str | int) -> str | int:
    return _bounded(part, MAX_LOCATION_PART_LENGTH) if isinstance(part, str) else part

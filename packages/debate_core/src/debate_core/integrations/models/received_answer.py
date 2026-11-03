"""The answer a real router received, handed to record mode beside the error that refuses it (v1-e05-t10).

:class:`~debate_core.application.errors.InvalidModelOutput` carries a refused answer's problems and
none of its values, on purpose: it goes on to the structured-output guard, to logs and to reports,
and an answer may hold source text. Record mode still has to write what the model said, so that a
repaired call recorded live replays both of its halves. So the router that received the answer
hands it over here, and only record mode listens:

1. :class:`~debate_core.integrations.models.record_replay.RecordReplayModelRouter`, in record mode,
   opens :func:`receiving_answer` around each structured call it passes on;
2. the real router calls :func:`hand_over_answer` with the answer it is about to validate: the input
   of the model's call of the schema's tool, or `None` when the model made no such call;
3. when the call raises `InvalidModelOutput`, record mode writes the answer it was handed to the
   call's cassette. It writes nothing for an answer it was not handed.

Outside record mode nobody listens, and handing an answer over does nothing. The listener is a
context variable, so calls running at the same time each hear only their own answer.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final

from pydantic import JsonValue

__all__ = ["ReceivedAnswer", "hand_over_answer", "receiving_answer"]


@dataclass(slots=True)
class ReceivedAnswer:
    """What the real router handed over during one call."""

    received: bool = False
    """Whether it handed an answer over at all; a call that got no answer hands none over."""
    answer: JsonValue | None = None
    """The answer it handed over; `None` for one that never called the schema's tool."""


_LISTENER: Final[ContextVar[ReceivedAnswer | None]] = ContextVar("received_answer", default=None)


@contextmanager
def receiving_answer() -> Generator[ReceivedAnswer, None, None]:
    """Listen for the answer a router hands over inside this block, and stop listening after it."""
    received = ReceivedAnswer()
    token = _LISTENER.set(received)
    try:
        yield received
    finally:
        _LISTENER.reset(token)


def hand_over_answer(answer: JsonValue | None) -> None:
    """Hand record mode `answer`, as received and before it is validated; nothing when nobody listens."""
    listener = _LISTENER.get()
    if listener is not None:
        listener.received = True
        listener.answer = answer

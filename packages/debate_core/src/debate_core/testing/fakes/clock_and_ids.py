"""The clock and id generator fakes: the two ambient dependencies, made deterministic.

`FixedClock` and `SequentialIdGenerator` exist so that a service's output is byte-identical on every
run. They stand for :class:`~debate_core.application.ports.providers.Clock` and
:class:`~debate_core.application.ports.providers.IdGenerator`, which they satisfy structurally, and
import no port: this is the module nearly every test imports, and it reaches nothing a test does not
use.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from debate_core.domain import CROCKFORD_BASE32_ALPHABET

__all__ = ["FAKE_EPOCH", "FixedClock", "SequentialIdGenerator"]


#: The instant a `FixedClock` starts at unless told otherwise. Obviously synthetic, and in the
#: past, so a timestamp that leaks into a golden file is recognisable at a glance.
FAKE_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


class FixedClock:
    """A clock that stays where it is put.

    By default every `now()` returns the same instant. Give it a `step` and each read advances by
    that much, which is how a test gives a sequence of records distinct, predictable timestamps
    without sleeping.
    """

    def __init__(self, start: datetime = FAKE_EPOCH, *, step: timedelta = timedelta(0)) -> None:
        self._moment = _require_aware(start)
        self._step = step

    def now(self) -> datetime:
        moment = self._moment
        self._moment = moment + self._step
        return moment

    def advance(self, delta: timedelta) -> datetime:
        """Move the clock forward by `delta` and return the new instant."""
        self._moment = self._moment + delta
        return self._moment

    def set(self, moment: datetime) -> None:
        """Move the clock to an exact instant, which must be timezone-aware."""
        self._moment = _require_aware(moment)


def _require_aware(moment: datetime) -> datetime:
    """Reject naive datetimes here, where the mistake is easy to see, not at model validation."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"a clock instant must be timezone-aware, got {moment!r}")
    return moment.astimezone(UTC)


class SequentialIdGenerator:
    """Deterministic, readable ULIDs: `0CARD000000000000000000001`, `…2`, `…3`.

    Real ULIDs are time-ordered and random, which makes a golden file impossible to check in.
    These are valid ULIDs — 26 Crockford-base32 characters starting below `8` — that count up, and
    an optional prefix labels which generator minted them when a test wires up several.
    """

    def __init__(self, prefix: str = "", *, start: int = 1) -> None:
        if len(prefix) > 24:
            raise ValueError(f"prefix must be at most 24 characters, got {len(prefix)}")
        unusable = sorted(set(prefix) - set(CROCKFORD_BASE32_ALPHABET))
        if unusable:
            raise ValueError(
                f"prefix must use the Crockford base32 alphabet ({CROCKFORD_BASE32_ALPHABET}); "
                f"cannot use {''.join(unusable)}"
            )
        self._prefix = prefix
        self._next = start
        self._digits = 25 - len(prefix)

    def new_id(self) -> str:
        counter = self._next
        self._next += 1
        rendered = str(counter)
        if len(rendered) > self._digits:
            raise ValueError(f"counter {counter} does not fit in {self._digits} characters")
        return f"0{self._prefix}{rendered.zfill(self._digits)}"

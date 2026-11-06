"""What the virtual loop asked the real selector beneath it, for tests that claim no real time passed.

`VirtualTimeEventLoop`'s selector is a real `selectors.DefaultSelector` underneath: where an ordinary
loop would wait, it asks the real selector to poll (a timeout of 0) and moves its own clock instead.
A real selector waits for as long as its timeout, so a run in which every call reached it with a
timeout of 0 is a run in which the loop never really waited, however busy the machine was.

That replaces the bounds on `time.perf_counter` these tests used to assert, under 100 ms, which a
hiccup of that length on a busy runner broke (v1-e07-t16, PM ruling of 2026-11-05). The calls are read
at the real selector's own class, which the virtual loop's selector inherits from, so nothing in the
loop changes for a test to see them.
"""

from __future__ import annotations

import selectors
from collections.abc import Generator
from contextlib import contextmanager

import pytest


@contextmanager
def real_selector_timeouts() -> Generator[list[float | None]]:
    """Every timeout a selector derived from `DefaultSelector` passed to it while the block runs.

    `DefaultSelector` itself is left out: the virtual loop's selector is a subclass, and a plain one
    belongs to something else in the process.
    """
    asked: list[float | None] = []
    real_select = selectors.DefaultSelector.select

    def select(
        self: selectors.BaseSelector, timeout: float | None = None
    ) -> list[tuple[selectors.SelectorKey, int]]:
        if type(self) is not selectors.DefaultSelector:
            asked.append(timeout)
        return real_select(self, timeout)  # pyright: ignore[reportArgumentType]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(selectors.DefaultSelector, "select", select)
        yield asked


def assert_only_polled(asked: list[float | None]) -> None:
    """The real selector was asked something, and only ever to poll: nothing really waited."""
    assert asked, "the virtual loop's selector never reached the real one: the recording saw nothing"
    waits = sorted(
        {timeout for timeout in asked if timeout != 0}, key=lambda timeout: (timeout is None, timeout)
    )
    assert not waits, f"the real selector was asked to wait (timeouts {waits}), so real time passed"

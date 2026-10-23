"""An in-memory copy of the suppression list or removal log, and an empty suppression list.

`InMemoryAppendOnlyRecord` stands for
:class:`~debate_core.application.ports.suppression.AppendOnlyRecord`, which it satisfies
structurally.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from debate_core.application.caselist.suppression import RecordedSuppressionList

__all__ = ["InMemoryAppendOnlyRecord", "empty_suppression_list"]


class InMemoryAppendOnlyRecord:
    """One copy of the suppression list or removal log, as a list of lines.

    Append-only exactly as the real copies are: lines can be read and added, never changed. Every
    append is also kept in :attr:`appends`, so a test can assert on what was written and when, and
    :attr:`fail_next_append` makes the next append raise, as a bucket refusing the write would.
    """

    def __init__(self, location: str = "in-memory record", lines: Iterable[str] = ()) -> None:
        self._location = location
        self.lines: list[str] = list(lines)
        self.appends: list[tuple[str, ...]] = []
        self.fail_next_append: Exception | None = None

    @property
    def location(self) -> str:
        return self._location

    async def read_lines(self) -> tuple[str, ...]:
        return tuple(self.lines)

    async def append_lines(self, lines: Sequence[str]) -> None:
        if not lines:
            return
        if self.fail_next_append is not None:
            failure, self.fail_next_append = self.fail_next_append, None
            raise failure
        self.appends.append(tuple(lines))
        self.lines.extend(lines)


def empty_suppression_list() -> RecordedSuppressionList:
    """A suppression list with nothing on it, for a test that is not about removals.

    Every service that stores or publishes a source takes the list as a required argument with no
    default (`v1-e30-t07`), so a test that does not care about removals says so at the call site by
    passing this, rather than the service quietly assuming it.
    """
    return RecordedSuppressionList(InMemoryAppendOnlyRecord("empty suppression list"))

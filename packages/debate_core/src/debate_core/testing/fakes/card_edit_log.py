"""The in-memory fake of the card edit log (`v1-e03-t05`)."""

from __future__ import annotations

from debate_core.application.ports.card_edit_log import CardEditEntry, CardEditLog

__all__ = ["InMemoryCardEditLog", "build_fake_card_edit_log"]


class InMemoryCardEditLog:
    """Card edit entries in a list, in the order they were appended.

    Append-only, like the port: nothing here changes or removes an entry. `entries` is every entry
    for every card, for a test asserting that a refused edit appended nothing.
    """

    def __init__(self) -> None:
        self.entries: list[CardEditEntry] = []

    async def append(self, entry: CardEditEntry) -> None:
        self.entries.append(entry)

    async def entries_for(self, card_id: str) -> tuple[CardEditEntry, ...]:
        return tuple(entry for entry in self.entries if entry.card_id == card_id)


def build_fake_card_edit_log() -> CardEditLog:
    """Build the in-memory :class:`CardEditLog` (v1-e03-t05), typed as the port.

    The annotation is the point, as it is on :class:`FakePorts`: pyright strict checks the fake
    against the Protocol here, so a signature that drifts fails in this package. A test that wants to
    read `entries` builds :class:`InMemoryCardEditLog` directly.
    """
    return InMemoryCardEditLog()

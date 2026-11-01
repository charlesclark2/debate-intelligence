"""Where the review queue's order model is kept (`v1-e32-t26`).

The model is `v1-e32-t21`'s proxy, trained on this machine from a caselist's feature table: its
vocabulary is words of the caselist's tags and headings, so it is derived from caselist data. It is
kept beside t21's feature table under the data directory, follows that directory's retention and
removal, and is never written to the repository. The store holds its text whole: the application
layer reads and checks it (:mod:`~debate_core.application.review_queue_order`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["QueueOrderModelStore"]


@runtime_checkable
class QueueOrderModelStore(Protocol):
    """One machine's review-order model files, one per caselist and topic."""

    def location(self, caselist: str, topic_id: str) -> str:
        """Where the model of `caselist` on `topic_id` is kept, to name in a message."""
        ...

    async def read(self, caselist: str, topic_id: str) -> str | None:
        """The model file's text; None when none was trained."""
        ...

    async def write(self, caselist: str, topic_id: str, text: str) -> str:
        """Replace the model file with `text`, atomically; return where it went."""
        ...

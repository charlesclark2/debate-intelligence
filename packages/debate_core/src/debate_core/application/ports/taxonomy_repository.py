"""The coach's position taxonomies and topic map, as the landscape services read them.

`v1-e32-t01-position-taxonomy` keeps both in YAML under `config/landscape/`: `topics.yaml` places a
caselist snapshot on a topic, and `taxonomies/<topic id>.yaml` lists that topic's positions, with
`generic.yaml`'s format-level positions merged in by event. The classifier (`v1-e32-t02`) and the
report (`v1-e32-t03`) ask this port, so neither knows where the files are or how they are checked.

Synchronous, unlike the storage ports: the files are a few kilobytes read once when the repository
is built, and an adapter checks every file then, so a bad edit fails before any report starts
rather than half-way through one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from debate_core.application.errors import DomainError, NotFound
from debate_core.domain.landscape import Taxonomy, Topic, TopicMap

__all__ = [
    "NoTaxonomyForTopic",
    "ResolvedTopic",
    "TaxonomyConfigError",
    "TaxonomyRepository",
]


class TaxonomyConfigError(DomainError):
    """A topic map or taxonomy file could not be read or failed its checks.

    The message names the file and what is wrong with it; `path` is the file, as the adapter named it.
    """

    def __init__(self, path: str, problem: str) -> None:
        self.path = path
        self.problem = problem
        super().__init__(f"{path}: {problem}")


class NoTaxonomyForTopic(NotFound):
    """The topic exists but has no taxonomy yet, or no topic has this id."""

    def __init__(self, topic_id: str) -> None:
        super().__init__("taxonomy", topic_id)


@dataclass(frozen=True, slots=True)
class ResolvedTopic:
    """The topic a snapshot is on, and the taxonomy to count it against when the topic has one."""

    topic: Topic
    taxonomy: Taxonomy | None
    """This topic's positions with generic.yaml's for its event; None for a topic with no taxonomy."""


@runtime_checkable
class TaxonomyRepository(Protocol):
    """Reads the topic map and each topic's taxonomy, checked as one configuration."""

    def topic_map(self) -> TopicMap:
        """`topics.yaml`: every topic and the caselist date ranges it covers."""
        ...

    def taxonomy(self, topic_id: str) -> Taxonomy:
        """The topic's positions followed by generic.yaml's for its event, checked as one taxonomy.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

    def resolve(self, caselist: str, snapshot: date) -> ResolvedTopic | None:
        """The topic `caselist`'s snapshot of `snapshot` is on, or None when no range covers it."""
        ...

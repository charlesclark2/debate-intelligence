"""The coach's position taxonomies and topic map, as the landscape services read them.

`v1-e32-t01-position-taxonomy` keeps both in YAML under `config/landscape/`: `topics.yaml` places a
caselist snapshot on a topic, and `taxonomies/<topic id>.yaml` lists that topic's positions, with
`generic.yaml`'s format-level positions merged in by event. The classifier (`v1-e32-t02`) and the
report (`v1-e32-t03`) ask this port, so neither knows where the files are or how they are checked.
The coach's review-queue decisions on a topic's headings (`overrides/<topic id>.yaml`,
`v1-e32-t02`) are read and checked with them, against the topic's merged taxonomy, and so is when a
plan text names the topic's resolutional aff (`plan_texts/<topic id>.yaml`, `v1-e32-t09`), and who a
CP text read by its place names (`analytic_texts/<topic id>.yaml`, `v1-e32-t11`), and the coach's words for a
plan's mechanisms, which a counterplan's draft marks a block by (`plan_mechanisms/<topic id>.yaml`,
`v1-e33-t14`).

Synchronous, unlike the storage ports: the files are a few kilobytes read once when the repository
is built, and an adapter checks every file then, so a bad edit fails before any report starts
rather than half-way through one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from debate_core.application.errors import DomainError, NotFound
from debate_core.application.plan_mechanism_words import PlanMechanismWords
from debate_core.arguments.landscape.analytic_texts import CounterplanActors
from debate_core.arguments.landscape.kritikal_aff import KritikalAffConfig
from debate_core.arguments.landscape.plan_text import ResolutionalPlanWords
from debate_core.domain.landscape import Taxonomy, Topic, TopicMap
from debate_core.domain.landscape_classification import OverrideRules

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

    def overrides(self, topic_id: str) -> OverrideRules:
        """The coach's decisions on the topic's headings; none when the topic has no overrides file.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

    def resolutional_plan_words(self, topic_id: str) -> ResolutionalPlanWords | None:
        """When a plan text naming no aff names the topic's resolutional aff; None with no such file.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

    def cp_text_actors(self, topic_id: str) -> CounterplanActors | None:
        """The actors a CP text read by its place must name (`v1-e32-t11`); None with no such file.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

    def kritikal_aff(self, topic_id: str) -> KritikalAffConfig | None:
        """The topic's K-aff position and its K families (`v1-e32-t17`); None with no such file, when the
        topic reads no K aff.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

    def plan_mechanism_words(self, topic_id: str) -> PlanMechanismWords | None:
        """The coach's words for a plan's mechanisms (`v1-e33-t14`); None with no such file, and a CP draft is
        then marked as before.

        Raises :class:`NoTaxonomyForTopic` for a topic with no taxonomy, or no such topic.
        """
        ...

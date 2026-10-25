"""Each affirmative round's aff for the landscape report, by plan text and by the team's other rounds.

`v1-e32-t09` ac4, through `v1-e32-t03`'s seam. :func:`build_aff_assignments` turns a caselist's
on-topic disclosures, `v1-e32-t02`'s classifications and each affirmative file's plan-text verdict
(:class:`~debate_core.application.plan_texts.PlanTextService`) into the
:class:`~debate_core.domain.landscape_report.AffAssignment` values the report counts:

* **a round** is t03's: :func:`~debate_core.application.landscape_report.round_id` of its
  disclosures, so the report and this module always mean the same round; only affirmative (or pro)
  rounds dated on or before `through` are assigned;
* **a placed aff** is t03's `PLACED_CARD` rule: a card of the round's files `v1-e32-t02` placed under
  an aff (through its `merged_into` links), READS, at or above the review threshold;
* **the assignment** is :func:`~debate_core.arguments.landscape.aff_assignment.assign_affs`':
  `PLAN_TEXT`, then `TEAM_CARRY`, and a round no signal identifies is not assigned.

A team is the round's school and team code, compared without case, and is only ever an opaque key
here. Nothing is written or logged.

:class:`AffAssignmentService` is the producer `v1-e32-t05`'s run takes (the PM's note of 2026-10-24),
as an :class:`AffAssignmentSource`: for a caselist and a through date it reads the caselist's sources
on its topic as `v1-e32-t02`'s classifier does, reads each affirmative file's plan text
(:class:`~debate_core.application.plan_texts.PlanTextService`, cached), classifies the cards
(:class:`~debate_core.application.position_classification.PositionClassificationService`, cached),
and returns :func:`build_aff_assignments`' assignments.

Inside a landscape run it is asked through :meth:`AffAssignmentService.assignments` instead, with the
run's own reading and classifications, so the caselist is neither read nor classified twice and a
dry run writes nothing (`v1-e32-t05`, wired by the PM's condition of 2026-10-24).
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Protocol, runtime_checkable

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE
from debate_core.application.errors import DomainError
from debate_core.application.landscape_report import round_id
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.plan_texts import PlanTextRun, PlanTextService
from debate_core.application.ports.classification_store import ClassificationStore
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.application.position_classification import PositionClassificationService
from debate_core.arguments.landscape.aff_assignment import (
    AffRound,
    AssignmentCounts,
    KritikalSignals,
    assign_affs,
)
from debate_core.arguments.landscape.kritikal_aff import KritikalAffConfig, KritikalAffInputs, KritikalReading
from debate_core.arguments.landscape.plan_text import (
    DocumentPlanText,
    PlanTextVocabulary,
    ResolutionalPlanWords,
)
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD, needs_review
from debate_core.domain.caselist import Disclosure, Side
from debate_core.domain.landscape import PositionKind, Taxonomy
from debate_core.domain.landscape_classification import ItemKind, PositionClassification, PositionRole
from debate_core.domain.landscape_report import AffAssignment

_AFFIRMATIVE: Final = frozenset({Side.AFF, Side.PRO})

__all__ = [
    "AffAssignmentCannotStart",
    "AffAssignmentRun",
    "AffAssignmentsForReport",
    "AffAssignmentService",
    "AffAssignmentSource",
    "build_aff_assignments",
]


class AffAssignmentCannotStart(DomainError):
    """The caselist's through date is on no topic with a taxonomy, or no affirmative source was read."""


@runtime_checkable
class AffAssignmentSource(Protocol):
    """What a landscape run asks for its affirmative rounds' affs."""

    async def aff_assignments(self, caselist: str, through: date) -> tuple[AffAssignment, ...]:
        """Each affirmative round of `caselist` disclosed on or before `through` that a signal identifies."""
        ...


@dataclass(frozen=True, slots=True)
class AffAssignmentRun:
    assignments: tuple[AffAssignment, ...] = field(repr=False)
    counts: AssignmentCounts
    aff_teams: int
    """Distinct teams with an affirmative round in range."""
    identified_teams: int
    """Of those, teams with a round assigned an aff or left to a placed card."""
    plan_texts: PlanTextRun | None = field(default=None, repr=False)
    """The plan-text reading the assignments were made from, when :class:`AffAssignmentService` read it."""
    kritikal: KritikalAffInputs | None = field(default=None, repr=False)
    """What the report's K-aff group is counted from (`v1-e32-t17`); None when the topic reads no K aff."""


@dataclass(frozen=True, slots=True)
class AffAssignmentsForReport:
    """What a landscape run is given for its affirmative rounds: the assignments, and the K-aff inputs."""

    assignments: tuple[AffAssignment, ...] = field(repr=False)
    kritikal: KritikalAffInputs | None = field(default=None, repr=False)


class AffAssignmentService:
    """The producer of each affirmative round's aff, for a caselist and a through date."""

    def __init__(
        self,
        *,
        store: ParsedStore,
        local: LocalEvidence,
        suppression: SuppressionList,
        taxonomies: TaxonomyRepository,
        classifications: ClassificationStore,
        plan_texts: PlanTextService,
    ) -> None:
        self._store = store
        self._local = local
        self._suppression = suppression
        self._taxonomies = taxonomies
        self._classifications = classifications
        self._plan_texts = plan_texts

    async def aff_assignments(self, caselist: str, through: date) -> tuple[AffAssignment, ...]:
        return (await self.run(caselist, through)).assignments

    async def run(self, caselist: str, through: date, *, version: str | None = None) -> AffAssignmentRun:
        """The assignments with their counts and the plan-text reading behind them.

        `version` names the parsed store's version directory; the newest by default.
        """
        resolved = self._taxonomies.resolve(caselist, through)
        if resolved is None or resolved.taxonomy is None:
            raise AffAssignmentCannotStart(
                f"topics.yaml puts {caselist} on {through} on no topic with a taxonomy"
            )
        reading = await read_seed_sources(
            store=self._store,
            local=self._local,
            suppression=self._suppression,
            topic=resolved.topic,
            caselist=caselist,
            version=version,
            through=through,
        )
        taxonomy = self._taxonomies.taxonomy(resolved.topic.id)
        plan_texts = await self._read_plan_texts(reading, taxonomy, writes=True)
        classified = await PositionClassificationService(
            taxonomies=self._taxonomies, store=self._classifications
        ).classify(reading)
        built = build_aff_assignments(
            disclosures=reading.disclosures,
            through=through,
            classifications=classified.classifications,
            plan_texts=plan_texts.verdicts,
            taxonomy=taxonomy,
            resolutional=self._taxonomies.resolutional_plan_words(taxonomy.topic_id),
            kritikal=self._taxonomies.kritikal_aff(taxonomy.topic_id),
            kritikal_readings=plan_texts.kritikal,
        )
        return dataclasses.replace(built, plan_texts=plan_texts)

    async def assignments(
        self,
        *,
        reading: SeedReading,
        through: date,
        classifications: Sequence[PositionClassification],
        taxonomy: Taxonomy,
        writes: bool,
    ) -> AffAssignmentsForReport:
        """`v1-e32-t05`'s seam: the affs of a landscape run's reading, from its own classifications.

        Only the plan texts are read here, from their cache; `writes` False reads them without writing
        it, for a dry run.
        """
        plan_texts = await self._read_plan_texts(reading, taxonomy, writes=writes)
        built = build_aff_assignments(
            disclosures=reading.disclosures,
            through=through,
            classifications=classifications,
            plan_texts=plan_texts.verdicts,
            taxonomy=taxonomy,
            resolutional=self._taxonomies.resolutional_plan_words(taxonomy.topic_id),
            kritikal=self._taxonomies.kritikal_aff(taxonomy.topic_id),
            kritikal_readings=plan_texts.kritikal,
        )
        return AffAssignmentsForReport(assignments=built.assignments, kritikal=built.kritikal)

    async def _read_plan_texts(
        self, reading: SeedReading, taxonomy: Taxonomy, *, writes: bool
    ) -> PlanTextRun:
        """Each affirmative source's plan-text verdict, from the cache or by parsing it."""
        affirmative = {
            source.sha256
            for source in reading.sources
            if any(team.side in _AFFIRMATIVE for team in source.teams)
        }
        documents = [
            one.source_document()
            for one in await enumerate_sources(self._local, reading.caselist)
            if one.sha256 in affirmative
        ]
        service = self._plan_texts if writes else self._plan_texts.without_writes()
        vocabulary = PlanTextVocabulary(
            taxonomy,
            self._taxonomies.resolutional_plan_words(taxonomy.topic_id),
            self._taxonomies.kritikal_aff(taxonomy.topic_id),
        )
        return await service.read(reading.caselist, documents, vocabulary)


def build_aff_assignments(
    *,
    disclosures: Sequence[Disclosure],
    through: date,
    classifications: Sequence[PositionClassification],
    plan_texts: Mapping[str, DocumentPlanText],
    taxonomy: Taxonomy,
    resolutional: ResolutionalPlanWords | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    kritikal: KritikalAffConfig | None = None,
    kritikal_readings: Mapping[str, KritikalReading] | None = None,
) -> AffAssignmentRun:
    """Every affirmative round in range assigned its aff where a signal names one, with counts.

    `resolutional` is the topic's resolutional plan, whose aff gives way to any other a round or a team
    names (:meth:`~debate_core.arguments.landscape.plan_text.PlanTextVocabulary.narrowest`).
    """
    documents: defaultdict[str, set[str]] = defaultdict(set)
    teams: dict[str, str | None] = {}
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    for disclosure in disclosures:
        if disclosure.side not in _AFFIRMATIVE or disclosure.snapshot > through:
            continue
        one = round_id(disclosure)
        documents[one].add(disclosure.source_sha256)
        teams[one] = _team(disclosure)
        by_source[disclosure.source_sha256].add(one)
    placed: defaultdict[str, set[str]] = defaultdict(set)
    advantage_rounds: set[str] = set()
    for item in classifications:
        if (
            item.item_kind is not ItemKind.CARD
            or item.position_id is None
            or item.role is not PositionRole.READS
            or needs_review(item, review_threshold)
        ):
            continue
        position = taxonomy.resolve(item.position_id)
        if position.deprecated:
            continue
        if position.kind is PositionKind.AFF:
            for one in by_source.get(item.source_sha256, ()):
                placed[one].add(position.id)
        elif position.kind is PositionKind.ADVANTAGE:
            advantage_rounds.update(by_source.get(item.source_sha256, ()))
    rounds = [
        AffRound(round_key=one, team=teams[one], documents=tuple(sorted(documents[one])))
        for one in sorted(documents)
    ]
    readings = kritikal_readings or {}
    signals = (
        None
        if kritikal is None
        else KritikalSignals(
            position_id=taxonomy.resolve(kritikal.position_id).id,
            marker_documents=frozenset(sha for sha, found in readings.items() if found.markers),
            advantage_rounds=frozenset(advantage_rounds),
        )
    )
    assigned, counts = assign_affs(
        rounds,
        plan_texts,
        {one: frozenset(found) for one, found in placed.items()},
        PlanTextVocabulary(taxonomy, resolutional),
        signals,
    )
    keys = {one.round_key for one in assigned} | set(placed)
    return AffAssignmentRun(
        assignments=tuple(
            AffAssignment(round_id=one.round_key, position_id=one.position_id, method=one.method)
            for one in assigned
        ),
        counts=counts,
        aff_teams=len({team for team in teams.values() if team is not None}),
        identified_teams=len({teams[one] for one in keys if teams.get(one) is not None}),
        kritikal=None
        if kritikal is None or signals is None
        else KritikalAffInputs(
            position_id=signals.position_id,
            marker_sources=signals.marker_documents,
            heading_families={
                sha: found.heading_families for sha, found in readings.items() if found.heading_families
            },
            families={one.id: one.label for one in kritikal.families},
            refused_by_advantage=frozenset(counts.refused_by_advantage),
        ),
    )


def _team(disclosure: Disclosure) -> str | None:
    if disclosure.school == UNKNOWN_SCHOOL or disclosure.team_code == UNKNOWN_TEAM_CODE:
        return None
    return f"{disclosure.school.casefold()}/{disclosure.team_code.casefold()}"

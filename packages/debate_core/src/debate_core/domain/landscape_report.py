"""What a weekly argument landscape report says, and the two inputs it takes beyond E30 and t02.

`v1-e32-t03-landscape-report` counts, for one caselist through one snapshot, the positions its
teams read (:mod:`debate_core.domain.landscape`), from the classifications `v1-e32-t02` writes
(:mod:`debate_core.domain.landscape_classification`), the E30 disclosures that say who read each
file on which side in which round, and the E31 fingerprints that say which cards are one card. This
module is the report as values; `LandscapeReportService` builds it and the renderer
(:mod:`debate_core.arguments.landscape.render`) writes it out.

## What a report holds

* a :class:`ReportHeader`: caselist, snapshot, topic, taxonomy version, the coach's overrides digest,
  parser version, prompt version (`none` while classification is deterministic), classification
  coverage by cards and by rounds, the denominators every share is taken over, and the staleness
  facts `v1-e34-t03`'s hook decided;
* one :class:`PositionStats` per position read: rounds, distinct teams, the aff/neg split, the
  snapshot it was first seen in and whether that is this one;
* up to N :class:`TopCard` rows per position, one per card cluster, ranked by distinct teams;
* up to N :class:`ImpactCard` rows per DA and advantage, the clusters of its cards labelled as an
  impact (`v1-e32-t10`), and per kind an :class:`ImpactCoverage`: how many of its documents carry no
  labelled impact;
* an :class:`UnclassifiedSummary`: what the report could not count, by cards and by rounds;
* how affirmative rounds were identified, one :class:`AffIdentification` per method;
* :class:`AdvantagesByAff` (`v1-e32-t15`): under each aff `v1-e32-t09` assigned rounds to, and each
  mechanism under it, its advantages ranked by distinct teams, and the advantage reads of the
  affirmative rounds no aff was assigned to.

## What a report never holds

* **No team code, school or debater name** (`docs/policies/caselist-data-use.md`, "What a report
  may show": the circuit-wide landscape shows no identity at all). A round is named by nothing; a
  team is only ever a count.
* **No card body.** A top card carries its tag and short cite exactly as parsed and a source
  reference: the content-addressed `raw/` key of the file and the card's first paragraph in it.
* **No claim beyond the disclosure.** Every card row is
  :attr:`~debate_core.domain.enums.ProvenanceMode.FILE_IMPORT`: disclosed by a team, not verified.

## The inputs from E31 and `v1-e32-t09`

* :class:`LandscapeCard` is one card of one parsed source as E31's occurrence table names it: the
  source digest and first paragraph (how a classification names it too), its exact fingerprint
  and the near-duplicate cluster it was placed in, with its tag and short cite.
* :class:`AffAssignment` is the seam `v1-e32-t09` plugs into: one affirmative round, the aff it was
  identified as reading, and the method (signal) that named it. The report counts it when present
  and otherwise shows the affirmative rounds it could not identify.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.caselist import CaselistSlug
from debate_core.domain.enums import ProvenanceMode
from debate_core.domain.landscape import PositionId, PositionKind, PositionSide, TaxonomyVersion
from debate_core.domain.landscape_texts import LandscapeTexts

__all__ = [
    "AFF_METHOD_PATTERN",
    "DEFAULT_ADVANTAGES_PER_AFF",
    "DEFAULT_IMPACT_CARDS",
    "DEFAULT_TOP_CARDS",
    "IMPACT_KINDS",
    "PLACED_CARD_METHOD",
    "ROUND_ID_PATTERN",
    "AdvantagesByAff",
    "AffAdvantage",
    "AffAdvantages",
    "AffAssignment",
    "AffIdentification",
    "AffWithoutAdvantages",
    "ImpactCard",
    "ImpactCoverage",
    "LandscapeCard",
    "LandscapeReport",
    "PositionStats",
    "ReportHeader",
    "TopCard",
    "UnassignedAdvantageReads",
    "UnclassifiedSummary",
]

DEFAULT_TOP_CARDS: Final = 5
"""How many clusters a position lists by default (ac2)."""

DEFAULT_IMPACT_CARDS: Final = 3
"""How many impact clusters a DA or advantage lists by default (`v1-e32-t10`, the PM's brief)."""

DEFAULT_ADVANTAGES_PER_AFF: Final = 5
"""How many advantages each aff and mechanism lists (`v1-e32-t15`, the PM's ruling of 2026-10-24)."""

IMPACT_KINDS: Final = (PositionKind.ADVANTAGE, PositionKind.DA)
"""The kinds whose impact cards a report lists, in report order (`v1-e32-t10`)."""

ROUND_ID_PATTERN: Final = r"^[0-9a-f]{16}$"
"""A round id: 16 hex digits of a digest of the round's disclosure fields, which it never shows."""

AFF_METHOD_PATTERN: Final = r"^[A-Z][A-Z0-9_]*$"
"""An identification method: an upper-case token, such as `PLAN_TEXT`, that `v1-e32-t09` names."""

PLACED_CARD_METHOD: Final = "PLACED_CARD"
"""The method of an aff identified by a card in the round that `v1-e32-t02` placed under it."""

RoundId = Annotated[str, StringConstraints(pattern=ROUND_ID_PATTERN)]
AffMethod = Annotated[str, StringConstraints(pattern=AFF_METHOD_PATTERN)]


class LandscapeCard(DomainModel):
    """One card of one parsed source, as E31's occurrence table names and clusters it."""

    source_sha256: Sha256Hex = Field(description="The parsed source the card is in.")
    element_index: int = Field(ge=0, description="The card's first paragraph in its document.")
    exact_fingerprint: Sha256Hex = Field(description="The card's exact fingerprint.")
    cluster_id: Sha256Hex = Field(description="The near-duplicate cluster it was placed in.")
    tag: str | None = Field(repr=False, description="The tag exactly as parsed; None when it had none.")
    short_cite: str | None = Field(repr=False, description="The short cite exactly as parsed.")
    headings: tuple[str, ...] = Field(
        default=(),
        repr=False,
        description=(
            "The headings over the card, outermost first, normalized as the position matcher reads them; "
            "the empty ones left out. `v1-e32-t10`'s impact rule reads them, and no report shows them."
        ),
    )


class AffAssignment(DomainModel):
    """`v1-e32-t09`'s answer for one affirmative round: the aff it reads, and how that was known."""

    round_id: RoundId = Field(description="The round, as `round_id` names it from its disclosure.")
    position_id: PositionId = Field(description="An aff of the topic's taxonomy.")
    method: AffMethod = Field(description="The signal that named it, such as `PLAN_TEXT`.")


class PositionStats(DomainModel):
    """One position read in the report's range: a row of positions.csv (ac1)."""

    position_id: PositionId
    label: NonEmptyText
    kind: PositionKind
    side: PositionSide
    rounds: int = Field(ge=1, description="Distinct rounds that read it.")
    teams: int = Field(ge=0, description="Distinct teams that read it, on any side.")
    aff_rounds: int = Field(ge=0, description="Of the rounds, those on the affirmative (or pro).")
    neg_rounds: int = Field(ge=0, description="Of the rounds, those on the negative (or con).")
    first_seen_snapshot: date = Field(
        description="The earliest snapshot a round reading it was disclosed in."
    )
    is_new: bool = Field(description="First seen after the previous snapshot.")
    side_teams_reading: int = Field(ge=0, description="Distinct teams that read it on its own side.")
    side_teams_disclosing: int = Field(
        ge=0, description="Distinct teams that disclosed on its side (either side for `both`)."
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.aff_rounds + self.neg_rounds > self.rounds:
            raise ValueError("a position's aff and neg rounds are among its rounds")
        if self.side_teams_reading > min(self.teams, self.side_teams_disclosing):
            raise ValueError("the teams reading a position on its side are among its teams and its side's")
        return self

    @property
    def share_of_teams(self) -> tuple[int, int]:
        """(teams reading it on its side, teams disclosing on that side): the share, as a fraction."""
        return (self.side_teams_reading, self.side_teams_disclosing)


class TopCard(DomainModel):
    """One of a position's most-read cards: a row of top_cards.csv (ac2)."""

    position_id: PositionId
    rank: int = Field(ge=1, description="1 for the cluster the most teams read within the position.")
    fingerprint: Sha256Hex = Field(description="The cluster id: near-duplicate copies count as one card.")
    teams_reading: int = Field(
        ge=0, description="Distinct teams reading a card of the cluster under the position."
    )
    tag: str | None = Field(description="One card's tag, exactly as parsed.")
    short_cite: str | None = Field(description="The same card's short cite, exactly as parsed.")
    source_object_key: NonEmptyText = Field(description="The content-addressed `raw/` key of its file.")
    element_index: int = Field(ge=0, description="The card's first paragraph in that file.")
    source_snapshot: date = Field(description="The snapshot that file was first disclosed in.")
    provenance_mode: Literal[ProvenanceMode.FILE_IMPORT] = ProvenanceMode.FILE_IMPORT


class ImpactCard(TopCard):
    """One of a DA's or an advantage's impact cards: a row of impact_cards.csv (`v1-e32-t10`).

    A :class:`TopCard` of the cluster's labelled copies only: its teams are the teams reading a copy
    labelled as an impact, and the card it shows is one of those copies.
    """


class ImpactCoverage(DomainModel):
    """How many documents of one kind carry a labelled impact (`v1-e32-t10` ac3)."""

    kind: PositionKind
    documents: int = Field(ge=0, description="Documents holding a card counted for a position of the kind.")
    labelled_documents: int = Field(ge=0, description="Of those, the documents holding an impact card.")

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.labelled_documents > self.documents:
            raise ValueError("documents with a labelled impact are among the documents")
        return self

    @property
    def unlabelled_documents(self) -> int:
        """The documents carrying no labelled impact."""
        return self.documents - self.labelled_documents


class AffIdentification(DomainModel):
    """How many affirmative rounds one method identified the aff of."""

    method: AffMethod
    rounds: int = Field(ge=1)


class AffAdvantage(DomainModel):
    """One advantage read under one aff or mechanism, with the distinct teams that read it there."""

    position_id: PositionId
    label: NonEmptyText
    teams: int = Field(ge=0, description="Distinct teams reading it in the aff's assigned rounds.")


class AffAdvantages(DomainModel):
    """One aff's or mechanism's section (`v1-e32-t15`): its top advantages, and how many more there are.

    A mechanism's rounds count under it and once under its top-level aff, so an aff's counts take in
    its mechanisms' rounds and a team is one team across them.
    """

    position_id: PositionId
    label: NonEmptyText
    mechanism_of: PositionId | None = Field(
        default=None, description="The top-level aff a mechanism is listed under; None for that aff."
    )
    mechanism_of_label: NonEmptyText | None = None
    rounds: int = Field(ge=1, description="Affirmative rounds assigned to it (or to its mechanisms).")
    teams: int = Field(ge=0, description="Distinct teams of those rounds.")
    advantage_teams: int = Field(ge=0, description="Of those teams, the ones reading an advantage in them.")
    advantages: tuple[AffAdvantage, ...] = Field(
        min_length=1, description="The top advantages by teams, then id: at most the report's cut-off."
    )
    more: int = Field(ge=0, description="Advantages read under it beyond the cut-off.")
    more_teams: int = Field(
        ge=0, description="Distinct teams reading any of those: a team is one team, however many it reads."
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if (self.mechanism_of is None) != (self.mechanism_of_label is None):
            raise ValueError("a mechanism names its aff by id and label, and a top-level aff by neither")
        if self.advantage_teams > self.teams or self.more_teams > self.advantage_teams:
            raise ValueError("an aff's advantage teams are among its teams, and its hidden ones among those")
        if self.more == 0 and self.more_teams:
            raise ValueError("no advantage is hidden, so no team reads one")
        return self


class AffWithoutAdvantages(DomainModel):
    """An aff or mechanism with assigned rounds and no advantage read in them: one entry of a closing line."""

    position_id: PositionId
    label: NonEmptyText
    mechanism_of: PositionId | None = None
    mechanism_of_label: NonEmptyText | None = None
    rounds: int = Field(ge=1)


class UnassignedAdvantageReads(DomainModel):
    """The advantage reads of affirmative rounds `v1-e32-t09` assigned no aff (`v1-e32-t15`)."""

    reads: int = Field(
        ge=0, description="Round-advantage pairs: a round reading two advantages is two reads."
    )
    rounds: int = Field(ge=0, description="Affirmative rounds with no assigned aff reading an advantage.")
    teams: int = Field(ge=0, description="Distinct teams of those rounds.")
    placed_card_rounds: int = Field(
        ge=0, description="Of those rounds, the ones whose aff only a placed card identifies (`PLACED_CARD`)."
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.placed_card_rounds > self.rounds or self.rounds > self.reads:
            raise ValueError("placed-card rounds are among the rounds, and every round holds a read")
        return self


class AdvantagesByAff(DomainModel):
    """report.md's advantages by affirmative (`v1-e32-t15`)."""

    advantages_per_aff: int = Field(ge=1, description="The cut-off: advantages shown per aff and mechanism.")
    affs: tuple[AffAdvantages, ...] = Field(
        description="Each top-level aff reading an advantage, followed by its mechanisms that read one, by "
        "teams, then rounds, then id."
    )
    without_advantages: tuple[AffWithoutAdvantages, ...] = Field(
        description="The affs and mechanisms with assigned rounds and no advantage read, in the same order."
    )
    unassigned: UnassignedAdvantageReads


class UnclassifiedSummary(DomainModel):
    """What the report could not count (ac3): cards, and rounds by side."""

    cards: int = Field(ge=0, description="Every card of every source in the range.")
    unplaced_cards: int = Field(ge=0, description="Cards nothing placed: waiting in the review queue.")
    below_threshold_cards: int = Field(ge=0, description="Cards placed below the review threshold.")
    decided_no_position_cards: int = Field(
        ge=0, description="Cards under headings the coach ruled name no position: not counted, not queued."
    )
    other_side_position_rounds: int = Field(
        ge=0,
        description=(
            "Rounds that placed a card under a position of the other side: answering it, so not a read."
        ),
    )
    aff_rounds: int = Field(ge=0)
    aff_rounds_unidentified: int = Field(ge=0, description="Affirmative rounds with no identified aff.")
    neg_rounds: int = Field(ge=0)
    neg_rounds_unplaced: int = Field(ge=0, description="Negative rounds with no counted negative position.")

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.unplaced_cards + self.below_threshold_cards + self.decided_no_position_cards > self.cards:
            raise ValueError("unclassified cards are among the cards")
        if self.aff_rounds_unidentified > self.aff_rounds or self.neg_rounds_unplaced > self.neg_rounds:
            raise ValueError("unclassified rounds are among their side's rounds")
        return self

    @property
    def unclassified_cards(self) -> int:
        return self.unplaced_cards + self.below_threshold_cards


class ReportHeader(DomainModel):
    """The header block: what the report was built from, and the denominators of its shares."""

    caselist: CaselistSlug
    snapshot: date = Field(description="The newest snapshot the report counts.")
    previous_snapshot: date | None = Field(description="The snapshot before it; None for the first.")
    topic_id: PositionId
    taxonomy_version: TaxonomyVersion
    overrides_digest: NonEmptyText = Field(description="The coach's overrides, by digest, or `none`.")
    parser_version: NonEmptyText
    prompt_version: NonEmptyText = Field(description="`none` while classification is deterministic.")
    review_threshold: float = Field(ge=0.0, le=1.0)
    top_cards_per_position: int = Field(ge=1)
    impact_cards_per_position: int = Field(ge=1)
    cards: int = Field(ge=0, description="Every card of every source in the range.")
    cards_placed: int = Field(ge=0, description="Cards under a position at or above the threshold.")
    rounds: int = Field(ge=0, description="Distinct rounds disclosed in the range.")
    rounds_with_a_read: int = Field(ge=0, description="Rounds reading at least one counted position.")
    aff_rounds: int = Field(ge=0)
    neg_rounds: int = Field(ge=0)
    teams: int = Field(ge=0, description="Distinct teams disclosing, on any side.")
    aff_teams: int = Field(ge=0, description="Distinct teams disclosing on the affirmative.")
    neg_teams: int = Field(ge=0, description="Distinct teams disclosing on the negative.")
    stale: bool = Field(description="What `v1-e34-t03`'s hook decided.")
    newest_snapshot: date = Field(description="The newest snapshot the store holds, per the hook.")
    snapshot_age_days: int = Field(description="Its age on the report date, per the hook.")
    archives_awaiting_download: int = Field(ge=0)
    provenance_mode: Literal[ProvenanceMode.FILE_IMPORT] = ProvenanceMode.FILE_IMPORT

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.cards_placed > self.cards or self.rounds_with_a_read > self.rounds:
            raise ValueError("coverage counts are among the totals")
        if self.aff_rounds + self.neg_rounds > self.rounds:
            raise ValueError("aff and neg rounds are among the rounds")
        if self.previous_snapshot is not None and self.previous_snapshot >= self.snapshot:
            raise ValueError("the previous snapshot is before the snapshot")
        return self


class LandscapeReport(DomainModel):
    """One caselist's landscape through one snapshot."""

    header: ReportHeader
    positions: tuple[PositionStats, ...] = Field(description="Every position read, in report order.")
    top_cards: tuple[TopCard, ...] = Field(description="Each position's most-read cards, in report order.")
    impact_cards: tuple[ImpactCard, ...] = Field(
        description="Each DA's and advantage's impact cards, in report order."
    )
    impact_coverage: tuple[ImpactCoverage, ...] = Field(description="One per kind of :data:`IMPACT_KINDS`.")
    unclassified: UnclassifiedSummary
    aff_identification: tuple[AffIdentification, ...] = Field(
        description="Identified affirmative rounds by method, in method order."
    )
    texts: LandscapeTexts | None = Field(
        default=None,
        description="`v1-e32-t11`'s CP texts, alternatives, roles of the ballot and overview counts; None "
        "when the run read none.",
    )
    advantages_by_aff: AdvantagesByAff | None = Field(
        default=None,
        description="`v1-e32-t15`'s advantages per assigned aff; None when the taxonomy has no advantage.",
    )

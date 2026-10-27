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
* under each impact row its scenario and internal link, and per DA and advantage one
  :class:`ChainCard` per chain role, with a :class:`ChainCoverage` per kind (`v1-e32-t14`); and what
  names each impact row, a :class:`LeadInSource`, counted per kind (`v1-e32-t25`);
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
from enum import StrEnum
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
    "LEAD_IN_ORDER",
    "PLACED_CARD_METHOD",
    "ROUND_ID_PATTERN",
    "AdvantagesByAff",
    "AffAdvantage",
    "AffAdvantages",
    "AffAssignment",
    "AffIdentification",
    "AffWithoutAdvantages",
    "CHAIN_ROLES",
    "ChainCard",
    "ChainCoverage",
    "ChainRole",
    "ImpactCard",
    "ImpactCoverage",
    "KritikalAffs",
    "KritikalFamilyCount",
    "LandscapeCard",
    "LandscapeReport",
    "LeadInSource",
    "NamedRows",
    "PositionStats",
    "ReportHeader",
    "RoleGap",
    "TopCard",
    "TransitionPlans",
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


class ChainRole(StrEnum):
    """A card's place in a DA's or an advantage's link chain, as a team labelled it (`v1-e32-t14`)."""

    UNIQUENESS = "uniqueness"
    LINK = "link"
    INTERNAL_LINK = "internal_link"
    IMPACT = "impact"
    HARMS = "harms"
    INHERENCY = "inherency"
    SOLVENCY = "solvency"


CHAIN_ROLES: Final = {
    PositionKind.DA: (ChainRole.UNIQUENESS, ChainRole.LINK, ChainRole.INTERNAL_LINK, ChainRole.IMPACT),
    PositionKind.ADVANTAGE: (
        ChainRole.UNIQUENESS,
        ChainRole.LINK,
        ChainRole.INTERNAL_LINK,
        ChainRole.IMPACT,
        ChainRole.HARMS,
        ChainRole.INHERENCY,
        ChainRole.SOLVENCY,
    ),
}
"""The roles each kind's link chain shows, in report order: the coach's list (`v1-e32-t14`)."""


class LeadInSource(StrEnum):
    """What names an impact row under report.md's "What each impact runs through" (`v1-e32-t25`).

    The value is the mark report.md prints after the name, so the coach can judge it.
    """

    SCENARIO = "scenario"
    INTERNAL_LINK = "internal link"
    LINK = "link"
    TAG = "tag"
    CARD_ABOVE = "card above"


LEAD_IN_ORDER: Final = (
    LeadInSource.SCENARIO,
    LeadInSource.INTERNAL_LINK,
    LeadInSource.LINK,
    LeadInSource.TAG,
    LeadInSource.CARD_ABOVE,
)
"""The order in which an impact row's sources name it, the first it has naming it (`v1-e32-t25`)."""

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
    heading_answers: tuple[bool, ...] = Field(
        default=(),
        repr=False,
        description=(
            "Beside each of `headings`, whether it answers (`AT:`); empty when none does. "
            "`v1-e32-t14`'s answer sub-heading fills no chain role and names no scenario."
        ),
    )

    @model_validator(mode="after")
    def _check_answers(self) -> Self:
        if self.heading_answers and len(self.heading_answers) != len(self.headings):
            raise ValueError("heading_answers is empty or one flag per heading")
        return self

    def answers(self, index: int) -> bool:
        """Whether heading `index` answers a position."""
        return bool(self.heading_answers) and self.heading_answers[index]


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
    labelled as an impact, and the card it shows is one of those copies. `v1-e32-t14` adds what the
    impact runs through, each from those copies and only as their files label it.
    """

    scenario: str | None = Field(
        default=None,
        description="The scenario name, normalized heading words two or more teams use; None when none is.",
    )
    internal_link_tag: str | None = Field(
        default=None,
        description="The tag, as parsed, of the labelled internal-link card above it; None when none is.",
    )
    link_tag: str | None = Field(
        default=None,
        description=(
            "The tag, as parsed, of the labelled link card above it (`v1-e32-t27`); None when none is. "
            "report.md only."
        ),
    )
    card_above_tag: str | None = Field(
        default=None,
        description=(
            "With no labelled internal link: the tag of the card directly above it in its block, when that "
            "card is not an impact card. A fact about the file, never called an internal link; report.md "
            "only."
        ),
    )
    named_by: LeadInSource | None = Field(
        default=None,
        description=(
            "What names the row under 'What each impact runs through' (`v1-e32-t25`): the first of its "
            "scenario, internal link, own tag and card above that is there and holds no caselist word. "
            "None when none is: the row is left out there, and counted."
        ),
    )

    @model_validator(mode="after")
    def _check_named_by(self) -> Self:
        if self.named_by is not None and self.runs_through is None:
            raise ValueError(f"its {self.named_by.value} names the row, but the row has none")
        return self

    @property
    def runs_through(self) -> str | None:
        """The words :attr:`named_by` names the row with; None when the row is left out."""
        if self.named_by is None:
            return None
        text = {
            LeadInSource.SCENARIO: self.scenario,
            LeadInSource.INTERNAL_LINK: self.internal_link_tag,
            LeadInSource.LINK: self.link_tag,
            LeadInSource.TAG: self.tag,
            LeadInSource.CARD_ABOVE: self.card_above_tag,
        }[self.named_by]
        return text if text is not None and text.strip() else None


class ChainCard(TopCard):
    """A DA's or an advantage's most-read card for one chain role (`v1-e32-t14`), rank 1 always.

    A :class:`TopCard` of the cluster's copies labelled with the role, ranked as impact cards are.
    """

    role: ChainRole


class RoleGap(DomainModel):
    """How many positions of a kind have no labelled card for one chain role."""

    role: ChainRole
    positions: int = Field(ge=0)


class NamedRows(DomainModel):
    """How many impact rows of a kind one source names (`v1-e32-t25`)."""

    source: LeadInSource
    rows: int = Field(ge=0)


class ChainCoverage(DomainModel):
    """What one kind's scenarios and link chains could not see (`v1-e32-t14` ac3)."""

    kind: PositionKind
    documents: int = Field(ge=0, description="Documents holding a card counted for a position of the kind.")
    unstructured_documents: int = Field(
        ge=0, description="Of those, the documents with no scenario heading and no chain-role label."
    )
    positions: int = Field(ge=0, description="Positions of the kind the report lists.")
    impact_rows: int = Field(ge=0)
    rows_with_scenario: int = Field(ge=0)
    rows_with_internal_link: int = Field(ge=0)
    rows_with_card_above: int = Field(
        ge=0,
        description=(
            "Rows with no labelled internal link whose card above is there and holds no caselist word. It "
            "names the row only when no scenario or tag does (`v1-e32-t25`)."
        ),
    )
    withheld_names: int = Field(
        ge=0,
        description="Scenario names two or more teams use, withheld for a school, team code or tournament.",
    )
    roles_without_card: tuple[RoleGap, ...] = Field(description="One per role of the kind, in role order.")
    unlisted_words: int = Field(
        ge=0,
        description=(
            "Scenario words two or more teams use under a position with the coach's list that the list does "
            "not hold (`v1-e32-t22`): counted for the dry run, never shown."
        ),
    )
    unlisted_words_withheld: int = Field(
        ge=0, description="Of those, the words holding a word of a caselist school, team code or tournament."
    )
    named_rows: tuple[NamedRows, ...] = Field(
        description="The impact rows each source names (`v1-e32-t25`), one per source in naming order."
    )
    rows_left_out: int = Field(ge=0, description="Impact rows no source names, left out and counted.")
    withheld_tags: int = Field(
        ge=0,
        description=(
            "Internal-link, impact and card-above tags that would have named a row, withheld for holding a "
            "word of a caselist school, team code or tournament; the next source named the row instead."
        ),
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.unlisted_words_withheld > self.unlisted_words:
            raise ValueError("unlisted words holding a caselist word are among the unlisted words")
        if self.unstructured_documents > self.documents:
            raise ValueError("unstructured documents are among the documents")
        if max(self.rows_with_scenario, self.rows_with_internal_link + self.rows_with_card_above) > (
            self.impact_rows
        ):
            raise ValueError("rows with a scenario or a lead-in are among the impact rows")
        if tuple(one.source for one in self.named_rows) != LEAD_IN_ORDER:
            raise ValueError("named rows are counted once per source, in naming order")
        if sum(one.rows for one in self.named_rows) + self.rows_left_out != self.impact_rows:
            raise ValueError("every impact row is named by one source or left out")
        if self.named_rows[0].rows != self.rows_with_scenario:
            raise ValueError("the rows a scenario names are the rows with a scenario")
        return self


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


class KritikalFamilyCount(DomainModel):
    """One K family named in the K-aff files' headings: a count of words, never a placement."""

    family_id: PositionId
    label: NonEmptyText
    files: int = Field(ge=1, description="Files of the K-aff rounds whose headings name it.")
    teams: int = Field(ge=1, description="Distinct teams of the K-aff rounds disclosing those files.")


class KritikalAffs(DomainModel):
    """report.md's kritikal affirmatives (`v1-e32-t17`, the PM's rulings of 2026-10-25)."""

    position_id: PositionId
    label: NonEmptyText
    rounds: int = Field(ge=0, description="Affirmative rounds assigned the K aff, by either method.")
    teams: int = Field(ge=0, description="Distinct teams of those rounds.")
    by_marker: int = Field(ge=0, description="Of the rounds, those a marker in their own file identifies.")
    by_carry: int = Field(ge=0, description="Of the rounds, those carried from the team's other rounds.")
    refused_by_advantage: int = Field(
        ge=0, description="Rounds the K aff was not carried into because their own file reads an advantage."
    )
    families: tuple[KritikalFamilyCount, ...] = Field(
        description="The K families the K-aff files' headings name, by files, then teams, then the config's "
        "order."
    )
    control_files: int = Field(
        ge=0, description="Files with a K-aff marker and no plan text in rounds another method identifies."
    )
    control_rounds: int = Field(ge=0, description="The rounds those files are disclosed in.")
    control_by_method: dict[AffMethod, int] = Field(
        default_factory=dict[AffMethod, int],
        description="Those rounds by the method that identified them: the TEAM_CARRY share is what a K-aff "
        "marker beating the team's carry would move.",
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.by_marker + self.by_carry != self.rounds:
            raise ValueError("every K-aff round is identified by its own marker or by carry")
        if self.control_rounds and not self.control_files:
            raise ValueError("a control round holds a marker file")
        return self


class TransitionPlans(DomainModel):
    """The method table's rows for plan texts under a transition label (`v1-e32-t24`, the PM's rulings of
    2026-10-26). The rounds they identify are counted by method with the others."""

    refused_kritikal_carry: int = Field(
        ge=0,
        description="Affirmative rounds the K aff was not carried into because their own file holds such a "
        "plan text naming a policy aff.",
    )
    control_rounds: int = Field(
        ge=0,
        description="Affirmative rounds another method identifies whose own file holds such a plan text "
        "naming another aff: kept as they are.",
    )
    control_by_method: dict[AffMethod, int] = Field(
        default_factory=dict[AffMethod, int], description="Those rounds by the method that identified them."
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if sum(self.control_by_method.values()) != self.control_rounds:
            raise ValueError("every control round has the method that identified it")
        return self


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
    chain_cards: tuple[ChainCard, ...] = Field(
        default=(), description="Each DA's and advantage's most-read card per chain role, in report order."
    )
    chain_coverage: tuple[ChainCoverage, ...] = Field(
        default=(), description="One per kind of :data:`IMPACT_KINDS` (`v1-e32-t14`)."
    )
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
    kritikal_affs: KritikalAffs | None = Field(
        default=None,
        description="`v1-e32-t17`'s kritikal affirmatives; None when the run read no K-aff markers.",
    )
    transition_plans: TransitionPlans | None = Field(
        default=None,
        description="`v1-e32-t24`'s method-table rows for plan texts under a transition label; None when the "
        "run read none.",
    )

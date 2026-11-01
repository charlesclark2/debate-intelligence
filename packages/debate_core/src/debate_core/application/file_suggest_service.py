"""FileSuggestService: a draft recipe from the landscape's most-read cards for a position (`v1-e33-t03`).

`debate-research files suggest --caselist <slug> --position <p>` is a thin wrapper over this. It writes
a recipe a coach starts from, never one to build as it stands: `status: draft`, so `files build`
refuses it until the coach marks it ready or builds it with `--allow-draft`.

## Where the cards come from

From the landscape's own counts, through its application layer and never from a published file: a
dry run of :class:`~debate_core.application.landscape_run.LandscapeRunService` (`v1-e32-t05`), which
classifies deterministically, calls no model and writes nothing but the plan-text and analytic-text
caches (`v1-e32-t30`), with `top_cards` set to the request's `--top`. Its report's top cards for the
position are the rows `top_cards.csv` reports: each an E31 cluster, ranked by the distinct teams
reading a copy of it under the position, then by cluster id. A row shows one card of the cluster,
and that card's exact fingerprint is the one the draft names.

## How the draft is laid out

* **One pocket**, the position's label.
* **Blocks by the commonest heading.** Each card goes under the block heading most of its cluster's
  copies sit under (the innermost heading over the card, normalized as the position matcher reads
  it, with the disclosing team's names taken out); ties go to the first in text order, and a card
  with no heading goes under the position's label. Blocks come in the order of their most-read card,
  and cards inside a block by rank, so the draft reads in the order of the read counts as far as its
  grouping allows.
* **Read counts as comments**, one above each card: its rank and how many teams read it.
* **No tag and no text of a card.** No tag override is written: a tag is the coach's to write. The
  comments hold counts; the headings are the ones the landscape reads.

## A counterplan's draft (`v1-e33-t11`)

A position the taxonomy marks as a counterplan (:attr:`~debate_core.domain.landscape.PositionKind.CP`)
gets three things more, and every other position's draft is as it was:

* **A slot for the counterplan's text.** Its first block opens with the analytic :data:`CP_TEXT_SLOT`,
  a placeholder for the coach to replace with the text the team reads. It is never a text from a team's
  file or the landscape's quoted CP texts. `files build` writes it as it stands, like any analytic, and
  the built file's quality report warns of it on its block (`v1-e33-t15`).
* **No other position's block.** A block whose heading the position matcher places under another
  position, read as it reads a heading directly over a card, is left out with its cards, which go
  nowhere else in the draft. A heading that places nothing stays. The result counts what was left out
  (:class:`OtherPositionsLeftOut`).
* **Except an affirmative-side one, marked (`v1-e33-t13`).** A block whose heading places an aff or an
  advantage (:data:`_AFFIRMATIVE_SIDE_KINDS`) stays, with :data:`CHECK_AGAINST_THE_PLAN` above it: in a
  CP file it is often the counterplan's solvency for that advantage. It keeps its cards in rank order
  and its place in the draft, by its most-read card, like any block that stays. A block any other kind
  places (a DA, another CP, a K, a T, a theory argument, or LD's and PF's kinds) is still left out. The
  result counts what was kept this way (:class:`AffirmativeSideKept`).
* **Blocks that depend on the plan, marked.** A block whose heading names a plank or mechanism of the
  plan gets the comment :data:`CHECK_AGAINST_THE_PLAN` above it, and stays. A heading names one when it
  holds, as whole words, an alias or tag keyword of one of the taxonomy's affirmatives (each is one plan,
  named by its mechanism), or opens with a plank label as `v1-e32-t16` reads one (`plank 2 ...`).

## How each card is pinned

To the occurrence the recipe resolver's own AUTO rule takes (`v1-e33-t01`, with `v1-e33-t03`'s
attributed-first amendment): an attributed occurrence first, then the latest, so a suggestion and a
build agree on the rule. The pin names the occurrence's caselist, source SHA-256 and element index,
and nothing more where that names one disclosure. Where the same bytes were disclosed by more than
one team, a pin of those three matches every disclosure, and the resolver refuses it; the pin then
names the chosen disclosure's side, then its tournament, then its round, and only when none of those
tells the disclosures apart its school and team code, exactly as disclosed, a step at a time until
the resolver takes it. That is personal data about students, which the data-use policy allows in the evidence
workspace, so a draft is never written inside a git working tree, as a built file is not. Every pin
is resolved once more before the draft is written; a card whose pin does not resolve is left out and
reported.

Nothing is logged.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

from debate_core.application.errors import DomainError
from debate_core.application.file_build_service import inside_a_git_working_tree
from debate_core.application.file_recipes import (
    RecipeErrorCode,
    RecipeResolver,
    ResolvedCard,
    ResolvedRecipe,
    load_recipe,
    recipe_hash,
)
from debate_core.application.landscape_run import LandscapeRunRequest, LandscapeRunResult, LandscapeRunService
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.parsed_store import OPENEV_STORE, ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.arguments.landscape.analytic_texts import plank_words
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, tag_words
from debate_core.domain.caselist import Event, Side, sides_for_event
from debate_core.domain.file_recipe import HEADING_MAX_LENGTH, FileRecipe, RecipeStatus
from debate_core.domain.landscape import Position, PositionKind, PositionSide, Taxonomy
from debate_core.domain.landscape_classification import ItemKind, section_item_id
from debate_core.domain.landscape_report import LandscapeCard, TopCard
from debate_core.evidence.file_checks.placeholders import CP_TEXT_SLOT
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "CHECK_AGAINST_THE_AFFIRMATIVE",
    "CHECK_AGAINST_THE_PLAN",
    "AffirmativeSideKept",
    "CP_TEXT_SLOT",
    "RECIPES_DIRECTORY",
    "LeftOut",
    "FileSuggestService",
    "OtherPositionsLeftOut",
    "SuggestRefused",
    "SuggestRequest",
    "SuggestResult",
    "SuggestedCard",
]

RECIPES_DIRECTORY: Final = "recipes"
"""Under the files directory: where a draft goes by default, one directory per topic."""


CHECK_AGAINST_THE_PLAN: Final = (
    "# Check this block against the affirmative's plan: its heading names a plank or mechanism of a plan."
)
"""The comment above a counterplan draft's block whose heading names a plank or mechanism of the plan."""

CHECK_AGAINST_THE_AFFIRMATIVE: Final = (
    "# Check this block against the affirmative's plan: its heading names an affirmative or one of its "
    "advantages."
)
"""The comment above a counterplan draft's block whose heading places an aff or an advantage (`v1-e33-t13`),
and names no plank or mechanism of the plan (`v1-e33-t14`)."""

#: The disclosure fields a pin adds, a step at a time and the least personal first, while its key
#: matches more than one disclosure: a school and team code only when nothing else tells them apart.
_NARROWING_STEPS: Final = (("side",), ("tournament",), ("round",), ("school", "team_code"))
_NARROWING: Final = tuple(name for step in _NARROWING_STEPS for name in step)

#: The kinds of an affirmative-side position: a counterplan's draft keeps, marked, a block one of them
#: places, and leaves out a block any other kind places (`v1-e33-t13`).
_AFFIRMATIVE_SIDE_KINDS: Final = frozenset({PositionKind.AFF, PositionKind.ADVANTAGE})


class SuggestRefused(DomainError):
    """The request names a position, a side or a place the draft cannot be written for.

    `known` is the positions the taxonomy has, when the position is unknown.
    """

    def __init__(self, message: str, *, known: Sequence[str] = (), hint: str | None = None) -> None:
        super().__init__(message)
        self.known: tuple[str, ...] = tuple(known)
        self.hint = hint


@dataclass(frozen=True, slots=True)
class SuggestRequest:
    caselist: str
    position: str
    side: Side | None = None
    """The file's side; None for the position's own, which a position both sides read needs."""
    snapshot: date | None = None
    """The weekly snapshot the landscape counts through; None for the newest."""
    top: int = 10
    out: Path | None = None
    """Where to write the draft; None for `<files dir>/recipes/<topic>/<position>-<side>-draft.yaml`."""


@dataclass(frozen=True, slots=True)
class SuggestedCard:
    """One card in the draft: where it ranks, how many teams read it, its block and what its pin names."""

    rank: int
    teams_reading: int
    fingerprint: str
    block: str = field(repr=False)
    pin_fields: tuple[str, ...]
    """The pin's keys beyond its caselist, source and element index: what made it one disclosure."""


@dataclass(frozen=True, slots=True)
class LeftOut:
    """A most-read card the draft does not hold, and why: an error code, never card text."""

    rank: int
    fingerprint: str
    reason: str


@dataclass(frozen=True, slots=True)
class OtherPositionsLeftOut:
    """A counterplan draft's blocks whose heading the position matcher places under another position.

    Left out with their cards, which go nowhere else in the draft.
    """

    blocks: int
    cards: int


@dataclass(frozen=True, slots=True)
class AffirmativeSideKept:
    """A counterplan draft's blocks whose heading the position matcher places under an aff or an advantage.

    Kept with their cards, each with :data:`CHECK_AGAINST_THE_PLAN` above it (`v1-e33-t13`).
    """

    blocks: int
    cards: int


@dataclass(frozen=True, slots=True)
class SuggestResult:
    path: Path
    caselist: str
    snapshot: date
    topic: str
    position: str
    side: Side
    recipe_hash: str
    cards: tuple[SuggestedCard, ...]
    left_out: tuple[LeftOut, ...] = ()
    other_positions: OtherPositionsLeftOut | None = None
    """What a counterplan's draft left out as another position's; None for any other position's draft."""
    affirmative_side_kept: AffirmativeSideKept | None = None
    """What a counterplan's draft kept under an aff's or advantage's heading; None for any other draft."""
    text: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class _Ranked:
    row: TopCard
    fingerprint: str
    block: str


class FileSuggestService:
    """Writes a draft recipe from a landscape's most-read cards for one position.

    `files_dir` is where drafts go by default (`<files_dir>/recipes/<topic>/`). The parsed store,
    caselist records and suppression list are the recipe resolver's, so a draft is pinned as a build
    will resolve it; `parser_version` is the running parser's.
    """

    def __init__(
        self,
        *,
        landscape: LandscapeRunService,
        parsed_store: ParsedStore,
        caselists: CaselistRepository,
        suppression: SuppressionList,
        parser_version: str,
        files_dir: Path,
    ) -> None:
        self._landscape = landscape
        self._files_dir = files_dir
        self._resolver = RecipeResolver(
            parsed_store=parsed_store,
            caselists=caselists,
            suppression=suppression,
            parser_version=parser_version,
        )

    async def suggest(self, request: SuggestRequest) -> SuggestResult:
        if request.top < 1:
            raise SuggestRefused(f"--top is at least 1; got {request.top}")
        run = await self._landscape.run(
            LandscapeRunRequest(
                caselist=request.caselist, snapshot=request.snapshot, dry_run=True, top_cards=request.top
            )
        )
        position, event, side = _position_and_side(run, request)
        ranked = _ranked(run, position)
        if not ranked:
            raise SuggestRefused(
                f"no card of {position.id} was read in {request.caselist} through "
                f"{run.snapshot.isoformat()}, so there is nothing to suggest",
                hint="Name a position a team read: `landscape report` lists them in positions.csv.",
            )
        counterplan = position.kind is PositionKind.CP
        other_positions: OtherPositionsLeftOut | None = None
        affirmative_side: frozenset[str] = frozenset()
        if counterplan:
            ranked, other_positions, affirmative_side = _without_other_positions(run, position, ranked)
            if not ranked:
                raise SuggestRefused(
                    f"each of the most-read card(s) of {position.id} sits in a block whose heading places "
                    "another position, so there is nothing to suggest",
                    hint="Ask for more with --top, or start the file from the counterplan's own blocks.",
                )
        path = self._draft_path(request, run.topic_id, position.id, side)
        draft = _recipe(run, position, event, side, [{"fingerprint": one.fingerprint} for one in ranked])
        resolved = await self._resolver.resolve(draft)
        chosen = {card.fingerprint: card for card in resolved.cards}
        left_out = [
            LeftOut(one.row.rank, one.fingerprint, _error_at(resolved, index) or "UNRESOLVED")
            for index, one in enumerate(ranked)
            if one.fingerprint not in chosen
        ]
        kept = [one for one in ranked if one.fingerprint in chosen]
        pins = {one.fingerprint: _pin(chosen[one.fingerprint], steps=0) for one in kept}
        still = await self._mismatched(run, position, event, side, kept, pins)
        for steps in range(1, len(_NARROWING_STEPS) + 1):
            if not still:
                break
            for fingerprint in still:
                pins[fingerprint] = _pin(chosen[fingerprint], steps=steps)
            still = await self._mismatched(run, position, event, side, kept, pins)
        left_out += [
            LeftOut(one.row.rank, one.fingerprint, str(RecipeErrorCode.PIN_MISMATCH))
            for one in kept
            if one.fingerprint in still
        ]
        kept = [one for one in kept if one.fingerprint not in still]
        if not kept:
            raise SuggestRefused(
                f"none of the {len(ranked)} most-read card(s) of {position.id} resolves to an occurrence a "
                "recipe can use",
                hint="Each was stopped by the removal suppression list or a hold, or its pin did not "
                "resolve.",
            )
        text = _render(
            run,
            position,
            event,
            side,
            kept,
            pins,
            counterplan=counterplan,
            naming_the_plan=_naming_the_plan(run, kept) if counterplan else frozenset(),
            affirmative_side=affirmative_side,
        )
        loaded = load_recipe(text)
        if loaded.recipe is None:
            raise AssertionError(f"files suggest wrote a recipe that does not load: {loaded.errors}")
        _write_new(path, text)
        return SuggestResult(
            path=path,
            caselist=request.caselist,
            snapshot=run.snapshot,
            topic=run.topic_id,
            position=position.id,
            side=side,
            recipe_hash=recipe_hash(loaded.recipe),
            cards=tuple(
                SuggestedCard(
                    rank=one.row.rank,
                    teams_reading=one.row.teams_reading,
                    fingerprint=one.fingerprint,
                    block=one.block,
                    pin_fields=tuple(
                        key for key in pins[one.fingerprint] if key in ("snapshot", *_NARROWING)
                    ),
                )
                for one in _in_file_order(kept)
            ),
            left_out=tuple(sorted(left_out, key=lambda one: one.rank)),
            other_positions=other_positions,
            affirmative_side_kept=_affirmative_side_kept(kept, affirmative_side) if counterplan else None,
            text=text,
        )

    async def _mismatched(
        self,
        run: LandscapeRunResult,
        position: Position,
        event: Event,
        side: Side,
        kept: Sequence[_Ranked],
        pins: Mapping[str, Mapping[str, Any]],
    ) -> set[str]:
        """The fingerprints whose pin, as it stands, the resolver refuses."""
        items = [{"fingerprint": one.fingerprint, "pin": dict(pins[one.fingerprint])} for one in kept]
        resolved = await self._resolver.resolve(_recipe(run, position, event, side, items))
        refused: set[str] = set()
        for index, one in enumerate(kept):
            if _error_at(resolved, index) is not None:
                refused.add(one.fingerprint)
        return refused

    @property
    def _recipes_root(self) -> Path:
        return self._files_dir / RECIPES_DIRECTORY

    def _draft_path(self, request: SuggestRequest, topic: str, position: str, side: Side) -> Path:
        path = (
            request.out.expanduser().resolve()
            if request.out is not None
            else self._recipes_root / topic / f"{position}-{side.value.lower()}-draft.yaml"
        )
        if inside_a_git_working_tree(path.parent):
            raise SuggestRefused(
                f"{path} is inside a git working tree; a draft's pins can name a school and a team code as "
                "disclosed, and those are never committed",
                hint=f"Write it outside any checkout, or leave --out out for {self._recipes_root}.",
            )
        if path.exists():
            raise SuggestRefused(
                f"{path} is already there; a draft is never written over, since it may hold your edits",
                hint="Move or rename it, or name another file with --out.",
            )
        return path


def _position_and_side(run: LandscapeRunResult, request: SuggestRequest) -> tuple[Position, Event, Side]:
    taxonomy = run.taxonomy
    if taxonomy is None or taxonomy.event is None:
        raise AssertionError("a landscape run reports the taxonomy it counted under")
    active = sorted(one.id for one in taxonomy.positions if not one.deprecated)
    try:
        position = taxonomy.resolve(request.position)
    except KeyError:
        raise SuggestRefused(
            f"{request.position} is not a position of {taxonomy.topic_id} {taxonomy.taxonomy_version}",
            known=active,
        ) from None
    event = taxonomy.event
    legal = sides_for_event(event) - {Side.UNKNOWN}
    if request.side is not None:
        if request.side not in legal:
            names = " or ".join(sorted(str(one) for one in legal))
            raise SuggestRefused(f"a {event} file is {names}", known=sorted(str(one) for one in legal))
        return position, event, request.side
    if position.side is PositionSide.BOTH:
        raise SuggestRefused(
            f"both sides read {position.id}, so the draft needs a side: pass --side",
            known=sorted(str(one) for one in legal),
        )
    affirmative = position.side is PositionSide.AFF
    if event is Event.PF:
        return position, event, Side.PRO if affirmative else Side.CON
    return position, event, Side.AFF if affirmative else Side.NEG


def _ranked(run: LandscapeRunResult, position: Position) -> list[_Ranked]:
    """The position's top cards in rank order, each with its card's fingerprint and its block heading."""
    by_key = {(card.source_sha256, card.element_index): card for card in run.cards}
    clusters: dict[str, list[LandscapeCard]] = {}
    for card in run.cards:
        clusters.setdefault(card.cluster_id, []).append(card)
    ranked: list[_Ranked] = []
    seen: set[str] = set()
    for row in sorted(
        (one for one in run.report.top_cards if one.position_id == position.id), key=lambda one: one.rank
    ):
        shown = by_key.get((row.source_object_key.rsplit("/", 1)[-1], row.element_index))
        if shown is None or shown.exact_fingerprint in seen:
            continue
        seen.add(shown.exact_fingerprint)
        ranked.append(
            _Ranked(row, shown.exact_fingerprint, _commonest_heading(clusters[row.fingerprint], position))
        )
    return ranked


def _commonest_heading(copies: Sequence[LandscapeCard], position: Position) -> str:
    """The innermost heading most copies sit under; the first in text order on a tie; else the label."""
    counts = Counter(card.headings[-1] for card in copies if card.headings)
    if not counts:
        return position.label
    heading = min(counts, key=lambda one: (-counts[one], one))
    return heading[:HEADING_MAX_LENGTH]


def _without_other_positions(
    run: LandscapeRunResult, position: Position, ranked: Sequence[_Ranked]
) -> tuple[list[_Ranked], OtherPositionsLeftOut, frozenset[str]]:
    """`ranked` without the blocks whose heading the position matcher places under another position.

    A block an aff or an advantage places stays: it is in the headings returned, for the comment above it.
    """
    taxonomy = run.taxonomy
    if taxonomy is None or run.overrides is None:
        raise AssertionError("a landscape run reports the taxonomy and overrides it placed under")
    matcher = PositionMatcher(taxonomy, run.overrides)
    elsewhere: dict[str, PositionKind] = {}
    for one in ranked:
        placed = matcher.place(_directly_under(one)).position_id
        if placed not in (None, position.id):
            elsewhere[one.block] = taxonomy.position(placed).kind
    affirmative_side = frozenset(
        block for block, kind in elsewhere.items() if kind in _AFFIRMATIVE_SIDE_KINDS
    )
    left_out = elsewhere.keys() - affirmative_side
    kept = [one for one in ranked if one.block not in left_out]
    return kept, OtherPositionsLeftOut(blocks=len(left_out), cards=len(ranked) - len(kept)), affirmative_side


def _affirmative_side_kept(kept: Sequence[_Ranked], affirmative_side: frozenset[str]) -> AffirmativeSideKept:
    """How many of the draft's blocks, and their cards, are under a heading an aff or an advantage places."""
    held = [one for one in kept if one.block in affirmative_side]
    return AffirmativeSideKept(blocks=len({one.block for one in held}), cards=len(held))


def _directly_under(one: _Ranked) -> MatchItem:
    """A section under `one`'s block heading alone, as the matcher reads a heading directly over a card."""
    source = one.row.source_object_key.rsplit("/", 1)[-1]
    return MatchItem(
        item_id=section_item_id(source, (one.block,)),
        kind=ItemKind.SECTION,
        source_sha256=source,
        first_element_index=None,
        headings=(NormalizedHeading(text=one.block, answer=False),),
        tag=None,
    )


def _naming_the_plan(run: LandscapeRunResult, kept: Sequence[_Ranked]) -> frozenset[str]:
    """The block headings of `kept` that name a plank or mechanism of the plan."""
    if run.taxonomy is None:
        raise AssertionError("a landscape run reports the taxonomy it counted under")
    words = _plan_words(run.taxonomy)
    return frozenset(
        one.block
        for one in kept
        if plank_words(one.block) != one.block or any(f" {phrase} " in f" {one.block} " for phrase in words)
    )


def _plan_words(taxonomy: Taxonomy) -> frozenset[str]:
    """Every active affirmative's aliases and tag keywords, as words: the mechanisms a plan is named by."""
    return frozenset(
        words
        for one in taxonomy.active_positions
        if one.kind is PositionKind.AFF
        for words in (*one.aliases, *map(tag_words, one.tag_keywords))
        if words
    )


def _in_file_order(ranked: Sequence[_Ranked]) -> list[_Ranked]:
    """Blocks in the order of their most-read card, and cards in a block by rank."""
    first_rank: dict[str, int] = {}
    for one in ranked:
        first_rank.setdefault(one.block, one.row.rank)
    return sorted(ranked, key=lambda one: (first_rank[one.block], one.row.rank))


def _pin(card: ResolvedCard, *, steps: int) -> dict[str, Any]:
    """The pin to `card`'s occurrence: its key, a camp release, and the first `steps` narrowing steps."""
    row = card.occurrence
    pin: dict[str, Any] = {
        "caselist": row.caselist,
        "source_sha256": row.source_sha256,
        "element_index": row.first_element_index,
    }
    if row.caselist == OPENEV_STORE:
        pin["snapshot"] = row.snapshot
    disclosure = card.disclosure
    if steps and disclosure is not None:
        given = {
            "side": str(disclosure.side) if disclosure.side is not Side.UNKNOWN else None,
            "school": disclosure.school,
            "team_code": disclosure.team_code,
            "tournament": disclosure.tournament,
            "round": disclosure.round_label.raw if disclosure.round_label is not None else None,
        }
        wanted = {name for step in _NARROWING_STEPS[:steps] for name in step}
        pin.update({key: value for key, value in given.items() if key in wanted and value is not None})
    return pin


def _error_at(resolved: ResolvedRecipe, index: int) -> str | None:
    """The code of the resolver's error at the draft's `index`th item, or None when it resolved."""
    prefix = f"structure[0].blocks[0].items[{index}]"
    for error in resolved.errors:
        if error.path == prefix or error.path.startswith(f"{prefix}."):
            return str(error.code)
    return None


def _recipe(
    run: LandscapeRunResult,
    position: Position,
    event: Event,
    side: Side,
    items: Sequence[Mapping[str, Any]],
) -> FileRecipe:
    """A one-block draft of `items`, for the resolver: what each card resolves to, item by item."""
    return FileRecipe.model_validate(
        {
            "schema_version": 1,
            "title": _title(position),
            "topic": run.topic_id,
            "format": str(event),
            "caselist": run.caselist,
            "position": position.id,
            "side": str(side),
            "fingerprint_version": FINGERPRINT_VERSION,
            "status": str(RecipeStatus.DRAFT),
            "structure": [
                {"pocket": position.label, "blocks": [{"block": position.label, "items": list(items)}]}
            ],
        }
    )


def _title(position: Position) -> str:
    return f"{position.label}: most-read cards"[:HEADING_MAX_LENGTH]


def _render(
    run: LandscapeRunResult,
    position: Position,
    event: Event,
    side: Side,
    kept: Sequence[_Ranked],
    pins: Mapping[str, Mapping[str, Any]],
    *,
    counterplan: bool,
    naming_the_plan: frozenset[str],
    affirmative_side: frozenset[str],
) -> str:
    """The draft's YAML, written by hand so each card carries its read count as a comment.

    A counterplan's first block opens with :data:`CP_TEXT_SLOT`, and each block in `marked` (one naming
    the plan or one an aff or an advantage places) has :data:`CHECK_AGAINST_THE_PLAN` above it.
    """
    through = run.snapshot.isoformat()
    lines = [
        f"# Draft recipe from the {run.caselist} landscape through {through}: the {len(kept)} most-read",
        f"# card(s) of {position.id}, by the number of teams that read each. Each card is pinned to the",
        "# occurrence a build would choose. Edit the headings and order, add your own cards and analytics,",
        "# write your own tags, then set status: ready. Written by `debate-research files suggest`.",
        "schema_version: 1",
        f"title: {_quoted(_title(position))}",
        f"topic: {run.topic_id}",
        f"format: {event}",
        f"caselist: {run.caselist}",
        f"position: {position.id}",
        f"side: {side}",
        f"fingerprint_version: {FINGERPRINT_VERSION}",
        f"status: {RecipeStatus.DRAFT}",
        "structure:",
        f"  - pocket: {_quoted(position.label)}",
        "    blocks:",
    ]
    block: str | None = None
    for one in _in_file_order(kept):
        if one.block != block:
            first = block is None
            block = one.block
            if block in naming_the_plan | affirmative_side:  # SKELETON: one comment for both
                lines.append(f"      {CHECK_AGAINST_THE_PLAN}")
            lines += [f"      - block: {_quoted(block)}", "        items:"]
            if counterplan and first:
                lines += [
                    "          # The counterplan's text: replace the placeholder with the text you read.",
                    f"          - analytic: {_quoted(CP_TEXT_SLOT)}",
                ]
        teams = one.row.teams_reading
        read_by = f"{teams} team{'' if teams == 1 else 's'}"
        lines += [
            f"          # rank {one.row.rank}: read by {read_by} through {through}",
            f"          - fingerprint: {one.fingerprint}",
            "            pin:",
        ]
        for key, value in pins[one.fingerprint].items():
            lines.append(f"              {key}: {value if isinstance(value, int) else _quoted(str(value))}")
    return "\n".join(lines) + "\n"


def _quoted(text: str) -> str:
    """A YAML double-quoted scalar: JSON's string form is one, whatever the text holds."""
    return json.dumps(text, ensure_ascii=False)


def _write_new(path: Path, text: str) -> None:
    """Write the draft beside its final name and link it in, refusing a file that appeared meanwhile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = path.with_name(f".{path.name}.incoming")
    incoming.write_text(text, encoding="utf-8")
    try:
        os.link(incoming, path)
    except FileExistsError:
        raise SuggestRefused(f"{path} is already there; a draft is never written over") from None
    finally:
        incoming.unlink()

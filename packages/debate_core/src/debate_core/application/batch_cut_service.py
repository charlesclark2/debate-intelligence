"""BatchCutService: a ranked search in, up to N VERIFIED cards out, and a line for every result it tried.

`debate-research search ... --auto-cut N` (`v1-e08-t06`, architecture proposal §11) runs this after the
search. It composes what `cut` already composes, unchanged:
:class:`~debate_core.application.article_fetch.ArticleFetch` retrieves each result's URL (E04) and
:class:`~debate_core.application.card_service.CardService` cuts, cites, verifies and saves a card from
the snapshot (`v1-e06-t02`). What is here is the walk:

1. **In rank order.** The candidates are the search's ranked results (:func:`batch_candidates`), and a
   candidate is started only when the cards already VERIFIED plus the cuts still running are fewer
   than N, so a run never cuts more than it needs when every cut succeeds. Which candidates are cut
   is therefore the same whatever order the cuts finish in: candidate *k* is cut exactly when fewer
   than N of the candidates before it ended VERIFIED (unless the budget stopped the run first).
2. **Skipping what is known to be inaccessible.** A result whose Article an earlier retrieval
   recorded as PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND or UNSUPPORTED_TYPE
   (:data:`KNOWN_INACCESSIBLE`) is not fetched again; a result the retrieval finds is not ACCESSIBLE
   (E04's classifier, robots, the fetcher) is not cut. Each is a SKIPPED entry with its access
   status and the reason, and the walk goes on to the next candidate. ERROR is not on the list: a
   failed fetch may answer next time. No access check of its own is made here.
3. **At most `concurrency` cuts at once.** Each attempt (its fetch and its cut) holds one place of an
   :class:`asyncio.Semaphore`. Per-host pacing is the fetcher's (`http.per_host_interval_seconds`)
   and every retry is the fetcher's or the router's: nothing here retries anything.
4. **Until N cards are VERIFIED, the candidates run out, or the budget stops it.** A model call the
   budget guard refuses (:class:`~debate_core.application.budget.BudgetExceededError`, the guard of
   `v1-e05-t07`, which `--max-cost` sets) ends the run: no candidate is started after it, the cuts
   already running finish, and their cards are kept. The candidate whose call was refused is a
   BUDGET_EXCEEDED entry. A call the guard cannot price while a limit is set
   (:class:`~debate_core.application.budget.UnpricedModelError`) ends the run the same way, with that
   code: an unpriced call is never let past `--max-cost` as though it were free, and the next cut's
   would be refused too.

## What counts

Only the evidence verifier sets VERIFIED
(:class:`~debate_core.application.evidence_verifier.EvidenceVerifier`).
A card it did not pass is an UNVERIFIED entry: saved, as every cut card is, and returned apart from
the VERIFIED ones (:attr:`BatchReport.unverified`), never counted toward N. A failure that is not a
verdict about a card (a model provider that did not answer, a damaged snapshot) is a FAILED entry
with its error code, and the walk goes on. An exception that is not a
:class:`~debate_core.application.errors.DomainError` is a bug, and propagates.

## Cost

Each entry carries what its model calls cost, read from the usage log as the calls are recorded
(:class:`SpendTally`): every real call is recorded in the task that made it, so a cut's cost is its
own even with others running beside it. A replayed or fake answer costs nothing and records nothing,
so its entry says 0. An entry with a call the pricing file does not price says `None`, not 0.

## What an entry never holds

Evidence text, a tag, a cite or a model's words: ranks, URLs, the result's title, statuses, codes,
ids, the classifier's reason (status codes and marker ids, `v1-e04-t03`) and the verifier's details,
which hold none either.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol

from debate_core.application.article_fetch import SOURCE_NOT_ACCESSIBLE_CODE, FetchReport
from debate_core.application.budget import BudgetExceededError, UnpricedModelError
from debate_core.application.card_types import CutRequest, CutResult
from debate_core.application.errors import DomainError, error_code_of, reported_error_message
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.domain import AccessStatus, Ulid, VerificationStatus
from debate_core.domain.argument_taxonomy import ArgumentTaxonomy
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.search import SearchExpansion

__all__ = [
    "BUDGET_EXCEEDED_CODE",
    "KNOWN_INACCESSIBLE",
    "BatchCandidate",
    "BatchCutRequest",
    "BatchCutService",
    "BatchEntry",
    "BatchEntryStatus",
    "BatchNeed",
    "BatchReport",
    "BatchStopReason",
    "Cutting",
    "Retrieving",
    "SpendReading",
    "SpendTally",
    "batch_candidates",
    "batch_need",
]

KNOWN_INACCESSIBLE: Final = frozenset(
    {
        AccessStatus.PAYWALLED,
        AccessStatus.BLOCKED,
        AccessStatus.ROBOTS_DISALLOWED,
        AccessStatus.NOT_FOUND,
        AccessStatus.UNSUPPORTED_TYPE,
    }
)
"""The statuses an earlier retrieval records that make a result not worth fetching again in a batch."""

BUDGET_EXCEEDED_CODE: Final = "BUDGET_EXCEEDED"
"""The code of an entry whose model call the budget guard refused, and of the stop it caused."""


class BatchEntryStatus(StrEnum):
    """What became of one candidate. Values are stable: they are written into report.json.

    A cut card's verdict is not one of these: it is the card's own
    :class:`~debate_core.domain.VerificationStatus`, which only the verifier sets, read off the card
    (:attr:`BatchEntry.card_status`). This module never names a verification status itself.
    """

    CUT = "CUT"
    """A card was cut and saved; :attr:`BatchEntry.card_status` is what the verifier made of it."""
    SKIPPED = "SKIPPED"
    """The source is not ACCESSIBLE, as recorded earlier or as the retrieval found: no card was cut."""
    FAILED = "FAILED"
    """The cut could not run (a provider that did not answer, a damaged snapshot): no card was saved."""
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    """The budget guard refused one of its model calls, over the limit or unpriced, which ended the run:
    no card was saved."""


class BatchStopReason(StrEnum):
    """Why the run ended. Values are stable: they are written into report.json."""

    COMPLETE = "COMPLETE"
    """N cards are VERIFIED."""
    CANDIDATES_EXHAUSTED = "CANDIDATES_EXHAUSTED"
    """Every candidate was tried, and fewer than N cards are VERIFIED."""
    ALL_REMAINING_INACCESSIBLE = "ALL_REMAINING_INACCESSIBLE"
    """Every candidate was tried, fewer than N cards are VERIFIED, and every other one was SKIPPED."""
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    """The budget guard refused a model call before N cards were VERIFIED."""


class Retrieving(Protocol):
    """Retrieves one URL into a snapshot, or says why not: `ArticleFetch`."""

    async def retrieve(self, url: str) -> FetchReport: ...


class Cutting(Protocol):
    """Cuts, verifies and saves one card from a snapshot: `CardService`."""

    async def cut_card(self, request: CutRequest) -> CutResult: ...


@dataclass(frozen=True, slots=True)
class BatchCandidate:
    """One ranked result a batch may cut: its rank, its URL, and what an earlier retrieval recorded."""

    rank: int
    url: str
    title: str
    known_access: AccessStatus = AccessStatus.UNKNOWN
    """The status on the result's Article: UNKNOWN for a source no retrieval has read."""
    need: BatchNeed | None = None
    """What this candidate's card is cut for, when it is not the request's: a daily digest's results
    come from searches for different arguments and needs (v1-e08-t07). None takes the request's."""


def batch_candidates(outcome: SearchOutcome) -> tuple[BatchCandidate, ...]:
    """The search's ranked results as candidates, in rank order, each with its Article's access status.

    The URL is the result's own (`url` in `search --json`), which is what `cut` would be given.
    """
    access = {
        result.rank: article.access_status
        for result, article in zip(outcome.results, outcome.articles, strict=True)
    }
    return tuple(
        BatchCandidate(
            rank=ranked.rank,
            url=ranked.candidate.url,
            title=ranked.candidate.title,
            known_access=access.get(ranked.rank, AccessStatus.UNKNOWN),
        )
        for ranked in sorted(outcome.ranked_candidates, key=lambda ranked: ranked.rank)
    )


@dataclass(frozen=True, slots=True)
class BatchNeed:
    """What every card of a batch is cut for, and the block heading the bundle files them under."""

    argument: str
    """The argument, as the model is told it: the taxonomy's label, `Politics DA`."""
    need: str
    """The need within it: the need's label and description, for the query searched."""
    heading: str
    """The bundle's block heading: `Politics DA — Link: health insurance`."""


def batch_need(taxonomy: ArgumentTaxonomy, expansion: SearchExpansion, query: str) -> BatchNeed:
    """The research need of a search expanded for an argument and need, in the taxonomy's own words."""
    argument = taxonomy.find_argument(expansion.argument)
    if argument is None:
        raise ValueError(
            f"the taxonomy has no argument {expansion.argument!r}; the search was expanded by another"
        )
    need = taxonomy.family_of(argument).need(expansion.need)
    return BatchNeed(
        argument=argument.label,
        need=f"{need.label} for {query}: {need.description}",
        heading=f"{argument.label} — {need.label}: {query}",
    )


@dataclass(frozen=True, slots=True)
class BatchCutRequest:
    """Cut until `wanted` cards are VERIFIED from `candidates`, for `need`, at most `concurrency` at once."""

    candidates: Sequence[BatchCandidate]
    wanted: int
    need: BatchNeed
    owner_id: Ulid
    concurrency: int = 1
    format_profile: str = DEFAULT_FORMAT_PROFILE

    def __post_init__(self) -> None:
        if self.wanted < 1:
            raise ValueError(f"a batch cuts at least one card; {self.wanted!r} asks for none")
        if self.concurrency < 1:
            raise ValueError(f"a batch runs at least one cut at a time; {self.concurrency!r} runs none")


@dataclass(frozen=True, slots=True)
class BatchEntry:
    """One candidate a batch tried, and what became of it. Never evidence text, a tag or a cite."""

    rank: int
    url: str
    title: str
    status: BatchEntryStatus
    card_status: VerificationStatus | None
    """For a CUT entry, the saved card's status as the verifier set it; None for every other entry."""
    access_status: AccessStatus | None
    """The source's status: as the retrieval found it, as recorded for a source not fetched again, or
    None when the retrieval itself failed."""
    fetched: bool
    """Whether this run asked the publisher (False for a stored snapshot reused, or a source skipped)."""
    reasons: tuple[str, ...] = ()
    """Codes a program reads: the card's failure codes, `SOURCE_NOT_ACCESSIBLE`, an error's code."""
    details: tuple[str, ...] = ()
    """Sentences for people: the classifier's reason, each failure's detail, an error's message."""
    card_id: Ulid | None = None
    snapshot_id: Ulid | None = None
    cost_usd: float | None = 0.0
    """What its model calls cost at the pricing file's prices; None when one of them is not priced."""
    result: CutResult | None = field(default=None, repr=False, compare=False)
    """The cut, for a CUT entry: what the bundle is rendered from."""

    @property
    def verdict(self) -> str:
        """What a person reads: a CUT entry's card status, else the entry's own status."""
        return self.card_status.value if self.card_status is not None else self.status.value

    @property
    def is_verified(self) -> bool:
        """Whether a card was cut and the verifier passed it."""
        return self.card_status is VerificationStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class BatchReport:
    """What a batch did: an entry per candidate it tried, in rank order, and why it ended."""

    wanted: int
    entries: tuple[BatchEntry, ...]
    stop_reason: BatchStopReason

    @property
    def verified(self) -> tuple[CutResult, ...]:
        """The VERIFIED cards, in rank order: the bundle's block."""
        return tuple(e.result for e in self.entries if e.is_verified and e.result is not None)

    @property
    def unverified(self) -> tuple[CutResult, ...]:
        """The UNVERIFIED cards, in rank order: only ever the bundle's bannered section."""
        return tuple(e.result for e in self.entries if e.result is not None and not e.is_verified)

    @property
    def complete(self) -> bool:
        """Whether `wanted` cards are VERIFIED."""
        return len(self.verified) >= self.wanted

    @property
    def cost_usd(self) -> float | None:
        """What every entry's model calls cost together; None when any entry's cost is unknown."""
        costs = [entry.cost_usd for entry in self.entries]
        return None if any(cost is None for cost in costs) else sum(cost or 0.0 for cost in costs)


# ------------------------------------------------------------------------------------------------
# Cost, per task
# ------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class SpendReading:
    """What the model calls made inside one :meth:`SpendTally.measuring` block have cost so far."""

    usd: float = 0.0
    unpriced_calls: int = 0

    @property
    def cost_usd(self) -> float | None:
        """`usd`, or None once a call the pricing file does not price was made."""
        return None if self.unpriced_calls else self.usd


_READING: ContextVar[SpendReading | None] = ContextVar("batch_cut_spend_reading", default=None)


class SpendTally:
    """Adds each recorded model call's cost to the reading of the block, and the task, that made it.

    The usage log calls :meth:`record` for every real call it appends (the composition root wires
    it); a call made outside any :meth:`measuring` block is recorded nowhere here. Each asyncio task
    has its own context, so two cuts running at once read only their own calls.
    """

    def record(self, usd: float | None) -> None:
        """Count one call's cost against the current block, if there is one; None is an unpriced call."""
        reading = _READING.get()
        if reading is None:
            return
        if usd is None:
            reading.unpriced_calls += 1
        else:
            reading.usd += usd

    @contextmanager
    def measuring(self) -> Generator[SpendReading]:
        """A reading of every call recorded in this task until the block ends."""
        reading = SpendReading()
        token = _READING.set(reading)
        try:
            yield reading
        finally:
            _READING.reset(token)


# ------------------------------------------------------------------------------------------------
# The walk
# ------------------------------------------------------------------------------------------------


class BatchCutService:
    """Cuts a search's results in rank order until N cards are VERIFIED. Holds no state between runs."""

    def __init__(self, *, fetching: Retrieving, cutting: Cutting, spend: SpendTally | None = None) -> None:
        self._fetching = fetching
        self._cutting = cutting
        self._spend = spend or SpendTally()

    async def cut(self, request: BatchCutRequest) -> BatchReport:
        """Walk `request.candidates`; see the module docstring. Raises only what is not a DomainError."""
        walk = _Walk(request)
        async with asyncio.TaskGroup() as group:
            for candidate in request.candidates:
                if not await walk.room_for_another():
                    break
                if candidate.known_access in KNOWN_INACCESSIBLE:
                    walk.add(_known_inaccessible(candidate))
                    continue
                walk.started()
                group.create_task(self._attempt(candidate, request, walk))
        return walk.report()

    async def _attempt(self, candidate: BatchCandidate, request: BatchCutRequest, walk: _Walk) -> None:
        """Fetch and cut one candidate under the semaphore, and add its entry; never raises a DomainError."""
        entry: BatchEntry | None = None
        try:
            async with walk.semaphore:
                if walk.stopped:
                    return
                with self._spend.measuring() as reading:
                    entry = await self._fetch_and_cut(candidate, request, reading)
        finally:
            await walk.finished(entry)

    async def _fetch_and_cut(
        self, candidate: BatchCandidate, request: BatchCutRequest, reading: SpendReading
    ) -> BatchEntry:
        report: FetchReport | None = None
        need = candidate.need or request.need
        try:
            report = await self._fetching.retrieve(candidate.url)
            # ArticleFetch gives a snapshot only for an ACCESSIBLE retrieval, and CardService refuses any
            # other snapshot, so the status itself needs no second check here.
            if report.snapshot is None:
                return _entry(
                    candidate,
                    BatchEntryStatus.SKIPPED,
                    report,
                    reading,
                    reasons=(SOURCE_NOT_ACCESSIBLE_CODE,),
                    details=(report.reason,),
                )
            result = await self._cutting.cut_card(
                CutRequest(
                    snapshot_id=report.snapshot.snapshot_id,
                    need=need.need,
                    owner_id=request.owner_id,
                    argument=need.argument,
                    format_profile=request.format_profile,
                )
            )
        except (BudgetExceededError, UnpricedModelError) as refused:
            code = (
                BUDGET_EXCEEDED_CODE if isinstance(refused, BudgetExceededError) else error_code_of(refused)
            )
            return _entry(
                candidate,
                BatchEntryStatus.BUDGET_EXCEEDED,
                report,
                reading,
                reasons=(code,),
                details=(str(refused),),
            )
        except DomainError as failed:
            return _entry(
                candidate,
                BatchEntryStatus.FAILED,
                report,
                reading,
                reasons=(error_code_of(failed),),
                details=(reported_error_message(failed),),
            )
        return _entry(
            candidate,
            BatchEntryStatus.CUT,
            report,
            reading,
            reasons=tuple(code.value for code in result.reason_codes),
            details=tuple(failure.detail for failure in result.reasons),
            result=result,
        )


class _Walk:
    """One batch in progress: how many cards are VERIFIED, how many cuts are running, and the entries."""

    def __init__(self, request: BatchCutRequest) -> None:
        self.wanted = request.wanted
        self.semaphore = asyncio.Semaphore(request.concurrency)
        self.stopped = False
        """Set when the budget guard refused a call: nothing more is started."""
        self._verified = 0
        self._running = 0
        self._entries: list[BatchEntry] = []
        self._changed = asyncio.Condition()

    async def room_for_another(self) -> bool:
        """Wait until another candidate may start, or the run is over; True when it may start."""
        async with self._changed:
            await self._changed.wait_for(
                lambda: (
                    self.stopped
                    or self._verified >= self.wanted
                    or self._verified + self._running < self.wanted
                )
            )
        return not self.stopped and self._verified < self.wanted

    def started(self) -> None:
        self._running += 1

    def add(self, entry: BatchEntry) -> None:
        self._entries.append(entry)
        if entry.is_verified:
            self._verified += 1
        elif entry.status is BatchEntryStatus.BUDGET_EXCEEDED:
            self.stopped = True

    async def finished(self, entry: BatchEntry | None) -> None:
        """One attempt is over, with its entry, or with none when it was never started."""
        async with self._changed:
            self._running -= 1
            if entry is not None:
                self.add(entry)
            self._changed.notify_all()

    def report(self) -> BatchReport:
        entries = tuple(sorted(self._entries, key=lambda entry: entry.rank))
        verified = sum(1 for entry in entries if entry.is_verified)
        if verified >= self.wanted:
            reason = BatchStopReason.COMPLETE
        elif self.stopped:
            reason = BatchStopReason.BUDGET_EXCEEDED
        elif (
            entries
            and all(entry.status is BatchEntryStatus.SKIPPED for entry in entries if not entry.is_verified)
            and verified < len(entries)
        ):
            reason = BatchStopReason.ALL_REMAINING_INACCESSIBLE
        else:
            reason = BatchStopReason.CANDIDATES_EXHAUSTED
        return BatchReport(wanted=self.wanted, entries=entries, stop_reason=reason)


def _known_inaccessible(candidate: BatchCandidate) -> BatchEntry:
    return BatchEntry(
        rank=candidate.rank,
        url=candidate.url,
        title=candidate.title,
        status=BatchEntryStatus.SKIPPED,
        card_status=None,
        access_status=candidate.known_access,
        fetched=False,
        reasons=(SOURCE_NOT_ACCESSIBLE_CODE,),
        details=(
            f"an earlier retrieval recorded this source as {candidate.known_access.value}, "
            "so it was not fetched again",
        ),
    )


def _entry(
    candidate: BatchCandidate,
    status: BatchEntryStatus,
    report: FetchReport | None,
    reading: SpendReading,
    *,
    reasons: tuple[str, ...],
    details: tuple[str, ...],
    result: CutResult | None = None,
) -> BatchEntry:
    return BatchEntry(
        rank=candidate.rank,
        url=candidate.url,
        title=candidate.title,
        status=status,
        card_status=result.card.verification_status if result is not None else None,
        access_status=report.access_status if report is not None else None,
        fetched=report.fetched if report is not None else False,
        reasons=tuple(dict.fromkeys(reasons)),
        details=tuple(dict.fromkeys(details)),
        card_id=result.card.card_id if result is not None else None,
        snapshot_id=report.snapshot.snapshot_id if report is not None and report.snapshot else None,
        cost_usd=reading.cost_usd,
        result=result,
    )

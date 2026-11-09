"""What `debate-research search` prints: the results table, the provider footer and the JSON (`v1-e08-t05`).

Rendering only. The ranking, the merging and the status are `debate_core`'s, read off the
:class:`~debate_core.application.federated_search_types.SearchOutcome`; nothing here reorders, drops or
scores a result.

## The footer

One line per provider the search selected, in the order it asked them, under a heading that names the
search's status. Every provider is named whatever happened to it, so a partial result is never silent:

* `openalex: ok, 12 results` (and `from 7 queries` when the query was expanded);
* `rss: partial, 4 results: 2 of 10 feeds failed: …`, a provider that answered only part of the search;
* `rss: ok, 4 results: not counted as partial: Roll Call failing since 2026-11-02: …`, a shortfall the
  provider names without making its answer partial: a feed that has failed on every read for days
  (`v1-e07-t14`). It goes after the provider's other reasons, in the JSON's `reasons` too;
* `openalex: timeout: no answer within 10s`, or `error`, `rate limited`, `breaker open`,
  `not configured`, each with the provider's own reason, and `on 2 of 7 queries` when only some of
  its calls failed.

## Dates

The table's Date column shows what is known: `2022-05-17`, or `2023-03` and `2021` for a date a
provider knows only to its month or year (Crossref's, v1-e07-t03). `--json` still gives
`published_at` as the period's first instant.

## No evidence text

A search returns sources, not cards. Neither surface prints a snippet, an abstract or a feed's
description: a result carries its identifiers, its metadata, the providers that found it, the seven
features and the explanation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, TableSpec
from debate_core.application.federated_ranking import RankedCandidate
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.domain import AccessStatus, Article, SearchStatus
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderOutcome, ProviderStatus

__all__ = [
    "NO_PROVIDER_ENABLED_CODE",
    "NO_RESULTS_CODE",
    "SEARCH_FAILED_CODE",
    "SEARCH_PARTIAL_CODE",
    "ProviderSummary",
    "SearchProgress",
    "display_date",
    "footer_lines",
    "outcome_failure",
    "provider_calls_json",
    "provider_summaries",
    "results_table",
    "search_payload",
    "status_footer_lines",
]

SEARCH_PARTIAL_CODE = "SEARCH_PARTIAL"
NO_RESULTS_CODE = "NO_RESULTS"
SEARCH_FAILED_CODE = "SEARCH_FAILED"
NO_PROVIDER_ENABLED_CODE = "NO_PROVIDER_ENABLED"

_OUTCOME_WORDS = {
    ProviderOutcome.OK: "ok",
    ProviderOutcome.TIMEOUT: "timeout",
    ProviderOutcome.ERROR: "error",
    ProviderOutcome.RATE_LIMITED: "rate limited",
    ProviderOutcome.BREAKER_OPEN: "breaker open",
    ProviderOutcome.NOT_CONFIGURED: "not configured",
}

_HEADINGS = {
    SearchStatus.COMPLETE: "Providers: COMPLETE",
    SearchStatus.PARTIAL: "Providers: PARTIAL, results may be missing",
    SearchStatus.FAILED: "Providers: FAILED",
}


# ------------------------------------------------------------------------------------------------
# Per provider
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderSummary:
    """How one provider did across every query the search asked it."""

    provider: str
    outcome: str
    """`ok`, `partial`, or the outcome of its first call that did not answer, in words."""
    queries: int
    failed: int
    """Calls that did not answer: the outcome was anything but `ok`."""
    results: int
    """Results its answers held, before deduplication."""
    reasons: tuple[str, ...]
    """Each distinct reason it gave, without its name in front, in the order it gave them."""

    def line(self) -> str:
        """The footer line: `rss: ok, 2 results`, `openalex: timeout: no answer within 10s`."""
        noun = "result" if self.results == 1 else "results"
        if self.outcome in ("ok", "partial"):
            text = f"{self.provider}: {self.outcome}, {self.results} {noun}"
            if self.queries > 1:
                text += f" from {self.queries} queries"
        else:
            text = f"{self.provider}: {self.outcome}"
            if self.queries > 1:
                text += f" on {self.failed} of {self.queries} queries"
        return text + (f": {'; '.join(self.reasons)}" if self.reasons else "")

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "provider": self.provider,
            "outcome": self.outcome,
            "queries": self.queries,
            "failed": self.failed,
            "results": self.results,
            "reasons": list(self.reasons),
        }


NOT_PARTIAL: Final = "not counted as partial:"
"""What precedes a shortfall the provider reported without making its answer partial (v1-e07-t14)."""


def _reason(provider: str, text: str | None) -> str | None:
    if not text:
        return None
    return text.removeprefix(f"{provider}: ")


def provider_summaries(statuses: Sequence[ProviderStatus]) -> tuple[ProviderSummary, ...]:
    """One summary per provider, in the order the search first asked each."""
    grouped: dict[str, list[ProviderStatus]] = {}
    for status in statuses:
        grouped.setdefault(status.provider, []).append(status)
    summaries: list[ProviderSummary] = []
    for provider, calls in grouped.items():
        failed = [call for call in calls if call.outcome is not ProviderOutcome.OK]
        answered = [call for call in calls if call.response is not None]
        partial = [call for call in answered if call.response is not None and call.response.partial]
        if failed:
            outcome = _OUTCOME_WORDS[failed[0].outcome]
            texts = [call.error for call in failed]
        elif partial:
            outcome = "partial"
            texts = [call.response.error for call in partial if call.response is not None]
        else:
            outcome = "ok"
            texts = []
        reasons = tuple(dict.fromkeys(reason for text in texts if (reason := _reason(provider, text))))
        notes = (note for call in answered if call.response is not None for note in call.response.notes)
        reasons += tuple(dict.fromkeys(f"{NOT_PARTIAL} {note}" for note in notes))
        summaries.append(
            ProviderSummary(
                provider=provider,
                outcome=outcome,
                queries=len(calls),
                failed=len(failed),
                results=sum(len(call.response.results) for call in answered if call.response is not None),
                reasons=reasons,
            )
        )
    return tuple(summaries)


def footer_lines(outcome: SearchOutcome) -> list[str]:
    """The provider status footer: a heading naming the status, then one line per provider."""
    return status_footer_lines(outcome.status, outcome.provider_statuses)


def status_footer_lines(status: SearchStatus, statuses: Sequence[ProviderStatus]) -> list[str]:
    """The footer over any calls: one search's, or every search of a daily digest (v1-e08-t07)."""
    return [_HEADINGS[status], *(f"  {summary.line()}" for summary in provider_summaries(statuses))]


def provider_calls_json(statuses: Sequence[ProviderStatus]) -> list[JsonValue]:
    """Every call as the JSON's `provider_calls`: its provider, query, outcome, results and error."""
    return [
        {
            "provider": status.provider,
            "query": status.query.query,
            "outcome": status.outcome.value,
            "elapsed_ms": status.elapsed_ms,
            "results": len(status.response.results) if status.response is not None else 0,
            "partial": status.response.partial if status.response is not None else False,
            "error": status.error or (status.response.error if status.response is not None else None),
        }
        for status in statuses
    ]


# ------------------------------------------------------------------------------------------------
# Results
# ------------------------------------------------------------------------------------------------


def _articles_by_rank(outcome: SearchOutcome) -> dict[int, Article]:
    return {result.rank: article for result, article in zip(outcome.results, outcome.articles, strict=True)}


def display_date(ranked: RankedCandidate) -> str:
    """The date to the precision known: `2022-05-17`, `2023-03` or `2021` (v1-e07-t03), or `undated`."""
    published, precision = ranked.candidate.published_at, ranked.candidate.date_precision
    if published is None:
        return "undated"
    if precision is DatePrecision.YEAR:
        return f"{published.year:04d}"
    if precision is DatePrecision.MONTH:
        return f"{published.year:04d}-{published.month:02d}"
    return published.date().isoformat()


def _access(ranked: RankedCandidate, article: Article | None) -> str:
    """The access a person can expect: an Article's measured status, else the providers' open-access hint."""
    if article is not None and article.access_status is not AccessStatus.UNKNOWN:
        return article.access_status.value
    if ranked.candidate.open_access:
        return "UNKNOWN (open access)"
    return "UNKNOWN"


def _provider_order(ranked: RankedCandidate, candidates: Sequence[CandidateResult]) -> int | None:
    """Where the source first appears in what the providers returned, in fan-out order, from 1.

    The baseline v1-e08-t03 measures the ranking against ("raw provider order"): the merged
    candidates' first appearance, query by query and provider by provider.
    """
    positions = [candidates.index(member) + 1 for member in ranked.candidate.members if member in candidates]
    return min(positions) if positions else None


def _result_json(
    ranked: RankedCandidate, article: Article | None, candidates: Sequence[CandidateResult]
) -> dict[str, JsonValue]:
    candidate = ranked.candidate
    return {
        "rank": ranked.rank,
        "provider_order": _provider_order(ranked, candidates),
        "score": ranked.total_score,
        "lexical_score": ranked.lexical_score,
        "features": dict(ranked.features),
        "contributions": dict(ranked.contributions),
        "explanation": ranked.explanation,
        "title": candidate.title,
        "url": candidate.url,
        "canonical_url": candidate.canonical_url,
        "publication": candidate.publication,
        "authors": list(candidate.authors),
        "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
        "source_type": candidate.source_type.value,
        "open_access": candidate.open_access,
        "open_access_url": candidate.open_access_url,
        "citation_count": candidate.citation_count,
        "identifiers": candidate.identifiers.model_dump(mode="json"),
        "providers": list(candidate.providers),
        "provider_record_ids": {
            member.provider: member.provider_record_id
            for member in candidate.members
            if member.provider_record_id is not None
        },
        "matched_on": [rule.value for rule in candidate.matched_on],
        "field_sources": dict(candidate.field_sources),
        "article_id": article.article_id if article is not None else None,
        "access_status": article.access_status.value if article is not None else None,
    }


def search_payload(outcome: SearchOutcome) -> dict[str, JsonValue]:
    """The search as JSON: `data` on exit 0, `error.details` otherwise. Never a snippet or an abstract."""
    search = outcome.search
    articles = _articles_by_rank(outcome)
    return {
        "search_id": search.search_id,
        "query": search.query,
        "status": search.status.value,
        "filters": search.filters.model_dump(mode="json"),
        "expansion": search.expansion.model_dump(mode="json") if search.expansion is not None else None,
        "results": [
            _result_json(ranked, articles.get(ranked.rank), outcome.candidates)
            for ranked in outcome.ranked_candidates
        ],
        "providers": [summary.as_json() for summary in provider_summaries(outcome.provider_statuses)],
        "provider_calls": provider_calls_json(outcome.provider_statuses),
        "provider_health": [health.model_dump(mode="json") for health in outcome.provider_health],
    }


def results_table(outcome: SearchOutcome) -> TableSpec:
    """The ranked rows, then the expansion's line and the provider status footer."""
    articles = _articles_by_rank(outcome)
    count = len(outcome.ranked_candidates)
    title = f'{count} {"result" if count == 1 else "results"} for "{outcome.search.query}"'
    if outcome.status is SearchStatus.PARTIAL:
        title = f"PARTIAL: {title}"
    rows = [
        (
            str(ranked.rank),
            ranked.candidate.title,
            ranked.candidate.publication or "",
            display_date(ranked),
            ranked.candidate.source_type.value.lower(),
            _access(ranked, articles.get(ranked.rank)),
            ranked.explanation,
        )
        for ranked in outcome.ranked_candidates
    ]
    below: list[str] = []
    expansion = outcome.search.expansion
    if expansion is not None:
        suggested = sum(1 for query in expansion.queries if query.origin.value == "model")
        below.append(
            f"Expanded for {expansion.argument} / {expansion.need} (taxonomy {expansion.taxonomy_version}): "
            f"{len(expansion.queries)} queries" + (f", {suggested} from a model" if suggested else "")
        )
    below.extend(footer_lines(outcome))
    return TableSpec(
        title=title,
        columns=("Rank", "Title", "Publisher / venue", "Date", "Type", "Access", "Why"),
        rows=rows,
        lines_below=below,
    )


# ------------------------------------------------------------------------------------------------
# Outcomes that are not a plain success
# ------------------------------------------------------------------------------------------------


def _named(summaries: Sequence[ProviderSummary]) -> str:
    return ", ".join(f"{summary.provider} ({summary.outcome})" for summary in summaries)


def outcome_failure(
    outcome: SearchOutcome, payload: dict[str, JsonValue], exit_code: ExitCode
) -> CommandFailure:
    """The failure a search that did not end `OK` reports, carrying the whole search as its details."""
    summaries = provider_summaries(outcome.provider_statuses)
    panel = {summary.provider: summary.line().removeprefix(f"{summary.provider}: ") for summary in summaries}
    if exit_code is ExitCode.SEARCH_PARTIAL:
        missing = [summary for summary in summaries if summary.outcome != "ok"]
        return CommandFailure(
            code=SEARCH_PARTIAL_CODE,
            message=f"{len(missing)} of {len(summaries)} providers did not answer in full: {_named(missing)}",
            exit_code=exit_code,
            details=payload,
            panel_details=panel,
            hint="The results are what the other providers found. The same search later may find more.",
        )
    if exit_code is ExitCode.NO_RESULTS:
        return CommandFailure(
            code=NO_RESULTS_CODE,
            message=f'every provider answered, and nothing matched "{outcome.search.query}"',
            exit_code=exit_code,
            details=payload,
            panel_details=panel,
            hint="Try fewer words, an earlier --since, or --argument with --need.",
        )
    if exit_code is ExitCode.RETRIEVAL_FAILURE:
        return CommandFailure(
            code=SEARCH_FAILED_CODE,
            message=f"no provider answered: {_named(summaries)}",
            exit_code=exit_code,
            details=payload,
            panel_details=panel,
            hint="Nothing was found because nothing answered. The same search may work later.",
        )
    return CommandFailure(
        code=NO_PROVIDER_ENABLED_CODE,
        message=f"no provider was asked: none of {', '.join(panel)} is enabled",
        exit_code=exit_code,
        details=payload,
        panel_details=panel,
        hint="Name enabled providers with --providers, or enable them in providers.enabled "
        "(config/profiles/<env>.toml, or DEBATE_PROVIDERS__ENABLED).",
    )


class SearchProgress:
    """The search's two progress lines on stderr: before it asks the providers, and once it has ranked."""

    def __init__(self, output: CliOutput, command: str) -> None:
        self._output = output
        self._command = command

    def searching(self, query: str, providers: Sequence[str] | None) -> None:
        asked = ", ".join(providers) if providers else "every enabled provider"
        self._output.event_line(
            self._command,
            "searching",
            {"query": query, "providers": list(providers) if providers else None},
            text=f'Searching {asked} for "{query}"',
        )

    def searched(self, outcome: SearchOutcome) -> None:
        count = len(outcome.ranked_candidates)
        self._output.event_line(
            self._command,
            "searched",
            {"status": outcome.status.value, "results": len(outcome.ranked_candidates)},
            text=f"Ranked {count} {'source' if count == 1 else 'sources'} ({outcome.status.value.lower()})",
        )

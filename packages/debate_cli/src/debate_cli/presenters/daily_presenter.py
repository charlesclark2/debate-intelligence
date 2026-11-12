"""What `debate-research daily` writes and prints: the digest file, its summary and its JSON (`v1-e08-t07`).

Rendering only. What is in the digest, in which group and in what order, and what was left out as
listed before, are :class:`~debate_core.application.digest_service.DigestService`'s, read off its
:class:`~debate_core.application.digest_service.Digest`; nothing here drops, reorders or scores a result.

## The file

`<preset>-<date>.md` (or `.json` with `--format json`). The Markdown has a heading, the window, the
counts and the status; a note for each feed topic with a feed still awaiting the coach's review; one
section per argument/need pair, each new result with its title, publisher, date, the ranking's
explanation and its URL; and the provider status footer, the same lines `search` prints. The JSON is
:func:`digest_payload`: the same digest, with each result's identifiers, rank and score, every
provider summary and every call.

## No evidence text

A digest lists sources, not cards: a result's title, metadata, explanation and URL, never a snippet,
an abstract or a feed's description.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_cli.presenters.batch_report_presenter import AutoCutFiles, AutoCutSettings, entry_json
from debate_cli.presenters.search_presenter import (
    NO_PROVIDER_ASKED,
    NO_PROVIDER_ENABLED_CODE,
    SEARCH_FAILED_CODE,
    SEARCH_PARTIAL_CODE,
    display_date,
    no_provider_asked_message,
    provider_calls_json,
    provider_summaries,
    status_footer_lines,
)
from debate_core.application.batch_cut_service import BatchReport
from debate_core.application.digest_service import Digest, DigestItem
from debate_core.application.federated_search import partial_providers
from debate_core.domain import SearchStatus
from debate_core.domain.discovery import ProviderOutcome

__all__ = [
    "DigestFormat",
    "auto_cut_footer",
    "auto_cut_payload",
    "digest_failure",
    "digest_file_name",
    "digest_footer",
    "digest_markdown",
    "digest_payload",
    "digest_table",
    "exit_code_for_digest",
]


class DigestFormat(StrEnum):
    """What `--format` writes the digest file as."""

    MD = "md"
    JSON = "json"


_MARKDOWN_SPECIAL: Final = re.compile(r"([\\`*_\[\]<>#|])")


def _plain(text: str) -> str:
    """`text` with the characters Markdown would read as markup escaped, so a title prints as written."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", " ".join(text.split()))


QUERY_ALONE_NOTE: Final = (
    "No digest templates for this group in config/daily_templates.yaml: its searches asked the "
    "preset's queries alone."
)
"""Under a group whose pair has no digest templates (v1-e08-t25): it never asks the taxonomy's."""


def digest_file_name(digest: Digest, file_format: DigestFormat) -> str:
    """`politics-2026-09-17.md`: the preset, the date and the format."""
    return f"{digest.preset.name}-{digest.day.isoformat()}.{file_format.value}"


def digest_footer(digest: Digest) -> list[str]:
    """The provider status footer over every call of every search: `search`'s own lines."""
    return status_footer_lines(digest.status, digest.provider_statuses, uncounted=digest.uncounted)


def _window_words(digest: Digest) -> str:
    """`2026-09-17 (1 day, UTC)` for a `--date` digest; with no `--date`, the run's hours in its zone:
    `2026-09-17 07:00 to 2026-09-18 07:00 America/Chicago (the 24 hours before the run)`."""
    days = digest.window.days
    if digest.zone is not None:
        first, last = (
            moment.astimezone(digest.zone).strftime("%Y-%m-%d %H:%M")
            for moment in (digest.since, digest.until)
        )
        return f"{first} to {last} {digest.zone.key} (the {24 * days} hours before the run)"
    first, last = digest.since.date().isoformat(), digest.until.date().isoformat()
    span = first if first == last else f"{first} to {last}"
    return f"{span} ({days} {'day' if days == 1 else 'days'}, UTC)"


def _review_lines(digest: Digest) -> list[str]:
    return [
        f"Feed topic {topic.topic} was read with {len(topic.awaiting_coach_review)} "
        f"{'feed' if len(topic.awaiting_coach_review) == 1 else 'feeds'} still awaiting the coach's review: "
        f"{', '.join(topic.awaiting_coach_review)}."
        for topic in digest.awaiting_review
    ]


def _counts(digest: Digest) -> str:
    new = len(digest.items)
    return (
        f"{new} new {'result' if new == 1 else 'results'}; {digest.listed_before} left out as listed "
        "in an earlier digest"
    )


def _item_markdown(position: int, item: DigestItem) -> list[str]:
    candidate = item.ranked.candidate
    return [
        f"### {position}. {_plain(candidate.title)}",
        "",
        f"- Publisher: {_plain(candidate.publication or 'unknown')}",
        f"- Date: {display_date(item.ranked)}",
        f"- Why: {_plain(item.ranked.explanation)}",
        f"- URL: <{candidate.canonical_url or candidate.url}>",
        "",
    ]


def digest_markdown(digest: Digest) -> str:
    """The digest file in Markdown: see the module docstring."""
    lines = [
        f"# {_plain(digest.heading)}",
        "",
        f"- Preset: {digest.preset.name}" + (f", on {digest.preset.topic}" if digest.preset.topic else ""),
        f"- Window: {_window_words(digest)}",
        f"- {_counts(digest)}",
        f"- Status: {digest.status.value}",
        "",
    ]
    for line in _review_lines(digest):
        lines += [f"> {line}", ""]
    for group in digest.groups:
        lines += [f"## {_plain(group.heading)}", ""]
        if group.asked_taxonomy_templates:
            lines += [f"> {QUERY_ALONE_NOTE}", ""]
        if not group.items:
            lines += ["No new results.", ""]
        for position, item in enumerate(group.items, start=1):
            lines += _item_markdown(position, item)
    heading, *providers = digest_footer(digest)
    lines += ["## Providers", "", heading, "", *(f"- {line.strip()}" for line in providers), ""]
    return "\n".join(lines)


def _item_json(position: int, item: DigestItem) -> dict[str, JsonValue]:
    candidate = item.ranked.candidate
    return {
        "position": position,
        "title": candidate.title,
        "publisher": candidate.publication,
        "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
        "date": display_date(item.ranked),
        "explanation": item.ranked.explanation,
        "url": candidate.url,
        "canonical_url": candidate.canonical_url,
        "identifiers": candidate.identifiers.model_dump(mode="json"),
        "source_type": candidate.source_type.value,
        "providers": list(candidate.providers),
        "query": item.query,
        "search_id": item.search_id,
        "rank": item.ranked.rank,
        "score": item.ranked.total_score,
        "article_id": item.article.article_id if item.article is not None else None,
        "access_status": item.known_access.value,
    }


def digest_payload(digest: Digest) -> dict[str, JsonValue]:
    """The digest as JSON: the `.json` file, and the `--json` output's `data` (with `file` added)."""
    preset = digest.preset
    return {
        "preset": preset.name,
        "heading": digest.heading,
        "date": digest.day.isoformat(),
        "topic": preset.topic,
        "window": {
            "days": digest.window.days,
            "since": digest.since.isoformat(),
            "until": digest.until.isoformat(),
        },
        "status": digest.status.value,
        "new_results": len(digest.items),
        "listed_before": digest.listed_before,
        "feed_topics": [
            {"topic": topic.topic, "awaiting_coach_review": list(topic.awaiting_coach_review)}
            for topic in digest.feed_topics
        ],
        "groups": [
            {
                "argument": group.pair.argument,
                "need": group.pair.need,
                "heading": group.heading,
                "asked_taxonomy_templates": group.asked_taxonomy_templates,
                "results": [_item_json(position, item) for position, item in enumerate(group.items, start=1)],
            }
            for group in digest.groups
        ],
        "searches": [
            {
                "search_id": outcome.search.search_id,
                "query": outcome.search.query,
                "argument": outcome.search.expansion.argument if outcome.search.expansion else None,
                "need": outcome.search.expansion.need if outcome.search.expansion else None,
                "status": outcome.status.value,
            }
            for outcome in digest.outcomes
        ],
        "providers": [
            summary.as_json()
            for summary in provider_summaries(digest.provider_statuses, uncounted=digest.uncounted)
        ],
        "provider_calls": provider_calls_json(digest.provider_statuses),
    }


def digest_table(digest: Digest) -> TableSpec:
    """What a person sees: each group's count, then the file, the counts, the reviews and the footer."""
    title = f"{digest.heading}: {_counts(digest)}"
    if digest.status is SearchStatus.PARTIAL:
        title = f"PARTIAL: {title}"
    below = [f"Digest: {digest.file}"] if digest.file is not None else []
    below += _review_lines(digest)
    below += [f"{group.heading}: {QUERY_ALONE_NOTE}" for group in digest.groups if group.asked_taxonomy_templates]
    below += digest_footer(digest)
    return TableSpec(
        title=title,
        columns=("Argument and need", "New results"),
        rows=[(group.heading, str(len(group.items))) for group in digest.groups],
        lines_below=below,
    )


def exit_code_for_digest(digest: Digest) -> ExitCode:
    """0 for a complete digest, new results or none; 6 partial; 3 when nothing answered; 1 when nothing
    was asked, because every one of the preset's providers is not configured (not enabled, or enabled
    without its key)."""
    if digest.status is SearchStatus.COMPLETE:
        return ExitCode.OK
    if digest.status is SearchStatus.PARTIAL:
        return ExitCode.SEARCH_PARTIAL
    asked = any(status.outcome is not ProviderOutcome.NOT_CONFIGURED for status in digest.provider_statuses)
    return ExitCode.RETRIEVAL_FAILURE if asked else ExitCode.DOMAIN_FAILURE


def _named(digest: Digest, outcomes: Sequence[str]) -> str:
    return ", ".join(
        f"{summary.provider} ({summary.outcome})"
        for summary in provider_summaries(digest.provider_statuses, uncounted=digest.uncounted)
        if summary.outcome in outcomes or not outcomes
    )


def digest_failure(digest: Digest, payload: dict[str, JsonValue], exit_code: ExitCode) -> CommandFailure:
    """The failure a digest that did not end `OK` reports, carrying the whole digest as its details."""
    summaries = provider_summaries(digest.provider_statuses, uncounted=digest.uncounted)
    panel = {summary.provider: summary.line().removeprefix(f"{summary.provider}: ") for summary in summaries}
    if exit_code is ExitCode.SEARCH_PARTIAL:
        missing = [summary for summary in summaries if summary.outcome != "ok"]
        return CommandFailure(
            code=SEARCH_PARTIAL_CODE,
            message=(
                f"{len(missing)} of {len(summaries)} providers did not answer in full: "
                + ", ".join(f"{summary.provider} ({summary.outcome})" for summary in missing)
            ),
            exit_code=exit_code,
            details=payload,
            panel_details=panel,
            hint="The digest was written with what the other providers found; its results count as listed.",
        )
    if exit_code is ExitCode.RETRIEVAL_FAILURE:
        return CommandFailure(
            code=SEARCH_FAILED_CODE,
            message=f"no provider answered, so no digest was written: {_named(digest, ())}",
            exit_code=exit_code,
            details=payload,
            panel_details=panel,
            hint="Nothing was marked as listed. The same digest may work later.",
        )
    message, panel_message = no_provider_asked_message(
        f"{NO_PROVIDER_ASKED}, so no digest was written", summaries
    )
    return CommandFailure(
        code=NO_PROVIDER_ENABLED_CODE,
        message=message,
        exit_code=exit_code,
        details=payload,
        panel_details=panel,
        panel_message=panel_message,
        hint="Enable the preset's providers in providers.enabled "
        "(config/profiles/<env>.toml, or DEBATE_PROVIDERS__ENABLED).",
    )


def auto_cut_payload(
    report: BatchReport, digest: Digest, settings: AutoCutSettings, files: AutoCutFiles
) -> dict[str, JsonValue]:
    """`daily --auto-cut`'s report.json, and the `auto_cut` object of its `--json` output."""
    return {
        "preset": digest.preset.name,
        "date": digest.day.isoformat(),
        "digest": str(digest.file) if digest.file is not None else None,
        "block": digest.heading,
        "wanted": settings.wanted,
        "concurrency": settings.concurrency,
        "card_format": settings.card_format,
        "max_cost_usd": settings.max_cost_usd,
        "verified": len(report.verified),
        "unverified": len(report.unverified),
        "complete": report.complete,
        "stop_reason": report.stop_reason.value,
        "digest_status": digest.status.value,
        "partial_providers": list[JsonValue](
            partial_providers(digest.provider_statuses, uncounted=digest.uncounted)
        ),
        "cost_usd": report.cost_usd,
        "bundle": str(files.bundle) if files.bundle is not None else None,
        "manifest": str(files.manifest) if files.manifest is not None else None,
        "report": str(files.report),
        "entries": [entry_json(entry) for entry in report.entries],
    }


def auto_cut_footer(digest: Digest) -> list[str]:
    """What goes below `daily --auto-cut`'s table before the files: the digest and its provider footer."""
    return [f"Digest: {digest.file}", *digest_footer(digest)]

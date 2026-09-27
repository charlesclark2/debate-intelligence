"""`debate-research caselist cards`: how many cards a caselist holds, and which are read most.

::

    debate-research caselist cards --caselist hsld26 --parsed ~/debate-data/parsed/hsld26
    debate-research caselist cards --caselist hsld26 --parsed <dir> --snapshot 2026-09-15 --top 25
    debate-research caselist cards --caselist hsld26 --parsed <dir> --json
    debate-research caselist cards --caselist hsld26 --parsed <dir> --by-team

Reads parsed-card JSONL (the `ParsedCard` schema of `v1-e31-t03`, or the per-source
`ParsedDocument` records `v1-e31-t06` writes) from `--parsed`, and the disclosures this machine's
caselist imports recorded. Prints the totals — cards, exact unique cards, clusters, the duplicate
rate — and the top clusters by the number of distinct teams that read them, each with a short cite
and a tag.

Every decision is :class:`~debate_core.application.caselist_card_stats.CaselistCardStatsService`'s
(`v1-e31-t04-card-fingerprints`); this is the rendering.

## What it shows about teams

Nothing, by default: a cluster's row carries counts. `--by-team` adds the school and team code of
every team that read it, and never more than that (`docs/policies/caselist-data-use.md`, "What a
report may show"). No debater name exists anywhere to print, and a card's cutter mark — the
initials in its cite tail — is never printed, with or without the flag.

## `--json`

Accepted here as well as before the command group (`debate-research --json caselist cards …`), so
the invocation in the spec works as written. Either way the output is the one JSON envelope every
command writes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from debate_cli.commands.caselist import _snapshot_date  # pyright: ignore[reportPrivateUsage]
from debate_cli.context import cli_context, command_name
from debate_cli.output import CliOutput, JsonValue, OutputMode, TableSpec
from debate_core.application.caselist_card_stats import CaselistCardReport, ClusterSummary, read_parsed_cards

__all__ = ["cards", "cards_summary"]


def cards(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hsld26.")],
    parsed: Annotated[
        Path,
        typer.Option(
            "--parsed",
            exists=True,
            file_okay=False,
            help="Directory of parsed-card JSONL files to read.",
        ),
    ],
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="Report as of this snapshot, YYYY-MM-DD. Default: everything."),
    ] = None,
    top: Annotated[int, typer.Option("--top", min=1, help="How many clusters to list.")] = 10,
    by_team: Annotated[
        bool,
        typer.Option("--by-team", help="Also list the school and team code of each team that read a card."),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """Count a caselist's cards and list the ones read by the most teams."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    as_of = _snapshot_date(snapshot) if snapshot is not None else None
    service = cli.services.caselist_card_stats()
    report = asyncio.run(
        service.report(
            read_parsed_cards(parsed),
            caselist=caselist,
            snapshot=as_of,
            top=top,
            include_teams=by_team,
        )
    )
    cli.output.success(command_name(ctx), cards_summary(report), display=_table(report, by_team=by_team))


def cards_summary(report: CaselistCardReport) -> dict[str, JsonValue]:
    """The JSON payload: totals and top clusters. Never an occurrence row, never a cutter mark."""
    totals = report.totals
    return {
        "caselist": report.caselist,
        "snapshot": report.snapshot.isoformat() if report.snapshot is not None else None,
        "fingerprint_version": report.fingerprint_version,
        "totals": {
            "parsed_cards": totals.parsed_cards,
            "cards": totals.cards,
            "occurrences": totals.occurrences,
            "exact_unique": totals.exact_unique,
            "clusters": totals.clusters,
            "duplicate_rate": round(totals.duplicate_rate, 4),
            "teams": totals.teams,
            "linked_abbreviated": totals.linked_abbreviated,
            "unlinked_abbreviated": totals.unlinked_abbreviated,
        },
        "top_clusters": [_cluster_payload(cluster) for cluster in report.top_clusters],
    }


def _cluster_payload(cluster: ClusterSummary) -> JsonValue:
    payload: dict[str, JsonValue] = {
        "cluster_id": cluster.cluster_id,
        "short_cite": cluster.short_cite,
        "tag": cluster.tag,
        "distinct_teams": cluster.distinct_teams,
        "occurrences": cluster.occurrences,
        "files": cluster.files,
    }
    if cluster.teams is not None:
        payload["teams"] = [{"school": school, "team_code": code} for school, code in cluster.teams]
    return payload


def _table(report: CaselistCardReport, *, by_team: bool) -> TableSpec:
    totals = report.totals
    columns = ["Cluster", "Teams", "Occurrences", "Files", "Short cite", "Tag"]
    if by_team:
        columns.append("Read by")
    rows: list[list[str]] = []
    for cluster in report.top_clusters:
        row = [
            cluster.cluster_id[:12],
            str(cluster.distinct_teams),
            str(cluster.occurrences),
            str(cluster.files),
            cluster.short_cite or "-",
            _shorten(cluster.tag),
        ]
        if by_team:
            row.append(", ".join(f"{school} {code}" for school, code in cluster.teams or ()))
        rows.append(row)
    as_of = f" as of {report.snapshot.isoformat()}" if report.snapshot is not None else ""
    return TableSpec(
        columns=columns,
        rows=rows,
        title=f"{report.caselist} cards{as_of}: top {len(rows)} by distinct teams",
        caption=(
            f"{totals.cards} cards, {totals.exact_unique} exact unique, {totals.clusters} clusters, "
            f"duplicate rate {totals.duplicate_rate:.1%}; {totals.occurrences} occurrences across "
            f"{totals.teams} teams; abbreviated cards linked {totals.linked_abbreviated}, unlinked "
            f"{totals.unlinked_abbreviated}. Fingerprints {report.fingerprint_version}."
        ),
    )


def _shorten(tag: str, limit: int = 60) -> str:
    flat = " ".join(tag.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"

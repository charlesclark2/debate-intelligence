"""`debate-research caselist import`: one weekly archive into the local evidence store.

Every decision about what an archive member *is* — new, carried forward, revised, a duplicate,
taken down, suppressed — belongs to
:class:`~debate_core.application.caselist.import_service.CaselistImportService` in `debate_core`.
What is here is the part that is genuinely a command-line surface: which flags mean what, which
event a caselist slug implies, where the manifest lands, and how a summary is rendered for a
person and for a program.

::

    debate-research caselist import ~/Downloads/hsld26-0915.zip \\
        --caselist hsld26 --snapshot 2026-09-15

    debate-research caselist import ~/Downloads/hsld26-0915 --caselist hsld26 \\
        --snapshot 2026-09-15 --dry-run          # classify everything, write nothing
    debate-research --json caselist import ...   # one JSON object for a scheduled consumer

## The archive is a zip or a directory

Both are read the same way and both produce the same relative paths, so it makes no difference to
what gets stored which one the operator happens to have
(:func:`debate_core.integrations.local.archive_reader.read_archive`).

## Which event

`--event` says which sides the caselist debates, and it decides whether `Aff` or `Pro` is a legal
side on a disclosure. It is inferred from the slug for the caselists that exist
(:data:`EVENTS_BY_SLUG_PREFIX`), because typing `--event LD` after `--caselist hsld26` every week
is a way to eventually type the wrong one. A slug this build does not recognise is a refusal that
names the flag, not a guess.

## Nothing is written under `--dry-run`

No blob, no record, no snapshot row and no manifest. It is the rehearsal an operator does first
on a week that looks odd, and the counts it prints are the counts a real run would produce.

## Exit codes

From :mod:`debate_cli.exit_codes`, and no new numbers. `0` when the import ran. `1` for the
deterministic refusals an operator has to act on: an archive over the size ceiling, an unreadable
path, a slug whose event cannot be inferred, or an archive older than one already imported
without `--allow-out-of-order`. All four arrive as
:class:`~debate_core.application.errors.DomainError`s and are rendered by the root group.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Final

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.caselist.import_service import Classification, ImportReport
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.settings import ConfigurationError
from debate_core.domain.caselist import Event
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.fs_object_store import FsEvidenceObjectStore

__all__ = [
    "EVENTS_BY_SLUG_PREFIX",
    "InvalidSnapshotDate",
    "UnknownCaselistEvent",
    "event_for_caselist",
    "import_archive",
    "import_summary",
]

EVENTS_BY_SLUG_PREFIX: Final[dict[str, Event]] = {
    "hsld": Event.LD,
    "hspolicy": Event.POLICY,
    "hspf": Event.PF,
    "ndtceda": Event.POLICY,
    "nfald": Event.LD,
    # The synthetic caselist the test archives are built under (`tests/fixtures/caselist/`).
    # Named here rather than special-cased in a test so that the smoke check runs the same code
    # path an operator runs.
    "testcl": Event.LD,
}
"""Which event each published caselist slug debates, by the letters before its season year.

A table rather than a rule, because a slug is data (`CaselistSlug` is a validated string, not an
enum) and next season's slugs are rows somebody adds here. A slug that is not in it is a refusal
naming `--event`, never a guess: guessing wrong would file every disclosure in the archive under
a side the event does not debate.
"""


def event_for_caselist(caselist: str) -> Event | None:
    """The event a caselist slug implies, or `None` when this build does not know the slug."""
    prefix = caselist.rstrip("0123456789")
    return EVENTS_BY_SLUG_PREFIX.get(prefix)


def import_archive(
    ctx: typer.Context,
    source: Annotated[
        Path,
        typer.Argument(
            exists=True,
            help="The weekly archive: a .zip straight from OpenCaselist, or a directory.",
        ),
    ],
    caselist: Annotated[
        str,
        typer.Option("--caselist", help="Caselist slug the archive was published for, e.g. hsld26."),
    ],
    snapshot: Annotated[
        str,
        typer.Option("--snapshot", help="The date the archive was published, as YYYY-MM-DD."),
    ],
    event: Annotated[
        Event | None,
        typer.Option("--event", help="Which event the caselist debates. Inferred from the slug."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Classify everything and write nothing at all."),
    ] = False,
    allow_out_of_order: Annotated[
        bool,
        typer.Option(
            "--allow-out-of-order",
            help="Import an archive older than one already imported for this caselist.",
        ),
    ] = False,
) -> None:
    """Import one weekly caselist archive, deduplicated against the ones already imported."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    published = _snapshot_date(snapshot)
    resolved_event = event or event_for_caselist(caselist)
    if resolved_event is None:
        raise UnknownCaselistEvent(caselist)

    service = cli.services.caselist_import()
    cli.output.detail(f"reading {source.name}")
    report = _run(
        service.import_archive(
            read_archive(
                source,
                max_archive_bytes=settings.caselist.max_archive_bytes,
                max_unpacked_bytes=settings.caselist.max_unpacked_bytes,
            ),
            caselist=caselist,
            snapshot=published,
            event=resolved_event,
            archive_sha256=archive_digest(source),
            allow_out_of_order=allow_out_of_order,
            dry_run=dry_run,
        )
    )

    manifest = None
    if not dry_run:
        objects = FsEvidenceObjectStore(settings.storage.data_dir)
        manifest = write_manifest(report, objects.path_for(manifest_key(caselist, published)))
        cli.output.detail(f"wrote {manifest.name}")

    cli.output.success(
        command_name(ctx),
        import_summary(report, manifest),
        display=_summary_table(report, manifest),
    )


def _snapshot_date(value: str) -> date:
    """Parse `--snapshot` as a plain calendar date.

    Taken as a string and parsed here rather than declared as a `datetime` option, because a
    snapshot is the day an archive was published and an option typed as a datetime would accept
    `2026-09-15T06:00` and silently carry a time of day the source does not have.
    """
    try:
        return date.fromisoformat(value.strip())
    except ValueError as malformed:
        raise InvalidSnapshotDate(value) from malformed


class InvalidSnapshotDate(ConfigurationError):
    """`--snapshot` was not a calendar date. It names the archive's publication day."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"--snapshot must be a date as YYYY-MM-DD (the day the archive was published), not {value!r}",
            field="--snapshot",
            source="cli",
        )


class UnknownCaselistEvent(ConfigurationError):
    """The caselist slug is not one this build knows the event for, and `--event` was not given.

    A :class:`~debate_core.application.settings.ConfigurationError`, so the root group reports it
    as the deterministic failure it is: the operator supplies the flag and the same command works.
    """

    def __init__(self, caselist: str) -> None:
        known = ", ".join(sorted(EVENTS_BY_SLUG_PREFIX))
        super().__init__(
            f"this build does not know which event {caselist!r} debates, so it cannot tell a legal "
            f"side from an illegal one; pass --event, or add the slug prefix to the table in "
            f"debate_cli.commands.caselist (known prefixes: {known})",
            field="--event",
            source="cli",
        )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def import_summary(report: ImportReport, manifest: Path | None) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `caselist import`.

    Written for a program first, because the scheduled weekly import (`v1-e34-t02`) reads it:
    every classification has a count whether or not it occurred, `applied` says whether anything
    was written, and `manifest` is the path or `null` rather than a sentence to parse.
    """
    return {
        "caselist": report.caselist,
        "snapshot": report.snapshot.isoformat(),
        "event": str(report.event),
        "previous_snapshot": (
            report.previous_snapshot.isoformat() if report.previous_snapshot is not None else None
        ),
        "applied": report.applied,
        "archive_sha256": report.archive_sha256,
        "members": report.member_count,
        "counts": {str(name): report.count(name) for name in Classification},
        "skipped": {str(reason): count for reason, count in sorted(report.skipped.items(), key=str)},
        "skipped_total": sum(report.skipped.values()),
        "distinct_sha256": report.distinct_digests,
        "newly_stored_blobs": report.newly_stored_blobs,
        "warnings": report.warning_count,
        "manifest": str(manifest) if manifest is not None else None,
    }


def _summary_table(report: ImportReport, manifest: Path | None) -> TableSpec:
    """One row per classification, then the skips: what an operator checks the week against."""
    rows = [[str(name), str(report.count(name))] for name in Classification]
    rows.append(["SKIPPED", str(sum(report.skipped.values()))])
    return TableSpec(
        columns=("Classification", "Files"),
        rows=rows,
        title=(
            f"{report.caselist} {report.snapshot.isoformat()} "
            f"({'dry run' if not report.applied else 'imported'})"
        ),
        caption=_caption(report, manifest),
    )


def _caption(report: ImportReport, manifest: Path | None) -> str:
    """What the numbers mean, in the one line under the table."""
    against = (
        f"against {report.previous_snapshot.isoformat()}"
        if report.previous_snapshot is not None
        else "the first archive for this caselist"
    )
    warned = f", {report.warning_count} filename(s) not fully read" if report.warning_count else ""
    if not report.applied:
        return (
            f"{report.member_count} member(s), {against}{warned}. Planned only; nothing was "
            "written. Re-run without --dry-run to import it."
        )
    return (
        f"{report.member_count} member(s), {against}{warned}. "
        f"{report.newly_stored_blobs} new file(s) stored; manifest at "
        f"{manifest.name if manifest else 'none'}."
    )


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion.

    The services are `async` because the API and the workers will await them; a CLI command is the
    one caller with no event loop of its own, so it starts one for the duration of the command.
    """
    return asyncio.run(awaitable)

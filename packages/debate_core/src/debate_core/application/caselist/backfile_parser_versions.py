"""Which backfiles have no parsed-store directory at the running parser version (`v1-e40-t46`).

Nothing re-parses a backfile after a parser bump: the weekly run parses only the caselists it
follows, and `caselist backfile-import` runs once per backfile, by hand. On 2026-11-12 hspolicy25's
parsed store held only `2026.10.27-docx-7` while the weekly run and the other backfiles were at
`2026.11.03-docx-9`, and nothing said so. `caselist runs --remote`, which the operator reads after
every weekly run, now names each backfile like that (the PM's rulings, 2026-11-12).

## The rule

* **The backfiles** are `caselist.backfile_caselists`, the setting `caselist backfile-import` and
  the pull's refusal read (:mod:`debate_core.application.caselist.backfiles`), in its order.
* **The reference version** is the parser version the newest run that did not fail recorded
  restoring the parsed store at (its details' `bucket_run.restore.parsed_version`, which a
  bucket-mode run writes from its own build), among the runs read. Failing that, this build's
  parser version, the one the parse stage stamps. Which was used is said on the line and in
  `--json`.
* **A backfile is named** when none of its version directories is at the reference version, any
  generation of it (`_reparse-2` too). It is named with every parser version it does hold, newest
  first, each once; with none, it is not imported, which is not an error. A backfile that has a
  directory at the reference version is never named, whatever older ones it also holds.
* **It is informational.** It changes no exit status, verdict or overdue warning.

The one read it adds is each backfile's version directories in the parsed store, through
:class:`~debate_core.application.ports.version_directories.VersionDirectoryPlace`: a delimited
listing of `parsed/<backfile>/` in the bucket, never of every caselist. Counts and parser-version
labels only, as every run record is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.application.ports.version_directories import VersionDirectoryPlace
from debate_core.application.sync_runs import RecordedRun

__all__ = [
    "BackfileBehind",
    "BackfileParserVersions",
    "ReferenceSource",
    "ReferenceVersion",
    "backfile_parser_versions",
    "reference_version",
]


class ReferenceSource(StrEnum):
    """Where the reference version came from, as `--json` gives it."""

    THIS_BUILD = "this_build"
    """This build's parser version: no run read recorded one."""
    NEWEST_RUN = "newest_run"
    """The newest run read that did not fail and recorded the parser version it restored at."""


@dataclass(frozen=True, slots=True)
class ReferenceVersion:
    """The parser version each backfile is judged against, and where it came from."""

    parser_version: str
    source: ReferenceSource
    run_id: str | None = None
    """The run it was read from, for :attr:`ReferenceSource.NEWEST_RUN`; else `None`."""

    @property
    def described(self) -> str:
        """`parser 2026.11.03-docx-9 (this build)`, or `(recorded by run <run id>)`."""
        source = "this build" if self.run_id is None else f"recorded by run {self.run_id}"
        return f"parser {self.parser_version} ({source})"

    def as_json(self) -> dict[str, object]:
        return {"parser_version": self.parser_version, "source": str(self.source), "run_id": self.run_id}


@dataclass(frozen=True, slots=True)
class BackfileBehind:
    """One backfile with no directory at the reference version, and the parser versions it holds."""

    caselist: str
    parser_versions: tuple[str, ...]
    """Newest first, each once; empty for a backfile with no parsed store."""

    @property
    def imported(self) -> bool:
        return bool(self.parser_versions)

    def as_json(self) -> dict[str, object]:
        return {
            "caselist": self.caselist,
            "imported": self.imported,
            "parser_versions": list(self.parser_versions),
        }


@dataclass(frozen=True, slots=True)
class BackfileParserVersions:
    """The backfiles checked against one reference version, and the ones named."""

    reference: ReferenceVersion
    backfiles_checked: int
    named: tuple[BackfileBehind, ...]

    def lines(self) -> tuple[str, ...]:
        """What `caselist runs --remote` prints below its table; nothing when there are no backfiles."""
        if not self.backfiles_checked:
            return ()
        if not self.named:
            return (f"All {self.backfiles_checked} backfile(s) are at {self.reference.described}.",)
        return (
            f"{len(self.named)} of {self.backfiles_checked} backfile(s) have no parsed-store directory "
            f"at {self.reference.described}:",
            *(
                f"  {one.caselist}: holds {', '.join(one.parser_versions)}"
                if one.imported
                else f"  {one.caselist}: not imported (no parsed store)"
                for one in self.named
            ),
        )

    def as_json(self) -> dict[str, object]:
        return {
            "reference": self.reference.as_json(),
            "backfiles_checked": self.backfiles_checked,
            "named": [one.as_json() for one in self.named],
        }


def reference_version(runs: Sequence[RecordedRun], *, build_version: str) -> ReferenceVersion:
    """The newest of `runs` that did not fail and recorded a restored parser version; else this build's."""
    recorded = [
        (run.record.started_at, run.record.run_id, version)
        for run in runs
        if run.record.succeeded and (version := _restored_parser_version(run)) is not None
    ]
    if not recorded:
        return ReferenceVersion(parser_version=build_version, source=ReferenceSource.THIS_BUILD)
    _, run_id, version = max(recorded)
    return ReferenceVersion(parser_version=version, source=ReferenceSource.NEWEST_RUN, run_id=run_id)


def _restored_parser_version(run: RecordedRun) -> str | None:
    bucket_run = run.details.bucket_run if run.details is not None else None
    restore = bucket_run.restore if bucket_run is not None else None
    return restore.parsed_version if restore is not None else None


async def backfile_parser_versions(
    place: VersionDirectoryPlace, *, backfiles: Sequence[str], reference: ReferenceVersion
) -> BackfileParserVersions:
    """List each of `backfiles`' version directories in `place` and name those behind `reference`."""
    named: list[BackfileBehind] = []
    for caselist in backfiles:
        held = {parse_version_directory(name)[0] for name in await place.version_directories(caselist)}
        if reference.parser_version not in held:
            named.append(BackfileBehind(caselist, tuple(sorted(held, reverse=True))))
    return BackfileParserVersions(reference=reference, backfiles_checked=len(backfiles), named=tuple(named))

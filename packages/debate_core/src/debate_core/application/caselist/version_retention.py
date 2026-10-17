"""Which parsed-store version directories are superseded, and retiring them (`v1-e31-t16`).

`debate-research caselist retire` is a thin command over this module. The rule is written for
readers in `docs/data/parsed-card-store.md` ("Retention"); this is its definition.

## The rule

Every directory is judged against **this build's parser version**, in one place at a time:

* **Current**: the newest generation of this build's parser version. What `caselist parse` writes
  to and `--publish` copies. Never retired.
* **Newer than this build**: a parser version that sorts after this build's, so a newer build
  wrote it. Never retired by this build, which cannot know what supersedes it.
* **Superseded**: anything that sorts below the current directory, an earlier parser version or an
  earlier generation of this one. Nothing writes to it again or reads it. Retired on request.
* **Not yet superseded**: older than this build's parser version, in a place that has no current
  directory yet, such as a bucket the new directory has not been published to. Kept: retiring it
  would leave that place with nothing to read.

Directories sort as the parsed store sorts them: by parser version, then generation
(:func:`~debate_core.application.ports.parsed_store.parse_version_directory`). A parser version
begins with its date, so that order is the order they were written in.

## Retiring takes a dry run and a confirmation

A plan lists every directory and what it holds, and is all a run without `--execute` does. To act,
the operator names the directories (`--version`, from the listing) and passes the plan's
confirmation code, a digest of what the dry run showed: the place, the directories and their counts.
A plan whose code differs from the one given is refused, so a directory that changed since the dry
run, or a place other than the one the dry run read, is never acted on. Every refusal is a reason
code on the plan, and :meth:`VersionDirectoryRetention.execute` checks again rather than trusting
its caller.

How a place retires is its own (:mod:`debate_core.application.ports.version_directories`): this
machine deletes the directory, and the bucket tags its objects for the lifecycle rule.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.application.ports.version_directories import (
    DirectoryContents,
    RetirementMethod,
    VersionDirectoryPlace,
)

__all__ = [
    "CONFIRMATION_LENGTH",
    "DirectoryRow",
    "RetentionPlan",
    "RetentionRefusal",
    "RetentionRefused",
    "RetentionResult",
    "Standing",
    "VersionDirectoryRetention",
    "standings",
]

CONFIRMATION_LENGTH: Final = 12
"""Hex characters of the plan digest an operator types back."""


class Standing(StrEnum):
    """Where a version directory stands against this build's parser version."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    NEWER_THAN_THIS_BUILD = "newer_than_this_build"
    NOT_YET_SUPERSEDED = "not_yet_superseded"


def standings(names: Sequence[str], parser_version: str) -> dict[str, Standing]:
    """Each of one caselist's version directories in one place, judged by the rule above."""
    generations = [
        generation
        for name in names
        for named, generation in [parse_version_directory(name)]
        if named == parser_version
    ]
    current = (parser_version, max(generations)) if generations else None
    judged: dict[str, Standing] = {}
    for name in names:
        key = parse_version_directory(name)
        if key[0] > parser_version:
            judged[name] = Standing.NEWER_THAN_THIS_BUILD
        elif current is None:
            judged[name] = Standing.NOT_YET_SUPERSEDED
        elif key == current:
            judged[name] = Standing.CURRENT
        else:
            judged[name] = Standing.SUPERSEDED
    return judged


@dataclass(frozen=True, slots=True)
class DirectoryRow:
    caselist: str
    version: str
    standing: Standing
    contents: DirectoryContents


@dataclass(frozen=True, slots=True)
class RetentionRefusal:
    """Why a plan cannot be executed. `code` is what `--json` reports."""

    code: str
    message: str
    caselist: str | None = None
    version: str | None = None


#: The refusal a named directory gets for its standing, when it is not superseded.
_STANDING_REFUSALS: Final = {
    Standing.CURRENT: (
        "CURRENT_VERSION_DIRECTORY",
        "is the current directory of parser version {parser_version}; it is never retired",
    ),
    Standing.NEWER_THAN_THIS_BUILD: (
        "NEWER_THAN_THIS_BUILD",
        "was written by a parser version newer than this build's {parser_version}; a newer build retires it",
    ),
    Standing.NOT_YET_SUPERSEDED: (
        "NOT_YET_SUPERSEDED",
        "is not superseded here yet: this place has no directory of parser version {parser_version}",
    ),
}


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """Every version directory in the caselists asked for, in one place, and what a run would do."""

    location: str
    method: RetirementMethod
    parser_version: str
    restore: bool
    named: tuple[str, ...]
    """The directories the operator named with `--version`; empty for a listing."""
    rows: tuple[DirectoryRow, ...]
    refusals: tuple[RetentionRefusal, ...]
    """Why the named directories cannot be acted on, if they cannot. Empty when they can."""

    @property
    def selected(self) -> tuple[DirectoryRow, ...]:
        """What a run would retire or restore: the named directories, or every superseded one."""
        if self.restore:
            return tuple(row for row in self.rows if row.version in self.named)
        return tuple(
            row
            for row in self.rows
            if row.standing is Standing.SUPERSEDED and (not self.named or row.version in self.named)
        )

    @property
    def confirmation(self) -> str:
        """The code `--confirm` takes: a digest of the place, the action and the selected directories."""
        shown = {
            "location": self.location,
            "action": "restore" if self.restore else str(self.method),
            "directories": [
                [row.caselist, row.version, row.contents.objects, row.contents.bytes] for row in self.selected
            ],
        }
        digest = hashlib.sha256(json.dumps(shown, sort_keys=True).encode()).hexdigest()
        return digest[:CONFIRMATION_LENGTH]

    def refusal(self, confirmation: str | None) -> RetentionRefusal | None:
        """Why this plan may not be executed with `confirmation`, or `None` when it may."""
        if self.refusals:
            return self.refusals[0]
        if not self.named:
            return RetentionRefusal(
                code="VERSION_NOT_NAMED",
                message="name each directory to retire with --version, as the dry run lists it",
            )
        if confirmation != self.confirmation:
            return RetentionRefusal(
                code="CONFIRMATION_MISMATCH",
                message=(
                    "the confirmation code is not this plan's: run the dry run again, read it, and "
                    "pass the code it prints"
                    if confirmation
                    else "pass the confirmation code the dry run prints"
                ),
            )
        return None


@dataclass(frozen=True, slots=True)
class RetentionResult:
    plan: RetentionPlan
    acted_on: tuple[tuple[DirectoryRow, int], ...]
    """Each directory acted on, with how many objects were deleted, tagged or untagged."""


class RetentionRefused(ValueError):
    """`execute` was asked to act on a plan that refuses. The caller should have checked."""

    def __init__(self, refusal: RetentionRefusal) -> None:
        self.refusal = refusal
        super().__init__(f"{refusal.code}: {refusal.message}")


class VersionDirectoryRetention:
    """Plans and carries out the retirement of superseded version directories in one place."""

    def __init__(self, place: VersionDirectoryPlace, *, parser_version: str) -> None:
        self._place = place
        self._parser_version = parser_version

    async def plan(
        self,
        *,
        caselists: Sequence[str] = (),
        versions: Sequence[str] = (),
        restore: bool = False,
    ) -> RetentionPlan:
        """List every directory of `caselists` (all, when none are named) and judge `versions`."""
        chosen = tuple(caselists) or await self._place.caselists()
        named = tuple(dict.fromkeys(versions))
        rows: list[DirectoryRow] = []
        for caselist in sorted(chosen):
            names = await self._place.version_directories(caselist)
            judged = standings(names, self._parser_version)
            for name in sorted(names, key=parse_version_directory):
                candidate = name in named if named else judged[name] is Standing.SUPERSEDED
                contents = await self._place.contents(
                    caselist, name, count_tagged=candidate and self._place.method is RetirementMethod.TAG
                )
                rows.append(DirectoryRow(caselist, name, judged[name], contents))
        return RetentionPlan(
            location=self._place.location,
            method=self._place.method,
            parser_version=self._parser_version,
            restore=restore,
            named=named,
            rows=tuple(rows),
            refusals=self._refusals(rows, named, restore=restore),
        )

    async def execute(self, plan: RetentionPlan, *, confirmation: str | None) -> RetentionResult:
        """Retire, or with `restore` untag, the plan's selected directories. Checks the plan first."""
        refusal = plan.refusal(confirmation)
        if refusal is not None:
            raise RetentionRefused(refusal)
        acted: list[tuple[DirectoryRow, int]] = []
        for row in plan.selected:
            if plan.restore:
                count = await self._place.restore(row.caselist, row.version)
            else:
                count = await self._place.retire(row.caselist, row.version)
            acted.append((row, count))
        return RetentionResult(plan=plan, acted_on=tuple(acted))

    def _refusals(
        self, rows: Sequence[DirectoryRow], named: Sequence[str], *, restore: bool
    ) -> tuple[RetentionRefusal, ...]:
        refusals: list[RetentionRefusal] = []
        if restore and self._place.method is RetirementMethod.DELETE:
            refusals.append(
                RetentionRefusal(
                    code="NOTHING_TO_RESTORE_HERE",
                    message=f"retiring on {self._place.location} deletes; only a bucket's can be undone",
                )
            )
        for version in named:
            found = [row for row in rows if row.version == version]
            if not found:
                refusals.append(
                    RetentionRefusal(
                        code="NO_SUCH_VERSION_DIRECTORY",
                        message=f"no caselist asked for has a directory {version} on {self._place.location}",
                        version=version,
                    )
                )
                continue
            if restore:
                continue
            for row in found:
                if row.standing is Standing.SUPERSEDED:
                    continue
                code, reason = _STANDING_REFUSALS[row.standing]
                refusals.append(
                    RetentionRefusal(
                        code=code,
                        message=f"{row.caselist}/{row.version} "
                        + reason.format(parser_version=self._parser_version),
                        caselist=row.caselist,
                        version=row.version,
                    )
                )
        return tuple(refusals)

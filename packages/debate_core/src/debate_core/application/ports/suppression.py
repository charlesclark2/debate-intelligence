"""The suppression list and the removal log: what a takedown leaves behind so it stays done.

A removal under `docs/policies/caselist-data-use.md` deletes a source everywhere it is stored. That
is the easy half. OpenCaselist's weekly archives are **cumulative**, so the file a team asked us to
remove is in next Monday's archive too, and the Monday after; without something that remembers the
request, the next import puts it straight back. The suppression list is that memory, and every path
that can store a source — both importers, the publisher, `store sync` — consults it
(`v1-e30-t07-source-removal`).

## Two records, both append-only

`suppression-list.jsonl`
    One :class:`SuppressionEntry` per line. A sha256 is suppressed while its *latest* entry is a
    suppression; a mistaken removal is reversed by appending an un-suppress entry, never by
    editing a line. The list is the evidence that a request was honoured, and a file that can be
    rewritten is not evidence.
`removal-log.jsonl`
    One :class:`RemovalLogEntry` per execution of `caselist remove` or `caselist unsuppress`.

Each lives in two places — the environment's data directory and
`manifests/_suppression/` in its bucket — and the two are merged as a set union whenever a command
holds both (:class:`~debate_core.application.caselist.suppression.RecordedSuppressionList`). Neither
side is ever rewritten or truncated: an :class:`AppendOnlyRecord` can only read its lines and add
lines to the end.

## No names, by construction

Neither record may carry a school name, a team code or a person's name (the policy's personal-data
rule 6, and the task spec's first forbidden item). That is not left to the caller's care: every
field here is a digest, a date, an enumerated code or a request id matching
:data:`REQUEST_ID_PATTERN`, and the models forbid extra keys. There is no field a name could be
written into. A takedown log that identified the person who asked for the takedown would defeat
its own purpose.

## Two scopes of suppression

A whole **source**: these bytes are never stored again, by any import, under any path. What a
removal of a file nobody else holds appends.

One **disclosure**: these bytes, at this archive path of this caselist, are never recorded again —
but the bytes themselves stay for the other team or camp file that also holds them. What a `--team`
removal of a *shared* file appends without `--include-shared`; the cumulative archive still holds
the requesting team's copy at the same path, and without this the next import would record it as
their disclosure again. The path is stored only as :func:`disclosure_digest`, the SHA-256 of the
caselist and path, never as text. Reversing that digest needs the archive in hand, exactly as
reversing a file's own sha256 does, so it identifies no more than the sha256 values the list was
always going to hold (Deviation recorded in the session report; spec ac4 amended).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Final, Literal, Protocol, Self, runtime_checkable

from pydantic import StringConstraints, model_validator

from debate_core.application.errors import DomainError
from debate_core.domain import Sha256Hex
from debate_core.domain.base import DomainModel, UtcDatetime

__all__ = [
    "REINSTATEMENT_REASONS",
    "REMOVAL_REASONS",
    "REQUEST_ID_PATTERN",
    "SUPPRESSION_SCHEMA_VERSION",
    "AppendOnlyRecord",
    "AppendOnlyViolation",
    "InboxRewriteRecord",
    "ReasonCode",
    "RemovalLog",
    "RemovalLogEntry",
    "RemovalLogKind",
    "RemovalOutcome",
    "RemovalSelectorKind",
    "RequestId",
    "SuppressionAction",
    "SuppressionEntry",
    "SuppressionList",
    "SuppressionState",
    "UnreadableAppendOnlyRecord",
    "canonical_line",
    "disclosure_digest",
]

SUPPRESSION_SCHEMA_VERSION: Final = 1
"""Version of a suppression-list or removal-log line. Bumped only by a change an old reader breaks on."""

REQUEST_ID_PATTERN: Final = r"^RM-[0-9]{4}-[0-9]{2,4}$"
"""`RM-2026-01`: the register id `docs/runbooks/caselist-removal.md` step 1 assigns a request.

A pattern rather than free text so that the request id cannot become the field a name is typed
into: `RM-`, a year, a sequence number, and nothing else.
"""

RequestId = Annotated[str, StringConstraints(pattern=REQUEST_ID_PATTERN)]

_ERROR_CODE_PATTERN: Final = r"^[A-Z][A-Z0-9_]*$"


class ReasonCode(StrEnum):
    """Why an entry was appended: the register's codes (`caselist-removal.md` step 1), two for reversal."""

    REQUESTED_BY_TEAM = "REQUESTED_BY_TEAM"
    REQUESTED_BY_SCHOOL = "REQUESTED_BY_SCHOOL"
    REQUESTED_BY_SITE_ADMIN = "REQUESTED_BY_SITE_ADMIN"
    REQUESTED_BY_CAMP = "REQUESTED_BY_CAMP"
    POLICY = "POLICY"
    """Imported outside the data-use policy; the coach's own removal."""
    LEGAL = "LEGAL"
    REMOVED_IN_ERROR = "REMOVED_IN_ERROR"
    """Un-suppress: the removal was a mistake (`caselist-removal.md`, "If you removed the wrong thing")."""
    REQUEST_WITHDRAWN = "REQUEST_WITHDRAWN"
    """Un-suppress: the requester withdrew the request in writing."""


REMOVAL_REASONS: Final = frozenset(
    {
        ReasonCode.REQUESTED_BY_TEAM,
        ReasonCode.REQUESTED_BY_SCHOOL,
        ReasonCode.REQUESTED_BY_SITE_ADMIN,
        ReasonCode.REQUESTED_BY_CAMP,
        ReasonCode.POLICY,
        ReasonCode.LEGAL,
    }
)
"""The codes a suppression may carry."""

REINSTATEMENT_REASONS: Final = frozenset({ReasonCode.REMOVED_IN_ERROR, ReasonCode.REQUEST_WITHDRAWN})
"""The codes an un-suppress may carry."""


class SuppressionAction(StrEnum):
    SUPPRESS = "SUPPRESS"
    UNSUPPRESS = "UNSUPPRESS"


def canonical_line(model: DomainModel) -> str:
    """One model as one JSONL line: sorted keys, fixed separators, so equal entries are equal text.

    Equal text is what lets two copies of the list be merged as a set union of lines.
    """
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def disclosure_digest(caselist: str, source_path: str) -> Sha256Hex:
    """The SHA-256 a disclosure-scoped suppression stores in place of the archive path.

    Of `<caselist>/<path>`, UTF-8: the path alone would make one team's directory in two seasons'
    caselists one entry.
    """
    return hashlib.sha256(f"{caselist}/{source_path}".encode()).hexdigest()


class SuppressionEntry(DomainModel):
    """One line of the suppression list.

    A `SUPPRESS` with no :attr:`disclosure` suppresses the whole source; with one, only that
    disclosure. An `UNSUPPRESS` lifts every suppression of :attr:`sha256` recorded before it.
    """

    schema_version: Literal[1] = SUPPRESSION_SCHEMA_VERSION
    action: SuppressionAction
    sha256: Sha256Hex
    disclosure: Sha256Hex | None = None
    """:func:`disclosure_digest` of the one disclosure suppressed, or `None` for the whole source."""
    recorded_at: UtcDatetime
    """When the entry was appended. "Latest entry wins" is decided by this, not by line order."""
    reason: ReasonCode
    request_id: RequestId | None = None
    """The register id. Required on a suppression; optional on an un-suppress."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.action is SuppressionAction.SUPPRESS:
            if self.request_id is None:
                raise ValueError("a suppression needs the request id it honours")
            if self.reason not in REMOVAL_REASONS:
                raise ValueError(f"{self.reason} is not a reason to suppress")
        else:
            if self.disclosure is not None:
                raise ValueError("an un-suppress lifts every suppression of a sha256 and names no disclosure")
            if self.reason not in REINSTATEMENT_REASONS:
                raise ValueError(f"{self.reason} is not a reason to un-suppress")
        return self

    def to_line(self) -> str:
        return canonical_line(self)

    @classmethod
    def from_line(cls, line: str) -> SuppressionEntry:
        return cls.model_validate_json(line)


@dataclass(frozen=True, slots=True)
class SuppressionState:
    """What the list currently suppresses, after every entry has been applied in time order.

    Build it with :meth:`from_entries`. The order of lines in a file is irrelevant — the local and
    remote copies can hold the same entries in different orders — because entries are applied by
    :attr:`SuppressionEntry.recorded_at`, ties broken by their text.
    """

    sources: frozenset[Sha256Hex] = frozenset()
    """Digests suppressed as a whole source."""

    disclosures: frozenset[tuple[Sha256Hex, Sha256Hex]] = frozenset()
    """`(sha256, disclosure digest)` pairs suppressed as one disclosure each."""

    latest: dict[Sha256Hex, SuppressionEntry] = field(default_factory=lambda: {})
    """The most recent entry for every digest the list mentions, suppressed or not."""

    @classmethod
    def from_entries(cls, entries: Iterable[SuppressionEntry]) -> SuppressionState:
        sources: set[str] = set()
        disclosures: set[tuple[str, str]] = set()
        latest: dict[str, SuppressionEntry] = {}
        for entry in sorted(entries, key=lambda one: (one.recorded_at, one.to_line())):
            latest[entry.sha256] = entry
            if entry.action is SuppressionAction.UNSUPPRESS:
                sources.discard(entry.sha256)
                disclosures = {pair for pair in disclosures if pair[0] != entry.sha256}
            elif entry.disclosure is None:
                sources.add(entry.sha256)
            else:
                disclosures.add((entry.sha256, entry.disclosure))
        return cls(sources=frozenset(sources), disclosures=frozenset(disclosures), latest=latest)

    def suppresses_source(self, sha256: str) -> bool:
        """Whether these bytes may not be stored at all."""
        return sha256 in self.sources

    def suppresses(self, sha256: str, *, disclosure: str | None) -> bool:
        """Whether a member with these bytes, at the disclosure with this digest, may not be recorded.

        `disclosure` is :func:`disclosure_digest` of the member's caselist and path, or `None` for
        an import that records no disclosures (OpenEv), which only a whole-source entry stops.
        """
        return sha256 in self.sources or (disclosure is not None and (sha256, disclosure) in self.disclosures)

    def is_suppressed(self, sha256: str) -> bool:
        """Whether any suppression of `sha256` is in force, whole-source or disclosure-scoped."""
        return sha256 in self.sources or any(pair[0] == sha256 for pair in self.disclosures)

    def __len__(self) -> int:
        return len(self.sources) + len(self.disclosures)


class RemovalLogKind(StrEnum):
    REMOVAL = "REMOVAL"
    UNSUPPRESS = "UNSUPPRESS"


class RemovalOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    """Something failed part-way; re-running the same command finishes it. `error_code` says what failed."""


class RemovalSelectorKind(StrEnum):
    """Whether the operator named a file or a team. Never *which* team."""

    SOURCE = "SOURCE"
    TEAM = "TEAM"


class InboxRewriteRecord(DomainModel):
    """One inbox archive a removal rewrote without the removed files: its digest before and after.

    The next pull imports the rewritten file and its manifest names the `after` digest; this pair is
    what ties that digest back to the archive as downloaded (`v1-e30-t09`).
    """

    from_sha256: Sha256Hex
    to_sha256: Sha256Hex


class RemovalLogEntry(DomainModel):
    """One line of the removal log: one execution, in sha256 values, counts and codes.

    The request id, the date, the reason code, the environment and the sha256 values, as the policy
    requires, and counts of what was deleted so the register can be filled in without re-running
    anything. Never a school, a team code, a path or a name — see the module docstring.
    """

    schema_version: Literal[1] = SUPPRESSION_SCHEMA_VERSION
    kind: RemovalLogKind
    recorded_at: UtcDatetime
    request_id: RequestId | None = None
    reason: ReasonCode
    environment: Annotated[str, StringConstraints(pattern=r"^(dev|prod|test)$")]
    outcome: RemovalOutcome
    selector: RemovalSelectorKind | None = None
    """What kind of selector a removal was given. `None` on an un-suppress."""
    include_shared: bool = False
    removed_sha256: tuple[Sha256Hex, ...] = ()
    """Sources removed whole and suppressed: blob, records, objects and every version."""
    withdrawn_sha256: tuple[Sha256Hex, ...] = ()
    """Shared sources kept for their other holder, with only the requester's disclosures withdrawn."""
    unsuppressed_sha256: tuple[Sha256Hex, ...] = ()
    local_records_deleted: int = 0
    local_files_deleted: int = 0
    manifests_rewritten: int = 0
    manifest_rows_dropped: int = 0
    s3_versions_deleted: int = 0
    inbox_files_deleted: int = 0
    """Files deleted from the sync's inbox (`v1-e30-t09`): removed camp files, and imported archives."""
    inbox_files_rewritten: int = 0
    """Archives in the inbox, still waiting to be imported, rewritten without the removed files."""
    inbox_rewrites: tuple[InboxRewriteRecord, ...] = ()
    error_code: Annotated[str, StringConstraints(pattern=_ERROR_CODE_PATTERN)] | None = None

    def to_line(self) -> str:
        return canonical_line(self)

    @classmethod
    def from_line(cls, line: str) -> RemovalLogEntry:
        return cls.model_validate_json(line)


class UnreadableAppendOnlyRecord(DomainError):
    """A copy of the suppression list or removal log holds a line this build cannot read.

    Names the copy and the line number, never the line. Nothing is repaired: a list that cannot be
    read cannot be honoured, and a list that was "fixed" is no longer the record of what was asked.
    """

    def __init__(self, location: str, line_number: int, reason: str) -> None:
        self.location = location
        self.line_number = line_number
        super().__init__(f"{location} line {line_number} is not readable: {reason}; nothing was changed")


class AppendOnlyViolation(DomainError):
    """A write would have changed a line already in an append-only record, or one changed under us."""

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        super().__init__(f"refusing to write {location}: {reason}")


@runtime_checkable
class AppendOnlyRecord(Protocol):
    """One copy of an append-only JSONL record: the local file, or the object in the bucket.

    It can read its lines and add lines to the end, and that is all. There is no method that
    replaces a line, removes one or truncates the record, and an implementation must make sure its
    own append cannot do any of those either.
    """

    @property
    def location(self) -> str:
        """Where this copy lives, for messages: a path, or `s3://bucket/key`. Never its contents."""
        ...

    async def read_lines(self) -> tuple[str, ...]:
        """Every line, in file order, without newlines. A record that does not exist yet has none.

        Raises :class:`UnreadableAppendOnlyRecord` for a record whose last line was never finished.
        """
        ...

    async def append_lines(self, lines: Sequence[str]) -> None:
        """Add `lines` to the end, each newline-terminated, leaving every existing byte where it was."""
        ...


@runtime_checkable
class SuppressionList(Protocol):
    """The removal suppression list, read and appended to as entries.

    What the importers, the publisher, `store sync` and the V2 debate tub (`v2-e35-t05`) consult.
    :meth:`entries` is the union of every copy the implementation holds; :meth:`append` writes the
    new entries — and any entry one copy has that another lacks — to every copy.
    """

    async def entries(self) -> tuple[SuppressionEntry, ...]: ...

    async def append(self, entries: Sequence[SuppressionEntry]) -> None: ...


@runtime_checkable
class RemovalLog(Protocol):
    """The removal log: one entry per execution, local and in the bucket, merged like the list."""

    async def entries(self) -> tuple[RemovalLogEntry, ...]: ...

    async def append(self, entries: Sequence[RemovalLogEntry]) -> None: ...

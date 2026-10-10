"""The errors that cross a port boundary.

Every port in :mod:`debate_core.application.ports` raises from this hierarchy and nothing else.
That is what makes adapters interchangeable: a use case that catches :class:`NotFound` keeps
working whether the record was missing from a SQLite file, an S3 bucket or a DynamoDB table, and
no `sqlite3.OperationalError`, `botocore` `ClientError` or `httpx` exception ever reaches a
service (architecture proposal §6).

An adapter therefore translates its library's failures at its own edge. Anything it cannot
translate is a bug in the adapter, not a condition the application layer is expected to handle.

The hierarchy::

    DomainError
    ├── NotFound
    ├── Conflict
    │   ├── AlreadyExists
    │   └── RevisionMismatch
    ├── InvalidCursor
    ├── BlobIntegrityError
    ├── SnapshotIntegrityError
    ├── ArchiveTooLarge
    ├── UnreadableArchive
    ├── StoreError
    │   ├── StoreAccessDenied
    │   │   └── LocalStoreAccessDenied
    │   ├── StoreCredentialsExpired
    │   └── StoreUnavailable
    ├── InvalidModelOutput
    └── ProviderError
        ├── ProviderUnavailable
        └── ProviderRateLimited

Each class keeps the facts of the failure as attributes rather than only in its message, so a CLI
can render "card 01J… was edited by someone else" instead of parsing a string.

## Error codes

A failure is reported to a program by one word, its **error code**: the class name in upper snake
case, `StoreUnavailable` → `STORE_UNAVAILABLE` (:func:`error_code_of`). It is the `error.code` of
the CLI's `--json` envelope, the `code` of each object a `store sync` or a `caselist publish` could
not move, and what a failed stage of `caselist pull` records (`v1-e34-t13`). There is one
vocabulary, defined here, because the services that record a code and the command that turns codes
into an exit status must mean the same thing by it; `debate_cli.exit_codes` reads it from here, and
this package never reads anything from there.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import ClassVar, Final

__all__ = [
    "UNMODELLED_ERROR_CODE",
    "AlreadyExists",
    "ArchiveTooLarge",
    "BlobIntegrityError",
    "Conflict",
    "DomainError",
    "InvalidCursor",
    "InvalidModelOutput",
    "LocalStoreAccessDenied",
    "NotFound",
    "ProviderError",
    "ProviderRateLimited",
    "ProviderUnavailable",
    "RevisionMismatch",
    "SnapshotIntegrityCheck",
    "SnapshotIntegrityError",
    "StoreAccessDenied",
    "StoreCredentialsExpired",
    "StoreError",
    "StoreUnavailable",
    "UnreadableArchive",
    "error_code_of",
    "error_code_of_class",
    "reported_error_code",
]


class DomainError(Exception):
    """Base class for every error raised across an application port.

    Catching this catches everything the ports can fail with, which is what the CLI's and API's
    top-level error handlers do. It deliberately derives from :class:`Exception`, not from a
    library-specific base, so no caller needs to import an adapter to handle a failure.
    """


# --------------------------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------------------------


class NotFound(DomainError):
    """A record or blob that was asked for by key does not exist.

    Ports raise this from `get`-style methods, which exist for callers that treat absence as a
    failure. Callers that treat absence as an ordinary answer use the `find_*` methods, which
    return `None` instead.
    """

    def __init__(self, entity: str, key: str) -> None:
        self.entity = entity
        """What was being looked up, e.g. `"Card"` or `"snapshot blob"`."""
        self.key = key
        """The key that produced no record."""
        super().__init__(f"{entity} not found: {key}")


class InvalidCursor(DomainError):
    """A pagination cursor was not one this repository issued.

    Cursors are opaque strings minted by a repository and only meaningful to the implementation
    that minted them (a SQLite key, a DynamoDB `LastEvaluatedKey`). Handing one repository
    another's cursor is a programming error, and it is reported rather than silently treated as
    "start from the beginning".
    """

    def __init__(self, cursor: str) -> None:
        self.cursor = cursor
        """The cursor value that could not be decoded."""
        super().__init__(f"not a cursor issued by this repository: {cursor!r}")


# --------------------------------------------------------------------------------------------
# Write conflicts
# --------------------------------------------------------------------------------------------


class Conflict(DomainError):
    """A write could not be applied because the stored state was not what the caller assumed."""


class AlreadyExists(Conflict):
    """A create was asked for, but a record with that key is already stored."""

    def __init__(self, entity: str, key: str) -> None:
        self.entity = entity
        """What was being created, e.g. `"Card"`."""
        self.key = key
        """The key that is already taken."""
        super().__init__(f"{entity} already exists: {key}")


class RevisionMismatch(Conflict):
    """An optimistic-concurrency check failed: the stored revision moved since it was read.

    This is the error that keeps a background reprocessing job from silently overwriting a
    student's edit (architecture proposal §7). It is an expected outcome, not a system fault: the
    caller re-reads the record, re-applies its change and writes again, or tells the user their
    copy is stale.
    """

    def __init__(
        self,
        entity: str,
        key: str,
        expected_revision: int,
        actual_revision: int | None = None,
    ) -> None:
        self.entity = entity
        """What was being written, e.g. `"Card"`."""
        self.key = key
        """The key of the record whose revision moved."""
        self.expected_revision = expected_revision
        """The revision the caller read and expected to still be stored."""
        self.actual_revision = actual_revision
        """The revision actually stored, or `None` when the record has since been deleted."""
        stored = "the record no longer exists" if actual_revision is None else f"stored {actual_revision}"
        super().__init__(f"{entity} {key} changed: expected revision {expected_revision}, {stored}")


# --------------------------------------------------------------------------------------------
# Stored-content integrity
# --------------------------------------------------------------------------------------------


class BlobIntegrityError(DomainError):
    """Stored bytes do not hash to the content-addressed key they are filed under.

    A snapshot is the anchor of every card cut from it, so a blob that no longer matches its key
    is never returned or repaired: the read fails loudly and the affected cards stay unverifiable
    (architecture proposal §8).
    """

    def __init__(self, key: str, actual_sha256: str | None = None) -> None:
        self.key = key
        """The content-addressed key the blob is stored under."""
        self.actual_sha256 = actual_sha256
        """The digest the stored bytes actually produce, when it was computed."""
        found = "" if actual_sha256 is None else f"; stored bytes hash to {actual_sha256}"
        super().__init__(f"blob {key} failed its integrity check{found}")


class SnapshotIntegrityCheck(StrEnum):
    """Which of a snapshot's integrity checks failed. Values are stable, for logs and reason codes."""

    UNKNOWN_NORMALIZER_VERSION = "unknown_normalizer_version"
    """The snapshot names a normalizer version this installation does not have. Its text cannot be
    re-verified here, so it is refused before anything is read."""

    RAW_BYTES_HASH = "raw_bytes_hash"
    """The raw blob's bytes do not hash to the snapshot's `sha256` or to its `raw_blob_key`."""

    RAW_BYTE_SIZE = "raw_byte_size"
    """The raw blob is not the `byte_size` the snapshot recorded."""

    NORMALIZED_BLOB_HASH = "normalized_blob_hash"
    """The normalized blob's bytes do not hash to the snapshot's `normalized_blob_key`."""

    NORMALIZED_BLOB_MALFORMED = "normalized_blob_malformed"
    """The normalized blob is not a canonical `debate-snapshot-text/1` document."""

    NORMALIZER_VERSION_MISMATCH = "normalizer_version_mismatch"
    """The normalized blob was written under a different normalizer version than the snapshot records."""

    NORMALIZED_TEXT_HASH = "normalized_text_hash"
    """The normalized text does not hash to the snapshot's `normalized_text_hash`."""


class SnapshotIntegrityError(DomainError):
    """A stored snapshot is not what its :class:`~debate_core.domain.SourceSnapshot` record says it is.

    Raised by :meth:`~debate_core.application.snapshot_service.SnapshotService.load` when re-hashing
    a snapshot's blobs, or reading its normalized text, disagrees with the record. Every card cut
    from such a snapshot is unverifiable until the source is retrieved again; nothing is repaired
    and no text is returned (architecture proposal §8).

    A blob that is simply absent is :class:`NotFound`, not this: a missing snapshot and a damaged
    one are different findings, and the verifier (`v1-e03-t04`) reports them differently.
    """

    def __init__(
        self,
        snapshot_id: str,
        check: SnapshotIntegrityCheck,
        *,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        self.snapshot_id = snapshot_id
        """The snapshot whose stored content failed."""
        self.check = check
        """Which check failed."""
        self.expected = expected
        """What the snapshot record says, when the check compares against a recorded value."""
        self.actual = actual
        """What the stored content actually produced, when it could be computed."""
        detail = ""
        if expected is not None or actual is not None:
            detail = f": expected {expected}, found {actual}"
        super().__init__(f"snapshot {snapshot_id} failed its integrity check {check.value}{detail}")


# --------------------------------------------------------------------------------------------
# Reaching the store at all
# --------------------------------------------------------------------------------------------


class ArchiveTooLarge(DomainError):
    """An archive is larger than this installation will open, so nothing was read from it.

    A deterministic answer the operator has to act on — point at the right file, or raise the
    ceiling in `settings.caselist` — rather than a bug or a provider being unavailable. It names
    the archive's own filename and never a member's path, because a member's path carries a school
    and a team code (`docs/policies/caselist-data-use.md`).
    """

    def __init__(self, *, measured: str, actual_bytes: int, limit_bytes: int, source: str) -> None:
        self.measured = measured
        """Which ceiling was exceeded: `archive` (size on disk) or `unpacked` (declared total)."""
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        self.source = source
        """The archive's own filename. Never a member's path."""
        super().__init__(
            f"{source} is {actual_bytes} bytes "
            f"{'on disk' if measured == 'archive' else 'unpacked'}, over this installation's "
            f"{limit_bytes}-byte ceiling; nothing was read from it"
        )


class UnreadableArchive(DomainError):
    """The path handed to an importer is neither a readable archive nor a directory."""

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        """The archive's own filename. Never a member's path."""
        self.reason = reason
        super().__init__(f"{source} cannot be read as an archive: {reason}")


class StoreError(DomainError):
    """A store could not be reached or refused the request, whatever it stores things in.

    The three errors below are the conditions a *remote* store adds to the ones a local directory
    already has, and they exist so that `botocore`'s `ClientError`, `NoCredentialsError` and
    `UnauthorizedSSOTokenError` stop at the adapter's edge
    (:mod:`debate_core.integrations.s3.errors`). They say nothing about AWS: a filesystem store
    raises :class:`StoreAccessDenied` when the operating system refuses a directory, and a future
    store on another cloud would map its own failures the same way.

    Catching this catches "the store is not answering" without catching
    :class:`NotFound`, which is an answer.
    """


class StoreAccessDenied(StoreError):
    """The credentials are valid, and they are not allowed to do this.

    Almost always a policy that does not grant the action rather than anything wrong with the
    request: an `EvidenceOperator` session listing the bucket root, or a `DebateMaintainer` session
    reaching for `debate-prod-evidence`, which ADR-0010 rule 4 denies on purpose.

    The message names the operation and the resource and nothing else. It never carries the
    credential, the session token or the object's contents.
    """

    def __init__(self, operation: str, resource: str, *, hint: str | None = None) -> None:
        self.operation = operation
        """The store operation that was refused, e.g. `"GetObject"`."""
        self.resource = resource
        """What it was refused on: a bucket, a key, a directory. Never a credential."""
        self.hint = hint
        """One line a CLI can print to say what to do about it, when there is one."""
        super().__init__(f"not allowed to {operation} {resource}" + (f": {hint}" if hint else ""))


class LocalStoreAccessDenied(StoreAccessDenied):
    """The operating system refused a directory of this machine's own store.

    Raised by the filesystem adapters, and by nothing that talks to a bucket, so a caller can tell
    the two refusals apart by type rather than by reading a message (`v1-e34-t13`). They have
    different fixes: this one is a permission on the environment's data directory, and a refusal
    by the bucket is a grant the profile lacks. Neither is an expired login.

    :attr:`resource` is the directory's *role* — "the blob directory" — and never its path.

    It is the same failure to a program as its parent: the same error code, so nothing that
    branches on `STORE_ACCESS_DENIED` has to learn a second word, and the same exit status.
    """

    ERROR_CODE: ClassVar[str] = "STORE_ACCESS_DENIED"


class StoreCredentialsExpired(StoreError):
    """There are no usable credentials: the SSO session expired, or there were never any.

    Split out from :class:`StoreAccessDenied` because the answer is different and boring — log in
    again — and because a wall of `botocore` traceback is the wrong way to tell an operator that.
    The adapter fills in :attr:`hint` with the exact command to run, so the CLI prints one line
    (`v1-e29-t05-evidence-sync-cli` ac4).
    """

    def __init__(self, message: str = "no usable AWS credentials", *, hint: str | None = None) -> None:
        self.hint = hint
        """The command that fixes it, e.g. `"aws sso login --profile debate-dev-evidence"`."""
        super().__init__(message + (f": {hint}" if hint else ""))


class StoreUnavailable(StoreError):
    """The store did not complete the request, and the reason is not one of the two above.

    A 500 from S3, a throttle, a timeout, a connection that never opened, or a response code this
    adapter has no more specific translation for. It is deliberately one class rather than a
    catalogue: a caller's response to all of it is to retry or to give up, and the underlying
    exception stays on `__cause__` for the log.

    It exists so that the promise in this module's first paragraph holds without exception — no
    `ClientError` reaches a service, not even an unrecognised one.
    """

    def __init__(self, operation: str, resource: str, message: str) -> None:
        self.operation = operation
        """The store operation that failed."""
        self.resource = resource
        """What it was attempted on."""
        super().__init__(f"{operation} on {resource} failed: {message}")


# --------------------------------------------------------------------------------------------
# Model output
# --------------------------------------------------------------------------------------------


class InvalidModelOutput(DomainError):
    """A model returned something that is not a valid instance of the requested output schema.

    Raised by :meth:`~debate_core.application.ports.providers.ModelRouter.invoke` after the
    router's own repair attempts, if any, have failed. It carries the prompt identity so a failing
    prompt version can be found without correlating logs.
    """

    def __init__(
        self,
        prompt_id: str,
        prompt_version: str,
        message: str,
        *,
        model_id: str | None = None,
    ) -> None:
        self.prompt_id = prompt_id
        """Identifier of the prompt whose output failed validation."""
        self.prompt_version = prompt_version
        """Semantic version of that prompt."""
        self.model_id = model_id
        """The model that produced the output, when the router resolved one."""
        by_model = "" if model_id is None else f" from {model_id}"
        super().__init__(f"invalid output{by_model} for prompt {prompt_id}@{prompt_version}: {message}")


# --------------------------------------------------------------------------------------------
# External providers
# --------------------------------------------------------------------------------------------


class ProviderError(DomainError):
    """Base class for failures of an external provider (search, fetch, model).

    A provider failure is a normal condition, not an outage of the platform: a federated search
    that loses one provider reports `PARTIAL` and names the provider that dropped out rather than
    failing the whole search (architecture proposal §9).
    """

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        """Name of the provider as it appears in settings and in `Search.provider_set`."""
        super().__init__(f"{provider}: {message}")


class ProviderUnavailable(ProviderError):
    """A provider could not be reached, timed out, or returned a server error."""

    def __init__(self, provider: str, message: str = "unavailable") -> None:
        super().__init__(provider, message)


class ProviderRateLimited(ProviderError):
    """A provider refused the call because the caller is over its rate limit.

    Separate from :class:`ProviderUnavailable` because the response is different: back off for
    `retry_after_seconds` and try again, rather than treat the provider as down.
    """

    def __init__(
        self,
        provider: str,
        message: str = "rate limited",
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        """Seconds to wait before retrying, when the provider stated a `Retry-After`."""
        wait = "" if retry_after_seconds is None else f" (retry after {retry_after_seconds}s)"
        super().__init__(provider, f"{message}{wait}")


# --------------------------------------------------------------------------------------------
# Error codes
# --------------------------------------------------------------------------------------------

UNMODELLED_ERROR_CODE: Final = "INTERNAL_ERROR"
"""The code of a failure that is not a :class:`DomainError`: an exception nobody modelled.

The CLI reports such an exception under the name of its exit status 70, and a failure a service
records instead of raising is recorded under the same word (:func:`reported_error_code`). It is on
no list of failures a retry may cure.
"""

_WORD_BOUNDARY: Final = re.compile(r"(?<!^)(?=[A-Z])")


def error_code_of_class(kind: type[BaseException]) -> str:
    """The error code instances of `kind` are reported under: `RevisionMismatch` → `REVISION_MISMATCH`.

    A class that refines another without being a different failure to a program names the code it
    keeps in `ERROR_CODE` (:class:`LocalStoreAccessDenied`); every other class is its own name.
    """
    declared = vars(kind).get("ERROR_CODE")
    if isinstance(declared, str):
        return declared
    return _WORD_BOUNDARY.sub("_", kind.__name__).upper()


def error_code_of(error: BaseException) -> str:
    """The error code of `error`, from its class: see :func:`error_code_of_class`.

    Defined for any exception, because the services that carry on past one object's failure catch
    an `OSError` beside the port errors and report each by its class (`FILE_NOT_FOUND_ERROR`).
    """
    return error_code_of_class(type(error))


def reported_error_code(error: BaseException) -> str:
    """The code the CLI would report `error` under had it ended the command, for a failure that did not.

    A :class:`DomainError`'s own code; :data:`UNMODELLED_ERROR_CODE` for anything else. A stage of
    `caselist pull` records its failures with this, so that a failure reads the same whether it
    stopped the run or one stage of it.
    """
    if isinstance(error, DomainError):
        return error_code_of(error)
    return UNMODELLED_ERROR_CODE

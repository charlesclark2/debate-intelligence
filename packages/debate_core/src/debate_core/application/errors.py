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
    ├── ArchiveTooLarge
    ├── UnreadableArchive
    ├── StoreError
    │   ├── StoreAccessDenied
    │   ├── StoreCredentialsExpired
    │   └── StoreUnavailable
    ├── InvalidModelOutput
    └── ProviderError
        ├── ProviderUnavailable
        └── ProviderRateLimited

Each class keeps the facts of the failure as attributes rather than only in its message, so a CLI
can render "card 01J… was edited by someone else" instead of parsing a string.
"""

from __future__ import annotations

__all__ = [
    "AlreadyExists",
    "ArchiveTooLarge",
    "BlobIntegrityError",
    "Conflict",
    "DomainError",
    "InvalidCursor",
    "InvalidModelOutput",
    "NotFound",
    "ProviderError",
    "ProviderRateLimited",
    "ProviderUnavailable",
    "RevisionMismatch",
    "StoreAccessDenied",
    "StoreCredentialsExpired",
    "StoreError",
    "StoreUnavailable",
    "UnreadableArchive",
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

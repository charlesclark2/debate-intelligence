"""The application layer: use cases, the ports they depend on, and the errors they raise.

This layer orchestrates. It holds no entity invariants — those are in
:mod:`debate_core.domain` — and it holds no I/O. Everything outside the process is reached through
a Protocol in :mod:`debate_core.application.ports`, so nothing here imports `boto3`, `httpx`,
`sqlite3`, Typer or FastAPI, and an import-linter contract (v1-e02-t06-import-boundary-guard)
makes that a build failure rather than a convention.

Services take their ports as constructor arguments. There is no service locator, no registry and
no module-level singleton to reach for instead; the composition root — the CLI, the API, a worker,
or a test — is the one place that decides which adapter is used. The pattern is written up in
`docs/architecture/ports-and-adapters.md`.
"""

from debate_core.application.errors import (
    AlreadyExists,
    BlobIntegrityError,
    Conflict,
    DomainError,
    InvalidCursor,
    InvalidModelOutput,
    NotFound,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    RevisionMismatch,
)

__all__ = [
    "AlreadyExists",
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
]

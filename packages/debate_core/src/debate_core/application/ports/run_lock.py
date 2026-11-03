"""The port for the bucket's run lock: one small object, changed only by conditional writes.

ADR-0020 (4). In bucket mode (`caselist.run_state = "bucket"`, `v1-e40-t04`) one runner at a time
may write to an evidence bucket, and which one is recorded in `reports/sync/run-lock.json` in that
bucket. Every change to the object is a compare-and-swap: the first of two concurrent writers wins
and the other is told so. :class:`LockObjectStore` is that object and nothing more; what the body
says, and when a lease may be taken over, is
:mod:`debate_core.application.caselist.run_lock`'s.

The methods are synchronous on purpose. The lease is renewed by a background thread and checked by
a write fence that runs inside the S3 client's own worker threads, neither of which has an event
loop to await on.

:class:`WriteFence` is the other side of the same lock: what the S3 adapters' clients ask before
every write in bucket mode (`debate_core.integrations.s3.fencing`). It is a port so that the
integration package depends on a shape, never on the lease that implements it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from debate_core.application.errors import DomainError

__all__ = ["LockObject", "LockObjectChanged", "LockObjectStore", "WriteFence"]


@dataclass(frozen=True, slots=True)
class LockObject:
    """The lock object's current body and the entity tag a conditional write names it by."""

    body: bytes
    etag: str


class LockObjectChanged(DomainError):
    """A conditional write of the lock object was refused: it is not the object it was read as.

    S3 answers `412 Precondition Failed` when another writer changed it first (or created it, for a
    write that required it absent), `404` when it is gone, and `409` when two writes raced. All
    three mean the same to a runner: the version it holds is not the bucket's.
    """

    def __init__(self, key: str, reason: str) -> None:
        self.key = key
        self.reason = reason
        super().__init__(f"the run lock {key} was not the version this runner held: {reason}")


@runtime_checkable
class LockObjectStore(Protocol):
    """One named object in one bucket, read with its entity tag and written only conditionally."""

    @property
    def key(self) -> str:
        """The object's key, `reports/sync/run-lock.json`."""
        ...

    def read(self) -> LockObject | None:
        """The object and its entity tag, or `None` when the bucket holds no such object.

        "No such object" is answered by a listing of the key's own prefix, which the everyday grant
        allows, so that a refusal to read an object that is there is never mistaken for its absence
        (a `GetObject` without `s3:ListBucket` on the key answers 403 for a missing key).
        """
        ...

    def create(self, body: bytes) -> str:
        """Write `body` only if no object is there (`If-None-Match: *`). Returns the new entity tag.

        Raises :class:`LockObjectChanged` when one is.
        """
        ...

    def replace(self, body: bytes, *, etag: str) -> str:
        """Write `body` only over the version `etag` names (`If-Match`). Returns the new entity tag.

        Raises :class:`LockObjectChanged` when the object is another version, or gone.
        """
        ...


@runtime_checkable
class WriteFence(Protocol):
    """What a write to an evidence bucket asks first, in bucket mode (ADR-0020 (4), "Fencing")."""

    def before_write(self, key: str, *, renew: bool) -> None:
        """Return only when this runner may write `key` now; raise otherwise.

        `renew` is whether the write must be preceded by a renewal of the lease that started after
        it was asked for: a named object's write must, a content-addressed object's need not, and a
        part of an upload already fenced need not.
        """
        ...

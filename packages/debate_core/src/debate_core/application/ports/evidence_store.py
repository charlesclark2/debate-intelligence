"""The port for evidence objects that have *names*, not digests.

:class:`~debate_core.application.ports.persistence.SnapshotStore` covers everything the evidence
store holds that is addressed by the SHA-256 of its own bytes, which is most of it. It cannot cover
the rest, because the rest is named on purpose:

::

    manifests/hsld26/2026-09-15.jsonl              one snapshot's sources
    manifests/_suppression/suppression-list.jsonl  digests that must never be re-imported
    reports/sync/2026-09-15T06-00Z.json            one scheduled sync run

A manifest is the record of *what the store holds*, so it has to be findable by the date and the
caselist it describes rather than by a digest nobody has yet. It is also the one kind of evidence
object that legitimately changes: a new snapshot of a caselist writes a new manifest at a new key,
and the suppression list is appended to (`docs/architecture/evidence-store-layout.md`).

So this port is deliberately the *smaller* of the two and the less safe one. It can overwrite,
because named objects are versioned in the bucket and a manifest that gains a row is still the same
manifest. Content-addressed blobs must never go through it —
:class:`~debate_core.application.ports.persistence.SnapshotStore` is what refuses to overwrite
them, and that refusal is the evidence chain (architecture proposal §8).

It works in *files* rather than `bytes` because the objects it moves are the big ones: a
30-megabyte camp manifest, a report, an archive. :class:`~debate_core.integrations.s3.
S3EvidenceObjectStore` streams them through a multipart transfer and
:class:`~debate_core.integrations.local.FsEvidenceObjectStore` copies them, and neither ever holds
one whole in memory. `v1-e29-t05-evidence-sync-cli` is the caller: it diffs two of these — the
local directory and the bucket for `DEBATE_ENV` — and moves what differs.

## Where the digest comes from, and when it is `None`

:attr:`ObjectInfo.sha256` is the one field whose meaning depends on which method returned it, and
the rule is the same for every implementation:

| From | `sha256` |
|---|---|
| :meth:`EvidenceObjectStore.list_objects` | Always `None` |
| :meth:`EvidenceObjectStore.head` | What the store recorded when the object was written, or `None` |
| :meth:`EvidenceObjectStore.put_file` | The digest of the bytes just written |
| :meth:`EvidenceObjectStore.get_file` | The digest of the bytes that just landed on disk |

Listing never states a digest, even where a store could work one out, because that is the only rule
that costs the same everywhere: S3's `ListObjectsV2` does not return checksums, so a listing that
promised digests would mean one `HeadObject` per object, and a caller walking 60,000 keys would pay
for it without asking. A caller that needs digests asks for them one object at a time, which is
what makes the cost visible in the code that chose it.

`head` returns `None` when the store holds no digest for an object — something other than these
adapters put it there. It is not an error and not a reason to refuse to sync: it means "you will
have to read the object to find out", and `v1-e29-t05` treats such an object as changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from debate_core.domain import Sha256Hex

__all__ = [
    "MAX_OBJECT_KEY_BYTES",
    "OBJECT_KEY_PATTERN",
    "EvidenceObjectStore",
    "ObjectInfo",
    "ObjectKey",
    "validate_object_key",
]

ObjectKey = str
"""A named object's key: slash-separated path segments, relative to the root of the store.

The same string in both implementations — `manifests/hsld26/2026-09-15.jsonl` is that key in the
bucket and that path under the local evidence directory — which is what lets
`v1-e29-t05-evidence-sync-cli` diff the two by key and get a meaningful answer.
"""

OBJECT_KEY_PATTERN = re.compile(r"^(?!/)(?!.*//)(?!.*(?:^|/)\.\.?(?:/|$))[A-Za-z0-9._/-]+(?<!/)$")
"""What a key may look like: `A-Z a-z 0-9 . _ - /`, no empty, `.` or `..` segment, no trailing `/`.

Every clause is a containment rule rather than a style rule, because this key becomes a filesystem
path in :class:`~debate_core.integrations.local.FsEvidenceObjectStore`. A key containing `..` would
name a file outside the evidence directory and a leading `/` would name an absolute path, so
validating the key *is* the traversal guard — and it lives in the port so that both implementations
get the same one rather than each writing its own.

The alphabet is narrower than either store would accept. S3 permits almost any UTF-8 and a POSIX
filename permits anything but `/` and NUL, but every key in
`docs/architecture/evidence-store-layout.md` is already inside this set, and the characters left out
are the ones that turn a key into a bug somewhere else: a space or a backslash that a shell command
in a runbook splits or escapes away, a `:` or a `*` that Windows cannot put on a disk, a control
character that makes a log line lie. A key is quoted in logs, in CloudTrail and in error messages,
so it stays something a human can read back and retype.
"""

MAX_OBJECT_KEY_BYTES = 1024
"""Longest key the store accepts, which is S3's own limit on a key.

Enforced for both implementations rather than only the one that has it: a local store that happily
wrote a 2,000-character path would hold evidence that could never be synced to the bucket, and the
failure would surface as a rejected request during a sync of the whole corpus rather than at the
call that chose the name.
"""


def validate_object_key(key: str) -> ObjectKey:
    """Return `key` unchanged, or raise :class:`ValueError` if it is not a usable object key.

    Adapters call this before touching their storage — see :data:`OBJECT_KEY_PATTERN` for why it is
    a guard and not a convention. It raises `ValueError` rather than a
    :class:`~debate_core.application.errors.DomainError` because a malformed key is a caller's bug:
    no listing of any store can produce one, so no amount of retrying or re-reading will help.
    """
    if OBJECT_KEY_PATTERN.match(key) is None:
        raise ValueError(
            "not an evidence object key (expected segments of A-Z a-z 0-9 . _ - separated by '/', "
            f"with no leading or trailing '/' and no '.' or '..' segment): {key!r}"
        )
    if len(key.encode()) > MAX_OBJECT_KEY_BYTES:
        raise ValueError(f"evidence object key is longer than {MAX_OBJECT_KEY_BYTES} bytes: {key[:80]!r}…")
    return key


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """What a store can say about one named object without a caller reading it.

    Frozen, like :class:`~debate_core.application.ports.persistence.Page`, and a plain dataclass
    rather than a Pydantic model: it is an answer a store just produced, not input that needs
    validating.
    """

    key: ObjectKey
    """The object's key, exactly as it would appear in a listing of the store."""

    size: int
    """Size in bytes. Zero is a legitimate answer — an empty manifest is an empty manifest."""

    sha256: Sha256Hex | None = None
    """SHA-256 of the object's bytes, lowercase hex, or `None`.

    Which of those it is depends on the method that returned this instance; the table in this
    module's docstring is the rule. `None` never means "the object is damaged" — it means the store
    was not asked to read the object and has no digest recorded for it.
    """

    version_id: str | None = None
    """The store's id for this version of the object, when it keeps versions.

    S3 returns one for every object in a versioned bucket, which is what a removal request and an
    audit walk (`docs/runbooks/caselist-removal.md`). The filesystem store keeps no versions and
    leaves this `None`, and nothing in the platform may require it to be set.
    """


@runtime_checkable
class EvidenceObjectStore(Protocol):
    """Stores evidence objects under names a caller chose: manifests, reports, built files.

    The companion to :class:`~debate_core.application.ports.persistence.SnapshotStore` and, like
    it, a :class:`~typing.Protocol`: the S3 and filesystem implementations conform structurally and
    never import this module at runtime. Both pass one shared contract
    (:mod:`debate_core.testing.contracts.evidence_object_store`), which is what makes "sync the
    local store to the bucket" a single piece of logic over two of these rather than two code paths
    (architecture proposal §6, §17).

    **Every method takes a key validated by :func:`validate_object_key`** and raises `ValueError`
    for one that is not — see there for why that is a containment rule.

    **Errors come from :mod:`debate_core.application.errors` and nowhere else.** A missing object is
    :class:`~debate_core.application.errors.NotFound`; a refused request is
    :class:`~debate_core.application.errors.StoreAccessDenied` or
    :class:`~debate_core.application.errors.StoreCredentialsExpired`; anything else the store failed
    at is :class:`~debate_core.application.errors.StoreUnavailable`. No `botocore` `ClientError`
    and no `OSError` crosses this boundary.

    **There is no `delete`.** Removing evidence is an operator procedure under
    `docs/runbooks/caselist-removal.md`, run with a credential scoped to it, and V1's sync never
    deletes anything on either side.
    """

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        """Return every object whose key starts with `prefix`, sorted by key.

        `prefix` is matched as a string, not as a path: `manifests/hs` matches
        `manifests/hsld26/…`. An empty prefix lists the whole store. A prefix that matches nothing
        returns an empty tuple — absence is an ordinary answer to a listing, so this never raises
        `NotFound`.

        The digests are `None`, always; the table in this module's docstring says why. The return is
        a tuple rather than an iterator because the caller that wants this is diffing two stores and
        needs both sides before it can plan anything: implementations page through their storage
        internally and hand back the whole listing.

        Sorted by key so that two implementations listing the same synced content produce the same
        sequence, which keeps a sync plan and its printed summary reproducible.
        """
        ...

    async def head(self, key: ObjectKey) -> ObjectInfo:
        """Return what the store knows about one object, without reading its bytes.

        Raises :class:`~debate_core.application.errors.NotFound` when nothing is stored under `key`.
        :attr:`ObjectInfo.sha256` is the digest the store recorded when the object was written, or
        `None` when it holds none.
        """
        ...

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        """Store the contents of the file at `source` under `key` and return the stored object.

        The digest on the returned :class:`ObjectInfo` is of the bytes actually written, computed
        while they were streamed, and the store records it so that a later :meth:`head` can state
        it. Nothing is read whole into memory.

        **This overwrites.** A second `put_file` to the same key replaces what was there, which is
        what a re-published manifest is. That is safe here and only here: a content-addressed blob
        goes through :meth:`~debate_core.application.ports.persistence.SnapshotStore.put`, which
        refuses. Callers must never route a `sha256/` key through this method.

        Raises :class:`FileNotFoundError` when `source` does not exist — the caller named a local
        file that is not there, which is its bug and not the store's condition.
        """
        ...

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        """Download the object at `key` to `destination` and return what landed there.

        The write is atomic: the bytes go to a temporary file beside `destination` and are renamed
        into place, so a reader sees the whole object or no file at all, and an interrupted download
        leaves `destination` as it was. Parent directories are created as needed.

        :attr:`ObjectInfo.sha256` is the digest of the bytes that landed on disk, computed while
        they streamed. When the store recorded a digest for the object and the two disagree, nothing
        is renamed into place and
        :class:`~debate_core.application.errors.BlobIntegrityError` is raised: evidence that arrived
        damaged is never handed to a caller that would then verify a card against it.

        Raises :class:`~debate_core.application.errors.NotFound` when nothing is stored under `key`.
        """
        ...

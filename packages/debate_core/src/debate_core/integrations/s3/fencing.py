"""Every write an S3 client makes in bucket mode asks the run lock first (ADR-0020 (4) 4, `v1-e40-t04`).

One chokepoint rather than one check per adapter: :func:`fence_client` registers a handler on a
client's own event system, `before-parameter-build.s3`, which botocore emits before every operation
that client makes, whichever adapter makes it: a manifest's `PutObject`, a parsed file's multipart
upload, a retirement's `PutObjectTagging`, a takedown's `DeleteObject`. The handler asks the
:class:`~debate_core.application.ports.run_lock.WriteFence` before a write, and a refusal raises
out of the call before any request is sent. So a command that forgot to take the lock fails closed:
its write is refused (`RUN_LOCK_NOT_HELD`), never sent unfenced.

## What is a write

An operation whose name begins `Get`, `Head` or `List` reads, and passes. Of the rest:

* the parts of a multipart upload (:data:`UPLOAD_PARTS`) ask only that the lease is still held,
  because the object lands at `CompleteMultipartUpload`, which renews;
* everything else (`PutObject`, `CompleteMultipartUpload`, `CopyObject`, `PutObjectTagging`,
  `DeleteObject`, `DeleteObjects`, and any operation not named here) renews first, unless its key
  is content-addressed (:func:`~debate_core.application.caselist.run_lock.is_content_addressed`).

An operation nobody listed is treated as a write: the safe way to be wrong.

The lock object's own client is never fenced; its writes are the lock's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from debate_core.application.ports.run_lock import WriteFence

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["READ_PREFIXES", "UPLOAD_PARTS", "fence_client"]

READ_PREFIXES: Final = ("Get", "Head", "List")
"""An operation whose name starts with one of these reads and is never fenced."""

UPLOAD_PARTS: Final = frozenset(
    {"CreateMultipartUpload", "UploadPart", "UploadPartCopy", "AbortMultipartUpload"}
)
"""The steps of a multipart upload before it lands: checked, not renewed."""

_EVENT: Final = "before-parameter-build.s3"


def fence_client(client: S3Client, fence: WriteFence) -> None:
    """Make every write `client` sends ask `fence` first. Idempotent for one fence."""

    def ask_the_fence(params: dict[str, Any], model: Any, **_: object) -> None:
        operation = str(getattr(model, "name", ""))
        if operation.startswith(READ_PREFIXES):
            return
        key = params.get("Key")
        fence.before_write(str(key) if isinstance(key, str) else "", renew=operation not in UPLOAD_PARTS)

    client.meta.events.register(_EVENT, ask_the_fence, unique_id=f"debate-run-lock-fence-{id(fence)}")

"""The parsed store's version directories in one place, for retiring the superseded ones (`v1-e31-t16`).

`caselist parse` writes a new version directory for a parser version bump or a re-parse and never
touches the old one (:mod:`debate_core.application.ports.parsed_store`). Nothing reads the old one
again, and each holds about 5.8 GB. :mod:`debate_core.application.caselist.version_retention`
decides which are superseded; this port is what it lists them in and retires them through. There
are two places, and they retire differently:

* **This machine** (`<data_dir>/parsed/`): retiring deletes the directory.
* **The environment's evidence bucket** (`parsed/`): retiring tags every current object under the
  directory with :data:`RETIREMENT_TAG_KEY` = :data:`RETIREMENT_TAG_VALUE`. The bucket's lifecycle
  rule on `parsed/` expires what carries that tag, and setting it to :data:`RESTORED_TAG_VALUE`
  before then undoes it. The
  everyday `EvidenceOperator` permission set has no `s3:DeleteObject` by design, and only a takedown
  deletes (PM ruling, 2026-10-15); it was given `s3:PutObjectTagging` and `s3:GetObjectTagging` on
  `parsed/` for this, and nothing else. `infrastructure/modules/evidence_bucket/main.tf` filters
  on the same tag, and a test reads it there.

A tag carries no school, team code or file name: its key and value are these two constants
(`docs/policies/caselist-data-use.md`, "Never in S3 keys or object metadata").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

__all__ = [
    "RESTORED_TAG_VALUE",
    "RETIREMENT_TAG_KEY",
    "RETIREMENT_TAG_VALUE",
    "DirectoryContents",
    "RetirementMethod",
    "VersionDirectoryPlace",
]

RETIREMENT_TAG_KEY: Final = "debate-retention"
"""The object tag the bucket's lifecycle rule on `parsed/` expires by."""

RETIREMENT_TAG_VALUE: Final = "superseded"
"""The value the lifecycle rule expires. Any other value under the key expires nothing."""

RESTORED_TAG_VALUE: Final = "restored"
"""What restoring sets the tag to. Restoring rewrites the value rather than removing the tag: the
everyday set has `s3:PutObjectTagging` but not `s3:DeleteObjectTagging`, and a tag set left empty is
not something every S3 implementation accepts. The value also records that the directory was
retired once and brought back."""


class RetirementMethod(StrEnum):
    """What retiring a directory does in a place."""

    DELETE = "delete"
    """Deleted at once: this machine."""
    TAG = "tag"
    """Tagged for the bucket's lifecycle rule, which expires it after the grace period."""


@dataclass(frozen=True, slots=True)
class DirectoryContents:
    """What one version directory holds in one place. Counts only."""

    objects: int
    """Files on this machine; current objects in the bucket."""
    bytes: int
    tagged: int | None
    """How many objects already carry the retirement tag; `None` in a place that does not tag, and
    where the tags were not read."""


@runtime_checkable
class VersionDirectoryPlace(Protocol):
    """One place that holds the parsed store: this machine, or the environment's bucket.

    Names are a caselist slug and a version directory's name, as
    :func:`~debate_core.application.ports.parsed_store.version_directory_name` makes them, never a
    path: an adapter builds the path or key itself and refuses a name that would leave the
    caselist's directory.
    """

    @property
    def location(self) -> str:
        """`this machine`, or `s3://<bucket>`: what a plan says it was made for. Never a path."""
        ...

    @property
    def method(self) -> RetirementMethod: ...

    async def caselists(self) -> tuple[str, ...]:
        """The caselists the store has a directory for, sorted."""
        ...

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        """The version directories `caselist` has here, in any order."""
        ...

    async def contents(self, caselist: str, version: str, *, count_tagged: bool) -> DirectoryContents:
        """What the directory holds. `count_tagged` reads each object's tags, one request each in a
        bucket, so a plan asks it only of a directory it might retire or restore."""
        ...

    async def retire(self, caselist: str, version: str) -> int:
        """Delete or tag every object of the directory, by :attr:`method`. Returns how many."""
        ...

    async def restore(self, caselist: str, version: str) -> int:
        """Set the retirement tag of every object that has it to :data:`RESTORED_TAG_VALUE`. Returns how many.

        Raises `NotImplementedError` in a place that deletes: there is nothing left to restore.
        """
        ...

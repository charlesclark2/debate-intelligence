"""What a removal left in the bucket, counted from a version listing (`v1-e30-t10`).

A takedown deletes every version of every object of a removed file. One that stopped part-way, or
a delete made some other way, can leave versions behind, and a version that can be restored is a
file not removed. `debate-research caselist status` reports them through
:meth:`~debate_core.application.caselist.status_service.CaselistStatusService.status`, so the check
an operator already runs after a removal says whether anything is left, without the takedown
profile.

## It reads, with the everyday profile

One call, `ListObjectVersions`, under two prefixes per caselist: its sources (`raw/caselist/<slug>/`,
or `raw/openev/` for camp files) and its parsed cards (`parsed/<caselist>/`). The everyday
`EvidenceOperator` profile may list versions under `raw/` and `parsed/` (`v1-e29-t06`). Nothing is
downloaded and nothing is deleted: this module calls no other method of the version store, and the
credential it is given cannot delete.

## What is residue

The suppression list says what was removed. A file whose **whole source** is suppressed is gone for
every holder, so any version of an object named for its digest is something a removal should have
taken. That covers the files a request named and the later uploads a removal took down with them
(`v1-e30-t11`), because each is suppressed whole. Per file, three counts:

`current_objects`
    Objects that are the current version of their key. A takedown deletes each version by its id,
    and S3 then makes the next version current, so what a takedown that stopped among an object's
    versions leaves is a current object with the older versions beneath it.
`noncurrent_versions`
    Data versions that are not current: under a newer version, or under a delete marker.
`delete_markers`
    A delete made without a version id hides an object under a marker and keeps every version. No
    plain listing shows that key again. The takedown leaves no marker, so one is counted.

An object is matched by its key alone: its last segment is the file's digest (`raw/`), or the
digest and an extension (`parsed/…/<sha256>.jsonl`).

## What it does not see

* **Manifests and the parsed store's aggregates.** A noncurrent version of a manifest, or of an
  `index.jsonl`, can still hold a removed file's row. Its key names no file, so telling would mean
  downloading every noncurrent version, and this check lists only. `caselist remove` purges them:
  a re-run sweeps every noncurrent manifest version that names what the list stops.
* **A file withdrawn from one team and kept for another.** It is suppressed for one disclosure, not
  whole, and the other holders' copy is the same object. Nothing in a key says which holder a
  version was for.

So "nothing found" means no version of a wholly removed file is left under these two prefixes, and
the command says exactly that.

## A refused listing is not an empty one

In an environment where the grant has not been applied the listing is refused
(:class:`~debate_core.application.errors.StoreAccessDenied`). The caselist is then reported as not
checked, with no counts at all: a zero would say nothing is left. Any other failure of the bucket
is raised, as it is for the rest of the comparison.

## What it reports

Counts and digests. The command prints the first twelve characters of each digest
(:attr:`ResidueFile.sha256_prefix`), which is enough to find the entry, and its request id, in the
suppression list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from debate_core.application.caselist.publish_plan import remote_source_prefix
from debate_core.application.errors import StoreAccessDenied, error_code_of
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore
from debate_core.application.ports.parsed_store import PARSED_PREFIX
from debate_core.application.ports.suppression import SuppressionState
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex

__all__ = [
    "RESIDUE_DIGEST_PREFIX_LENGTH",
    "CaselistResidue",
    "OlderVersions",
    "RemovalCompletion",
    "ResidueFile",
    "removal_residue",
    "residue_prefixes",
]

RESIDUE_DIGEST_PREFIX_LENGTH: Final = 12
"""How much of a digest the report prints: what the removal plan prints for a later upload too."""

_DIGEST: Final = re.compile(SHA256_HEX_PATTERN)


@dataclass(frozen=True, slots=True)
class ResidueFile:
    """One removed file, and what the bucket still holds under keys named for it."""

    sha256: Sha256Hex
    current_objects: int = 0
    noncurrent_versions: int = 0
    delete_markers: int = 0

    @property
    def sha256_prefix(self) -> str:
        return self.sha256[:RESIDUE_DIGEST_PREFIX_LENGTH]


@dataclass(frozen=True, slots=True)
class OlderVersions:
    """How many versions of one key role in a caselist are older than a removal that touched it."""

    role: str
    """`manifest`, or the aggregate's file name: `index.jsonl`, `failures.jsonl`, `occurrences.jsonl`."""
    versions: int


@dataclass(frozen=True, slots=True)
class RemovalCompletion:
    """When a removal request was last completed in this environment, from the removal log."""

    request_id: str | None
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CaselistResidue:
    """What a version listing shows of one caselist's removed files, or that it could not be made."""

    caselist: str
    checked: bool
    """False when the listing was refused. The counts are then `None`, never zero."""
    files: tuple[ResidueFile, ...] = ()
    """Every removed file with anything left, in digest order. Empty when :attr:`checked` is false."""
    not_checked_reason: str | None = None
    """The error code of the refusal, e.g. `STORE_ACCESS_DENIED`."""
    older_versions: tuple[OlderVersions, ...] = ()
    """Manifest and aggregate versions older than a removal that touched this caselist, by role."""
    older_than: RemovalCompletion | None = None
    """The latest completed removal that touched this caselist, or `None` when none did."""

    @property
    def found(self) -> bool:
        return bool(self.files) or bool(self.older_versions)

    @property
    def current_objects(self) -> int | None:
        return sum(one.current_objects for one in self.files) if self.checked else None

    @property
    def noncurrent_versions(self) -> int | None:
        return sum(one.noncurrent_versions for one in self.files) if self.checked else None

    @property
    def delete_markers(self) -> int | None:
        return sum(one.delete_markers for one in self.files) if self.checked else None


def residue_prefixes(caselist: str) -> tuple[str, str]:
    """The two prefixes one caselist's check lists versions under: its sources, and its parsed cards."""
    return remote_source_prefix(caselist), f"{PARSED_PREFIX}/{caselist}/"


async def removal_residue(
    versions: EvidenceVersionStore, caselist: str, suppression: SuppressionState
) -> CaselistResidue:
    """Count what the bucket still holds of `caselist`'s wholly suppressed files. Lists only."""
    counts: dict[Sha256Hex, list[int]] = {}
    try:
        for prefix in residue_prefixes(caselist):
            for version in await versions.list_versions(prefix):
                digest = _digest_named_by(version.key)
                if digest is None or not suppression.suppresses_source(digest):
                    continue
                current, noncurrent, markers = counts.setdefault(digest, [0, 0, 0])
                if version.is_delete_marker:
                    markers += 1
                elif version.is_latest:
                    current += 1
                else:
                    noncurrent += 1
                counts[digest] = [current, noncurrent, markers]
    except StoreAccessDenied as refused:
        return CaselistResidue(caselist=caselist, checked=False, not_checked_reason=error_code_of(refused))
    return CaselistResidue(
        caselist=caselist,
        checked=True,
        files=tuple(
            ResidueFile(
                sha256=digest, current_objects=current, noncurrent_versions=noncurrent, delete_markers=markers
            )
            for digest, (current, noncurrent, markers) in sorted(counts.items())
        ),
    )


def _digest_named_by(key: ObjectKey) -> Sha256Hex | None:
    """The digest an object's last key segment is, with or without an extension, or `None`."""
    stem = key.rsplit("/", 1)[-1].split(".", 1)[0]
    return stem if _DIGEST.match(stem) is not None else None

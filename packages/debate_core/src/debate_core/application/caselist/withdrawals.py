"""What a complete archive no longer holds: withdrawals, and files uploaded again (`v1-e34-t04`).

ADR-0017 decision 5: a sha256 an earlier snapshot of a caselist held, and that caselist's complete
archive (`<slug>-all-<date>.zip`) does not, is gone from OpenCaselist. That is the one measure of
removal the site's own data supports. A weekly's path-level `REMOVED` is not: a weekly is a window
of edits, and a filename carries a per-team sequence number, so a path missing from one week is a
rename as often as a withdrawal (`v1-e30-t06` ac2).

A digest can be gone for two reasons, and they are counted apart (PM decision, `v1-e34-t04`):

**withdrawn**
    No path the digest was ever held at is in the complete archive. The disclosure is gone.
**superseded**
    At least one of those paths is in the complete archive, holding other bytes: the team uploaded
    the file again. The earlier version is gone; the disclosure is not.

"Earlier" is every snapshot of the caselist dated before the complete archive, weekly and complete
alike, as their manifests' stored rows say. A digest the suppression list stops has no manifest
row anywhere, so a removal of ours is never counted as a withdrawal of theirs.

What this cannot tell apart: a file uploaded again under a new name. The sequence number in the
name changes, so the old path is gone too and the old digest counts as withdrawn. The count is an
upper bound on withdrawals for that reason, and the superseded count a lower bound on re-uploads.

**Counts only.** No path, school, team code or file name leaves this module; the rows it is given
are read from the manifests, which may hold them, and nothing here returns or logs one
(`docs/policies/caselist-data-use.md` rule 4). Whether a withdrawal should suppress anything is a
question for the data-use policy and `v1-e30-t07`, not for this count.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["EarlierSnapshots", "WithdrawalCount", "count_withdrawals"]


@dataclass(frozen=True, slots=True)
class EarlierSnapshots:
    """What a caselist's snapshots before a complete archive held: weekly and complete alike."""

    rows: tuple[tuple[str, str], ...]
    """`(sha256, path)` of every stored row of every one of them. Never logged."""

    count: int
    """How many snapshots those rows came from."""


@dataclass(frozen=True, slots=True)
class WithdrawalCount:
    """Digests earlier snapshots held that a complete archive does not, in two counts."""

    withdrawn: int
    """Gone, and so is every path it was held at."""

    superseded: int
    """Gone, and a path it was held at now holds other bytes: uploaded again."""

    earlier_snapshots: int
    """How many earlier snapshots were compared, weekly and complete."""


def count_withdrawals(earlier: EarlierSnapshots, archive: Iterable[tuple[str, str]]) -> WithdrawalCount:
    """Count what `earlier` held and the complete archive does not. See the module docstring.

    `archive` is `(sha256, path)` for every member of the complete archive that has a digest,
    those the suppression list stopped included: a file still in the archive is not withdrawn,
    whatever we did with it.
    """
    present_digests: set[str] = set()
    present_paths: set[str] = set()
    for digest, path in archive:
        present_digests.add(digest)
        present_paths.add(path)
    gone: dict[str, set[str]] = {}
    for digest, path in earlier.rows:
        if digest not in present_digests:
            gone.setdefault(digest, set()).add(path)
    superseded = sum(1 for paths in gone.values() if paths & present_paths)
    return WithdrawalCount(
        withdrawn=len(gone) - superseded,
        superseded=superseded,
        earlier_snapshots=earlier.count,
    )

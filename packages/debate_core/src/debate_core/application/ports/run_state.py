"""The port for this machine's half of a run's state: what a run-state bundle is packed from and into.

ADR-0020 (3). The run-state bundle is one gzipped tar of the data directory's manifests
(`<data_dir>/objects/manifests/`) and its SQLite database, kept in the bucket under
`manifests/_run-state/`. The two are one object because they must agree: the importer reads its
previous snapshot and the disclosures from the database, and the select stage reads what is held
from the manifests. :mod:`debate_core.application.caselist.run_state` decides when a bundle is saved
and restored; this port is the files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from debate_core.application.errors import DomainError

__all__ = ["BUNDLE_DATABASE_NAME", "BUNDLE_MANIFESTS_DIRECTORY", "RunStateBundleUnreadable", "RunStateFiles"]

BUNDLE_MANIFESTS_DIRECTORY: Final = "objects/manifests"
"""Where the manifests are in a bundle, and under the data directory: the same relative path."""

BUNDLE_DATABASE_NAME: Final = "debate.sqlite3"
"""The database's name in a bundle."""


class RunStateBundleUnreadable(DomainError):
    """A run-state bundle holds something other than manifests and the database, or is not a bundle.

    Nothing of it is unpacked. Named by what is wrong, never by a member's name, which may be a
    manifest's caselist and date and is not quoted from an archive nobody vouched for.
    """

    def __init__(self, problem: str) -> None:
        self.problem = problem
        super().__init__(f"the run-state bundle could not be read ({problem}), so nothing of it was restored")


@runtime_checkable
class RunStateFiles(Protocol):
    """This environment's data directory, as the run-state bundle sees it."""

    def pack(self, destination: Path) -> None:
        """Write a bundle of this machine's manifests and a consistent copy of its database."""
        ...

    def unpack(self, bundle: Path, staging: Path) -> None:
        """Unpack `bundle` into the empty directory `staging`, checking every member first.

        Raises :class:`RunStateBundleUnreadable` for anything but `objects/manifests/...` files and
        the database, and leaves nothing unpacked.
        """
        ...

    def install(self, staging: Path) -> None:
        """Make `staging`'s manifests and database this machine's, each replaced whole by a rename."""
        ...

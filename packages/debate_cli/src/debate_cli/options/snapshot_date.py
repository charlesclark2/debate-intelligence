"""`--snapshot`: the day an archive or a report was published, as a plain calendar date.

Taken by `caselist import`, `caselist cards`, `landscape` and `files`. It lived in
:mod:`debate_cli.commands.caselist` until v1-e01-t32.
"""

from __future__ import annotations

from datetime import date

from debate_core.application.settings import ConfigurationError

__all__ = ["InvalidSnapshotDate", "parse_snapshot_date"]


def parse_snapshot_date(value: str) -> date:
    """Parse `--snapshot` as a plain calendar date.

    Taken as a string and parsed here rather than declared as a `datetime` option, because a
    snapshot is the day an archive was published and an option typed as a datetime would accept
    `2026-09-15T06:00` and silently carry a time of day the source does not have.
    """
    try:
        return date.fromisoformat(value.strip())
    except ValueError as malformed:
        raise InvalidSnapshotDate(value) from malformed


class InvalidSnapshotDate(ConfigurationError):
    """`--snapshot` was not a calendar date. It names the archive's publication day."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"--snapshot must be a date as YYYY-MM-DD (the day the archive was published), not {value!r}",
            field="--snapshot",
            source="cli",
        )

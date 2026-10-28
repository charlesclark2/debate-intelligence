"""A removal stopped by `raw/` or `parsed/` versions it left, as the CLI reports it (`v1-e30-t29`).

The service raises :class:`~debate_core.application.caselist.removal_service.RemovalIncomplete` from
:class:`~debate_core.application.caselist.removal_service.BucketObjectsLeft`, as it does from
:class:`~debate_core.application.caselist.removal_service.SchoolViewsLeft` (`v1-e32-t13`). The CLI
has no handler of its own for either: both reach the envelope through `RemovalIncomplete`, and these
tests hold the new one to the same exit code, code and details as the school views', counts only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure
from debate_core.application.caselist.removal_service import (
    BucketObjectsLeft,
    RemovalIncomplete,
    RemovalReport,
    SchoolViewsLeft,
)
from debate_core.application.errors import DomainError


def stopped_by(cause: DomainError) -> RemovalIncomplete:
    """`RemovalIncomplete` as `execute()` raises it: from `cause`, after every suppression entry went on."""
    try:
        try:
            raise cause
        except DomainError as caught:
            raise RemovalIncomplete(
                cast("RemovalReport", SimpleNamespace()), caught, suppressed=True
            ) from caught
    except RemovalIncomplete as incomplete:
        return incomplete


def test_it_ends_the_command_as_school_views_left_does() -> None:
    left = CommandFailure.from_exception(stopped_by(BucketObjectsLeft(3, 2)))
    views = CommandFailure.from_exception(stopped_by(SchoolViewsLeft(3)))

    assert left.exit_code is views.exit_code is ExitCode.DOMAIN_FAILURE
    assert left.code == views.code == "REMOVAL_INCOMPLETE"
    assert left.details == {"error_code": "BUCKET_OBJECTS_LEFT"}
    assert views.details == {"error_code": "SCHOOL_VIEWS_LEFT"}


def test_its_message_counts_and_says_to_run_the_same_removal_again() -> None:
    failure = CommandFailure.from_exception(stopped_by(BucketObjectsLeft(3, 2)))

    assert failure.message == (
        "the removal stopped part-way (BUCKET_OBJECTS_LEFT): 3 version(s) or delete marker(s) of 2 "
        "source or parsed file(s) this removal reached are still in the bucket after it deleted them; "
        "run the same removal again. Every suppression entry was appended first, so nothing removed "
        "can be re-imported. Re-run the same command to finish."
    )
    assert "raw/" not in failure.message
    assert "parsed/" not in failure.message

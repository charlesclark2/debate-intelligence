"""Which failures the next scheduled run may cure, as `debate_core`'s tests know it (`v1-e34-t19`).

`debate_core` does not decide this. `debate_cli.exit_codes` does, for the command's exit status,
and the composition root hands the run monitor that same rule for the notification. The tests of
this package do not import the CLI, so the five codes are written out here by hand, from the table
in `docs/runbooks/caselist-scheduled-sync.md` ("What the exit code says"). A test of the CLI holds
the real rule to the same five (`packages/debate_cli/tests/commands/test_caselist_pull.py`).
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

from debate_core.application.sync_runs import SyncRunMonitor

__all__ = ["A_RETRY_MAY_CURE", "a_retry_may_cure", "the_commands_retry_rule"]

A_RETRY_MAY_CURE = frozenset(
    {
        "STORE_UNAVAILABLE",
        "STORE_CREDENTIALS_EXPIRED",
        "STORE_ACCESS_DENIED",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_RATE_LIMITED",
    }
)
"""The codes that exit `3`: a store or OpenCaselist that did not answer, or refused."""


def a_retry_may_cure(codes: Sequence[str]) -> bool:
    """The command's rule: every one of `codes` is a failure a later run may not meet."""
    return all(code in A_RETRY_MAY_CURE for code in codes)


def the_commands_retry_rule() -> dict[str, Any]:
    """The monitor's keyword for the rule, where the monitor takes one.

    Empty against the source as it was before `v1-e34-t19`, which had no such keyword, so that the
    tests built on these helpers still run there and fail on what they assert.
    """
    if "may_succeed_on_retry" in inspect.signature(SyncRunMonitor).parameters:
        return {"may_succeed_on_retry": a_retry_may_cure}
    return {}

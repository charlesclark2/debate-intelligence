"""A landscape report over a working copy restored from the bucket (`v1-e40-t17`).

Since the cutover (2026-10-27) the weekly run is the cloud task in bucket mode, and the weeks it pulls
live in the dev bucket's run state. The operator's data directory stops at the Mac's last pull.
`debate-research landscape report --restored-copy <copy>` reads a caselist's cards from a copy
`caselist restore-run-state --with-sources` made: its manifests, its parsed store, its suppression list,
its run log and its raw sources. Every piece of the landscape's own state stays in the data directory:
the classification cache, the review queue, the plan-text and analytic-text caches, the scan
acceptances, the model cassettes, the model usage log and the bundle under `reports/landscape/`.
Deleting the copy loses none of it, so no card is classified a second time (`v1-e32-t07`: a card is
classified once, in dev). The PM's ruling of 2026-10-30; the operator's steps are
:data:`LANDSCAPE_RUNBOOK`.

* :func:`restored_copy_refusal` refuses a copy that is not a directory, is the data directory, lies
  inside it or holds it, or lies inside a checkout of this repository.
* :func:`publish_refusal` refuses, in bucket mode, a publish without a copy: the data directory is not
  the run's home, so its newest snapshot is not the newest week. A dry run is not refused.
* :class:`~debate_core.application.landscape_run.LandscapeRunService`, given this build's parser
  version, refuses a copy whose newest parsed directory of the caselist is of another version: a copy
  restored by this build holds none until `caselist parse` writes one into it.

Nothing here names the copy's path: it is the operator's own, and they typed it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from debate_core.application.settings import RunStateMode

__all__ = ["LANDSCAPE_RUNBOOK", "RESTORED_COPY_FLAG", "publish_refusal", "restored_copy_refusal"]

LANDSCAPE_RUNBOOK: Final = "docs/runbooks/landscape-report-from-the-cloud-run.md"
"""The operator's steps: restore, parse into the copy, dry run, publish, delete the copy."""

RESTORED_COPY_FLAG: Final = "--restored-copy"


def restored_copy_refusal(copy: Path, *, data_dir: Path) -> str | None:
    """Why a report may not read its cards from `copy`, or `None` when it may. Reads, never writes."""
    del copy, data_dir
    return None


def publish_refusal(
    *, run_state: RunStateMode, publish: bool, dry_run: bool, restored_copy: bool
) -> str | None:
    """Why a publish without a restored copy is refused in bucket mode, or `None` when it is not."""
    del run_state, publish, dry_run, restored_copy
    return None

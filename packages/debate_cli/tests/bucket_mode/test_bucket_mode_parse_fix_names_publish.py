"""A bucket-mode pull is built to name `--publish` for every parsed store it owes (`v1-e34-t31`).

The parse stage names `caselist parse --publish-only` for a caselist only where the version
directory it rebuilt is still there to publish after the run. In local mode it is: the data
directory is the operator's. In bucket mode it is not: the cloud run's working copy is on its
task's ephemeral storage, and the parsed store a later run or `caselist restore-run-state` restores
is the bucket's, not the one the failed publish left. The composition root tells the pull which, and
`packages/debate_core/tests/application/caselist/test_caselist_sync_names_publish_only_per_caselist.py`
holds the stage to what it is told.
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_cli.caselist_events import event_for_caselist
from debate_cli.container import ServiceContainer
from debate_core.application.settings import load_settings

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""


@pytest.mark.parametrize(("run_state", "kept"), [("local", True), ("bucket", False)])
def test_the_pull_is_told_whether_its_working_copy_outlives_it(
    world: World, run_state: str, kept: bool
) -> None:
    world.mode(run_state)

    service = ServiceContainer(settings_loader=load_settings).caselist_sync(
        event_for_caselist=event_for_caselist
    )

    assert service._working_copy_outlives_the_run is kept  # pyright: ignore[reportPrivateUsage]

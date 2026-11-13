"""Only `caselist pull` writes a record to the run log a scheduled pull's guard reads (`v1-e40-t44`).

The PM's ruling 3 of 2026-11-12: only records of `caselist pull` runs count, and the guard must not depend
on the no-import window to keep a backfile import's out. The record has no field that names its command
(its fields are frozen, `v1-e34-t19`), so the guard counts every record of mode `run`: what makes that
right is that nothing else writes one. The run log's one writer is :class:`SyncRunMonitor`, which appends
a record as each pull it watches ends; the composition root alone builds one, and `caselist pull` alone
asks for it. `test_backfile_import.py` shows a backfile import leaving the bucket's run log as it was.

A module that comes to name the monitor, or the run log, fails this until it is classified here: a new
writer would make the guard count runs that are not pulls, and a new reader is one more place a record's
meaning is relied on.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

PACKAGES: Final = Path(__file__).resolve().parents[2]
"""`packages/`, beside this package."""

BUILDS_THE_MONITOR: Final = {"debate_cli/container.py"}
ASKS_FOR_THE_MONITOR: Final = {"debate_cli/commands/caselist_pull.py"}
"""Every module but the composition root that reaches `ServiceContainer.caselist_sync_monitor`."""

NAMES_THE_RUN_LOG: Final = {
    "debate_core/application/sync_runs.py": "defines it; SyncRunMonitor is its one writer",
    "debate_cli/container.py": "builds the monitor, and the history `caselist runs` reads",
    "debate_core/application/caselist/run_state.py": "restores and saves it whole; reads it for the guard",
    "debate_core/application/landscape_run.py": "reads it for the landscape's staleness",
    "debate_core/application/landscape_staleness.py": "reads it for the landscape's staleness",
}


def source_modules() -> dict[str, ast.Module]:
    """Every module of every package's `src/`, by its path under `src/`."""
    found: dict[str, ast.Module] = {}
    for path in sorted(PACKAGES.glob("*/src/**/*.py")):
        _package, _src, *under_src = path.relative_to(PACKAGES).parts
        found[Path(*under_src).as_posix()] = ast.parse(path.read_text(encoding="utf-8"))
    return found


def names_in(tree: ast.Module) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.name.rsplit(".", 1)[-1])
    return used


def builds(tree: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(tree)
    )


def test_the_composition_root_alone_builds_the_run_monitor() -> None:
    modules = source_modules()
    assert {path for path, tree in modules.items() if builds(tree, "SyncRunMonitor")} == BUILDS_THE_MONITOR


def test_caselist_pull_alone_asks_for_the_run_monitor() -> None:
    modules = source_modules()
    reaching = {
        path
        for path, tree in modules.items()
        if "caselist_sync_monitor" in names_in(tree) and path not in BUILDS_THE_MONITOR
    }
    assert reaching == ASKS_FOR_THE_MONITOR


def test_every_module_naming_the_run_log_is_one_classified_here() -> None:
    modules = source_modules()
    naming = {
        path for path, tree in modules.items() if {"SyncRunLog", "SYNC_RUN_LOG_FILENAME"} & names_in(tree)
    }
    assert naming == set(NAMES_THE_RUN_LOG)

"""Fixtures shared by the contract bindings in this directory.

Only one thing is shared: the SQLite database the three local repository bindings hand out
handles onto. It lives under `tmp_path`, so every test gets an empty store and nothing here can
reach a real data directory.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.integrations.local import SqliteDatabase


@pytest.fixture
def sqlite_database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    """One migrated, empty database per test, closed afterwards.

    The three SQLite repositories share it, exactly as the composition root wires them: one
    connection, one set of pragmas, one migration run. It is also what makes a repository factory
    able to hand out two handles onto the *same* storage, which the optimistic-concurrency
    contract needs.
    """
    with SqliteDatabase.open(tmp_path) as opened:
        yield opened

"""Workspace-wide test setup: the repository root on `sys.path`, and terminal-independent rendering.

The repository root goes on `sys.path` so that `tests/fixtures/` is importable from any package.

Every other test in this workspace imports either an installed package (`debate_core`,
`debate_cli`) or a data file it opens by path, and neither needs this. The synthetic caselist
archives (`v1-e30-t03-archive-importer`) are the first fixture that is *code*: a builder that
four suites in three packages generate the same three archives from —
`packages/debate_core/tests/application/caselist/`, `packages/debate_core/tests/integrations/local/`,
`packages/debate_cli/tests/` and `tests/smoke/`. Copying it into each of them would be four
fixtures that can drift from the one `expected_summary.json` they are all checked against.

pytest runs with `--import-mode=importlib`, which does not put the rootdir on `sys.path` the way
the legacy `prepend` mode did. This file is collected before any test module because it sits at
the rootdir, and with the root on the path `tests.fixtures.caselist.build_synthetic_archives`
resolves as an implicit namespace package (PEP 420) — no `__init__.py` in `tests/`, which would
otherwise make `tests` look like a distributable package.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import typer.rich_utils

REPOSITORY_ROOT = Path(__file__).parent

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


# --------------------------------------------------------------------------------------------
# Rendering: plain text at a fixed width, whatever terminal the suite was started in
# --------------------------------------------------------------------------------------------
#
# Tests across the workspace assert on text Rich rendered: every `--help` and every table the CLI
# prints, in packages/debate_cli/tests and tests/smoke alike. Rich decides how to render from its
# surroundings, and two things differ between a laptop and a CI runner:
#
# * Colour. Typer's help console forces a terminal whenever GITHUB_ACTIONS, FORCE_COLOR or
#   PY_COLORS is set, and reads them once, when typer.rich_utils is imported. On a runner the help
#   panels arrive full of ANSI escapes and `"--caselist" in result.stdout` fails, which is how the
#   first CI run of v1-e01-t04 failed three tests. The CLI's own consoles honour FORCE_COLOR too.
# * Width. With no fixed width Rich uses COLUMNS, or the terminal the process inherited, or 80.
#   Narrow enough, tables and option panels wrap mid-word.
#
# Before this fixture, 16 tests in 9 modules failed in some such environment; CI's runner happened
# to trip 3 of them. No test in this workspace should depend on the terminal, so the fixture is
# autouse for every test, not only the CLI ones. Typer's settings are patched as module
# attributes, because it reads them each time it builds a help console; setting the environment
# instead would come too late. packages/debate_cli/tests/test_help_rendering.py holds the pin.

# Wide enough that no option name, command name or table cell the tests look for wraps, and fixed,
# so output is the same on every machine.
RENDER_WIDTH = 200

# Environment variables that make Rich or Typer render for a terminal, or at another width.
_TERMINAL_VARIABLES = ("FORCE_COLOR", "PY_COLORS", "TTY_COMPATIBLE", "TTY_INTERACTIVE", "TERMINAL_WIDTH")


@pytest.fixture(autouse=True)
def plain_fixed_width_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every Rich console a test builds, Typer's help included, render plain text at RENDER_WIDTH."""
    for variable in _TERMINAL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    # Read by Rich when a console is built without an explicit width, as debate_cli's are.
    monkeypatch.setenv("COLUMNS", str(RENDER_WIDTH))
    monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", False)
    monkeypatch.setattr(typer.rich_utils, "COLOR_SYSTEM", None)
    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", RENDER_WIDTH)

"""Puts the repository root on `sys.path`, so `tests/fixtures/` is importable from any package.

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

REPOSITORY_ROOT = Path(__file__).parent

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

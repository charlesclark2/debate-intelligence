"""Put `tests/specs/` and `scripts/` on `sys.path` for the spec-tooling tests.

The tooling under test is standalone PEP 723 scripts rather than an installed package, and the
project's pytest import mode is `importlib`, which does not add a test module's own directory to
`sys.path` the way the default mode does.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

for directory in (HERE, HERE.parents[1] / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

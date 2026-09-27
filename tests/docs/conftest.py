"""Put `scripts/` on `sys.path` for the documentation-tooling tests.

`scripts/check_links.py` is a standalone PEP 723 script rather than an installed package, and the
project's pytest import mode is `importlib`, which does not add a test module's own directory to
`sys.path` the way the default mode does.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

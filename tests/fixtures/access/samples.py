"""Reading the saved access samples and their hand-written `expected_statuses.json` (v1-e04-t03)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

FIXTURES: Final = Path(__file__).parent


def load_expected_statuses() -> dict[str, dict[str, Any]]:
    """`expected_statuses.json`, parsed: one entry per sample, keyed by the sample's name."""
    expected: dict[str, dict[str, Any]] = json.loads(
        (FIXTURES / "expected_statuses.json").read_text(encoding="utf-8")
    )
    return expected


def sample_bytes(file_name: str) -> bytes:
    """A sample's bytes, exactly as committed."""
    return (FIXTURES / file_name).read_bytes()

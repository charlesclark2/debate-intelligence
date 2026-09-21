"""Shared fixtures for the debate `.docx` parser's tests.

The packages these tests read are built in memory by
:mod:`debate_core.testing.docx_builder`, which ships with the library because
`v1-e31-t05-parser-eval` and `v1-e31-t06-parse-pipeline` need the same helpers. What is left here
is the one thing that is genuinely per-session: the loaded style profile.
"""

from __future__ import annotations

import pytest

from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.style_profile_loader import load_style_profile


@pytest.fixture(scope="session")
def profile() -> StyleProfile:
    """The Verbatim style profile, loaded once for the whole session."""
    return load_style_profile()

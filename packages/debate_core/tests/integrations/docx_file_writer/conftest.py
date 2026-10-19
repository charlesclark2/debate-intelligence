"""Shared fixtures for the lossless card writer's tests (`v1-e33-t02`).

Every source here is synthetic, built in memory with :mod:`debate_core.testing.docx_builder`, the
convention `v1-e31-t15` set. No real team or caselist file is read or committed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from debate_core.domain.style_profile import StyleProfile
from debate_core.integrations.docx_file_writer.base_template import BaseTemplate, load_base_template
from debate_core.integrations.docx_parser.parser import DebateDocxParser


@pytest.fixture(scope="session")
def parser() -> DebateDocxParser:
    """The E31 parser at the version the writer runs under."""
    return DebateDocxParser()


@pytest.fixture(scope="session")
def profile(parser: DebateDocxParser) -> StyleProfile:
    return parser.profile


@pytest.fixture(scope="session")
def base() -> BaseTemplate:
    return load_base_template()


@pytest.fixture
def built_at() -> datetime:
    """A fixed request time: no test reads the clock."""
    return datetime(2026, 10, 19, 12, 30, tzinfo=UTC)

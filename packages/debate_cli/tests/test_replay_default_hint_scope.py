"""Who keeps the record hint when `debate-research`'s replay default names live mode (v1-e06-t09).

The live hint is the CLI's, given by its composition root to the routers `cut`, `search` and `daily`
build (`container._build_card_model_router` and `_build_search_model_router`). A program that builds its
router itself, through :func:`~debate_core.integrations.models.factory.build_model_router` (a script, an
eval runner, the shared `model_router` fixture's neighbours in a test), is somebody who records cassettes,
and its refusal under the same default still says how to record one. Nothing here reaches a model:
replay holds no real router, and the cassette directory is empty.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import load_settings
from debate_core.domain.model_contracts import ModelPrompt, TaskClass
from debate_core.integrations.models import MissingFixtureError, build_model_router
from debate_core.testing.contracts.model_router import ContractPassage

from .model_mode_hints import LIVE_MODE_HINT, RECORD_HINT

UNRECORDED_PROMPT = ModelPrompt(
    prompt_id="example.select-passage", prompt_version="9.9.9", variables={"tag": "Warming kills"}
)


@pytest.fixture(autouse=True)
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No DEBATE_* variable from the shell running the suite reaches these settings, and no mode is chosen."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def test_a_router_a_script_builds_under_the_replay_default_keeps_the_record_hint(tmp_path: Path) -> None:
    settings = load_settings(
        environment="test",
        overrides={"models": {"provider": "bedrock"}, "storage": {"data_dir": str(tmp_path / "data")}},
        env_file=tmp_path / "no.env",
    )
    router = build_model_router(settings, environ={}, cassette_dir=tmp_path / "cassettes")

    with pytest.raises(MissingFixtureError) as refused:
        asyncio.run(router.generate_structured(TaskClass.HIGH_VOLUME, UNRECORDED_PROMPT, ContractPassage))

    assert str(refused.value).endswith(f". {RECORD_HINT}")
    assert LIVE_MODE_HINT not in str(refused.value)

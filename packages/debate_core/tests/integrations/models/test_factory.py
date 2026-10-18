"""Which router a run gets: `models.provider`, then the model mode, and no code change (ac5).

The "real router" in these tests is the scripted fake from `debate_core.testing`, standing in for
the Bedrock adapter that v1-e05-t02 has not built; nothing here can reach a model or AWS.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.ports.model_router import ModelRouter, RoutingConfigError
from debate_core.application.settings import ConfigurationError, ModelSettings, Settings, load_settings
from debate_core.domain.model_contracts import ModelPrompt, ModelProvider, TaskClass
from debate_core.integrations.models import (
    FakeModelRouter,
    MissingFixtureError,
    ModelMode,
    ModelModeError,
    RecordingRefusedError,
    RecordReplayModelRouter,
    RoutingPolicy,
    build_model_router,
)
from debate_core.testing import ScriptedModelRouter
from debate_core.testing.contracts.model_router import ContractPassage
from debate_core.testing.fakes import ScriptedModelResponse

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
EXAMPLE_ROUTING_FILE = REPOSITORY_ROOT / "config" / "model_routing.example.yaml"
EXAMPLE_PROMPT = ModelPrompt(
    prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
)
NO_CI: Mapping[str, str] = {}


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


@pytest.fixture(autouse=True)
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No DEBATE_* variable from the shell running the suite reaches these settings."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def settings_with(tmp_path: Path, **models: object) -> Settings:
    """The test profile, with `models` overriding its model settings and no `.env` file."""
    return load_settings(environment="test", overrides={"models": models}, env_file=tmp_path / "no.env")


class RealRouterSpy:
    """A `RealRouterFactory` that records the policy it was given and builds a scripted router."""

    def __init__(self, *answers: ScriptedModelResponse) -> None:
        self.policies: list[RoutingPolicy] = []
        self.router = ScriptedModelRouter(answers)

    def __call__(self, policy: RoutingPolicy) -> ModelRouter:
        self.policies.append(policy)
        return self.router


# ---------------------------------------------------------------------------------------------
# models.provider = fake
# ---------------------------------------------------------------------------------------------


def test_the_test_profile_selects_the_fixture_keyed_fake(tmp_path: Path) -> None:
    settings = settings_with(tmp_path)

    router = build_model_router(settings, repository_root=REPOSITORY_ROOT)

    assert settings.models.provider is ModelProvider.FAKE
    assert isinstance(router, FakeModelRouter)
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))
    assert response.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)


def test_the_fake_does_not_read_the_mode_variable(tmp_path: Path) -> None:
    """A developer's DEBATE_MODEL_MODE, even a wrong one, does not touch a fake-provider run."""
    router = build_model_router(
        settings_with(tmp_path), environ={"DEBATE_MODEL_MODE": "nonsense"}, repository_root=REPOSITORY_ROOT
    )

    assert isinstance(router, FakeModelRouter)


def test_the_fake_ignores_a_record_option_even_in_ci(tmp_path: Path) -> None:
    """There is nothing to record from the fake, so record in CI is not refused for it either."""
    router = build_model_router(
        settings_with(tmp_path), mode="record", environ={"CI": "true"}, repository_root=REPOSITORY_ROOT
    )

    assert isinstance(router, FakeModelRouter)


def test_an_environment_variable_selects_the_fake_with_no_code_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_MODELS__PROVIDER", "fake")
    settings = load_settings(environment="dev", env_file=tmp_path / "no.env")

    assert isinstance(build_model_router(settings, repository_root=REPOSITORY_ROOT), FakeModelRouter)


# ---------------------------------------------------------------------------------------------
# A real provider: the mode decides
# ---------------------------------------------------------------------------------------------


def test_dev_and_prod_replay_by_default(tmp_path: Path) -> None:
    for environment in ("dev", "prod"):
        settings = load_settings(environment=environment, env_file=tmp_path / "no.env")

        router = build_model_router(settings, environ={}, repository_root=REPOSITORY_ROOT)

        assert settings.models.provider is ModelProvider.BEDROCK
        assert isinstance(router, RecordReplayModelRouter)
        assert router.mode is ModelMode.REPLAY


def test_a_real_provider_replays_the_committed_cassettes_by_default(tmp_path: Path) -> None:
    spy = RealRouterSpy()
    settings = settings_with(tmp_path, provider="bedrock")

    router = build_model_router(settings, environ={}, real_router=spy, repository_root=REPOSITORY_ROOT)
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert response.output == ContractPassage(paragraph_id=2, start_offset=12, end_offset=57)
    assert response.route.provider is ModelProvider.FAKE
    assert spy.policies == [], "replay never builds the real router"


def test_the_variable_selects_live_with_no_code_change(tmp_path: Path) -> None:
    spy = RealRouterSpy({"paragraph_id": 1, "start_offset": 0, "end_offset": 9})
    settings = settings_with(tmp_path, provider="bedrock")

    router = build_model_router(settings, environ={"DEBATE_MODEL_MODE": "live"}, real_router=spy)
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert isinstance(router, RecordReplayModelRouter) and router.mode is ModelMode.LIVE
    assert response.output.paragraph_id == 1
    assert spy.policies == [RoutingPolicy.load(EXAMPLE_ROUTING_FILE)]


def test_the_option_wins_over_the_variable(tmp_path: Path) -> None:
    router = build_model_router(
        settings_with(tmp_path, provider="bedrock"),
        mode="record",
        environ={"DEBATE_MODEL_MODE": "live"},
        real_router=RealRouterSpy(),
        cassette_dir=tmp_path / "cassettes",
    )

    assert isinstance(router, RecordReplayModelRouter) and router.mode is ModelMode.RECORD


def test_record_in_ci_is_refused_before_a_real_router_is_built(tmp_path: Path) -> None:
    spy = RealRouterSpy()

    with pytest.raises(RecordingRefusedError, match="CI=true"):
        build_model_router(
            settings_with(tmp_path, provider="bedrock"),
            environ={"DEBATE_MODEL_MODE": "record", "CI": "true"},
            real_router=spy,
            cassette_dir=tmp_path / "cassettes",
        )

    assert spy.policies == []


@pytest.mark.parametrize("mode", ["record", "live"])
def test_record_and_live_without_a_real_router_name_the_one_to_pass(tmp_path: Path, mode: str) -> None:
    with pytest.raises(
        ConfigurationError, match="debate_core.integrations.bedrock.bedrock_model_router"
    ) as raised:
        build_model_router(settings_with(tmp_path, provider="bedrock"), mode=mode, environ=NO_CI)

    assert raised.value.field == "models.provider"


def test_an_unknown_mode_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ModelModeError):
        build_model_router(settings_with(tmp_path, provider="bedrock"), environ={"DEBATE_MODEL_MODE": "fake"})


def test_a_bad_routing_file_fails_before_any_router_exists(tmp_path: Path) -> None:
    routing = tmp_path / "routing.yaml"
    routing.write_text(
        "version: 1\nroutes:\n  high_volume:\n    provider: bedrock\n    region: r\n    timeout_seconds: 5\n",
        encoding="utf-8",
    )
    spy = RealRouterSpy()

    with pytest.raises(RoutingConfigError) as raised:
        build_model_router(
            settings_with(tmp_path, provider="bedrock", routing_file=routing),
            mode="live",
            real_router=spy,
        )

    assert raised.value.field == "routes.high_volume.model_id"
    assert spy.policies == []


# ---------------------------------------------------------------------------------------------
# One control, and settings never choose replay
# ---------------------------------------------------------------------------------------------


def test_no_setting_chooses_record_replay_or_live(tmp_path: Path) -> None:
    every_setting = settings_with(tmp_path).redacted_dict()

    assert set(ModelSettings.model_fields) == {"provider", "routing_file", "budget_usd_daily"}
    assert [key for key in every_setting if "mode" in key.rsplit(".", 1)[-1]] == []


@pytest.mark.parametrize("value", ["replay", "record", "live"])
def test_the_provider_setting_refuses_a_mode(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match=r"models\.provider"):
        settings_with(tmp_path, provider=value)


# ---------------------------------------------------------------------------------------------
# The shared `model_router` pytest fixture
# ---------------------------------------------------------------------------------------------


def test_the_shared_model_router_fixture_is_the_offline_fake(model_router: ModelRouter) -> None:
    response = run(model_router.generate_structured(TaskClass.HIGH_VOLUME, EXAMPLE_PROMPT, ContractPassage))

    assert isinstance(model_router, FakeModelRouter)
    assert response.output == ContractPassage(paragraph_id=3, start_offset=0, end_offset=42)
    assert response.route.provider is ModelProvider.FAKE


def test_the_shared_fixture_fails_loudly_on_an_unwritten_answer(model_router: ModelRouter) -> None:
    unwritten = EXAMPLE_PROMPT.model_copy(update={"prompt_version": "9.9.9"})

    with pytest.raises(MissingFixtureError, match="example.select-passage@9.9.9"):
        run(model_router.generate_structured(TaskClass.HIGH_VOLUME, unwritten, ContractPassage))

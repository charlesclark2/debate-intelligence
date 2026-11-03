"""Record and live mode send structured calls, rendered by the prompt registry (v1-e05-t04).

`bedrock_router_factory(registry)` is passed to `build_model_router` as its `real_router`, exactly as
a composition root will. Nothing here reaches AWS: boto3's `Session.client` is replaced by one that
hands back a client held by botocore's Stubber, which answers the planned Converse call and fails the
test on any other, and the suite's socket guard is still on.

The system and user text the Stubber expects are written out by hand from
`tests/fixtures/prompts/example/select-passage.md`.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

from debate_core.application.settings import ConfigurationError, Settings, load_settings
from debate_core.domain.model_contracts import ModelProvider, TaskClass
from debate_core.integrations.bedrock import bedrock_model_router, bedrock_router_factory
from debate_core.integrations.bedrock.router import (
    build_bedrock_runtime_client,
    converse_request,
    tool_name_for,
)
from debate_core.integrations.models import (
    ModelMode,
    RecordReplayModelRouter,
    RoutingPolicy,
    build_model_router,
)
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.contracts.model_router import ContractPassage

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
EXAMPLE_ROUTING_FILE = REPOSITORY_ROOT / "config" / "model_routing.example.yaml"
SAMPLE_PROMPTS = REPOSITORY_ROOT / "tests" / "fixtures" / "prompts"

SYSTEM_TEXT = (
    "You choose one passage from a numbered list of paragraphs.\n"
    "Answer with the paragraph's number and the character offsets where the passage starts and ends.\n"
    "Never copy any of the paragraph's words into your answer."
)
USER_TEXT = "Choose the passage that best supports this tag: Warming kills"
ANSWER = {"paragraph_id": 4, "start_offset": 10, "end_offset": 80}


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


@pytest.fixture(autouse=True)
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No DEBATE_* variable from the shell running the suite reaches these settings."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """The test profile with the Bedrock provider: the example routing file, no `.env`.

    No budget limit, and a data directory of the test's own: the profile's $0 daily limit refuses
    every live call to a model with no price (v1-e05-t07), and a live call is logged under the data
    directory.
    """
    return load_settings(
        environment="test",
        overrides={
            "models": {"provider": "bedrock", "budget_usd_daily": None},
            "storage": {"data_dir": str(tmp_path / "data")},
        },
        env_file=tmp_path / "no.env",
    )


@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry.load(SAMPLE_PROMPTS)


@pytest.fixture
def stubber(fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stubber]:
    """Every bedrock-runtime client built from here on is this one, held by a Stubber."""
    route = RoutingPolicy.load(EXAMPLE_ROUTING_FILE).resolve(TaskClass.HIGH_VOLUME)
    assert route.region is not None
    client: Any = build_bedrock_runtime_client(route.region, route.timeout_seconds)

    def stubbed_client(*_: object, **__: object) -> Any:
        return client

    monkeypatch.setattr(boto3.session.Session, "client", stubbed_client)
    with Stubber(client) as stub:
        yield stub
        stub.assert_no_pending_responses()


def plan_answer(stub: Stubber) -> None:
    """Expect the sample prompt's Converse request, with the hand-written text, and answer it."""
    route = RoutingPolicy.load(EXAMPLE_ROUTING_FILE).resolve(TaskClass.HIGH_VOLUME)
    expected = converse_request(route, USER_TEXT, SYSTEM_TEXT, ContractPassage)
    assert expected["system"] == [{"text": SYSTEM_TEXT}]
    assert expected["messages"] == [{"role": "user", "content": [{"text": USER_TEXT}]}]
    stub.add_response(
        "converse",
        {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tooluse-1",
                                "name": tool_name_for(ContractPassage),
                                "input": ANSWER,
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 140, "outputTokens": 20, "totalTokens": 160},
            "metrics": {"latencyMs": 900},
            "ResponseMetadata": {"RequestId": "example-request-0003", "HTTPStatusCode": 200},
        },
        expected,
    )


def test_live_mode_sends_a_structured_call_with_the_text_the_registry_renders(
    settings: Settings, registry: PromptRegistry, stubber: Stubber, tmp_path: Path
) -> None:
    plan_answer(stubber)
    cassettes = tmp_path / "cassettes"
    router = build_model_router(
        settings,
        mode="live",
        environ={},
        real_router=bedrock_router_factory(registry),
        cassette_dir=cassettes,
    )
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    assert isinstance(router, RecordReplayModelRouter) and router.mode is ModelMode.LIVE
    assert response.output == ContractPassage(**ANSWER)
    assert response.metadata.route.provider is ModelProvider.BEDROCK
    assert response.metadata.prompt_version == "1.0.0"
    assert response.metadata.provider_request_id == "example-request-0003"
    assert not cassettes.exists()
    [day_file] = (settings.storage.data_dir / "usage").iterdir()
    [logged] = [json.loads(line) for line in day_file.read_text(encoding="utf-8").splitlines()]
    assert (logged["prompt_id"], logged["input_tokens"], logged["output_tokens"]) == (
        "example.select-passage",
        140,
        20,
    )


def test_record_mode_sends_the_call_and_writes_a_cassette_replay_then_serves(
    settings: Settings, registry: PromptRegistry, stubber: Stubber, tmp_path: Path
) -> None:
    plan_answer(stubber)
    cassettes = tmp_path / "cassettes"
    recorder = build_model_router(
        settings,
        mode="record",
        environ={},
        real_router=bedrock_router_factory(registry),
        cassette_dir=cassettes,
    )
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    recorded = run(recorder.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    [cassette] = (cassettes / "example.select-passage").iterdir()
    document = json.loads(cassette.read_text(encoding="utf-8"))
    assert document["request"]["prompt"] == {
        "prompt_id": "example.select-passage",
        "prompt_version": "1.0.0",
        "variables": {"tag": "Warming kills"},
    }
    assert SYSTEM_TEXT not in cassette.read_text(encoding="utf-8")

    replayer = build_model_router(settings, mode="replay", environ={}, cassette_dir=cassettes)
    replayed = run(replayer.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    assert replayed.output == recorded.output == ContractPassage(**ANSWER)
    assert replayed.metadata.model_id == recorded.metadata.model_id
    assert replayed.metadata.route.provider is ModelProvider.FAKE


def test_a_bedrock_router_built_without_the_registry_still_refuses_before_sending(
    settings: Settings, registry: PromptRegistry, stubber: Stubber, tmp_path: Path
) -> None:
    router = build_model_router(
        settings, mode="live", environ={}, real_router=bedrock_model_router, cassette_dir=tmp_path
    )
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    with pytest.raises(ConfigurationError, match="bedrock_router_factory"):
        run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

"""GeneratedArtifactMetadata on every structured result (v1-e05-t04-prompt-registry, ac3).

The metadata is built from the result's own route, prompt and time, so it is checked here on the
results of three routers: the fixture-keyed fake, the replay router over the committed cassette, and
the scripted fake. Each expected value is written out by hand from the fixture, cassette or script
it comes from, not read back from the code under test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.model_contracts import (
    Effort,
    ModelParams,
    ModelProvider,
    ModelResponse,
    ResolvedRoute,
    TaskClass,
)
from debate_core.domain.provenance import GeneratedArtifactMetadata
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.contracts.model_router import ContractPassage
from debate_core.testing.fakes.clock_and_ids import FixedClock
from debate_core.testing.fakes.model_router import ScriptedModelRouter

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry.load(FIXTURES / "prompts")


def test_a_fake_router_result_carries_metadata_from_its_route_and_prompt(registry: PromptRegistry) -> None:
    router = FakeModelRouter(FIXTURES / "model_outputs")
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    # tests/fixtures/model_outputs/example.select-passage/e218aaf1...json, answered by the fake.
    assert response.metadata == GeneratedArtifactMetadata(
        prompt_id="example.select-passage",
        prompt_version="1.0.0",
        route=ResolvedRoute(
            task_class=TaskClass.HIGH_VOLUME,
            provider=ModelProvider.FAKE,
            model_id="fake-fixture-model",
            timeout_seconds=60.0,
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_a_replayed_result_carries_metadata_from_the_recorded_route(registry: PromptRegistry) -> None:
    router = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=FIXTURES / "model_cassettes")
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    # tests/fixtures/model_cassettes/example.select-passage/e218aaf1...json. Replay marks the route
    # fake, with no region or profile, and keeps the recorded model id, cap, timeout and request id.
    assert response.metadata == GeneratedArtifactMetadata(
        prompt_id="example.select-passage",
        prompt_version="1.0.0",
        route=ResolvedRoute(
            task_class=TaskClass.HIGH_VOLUME,
            provider=ModelProvider.FAKE,
            model_id="example-recorded-model",
            max_tokens=256,
            timeout_seconds=30.0,
        ),
        provider_request_id="example-request-0001",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert response.metadata.model_id == "example-recorded-model"
    assert response.metadata.region is None


def test_a_scripted_router_result_carries_metadata_with_the_parameters_sent(registry: PromptRegistry) -> None:
    clock = FixedClock(datetime(2026, 10, 17, 12, 30, tzinfo=UTC))
    router = ScriptedModelRouter([{"paragraph_id": 1, "start_offset": 0, "end_offset": 9}], clock=clock)
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})

    response = run(
        router.generate_structured(
            TaskClass.COMPLEX_REASONING,
            prompt,
            ContractPassage,
            ModelParams(temperature=0.25, max_tokens=512, timeout_seconds=12.5),
        )
    )

    assert response.metadata == GeneratedArtifactMetadata(
        prompt_id="example.select-passage",
        prompt_version="1.0.0",
        route=ResolvedRoute(
            task_class=TaskClass.COMPLEX_REASONING,
            provider=ModelProvider.FAKE,
            model_id="fake-model",
            temperature=0.25,
            max_tokens=512,
            timeout_seconds=12.5,
        ),
        created_at=datetime(2026, 10, 17, 12, 30, tzinfo=UTC),
    )
    assert response.metadata.temperature == 0.25


FULL_METADATA_JSON = (
    '{"prompt_id":"card.select","prompt_version":"1.10.0",'
    '"route":{"task_class":"complex_reasoning","provider":"bedrock","model_id":"example-model-id",'
    '"inference_profile":"example-profile","region":"example-region-1","temperature":0.3,'
    '"max_tokens":2048,"timeout_seconds":45.5,"effort":"high"},'
    '"provider_request_id":"example-request-0002",'
    '"snapshot_ids":["01JA8G6Z9R4M2K7Q5W3E1T0Y8B","01JA8G6Z9R4M2K7Q5W3E1T0Y8C"],'
    '"retrieval_ids":["search-result-7","01JA8G6Z9R4M2K7Q5W3E1T0Y8D"],'
    '"created_at":"2026-10-17T12:30:45.123456Z"}'
)
"""Every field set, written by hand in the order the model declares them."""


def test_metadata_round_trips_through_json_unchanged() -> None:
    metadata = GeneratedArtifactMetadata.model_validate_json(FULL_METADATA_JSON)

    assert metadata.model_dump_json() == FULL_METADATA_JSON
    assert GeneratedArtifactMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    assert metadata.inference_profile == "example-profile"
    assert metadata.route.effort is Effort.HIGH
    assert metadata.created_at == datetime(2026, 10, 17, 12, 30, 45, 123456, tzinfo=UTC)


def test_metadata_survives_a_round_trip_of_the_response_it_came_from(registry: PromptRegistry) -> None:
    router = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=FIXTURES / "model_cassettes")
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    dumped = response.model_dump(mode="json")
    reloaded = ModelResponse[ContractPassage].model_validate(dumped)

    assert "metadata" not in dumped
    assert reloaded.metadata == response.metadata


def test_metadata_with_inputs_adds_the_snapshot_and_retrieval_ids_and_changes_nothing_else(
    registry: PromptRegistry,
) -> None:
    router = FakeModelRouter(FIXTURES / "model_outputs")
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    cited = response.metadata.with_inputs(
        snapshot_ids=["01JA8G6Z9R4M2K7Q5W3E1T0Y8B"], retrieval_ids=("search-result-7",)
    )

    assert cited.snapshot_ids == ("01JA8G6Z9R4M2K7Q5W3E1T0Y8B",)
    assert cited.retrieval_ids == ("search-result-7",)
    assert cited.model_dump(exclude={"snapshot_ids", "retrieval_ids"}) == response.metadata.model_dump(
        exclude={"snapshot_ids", "retrieval_ids"}
    )
    assert response.metadata.snapshot_ids == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_ids", ["not-a-ulid"]),
        ("retrieval_ids", ["   "]),
        ("created_at", "2026-10-17T12:30:45"),
        ("prompt_version", ""),
    ],
    ids=["snapshot-not-a-ulid", "blank-retrieval-id", "naive-time", "blank-version"],
)
def test_metadata_refuses_a_value_that_cannot_be_traced(field: str, value: object) -> None:
    document = GeneratedArtifactMetadata.model_validate_json(FULL_METADATA_JSON).model_dump(mode="json")
    document[field] = value

    with pytest.raises(ValidationError):
        GeneratedArtifactMetadata.model_validate(document)


def test_metadata_holds_no_prompt_text_variables_or_output(registry: PromptRegistry) -> None:
    router = FakeModelRouter(FIXTURES / "model_outputs")
    prompt = registry.prompt("example.select-passage", {"tag": "Warming kills"})
    response = run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, ContractPassage))

    text = response.metadata.model_dump_json()

    assert "Warming kills" not in text
    assert "Choose the passage" not in text
    assert set(GeneratedArtifactMetadata.model_fields) == {
        "prompt_id",
        "prompt_version",
        "route",
        "provider_request_id",
        "snapshot_ids",
        "retrieval_ids",
        "created_at",
    }

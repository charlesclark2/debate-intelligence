"""The model-routing file: what a valid one loads to, and what an invalid one is rejected for.

The point of validating this file at startup is that a routing mistake is otherwise discovered
mid-run, after a call has already been billed and an answer has already been produced by the
wrong model. So the tests below are mostly about rejection: each one is a mistake someone will
actually make in a YAML file, and each asserts that the error names the key to fix.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.application.ports.providers import ModelTaskClass
from debate_core.application.routing_config import (
    ROUTING_SCHEMA_VERSION,
    ModelRoute,
    RoutingConfig,
    RoutingConfigError,
    load_routing_config,
)
from debate_core.application.settings import ConfigurationError, find_repository_root

REPOSITORY_ROOT = find_repository_root(Path(__file__).parent)

VALID = """
version: 1
routes:
  complex_reasoning:
    model_id: anthropic.claude-sonnet-5
    max_tokens: 8192
    temperature: 0.2
  high_volume:
    model_id: anthropic.claude-haiku-4-5
    max_tokens: 2048
    temperature: 0.0
  embeddings:
    model_id: amazon.titan-embed-text-v2:0
"""


WriteRouting = Callable[[str], Path]
"""Writes a routing file and returns its path."""


@pytest.fixture
def write_routing(tmp_path: Path) -> WriteRouting:
    """Write a routing file into this test's own directory and return its path."""

    def write(body: str) -> Path:
        path = tmp_path / "model_routing.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    return write


# ---------------------------------------------------------------------------------------------
# A valid file
# ---------------------------------------------------------------------------------------------


def test_a_valid_file_loads_every_route(write_routing: WriteRouting) -> None:
    config = load_routing_config(write_routing(VALID))

    assert config.version == ROUTING_SCHEMA_VERSION
    assert config.routed_task_classes == {
        ModelTaskClass.COMPLEX_REASONING,
        ModelTaskClass.HIGH_VOLUME,
        ModelTaskClass.EMBEDDINGS,
    }


def test_a_route_carries_the_model_id_and_its_parameters(write_routing: WriteRouting) -> None:
    route = load_routing_config(write_routing(VALID)).route_for(ModelTaskClass.COMPLEX_REASONING)

    assert route.model_id == "anthropic.claude-sonnet-5"
    assert route.max_tokens == 8192
    assert route.temperature == 0.2


def test_max_tokens_and_temperature_are_optional(write_routing: WriteRouting) -> None:
    """An embedding call has no temperature and no output length; omitting them is correct."""
    route = load_routing_config(write_routing(VALID)).route_for(ModelTaskClass.EMBEDDINGS)

    assert route.model_id == "amazon.titan-embed-text-v2:0"
    assert (route.max_tokens, route.temperature) == (None, None)


def test_the_version_defaults_when_the_file_omits_it(write_routing: WriteRouting) -> None:
    config = load_routing_config(write_routing("routes:\n  high_volume:\n    model_id: m\n"))

    assert config.version == ROUTING_SCHEMA_VERSION


def test_a_task_class_with_no_route_is_reported_not_guessed(write_routing: WriteRouting) -> None:
    config = load_routing_config(write_routing(VALID))

    assert ModelTaskClass.RERANK in config.unrouted_task_classes
    with pytest.raises(RoutingConfigError, match="rerank"):
        config.route_for(ModelTaskClass.RERANK)


def test_a_routing_config_is_frozen(write_routing: WriteRouting) -> None:
    config = load_routing_config(write_routing(VALID))

    with pytest.raises(Exception, match="frozen|immutable"):
        config.version = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------------------------
# Rejection (acceptance criterion 2)
# ---------------------------------------------------------------------------------------------


def test_an_unknown_task_class_is_rejected_by_name(write_routing: WriteRouting) -> None:
    path = write_routing("routes:\n  card_selection:\n    model_id: anthropic.claude-sonnet-5\n")

    with pytest.raises(RoutingConfigError) as raised:
        load_routing_config(path)

    message = str(raised.value)
    assert "card_selection" in message
    assert "complex_reasoning" in message  # the error lists what is allowed
    assert raised.value.field == "routes.card_selection"


def test_a_missing_model_id_is_rejected(write_routing: WriteRouting) -> None:
    path = write_routing("routes:\n  high_volume:\n    max_tokens: 100\n")

    with pytest.raises(RoutingConfigError, match="model_id"):
        load_routing_config(path)


def test_an_empty_model_id_is_rejected(write_routing: WriteRouting) -> None:
    path = write_routing('routes:\n  high_volume:\n    model_id: ""\n')

    with pytest.raises(RoutingConfigError, match="model_id"):
        load_routing_config(path)


@pytest.mark.parametrize("temperature", ["-0.5", "2.5", "10"])
def test_an_out_of_range_temperature_is_rejected(temperature: str, write_routing: WriteRouting) -> None:
    path = write_routing(f"routes:\n  high_volume:\n    model_id: m\n    temperature: {temperature}\n")

    with pytest.raises(RoutingConfigError, match="temperature"):
        load_routing_config(path)


@pytest.mark.parametrize("max_tokens", ["0", "-1"])
def test_a_nonsensical_max_tokens_is_rejected(max_tokens: str, write_routing: WriteRouting) -> None:
    path = write_routing(f"routes:\n  high_volume:\n    model_id: m\n    max_tokens: {max_tokens}\n")

    with pytest.raises(RoutingConfigError, match="max_tokens"):
        load_routing_config(path)


def test_an_unknown_field_inside_a_route_is_rejected(write_routing: WriteRouting) -> None:
    path = write_routing("routes:\n  high_volume:\n    model_id: m\n    temprature: 0.1\n")

    with pytest.raises(RoutingConfigError, match="temprature"):
        load_routing_config(path)


def test_an_unknown_top_level_key_is_rejected(write_routing: WriteRouting) -> None:
    path = write_routing("routes:\n  high_volume:\n    model_id: m\nfallback_model: m2\n")

    with pytest.raises(RoutingConfigError, match="fallback_model"):
        load_routing_config(path)


def test_a_file_with_no_routes_at_all_is_rejected(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="routes"):
        load_routing_config(write_routing("version: 1\nroutes: {}\n"))


def test_an_empty_file_is_rejected(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="empty"):
        load_routing_config(write_routing("\n"))


def test_a_document_that_is_not_a_mapping_is_rejected(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="mapping"):
        load_routing_config(write_routing("- complex_reasoning\n- high_volume\n"))


def test_invalid_yaml_says_so(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="not valid YAML"):
        load_routing_config(write_routing("routes:\n  high_volume:\n   - model_id: [m\n"))


def test_a_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "model_routing.yaml"

    with pytest.raises(RoutingConfigError, match=str(missing)):
        load_routing_config(missing)


def test_a_routing_failure_is_a_configuration_failure(write_routing: WriteRouting) -> None:
    """Callers that handle bad configuration handle a bad routing file without knowing about it."""
    with pytest.raises(ConfigurationError):
        load_routing_config(write_routing("routes:\n  nope:\n    model_id: m\n"))


def test_yaml_tags_do_not_construct_python_objects(write_routing: WriteRouting) -> None:
    """A routing file is data; `safe_load` is what keeps it from being code."""
    path = write_routing("routes: !!python/object/apply:os.system ['echo unsafe']\n")

    with pytest.raises(RoutingConfigError):
        load_routing_config(path)


# ---------------------------------------------------------------------------------------------
# The example file this task ships
# ---------------------------------------------------------------------------------------------


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_committed_example_file_is_valid_and_routes_every_task_class() -> None:
    assert REPOSITORY_ROOT is not None
    config = load_routing_config(REPOSITORY_ROOT / "config" / "model_routing.example.yaml")

    assert config.unrouted_task_classes == frozenset()
    assert all(route.model_id for route in config.routes.values())


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_example_file_routes_the_cheap_class_to_a_different_model_than_the_expensive_one() -> None:
    assert REPOSITORY_ROOT is not None
    config = load_routing_config(REPOSITORY_ROOT / "config" / "model_routing.example.yaml")

    assert (
        config.route_for(ModelTaskClass.HIGH_VOLUME).model_id
        != config.route_for(ModelTaskClass.COMPLEX_REASONING).model_id
    )


def test_a_route_can_be_built_directly_for_a_test_double() -> None:
    route = ModelRoute(model_id="fake-model")
    config = RoutingConfig(routes={ModelTaskClass.HIGH_VOLUME: route})

    assert config.route_for(ModelTaskClass.HIGH_VOLUME) is route

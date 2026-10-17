"""The model-routing policy: what a valid file loads to, what an invalid one is refused for, and
how a call is resolved.

The point of validating this file when it loads is that a routing mistake is otherwise discovered
mid-run, after a call has already been billed and an answer has already been produced by the
wrong model. So most of these tests are about refusal: each one is a mistake someone will make
in a YAML file, and each asserts that the error names the key to fix.

The routes here use made-up identifiers (`provider-model-a`); the real ones live only in
`config/model_routing.*.yaml`, and the tests of those files assert model families, never
identifiers, so they survive the next model release.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.application.ports.model_router import RoutingConfigError
from debate_core.application.settings import ConfigurationError, find_repository_root, load_settings
from debate_core.domain.model_contracts import Effort, ModelParams, ModelProvider, ResolvedRoute, TaskClass
from debate_core.integrations.models import ROUTING_SCHEMA_VERSION, ModelRoute, RoutingPolicy
from debate_core.integrations.models.routing_policy import DEFAULT_MAX_ATTEMPTS

REPOSITORY_ROOT = find_repository_root(Path(__file__).parent)

VALID = """
version: 1
routes:
  complex_reasoning:
    provider: bedrock
    model_id: provider-model-a
    inference_profile: us.provider-model-a
    region: us-east-1
    max_tokens: 8192
    temperature: 0.2
    timeout_seconds: 300
  high_volume:
    provider: bedrock
    model_id: provider-model-b
    region: us-east-1
    max_tokens: 2048
    timeout_seconds: 60
  embeddings:
    provider: bedrock
    model_id: provider-embedder
    region: us-east-1
    timeout_seconds: 30
"""

ROUTE = "    provider: bedrock\n    region: us-east-1\n    timeout_seconds: 60\n"
"""The lines every route needs besides its model, for the one-route files below."""


WriteRouting = Callable[[str], Path]
"""Writes a routing file and returns its path."""


@pytest.fixture
def write_routing(tmp_path: Path) -> WriteRouting:
    """Write a routing file into this test's own directory and return its path."""

    def write(body: str) -> Path:
        path = tmp_path / "model_routing.test.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    return write


def refusal(write_routing: WriteRouting, body: str) -> RoutingConfigError:
    """Load `body` and return the error it was refused with."""
    with pytest.raises(RoutingConfigError) as raised:
        RoutingPolicy.load(write_routing(body))
    return raised.value


# ---------------------------------------------------------------------------------------------
# A valid file
# ---------------------------------------------------------------------------------------------


def test_a_valid_file_loads_every_route(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    assert policy.version == ROUTING_SCHEMA_VERSION
    assert policy.routed_task_classes == {
        TaskClass.COMPLEX_REASONING,
        TaskClass.HIGH_VOLUME,
        TaskClass.EMBEDDINGS,
    }


def test_a_route_carries_provider_model_profile_region_and_default_parameters(
    write_routing: WriteRouting,
) -> None:
    route = RoutingPolicy.load(write_routing(VALID)).route_for(TaskClass.COMPLEX_REASONING)

    assert route.provider is ModelProvider.BEDROCK
    assert route.model_id == "provider-model-a"
    assert route.inference_profile == "us.provider-model-a"
    assert route.region == "us-east-1"
    assert (route.max_tokens, route.temperature, route.timeout_seconds) == (8192, 0.2, 300)


def test_temperature_max_tokens_and_profile_are_optional(write_routing: WriteRouting) -> None:
    """An embedding call has no temperature and no output length, and is called in-region."""
    route = RoutingPolicy.load(write_routing(VALID)).route_for(TaskClass.EMBEDDINGS)

    assert (route.max_tokens, route.temperature, route.inference_profile) == (None, None, None)


def test_the_version_defaults_when_the_file_omits_it(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(f"routes:\n  high_volume:\n    model_id: m\n{ROUTE}"))

    assert policy.version == ROUTING_SCHEMA_VERSION


def test_an_application_inference_profile_arn_is_accepted(write_routing: WriteRouting) -> None:
    """An ARN does not spell its model, so only a system profile id is checked against `model_id`."""
    arn = "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/example"
    body = f"routes:\n  high_volume:\n    model_id: m\n    inference_profile: {arn}\n{ROUTE}"

    assert RoutingPolicy.load(write_routing(body)).route_for(TaskClass.HIGH_VOLUME).inference_profile == arn


def test_a_task_class_with_no_route_is_reported_not_guessed(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    assert TaskClass.RERANK in policy.unrouted_task_classes
    with pytest.raises(RoutingConfigError, match="rerank") as raised:
        policy.route_for(TaskClass.RERANK)
    assert raised.value.field == "routes.rerank"


def test_a_routing_policy_is_frozen(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    with pytest.raises(Exception, match="frozen|immutable"):
        policy.version = 2  # type: ignore[misc]


def test_the_policy_loads_the_file_the_settings_name(write_routing: WriteRouting) -> None:
    """`models.routing_file` is the one control; a composition root does not choose a path itself."""
    path = write_routing(VALID)
    settings = load_settings(environment="test", overrides={"models": {"routing_file": path}})

    assert RoutingPolicy.from_settings(settings) == RoutingPolicy.load(path)


# ---------------------------------------------------------------------------------------------
# Refusal when the file loads (acceptance criterion ac3)
# ---------------------------------------------------------------------------------------------


def test_an_unknown_task_class_is_refused_naming_the_key(write_routing: WriteRouting) -> None:
    error = refusal(write_routing, f"routes:\n  card_selection:\n    model_id: m\n{ROUTE}")

    assert error.field == "routes.card_selection"
    assert "routes.card_selection" in str(error)
    assert "complex_reasoning" in str(error)  # the error lists what is allowed


def test_a_missing_model_id_is_refused_naming_the_key(write_routing: WriteRouting) -> None:
    error = refusal(write_routing, f"routes:\n  high_volume:\n    max_tokens: 100\n{ROUTE}")

    assert error.field == "routes.high_volume.model_id"
    assert "routes.high_volume.model_id" in str(error)


@pytest.mark.parametrize("temperature", ["-0.5", "1.5", "2.5"])
def test_an_out_of_range_temperature_is_refused_naming_the_key(
    temperature: str, write_routing: WriteRouting
) -> None:
    """The range is 0.0 to 1.0, Claude's; 1.5 loaded under the 0 to 2 range this replaced."""
    body = f"routes:\n  high_volume:\n    model_id: m\n    temperature: {temperature}\n{ROUTE}"
    error = refusal(write_routing, body)

    assert error.field == "routes.high_volume.temperature"
    assert "routes.high_volume.temperature" in str(error)


@pytest.mark.parametrize("temperature", ["0.0", "1.0"])
def test_the_ends_of_the_temperature_range_are_accepted(
    temperature: str, write_routing: WriteRouting
) -> None:
    body = f"routes:\n  high_volume:\n    model_id: m\n    temperature: {temperature}\n{ROUTE}"

    assert RoutingPolicy.load(write_routing(body)).route_for(TaskClass.HIGH_VOLUME).temperature == float(
        temperature
    )


def test_a_routing_failure_is_a_configuration_failure(write_routing: WriteRouting) -> None:
    """Callers that handle bad configuration handle a bad routing file without knowing about it."""
    with pytest.raises(ConfigurationError):
        RoutingPolicy.load(write_routing(f"routes:\n  nope:\n    model_id: m\n{ROUTE}"))


def test_an_empty_model_id_is_refused(write_routing: WriteRouting) -> None:
    error = refusal(write_routing, f'routes:\n  high_volume:\n    model_id: ""\n{ROUTE}')

    assert error.field == "routes.high_volume.model_id"


def test_a_missing_provider_is_refused(write_routing: WriteRouting) -> None:
    body = "routes:\n  high_volume:\n    model_id: m\n    region: us-east-1\n    timeout_seconds: 60\n"

    assert refusal(write_routing, body).field == "routes.high_volume.provider"


def test_an_unknown_provider_is_refused(write_routing: WriteRouting) -> None:
    body = "routes:\n  high_volume:\n    provider: openai\n    model_id: m\n    timeout_seconds: 60\n"

    assert refusal(write_routing, body).field == "routes.high_volume.provider"


def test_the_fake_provider_cannot_be_routed_to(write_routing: WriteRouting) -> None:
    """Offline routers are a setting (v1-e05-t03); a routing file always names a real model."""
    body = "routes:\n  high_volume:\n    provider: fake\n    model_id: m\n    timeout_seconds: 60\n"

    assert "provider 'fake'" in str(refusal(write_routing, body))


def test_a_bedrock_route_without_a_region_is_refused(write_routing: WriteRouting) -> None:
    body = "routes:\n  high_volume:\n    provider: bedrock\n    model_id: m\n    timeout_seconds: 60\n"
    error = refusal(write_routing, body)

    assert error.field == "routes.high_volume"
    assert "region is required" in str(error)


def test_a_profile_of_a_different_model_is_refused(write_routing: WriteRouting) -> None:
    """A Haiku profile under a Sonnet model id would bill one model and record another."""
    body = f"routes:\n  high_volume:\n    model_id: model-a\n    inference_profile: us.model-b\n{ROUTE}"
    error = refusal(write_routing, body)

    assert error.field == "routes.high_volume"
    assert "inference_profile 'us.model-b' is not a profile of model_id 'model-a'" in str(error)


def test_a_missing_timeout_is_refused(write_routing: WriteRouting) -> None:
    body = "routes:\n  high_volume:\n    provider: bedrock\n    model_id: m\n    region: us-east-1\n"

    assert refusal(write_routing, body).field == "routes.high_volume.timeout_seconds"


@pytest.mark.parametrize("timeout", ["0", "-1", "3601"])
def test_a_nonsensical_timeout_is_refused(timeout: str, write_routing: WriteRouting) -> None:
    body = (
        "routes:\n  high_volume:\n    provider: bedrock\n    model_id: m\n    region: r\n"
        f"    timeout_seconds: {timeout}\n"
    )

    assert refusal(write_routing, body).field == "routes.high_volume.timeout_seconds"


@pytest.mark.parametrize("max_tokens", ["0", "-1"])
def test_a_nonsensical_max_tokens_is_refused(max_tokens: str, write_routing: WriteRouting) -> None:
    body = f"routes:\n  high_volume:\n    model_id: m\n    max_tokens: {max_tokens}\n{ROUTE}"

    assert refusal(write_routing, body).field == "routes.high_volume.max_tokens"


@pytest.mark.parametrize("parameter", ["temperature: 0.5", "max_tokens: 100", "effort: low"])
@pytest.mark.parametrize("scoring_class", ["embeddings", "rerank"])
def test_a_scoring_class_takes_no_sampling_parameters(
    parameter: str, scoring_class: str, write_routing: WriteRouting
) -> None:
    error = refusal(write_routing, f"routes:\n  {scoring_class}:\n    model_id: m\n    {parameter}\n{ROUTE}")

    assert f"routes.{scoring_class}.{parameter.split(':')[0]}" in str(error)


def test_an_unknown_field_inside_a_route_is_refused(write_routing: WriteRouting) -> None:
    error = refusal(write_routing, f"routes:\n  high_volume:\n    model_id: m\n    temprature: 0.1\n{ROUTE}")

    assert error.field == "routes.high_volume.temprature"


def test_an_unknown_top_level_key_is_refused(write_routing: WriteRouting) -> None:
    error = refusal(write_routing, f"routes:\n  high_volume:\n    model_id: m\n{ROUTE}fallback_model: m2\n")

    assert error.field == "fallback_model"


def test_a_file_with_no_routes_at_all_is_refused(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="routes"):
        RoutingPolicy.load(write_routing("version: 1\nroutes: {}\n"))


def test_an_empty_file_is_refused(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="empty"):
        RoutingPolicy.load(write_routing("\n"))


def test_a_document_that_is_not_a_mapping_is_refused(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="mapping"):
        RoutingPolicy.load(write_routing("- complex_reasoning\n- high_volume\n"))


def test_invalid_yaml_says_so(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="not valid YAML"):
        RoutingPolicy.load(write_routing("routes:\n  high_volume:\n   - model_id: [m\n"))


def test_a_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "model_routing.test.yaml"

    with pytest.raises(RoutingConfigError, match=str(missing)):
        RoutingPolicy.load(missing)


def test_yaml_tags_do_not_construct_python_objects(write_routing: WriteRouting) -> None:
    """A routing file is data; `safe_load` is what keeps it from being code."""
    with pytest.raises(RoutingConfigError):
        RoutingPolicy.load(write_routing("routes: !!python/object/apply:os.system ['echo unsafe']\n"))


# ---------------------------------------------------------------------------------------------
# Resolving a call (acceptance criterion ac4)
# ---------------------------------------------------------------------------------------------


def test_a_call_with_no_overrides_resolves_to_the_route_defaults(write_routing: WriteRouting) -> None:
    resolved = RoutingPolicy.load(write_routing(VALID)).resolve(TaskClass.COMPLEX_REASONING)

    assert resolved == ResolvedRoute(
        task_class=TaskClass.COMPLEX_REASONING,
        provider=ModelProvider.BEDROCK,
        model_id="provider-model-a",
        inference_profile="us.provider-model-a",
        region="us-east-1",
        temperature=0.2,
        max_tokens=8192,
        timeout_seconds=300,
    )
    assert resolved.invocation_target == "us.provider-model-a"


def test_an_override_replaces_only_the_fields_it_sets(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    resolved = policy.resolve(TaskClass.COMPLEX_REASONING, ModelParams(temperature=0.0))

    assert resolved.temperature == 0.0  # an override of zero is an override, not "unset"
    assert (resolved.max_tokens, resolved.timeout_seconds) == (8192, 300)


def test_every_overridable_field_is_merged(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    resolved = policy.resolve(
        TaskClass.HIGH_VOLUME, ModelParams(temperature=0.7, max_tokens=10, timeout_seconds=5)
    )

    assert (resolved.temperature, resolved.max_tokens, resolved.timeout_seconds) == (0.7, 10, 5)
    assert resolved.model_id == "provider-model-b"  # an override never changes the model


def test_a_route_with_no_temperature_resolves_to_none(write_routing: WriteRouting) -> None:
    """None on the resolved route means none is sent and the model's default applies."""
    resolved = RoutingPolicy.load(write_routing(VALID)).resolve(TaskClass.HIGH_VOLUME)

    assert resolved.temperature is None
    assert resolved.invocation_target == "provider-model-b"  # no profile: the model itself


def test_resolving_an_unrouted_class_is_refused(write_routing: WriteRouting) -> None:
    with pytest.raises(RoutingConfigError, match="deep_audit"):
        RoutingPolicy.load(write_routing(VALID)).resolve(TaskClass.DEEP_AUDIT)


@pytest.mark.parametrize(
    "params", [ModelParams(temperature=0.5), ModelParams(max_tokens=10), ModelParams(effort=Effort.LOW)]
)
def test_a_sampling_override_on_a_scoring_class_is_a_caller_error(
    params: ModelParams, write_routing: WriteRouting
) -> None:
    with pytest.raises(ValueError, match="embeddings call takes no temperature, max_tokens or effort"):
        RoutingPolicy.load(write_routing(VALID)).resolve(TaskClass.EMBEDDINGS, params)


# ---------------------------------------------------------------------------------------------
# Effort, attempts and dimensions (v1-e05-t02-bedrock-adapter)
# ---------------------------------------------------------------------------------------------


def test_effort_is_a_route_default_reported_on_the_resolved_route(write_routing: WriteRouting) -> None:
    body = f"routes:\n  deep_audit:\n    model_id: m\n    effort: xhigh\n{ROUTE}"

    resolved = RoutingPolicy.load(write_routing(body)).resolve(TaskClass.DEEP_AUDIT)

    assert resolved.effort is Effort.XHIGH


def test_a_per_call_effort_replaces_the_route_default(write_routing: WriteRouting) -> None:
    body = f"routes:\n  deep_audit:\n    model_id: m\n    effort: xhigh\n    max_tokens: 99\n{ROUTE}"
    policy = RoutingPolicy.load(write_routing(body))

    resolved = policy.resolve(TaskClass.DEEP_AUDIT, ModelParams(effort=Effort.LOW))

    assert resolved.effort is Effort.LOW
    assert resolved.max_tokens == 99  # the other defaults stand


def test_an_effort_override_leaves_the_other_overrides_alone(write_routing: WriteRouting) -> None:
    policy = RoutingPolicy.load(write_routing(VALID))

    resolved = policy.resolve(TaskClass.COMPLEX_REASONING, ModelParams(max_tokens=10))

    assert (resolved.effort, resolved.max_tokens) == (None, 10)


def test_a_route_with_no_effort_sends_none(write_routing: WriteRouting) -> None:
    resolved = RoutingPolicy.load(write_routing(VALID)).resolve(TaskClass.HIGH_VOLUME)

    assert resolved.effort is None


@pytest.mark.parametrize("effort", ["extreme", "HIGH", "1"])
def test_an_unknown_effort_is_refused_at_load_naming_the_key(effort: str, write_routing: WriteRouting) -> None:
    body = f"routes:\n  high_volume:\n    model_id: m\n    effort: {effort}\n{ROUTE}"

    assert refusal(write_routing, body).field == "routes.high_volume.effort"


def test_every_effort_level_loads(write_routing: WriteRouting) -> None:
    for effort in Effort:
        body = f"routes:\n  high_volume:\n    model_id: m\n    effort: {effort.value}\n{ROUTE}"

        assert RoutingPolicy.load(write_routing(body)).route_for(TaskClass.HIGH_VOLUME).effort is effort


def test_a_route_with_no_attempts_gets_the_default(write_routing: WriteRouting) -> None:
    route = RoutingPolicy.load(write_routing(VALID)).route_for(TaskClass.HIGH_VOLUME)

    assert route.max_attempts == DEFAULT_MAX_ATTEMPTS


@pytest.mark.parametrize("attempts", ["0", "-1", "9"])
def test_a_nonsensical_attempt_count_is_refused(attempts: str, write_routing: WriteRouting) -> None:
    body = f"routes:\n  high_volume:\n    model_id: m\n    max_attempts: {attempts}\n{ROUTE}"

    assert refusal(write_routing, body).field == "routes.high_volume.max_attempts"


def test_dimensions_are_read_on_an_embeddings_route(write_routing: WriteRouting) -> None:
    body = f"routes:\n  embeddings:\n    model_id: m\n    dimensions: 512\n{ROUTE}"

    assert RoutingPolicy.load(write_routing(body)).route_for(TaskClass.EMBEDDINGS).dimensions == 512


@pytest.mark.parametrize("task_class", ["high_volume", "rerank"])
def test_dimensions_on_a_route_that_returns_no_vectors_are_refused(
    task_class: str, write_routing: WriteRouting
) -> None:
    error = refusal(write_routing, f"routes:\n  {task_class}:\n    model_id: m\n    dimensions: 512\n{ROUTE}")

    assert f"routes.{task_class}.dimensions" in str(error)


def test_a_timeout_override_on_a_scoring_class_is_allowed(write_routing: WriteRouting) -> None:
    resolved = RoutingPolicy.load(write_routing(VALID)).resolve(
        TaskClass.EMBEDDINGS, ModelParams(timeout_seconds=1)
    )

    assert resolved.timeout_seconds == 1


# ---------------------------------------------------------------------------------------------
# The committed files (acceptance criterion ac2)
# ---------------------------------------------------------------------------------------------

ROUTING_FILES = ("model_routing.example.yaml", "model_routing.dev.yaml", "model_routing.prod.yaml")


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
@pytest.mark.parametrize("name", ROUTING_FILES)
def test_every_committed_routing_file_loads_and_routes_every_task_class(name: str) -> None:
    assert REPOSITORY_ROOT is not None
    policy = RoutingPolicy.load(REPOSITORY_ROOT / "config" / name)

    assert policy.unrouted_task_classes == frozenset()
    assert {route.provider for route in policy.routes.values()} == {ModelProvider.BEDROCK}


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_default_file_routes_each_class_to_the_family_the_spec_names() -> None:
    """ac2, by family: an assert on a full identifier would fail on the next model release."""
    assert REPOSITORY_ROOT is not None
    policy = RoutingPolicy.load(REPOSITORY_ROOT / "config" / "model_routing.example.yaml")

    assert "claude-sonnet" in policy.route_for(TaskClass.COMPLEX_REASONING).model_id
    assert "claude-haiku" in policy.route_for(TaskClass.HIGH_VOLUME).model_id
    assert "claude-opus" in policy.route_for(TaskClass.DEEP_AUDIT).model_id
    assert "titan-embed" in policy.route_for(TaskClass.EMBEDDINGS).model_id
    assert "cohere.rerank" in policy.route_for(TaskClass.RERANK).model_id


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
@pytest.mark.parametrize("name", ROUTING_FILES)
def test_no_committed_claude_route_sends_a_temperature(name: str) -> None:
    """The current Claude models reject any temperature but their default (PM ruling, 2026-10-16)."""
    assert REPOSITORY_ROOT is not None
    policy = RoutingPolicy.load(REPOSITORY_ROOT / "config" / name)

    claude_routes = [route for route in policy.routes.values() if "claude" in route.model_id]
    assert claude_routes
    assert all(route.temperature is None for route in claude_routes)
    assert all(route.inference_profile is not None for route in claude_routes)


def test_a_route_can_be_built_directly_for_a_test_double() -> None:
    route = ModelRoute(provider=ModelProvider.BEDROCK, model_id="m", region="r", timeout_seconds=1)
    policy = RoutingPolicy(routes={TaskClass.HIGH_VOLUME: route})

    assert policy.route_for(TaskClass.HIGH_VOLUME) is route

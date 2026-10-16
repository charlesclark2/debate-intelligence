"""The model-routing policy: which model answers each task class, as data rather than code.

Application code names a :class:`~debate_core.domain.model_contracts.TaskClass` ("this is
high-volume classification") and never a model id. What a class resolves to lives in a YAML file
this module reads and validates, so upgrading a model is a configuration change rather than a
search-and-replace across the platform (architecture proposal §10, ADR-0005). A routing file looks
like this::

    version: 1
    routes:
      complex_reasoning:
        provider: bedrock
        model_id: anthropic.claude-sonnet-5-5
        inference_profile: us.anthropic.claude-sonnet-5-5
        region: us-east-1
        max_tokens: 8192
        timeout_seconds: 300

Identifiers live only in `config/model_routing.*.yaml`: the example file, which is the default
and the template, and one file per environment (`v1-e01-t09-dev-prerelease-channel`). Which one a
run reads is the `models.routing_file` setting, so :meth:`RoutingPolicy.from_settings` is how a
composition root loads it.

## Validated once, when the file loads

A key that is not a task class, a missing `model_id`, a temperature outside 0.0 to 1.0, a stray
field, an inference profile that belongs to a different model, a Bedrock route with no region:
each is refused by :meth:`RoutingPolicy.load` with a
:class:`~debate_core.application.ports.model_router.RoutingConfigError` naming the key. A file
that cannot load cannot start anything, and the alternative is finding the typo halfway through a
run that has already spent money.

## Resolving a call

:meth:`RoutingPolicy.resolve` merges a call's :class:`~debate_core.domain.model_contracts.ModelParams`
over its route's defaults, field by field, into the
:class:`~debate_core.domain.model_contracts.ResolvedRoute` an adapter sends and every response
reports. A class with no route is refused rather than sent to another class's model.

History: `v1-e02-t05-settings-config` wrote the first schema and loader, as
`debate_core.application.routing_config`; `v1-e05-t01-model-router-port` moved them here and added
the provider, inference profile, region, timeout and resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from debate_core.application.ports.model_router import RoutingConfigError
from debate_core.application.settings import Settings
from debate_core.domain.model_contracts import (
    MAX_OUTPUT_TOKENS,
    MAX_TEMPERATURE,
    MAX_TIMEOUT_SECONDS,
    MIN_TEMPERATURE,
    ModelParams,
    ModelProvider,
    ResolvedRoute,
    TaskClass,
)

__all__ = ["ROUTING_SCHEMA_VERSION", "ModelRoute", "RoutingPolicy"]

ROUTING_SCHEMA_VERSION = 1
"""Version of the routing file's own shape. Bumped only by a change that breaks existing files."""

_ARN_PREFIX = "arn:"


class ModelRoute(BaseModel):
    """What one task class routes to, and the parameters a call gets unless it overrides them.

    `temperature` and `max_tokens` are optional. A scoring class (embeddings, rerank) has neither,
    and the current Claude models reject any temperature but their default, so their routes leave
    it unset; a value is validated whenever it is present.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        # `model_id` is this domain's own term (architecture proposal §10), not an intrusion into
        # Pydantic's reserved `model_` namespace.
        protected_namespaces=(),
    )

    provider: ModelProvider = Field(description="Who answers calls on this route.")
    model_id: str = Field(
        min_length=1,
        description="The provider's identifier of the foundation model, e.g. a Bedrock model id.",
    )
    inference_profile: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Inference profile to call the model through: a system profile id such as "
            "`us.<model_id>`, or an application profile's ARN. Unset calls the model in-region."
        ),
    )
    region: str | None = Field(
        default=None, min_length=1, description="Region the call is sent to. Required for Bedrock."
    )
    temperature: float | None = Field(
        default=None,
        ge=MIN_TEMPERATURE,
        le=MAX_TEMPERATURE,
        description="Default sampling temperature; unset sends none, so the model's default applies.",
    )
    max_tokens: int | None = Field(
        default=None, ge=1, le=MAX_OUTPUT_TOKENS, description="Default output cap for a generative call."
    )
    timeout_seconds: float = Field(
        gt=0, le=MAX_TIMEOUT_SECONDS, description="Default wall-clock limit for a call, in seconds."
    )

    @model_validator(mode="after")
    def _check_route(self) -> Self:
        if self.provider is ModelProvider.FAKE:
            raise ValueError(
                "provider 'fake' cannot be routed to; offline routers are chosen by settings, not by "
                "the routing file"
            )
        if self.provider is ModelProvider.BEDROCK and self.region is None:
            raise ValueError("region is required for a bedrock route")
        profile = self.inference_profile
        is_system_profile = profile is not None and not profile.startswith(_ARN_PREFIX)
        if is_system_profile and not str(profile).endswith(f".{self.model_id}"):
            raise ValueError(
                f"inference_profile {profile!r} is not a profile of model_id {self.model_id!r}; "
                f"a system profile is named <geography>.{self.model_id}"
            )
        return self


class RoutingPolicy(BaseModel):
    """A whole routing file: every task class it routes, and how a call on each is resolved."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, protected_namespaces=())

    version: int = Field(
        default=ROUTING_SCHEMA_VERSION, ge=1, description="Schema version of this routing file."
    )
    routes: dict[TaskClass, ModelRoute] = Field(
        description="One entry per task class this file routes. Unknown keys are rejected."
    )

    @model_validator(mode="after")
    def _check_routes(self) -> Self:
        if not self.routes:
            raise ValueError("routes must name at least one task class")
        for task_class, route in self.routes.items():
            if not task_class.is_generative:
                for name in ("temperature", "max_tokens"):
                    if getattr(route, name) is not None:
                        raise ValueError(
                            f"routes.{task_class.value}.{name}: a {task_class.value} call does not "
                            f"generate output, so it takes no {name}"
                        )
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate the routing file at `path`.

        Raises :class:`RoutingConfigError`, naming the file and, where the failure is about one
        entry, the offending key, if the file is missing, is not YAML, or does not match the schema.
        """
        source = str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise RoutingConfigError(f"model-routing file not found: {path}", source=source) from error
        except OSError as error:
            raise RoutingConfigError(f"could not read {path}: {error}", source=source) from error

        try:
            # safe_load, not load: a routing file is data, and nothing in it should be able to
            # construct a Python object.
            document: Any = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise RoutingConfigError(f"{path} is not valid YAML: {error}", source=source) from error

        if document is None:
            raise RoutingConfigError(f"{path} is empty", source=source)
        if not isinstance(document, dict):
            raise RoutingConfigError(
                f"{path} must contain a mapping with a `routes` key, not a {type(document).__name__}",
                source=source,
            )

        try:
            return cls.model_validate(document)
        except ValidationError as error:
            raise RoutingConfigError(
                _describe(error, path), source=source, field=_first_field(error)
            ) from error

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Load the routing file the run's settings name (`models.routing_file`)."""
        return cls.load(settings.models.routing_file)

    @property
    def routed_task_classes(self) -> frozenset[TaskClass]:
        """The task classes this file has a route for."""
        return frozenset(self.routes)

    @property
    def unrouted_task_classes(self) -> frozenset[TaskClass]:
        """Task classes with no route here; calling one of them fails rather than guesses."""
        return frozenset(TaskClass) - self.routed_task_classes

    def route_for(self, task_class: TaskClass) -> ModelRoute:
        """The route for `task_class`, or a failure that names the missing key.

        Never falls back to another class's model. A silent fallback would mean a cheap
        classification billed at a reasoning model's rate, or a reasoning task answered by the
        cheap model with nobody noticing until the output is wrong.
        """
        route = self.routes.get(task_class)
        if route is None:
            routed = ", ".join(sorted(member.value for member in self.routed_task_classes))
            raise RoutingConfigError(
                f"no route for task class {task_class.value!r}; this file routes {routed}",
                field=f"routes.{task_class.value}",
            )
        return route

    def resolve(self, task_class: TaskClass, params: ModelParams | None = None) -> ResolvedRoute:
        """The route a call on `task_class` takes, with `params` merged over the route's defaults.

        A field `params` leaves unset keeps the route's value; a set field replaces it. Raises
        `ValueError` for a sampling override on a class that does not generate output, which is a
        caller's mistake rather than the file's.
        """
        overrides = params if params is not None else ModelParams()
        if not task_class.is_generative and (
            overrides.temperature is not None or overrides.max_tokens is not None
        ):
            raise ValueError(f"a {task_class.value} call takes no temperature or max_tokens")
        route = self.route_for(task_class)
        return ResolvedRoute(
            task_class=task_class,
            provider=route.provider,
            model_id=route.model_id,
            inference_profile=route.inference_profile,
            region=route.region,
            temperature=overrides.temperature if overrides.temperature is not None else route.temperature,
            max_tokens=overrides.max_tokens if overrides.max_tokens is not None else route.max_tokens,
            timeout_seconds=(
                overrides.timeout_seconds if overrides.timeout_seconds is not None else route.timeout_seconds
            ),
        )


def _describe(error: ValidationError, path: Path) -> str:
    """Pydantic's report, rewritten to name the key in the file rather than a Python location."""
    problems = "; ".join(f"{_dotted(detail['loc'])}: {detail['msg']}" for detail in error.errors())
    return f"{path} is not a valid model-routing file: {problems}"


def _first_field(error: ValidationError) -> str | None:
    """The first offending key, dotted, for a caller that wants to point at one line."""
    details = error.errors()
    return _dotted(details[0]["loc"]) if details else None


def _dotted(location: tuple[Any, ...]) -> str:
    """A Pydantic error location as the path through the YAML document: `routes.high_volume`.

    Pydantic appends `[key]` when the invalid thing is a mapping key rather than its value. That
    is true but not useful to someone reading an error about their YAML file, where the key *is*
    the line, so it is dropped.
    """
    parts = [str(part) for part in location if str(part) != "[key]"]
    return ".".join(parts) or "(document)"

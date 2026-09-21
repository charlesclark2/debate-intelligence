"""The model-routing file: which model each task class is answered by, as data rather than code.

Application code names a :class:`~debate_core.application.ports.providers.ModelTaskClass` — "this
is high-volume classification", "this is complex reasoning" — and never a model id. What that
class resolves to lives in a YAML file this module reads and validates, so upgrading a model is a
configuration change rather than a search-and-replace across the platform (architecture proposal
§10, ADR-005).

The file looks like this::

    version: 1
    routes:
      complex_reasoning:
        model_id: anthropic.claude-sonnet-5
        max_tokens: 8192
        temperature: 0.2

A key that is not a task class is rejected by name, as is a missing `model_id`, a temperature
outside its range or a stray field. Configuration is validated once, at startup, because the
alternative is discovering the typo halfway through a run that has already spent money.

## Boundaries

This task (`v1-e02-t05-settings-config`) owns the schema and the loader, and
`config/model_routing.example.yaml` next to it. The routing *policy* — the per-environment files,
provider and region selection, per-call parameter overrides and the resolved route reported back
on every response — is `v1-e05-t01-model-router-port`, which extends :class:`ModelRoute` rather
than replacing it. The dev and prod files themselves are written by
`v1-e01-t09-dev-prerelease-channel`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from debate_core.application.ports.providers import ModelTaskClass
from debate_core.application.settings import ConfigurationError

__all__ = [
    "ROUTING_SCHEMA_VERSION",
    "ModelRoute",
    "RoutingConfig",
    "RoutingConfigError",
    "load_routing_config",
]

ROUTING_SCHEMA_VERSION = 1
"""Version of the routing file's own shape. Bumped only by a change that breaks existing files."""


class RoutingConfigError(ConfigurationError):
    """A routing file is missing, unreadable, or does not match the schema.

    A subclass of :class:`~debate_core.application.settings.ConfigurationError` because that is
    what it is — one badly configured file — and so the CLI reports it as a configuration problem
    the user can fix, with the same exit code as any other.
    """


class ModelRoute(BaseModel):
    """What one task class resolves to.

    `max_tokens` and `temperature` are optional because they are meaningless for some classes: an
    embedding call has no temperature and no output length to cap. They are validated when
    present, which is the case that matters — a temperature of `5` is a file that should never
    have loaded.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        # `model_id` is this domain's own term (architecture proposal §10), not an intrusion into
        # Pydantic's reserved `model_` namespace.
        protected_namespaces=(),
    )

    model_id: str = Field(
        min_length=1,
        description="The provider's identifier for the model, e.g. `anthropic.claude-sonnet-5`.",
    )
    max_tokens: int | None = Field(
        default=None, ge=1, le=1_000_000, description="Output cap for a generative call."
    )
    temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Sampling temperature for a generative call."
    )


class RoutingConfig(BaseModel):
    """A whole routing file: every task class that has a route, and what it routes to."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, protected_namespaces=())

    version: int = Field(
        default=ROUTING_SCHEMA_VERSION, ge=1, description="Schema version of this routing file."
    )
    routes: dict[ModelTaskClass, ModelRoute] = Field(
        description="One entry per task class this file routes. Unknown keys are rejected."
    )

    @model_validator(mode="after")
    def _check_not_empty(self) -> Self:
        if not self.routes:
            raise ValueError("routes must name at least one task class")
        return self

    @property
    def routed_task_classes(self) -> frozenset[ModelTaskClass]:
        """The task classes this file has a route for."""
        return frozenset(self.routes)

    @property
    def unrouted_task_classes(self) -> frozenset[ModelTaskClass]:
        """Task classes with no route here; calling one of them fails rather than guesses."""
        return frozenset(ModelTaskClass) - self.routed_task_classes

    def route_for(self, task_class: ModelTaskClass) -> ModelRoute:
        """The route for `task_class`, or a failure that says which file is missing it.

        Never falls back to another class's model. A silent fallback would mean a cheap
        classification silently billed at a reasoning model's rate, or the reverse — a reasoning
        task answered by the cheap model and nobody noticing until the output is wrong.
        """
        route = self.routes.get(task_class)
        if route is None:
            routed = ", ".join(sorted(member.value for member in self.routed_task_classes))
            raise RoutingConfigError(
                f"no route for task class {task_class.value!r}; this file routes {routed}",
                field=f"routes.{task_class.value}",
            )
        return route


def load_routing_config(path: Path) -> RoutingConfig:
    """Read and validate the routing file at `path`.

    Raises :class:`RoutingConfigError` — naming the file and, where the failure is about one
    entry, the offending key — if the file is missing, is not YAML, or does not match the schema.
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
        return RoutingConfig.model_validate(document)
    except ValidationError as error:
        raise RoutingConfigError(_describe(error, path), source=source, field=_first_field(error)) from error


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

"""Where a generated artifact came from: the model, the prompt version, the parameters and the inputs.

Anything a model influenced is persisted with a :class:`GeneratedArtifactMetadata`, so that a card
tag, a selection or a summary can always be traced to the model that produced it, the exact prompt
version it ran and the sources it was shown (architecture proposal §2 and §10, ADR-0005,
v1-e05-t04-prompt-registry). A generated artifact persisted without one is forbidden.

Every structured model result carries its metadata: :attr:`ModelResponse.metadata
<debate_core.domain.model_contracts.ModelResponse.metadata>` builds it from the response's own
route, prompt and time, so no router can return a result without it or with a different one. The
caller adds what only it knows, the snapshots and retrieved items the prompt's variables came from,
with :meth:`GeneratedArtifactMetadata.with_inputs` before persisting.

An output the structured-output guard had to repair says so: `repair_attempted` is true and
`repair_prompt_version` names the version of the `model.repair` prompt that produced it, while
`prompt_id` and `prompt_version` stay the prompt the call ran (v1-e05-t05-structured-output-validation).

The metadata holds identifiers and parameters only. It never holds prompt text, variables or model
output, so it can be logged and exported without carrying evidence or a student's work with it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Ulid, UtcDatetime
from debate_core.domain.model_contracts import ResolvedRoute

__all__ = ["GeneratedArtifactMetadata"]


class GeneratedArtifactMetadata(DomainModel):
    """The provenance of one generated artifact: which call produced it, and from which inputs."""

    prompt_id: NonEmptyText = Field(description="Identifier of the registered prompt that was run.")
    prompt_version: NonEmptyText = Field(description="The exact version of that prompt.")
    route: ResolvedRoute = Field(
        description=(
            "The route the call took: model id, inference profile, region, and the temperature and other "
            "parameters actually sent."
        )
    )
    provider_request_id: NonEmptyText | None = Field(
        default=None, description="The provider's id for the request, when it gave one."
    )
    snapshot_ids: tuple[Ulid, ...] = Field(
        default=(), description="The source snapshots whose text the prompt was given, in the order given."
    )
    retrieval_ids: tuple[NonEmptyText, ...] = Field(
        default=(), description="The retrieved items (search results, cards) the prompt was given, in order."
    )
    created_at: UtcDatetime = Field(description="When the model call was made, in UTC.")
    repair_attempted: bool = Field(
        default=False,
        description="Whether the first answer failed validation and this output came from the repair call.",
    )
    repair_prompt_version: NonEmptyText | None = Field(
        default=None, description="The version of the `model.repair` prompt that produced it, when repaired."
    )

    @model_validator(mode="after")
    def _repair_fields_agree(self) -> Self:
        if self.repair_attempted != (self.repair_prompt_version is not None):
            raise ValueError("repair_prompt_version is set exactly when repair_attempted is true")
        return self

    @property
    def model_id(self) -> str:
        """The foundation model that answered."""
        return self.route.model_id

    @property
    def inference_profile(self) -> str | None:
        """The inference profile the call went through, when there was one."""
        return self.route.inference_profile

    @property
    def region(self) -> str | None:
        """The region the call was sent to; `None` for an offline router."""
        return self.route.region

    @property
    def temperature(self) -> float | None:
        """The temperature sent; `None` when the model's default applied."""
        return self.route.temperature

    def with_inputs(self, *, snapshot_ids: Iterable[str] = (), retrieval_ids: Iterable[str] = ()) -> Self:
        """This metadata with the snapshots and retrieved items the call's variables came from."""
        return self.evolve(snapshot_ids=tuple(snapshot_ids), retrieval_ids=tuple(retrieval_ids))

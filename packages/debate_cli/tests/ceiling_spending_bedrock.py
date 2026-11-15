"""A stand-in for Bedrock whose every call costs the most it could, for the commands' live-mode tests.

`search --expand-llm --auto-cut` (v1-e08-t17) and `daily --auto-cut` (v1-e08-t22) let the container
build every model router itself, live, through the usage log and the budget guard, over this stand-in
for `bedrock_router_factory`. Each call is reported as its guard ceiling: its prompt variables' bytes
in and its route's whole output cap out, on its route's model, so what it costs comes from the
committed routing and pricing files, never from a figure written in a test. No call leaves the process.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel
from tests.fixtures.card.every_page_router import EveryPageRouter
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE

from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.query_expansion import EXPAND_PROMPT_ID
from debate_core.application.settings import Settings
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    TaskClass,
)
from debate_core.integrations.models.factory import RealRouterFactory
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.routing_policy import RoutingPolicy
from debate_core.testing.fakes.model_router import ScriptedModelRouter

__all__ = ["MODEL_EXPANSION", "SpendsItsCeiling", "bedrock_stand_in", "live", "usage_records"]

MODEL_EXPANSION: Final = {
    "queries": [{"query": "health insurance midterm stakes", "rationale": "What the midterms mean for it."}]
}
"""What the stand-in answers `search.expand` with: one extra query."""


class SpendsItsCeiling:
    """Bedrock's stand-in for one router: answers as `EveryPageRouter` and the scripted expansion do,
    and reports every call as the most it could cost on its route: its prompt variables' bytes in, its
    route's whole output cap out, on its route's model, which is the budget guard's ceiling of it."""

    def __init__(self, policy: RoutingPolicy) -> None:
        self._policy = policy
        self._cards = EveryPageRouter()
        self._expansions = ScriptedModelRouter()

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if prompt.prompt_id == EXPAND_PROMPT_ID:
            self._expansions.enqueue(MODEL_EXPANSION)
            answered = await self._expansions.generate_structured(task_class, prompt, schema, params)
        else:
            answered = await self._cards.generate_structured(task_class, prompt, schema, params)
        route = self._policy.resolve(task_class, params)
        variables = json.dumps(prompt.variables, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        usage = ModelUsage(
            input_tokens=len(variables.encode("utf-8")), output_tokens=route.max_tokens, latency_ms=1.0
        )
        return answered.model_copy(update={"route": route, "usage": usage})

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        raise AssertionError("a search and its cuts embed nothing")

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        raise AssertionError("a search and its cuts rerank nothing")


def bedrock_stand_in(registry: PromptRegistry) -> RealRouterFactory:
    """In place of `debate_core.integrations.bedrock.bedrock_router_factory`."""

    def factory(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return SpendsItsCeiling(policy)

    return factory


def live(per_run_usd: float | None = None) -> Callable[[Settings], Settings]:
    """The profile's settings for a live run on the example routing file, with no daily limit, so
    `per_run_usd` (`models.budget_usd_per_run`) and `--max-cost` are the only limits."""

    def settings_for(settings: Settings) -> Settings:
        models = settings.models.model_copy(
            update={
                "provider": ModelProvider.BEDROCK,
                "routing_file": EXAMPLE_ROUTING_FILE,
                "budget_usd_daily": None,
                "budget_usd_per_run": per_run_usd,
            }
        )
        return settings.model_copy(update={"models": models})

    return settings_for


def usage_records(data_dir: Path) -> list[dict[str, Any]]:
    """Every call the usage log under `data_dir` recorded, in the order it recorded them."""
    return [
        json.loads(line)
        for path in sorted((data_dir / "usage").glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

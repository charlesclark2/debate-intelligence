"""The first real call on each route: what each Bedrock model accepts, asked of Bedrock itself.

Operator-run, with the operator's own credentials, never in a test or in CI (v1-e05-t02's ac7).
It reads every identifier, profile and region from the routing file it is given, so nothing here
names a model::

    AWS_PROFILE=<profile> uv run python -m debate_core.integrations.bedrock.first_call \
        --routing-file config/model_routing.dev.yaml

For every Claude route it makes one structured call exactly as the adapter does (the schema as the
only tool, `toolChoice` `auto`), then one request per question, each changed in one way from that
call:

| Probe | Changed from the adapter's call |
|---|---|
| `toolChoice any` | `toolChoice` `{"any": {}}` |
| `toolChoice tool` | `toolChoice` `{"tool": {"name": ...}}` |
| `temperature 0.5` | `inferenceConfig.temperature` 0.5 |
| `effort low` | `outputConfig.effort` `low` |
| `structured output` | `outputConfig.textFormat` with the schema, and no tools |
| `strict tool` | the tool's `strict` set |

Then one embedding and one rerank, to show those ids resolve. Each request is answered
`accepted` or `refused`, with Bedrock's error code and message, and the table printed is what the
report records. Every request is small (a few hundred tokens) and is billed like any other.

The prompt wording below is a diagnostic's, not a production prompt: production prompts come only
from the prompt registry (v1-e05-t04).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict

from debate_core.application.errors import DomainError, ModelAccessDenied, ModelRequestRejected
from debate_core.domain.model_contracts import (
    ModelParams,
    ModelPrompt,
    RenderedPrompt,
    ResolvedRoute,
    TaskClass,
)
from debate_core.integrations.bedrock.failures import translate_bedrock_error
from debate_core.integrations.bedrock.router import (
    BedrockModelRouter,
    ClientFactory,
    build_bedrock_runtime_client,
    converse_request,
    tool_name_for,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = ["PROBE_MAX_TOKENS", "Finding", "ProbeAnswer", "main", "render_table", "run_first_call"]

PROBE_MAX_TOKENS: Final = 2048
"""Output cap on every probe: room for a model's thinking and one short tool call, and no more."""

ACCEPTED: Final = "accepted"
REFUSED: Final = "refused"
NOT_TRIED: Final = "not tried"

_PROMPT: Final = ModelPrompt(prompt_id="bedrock.first-call", prompt_version="1.0.0")
_USER_TEXT: Final = "Call the ProbeAnswer tool once, with colour set to blue. Do not write anything else."
_STRUCTURED_TEXT: Final = 'Reply with the JSON object {"colour": "blue"} and nothing else.'


class ProbeAnswer(BaseModel):
    """The colour the request names."""

    model_config = ConfigDict(extra="forbid")

    colour: str


@dataclass(frozen=True, slots=True)
class Finding:
    """What Bedrock answered to one probe on one route."""

    task_class: TaskClass
    target: str
    probe: str
    outcome: str
    detail: str


def _render(_: ModelPrompt) -> RenderedPrompt:
    return RenderedPrompt(user=_USER_TEXT)


def _variants(route: ResolvedRoute) -> list[tuple[str, dict[str, Any]]]:
    """Each question as a Converse request: the adapter's own call, changed in exactly one way."""
    base = converse_request(route, _USER_TEXT, None, ProbeAnswer)
    name = tool_name_for(ProbeAnswer)

    def changed(edit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        request = copy.deepcopy(base)
        edit(request)
        return request

    def structured(request: dict[str, Any]) -> None:
        del request["toolConfig"]
        request["messages"] = [{"role": "user", "content": [{"text": _STRUCTURED_TEXT}]}]
        request["outputConfig"] = {
            "textFormat": {
                "type": "json_schema",
                "structure": {
                    "jsonSchema": {"name": name, "schema": _json_text(ProbeAnswer.model_json_schema())}
                },
            }
        }

    return [
        ("toolChoice any", changed(lambda r: r["toolConfig"].update(toolChoice={"any": {}}))),
        ("toolChoice tool", changed(lambda r: r["toolConfig"].update(toolChoice={"tool": {"name": name}}))),
        ("temperature 0.5", changed(lambda r: r.setdefault("inferenceConfig", {}).update(temperature=0.5))),
        ("effort low", changed(lambda r: r.update(outputConfig={"effort": "low"}))),
        ("structured output", changed(structured)),
        ("strict tool", changed(lambda r: r["toolConfig"]["tools"][0]["toolSpec"].update(strict=True))),
    ]


async def run_first_call(
    policy: RoutingPolicy, *, client_factory: ClientFactory = build_bedrock_runtime_client
) -> list[Finding]:
    """Probe every route `policy` has, and return what Bedrock answered to each probe."""
    router = BedrockModelRouter(policy, render_prompt=_render, client_factory=client_factory)
    params = ModelParams(max_tokens=PROBE_MAX_TOKENS)
    findings: list[Finding] = []
    for task_class in sorted(policy.routed_task_classes, key=list(TaskClass).index):
        if task_class.is_generative:
            findings.extend(await _probe_generative(router, task_class, policy.resolve(task_class, params)))
        else:
            findings.append(await _probe_scoring(router, task_class, policy.resolve(task_class)))
    return findings


async def _probe_generative(
    router: BedrockModelRouter, task_class: TaskClass, route: ResolvedRoute
) -> list[Finding]:
    target = route.invocation_target
    params = ModelParams(max_tokens=PROBE_MAX_TOKENS)
    try:
        response = await router.generate_structured(task_class, _PROMPT, ProbeAnswer, params)
    except DomainError as error:
        first = Finding(
            task_class, target, "toolChoice auto (the adapter's call)", _outcome(error), str(error)
        )
        if isinstance(error, ModelAccessDenied):
            rest = [
                Finding(task_class, target, probe, NOT_TRIED, "access denied")
                for probe, _ in _variants(route)
            ]
            return [first, *rest]
    else:
        detail = f"answered {response.output.model_dump()}; request id {response.provider_request_id}"
        first = Finding(task_class, target, "toolChoice auto (the adapter's call)", ACCEPTED, detail)
    findings = [first]
    client = router.client_for(route)
    for probe, request in _variants(route):
        try:
            answer = await asyncio.to_thread(client.converse, **request)
        except (ClientError, BotoCoreError) as error:
            translated = translate_bedrock_error(error, target)
            findings.append(Finding(task_class, target, probe, _outcome(translated), str(translated)))
        else:
            stop = answer.get("stopReason")
            request_id = answer.get("ResponseMetadata", {}).get("RequestId")
            findings.append(
                Finding(task_class, target, probe, ACCEPTED, f"stopReason {stop}; request id {request_id}")
            )
    return findings


async def _probe_scoring(router: BedrockModelRouter, task_class: TaskClass, route: ResolvedRoute) -> Finding:
    probe = "embed one text" if task_class is TaskClass.EMBEDDINGS else "rerank two documents"
    try:
        if task_class is TaskClass.EMBEDDINGS:
            embedded = await router.embed(["A short text to embed."])
            detail = f"{embedded.dimensions} dimensions; request id {embedded.provider_request_id}"
        else:
            reranked = await router.rerank("blue", ["The sky is blue.", "Grass is green."])
            order = [result.index for result in reranked.results]
            detail = f"order {order}; request id {reranked.provider_request_id}"
    except DomainError as error:
        return Finding(task_class, route.invocation_target, probe, _outcome(error), str(error))
    return Finding(task_class, route.invocation_target, probe, ACCEPTED, detail)


def _outcome(error: DomainError) -> str:
    """`refused` for a refusal of the request or the caller; anything else is a failure to answer."""
    return (
        REFUSED
        if isinstance(error, ModelRequestRejected | ModelAccessDenied)
        else f"failed ({type(error).__name__})"
    )


def _json_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True)


def render_table(findings: Sequence[Finding]) -> str:
    """The findings as the Markdown table the session report records."""
    rows = ["| Class | Called as | Probe | Outcome | Detail |", "|---|---|---|---|---|"]
    for finding in findings:
        cells = (
            finding.task_class.value,
            f"`{finding.target}`",
            finding.probe,
            finding.outcome,
            finding.detail,
        )
        rows.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> int:
    """Probe the routes of `--routing-file` and print the table. Exits 1 if any probe could not run."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--routing-file", type=Path, required=True, help="config/model_routing.<env>.yaml")
    arguments = parser.parse_args(argv)
    policy = RoutingPolicy.load(arguments.routing_file)
    findings = asyncio.run(run_first_call(policy))
    print(render_table(findings))
    return 1 if any(finding.outcome.startswith(("failed", NOT_TRIED)) for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())

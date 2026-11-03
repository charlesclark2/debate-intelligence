"""The first real call on each route: what each Bedrock model accepts, asked of Bedrock itself.

Operator-run, with the operator's own credentials, never in a test or in CI (v1-e05-t02's ac7,
moved to v1-e05-t08-bedrock-invoke-access's ac5). It reads every identifier, profile and region from
the routing files it is given, or from `models.routing_file` when it is given none, so nothing here
names a model. Every request is signed with the AWS profile `models.aws_profile` names, as every
Bedrock call is, and never with `AWS_PROFILE`::

    DEBATE_ENV=dev uv run python -m debate_core.integrations.bedrock.first_call \
        --routing-file config/model_routing.dev.yaml --routing-file config/model_routing.prod.yaml

**Each model is asked once.** Routes that call the same inference profile or model in the same
region are one target, however many classes or files name it: the dev and prod files name three
Claude models between them, so one run over both asks three models, not six routes. Each row names
every route its target serves.

For every Claude target it makes one structured call exactly as the adapter does (the schema as the
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
report records. Every request is small (a few hundred tokens). An accepted one is billed like any
other; one Bedrock refuses as invalid is refused before the model runs. The line under the table
counts the accepted requests and the tokens they were billed for.

The prompt wording below is a diagnostic's, not a production prompt: production prompts come only
from the prompt registry (v1-e05-t04).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict

from debate_core.application.errors import DomainError, ModelAccessDenied, ModelRequestRejected
from debate_core.application.settings import load_settings
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
    converse_request,
    tool_name_for,
)
from debate_core.integrations.models.routing_policy import RoutingPolicy

__all__ = [
    "PROBE_MAX_TOKENS",
    "Finding",
    "ProbeAnswer",
    "main",
    "render_table",
    "render_totals",
    "run_first_call",
]

PROBE_MAX_TOKENS: Final = 2048
"""Output cap on every probe: room for a model's thinking and one short tool call, and no more."""

ACCEPTED: Final = "accepted"
REFUSED: Final = "refused"
NOT_TRIED: Final = "not tried"

_PROMPT: Final = ModelPrompt(prompt_id="bedrock.first-call", prompt_version="1.0.0")
_USER_TEXT: Final = "Call the ProbeAnswer tool once, with colour set to blue. Do not write anything else."
_STRUCTURED_TEXT: Final = 'Reply with the JSON object {"colour": "blue"} and nothing else.'

_ACCOUNT_ID: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")
"""An AWS account id. Bedrock's AccessDenied message names the caller's role and the resource by
ARN, both carrying one, and the table is pasted into a committed report, which may hold none."""


class ProbeAnswer(BaseModel):
    """The colour the request names."""

    model_config = ConfigDict(extra="forbid")

    colour: str


@dataclass(frozen=True, slots=True)
class Finding:
    """What Bedrock answered to one probe on one target."""

    routes: tuple[str, ...]
    """Every route the target serves, as `<routing file> <task class>`."""
    target: str
    probe: str
    outcome: str
    detail: str
    input_tokens: int | None = None
    """What an accepted request was billed for, as Bedrock reported it; `None` when it reported none."""
    output_tokens: int | None = None


@dataclass(slots=True)
class _Target:
    """One inference profile or model in one region, the first route that names it, and every route."""

    policy: RoutingPolicy
    task_class: TaskClass
    route: ResolvedRoute
    routes: list[str]


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
    policies: Mapping[str, RoutingPolicy],
    *,
    aws_profile: str | None = None,
    client_factory: ClientFactory | None = None,
) -> list[Finding]:
    """Probe each target the routing files in `policies` name, once, and return what Bedrock answered.

    `policies` maps each routing file's name, as a row names it, to its policy. Every client is
    signed with `aws_profile`, or built by `client_factory` when a test gives one.
    """
    params = ModelParams(max_tokens=PROBE_MAX_TOKENS)
    targets: dict[tuple[bool, str, str | None], _Target] = {}
    for label, policy in policies.items():
        for task_class in sorted(policy.routed_task_classes, key=list(TaskClass).index):
            route = policy.resolve(task_class, params if task_class.is_generative else None)
            key = (task_class.is_generative, route.invocation_target, route.region)
            found = targets.setdefault(key, _Target(policy, task_class, route, []))
            found.routes.append(f"{label} {task_class.value}")
    findings: list[Finding] = []
    for target in targets.values():
        router = BedrockModelRouter(
            target.policy, aws_profile=aws_profile, render_prompt=_render, client_factory=client_factory
        )
        if target.task_class.is_generative:
            findings.extend(await _probe_generative(router, target))
        else:
            findings.append(await _probe_scoring(router, target))
    return findings


async def _probe_generative(router: BedrockModelRouter, found: _Target) -> list[Finding]:
    routes, route = tuple(found.routes), found.route
    target = route.invocation_target
    adapters_call = "toolChoice auto (the adapter's call)"
    params = ModelParams(max_tokens=PROBE_MAX_TOKENS)
    try:
        response = await router.generate_structured(found.task_class, _PROMPT, ProbeAnswer, params)
    except DomainError as error:
        first = Finding(routes, target, adapters_call, _outcome(error), str(error))
        if isinstance(error, ModelAccessDenied):
            rest = [
                Finding(routes, target, probe, NOT_TRIED, "access denied") for probe, _ in _variants(route)
            ]
            return [first, *rest]
    else:
        usage = response.usage
        detail = f"answered {response.output.model_dump()}; request id {response.provider_request_id}"
        first = Finding(
            routes, target, adapters_call, ACCEPTED, detail, usage.input_tokens, usage.output_tokens
        )
    findings = [first]
    client = router.client_for(route)
    for probe, request in _variants(route):
        try:
            answer = await asyncio.to_thread(client.converse, **request)
        except (ClientError, BotoCoreError) as error:
            translated = translate_bedrock_error(error, target)
            findings.append(Finding(routes, target, probe, _outcome(translated), str(translated)))
        else:
            stop = answer.get("stopReason")
            request_id = answer.get("ResponseMetadata", {}).get("RequestId")
            usage = answer.get("usage", {})
            findings.append(
                Finding(
                    routes,
                    target,
                    probe,
                    ACCEPTED,
                    f"stopReason {stop}; request id {request_id}",
                    usage.get("inputTokens"),
                    usage.get("outputTokens"),
                )
            )
    return findings


async def _probe_scoring(router: BedrockModelRouter, found: _Target) -> Finding:
    routes, target = tuple(found.routes), found.route.invocation_target
    embeds = found.task_class is TaskClass.EMBEDDINGS
    probe = "embed one text" if embeds else "rerank two documents"
    try:
        if embeds:
            embedded = await router.embed(["A short text to embed."])
            detail = f"{embedded.dimensions} dimensions; request id {embedded.provider_request_id}"
            input_tokens = embedded.usage.input_tokens
        else:
            reranked = await router.rerank("blue", ["The sky is blue.", "Grass is green."])
            order = [result.index for result in reranked.results]
            detail = f"order {order}; request id {reranked.provider_request_id}"
            input_tokens = None  # Cohere bills a search unit, not tokens
    except DomainError as error:
        return Finding(routes, target, probe, _outcome(error), str(error))
    return Finding(routes, target, probe, ACCEPTED, detail, input_tokens)


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
    """The findings as the Markdown table the session report records, with any account id masked."""
    rows = ["| Routes | Called as | Probe | Outcome | Detail |", "|---|---|---|---|---|"]
    for finding in findings:
        cells = (
            ", ".join(finding.routes),
            f"`{finding.target}`",
            finding.probe,
            finding.outcome,
            finding.detail,
        )
        masked = (_ACCOUNT_ID.sub("<account-id>", cell).replace("|", "\\|") for cell in cells)
        rows.append("| " + " | ".join(masked) + " |")
    return "\n".join(rows)


def render_totals(findings: Sequence[Finding]) -> str:
    """One line on what the run cost: the requests accepted, the tokens billed, and the refusals."""
    accepted = [finding for finding in findings if finding.outcome == ACCEPTED]
    input_tokens = sum(finding.input_tokens or 0 for finding in accepted)
    output_tokens = sum(finding.output_tokens or 0 for finding in accepted)
    refused = sum(1 for finding in findings if finding.outcome == REFUSED)
    return (
        f"{len(accepted)} requests accepted and billed, {input_tokens} input and {output_tokens} output "
        f"tokens; {refused} refused."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Probe the routing files' targets and print the table. Exits 1 if any probe could not run."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument(
        "--routing-file",
        type=Path,
        action="append",
        help="config/model_routing.<env>.yaml; give it once for each file. Default: models.routing_file",
    )
    arguments = parser.parse_args(argv)
    settings = load_settings()
    files: list[Path] = arguments.routing_file or [settings.models.routing_file]
    policies = {path.name: RoutingPolicy.load(path) for path in files}
    profile = settings.models.aws_profile
    environment = settings.environment.value
    print(
        f"Signed with AWS profile {profile} (models.aws_profile, DEBATE_ENV={environment})."
        if profile
        else f"Signed with no named AWS profile (models.aws_profile is not set, DEBATE_ENV={environment})."
    )
    print()
    findings = asyncio.run(run_first_call(policies, aws_profile=profile))
    print(render_table(findings))
    print()
    print(render_totals(findings))
    return 1 if any(finding.outcome.startswith(("failed", NOT_TRIED)) for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())

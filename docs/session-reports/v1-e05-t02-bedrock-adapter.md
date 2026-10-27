# Session report: v1-e05-t02-bedrock-adapter

| | |
|---|---|
| Task | `v1-e05-t02-bedrock-adapter` — Amazon Bedrock adapter |
| Spec | [`plan_specs/v1/e05-model-router/t02-bedrock-adapter.yaml`](../../plan_specs/v1/e05-model-router/t02-bedrock-adapter.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t02-bedrock-adapter` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`BedrockModelRouter` is the production `ModelRouter`. It lives in `debate_core.integrations.bedrock`, and every identifier, profile and region it uses comes from the routing file.

- **Structured output.** A structured call goes to Converse with the schema as the only tool and `toolChoice` `auto`, never forced. The adapter validates the tool's input against the schema. If the model skips the tool, calls it twice, stops on `max_tokens`, or sends input the schema rejects, the call raises `InvalidModelOutput`, which t05's guard will repair.
- **Embeddings and rerank.** Embeddings go to Titan, one text per InvokeModel call. Rerank goes to Cohere, all documents in one call.
- **Retries.** Throttling, ServiceUnavailable, ModelNotReady and InternalServer errors are retried up to the route's `max_attempts`, with full-jitter backoff. Every other failure raises a typed port error immediately.
- **Effort.** `effort` is a route default and a per-call parameter (ac6).
- **The aws extra.** `bedrock_model_router` is the `real_router` factory for `build_model_router`. If boto3 is missing it raises a configuration error naming `debate-core[aws]`.

Six of the seven Goal criteria and every node criterion pass, and all 34 mutants are caught.

**The Goal stays `InProgress`, because ac7 is NOT RUN.** ac7 is the first real call on each route. It needs AWS credentials allowed to call `bedrock:InvokeModel`, and no permission set the operator holds has that. The probe for it is built and tested, and its command is under Operator follow-ups.

**What to look at first:**

1. **Deviation 4: the router cannot send a structured call until t04 exists.** A ModelPrompt carries no text, and rendering one is the prompt registry's job. Until t04 wires its renderer in, `generate_structured` refuses before sending anything. Embeddings and rerank work today.
2. **Deviation 2: files outside `constraints.packages`.** ac6 needs `effort` on the domain's `ModelParams` and `ResolvedRoute`. ac3's typed errors belong in `application/errors.py`.
3. **Deviation 6: one more code is retried than ac3 names.** `InternalServerException` (500) is retried as a transient service error.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `optional-extra`: aws optional extra and lazy import (renamed per the PM's amendment) | Done | Uses the existing `aws` extra. `debate_core.integrations.bedrock` imports no AWS SDK at import time. `bedrock_model_router` calls `require_aws_sdk()` and raises `BedrockNotInstalledError`, a `ConfigurationError` with field `models.provider` that names `debate-core[aws]`. |
| `converse-client`: Converse client with credential chain and route config | Done | `build_bedrock_runtime_client(region, timeout)` creates a fresh `boto3.session.Session(region_name=...)` and passes nothing else, so credentials come only from the chain. It sets a 10 s connect timeout (or less), the read timeout from the route, and `total_max_attempts: 1` so that botocore does no retrying of its own. The router keeps one client per region and timeout. |
| `structured-tool-use`: structured output via tool use | Done | One tool, named after the schema class, with `toolChoice` `{"auto": {}}`. `inferenceConfig` and `outputConfig.effort` are sent only when the route sets them. The response is validated against the schema. `stopReason` must be `tool_use` or `end_turn`. Usage comes from `usage`, the request id from `ResponseMetadata`. |
| `embed-rerank`: Titan embeddings and Cohere rerank | Done | Titan V2 gets one request per text, with `dimensions` from the route when it sets one. Cohere gets `api_version` 2 and `top_n` equal to the number of documents. Results are re-sorted best first and checked to name each document exactly once. |
| `retries-and-contract`: throttling retries and contract suite | Done | Retry classification is in `failures.py`. The shared contract runs as `TestBedrockModelRouterContract`, with the Stubber playing Bedrock's answers: 18 tests. |

## Acceptance criteria

**Fail-first evidence.** I wrote the tests alongside the code, not before it. Every behaviour below is therefore shown failing by a mutant, listed in the Mutation run table after this one. The PM asked for mutants on toolChoice, retry classification and effort merging; those are mutants 1–2, 3–7 and 14–18. No test here uses Hypothesis, so agreement 8's fresh-database rule had nothing to apply to.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: BedrockModelRouter passes the shared ModelRouter contract suite with Stubber responses for Converse, Titan and Cohere | PASS | `uv run pytest packages/debate_core/tests/integrations/bedrock -k Contract` → `18 passed in 2.52s`. The binding sets `expected_route = policy.resolve`, so the contract checks routes field by field. |
| ac2 (amended 2026-10-16): the schema is sent as the single toolConfig tool with toolChoice auto, never forced; the toolUse input is parsed into the schema; no toolUse raises a typed error | PASS (typed error is `InvalidModelOutput`; see Deviation 1) | `test_structured_output_sends_the_schema_as_the_single_tool_with_tool_choice_auto` checks a request written out in full by hand. `test_structured_output_never_forces_the_tool` runs for all three Claude classes. `test_structured_output_with_no_tool_call_is_invalid_output_naming_the_prompt` covers the missing tool call. Mutants 1 and 2 are caught. |
| ac3: Throttling, ServiceUnavailable and ModelNotReady are retried up to the configured attempts with jittered backoff; AccessDenied and Validation fail at once with typed errors | PASS | `test_retry_a_throttled_call_until_it_succeeds_counting_each_attempt`: two throttles then an answer gives 3 requests (the Stubber's queue of 3 is empty), 2 waits and the answer. `test_retry_stops_at_the_routes_attempts_and_reports_the_rate_limit`: `max_attempts: 4` gives 4 requests, 3 waits, and `ProviderRateLimited` "after 4 attempts". `test_retry_never_resends_a_refusal_a_validation_error_or_a_model_that_ran` covers 8 codes, each with one planned answer and no wait. The bound comes from the route (`max_attempts`). Mutants 3–13 are caught. |
| ac4 (amended 2026-10-17): without the aws extra no boto3 is installed; selecting provider bedrock without it raises a clear configuration error naming debate-core[aws] | PASS | `uv run pytest packages/debate_core/tests/integrations/bedrock/test_aws_extra.py` → 7 passed. Those tests cover the lockfile's base closure of debate-core, record and live without the SDK, replay without the SDK, and a fresh interpreter. Cross-check: `uv export --package debate-core --frozen --no-dev --no-hashes` lists 14 packages and no boto3. With `--extra aws` it adds `boto3==1.43.98`, `botocore==1.43.98`, `jmespath`, `s3transfer`. Planting boto3 in the lock's base dependencies fails `test_debate_core_without_the_aws_extra_installs_no_aws_sdk`. Planting `import boto3` in the package fails `test_the_adapter_package_imports_with_no_aws_sdk_installed`. |
| ac5: the resolved model_id, inference profile and region and the request id are returned on every response | PASS | `test_structured_output_reports_model_profile_region_and_request_id`. The embed and rerank tests assert `provider_request_id` and `route.model_id`. Mutants 23 and 24 are caught. |
| ac6: `effort` is a route default and a per-call parameter, merged like the other overrides, validated at load, and reported on the resolved route | PASS | `uv run pytest packages/debate_core/tests/integrations/models/test_routing_policy.py` → 74 passed, including the 6 effort tests and `test_an_unknown_effort_is_refused_at_load_naming_the_key[extreme, HIGH, 1]` (field `routes.high_volume.effort`). Two adapter tests show it is sent as `outputConfig.effort`: `test_structured_output_sends_the_routes_effort_as_output_config` and `test_structured_output_sends_a_per_call_effort_over_the_routes`. Mutants 14–18 are caught. |
| ac7: operator-run first real call on each Claude route | NOT RUN | No session can close this. It needs credentials allowed `bedrock:InvokeModel`, which no permission set the operator holds grants (PM notes, 2026-10-17). The probe is `python -m debate_core.integrations.bedrock.first_call`, with Stubber tests: `test_first_call_*`, 4 tests. The command, and the IAM it needs, are under Operator follow-ups. The Stubber tests that pin each real answer are written after the run (Follow-up work). |
| Node `optional-extra`: `artifact_exists` `packages/debate_core/pyproject.toml` contains `bedrock` | PASS | `grep -c bedrock packages/debate_core/pyproject.toml` → `2`. The match is the aws extra's comment, which now names the Bedrock adapter. |
| Node `converse-client`: `uv run pytest …/bedrock/test_router.py -k client` | PASS | → `8 passed in 2.67s` |
| Node `structured-tool-use`: `uv run pytest …/bedrock/test_router.py -k structured` | PASS | → `24 passed in 3.55s` |
| Node `embed-rerank`: `uv run pytest …/bedrock/test_router.py -k "embed or rerank"` | PASS | → `21 passed in 2.86s` |
| Node `retries-and-contract`: `uv run pytest packages/debate_core/tests/integrations/bedrock` | PASS | → `90 passed in 4.64s` |
| Node `retries-and-contract`: `uv run lint-imports` | PASS | → `Contracts: 12 kept, 0 broken.` |

### Mutation run

Each mutant was applied to the committed tree, then I ran `uv run --frozen pytest -q -x -n 0 packages/debate_core/tests/integrations/bedrock packages/debate_core/tests/integrations/models/test_routing_policy.py` and restored the file. The restore was checked byte for byte, and `git status` was clean after each batch. The runs took 35 s to 1 min 41 s per batch of 6–12, at load averages of 17–21. Every mutant ended in a failing test. None ended in a collection error.

| # | Mutant | Caught by |
|---|---|---|
| 1 | toolChoice forced to `any` | `test_structured_output_sends_the_schema_as_the_single_tool_with_tool_choice_auto` |
| 2 | toolChoice forced to the named tool | the same |
| 3 | retry classification: `ValidationException` retried | `test_retry_never_resends_…[ValidationException-400-ModelRequestRejected]` |
| 4 | retry classification: `AccessDeniedException` retried | `test_retry_never_resends_…[AccessDeniedException-403-ModelAccessDenied]` |
| 5 | retry classification: `ModelTimeoutException` retried | `test_retry_never_resends_…[ModelTimeoutException-408-ModelUnavailableError]` |
| 6 | retry classification: throttling not retried | `test_retry_a_throttled_call_until_it_succeeds_counting_each_attempt` |
| 7 | retry classification: `ModelNotReadyException` not retried | `test_retry_an_unavailable_model_then_report_it_unavailable[ModelNotReadyException-429]` |
| 8 | retry bound off by one (`<=`) | `test_retry_stops_at_the_routes_attempts_and_reports_the_rate_limit` |
| 9 | retry bound ignores the route (constant 3) | the same |
| 10 | waits not jittered | `test_retry_waits_are_jittered_below_their_ceiling` |
| 11 | waits not doubled | `test_retry_waits_grow_by_doubling_up_to_the_cap` |
| 12 | waits not capped | the same |
| 13 | botocore's own retries left on | `test_the_client_config_bounds_connect_and_read_by_the_route_and_turns_botocore_retries_off` |
| 14 | effort merging: per-call override ignored | `test_structured_output_sends_a_per_call_effort_over_the_routes` |
| 15 | effort merging: route default ignored | `test_structured_output_sends_the_routes_effort_as_output_config` |
| 16 | effort merging: dropped from the resolved route | the same |
| 17 | effort not sent to Converse | the same |
| 18 | effort allowed on a scoring route | `test_a_scoring_class_takes_no_sampling_parameters[embeddings-effort: low]` |
| 19 | `dimensions` allowed on any route | `test_dimensions_on_a_route_that_returns_no_vectors_are_refused[high_volume]` |
| 20 | `max_tokens` stop accepted | `test_structured_output_cut_off_or_withheld_is_invalid_even_with_a_tool_call[max_tokens]` |
| 21 | any tool's call accepted | `test_structured_output_from_another_tool_is_not_an_answer` |
| 22 | a second call of the tool ignored | `test_structured_output_called_twice_is_refused_rather_than_picked_from` |
| 23 | temperature never sent | `test_structured_output_sends_a_temperature_only_when_one_is_set` |
| 24 | request id dropped | `test_structured_output_reports_model_profile_region_and_request_id` |
| 25 | model id sent instead of the inference profile | `test_structured_output_sends_the_schema_as_the_single_tool_with_tool_choice_auto` |
| 26 | client cached by region only | `test_a_client_is_built_once_per_region_and_timeout` |
| 27 | access denied reported as a rejected request | `test_retry_never_resends_…[AccessDeniedException-403-ModelAccessDenied]` |
| 28 | expired credential reported as a rejected request | `test_retry_never_resends_…[UnrecognizedClientException-403-ModelAccessDenied]` |
| 29 | model timeout reported as a rejected request | `test_retry_never_resends_…[ModelTimeoutException-408-ModelUnavailableError]` |
| 30 | embedding dimensions not sent | `test_embed_asks_for_the_dimensions_the_route_names` |
| 31 | rerank results not sorted | `test_rerank_orders_results_best_first_whatever_order_they_arrive_in` |
| 32 | rerank coverage unchecked | `test_rerank_refuses_results_that_do_not_name_each_document_once[results0]` |
| 33 | no AWS SDK check | `test_selecting_bedrock_without_the_extra_is_a_configuration_error_naming_it[record]` |
| 34 | default renderer sends anyway | `test_structured_output_without_a_prompt_renderer_sends_nothing` |

**Import contracts touched by this task, each broken on purpose.** Each was restored with `git checkout`, and `lint-imports` then reported `12 kept, 0 broken`.

- `import httpx` planted in `bedrock/router.py` → `… stay inside debate_core.integrations.opencaselist BROKEN`: "debate_core.integrations.bedrock is not allowed to import httpx".
- `import lxml` planted in `bedrock/router.py` → `Document libraries stay inside debate_core.integrations.docx_parser BROKEN`.
- `import debate_core.integrations.bedrock.router` planted in `integrations/models/factory.py` → `The AWS SDK never reaches … BROKEN`: "debate_core.integrations.models is not allowed to import boto3". This is why `build_model_router` cannot default to the Bedrock router and a composition root passes it in.

### Whole suite and checks

At load average 21, part 1 of 4 went past 115 s and was stopped by its `perl -e 'alarm 115'` guard. I therefore ran the default selection in eight parts, one after another, each under the same guard:

| Command | Result (load average at start) |
|---|---|
| `uv run pytest -q --part 1/8` | 984 passed in 52.86 s (49.6) |
| `--part 2/8` | 987 passed in 34.12 s (50.3) |
| `--part 3/8` | 986 passed, 2 warnings in 36.07 s (34.5). The warnings are the two smoke tests that assert the socket guard refuses `getaddrinfo`. |
| `--part 4/8` | 980 passed, 1 warning in 47.06 s (24.8) |
| `--part 5/8` | 973 passed in 38.36 s (20.6) |
| `--part 6/8` | 978 passed, 1 xfailed in 50.74 s (19.2) |
| `--part 7/8` | 981 passed, 1 skipped in 45.03 s (35.1) |
| `--part 8/8` | 981 passed, 1 xfailed in 44.51 s (27.5) |
| Total | 7,850 passed, 1 skipped, 2 xfailed, 0 failed |
| `uv run ruff format --check .` | `768 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright` (workspace, after the last format) | `0 errors, 0 warnings, 0 informations` (13 s) |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run pytest tests/architecture/test_import_contracts.py` | 33 passed |

## Files changed

- **`debate_core.integrations.bedrock`** (new):
  - `router.py`: `BedrockModelRouter`, the client builder and the Converse request.
  - `failures.py`: retry classification and translation to port errors.
  - `prompt_rendering.py`: the `PromptRenderer` seam, with a default that refuses.
  - `errors.py`: `BedrockNotInstalledError`.
  - `__init__.py`: `bedrock_model_router`, `require_aws_sdk`.
  - `first_call.py`: the operator's ac7 probe.
- **`debate_core.integrations.models`**: `routing_policy.py` gains `effort`, `max_attempts` and `dimensions` on a route, validated at load, with effort merged in `resolve`. `factory.py`'s docstring and its error for a missing real router now name `bedrock_model_router`.
- **`debate_core.domain.model_contracts`**: `Effort`, plus `effort` on `ModelParams` and `ResolvedRoute` (ac6; Deviation 2).
- **`debate_core.application`**: `errors.py` adds `ModelAccessDenied` and `ModelRequestRejected`, exported from `application/__init__.py`. `ports/model_router.py`'s error table lists them (ac3; Deviation 2).
- **Tests**:
  - `tests/integrations/bedrock/test_router.py`: the Stubber kit, client, structured, embed, rerank, retry, contract and first-call tests.
  - `tests/integrations/bedrock/test_aws_extra.py`: ac4.
  - `test_routing_policy.py`: effort, attempts and dimensions.
  - `test_factory.py`: the renamed message test.
  - `test_errors.py`: the two new errors.
- **`tests/fixtures/model_cassettes/example.select-passage/…json`**: `"effort": null` added by hand to the recorded params (Deviation 5).
- **`packages/debate_core/pyproject.toml`**: the aws extra's comment names the Bedrock adapter. No dependency changed.
- **`pyproject.toml`** (root): `debate_core.integrations.bedrock` is added to the source lists of the httpx/keyring and lxml contracts, and the AWS contract's comment explains why it is not on that contract's list.
- **The spec**: the PM's two amendments of 2026-10-17, applied as instructed (Deviation 3).

## Deviations from the spec

1. **ac2 names "a typed ModelOutputError", which does not exist yet.** t05 introduces `ModelOutputError`, which it raises after its repair attempt. Today the port's typed error for an answer that is not the schema is `InvalidModelOutput`. The shared contract requires that error, and t05's guard will catch it. A response with no toolUse block raises `InvalidModelOutput`. Suggested amendment: "raises the port's `InvalidModelOutput`".
2. **Files outside `constraints.packages: [debate_core.integrations]`:**
   - `debate_core.domain.model_contracts`: ac6 puts `effort` on the per-call parameters and the resolved route, and both are domain types.
   - `debate_core.application.errors`, its `__init__` and the port's error table: ac3's typed errors cross the port, and that module is where every port error lives. An adapter-local error class would force a use case to import the adapter to catch it.
   - The root `pyproject.toml` import contracts, one committed cassette, and a comment in `packages/debate_core/pyproject.toml`.

   Suggested amendment: add `debate_core.domain` and `debate_core.application` to `packages`.
3. **The PM's amendments of 2026-10-17, applied to the spec as instructed and marked in it:**
   - ac4 and the `optional-extra` node now name `debate-core[aws]`, and the description says no second extra is added.
   - The forbidden entry now forbids a new boto3 or botocore import outside `debate_core.integrations.bedrock`, and any in the domain or application layers.
4. **A structured call needs prompt text, and nothing provides it until t04.** A `ModelPrompt` holds an id, a version and variables, and t04's registry renders it. The spec says nothing about where the adapter's text comes from. The router takes a `render_prompt` callable. The default, `refuse_unregistered_prompt`, raises a `ConfigurationError` naming v1-e05-t04 before anything is sent or billed. So until t04 passes its renderer (`functools.partial(bedrock_model_router, render_prompt=...)`), record and live serve embeddings and rerank but not structured calls. I wrote no prompt text into the adapter: t04 forbids it for production calls. The ac7 probe has its own one-line diagnostic text.
5. **The committed example cassette was edited by hand.** The replay router compares a cassette's recorded request with the call exactly, field for field. Adding `effort` to `ModelParams` therefore changed every call's request, and the one committed cassette stopped matching. I added `"effort": null` to its params by hand (agreement 6). Any future `ModelParams` field will do the same to every recorded cassette (Follow-up work).
6. **`InternalServerException` is retried, beyond the three codes ac3 names.** The spec's description says "throttling and transient service errors are retried", and a 500 is the transient service error botocore's own standard mode retries. It is listed in `failures.RETRIED_CODES` and pinned by `test_retry_codes_are_exactly_the_throttle_and_the_passing_outages`. If the PM wants exactly three, it is a one-word change.
7. **The default suite ran in eight parts, not four,** because a fourth of it went past the two-minute line at load average 21. The parts together are still the whole selection.

## Decisions and assumptions

- **Where the retry bound and the embedding size live.** The spec says "the configured attempts" and "configurable dimensions" without naming a place. Both are route fields in the routing file:
  - `max_attempts`: default 3, range 1–8, the first attempt included.
  - `dimensions`: embeddings routes only.

  The backoff's base (1 s) and cap (20 s) are constructor arguments with defaults. No routing file was edited, so every route has the default 3 attempts and Titan's default dimensions.
- **Effort is sent as Converse's native `outputConfig.effort`.** The installed botocore (1.43.98) has that field in its Converse input shape, and the Stubber validates every request against that shape. I did not use `additionalModelRequestFields`. No routing file sets an effort, so each model's own default applies. Anthropic's documentation gives `high` for Sonnet 5.5 and `medium` for Haiku 5.5 and Opus 5.5. Whether a route should name a level is the PM's call (Follow-up work).
- **Not retried:**
  - `ModelTimeoutException` and a read timeout: the model ran, so a second attempt would run, and bill, again.
  - A connection that never opened: it is `ModelUnavailableError` at once. Retrying it would be safe, but ac3 does not ask for it.
- **One answer only.** Two calls of the schema's tool are refused rather than picked from. A stop reason other than `tool_use` or `end_turn` is refused even when a tool call is present.
- **Embeddings report one request id: the first request's.** Titan takes one text per request. Input tokens are summed, and are `None` if any response reports none. Output tokens are `None`.
- **Latency** is the wall-clock time of the attempt that succeeded, summed over an embedding call's requests. Converse's own `metrics.latencyMs` is not used.
- **The tool's `strict` flag is not sent.** Anthropic recommends it with `auto`, but Bedrock's model cards do not say whether these models accept it. The ac7 probe asks.
- **An AWS_PROFILE that names a missing profile** is `ModelAccessDenied` with a hint, so that no botocore exception leaves the adapter.

## Operator follow-ups

### The first real call on each route (ac7)

This cannot run until a profile holds the grant below. When one exists, run it in the task worktree. It makes 23 small requests for the prod file and 23 for dev, each a few hundred tokens with a 2,048-token output cap, and should take 1–3 minutes.

Replace `debate-bedrock-probe` with the name the permission-set task gives the profile; it is a placeholder. These are the one-time commands:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e05-t02-bedrock-adapter
aws sso login --profile debate-bedrock-probe
```

Then the probe, once per routing file. The prod file covers every identifier in use, and the dev file confirms dev's routes:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e05-t02-bedrock-adapter
AWS_PROFILE=debate-bedrock-probe uv run python -m debate_core.integrations.bedrock.first_call --routing-file config/model_routing.prod.yaml
AWS_PROFILE=debate-bedrock-probe uv run python -m debate_core.integrations.bedrock.first_call --routing-file config/model_routing.dev.yaml
```

**What success looks like.** Each command prints a Markdown table. For each Claude route there are seven rows: the adapter's own call, `toolChoice any`, `toolChoice tool`, `temperature 0.5`, `effort low`, `structured output` and `strict tool`. Then there is one row for embeddings and one for rerank. Each row says `accepted` or `refused`, with Bedrock's code and message.

- **Exit status 0** means every probe got an answer. Refusals are findings, not failures.
- **Exit status 1** means a probe could not run: access denied, or the model failed to answer. Paste both tables back into the session.

From the tables I record which `toolChoice` types and structured-output options each model accepts, whether a non-default temperature is refused, and that each id and profile resolves. I then add a Stubber test pinning each answer.

### IAM a profile needs for that call (for the PM's permission-set task)

No Terraform was written: it is outside this task's packages.

- **Action: `bedrock:InvokeModel` only.** Converse is authorised by `bedrock:InvokeModel`; there is no separate `bedrock:Converse` action. `bedrock:InvokeModelWithResponseStream` is not needed, because the adapter does not stream.
- **Resources.** The identifiers are from `config/model_routing.*.yaml`, and `<account-id>` is the Bedrock account's.
  - The three geographic inference profiles: `arn:aws:bedrock:us-east-1:<account-id>:inference-profile/us.anthropic.claude-sonnet-5-5`, `…/us.anthropic.claude-haiku-5-5` and `…/us.anthropic.claude-opus-5-5`.
  - The foundation models behind those profiles, in every region a `us.` profile may route to: `arn:aws:bedrock:{us-east-1,us-east-2,us-west-2}::foundation-model/anthropic.claude-{sonnet,haiku,opus}-5-5`. That is nine ARNs. They can be limited to calls made through the profiles with the condition `bedrock:InferenceProfileArn`.
  - `arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0`
  - `arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0`
- **Model access.** Anthropic models need their use-case form submitted once per account. Whoever makes the first call to a Marketplace-backed model may also need `aws-marketplace:Subscribe` and `aws-marketplace:ViewSubscriptions`. I have not verified this against the account, and the first call's refusal message will say so if it applies.

## Follow-up work

- **v1-e05-t04-prompt-registry:** give the Bedrock router its renderer: `bedrock_model_router(policy, render_prompt=registry.render)`, through `functools.partial` for `build_model_router`. Until then, structured calls in record and live mode refuse (Deviation 4).
- **v1-e05-t02 continuation, after the operator's run:** record the ac7 tables, add a Stubber test pinning each answer, and set the Goal to `Succeeded`. If `strict` is accepted, consider sending it. If a temperature is accepted, a route may set one again.
- **The PM's call:** whether any route should set `effort`, given that the model defaults differ (Decisions).
- **The first CLI command that calls a model (E06 or later):**
  - Pass `real_router=bedrock_model_router` to `build_model_router`.
  - Rename the import contract "The CLI reaches the AWS SDK only through debate_core.integrations.s3" to cover `integrations.bedrock`.
  - Check the exit codes: `exit_code_for` sends every `ProviderError`, including the non-retryable `ModelAccessDenied` and `ModelRequestRejected`, to `RETRIEVAL_FAILURE` (3).
- **v1-e05-t03 / the cassette format:** replay compares recorded requests field for field, so a new `ModelParams` field breaks every recorded cassette (Deviation 5). Comparing the parsed `ModelRequest`, where a missing field takes its default, would make adding an optional parameter backward compatible.
- **v1-e05-t07-usage-telemetry:** embeddings report summed input tokens and rerank reports none, because Cohere bills per search unit. Converse's `metrics.latencyMs` is available if telemetry wants the model's latency rather than wall-clock time.
- **The permission set** for `bedrock:InvokeModel` (the PM files it as its own task, per the 2026-10-17 notes).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-17

**Notes:**

Accepted as a partial merge. ac7, the first real call, cannot run until a profile may call
`bedrock:InvokeModel`, and the Goal stays `InProgress` until it is recorded.

**The adapter fails closed everywhere it could guess.** It never forces a tool, never picks one of
two tool calls, and never accepts a `max_tokens` stop. It never retries a call the model may have
run and billed. Until the registry exists it sends no structured call at all, rather than inventing
prompt text. Each is pinned by a mutant.

**The work itself:**

* **34 of 34 mutants caught,** including the three families I asked for: `toolChoice`, the retry
  classification and `effort` merging.
* **ac4 is shown from the lockfile,** not asserted. The base closure of `debate-core` holds no
  boto3, and planting it fails the test.
* **The import contracts were broken on purpose and held,** and the report explains why
  `build_model_router` cannot default to the Bedrock router.
* **Retries are bounded by the route,** jittered, doubled and capped, with botocore's own retries
  off, so attempts cannot multiply.
* **The IAM a profile needs is written out**: one action, and the resources by profile and
  foundation model, with the inference-profile condition.

**On fail-first.** The tests were written beside the code, so the mutants are the evidence that
each test reads its behaviour. I accept that here because every behaviour has its mutant. The
working agreement still asks for red first, and the next task should show it.

**Rulings:**

* **Deviation 1, `InvalidModelOutput` in place of a `ModelOutputError` that t05 has not built:**
  accepted. It is the port's error, the contract requires it, and t05's guard catches it.
* **Deviation 2, the domain and application edits:** accepted under working agreement 5. `effort`
  is a domain parameter, and port errors live with the port.
* **Deviation 3, the PM's two amendments:** applied as instructed.
* **Deviation 4, no structured call until t04:** accepted, and it is the right seam. t04 provides
  the renderer, and the PM's notes for t04 say how they meet.
* **Deviation 5, the hand-edited cassette:** accepted. Replay that breaks on every new optional
  parameter is a defect in t03's format: filed as a follow-up for the E05 batch.
* **Deviation 6, `InternalServerException` retried:** accepted. It is a transient service error,
  and the spec's description asks for those.
* **Deviation 7, eight parts:** accepted.
* **Decisions:** accepted. On `effort`, no route sets one until a task with evals has a reason to.
  The model defaults stand.

**Follow-up work, filed by the PM:**

* **A permission set that may call `bedrock:InvokeModel`,** as written under Operator follow-ups,
  and the account's model access. That is a new E05 task with Terraform the PM reads before
  apply. ac7 runs after it.
* **Cassette comparison that tolerates a new optional field:** E05.
* **The exit code for `ModelAccessDenied` and `ModelRequestRejected`** goes into the spec of the
  first CLI command that calls a model. They must not exit 3, the retryable code.
* **t04 wires its renderer,** and **t07 takes the token and latency notes.**

## PM record, 2026-10-22

Added by the PM. Nothing above is changed, and this section is not a review.

* **ac7 moves to `v1-e05-t08`.** ac7 needs the permission set that `v1-e05-t08` creates, and
  `v1-e05-t08` depends on this task, so neither could finish. The first real call on each Claude
  route is now `v1-e05-t08`'s ac5, recorded in that task's report and pinned by this task's
  Stubber tests.
* Every other criterion was met and accepted in the review above, so the Goal is set to
  `Succeeded` in the PM batch of 2026-10-22 (d).

## PM record, 2026-10-27

Added by the PM. Nothing above is changed, and this section is not a review.

The first real call on each of dev's Claude routes, as `v1-e05-t08`'s ac4 asks to be recorded here:

* **Step 7, the first call** (the runbook's `first_call` probe over both routing files):
  * **Haiku 4.5** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) and **Sonnet 4.6**
    (`us.anthropic.claude-sonnet-4-6`): the adapter's own call, `toolChoice any`, `toolChoice tool`,
    `temperature 0.5`, structured output and the strict tool were all accepted. `effort low` was
    refused on both: `ValidationException`, "This model doesn't support the effort field".
  * **Titan** embeddings answered with 1,024 dimensions, and **Cohere Rerank 3.5** answered.
  * **Haiku, Sonnet and Opus 5.5** were refused as "not available for this account"
    (`AccessDeniedException`, the zero quota), so their other probes read `not tried`.
  * `first call exit=1`, as the runbook says to expect while the 5.5 quotas are held at zero. The
    summary line: 14 requests accepted and billed, 6,861 input and 484 output tokens; 5 refused.
    Priced at Sonnet 4.6's rates throughout, that is under 3 cents.

The adapter's defaults hold on both dev models. A forced tool choice, a non-default temperature,
structured output and the strict tool were accepted. `effort` is refused by both 4.x models, and
dev's routes send none (`v1-e05-t11` pins it).

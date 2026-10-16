# Session report: v1-e05-t01-model-router-port

| | |
|---|---|
| Task | `v1-e05-t01-model-router-port` — ModelRouter interface and routing config |
| Spec | [`plan_specs/v1/e05-model-router/t01-model-router-port.yaml`](../../plan_specs/v1/e05-model-router/t01-model-router-port.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t01-model-router-port` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The ModelRouter port, its value types and the routing policy are built, and so is the contract suite t02 and t03 must pass. Code and tests name a task class, never a model:

- `ModelRouter.generate_structured(task_class, prompt, schema, params)`, `embed(texts)` and `rerank(query, documents)` return typed responses.
- Every response carries the `ResolvedRoute` it ran on.
- `RoutingPolicy` loads a `config/model_routing.*.yaml` file and refuses a bad one when it loads, naming the key.
- Model identifiers live only in those files. They were checked against the AWS Bedrock model cards on 2026-10-16.

The PM ruled twice on 2026-10-16 on how the spec, written before v1-e01-t09 split the routing file and before v1-e02-t04 settled where contract suites live, maps onto the repository. Both sets of rulings are applied: five spec amendments (quoted in Deviations), the three routing files updated, no Claude route setting a temperature, and the contract suite kept in `debate_core.testing.contracts` beside the five existing contracts. Every criterion passes as amended, and the Goal is `Succeeded`.

The model cards also showed that the current Claude models reject a forced `tool_choice`, which t02's spec assumes. The PM is amending t02; the finding and its sources are under Follow-up work.

What to look at first: the mutation table under "Checks shown failing". Every check this task added or moved fails for its own reason when it is removed, including ac3's three refusals and the import-linter entry.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-types` — TaskClass and request/response models | Done | `domain/model_contracts.py`. `ModelTaskClass` moved here as `TaskClass` and the old name is gone (PM ruling). |
| `router-port` — ModelRouter port signature | Done | `application/ports/model_router.py` replaces the e02 `invoke` stub that was in `ports/providers.py`. `RoutingConfigError` sits beside it, and `ModelUnavailableError` is in `application/errors.py`. |
| `routing-policy` — YAML routing policy and loader | Done | `integrations/models/routing_policy.py`, moved from `application/routing_config.py` with its tests (PM ruling). All three routing files are updated. |
| `contract-tests` — Reusable ModelRouter contract tests | Done | The suite is in `debate_core.testing.contracts.model_router` (path amended by the PM), bound in `tests/contracts/test_model_router_contract.py` to an in-test stand-in and to the shipped `FakeModelRouter`; the PM ruled to keep both. |

## Acceptance criteria

Run at `f6cf900` on 2026-10-16; the second spec amendment changed no code.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `TaskClass` defines the five classes, and the port exposes `generate_structured(task_class, prompt, schema, params)`, `embed(texts)` and `rerank(query, documents)` with typed request/response models | PASS | `uv run pytest packages/debate_core/tests/domain/test_model_contracts.py` → 16 passed (`test_the_five_task_classes_are_the_spec_s_and_two_of_them_only_score`, `test_a_response_has_no_free_text_field`). The signatures are in `application/ports/model_router.py`. `uv run pyright packages/debate_core` → 0 errors, with both bindings typed as `ModelRouter`. |
| ac2 (as amended): the `config/model_routing.*.yaml` files map each class to provider, model_id, inference profile/region and default parameters; `config/model_routing.example.yaml` routes complex_reasoning to Claude Sonnet, high_volume to Claude Haiku, embeddings to Titan Text Embeddings V2 and rerank to Cohere Rerank 3.5 | PASS | `uv run pytest packages/debate_core/tests/integrations/models/test_routing_policy.py` → 56 passed. These include `test_the_default_file_routes_each_class_to_the_family_the_spec_names` and `test_every_committed_routing_file_loads_and_routes_every_task_class` (three files). |
| ac3: unknown task class, missing `model_id` and out-of-range temperature each fail at load with a typed `RoutingConfigError` naming the key | PASS (load-time validation, per the PM's ruling on "at startup") | The same run covers `test_an_unknown_task_class_is_refused_naming_the_key` (`field == "routes.card_selection"`), `test_a_missing_model_id_is_refused_naming_the_key` (`routes.high_volume.model_id`) and `test_an_out_of_range_temperature_is_refused_naming_the_key[-0.5, 1.5, 2.5]` (`routes.high_volume.temperature`). Each is shown failing first below. |
| ac4: per-call overrides merge over task-class defaults, and the resolved route (model_id, profile/region, temperature) is on every response | PASS | The ac4 tests are `test_an_override_replaces_only_the_fields_it_sets` (including an override of `0.0`), `test_every_overridable_field_is_merged` and `test_a_route_with_no_temperature_resolves_to_none`. Contract `test_per_call_overrides_are_reported_on_the_route` and `test_the_resolved_route_is_populated` → `uv run pytest packages/debate_core/tests/contracts/test_model_router_contract.py` → 37 passed. |
| Node `model-types`: `artifact_exists` `domain/model_contracts.py` contains `class TaskClass` | PASS | `grep -c "class TaskClass" packages/debate_core/src/debate_core/domain/model_contracts.py` → `1` |
| Node `router-port`: `uv run pyright packages/debate_core` | PASS | → `0 errors, 0 warnings, 0 informations`. Run again after each move, as the PM asked; workspace-wide `uv run pyright` → 0 errors. |
| Node `routing-policy`: `uv run pytest packages/debate_core/tests/integrations/models/test_routing_policy.py` | PASS | → `56 passed in 3.80s` |
| Node `routing-policy`: `artifact_exists` `config/model_routing.example.yaml` contains `rerank` (path amended by the PM) | PASS | `grep -c rerank config/model_routing.example.yaml` → `3` |
| Node `contract-tests`: `artifact_exists` `packages/debate_core/src/debate_core/testing/contracts/model_router.py` (path amended by the PM) | PASS | `ls packages/debate_core/src/debate_core/testing/contracts/model_router.py` → present. As first written, the path under `tests/` was FAIL (`No such file or directory`); see Deviation 6. |
| Node `contract-tests`: `uv run lint-imports` | PASS | → `Contracts: 12 kept, 0 broken.` Run again after each move. |

### Checks shown failing

For each check this task added or moved, I ran a mutation that removes or weakens it. The runs used `.venv/bin/python -u` under `perl -e 'alarm 105'`, the tree was committed first, each file was restored from a byte copy, and `git status --porcelain` was clean after every batch. A mutant is classified from pytest's summary line, never from the exit code alone.

| # | Mutant | Caught by | Result |
|---|---|---|---|
| 1 | Unknown task class accepted (`dict[str, ModelRoute]`, with the scoring check rewritten so it doesn't crash) | `test_an_unknown_task_class_is_refused_naming_the_key` | CAUGHT: `DID NOT RAISE RoutingConfigError` |
| 2 | Missing `model_id` accepted (default `'m'`) | `test_a_missing_model_id_is_refused_naming_the_key` | CAUGHT: `DID NOT RAISE RoutingConfigError` |
| 3 | Temperature range back to e02's 0–2 (`MAX_TEMPERATURE = 2.0`) | `test_an_out_of_range_temperature_is_refused_naming_the_key[1.5]`, plus 3 domain tests | CAUGHT: `DID NOT RAISE RoutingConfigError` |
| 4 | The offending key is not named (location dropped) | 18 tests asserting `error.field`, including all three ac3 tests | CAUGHT |
| 5 | Provider `fake` routable | `test_the_fake_provider_cannot_be_routed_to` | CAUGHT |
| 6 | Bedrock route without a region | `test_a_bedrock_route_without_a_region_is_refused` | CAUGHT |
| 7 | Inference profile of another model accepted | `test_a_profile_of_a_different_model_is_refused` | CAUGHT |
| 8 | Temperature or max_tokens allowed on a scoring route | 4 parametrized cases | CAUGHT |
| 9 | Override temperature ignored | 2 ac4 tests and contract `test_per_call_overrides_are_reported_on_the_route` | CAUGHT |
| 10 | An override of `0.0` treated as unset (`if overrides.temperature`) | `test_an_override_replaces_only_the_fields_it_sets` | CAUGHT |
| 11 | `ModelRequest` accepts a scoring class | 2 domain tests and 4 contract cases (both bindings) | CAUGHT |
| 12 | Ragged embedding vectors accepted | `test_embeddings_are_one_rectangular_set_of_vectors` | CAUGHT |
| 13 | Rerank results in any order | `test_a_reranking_names_each_document_once_best_first` | CAUGHT |
| 14 | `ModelUnavailableError` reports its own code | `test_an_unreachable_model_is_a_provider_outage_that_names_the_model` | CAUGHT |
| 15 | The fake router drops the override on its route | contract `test_per_call_overrides_are_reported_on_the_route` (`TestFakeModelRouter`) | CAUGHT |
| 16 | The stand-in reports no token usage | contract `test_usage_is_reported` | CAUGHT |
| 17 | The stand-in skips validation (`model_construct`) | contract `test_an_answer_that_does_not_fit_the_schema_is_refused_naming_the_prompt` | CAUGHT |

17 of 17 were caught; each run took 0.5 to 3.0 s.

Mutant 1 needed a second attempt. The first version, `dict[str, ModelRoute]` alone, failed 32 tests, but the ac3 test failed with `AttributeError: 'str' object has no attribute 'is_generative'` from my own scoring-route validator. It did not fail for the reason the test exists. The two-edit version above isolates the guard.

ac3's first two refusals already existed in e02's loader, so their "red" is the guard removed, not a run against the start commit: a test that imports `RoutingPolicy` only errors at collection on the old source, which proves nothing. Mutant 3 is exactly the start commit's 0–2 range, and under it 1.5 loads.

**Import-linter entry.** I planted `import botocore` in `integrations/models/routing_policy.py` and ran `uv run --frozen lint-imports`:
- With `debate_core.integrations.models` on the AWS-SDK contract's list → `Contracts: 11 kept, 1 broken.` and `debate_core.integrations.models.routing_policy -> botocore (l.50)`.
- With the entry removed (the arrangement before this PR) → `Contracts: 12 kept, 0 broken.` The planted import passed.

### Test runs

These are the whole default selection between them (the five `testpaths`). Each ran under `alarm 105`.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q packages/debate_core/tests` | 4963 passed, 2 xfailed in 87.0 s (load ≈ 4.7) |
| `.venv/bin/python -m pytest -q packages/debate_cli/tests` | 638 passed in 25.1 s |
| `.venv/bin/python -m pytest -q packages/debate_api/tests packages/debate_workers/tests tests` | 1710 passed, 1 skipped in 103.1 s, at load average ≈ 9. This is close to the two-minute line; under that load, split it again next time. |

Also: `uv run ruff check .` and `ruff format --check .` → clean. `uv run scripts/validate_specs.py` → OK. `scripts/check_command_blocks.py`, `scripts/check_links.py` and `scripts/check_thin_handlers.py` → OK. `scripts/docs_index.py --check-descriptions` → OK (the index itself was not regenerated).

## Model identifiers: sources and check date

All identifiers were checked on **2026-10-16** against the AWS Bedrock user guide's model cards (docs.aws.amazon.com/bedrock/latest/userguide/), fetched in this session. None is UNVERIFIED. Per the PM's ruling, t02 confirms each one with its first real call.

| Class (default and prod) | Model id | Called as | Source page |
|---|---|---|---|
| complex_reasoning | `anthropic.claude-sonnet-5-5` | profile `us.anthropic.claude-sonnet-5-5`, us-east-1 | `model-card-anthropic-claude-sonnet-5-5.html` (launched 2026-09-28) |
| high_volume | `anthropic.claude-haiku-5-5` | profile `us.anthropic.claude-haiku-5-5`, us-east-1 | `model-card-anthropic-claude-haiku-5-5.html` (launched 2026-10-07) |
| deep_audit | `anthropic.claude-opus-5-5` | profile `us.anthropic.claude-opus-5-5`, us-east-1 | `model-card-anthropic-claude-opus-5-5.html` (launched 2026-09-22) |
| embeddings | `amazon.titan-embed-text-v2:0` | in-region, us-east-1, no profile | `model-card-amazon-titan-text-embeddings-v2.html` |
| rerank | `cohere.rerank-v3-5:0` | in-region, us-east-1, no profile | `rerank-supported.html` (us-east-1 listed for Cohere Rerank 3.5) |

- The cards list no in-region on-demand access in us-east-1 for any of the three Claude models; they are reached through a geographic or global profile. Calls from us-east-1 on the `us.` profiles go to us-east-1, us-east-2 and us-west-2, which is consistent with ADR-0010's region pin. The Bedrock Converse API is supported on `bedrock-runtime` for all three.
- Dev routes complex_reasoning to Haiku 5.5 and deep_audit to Sonnet 5.5, one tier cheaper, as its test requires.
- **Temperature.** The rule that Sonnet 5.5 and Haiku 5.5 return a 400 on any non-default temperature, and that Opus 5.5 has removed sampling parameters, comes from Anthropic's API reference (the claude-api skill's model table, cached 2026-10-06). The AWS cards don't mention sampling parameters, so "Bedrock passes the rule through" is an assumption for t02 to confirm with a Stubber test.

## Files changed

- **Spec** (`plan_specs/v1/e05-model-router/t01-model-router-port.yaml`): the PM's 2026-10-16 amendments, quoted in Deviations, and the Goal phase.
- **Domain** (`domain/model_contracts.py`, new; `domain/__init__.py`): `TaskClass`, `ModelProvider`, `ModelParams`, `ModelPrompt`, `ModelRequest`, `ResolvedRoute`, `ModelUsage`, `ModelResponse[T]`, `EmbeddingResponse`, `RerankResult` and `RerankResponse`.
- **Application** (`ports/model_router.py`, new; `ports/providers.py`, `ports/__init__.py`, `errors.py`, `application/__init__.py`, `settings.py` docstring): the port and `RoutingConfigError`; the e02 model section removed from `providers.py`; `ModelUnavailableError` added.
- **Integrations** (`integrations/models/__init__.py` and `routing_policy.py`, new; `application/routing_config.py`, deleted; `integrations/__init__.py` docstring): the routing policy.
- **Testing support** (`testing/fakes.py`, `testing/__init__.py`, `testing/contracts/model_router.py` new, `testing/contracts/__init__.py`, `testing/contracts/README.md`):
  - The e02 `FakeModelRouter` implements the new port, adding scripted `embed` and `rerank`.
  - `RecordedModelCall` is replaced by the domain's `ModelRequest`.
  - The contract suite is new.
- **Tests:**
  - `tests/integrations/models/test_routing_policy.py` (moved from `tests/application/test_routing_config.py` and rewritten).
  - `tests/domain/test_model_contracts.py` (new).
  - `tests/contracts/test_model_router_contract.py` (new: stand-in and fake bindings).
  - `tests/application/test_fakes.py`, `test_errors.py` and `test_settings_environments.py` (family asserts).
- **Config** (`config/model_routing.example.yaml`, `.dev.yaml`, `.prod.yaml`): current identifiers; provider, profile, region and timeout per route; no Claude temperature.
- **Repository config and docs:**
  - `pyproject.toml`: `debate_core.integrations.models` joins the AWS-SDK import contract, and a stale comment is updated.
  - `.env.example`: a comment.
  - `docs/architecture/ports-and-adapters.md`: the example and the error tree.
  - `packages/debate_core/README.md`: the module tables and a new `integrations/models/` section.

## Deviations from the spec

1. **The three routing files are outside `constraints.packages`.** `config/model_routing.example.yaml`, `.dev.yaml` and `.prod.yaml` were edited, as the PM's ruling required: new identifiers, provider, profile, region and timeout per route, and no temperature on Claude routes.

2. **Spec amendments, applied as the PM worded them** (commit `9410058`):
   - ac2: "the default file routes …" became "config/model_routing.example.yaml, the default and template file, routes … Amended by the PM, 2026-10-16: the routing file was split per environment by v1-e01-t09."
   - Routing-policy node, `artifact_exists`: `path: config/model_routing.yaml` became `path: config/model_routing.example.yaml`, preceded by the comment "Amended by the PM, 2026-10-16: the routing file was split per environment by v1-e01-t09."
   - Forbidden: "Model IDs, regions or inference profiles hard-coded outside config/model_routing.yaml" became "… hard-coded outside the config/model_routing.*.yaml files", with the same amendment note as a comment.

3. **Second set of spec amendments, from the PM's second ruling of 2026-10-16:**
   - ac2's opening clause: "config/model_routing.yaml maps each task class to provider, …" became "the config/model_routing.*.yaml files map each task class to provider, …". It falls under ac2's existing note: "Amended by the PM, 2026-10-16: the routing file was split per environment by v1-e01-t09."
   - Contract-tests node, `artifact_exists`: `path: packages/debate_core/tests/contracts/model_router_contract.py` became `path: packages/debate_core/src/debate_core/testing/contracts/model_router.py`, preceded by the comment "Amended by the PM, 2026-10-16: since v1-e02-t04 every reusable contract lives in debate_core.testing.contracts, because nothing under tests/ is importable under --import-mode=importlib."

4. **Other edits outside `constraints.packages`:**
   - `pyproject.toml`: the AWS-SDK contract's own comment says a new adapter subpackage is added to its list "in the PR that creates it". The mutation above shows the entry is what protects the package.
   - `.env.example` and `pyproject.toml`: comments naming the moved module.
   - `docs/architecture/ports-and-adapters.md`: the PM's ruling asked for this.
   - `packages/debate_core/README.md`.

5. **`debate_core.testing` is outside `constraints.packages`,** which lists application, domain and integrations. The e02 fake had to change to keep satisfying the port (the PM's ruling), and the contract suite lives there; see 6.

6. **Where the contract suite lives (resolved by the second amendment).** The node first named `packages/debate_core/tests/contracts/model_router_contract.py`. pytest runs with `--import-mode=importlib` and nothing under `packages/debate_core/tests/` is a package, so a module there could not be imported by t02's or t03's tests, which is the node's whole purpose. The suite follows the convention since v1-e02-t04 instead: the class in `debate_core.testing.contracts.model_router`, bound in `packages/debate_core/tests/contracts/test_model_router_contract.py`. The PM amended the path and ruled out a re-export file at the old one ("a file that only passes a check is what the working agreements rule out").

## Decisions and assumptions

- **Route schema.** `provider`, `model_id` and `timeout_seconds` are required on every route, and `region` is required for Bedrock. A system inference profile must be `<geography>.<model_id>`, which catches a Haiku profile under a Sonnet id: one model billed, another recorded. Application profile ARNs are exempt. Embeddings and rerank routes refuse `temperature` and `max_tokens`. Provider `fake` is refused in a file; offline routers are a setting (t03).
- **Temperature range 0.0–1.0**, checked in one place (`MAX_TEMPERATURE`) for the route, `ModelParams` and `ResolvedRoute`, as the PM ruled.
- **`ModelProvider.FAKE`** exists so that fake and replay responses can't be mistaken for billed answers in provenance.
- **`ModelRequest`** is the value form of a `generate_structured` call: class, prompt, the schema's dotted path, and params. t03 can key fixtures on it, and the e02 fake records it in place of `RecordedModelCall`. The schema is named by dotted path rather than bare class name so that two schemas with one name can't share a fixture key. t03 owns the key definition.
- **`ModelPrompt`** carries the prompt id, version and JSON-valued variables, never prompt text; the registry is t04.
- **`ModelUsage`** token counts are optional, because rerank is billed per search unit. The contract requires them for `generate_structured`.
- **`ModelUnavailableError(ProviderUnavailable)`** declares `ERROR_CODE = "PROVIDER_UNAVAILABLE"`. `debate_cli.exit_codes` recognises retryable failures by error code as well as by class, so a new code would have made an unreachable model non-retryable wherever only the code is recorded (`caselist pull`).
- **The e02 fake gained scripted `embed` and `rerank`** (vectors, and scores in document order), so it is a working fake of the whole port and not one that throws on two of its three calls. The fixture-keyed fake and the replay router are still t03's.
- **Contract bindings.** The PM asked for an in-test stand-in, which resolves routes through an in-test `RoutingPolicy` and so switches on the field-by-field route checks. I also bound the shipped `FakeModelRouter`, following the repository's convention of holding each shipped fake to its contract. A router is told what to answer through "planned answers", which t02 can turn into Stubber responses and t03 into cassettes.
- **`RoutingPolicy.from_settings(settings)`** reads `settings.models.routing_file`, which settings already anchors to the checkout or the bundled config.

## Operator follow-ups

None. Every command in this session ran in under two minutes, made no AWS call and needed no credentials. The identifiers came from public AWS documentation pages.

## Follow-up work

- **v1-e05-t03-fake-replay-models:** load and validate the routing file at CLI startup (`RoutingPolicy.from_settings`). The PM ruled this is t03's, and the PM adds it to t03's spec.
- **v1-e05-t02-bedrock-adapter:**
  - Carry `effort` (`output_config.effort`), the quality lever on the current Claude models, as a route default and a per-call parameter. Filed here at the PM's request; not added in t01.
  - Confirm with Stubber tests, and the first real call, that Bedrock Converse rejects a non-default temperature on Sonnet and Haiku 5.5. If it doesn't, a route may set one again.
  - Confirm each identifier and profile in the table above with its first real call (the PM's ruling).
- **v1-e05-t02-bedrock-adapter, for the PM's amendment (ruled 2026-10-16; the PM writes it in the next batch).** t02's ac2 says "generate_structured sends the schema as a forced toolConfig tool". The current models reject a forced tool. These are the model cards checked on **2026-10-16**, AWS Bedrock user guide (docs.aws.amazon.com/bedrock/latest/userguide/), section "Capabilities and Features", features supported on the `bedrock-runtime` endpoint:
  - `model-card-anthropic-claude-sonnet-5-5.html`: "Client-side tool calling (`tool_choice` types `auto` and `none` only)". "Structured outputs" is listed under Not Supported.
  - `model-card-anthropic-claude-opus-5-5.html`: the same `auto`/`none` restriction, with "Structured outputs" Not Supported on both `bedrock-runtime` and `bedrock-mantle`.
  - `model-card-anthropic-claude-haiku-5-5.html`: "Client-side tool calling" does not appear in either the supported or the not-supported list, and "Structured outputs" is Not Supported. Its `tool_choice` support is therefore unknown from the card, and t02's first real call should establish it.
  - Corroboration, not AWS: Anthropic's API reference (claude-api skill, cached 2026-10-06) says forced `tool_choice` (`any`/`tool`) returns a 400 on Sonnet 5.5 and Opus 5.5.
  - The PM's ruling for the amendment: `generate_structured` sends the schema as the single tool with `tool_choice` `auto`, not forced. A response that skips the tool call, or calls it with input the schema rejects, goes to t05's validation and repair. t02's first real call confirms which `tool_choice` types and structured-output options each model accepts, and records them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

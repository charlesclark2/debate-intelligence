# Session report: v1-e05-t05-structured-output-validation

| | |
|---|---|
| Task | `v1-e05-t05-structured-output-validation` — Structured output validation and repair |
| Spec | [`plan_specs/v1/e05-model-router/t05-structured-output-validation.yaml`](../../plan_specs/v1/e05-model-router/t05-structured-output-validation.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t05-structured-output-validation` |
| Session status | COMPLETE |

## Summary

- **The guard.** `StructuredOutputGuard.generate(task_class, prompt, schema, params, *, policy)` in `debate_core.application.structured_output` is how a service now asks for structured output. In order, it:
  1. checks the call's schema and task class against the prompt's registry entry, before any model call;
  2. makes the call;
  3. repairs an invalid answer exactly once, with the registered `model.repair@1.0.0` on the same task class and parameters;
  4. raises `ModelOutputError` with `attempts=2` if the repair is invalid too.
- **Pass-through.** A throttled, refused, denied or unreachable call is not invalid output. Its error passes through unchanged and nothing is repaired.
- **Strict validation lives in every router, not only the guard.** The port returns validated objects, so a guard above it cannot see coercion that has already happened. `validate_model_output` (strict JSON mode, `extra="forbid"` at every depth) is now the one validation that Bedrock, the fixture fake, replay, the scripted router and both in-test stand-ins use. The shared contract suite holds all of them to it.
- **Errors carry no answer text.** An `InvalidModelOutput` carries `OutputProblem` values (loc, type, msg) built from `errors(include_input=False, include_url=False, include_context=False)`, never `str(ValidationError)`. It is raised outside the `except`, so no chained error quotes the answer either.
- **Provenance.** `GeneratedArtifactMetadata` gains `repair_attempted` and `repair_prompt_version`.
- **Look at first:** PM question 1 in Follow-up work. The repair request holds the schema and the problems only, as instructed. So the model is never shown the task it is repairing, and two different calls that fail the same way send identical repair requests. The fixtures show it happening: two malformed cases share one repair file.

All six Goal criteria and every node criterion pass. All 20 targeted mutants are caught. The Goal is set to Succeeded.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| error-types | Done | `application/model_errors.py`: `ValidationPolicy`, `OutputAttempt`, `output_problems`, `describe_problems`, `ModelOutputError`, `PromptMismatchError`. `OutputProblem` and `InvalidModelOutput.problems` are in `application/errors.py`, beside the port error they describe. |
| validating-guard | Done | `application/structured_output.py`: `validate_model_output` and the guard. Every router and the contract suite were moved onto the validator (commit `798d53d`). |
| repair-loop | Done | `prompts/model/repair.md` at 1.0.0, released and locked with `scripts/lock_prompts.py`. `repair_prompt(...)` builds the request. |
| fail-closed-suite | Done | Six malformed fixtures under `tests/fixtures/model_outputs/malformed/`, plus three replay cassettes for ac5. The module, pyright and lint-imports all pass. |

## Acceptance criteria

All tests below are in `packages/debate_core/tests/application/test_structured_output.py` unless another file is named.

**Red first.** Before the green runs, the new tests were run against a refuse-nothing skeleton of the guard: lax `model_validate`, one call, no registry check, no repair, no policy check. Command: `.venv/bin/python -m pytest -q -n 0 -p no:randomly packages/debate_core/tests/application/test_structured_output.py`. Result: **40 failed, 8 passed**. The 8 that pass a skeleton are the ones that check the guard does not over-refuse or that it passes a provider error through:
- the valid pass-through;
- JSON-shaped enums, datetimes and tuples accepted;
- the `describe_problems` helper;
- the four provider-error pass-throughs;
- the fixture-directory listing.

The mutants below exercise those 8 too. The two new contract tests failed first on the two lax in-test stand-in routers: 8 failures across `TestStandInModelRouter` and the three record-replay bindings. They passed once the stand-ins used `validate_model_output`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: valid output passes through unchanged in one model call; invalid-then-valid succeeds after exactly two calls, with `repair_attempted=true` in the result's metadata | PASS | `test_validate_valid_output_passes_through_unchanged_in_one_model_call` checks that `result.response` is the router's own response and that there was one call. `test_repair_invalid_then_valid_succeeds_after_exactly_two_calls_and_says_so_in_the_metadata` checks two calls, `metadata.repair_attempted is True`, `repair_prompt_version == "1.0.0"`, and that `prompt_id` stays the caller's. |
| ac2: output still invalid after the repair raises `ModelOutputError` with prompt_id, version, attempts=2 and a truncated error list | PASS | `test_repair_still_invalid_raises_model_output_error_with_attempts_two`. A valid third answer is queued and never taken, and the whole message is pinned by hand. `test_repair_error_lists_at_most_ten_problems_and_counts_them_all`: 12 problems give 10 listed and "and 2 more". |
| ac3: with `fail_closed=True`, no code path returns a default, partial or coerced object; every malformed fixture raises | PASS | `test_every_malformed_fixture_raises_and_returns_nothing`, 6 cases × 2 policies: missing fields, wrong types, coercible values, extra keys, empty tool output, no tool call. Each case's problems are written by hand. `test_the_malformed_fixture_directory_holds_exactly_the_listed_cases` catches a case that has no fixture. The partial-object and coercion mutants are caught. |
| ac4: the repair prompt is registered (`model.repair`, semver) and repair calls reuse the original task class route | PASS | `test_repair_call_runs_the_registered_repair_prompt_on_the_original_route` checks the same task class, parameters and schema, and that the prompt is registered and released. `uv run scripts/lock_prompts.py --check` exits 0. `test_prompt_lock.py` passes. |
| ac5: a response that never calls the schema's tool is invalid output and gets the one repair; under replay the repair call needs a cassette of its own | PASS | `test_repair_an_answer_that_never_called_the_tool_gets_the_one_repair_under_replay`: the first attempt's problem is `missing_tool_call`, and the answer comes from the repair cassette. `test_repair_under_replay_needs_a_cassette_of_its_own` raises `MissingFixtureError` for `model.repair`, passed through and not swallowed. On the router side, Bedrock's no-toolUse test now pins `missing_tool_call` (`tests/integrations/bedrock/test_router.py`). |
| ac6: a call whose schema or task class differs from its prompt's registry entry is refused before the model is called, shown failing first | PASS | Three tests with `router.calls == []`: wrong schema, wrong task class, unregistered version. All three failed on the skeleton. Two more tests check that the guard refuses to build without `model.repair`, or with one that names a schema of its own. The "registry check after the call" mutant is caught. |
| PM: the sentinel is in neither the repair request, the error, nor any log record | PASS | `test_repair_sentinel_appears_in_no_repair_request_error_or_log_record`. Checked: the request JSON, the rendered repair prompt, `traceback.format_exception(error)`, `args`, `problems`, `attempt_records`, `__cause__`/`__context__`, and every captured record at DEBUG (message and `vars(record)`). `test_validate_error_carries_no_part_of_the_answer` and the contract test `test_a_refused_answer_is_described_without_its_values` check the same for every router. |
| PM: logs carry prompt_id, version, attempts and error counts only | PASS | `test_repair_logs_the_prompt_attempts_and_error_counts_only` pins each record's extras to exactly `prompt_id, prompt_version, attempt, attempts, error_count`. |
| Node error-types: `model_errors.py` contains `class ModelOutputError` | PASS | `grep -c "class ModelOutputError" packages/debate_core/src/debate_core/application/model_errors.py` → `1` |
| Node validating-guard: `uv run pytest packages/debate_core/tests/application/test_structured_output.py -k validate` | PASS | `13 passed` |
| Node repair-loop: `uv run pytest packages/debate_core/tests/application/test_structured_output.py -k repair` | PASS | `18 passed` |
| Node fail-closed-suite: `uv run pytest packages/debate_core/tests/application/test_structured_output.py` | PASS | `48 passed` |
| Node fail-closed-suite: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` (1 min 0 s, under load average 35) |

### Mutants

Twenty mutants were run, the PM's five first. Each was applied to `structured_output.py` or `model_errors.py` alone. Each run used `test_structured_output.py` and the router contract suite (`-x -n 0 -p no:randomly`), with a new empty `HYPOTHESIS_STORAGE_DIRECTORY`. The source bytes were restored and checked after every run. No Hypothesis property is involved, so the empty directory changes nothing; it is set to follow agreement 8. Every mutant failed at a test assertion, not at collection.

| # | Mutant | Result | First test that failed |
|---|---|---|---|
| 1 | A second repair allowed (`range(1, 3 + max_repairs)`) | Caught | `test_repair_still_invalid_raises_model_output_error_with_attempts_two` |
| 2 | Policy accepts `max_repairs=2` | Caught | `test_repair_policy_allows_exactly_one_repair` |
| 3 | A partial object (`model_construct`) returned under fail_closed after the failed repair | Caught | `test_repair_still_invalid_raises_model_output_error_with_attempts_two` |
| 4 | Coercion re-enabled (`strict=True` dropped) | Caught | `test_validate_model_output_refuses_what_lax_validation_would_accept[numeric string]` |
| 5 | Extra keys allowed (`extra="forbid"` dropped) | Caught | `test_validate_model_output_is_strict_at_every_depth_whatever_the_schema_configures` |
| 6 | The input value left in the summary (appended to each problem's msg) | Caught | `test_validate_error_carries_no_part_of_the_answer` |
| 7 | The error built from `str(ValidationError)` and chained `from error` | Caught | `test_validate_error_carries_no_part_of_the_answer` |
| 8 | The registry check after the call | Caught | `test_a_call_whose_schema_differs_from_its_registry_entry_is_refused_before_any_model_call` |
| 9 | Task class check dropped | Caught | `test_a_call_whose_task_class_differs_from_its_registry_entry_is_refused_before_any_model_call` |
| 10 | Provider errors caught and repaired as invalid output | Caught | `test_a_refused_or_throttled_call_passes_through_unchanged_and_is_not_repaired[throttled]` |
| 11 | Repair sent on another task class | Caught | `test_repair_call_runs_the_registered_repair_prompt_on_the_original_route` |
| 12 | Repair drops the call's parameters | Caught | `test_repair_call_runs_the_registered_repair_prompt_on_the_original_route` |
| 13 | Repair resends the call's variables | Caught | `test_repair_request_holds_the_schema_and_problems_and_nothing_the_call_or_model_said` |
| 14 | An author's message that quotes the refused value is kept | Caught | `test_validate_withholds_a_schema_authors_message_that_quotes_the_refused_value` |
| 15 | `attempts` miscounted | Caught | `test_repair_still_invalid_raises_model_output_error_with_attempts_two` |
| 16 | Repaired metadata not marked | Caught | `test_repair_invalid_then_valid_succeeds_after_exactly_two_calls_and_says_so_in_the_metadata` |
| 17 | The repair prompt's declared schema unchecked | Caught | `test_a_guard_refuses_a_repair_prompt_that_names_a_schema_of_its_own` |
| 18 | `None` (no tool call) not named `missing_tool_call` | Caught | `test_validate_model_output_reads_none_as_an_answer_that_never_called_the_tool` |
| 19 | A log record carries the problems' text | Caught | `test_repair_logs_the_prompt_attempts_and_error_counts_only` |
| 20 | The problem list not truncated | Caught | `test_repair_error_lists_at_most_ten_problems_and_counts_them_all` |

### Before the report (working agreements 8 and 10)

- **Affected set: left to the pull request's `ci`.** `uv run scripts/affected_tests.py` selects 453 test files. The root `conftest.py` imports the router port, and `application/errors.py` and the domain are imported almost everywhere. That is far past two minutes; my first attempt at the changed directories alone hit a 115 s alarm. Under the PM's ruling of 2026-10-19 the whole selection is left to `ci`, with no hand-off. Within the limit I ran the following, time-limited on the interpreter:
  - `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not live" packages/debate_core/tests/domain packages/debate_core/tests/contracts packages/debate_core/tests/testing packages/debate_core/tests/integrations/models packages/debate_core/tests/integrations/bedrock tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` → `2324 passed in 77.44s`
  - `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not live" packages/debate_core/tests/application` → `3608 passed in 86.78s`
  - The interrupted first attempt left no orphaned workers (`ps` showed none from this worktree).
- **Log-state check (one process).** The guard's tests assert on log records. No suite configures the guard's logger, and the one that changes the root level (the search-provider contract) restores it. As agreement 10 asks, they were still run once in one process after their neighbours: `.venv/bin/python -m pytest -q -n 0 -p no:randomly -m "not slow and not live" packages/debate_core/tests/contracts packages/debate_core/tests/integrations/bedrock packages/debate_core/tests/application/test_structured_output.py` → `427 passed`
- `uv run --frozen ruff check .` → `All checks passed!`
- `uv run --frozen ruff format --check .` → `1293 files already formatted`
- `uv run pyright packages/debate_core` → `0 errors` (above). Only debate_core changed.
- `uv run lint-imports` → `Contracts: 16 kept, 0 broken.`
- `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 51 CLI command and API route handlers within 25 statements`
- `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 47 indexed documents under docs/ have a description`
- `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 424 shell code blocks in 153 Markdown files`
- `uv run --frozen pre-commit run check-merge-conflict --all-files` → `Passed`
- `uv run scripts/lock_prompts.py --check` → exit 0
- `uv run scripts/validate_specs.py` → `OK: 439 files, 40 epics, 377 tasks, 22 releases`

## Files changed

- **`debate_core.application`** (in scope)
  - `model_errors.py`, `structured_output.py`: new.
  - `errors.py`: `OutputProblem`, and `InvalidModelOutput.problems`.
  - `ports/model_router.py`: one docstring paragraph saying every router validates through `validate_model_output` and services go through the guard.
- **`debate_core.integrations`** (in scope)
  - `bedrock/router.py`: the tool input goes through the shared validator. No-tool, repeated-tool and unfinished answers carry typed problems (`missing_tool_call`, `repeated_tool_call`, `unfinished_answer`).
  - `models/fake_router.py`: the shared validator, and `"output": null` stands for an answer with no tool call.
  - `models/record_replay.py`: the shared validator.
- **`debate_core.domain.provenance`** (outside `packages`, Deviation 1): `repair_attempted` and `repair_prompt_version` on `GeneratedArtifactMetadata`, with a validator that they agree.
- **`debate_core.testing`** (outside `packages`, Deviation 1)
  - `fakes/model_router.py`: `ScriptedModelRouter` validates strictly.
  - `contracts/model_router.py`: two contract tests, strict validation and no answer text in a refusal.
- **`prompts/`**: `model/repair.md`, and its entry in `prompts.lock.json`, written by `scripts/lock_prompts.py`. The README names the first released prompt.
- **`tests/fixtures/`**
  - `model_outputs/malformed/`: 6 call fixtures, 5 repair fixtures and a README.
  - `model_cassettes/`: two `example.select-passage` cassettes and one `model.repair` cassette; the README gains a `null` output paragraph.
- **Tests**
  - `packages/debate_core/tests/application/test_structured_output.py`: new, 48 tests.
  - Changed so the strict rule and the new fields are pinned:
    - `tests/integrations/bedrock/test_router.py`: problem types, and a strict-validation test.
    - `tests/integrations/models/test_artifact_metadata.py`: the hand-written full JSON gains the two fields, plus a test that older JSON without them loads.
    - The two in-test stand-in routers, in `tests/contracts/test_model_router_contract.py` and `tests/integrations/models/test_record_replay.py`.
- **`packages/debate_core/README.md`**: the guard in the application table, and a paragraph under "Things worth knowing".

## Deviations from the spec

1. **Files outside `constraints.packages: [debate_core.application, debate_core.integrations]`.**
   - `debate_core.domain.provenance`: ac1 asks the result's metadata to record `repair_attempted=true`, and the metadata persisted with an artifact is a domain type. A repaired artifact that did not say so would be provenance with a gap.
   - `debate_core.testing`: the strict rule has to hold in every router, or a coerced object reaches a fail-closed caller through the one that is lax (the PM's "one rule"). The scripted router and the shared contract suite live there.
   - `prompts/` and `tests/fixtures/` are the spec's own outputs.
   - Suggested amendment: add `debate_core.domain` and `debate_core.testing` to `packages`.
2. **Validation happens in the routers, through one function, rather than in the guard alone.** The plan says the guard "wraps `ModelRouter.generate_structured` with strict Pydantic validation". The port returns objects the router has already validated, so a guard above it cannot tell `"3"` coerced to `3` from a real `3`. The guard therefore relies on every router calling `validate_model_output`. The contract suite enforces that, and showed it by failing on the two lax stand-ins. The guard still owns the uniform error capture, the repair and the typed failure.
3. **`model.repair`'s front matter names a placeholder schema and a nominal task class.** `PromptSpec` requires both keys, but the repair answers in the failed call's schema and runs on the failed call's route (ac4). So its `output_schema` is `debate_core.application.structured_output.RepairedSchema`, an empty model that nothing is validated as, and the guard checks at construction that the entry names it. `task_class: complex_reasoning` is not used for routing. Both are pinned in the lock. The alternative is a `PromptSpec` change (an optional schema, or a "same as the call" task class), which is t04's file.
4. **t03's fixture format gains `"output": null`** for an answer with no tool call. Before this change it was a `FixtureFileError`. A file missing the `output` key is still one. Without it, the fake could not express ac3's "no tool call" case.

## Decisions and assumptions

- **`fail_closed` changes no behaviour of its own.** The PM ruled validation equally strict for every call, and no path returns anything but a valid object or an error. So the flag is carried on the result's policy and on `ModelOutputError.fail_closed`, where the caller's handling, marking the card UNVERIFIED, can rest on it. `ValidationPolicy` has no default for `fail_closed`, so every call site has to choose. The ac3 suite runs both policies and expects the same raise.
- **`max_repairs: Literal[1]`**, checked again at runtime. The spec names the field, and the PM ruled exactly one repair, so 0 is refused as well as 2.
- **Strict means JSON's strict.** The answer is serialised and validated with `model_validate_json(strict=True, extra="forbid")`, measured on pydantic 2.13.5 before writing it. Python-mode strict would refuse `"neg"` for an enum, a list for a tuple and an ISO string for a datetime, which is exactly what a model sends. `extra="forbid"` per call reaches nested models whatever their own `model_config` says (`test_validate_model_output_is_strict_at_every_depth_whatever_the_schema_configures`).
- **A schema author's message can quote the value, so it is checked.** Pydantic's own messages are written from the schema. A `value_error`, an `assertion_error` or a custom error type carries the validator's own text, and `f"label {label!r} is ..."` would leak it. Such a message is kept only when no string in the refused value appears in it, and is otherwise replaced by a fixed sentence. Location parts are cut to 64 characters, because an extra key's name is the model's text, and messages to 200.
- **`ModelOutputError` subclasses `InvalidModelOutput` and keeps its error code.** A caller that catches the port error catches it too. To a program it is the same failure, per the error-code convention in `errors.py`.
- **`PromptMismatchError` is a `ValueError`,** like the port's other caller mistakes (a scoring class sent to `generate_structured`). An unregistered prompt raises the registry's own `UnknownPromptError`, also before any call.
- **The repair prompt lists at most 10 problems** and names the failed prompt's `id@version` (metadata, no text), so a repair cassette says which prompt it repaired.
- **A response's `prompt_id` after a repair** is `model.repair`, because that call produced it. `StructuredResult.metadata` restores the caller's prompt and adds the two repair fields, so a persisted artifact names the prompt it answers.

## Operator follow-ups

None.

## Follow-up work

**PM questions**, paste-ready:

```text
v1-e05-t05 asks two questions.

1. What may a repair request carry? As built (your ruling of 2026-10-24), it holds the schema, the
   filtered problems and the failed prompt's id@version: nothing the model said and none of the
   call's variables. Two consequences:
   (a) The repair model is never shown the task. It can fix an answer's shape but has nothing to fill
       it from, so a repaired card selection names offsets the model never read the snapshot for.
       t06's span check would mark those UNVERIFIED, but the repair can do little else.
   (b) Two different calls that fail the same way send the same repair request, so they share one
       repair fixture or cassette. Under replay, call B can be served the repair recorded for call A.
       The committed fixtures show it: "wrong types" and "coercible values" share one repair file.
   Options:
   A. Keep it as built.
   B. Send the failed call's own variables again, unchanged (not re-authored), so the repair can
      redo the task. The source text goes to the model a second time. Cassettes become unique.
   C. Add only an opaque key of the failed call (a hash of its request) to the repair variables.
      Cassettes become unique; the repair still has no content.
   Recommendation: B. The spec's words are "never the original source text re-authored", and B sends
   it unchanged. Short of B, C at least fixes the replay collision. A repair with no task is mostly
   a shape fixer.

2. Record mode writes nothing when the real router raises InvalidModelOutput. So a repaired call
   recorded live replays as MissingFixtureError on its first half, and that half has to be written
   by hand (as ac5's cassettes are). Should record mode write the invalid answer, or "output": null
   for no tool call, so the pair can be recorded? That is t03's file, so it would be a follow-up task.
   Recommendation: yes, as a small t03 follow-up, written before the first live recording of a
   structured prompt.
```

**Elsewhere:**

- **v1-e05-t07 (usage telemetry).** An attempt that fails validation raises `InvalidModelOutput`, which carries no `ModelUsage`. So the tokens of a repaired call's first attempt are lost to telemetry and budgets. The error, or the guard's attempt record, would need the usage.
- **v1-e05-t06 (card selection).**
  - A schema validator's message must not quote the refused value. The guard withholds a message that does, but it cannot recognise a paraphrase or a partial quote.
  - t06's schemas get strict JSON validation; anything that needs coercion goes to the PM first, per the PM's note.
  - Its evidence actions call the guard with `ValidationPolicy(fail_closed=True)`.
- **The first CLI command that calls a model** builds the guard in the composition root, from the router and the loaded `PromptRegistry`, which must include `prompts/model/repair.md`. This sits with t04's existing note that `prompts/` must be bundled in installed builds.
- **Repair fixture keys include pydantic's messages.** A pydantic upgrade that rewords one turns the repair fixtures in `tests/fixtures/model_outputs/malformed/` and `model_cassettes/model.repair/` into `MissingFixtureError`. Their README says how to rewrite them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

Careful, well-tested work. The one change asked is question 1, which the session rightly put first.
1. **What is accepted as built:**
   * ac1 to ac6 and both of the PM's checks (the sentinel, and logs carrying counts only), with
     red runs against a refuse-nothing skeleton and 20 of 20 mutants caught;
   * **Deviation 2**, validation in every router through `validate_model_output`, held by the
     contract suite. The point that a guard above the port cannot see coercion that already happened
     is correct, and the suite proved it on the two lax stand-ins;
   * **strict JSON mode** rather than Python-mode strict, measured first;
   * withholding a schema author's message that quotes the refused value, and the length cuts;
   * `fail_closed` carried without behaviour of its own, with no default, so every caller chooses;
   * `max_repairs: Literal[1]`; `ModelOutputError` subclassing `InvalidModelOutput`;
   * **Deviations 3 and 4**: `RepairedSchema` with the nominal task class, pinned in the lock, and
     `"output": null` in t03's fixtures;
   * **Deviation 1**: `debate_core.domain` and `debate_core.testing` are needed. The PM amends
     `constraints.packages` in a PM batch.
2. **Question 1: (B), with the shape below. That is the change requested.** My instruction "never
   the original source text written again" meant never *re-authored*, as the spec says. It did not
   mean a repair should run blind. As built, the repair model gets no task, so a repaired card
   selection could only invent offsets, and two calls that fail alike share a cassette. Under
   replay, that serves one call another call's answer. Both outcomes are worse than sending the
   task again. The variables already went to the same model through the same router under data-use
   policy's model rules, so sending them unchanged a second time adds no exposure.
   * The repair request carries the failed call's own prompt, the same `prompt_id@version` and
     variables rendered by the registry exactly as the first call was, unchanged and not
     re-authored, followed by `model.repair`'s instructions with the schema and the filtered
     problems.
   * It still carries **nothing from the failed answer**: no value, no key the model invented beyond
     the 64-character location cut, and no text.
   * Mutant 13 flips. "Repair drops the call's variables or alters them" must now be caught, with a
     test that the rendered original appears in the repair request byte for byte.
   * Keep the sentinel test, with the sentinel in the model's answer. Add a second sentinel in the
     call's variables, which must appear in the repair request once, and in no error or log record.
   * Repair cassettes and fixtures become unique per call. Show "wrong types" and "coercible values"
     with repair files of their own.
   * `model.repair` 1.0.0 is not on dev yet, so edit it in place and re-lock it. Its changelog says
     what the request carries.
3. **Question 2: yes, as a v1-e05-t03 follow-up,** before the first live recording of a structured
   prompt. Record mode writes the invalid answer, or `"output": null` when no tool was called, so a
   repaired pair can be recorded. The PM files it, and nothing changes here.
4. **The follow-ups on t07** (a failed attempt's usage) and **t06** are right. The PM adds the t07
   one to its spec in a PM batch.
5. **The affected set** of 453 files is left to the PR's `ci` under agreement 10, and the
   application and contract directories passed (5,932). The one-process log-state run was the right
   extra check.

Re-review after the change. Expect a short one: question 1's shape, the flipped mutant, the two
sentinels and the unique repair fixtures.

## Changes after the PM's review

The one change asked for was question 1, option (B), in the shape the review's item 2 gives. Questions 2 and 4 are follow-ups the PM files, so nothing else changed. Commit `4791019`.

**The repair request now carries the failed call's own prompt.**
- **Rendered once, before any call.** The guard's registry check now also renders the call's prompt, with the registry's `render`, which is what a real router sends. That happens before any model call, so a call whose variables do not fit its prompt is refused before anything is sent, as a mismatched schema already was. `PromptCatalog` gains `render`.
- **The rendering goes into the repair unchanged.** `repair_prompt(failed, rendered, schema, problems)` puts it into the repair variables `failed_system` and `failed_user`: same `prompt_id@version`, same variables, not re-authored.
- **Turn order.** `model.repair` opens its system turn with the call's system turn and its user turn with the call's user turn. Its own instructions, the schema and the filtered problems follow.
- **Still nothing from the failed answer.** No value, no text, and no invented key beyond the 64-character location cut.
- **`model.repair` 1.0.0 was edited in place.** Its changelog says what the request carries. `scripts/lock_prompts.py --check` refused the edit ("has changed since it was released"), so the lock was reset to dev's empty lock and re-locked with the script. The body hash went from `62a594ad…` to `62f84d99…`.

**Tests.** The module has 50 tests (48 before): three were replaced and five added. All five new ones failed against the pre-review guard and prompt (from `9aa88d9`), checked out over the new ones and then restored. That run was `.venv/bin/python -m pytest -q -n 0 -p no:randomly packages/debate_core/tests/application/test_structured_output.py` → `18 failed, 32 passed`. The 18 are the five new tests, the replay repair test and the twelve malformed-fixture runs, because their repair keys changed.

| Test | What it pins |
|---|---|
| `test_repair_request_carries_the_call_and_the_problems_and_nothing_the_model_said` | The exact variable set. `failed_system` and `failed_user` equal the example prompt's turns, written by hand from `select-passage.md`. No failed-answer text. |
| `test_repair_request_carries_the_calls_own_rendered_prompt_byte_for_byte` | The registry's rendering of the call opens the repair's rendered system and user turns byte for byte, once each, then the repair instructions. |
| `test_repair_of_a_prompt_with_no_system_turn_opens_with_the_repair_instructions` | A prompt with no system turn: `failed_system` is `None`, and the repair's system turn is the instructions alone. |
| `test_repair_requests_of_two_calls_that_fail_alike_differ` | Two calls with the same problems send different repair requests. |
| `test_repair_sentinels_the_answers_reaches_nothing_and_the_calls_reaches_only_the_repair` | `SENTINEL`, in the model's answer, is in neither the repair request, the rendered repair, the error nor any log record. `CALL_SENTINEL`, in the call's variables, is in the repair request exactly once and in the rendered repair exactly once, and in no error or log record. |

**Fixtures.** Every malformed case has a repair fixture of its own: 6 files in `tests/fixtures/model_outputs/malformed/model.repair/`, up from 5. "wrong types" is `377e9052…` and "coercible values" is `d14add30…`. The six call fixtures are byte-identical to before, and the ac5 replay repair cassette is now `model.repair/715ebbc9…`. The malformed README says why the cases no longer share a file and shows the new `repair_prompt` call.

**Mutants.** The same runner as before (`-x -n 0 -p no:randomly`, a fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run, bytes restored and checked after each) ran 21 mutants, and all 21 were caught. Two rows changed from the first table:
- **Mutant 8, the registry check after the call:** now two edits, rendering the prompt up front and checking after the call. Caught by `test_a_call_whose_schema_differs_from_its_registry_entry_is_refused_before_any_model_call`.
- **Mutant 13 flips** to "repair drops the call's rendered prompt" (`failed_system=None`, `failed_user=""`).
- **Mutant 20 is new:** "repair alters the call's rendered prompt" (`failed_user` lower-cased).
- The old truncation mutant is now number 21. The other 18 are unchanged and still caught by the same tests.

Mutants 13 and 20 were caught first by the variable-set test. Each was then run again against `test_repair_request_carries_the_calls_own_rendered_prompt_byte_for_byte` alone, and that test caught both.

**Checks this round:**
- `ruff check .` → `All checks passed!`
- `ruff format --check .` → `1293 files already formatted`
- `lint-imports` → `16 kept, 0 broken`
- `pyright packages/debate_core` → `0 errors`
- `scripts/lock_prompts.py --check` → exit 0
- The guard, models, bedrock, contracts, architecture, specs, docs and command-block tests → `1300 passed`.
- The application tests that reach the guard (`test_structured_output`, `test_fakes`, `test_errors`, `test_port_conformance`) → `152 passed`.
- The one-process log-state run (contracts, bedrock, then the guard's module) → `429 passed`.
- **Not completed this round:** the whole `tests/application` directory. It passed in the first round (3608 tests), but this round it hit the 115 s alarm under load average 28. No workers were orphaned. Nothing else in that directory imports the changed modules. It stays with the PR's `ci`, as the affected set does.
- `scripts/validate_specs.py` → `OK: 439 files, 40 epics, 377 tasks, 22 releases`
- `scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 424 shell code blocks in 153 Markdown files`

The Goal stays `Succeeded`. Stopping for the PM's re-review.

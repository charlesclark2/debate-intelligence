# Session report: v1-e05-t10-record-mode-keeps-invalid-answers

| | |
|---|---|
| Task | `v1-e05-t10-record-mode-keeps-invalid-answers` — Record mode keeps an invalid answer, so a repaired call can be recorded live |
| Spec | [`plan_specs/v1/e05-model-router/t10-record-mode-keeps-invalid-answers.yaml`](../../plan_specs/v1/e05-model-router/t10-record-mode-keeps-invalid-answers.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t10-record-mode-keeps-invalid-answers` |
| Session status | COMPLETE |

## Summary

When the real router raises `InvalidModelOutput`, record mode now writes that answer's cassette,
keyed like any other recording. The cassette holds the answer as the router received it
(`"output": null` when no tool was called), plus the error's `problems`, `model_id` and `usage`.
Replay raises that same error, so the guard sends the same repair request and finds the repair's
own recorded cassette. A repaired call recorded live therefore replays both halves, and nothing is
written by hand.

`InvalidModelOutput` still carries no part of the answer. Instead the Bedrock adapter hands the
answer to record mode through a context variable that only record mode listens on
(`integrations/models/received_answer.py`).

Nothing is recorded for a provider error, a budget refusal, a call that never reached the provider,
or an invalid answer that no router handed over. Every committed cassette replays unchanged.

**PM, please look first at the first Deviation.** The cassette records the router's problems as
well as its answer, and replay raises those recorded problems instead of validating the output
again. Without that, ac1 fails for two of the three kinds of invalid answer.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `record-invalid` — Record mode keeps invalid answers | Done | The tests were run red on the unchanged router first (11 failed). Then the implementation, the Bedrock hand-over and the docs. 16 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — With a stand-in live router, recording a call whose first answer is invalid and whose repair is valid writes two cassettes, and replaying them gives the same InvalidModelOutput, the same repair request and the same result; a no-tool answer records as output null; a provider error records nothing; tests shown failing first | PASS | See the list below this table. |
| Node `record-invalid`: Record-replay tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/models/test_record_replay.py` → `155 passed in 3.98s` |

Evidence for ac1:

- **Two cassettes, then the same error, repair request and result.**
  `test_record_a_repaired_call_writes_both_halves_and_replay_gives_the_same_error_repair_and_result`
  covers three first answers: one that does not fit the schema (two problems), one that never called
  the tool, and one that fits the schema but is refused because the turn was cut off.
  - It checks that exactly two files are written, `example.select-passage/<key>.json` and
    `model.repair/<key>.json`.
  - The first cassette's whole `response` is compared with a value written by hand.
  - On replay through `StructuredOutputGuard`, the requests (the repair request included) are equal
    to the live run's, and so is what each call returned.
  - The replayed refusal is also compared with a hand-written error: its message, problems, model id
    and usage.
  - Output and attempts are equal to the live run's.
- **A no-tool answer records as `"output": null`.**
  `test_record_an_answer_that_never_called_the_tool_as_output_null` checks
  `response["output"] is None`.
- **A provider error records nothing.** `test_record_a_provider_error_records_nothing` covers access
  denied, throttled, unavailable and request rejected, each both with and without an answer handed
  over first, and checks that no file is written.
- **Budget refusals and calls that never reached the provider.** The tests
  `test_record_a_budget_refusal_records_nothing_and_reaches_no_model` and
  `test_record_a_call_that_never_reached_the_provider_records_nothing` cover them.
- **Red first.** The red run is below; the result was 11 failed, 143 passed.

The tests use `StandInLiveRouter`, which is written in the test file and holds only invented
answers. No test makes a live call.

### Red run

Command: `.venv/bin/python -m pytest -q -n 0 -p no:randomly --tb=line packages/debate_core/tests/integrations/models/test_record_replay.py`

It ran at commit `2b5ec59`: the new tests and the hand-over module, with the record router not yet
changed. Result: `11 failed, 143 passed`. Every failure has the same cause, which is that nothing is
recorded for an invalid answer:

- The repaired-call test, all three cases: `assert [PosixPath('model.repair/…')] == [PosixPath('example.select-passage/…'), …]`. Only the repair was written.
- The built-router test: `MissingFixtureError: no recorded answer for prompt example.select-passage@1.0.0`.
- The no-tool, replay-without-guard and unreadable-cassette tests (4 cases): `FileNotFoundError` on the first call's cassette.
- The scrub test: `ValueError: not enough values to unpack (expected 1, got 0)`. No cassette exists.

The "records nothing" tests passed red, which is expected, because the old router recorded nothing
at all. They are tested by mutants 2, 4, 6 and 12 below.

Three tests were written after the implementation:

- The Bedrock test, `test_structured_output_refused_is_recorded_as_received_and_replays_as_the_same_error`.
  Its red run is mutant 14, which is the adapter as it was before this task.
- The concurrent-calls test. Its red run is mutant 16.
- The two-problem case. Its red run is mutant 10.

### Mutation run

The script is
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e05-t10-record-mode-keeps-invalid-answers/cfbf9e7f-ba93-40c2-aca4-f70de6ebc7ef/scratchpad/mutants.py`
(scratch, not committed).

- For each mutant it edits a committed file, runs `test_record_replay.py`, the Bedrock
  `test_router.py` and `test_structured_output.py` (312 tests), and restores the file with
  `git checkout`.
- Each run set `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory. None of these tests uses
  Hypothesis.
- The tree was clean after every batch.
- All 16 mutants were run against the final tests at `9448c87`.
- Mutant 10 survived the first run. The tests were then strengthened (the two-problem case), and the
  mutant is caught now.

| # | Mutant | Result | Caught by |
|---|---|---|---|
| 1 | **PM:** an invalid answer recorded in a valid answer's form (route, usage, output, no problems), so replay returns a result | Caught (10 failed) | Repaired-call test (hand-written cassette); replay-without-guard; built-router; Bedrock test, where the cut-off case fails with `DID NOT RAISE InvalidModelOutput`, so replay returned a result |
| 2 | **PM:** a provider error recorded as an answer | Caught (9 failed) | `test_record_a_provider_error_records_nothing`, `test_a_failed_real_call_records_nothing` |
| 3 | **PM:** a no-tool answer recorded as `{}` rather than `null` | Caught (4 failed) | The no-tool test, the repaired-call test (no-tool case), the concurrent-calls test, the Bedrock test |
| 4 | Any refusal other than an invalid answer recorded (budget, render, provider) | Caught (12 failed) | Budget, never-reached and provider-error tests |
| 5 | Replay validates the recorded output again, raising its own wording of the problems | Caught (3 failed) | Repaired-call test (no-tool case: the repair request differs), Bedrock test |
| 6 | Record writes an invalid answer it was never handed | Caught (1 failed) | `test_record_never_writes_an_invalid_answer_it_was_not_handed` |
| 7 | The invalid answer's usage not recorded | Caught (9 failed) | Repaired-call, replay-without-guard, built-router, Bedrock tests |
| 8 | Replay drops the recorded usage | Caught (10 failed) | The same tests, plus the unreadable-usage case |
| 9 | Replay drops the recorded model id | Caught (9 failed) | Repaired-call, replay-without-guard, built-router, Bedrock tests |
| 10 | Only the first problem recorded | Caught (1 failed); survived before the two-problem case was added | Repaired-call test, schema case |
| 11 | A problem's location not recorded | Caught (4 failed) | Repaired-call, replay-without-guard, built-router, Bedrock tests |
| 12 | Live mode goes through the recording path | Caught (2 failed) | `test_live_mode_keeps_no_invalid_answer`, `test_live_mode_records_nothing` |
| 13 | Replay accepts a model id that is not text | Caught (1 failed) | `test_a_recorded_invalid_answer_that_cannot_be_read_is_refused[model-id-not-text]` |
| 14 | The Bedrock adapter hands nothing over (the adapter before this task) | Caught (4 failed) | Bedrock test, all four cases |
| 15 | The Bedrock adapter hands over only the first of repeated tool calls | Caught (1 failed) | Bedrock test, "called twice" |
| 16 | One process-wide listener instead of a context variable | Caught (1 failed) | `test_record_calls_made_together_each_keep_their_own_answer` |

### Checks before the report

The affected set was not run in this session.

- `uv run scripts/affected_tests.py` selects 279 of 538 test files (51.9%). The root `conftest.py`
  imports `fake_router`, which imports the `integrations.models` package, which imports
  `record_replay`.
- Half the default selection is about three minutes at the agreed ~6 minutes for the whole suite.
  Agreement 10 leaves that run to the pull request's `ci` check.
- Within the two minutes, the session ran the changed test directories, the other cassette
  consumers, the router contract suite, the always-run list and the docs checks:

  `.venv/bin/python -m pytest -q -n auto -m "not slow and not live" packages/debate_core/tests/integrations/models packages/debate_core/tests/integrations/bedrock packages/debate_core/tests/application/test_structured_output.py packages/debate_core/tests/application/test_budget.py packages/debate_core/tests/contracts packages/debate_core/tests/evidence/test_selection_contract.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`

  Result: `1611 passed in 29.36s`.

The cheap whole-repo checks:

| Check | Result |
|---|---|
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen ruff format --check .` | `1503 files already formatted` |
| `.venv/bin/pyright` (whole repo, as CI) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 54 indexed documents under docs/ have a description` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 505 shell code blocks in 187 Markdown files` |
| `uv run --frozen pre-commit run check-merge-conflict --all-files` | `Passed` |
| `uv run scripts/validate_specs.py` (after setting the phase) | `OK: 478 files, 40 epics, 416 tasks, 22 releases` |
| `git diff --name-only origin/dev...HEAD -- 'tests/fixtures/model_cassettes/**/*.json'` | No files: no committed cassette changed |

## Files changed

- **`packages/debate_core/src/debate_core/integrations/models/received_answer.py`** (new). This is
  how a real router hands record mode the answer it is about to validate: `receiving_answer()` (a
  context-variable listener) and `hand_over_answer()`. Nothing listens outside record mode.
- **`packages/debate_core/src/debate_core/integrations/models/record_replay.py`.**
  - Record mode listens around each structured call. On `InvalidModelOutput` it writes the refused
    answer's form, but only if it was handed an answer, and then re-raises.
  - Replay raises a cassette with `problems` as the same error.
  - The module docstring describes the form.
- **`packages/debate_core/src/debate_core/integrations/bedrock/router.py`.** The adapter hands over
  what the model answered before any refusal or validation: the tool's input, every input when the
  tool was called more than once, or `None` when it was not called. The docstring says so.
- **Tests.**
  - `packages/debate_core/tests/integrations/models/test_record_replay.py` gets a new section, with
    `StandInLiveRouter` and `ObservingRouter`.
  - `packages/debate_core/tests/integrations/bedrock/test_router.py` gets one test that records
    against a stubbed Converse and replays.
- **Docs.**
  - `tests/fixtures/model_cassettes/README.md` drops the line saying that the first half of a
    repaired call is written by hand, and says what record mode now writes.
  - `packages/debate_core/README.md` gets one table row for the new module.
- **`plan_specs/v1/e05-model-router/t10-record-mode-keeps-invalid-answers.yaml`.** The phase is set
  to Succeeded.

## Deviations from the spec

1. **The cassette also records why the router refused the answer, and replay raises that rather
   than validating the output again.** The spec says to write "the invalid answer as the router
   received it, or `"output": null`". With only that, replay would have to validate the output again
   to raise an error, and ac1 fails in two ways:
   - **An answer with no tool call** replays as `validate_model_output`'s "the answer did not call
     the schema's tool". The live run had Bedrock's own wording, "the model did not call the
     PassageChoice tool (stopReason 'end_turn')". The repair request quotes the problems, so the
     replayed repair has a different key and is `MissingFixtureError`. Mutant 5 shows this.
   - **An answer refused for its stop reason** (`max_tokens`, `guardrail_intervened`,
     `content_filtered`) may fit the schema, so replay would return a result where the live run was
     refused. This is the PM's first mutant, and mutant 1's Bedrock "cut off" case shows it.

   So the refused answer's response is `{"model_id", "output", "problems", "prompt_id",
   "prompt_version", "usage"}`. A response holding `problems` replays as that `InvalidModelOutput`;
   any other response replays exactly as before. Problems hold no part of the answer (t05's rule),
   and the whole document is scrubbed as before. If the PM agrees, the spec's description could say
   "the answer as the router received it, and the problems it was refused for".
2. **`packages/debate_core/README.md` is outside `constraints.packages`.** It gets one row in the
   models table for the new module, as that table lists every module in the package.

## Decisions and assumptions

- **How record mode gets the answer.** `InvalidModelOutput` holds no part of the answer by design
  (t05: the error goes to the guard, logs and reports), and `application/errors.py` is outside this
  task's packages. So the answer travels separately: the adapter calls `hand_over_answer()` with
  it, and only an open `receiving_answer()` block takes it.
  - The listener is a context variable, so concurrent calls under `asyncio.gather` each hear only
    their own answer. Mutant 16 shows a process-wide listener mixing them up.
  - It passes through `BudgetGuard` and `UsageRecordingRouter` untouched, because both await the
    real router in the same context.
- **No hand-over means nothing is written.** A router that raises `InvalidModelOutput` without
  handing over an answer gets no cassette, because a `null` would falsely claim the model called no
  tool. Replay of that call is then `MissingFixtureError`, as before this task.
  - The Bedrock adapter is the only real router, and it hands over.
  - A future real router has to call `hand_over_answer()` for its invalid answers to be recorded.
    The `received_answer` docstring says so.
- **A tool called more than once** is recorded as the list of its inputs, which is what the model
  said. Replay raises the recorded `repeated_tool_call` problem.
- **The replayed error's prompt id and version are the call's own**, which the key covers. Its
  model id and usage are the recorded ones. With `usage: null` the replayed error's usage is `None`.
- **Replay still logs nothing.** The usage recorder sits inside the record-and-replay router, so a
  replayed refusal's tokens reach the guard's attempt record only.
  `test_record_through_the_built_router_logs_both_halves_once_and_replay_logs_nothing` builds the
  chain with `build_model_router` and checks that the usage log holds exactly two lines (attempt 1
  with 100 tokens, attempt 2 with 200) both before and after the replay.
- **Removal is unchanged.** The removal runbook's model-cassettes step deletes a caselist's
  recordings under `<data dir>/landscape/model-cassettes/` whatever they hold, so invalid answers
  recorded there go with the valid ones. No runbook edit is needed.
- **v1-e01-t32 is running beside this task.** The new tests import nothing new from
  `debate_core.testing.contracts` (the existing `ContractPassage` and the contract names were there
  already), plus `FixedClock` from `debate_core.testing.fakes.clock_and_ids`. If t32 moves a
  re-export, the sync will show it.

## Operator follow-ups

None. The pull request's `ci` check runs the affected set (279 files) or the whole selection.

## Follow-up work

- **The two hand-written t05 invalid-answer cassettes** (`example.select-passage/d3356117…`, which
  has `null`, and `885bdb54…`, which has `{}`) are in the older form, without `problems`. They
  replay as before, as the PM asked. If one of them is ever re-recorded, it will come back in the new
  form with Bedrock's own wording.
- **v1-e32-t07's first recordings** of a structured prompt are the first real use of this. A
  repaired call will leave two files in the model-cassette directory.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

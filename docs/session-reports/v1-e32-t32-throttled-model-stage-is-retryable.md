# Session report: v1-e32-t32-throttled-model-stage-is-retryable

| | |
|---|---|
| Task | `v1-e32-t32-throttled-model-stage-is-retryable` — A landscape model stage stopped by throttling ends as retryable, not as a verdict |
| Spec | [`plan_specs/v1/e32-argument-landscape/t32-throttled-model-stage-is-retryable.yaml`](../../plan_specs/v1/e32-argument-landscape/t32-throttled-model-stage-is-retryable.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t32-throttled-model-stage-is-retryable` |
| Session status | COMPLETE |

## Summary

A `landscape report` whose model stage is stopped partway by throttling (`ProviderRateLimited`) or by a
model that did not answer (`ProviderUnavailable` and its subclasses, `ModelUnavailableError` among them)
now exits `3` (retry later), not `1`. A refused call (`ModelAccessDenied`, `ModelRequestRejected`) still
exits `1`. `ModelStageInterrupted` now carries the provider error that stopped the stage as `cause`.
`exit_code_for` checks that cause against `RETRYABLE_PROVIDER_FAILURES`, the same tuple v1-e05-t09 left
on exit 3. The `--json` error envelope keeps its shape and its `code` (`MODEL_STAGE_INTERRUPTED`), and
`error.details` gains one key, `cause_code` (`PROVIDER_RATE_LIMITED`, `MODEL_ACCESS_DENIED`, ...). The
cache already kept the answered cards across a stop. A new command-level test now shows that a rerun
asks the model only about the card the throttle stopped. Where the PM should look first: the exit-code
rule in [exit_codes.py](../../packages/debate_cli/src/debate_cli/exit_codes.py) and Decisions 2 and 3
below (a cause on neither list exits 1, and `error.code` is unchanged).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `throttled-model-stage-is-retryable` (Retryable model stage stop) | Done | Tests written first and shown red against the unchanged code; the three PM mutants are each caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a model stage stopped by throttling exits 3 with the cause's code, one stopped by an access denial exits 1, and a rerun asks the model only about cards not yet cached, by tests shown failing first | PASS | Red, before any code change: `.venv/bin/python -m pytest -n 0 -p no:randomly --tb=line -q <the three test files> -k "retryable_cause or refused_call or rerun_after_a_throttled or stopped_landscape_model_stage or unreachable_model_keeps"` → `12 failed, 188 deselected in 26.16s`. Each failed for its own reason. The throttled and model-unavailable CLI runs exited 1 where 3 was asserted. The access-denied and request-rejected runs already exited 1 and failed on `KeyError: 'cause_code'`. The rerun test failed at its first run's exit code (1, not 3). The six `test_output.py` cases failed on `details` missing `error`/`cause_code`. The `test_position_classification.py` case failed with `AttributeError: ... no attribute 'model_interrupted_by'`. Green: those three files plus `test_landscape_model_stage.py` and `test_landscape_run.py`, in full → `252 passed in 10.89s`. Mutants below. |
| Node: "Retryable model stage stop tests pass", `uv run pytest packages/debate_cli/tests -k landscape` | PASS | Run as `.venv/bin/python -m pytest packages/debate_cli/tests -k landscape -q` under a 115 s alarm → `73 passed in 16.08s`. `--collect-only` shows 11 of the selected tests are this task's (5 in `test_landscape_command.py`, 6 in `test_output.py`). |

### Mutants (agreement 8)

Each mutant was applied to the committed code, then the twelve new and changed tests were run with
`-n 0 -p no:randomly` and `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory (none of these
tests uses Hypothesis), then restored with `git checkout HEAD -- packages`, and `git status --porcelain`
printed nothing.

| Mutant | Change | Result |
|---|---|---|
| Throttling back to exit 1 | The new `ModelStageInterrupted` branch in `exit_code_for` deleted | Caught, `5 failed, 7 passed`: both retryable CLI cases, the rerun test, and the throttled and unavailable `test_output.py` cases |
| Access denied made retryable | The branch tests the cause against `ProviderError` instead of `RETRYABLE_PROVIDER_FAILURES` | Caught, `6 failed, 6 passed`: both refused CLI cases and the four `test_output.py` cases whose cause is refused or unclassified |
| The cache not kept across the stop | `results.clear()` added in the stage's `except ProviderError` branch, so nothing answered is cached | Caught, `4 failed, 8 passed`. The rerun test fails at [test_landscape_command.py:549](../../packages/debate_cli/tests/test_landscape_command.py#L549), `assert _asked(stopping_router) == [throttled]`: the rerun asked about both cards. The two retryable CLI cases (`sent` 0, not 1) and the core interruption test (nothing cached) fail as well. |

### Checks before the report

* Affected set: `uv run scripts/affected_tests.py` chose `206 of 575 test files (35.8%) ... from 10
  changed files`. `exit_codes.py` is imported by every CLI command, so that set reaches most of the
  CLI suite. I ran it once as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -q
  -m "not slow and not live" -p no:cacheprovider $(cat affected.txt)`. The alarm stopped it at 24% after
  1:55 with no failure printed, so the whole set takes several minutes. Per agreement 10 it is left to
  the pull request's `ci` check, which runs the same affected set.
* Within two minutes instead, the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
  `test_help_rendering.py`, `test_container_factories.py`) plus every test file that reads a changed
  module or name. These are `test_output.py`, `test_recorded_failure_codes.py`,
  `test_caselist_parse.py`, `commands/test_caselist_pull.py`, `test_landscape_command.py`,
  `test_position_classification.py`, every `debate_core/tests/application/test_landscape_*.py`, and
  `tests/smoke/*landscape*` (22 paths): `952 passed in 38.25s`.
* `ruff format --check packages/debate_cli packages/debate_core` → `912 files already formatted`; `ruff
  check` → `All checks passed!`; `pyright packages/debate_cli packages/debate_core` → `0 errors, 0
  warnings, 0 informations`.
* `uv run lint-imports` → `Contracts: 19 kept, 0 broken.`; `uv run python scripts/check_thin_handlers.py`
  → `OK: 68 CLI command and API route handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 512 files, 40 epics, 450 tasks, 22 releases`.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_model_stage.py`: `ModelStageInterrupted`
  takes the cause (`cause`, `error`, `cause_code`, `sent`, `unanswered`). `ModelStageOutcome` stores
  the error itself (`interrupted_by`), and `interrupted` is now a property naming its class.
* `packages/debate_core/src/debate_core/application/position_classification.py`:
  `ClassificationCounts.model_interrupted_by` carries the error, and `model_interrupted` is now a
  property.
* `packages/debate_core/src/debate_core/application/landscape_run.py`: raises `ModelStageInterrupted`
  with the cause, `from` it.
* `packages/debate_cli/src/debate_cli/exit_codes.py`: the exit-3 branch for a stage stopped by a
  retryable cause, and its docstrings.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: the command's "Exit codes" docstring
  (also its `--help` text) names the exit 3 and `error.details.cause_code`.
* Tests: `packages/debate_cli/tests/test_landscape_command.py` adds the v1-e32-t32 section and makes the
  `model_router` fixture's stage wiring a helper that takes a batch size. `test_output.py` adds the
  exit-code and envelope table for a stopped stage. `packages/debate_core/tests/application/test_position_classification.py`
  adds one assertion that the counts carry the raised error.

## Deviations from the spec

None.

## Decisions and assumptions

1. **The cause is carried on `ModelStageInterrupted`, not as a new exception per cause** (the PM's
   preference). It is kept as the exception (`cause`), and the run raises `from` it, so the traceback
   `--verbose` prints names it too. `exit_code_for` checks the cause with `isinstance` against
   `RETRYABLE_PROVIDER_FAILURES`, like the `STOPPED_BY_A_STORE` check above it. The rule then follows
   the same tuple a bare provider failure is judged by, and `ProviderTimedOut`, `ProviderCircuitOpen`
   and `ModelUnavailableError` count as unavailable because they subclass it. I did not compare the
   recorded code (`exit_code_for_failure_codes`). That would also work today, because the subclasses
   declare `PROVIDER_UNAVAILABLE`, but it would make the exit depend on each subclass declaring its code.
2. **A cause on neither list exits 1.** A stage stopped by a bare `ProviderError`, or a future subclass
   nobody has put on a list, is not called retryable. This follows `exit_code_for_failure_codes`'s rule,
   "nothing reaches 3 because nobody classified it", and the PM's wording, "a cause in the retryable
   provider failures". A bare `ProviderError` raised directly still exits 3, as before. Pinned by
   `test_output.py`'s `landscape-stage-unclassified` case.
3. **`--json` stays additive.** `error.code` is still `MODEL_STAGE_INTERRUPTED` for every cause, so a
   script that branches on it is unchanged and the code still says the cache kept what was answered.
   The cause's code is a new key, `error.details.cause_code`, beside the existing `error` (class name),
   `sent` and `unanswered`. `error.exit_code` follows the real exit status, as everywhere. Nothing
   else in the envelope changed.
4. **One stored field, not two.** The stage and the counts used to store only the class name
   (`interrupted`, `model_interrupted`). They now store the error, and those two names became read-only
   properties naming its class. `landscape evaluate`'s `interrupted` in its JSON, and the existing
   test that reads `"ModelUnavailableError"`, are unchanged, and the name cannot disagree with the
   error. Only the stage and the classification service built these fields with keyword arguments.
5. **Proved at the command, through the scripted router.** The new CLI tests build the replay stage with
   one card per call over `ScriptedModelRouter`. The first call is answered and the second raises the
   error the Bedrock adapter raises. No model is called. v1-e40-t17's `--restored-copy` and `would_ask`
   are untouched.
6. Before measuring I fetched `origin/dev` (`git fetch origin dev`) to diff this task's spec against it.
   The only difference was this branch's own phase change.

## Operator follow-ups

None. The affected set (about 206 files, several minutes) runs in the pull request's `ci` check.

## Follow-up work

* **`landscape evaluate` has the same verdict-versus-retry problem** (`v1-e32-argument-landscape`). Its
  JSON reports `interrupted` (the class name), but a throttled evaluation exits `1` like one below
  the bar. Its outcome now carries `interrupted_by`, so the same rule could give it exit 3.
* **`retry_after_seconds` is not passed on.** A `ProviderRateLimited` cause can carry how long to
  wait, and `error.details` names only its code. Adding it would be one more additive key, if the
  operator's runbook (v1-e40-t17) wants to say when to retry.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

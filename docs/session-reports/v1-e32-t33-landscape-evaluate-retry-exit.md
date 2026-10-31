# Session report: v1-e32-t33-landscape-evaluate-retry-exit

| | |
|---|---|
| Task | `v1-e32-t33-landscape-evaluate-retry-exit` — A throttled landscape evaluation exits as retryable, and a throttled stop says how long to wait |
| Spec | [`plan_specs/v1/e32-argument-landscape/t33-landscape-evaluate-retry-exit.yaml`](../../plan_specs/v1/e32-argument-landscape/t33-landscape-evaluate-retry-exit.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t33-landscape-evaluate-retry-exit` |
| Session status | COMPLETE |

## Summary

`landscape evaluate` now judges a model stage that stopped partway the way `landscape report` does.
`FormatEvaluation.stopped` builds the same `ModelStageInterrupted` a landscape run raises, and the command
reports it through t32's own path (`CommandFailure.from_exception` → `exit_code_for`). A throttle or a model
that did not answer exits `3`. A refused or unclassified cause exits `1`. Either way `error.code` is
`MODEL_STAGE_INTERRUPTED`, with `cause_code` in `error.details`. A completed evaluation under the bar still
exits `1` with `EVALUATION_BELOW_BAR`. When the cause is a `ProviderRateLimited` that carries a
`retry_after_seconds`, `ModelStageInterrupted` sets it, and both commands' `error.details` carry it as one
added key. The key is left out otherwise. **What to look at first:** the red run found that a stopped
evaluation whose answered cards met the bar **exited 0**, refused stops included, so it read as a pass
(Decision 2). Also, Bedrock's throttling never states a wait today, so on a real Bedrock throttle the new
key will be absent (Decision 6, Follow-up work).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `landscape-evaluate-retry-exit` (Evaluate retry exit) | Done | Tests written first and run red twice: once at the start commit, once against a plumbing-only commit. All four PM mutants are caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a throttled evaluation exits 3 with the cause's code, a refused one exits 1, and a throttled stop of either command reports `retry_after_seconds` when the cause carries it, by tests shown failing first | PASS | Red and green below; mutants below. |
| Node: "Evaluate retry exit tests pass", `uv run pytest packages/debate_cli/tests -k landscape` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k landscape -q` → `90 passed in 13.21s`. `--collect-only` shows that 12 of the selected tests are this task's. |

### Red, then green

The new tests: 3 report cases and 9 evaluate cases in `packages/debate_cli/tests/test_landscape_command.py`,
and 2 in `packages/debate_core/tests/application/test_landscape_model_stage.py`. Each run was
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly --tb=line -q <the two files> -k "says_how_long_to_wait or evaluate_stopped or evaluate_throttled or evaluate_completed or model_stopped_keeps or ran_to_the_end"`.

1. **At the start commit `a5b378d`:** `11 failed, 3 passed`. Every evaluate case and both core cases failed
   because `FormatEvaluation` has no `interrupted_by` (a `TypeError`/`AttributeError`). Those failures
   say only that the field is missing, so I committed that field and its plumbing alone (`a698308`, no
   change in behaviour) and ran the tests red again.
2. **Against the plumbing alone, `a698308`:** `9 failed, 5 passed in 1.17s`. Each failure has its own reason:
   * evaluate throttled, with a wait / without one / model unavailable: `assert 0 == 3`. The run exited
     **0**: the 12 answered cards met the bar, so the stop went unnoticed;
   * evaluate access denied / request rejected / unclassified: `assert 0 == 1`, the same exit 0;
   * evaluate throttled below the bar: `assert 1 == 3`. It exited 1 with `EVALUATION_BELOW_BAR`, a verdict;
   * report throttled with a wait: the key set lacked `retry_after_seconds`;
   * core, stopped evaluation: `AttributeError: 'ModelStageInterrupted' object has no attribute 'retry_after_seconds'`.

   Five passed at red, because the behaviour they pin did not change. They are the guards for the
   mutants: report throttled without a wait, and report with the model unavailable (key absent, as
   before); evaluate completed below the bar (`1`, `EVALUATION_BELOW_BAR`, details exactly the summary's
   keys); evaluate throttled with a name in a cassette (`1`, the scan decides); and core, an evaluation
   that ran to the end has no stop.
3. **Green, at `e2d2552`:** the same selection gave `14 passed, 85 deselected in 0.90s`. The changed areas in
   full (`test_landscape_command.py`, `test_output.py`, `test_help_rendering.py`, `test_landscape_model_stage.py`,
   `test_position_classification.py`, `test_landscape_run.py`) gave `275 passed in 26.78s`.

### Mutants (agreement 8)

Each mutant was applied to the committed code by a scratch script. The new and neighbouring tests were then
run (`-k "evaluate or says_how_long or stopped_by or stopped_landscape or model_stopped_keeps or
ran_to_the_end"` over `test_landscape_command.py`, `test_output.py` and `test_landscape_model_stage.py`, 37
tests), with `-n 0 -p no:randomly` and `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory for each
run. None of these tests uses Hypothesis. Each mutant was then restored with `git checkout HEAD -- packages`,
and `git status --porcelain` printed nothing. A second pass with `--tb=line` confirmed where each one failed.

| Mutant | Change | Result |
|---|---|---|
| Evaluate's throttle back to 1 | `exit_code=ExitCode.DOMAIN_FAILURE` added to the `dataclasses.replace` in `_evaluation_failure` | Caught, `4 failed, 33 passed`: the three retryable evaluate cases and throttled-below-the-bar, all at their exit-code assertions |
| A refused cause made retryable | in `exit_code_for`, the stop's cause tested against `ProviderError` instead of `RETRYABLE_PROVIDER_FAILURES` | Caught, `9 failed, 28 passed`: evaluate access-denied, request-rejected and unclassified, t32's two report cases, and t32's four refused/unclassified `test_output.py` cases |
| `retry_after_seconds` dropped from report's details | the two lines in `ModelStageInterrupted.__init__` that set it deleted | Caught, `3 failed, 34 passed`: report and evaluate throttled-with-a-wait at their key-set assertions, and the core test. The core test reads the attribute directly, so its failure is an `AttributeError` at the assertion line; the two CLI tests are the catches proper. |
| The key emitted for a non-rate-limit cause | `self.retry_after_seconds = getattr(cause, "retry_after_seconds", None)`, unconditionally | Caught, `13 failed, 24 passed`: every stop whose cause has no wait (report and evaluate, at their key-set assertions), and all six of t32's `test_output.py` exact-`details` cases |

### `--json` before and after, one throttled stop of each command

Both captured from the CLI over the test world: the scripted router for `report`, the stub evaluation for
`evaluate`, with the cause `ProviderRateLimited(..., retry_after_seconds=12.5)`. "Before" is `a698308`, whose
behaviour is the start commit's.

`landscape report`, exit `3` both times. The only change is one key added at the end of `details`:

```json
"details": {"error": "ProviderRateLimited", "cause_code": "PROVIDER_RATE_LIMITED", "sent": 1, "unanswered": 1}
"details": {"error": "ProviderRateLimited", "cause_code": "PROVIDER_RATE_LIMITED", "sent": 1, "unanswered": 1, "retry_after_seconds": 12.5}
```

`landscape evaluate` with the 12 answered cards meeting the bar. Before: **exit 0**, `"status": "ok"`, `"error": null`,
and the summary in `data` (`caselist` … `"interrupted": "ProviderRateLimited"`, `scan`). After: exit `3`:

```json
{"schema_version": 1, "status": "error", "command": "landscape evaluate", "data": null, "error": {"code": "MODEL_STAGE_INTERRUPTED", "message": "the model stage stopped on ProviderRateLimited after 12 card(s), with 18 not asked, so the evaluation is incomplete and was not measured against the bar", "exit_code": 3, "details": {"caselist": "synthetic26", "...": "every summary key, unchanged", "interrupted": "ProviderRateLimited", "scan": {"...": "..."}, "error": "ProviderRateLimited", "cause_code": "PROVIDER_RATE_LIMITED", "sent": 12, "unanswered": 18, "retry_after_seconds": 12.5}, "hint": null}}
```

The same evaluation stopped under the bar (the case the PM's brief describes) was already a failure
envelope: exit `1`, `"code": "EVALUATION_BELOW_BAR"`, `details` exactly the summary's 22 keys. After the
change it exits `3`, the code is `MODEL_STAGE_INTERRUPTED`, and `details` holds the same 22 keys plus `error`,
`cause_code`, `sent`, `unanswered` and, when given, `retry_after_seconds`. No key is removed or renamed in
either command. `test_evaluate_stopped_by_a_retryable_cause_exits_3_with_the_causes_code` pins the
evaluate key set exactly, against a list written out by hand from `evaluation_summary`. The values that
changed are the evaluate `error.code` and `exit_code` (Decision 1).

### Checks before the report

* Affected set: `uv run scripts/affected_tests.py` chose `210 of 597 test files (35.2%) ... from 8 changed
  files`. `landscape_model_stage.py` is imported by `exit_codes.py`, so the set reaches most of the CLI
  suite, as t32's did (206). I ran it once as CI's `--run` does,
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" $(cat affected.txt)`.
  The run was stopped at its 115-second limit (exit 124) about 4% in, with no failure printed. Under
  agreement 10 the set is left to the pull request's `ci` check, which runs the same set.
* Within two minutes instead, I ran the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`,
  `test_help_rendering.py`, `test_container_factories.py`) and every test file that names a changed module
  or class (`git grep` for `landscape_model_stage`, `landscape_model_evaluation`, `ModelStageInterrupted`,
  `FormatEvaluation`, the landscape command). That is `test_landscape_command.py`, `test_output.py` and
  `test_position_classification.py`, plus `test_recorded_failure_codes.py`, every
  `debate_core/tests/application/test_landscape_*.py`, `tests/smoke/*landscape*` and `tests/docs` (22 paths,
  each checked with `ls -d`): `1058 passed in 64.45s`.
* `ruff format --check packages/debate_cli packages/debate_core` → `927 files already formatted`; `ruff check` →
  `All checks passed!`; `pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
* `uv run lint-imports` → `Contracts: 19 kept, 0 broken.`; `scripts/check_thin_handlers.py` → `OK: 68 CLI command
  and API route handlers within 25 statements`.
* Docs: `scripts/check_command_blocks.py` → `OK: no # comments in 609 shell code blocks in 200 Markdown files`;
  `scripts/check_links.py` → `OK: 3105 relative links and anchors in 483 Markdown files`;
  `docs_index.py --check-descriptions` → `All 60 indexed documents under docs/ have a description`.
* `uv run scripts/validate_specs.py` → `OK: 530 files, 41 epics, 467 tasks, 22 releases`.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_model_evaluation.py`: `FormatEvaluation` keeps
  `interrupted_by` (the error) and `unanswered`, as t32's stage outcome does. `interrupted` is now a property
  naming the error's class, and `stopped` builds the `ModelStageInterrupted` for the stop.
  `evaluate_labelled_cards` fills both new fields.
* `packages/debate_core/src/debate_core/application/landscape_model_stage.py`: `ModelStageInterrupted` sets
  `retry_after_seconds` when its cause is a `ProviderRateLimited` that states one.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: `evaluate` never passes a stopped stage.
  `_evaluation_failure` decides in order: the scan, then the stop (through `CommandFailure.from_exception`),
  then the bar. The module docstring's exit codes for both commands are updated.
* `docs/runbooks/landscape-report-from-the-cloud-run.md`: step 4's paragraph. It says to wait
  `retry_after_seconds` on exit 3 when the envelope gives one, then run the same block again, and it gives
  evaluate's exit codes. The blocks, `--config-dir "$CFG"` and the run-from-the-checkout wording are untouched.
* Tests: `packages/debate_cli/tests/test_landscape_command.py` gets a report case in t32's section and a new
  v1-e32-t33 evaluate section. `packages/debate_core/tests/application/test_landscape_model_stage.py` gets
  two evaluation cases.

`exit_codes.py` is not changed: the rule is t32's as it stands.

## Deviations from the spec

None.

## Decisions and assumptions

1. **Which code path decides each exit.**
   * A throttled or unanswered `evaluate`: `_evaluation_failure`'s stop branch →
     `CommandFailure.from_exception(result.stopped)` → `exit_code_for`'s `ModelStageInterrupted` branch, the
     one t32 added → `3`.
   * A refused or unclassified `evaluate`: the same call. That branch does not match, so the `DomainError`
     line → `1`.
   * A completed `evaluate` under the bar: `_evaluation_failure`'s last branch, `EVALUATION_BELOW_BAR` with
     `ExitCode.DOMAIN_FAILURE`, as before.
   * A name either scan found: `_evaluation_failure`'s first branch, as before, whether or not the stage
     also stopped.
   * `report` is unchanged: `DebateResearchGroup` → `from_exception` → `exit_code_for`.
   * `retry_after_seconds`: set in `ModelStageInterrupted.__init__` and picked up by `_details_of` (the
     exception's scalar attributes), so one place serves both commands.

   The evaluate command reuses t32's exception and helper and copies neither. The one value that changes
   is evaluate's `error.code` for a stopped stage: `MODEL_STAGE_INTERRUPTED`, where it was
   `EVALUATION_BELOW_BAR`, or no error at all. `EVALUATION_BELOW_BAR` on an exit 3 would again say "the
   landscape is not good enough" about a run that was never measured, and a script that branches on the
   code would read the throttle as a verdict, the confusion this task is meant to remove. No key is
   renamed or removed.
2. **A stopped evaluation never passes.** Before this task, `passed` read only the accuracy and the scans.
   A stop whose answered cards met the bar exited `0`, the refused stops included (the red run). A score
   over part of the labelled cards is not the format's score, so `passed` now also needs `stopped is None`.
   This makes the PM's "a refused cause still exits 1" true, where before it held only below the bar.
3. **The scan decides before the stop.** A name in the prompt inputs or the cassettes is a finding that
   no retry removes, and a script that retried on `3` would only repeat it. Pinned by
   `test_evaluate_throttled_with_a_name_in_a_cassette_exits_1_for_the_scan`.
4. **`retry_after_seconds` is left out, not null, when there is no wait.** A bare `ProviderRateLimited`'s
   envelope does carry `retry_after_seconds: null`, because `_details_of` copies every scalar attribute
   and that error always has the attribute. A stop is not that error. Its cause may be a
   `ModelUnavailableError`, which has no idea of a wait, and the runbook's rule reads simplest as "if the
   key is there, wait that long". So `ModelStageInterrupted` has the attribute only when there is a
   number to quote.
5. **Evaluate's `error.details` is its summary plus the stop's own details** (`error`, `cause_code`, `sent`,
   `unanswered`, `retry_after_seconds`), taken whole from `from_exception` rather than chosen by hand. A
   stopped stage then reports the same keys under both commands, and the runbook describes them once.
   `error` repeats `interrupted` and `sent` repeats `asked`; both are additive. The message is evaluate's
   own, because the run's message says the cache and the review queue hold the answered cards, which an
   evaluation does not write.
6. **Bedrock states no wait today.** `bedrock/failures.py` builds `ProviderRateLimited(PROVIDER, ...)` without
   `retry_after_seconds`, so a real throttle of either command will not carry the key. The tests use a
   rate limit that states one, as the search and fetch providers' do. The runbook says the key is usually
   absent.
7. **Only `record` can be stopped by a model.** Replay answers from cassettes. Record calls the delegate
   for every request, even one with a cassette (`record_replay.py`), so a rerun after exit 3 asks about
   every labelled card again. The module docstring says so. A rerun of `report` asks only about the cards
   not yet cached (t32).
8. Before measuring I fetched `origin/dev` and diffed this task's spec against it. The only difference is
   this branch's own phase.

## Operator follow-ups

None. The affected set (210 files, several minutes) runs in the pull request's `ci` check.

## Follow-up work

* **Bedrock's throttle carries no wait** (`v1-e05-model-router`). `_translate_response` never sets
  `retry_after_seconds`. Whether a Bedrock `ThrottlingException` response carries a `Retry-After` header at
  all is unmeasured. If it does, the adapter could pass it on, and the runbook's sentence would then have a
  number to quote. Measuring it needs a live call, so it is the operator's.
* **The runbook's publish block prints neither `cause_code` nor `retry_after_seconds`.** The sentence
  points at `/tmp/landscape-publish.json`. Adding both to the block's `python3 -I -c` line would put them
  on screen, but that rewrites a pasted block, which this task was asked not to do. The landscape runbook
  owner (`v1-e40-t17`) can decide.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

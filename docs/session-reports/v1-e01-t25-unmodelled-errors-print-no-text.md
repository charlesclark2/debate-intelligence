# Session report: v1-e01-t25-unmodelled-errors-print-no-text

| | |
|---|---|
| Task | `v1-e01-t25-unmodelled-errors-print-no-text` — An unexpected error never prints its message on the command line |
| Spec | [`plan_specs/v1/e01-repo-foundation/t25-unmodelled-errors-print-no-text.yaml`](../../plan_specs/v1/e01-repo-foundation/t25-unmodelled-errors-print-no-text.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t25-unmodelled-errors-print-no-text` |
| Session status | COMPLETE |

## Summary

An exception the CLI does not model still ends the run with exit 70. Its message no longer
appears in the default output or in the `--json` envelope.

* **What it prints instead.** The message names the class: "debate-research stopped on an
  unexpected PermissionError. Its message is not printed, because it can quote a path on this
  machine." The hint says to re-run with `--verbose`, and `--verbose` prints the traceback, message
  included, on stderr. That traceback is the only place the message appears.
* **Where the change is.** It is made once, in `CommandFailure.from_exception`. That is the one
  place the CLI reads a message off an exception, so it covers three outputs: the panel, the
  envelope, and the stderr line written when a command fails after its result was already sent.
* **What does not change.** Every `DomainError` and every usage error keeps its message and its
  exit code.
* **ac1 was shown failing first.** The probe test failed 6 of 11 on the pre-task handler and passes
  now. All 6 mutants were caught. The whole suite passes in four parts.
* **For the PM to look at first: the sweep.** `caselist pull`'s run record, run details and
  notifications already carried only the class, so nothing there changed. The agent's stdout log
  did carry the message: on an exit 70 it holds the root handler's envelope. This change fixes that.
  Four other routes outside the generic handler still echo an `OSError`'s text, and are filed as
  Follow-up work 1 to 3.
* **The launchd agent does not run with `--verbose`.** Its logs never held a traceback, and from
  this build on they hold no message either.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `generic-handler`: The generic handler prints the class, not the message | Done | Probe test first (`ccdb62d`, red). Then the handler (`8edccc2`, green). Then the README and runbook (`cd18c70`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an unmodelled exception whose message holds a probe (a path and a title) produces output and a JSON envelope without it, shown failing first, and still exits 70 naming the class | **PASS** | **Red**, on `ccdb62d` with the pre-task handler: `uv run --frozen pytest packages/debate_cli/tests/test_unmodelled_error_prints_no_text.py -q -p no:randomly -n0` → `6 failed, 5 passed in 2.46s` (output below).<br>**Green**, on `8edccc2`: the same file, 11 passed.<br>The tests cover two probes, a `PermissionError` quoting a path and a `RuntimeError` quoting a path and a title. Each runs with and without `--json`, and once more after a result was already sent. In every case the probe is absent from stdout, stderr and the envelope. Exit is 70, `error.code` is `INTERNAL_ERROR`, the class is in the message and in `details.exception_type`, and `--verbose` is in the hint. |
| ac2: `--verbose` still shows the traceback with the message, and a modelled `DomainError` still prints its own message, both by test | **PASS** | Same file, green:<br>`test_verbose_prints_the_traceback_with_the_message[panel\|envelope]`: stderr holds `Traceback (most recent call last)` and `PermissionError: [Errno 13] Permission denied: '<probe path>'`.<br>`test_verbose_keeps_the_message_out_of_the_envelope`: with `--verbose --json`, stdout still has no probe.<br>`test_a_domain_error_still_prints_its_own_message`: `NotFound` → exit 1, message `Card not found: 01JZQXPROBE`.<br>`test_a_domain_error_that_names_a_file_keeps_its_sentence`: a `ConfigurationError` naming a file keeps it, exit 1.<br>`test_a_retryable_store_failure_still_exits_three_with_its_message`: `StoreUnavailable` → 3, message kept.<br>`test_app.py::test_the_traceback_of_a_bug_needs_verbose` now asserts the message is in the verbose run's traceback and absent without the flag. |
| ac3: the CLI README's exit-code section says what exit 70 prints and how to get the detail | **PASS** | `packages/debate_cli/README.md`, "Exit codes":<br>* the 70 row says it is reported by its class;<br>* a new paragraph, "Exit 70 names the exception's class, never its message", gives the envelope and the `--verbose` re-run;<br>* it says the scheduled agent runs without `--verbose`, and which errors keep their messages.<br>`uv run --frozen scripts/check_command_blocks.py --base origin/dev` → `OK: no '#' comments in 249 shell code blocks in 114 Markdown files`. |
| Node `generic-handler`: CLI tests pass (`uv run pytest packages/debate_cli/tests`) | **PASS** | `uv run --frozen pytest packages/debate_cli/tests -q` → `595 passed in 39.92s`. |

**The red run** (`ccdb62d`, before the handler changed), with each failure's assertion:

```text
FFFFF..F...                                                              [100%]
test_the_envelope_names_the_class_and_not_the_message[an OSError quoting its path]
E       assert 'PermissionError' in "[Errno 13] Permission denied: '/Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip'"
test_the_envelope_names_the_class_and_not_the_message[a bug quoting a path and a title]
E       assert 'RuntimeError' in "could not file 'Zqxprobe Lantern Camp Release' at /Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip"
test_the_panel_names_the_class_and_not_the_message[both probes]
E         │ [Errno 13] Permission denied: '/Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip' │
test_a_failure_after_the_result_names_only_the_class
E       assert 'PermissionError' in "INTERNAL_ERROR: [Errno 13] Permission denied: '/Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip' (after the result was already emitted)\n"
test_verbose_keeps_the_message_out_of_the_envelope
E       AssertionError: {"schema_version": 1, "status": "error", "command": "file", "data": null, "error": {"code": "INTERNAL_ERROR", "message": "[Errno 13] Permission denied: '/Users/zqxprobe-home/debate-data/inbox/openev-901-Zqxprobe_Lantern_Camp_Release.zip'", ...
6 failed, 5 passed in 2.46s
```

The five that passed on the old code are the `--verbose` and modelled-error tests (ac2). They pin
behaviour this task keeps.

**The same probe now** (`8edccc2`):

```text
$ debate-research --json file -> 70
{"schema_version": 1, "status": "error", "command": "file", "data": null, "error": {"code": "INTERNAL_ERROR", "message": "debate-research stopped on an unexpected PermissionError. Its message is not printed, because it can quote a path on this machine.", "exit_code": 70, "details": {"exception_type": "PermissionError"}, "hint": "This is a bug in debate-research. Re-run with --verbose for the traceback, which includes the error's message."}}

$ debate-research file -> 70
╭─ INTERNAL_ERROR ───────────────────────────────────────────────────────────────────────────────────────────╮
│ debate-research stopped on an unexpected PermissionError. Its message is not printed, because it can quote │
│ a path on this machine.                                                                                    │
│ exception_type: PermissionError                                                                            │
│                                                                                                            │
│ This is a bug in debate-research. Re-run with --verbose for the traceback, which includes the error's      │
│ message.                                                                                                   │
╰────────────────────────────────────────────────────────────────────────────────────────────────── exit 70 ─╯
```

The probe is invented: `zqxprobe` is in its path and its title, and in nothing this project writes.
Its absence is checked with everything except letters and digits removed from the output, so a
panel border or a line wrap cannot split it and pass by accident.

### Mutation run

Each mutant was applied by a script (in the session's scratchpad, not committed) to the committed
source at `cd18c70`. The run was then
`uv run --frozen pytest packages/debate_cli/tests/test_unmodelled_error_prints_no_text.py packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_output.py -q -n0 -p no:randomly`.
The source was restored with `git checkout -- packages/debate_cli/src` after each run, and
`git status --porcelain` printed 0 changed paths after every restore.

Every run had its own new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (0 entries, counted before the run).
None of the three files uses Hypothesis, so no catch below is a replay.

| Mutant | Caught by | Result |
|---|---|---|
| The message put back (`str(exception)`) | All 6 probe tests, `test_the_traceback_of_a_bug_needs_verbose`, `test_an_unmodelled_exception_is_an_internal_error` | `8 failed, 108 passed` |
| The class left out of the message | Both envelope tests, the after-the-result test, the `from_exception` unit test | `4 failed, 112 passed` |
| No `--verbose` hint (the hint left `None`) | Both envelope and both panel tests, `test_an_unmodelled_exception_exits_seventy`, the hint unit test | `6 failed, 110 passed` |
| `DomainError` withheld too (only usage errors keep their message) | The three modelled-error tests, `test_a_profile_that_is_not_configured_is_reported_under_its_own_code_with_exit_one` | `4 failed, 112 passed` |
| The traceback printed without `--verbose` (`detail` → `note`) | Both envelope and both panel tests, the after-the-result test, `test_the_traceback_of_a_bug_needs_verbose` | `6 failed, 110 passed` |
| The traceback never printed | Both `--verbose` traceback tests, `test_the_traceback_of_a_bug_needs_verbose` | `3 failed, 113 passed` |

A first attempt at this loop stopped after the first mutant: zsh read a `====` separator as a
command. That mutant's result was the same `8 failed` and the tree was restored. All six were then
run again in one loop, and the table is that run.

### Other checks

The load average was 11.80 before the first test run. Other sessions on the Mac pushed it to 57.20
during the mutation run, and it was 25.07, 25.36, 23.98 and 26.36 at the start of parts 1 to 4. Each
part ran under `perl -e 'alarm 170; exec @ARGV'`.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1685 passed in 82.36s` |
| `… --part 2/4` | `1693 passed, 1 xfailed in 68.14s` |
| `… --part 3/4` | `1696 passed, 1 skipped, 1 warning in 69.08s` |
| `… --part 4/4` | `1693 passed, 1 xfailed in 62.43s` |
| `uv run --frozen ruff format --check .` | `657 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run --frozen scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 249 shell code blocks in 114 Markdown files` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 347 files, 38 epics, 289 tasks, 20 releases` |

## The sweep: where an unmodelled exception's text can reach output

To build this list I read:

* in `debate_cli`: `app.py`, `output.py`, `exit_codes.py`, `installation.py` and every `except` in
  `commands/`;
* in `caselist pull`: the exception handling of `caselist_sync.py`, and `sync_runs.py` (record,
  details, notifications, redaction);
* every broad catch in `debate_core/application` (`except Exception`, `except OSError as`,
  `except (DomainError, OSError) as`), traced to the CLI output that shows it.

**Fixed here: the generic handler and what it feeds**

| # | Route | Before | After |
|---|---|---|---|
| 1 | The panel on stderr (default output) | `str(exception)` as the panel's body | The class and the fixed sentence; the hint points at `--verbose` |
| 2 | The `--json` envelope's `error.message` | `str(exception)` | The same sentence; `details` is `{"exception_type": <class>}` as before |
| 3 | A failure after a result was already sent (`CliOutput.failure`, the stderr line in `--json` mode) | `INTERNAL_ERROR: <message> (after the result was already emitted)` | The same line with the sentence |
| 4 | A `hint` attribute on an unmodelled exception, which `from_exception` used to promote | Printed as the hint | Not used; the `--verbose` hint is given |
| 5 | The agent's stdout log, `caselist-sync.jsonl` | On an exit 70, the envelope of row 2, message included | Row 2's envelope |

**Already clean in `caselist pull`, so unchanged.** No record field changed.

| Output | What it carries for an unmodelled exception |
|---|---|
| Run record, for a run that raised (`record_for_failure`) | `error_class` only. `error_message` is `None` for anything that is not a `DomainError` (`_error_message`). |
| Run details, for a run that raised (`details_for_failure`) | `failure_codes: ["INTERNAL_ERROR"]`. `fix_for` gives no hint for such an error, so `hint` is `null`. |
| Notification (`notifications_for`) | "Run … stopped with `<class>`." It is built from the record's class and the details' codes and hint, never from a message. |
| A stage that fails on one (`_failure`, `_camp_failure`, retention's per-file failures) | The class, never the message (`v1-e34-t12`, `v1-e34-t13`). That reason then goes through `redact` into the record. |
| The bucket's copy of the record and details | The same objects. |

**Not the generic handler: filed as follow-ups, nothing changed**

| # | Route | What reaches output | Where it shows |
|---|---|---|---|
| A | `store sync --apply`: `evidence_sync.py:862`, `error_message=str(failure)` for an `OSError` | The `OSError`'s text, path included | `--json` envelope, `data.failed[].message`. The table does not show it. |
| B | `caselist publish`: `publish_service.py:410`, `manifest_error = str(failure)`, and `:469`, a source's `str(failure)` | The same | `--json` envelope, `data.snapshots[].manifest_error` and `failed[].message` |
| C | `caselist remove`: `RemovalIncomplete` and `RemovalCompletedUnlogged` (`DomainError`s) put `{failure}` and `{unlogged}` into their own message. Either can be an `OSError`. | The `OSError`'s text, inside a modelled message | Panel and envelope. The removal log records only `error_code`. |
| D | Settings and routing: `settings.py:1285, 1312` and `routing_config.py:151` raise `ConfigurationError` / `RoutingConfigError` with `could not read {path}: {error}` | The profile's path and the `OSError`'s text, inside a modelled message | Panel and envelope |

* `caselist parse --publish` puts `str(failure)` in `ParsedObjectOutcome.error_message`
  (`parsed_publish.py:232`). Nothing renders that field today, so it is not a route. It is listed
  under Follow-up work 1 so it is fixed together with A and B before something renders it.
* A, B and D are text the CLI prints as written. C and D are modelled messages, which the PM's
  rule 1 keeps. None of the four reaches a run record or a notification, so the instruction to fix
  only what is the same generic handler leaves them all as follow-ups.

**The launchd agent.** `ops/launchd/run-caselist-sync.sh` ends in
`exec "${DEBATE_RESEARCH_BIN}" --json caselist pull "$@"`. The plist's `ProgramArguments` passes
only `--caselist <slug>` pairs (`install.sh`'s `@CASELIST_ARGUMENTS@` block). So the agent never
runs with `--verbose`, and `caselist-sync.err.log` has never held a traceback: `CliOutput.detail`
prints nothing without the flag.

Before this change, an exit 70 put the message in `caselist-sync.jsonl` through the envelope (row
5). From a build with this change, neither log holds it. The class is in `error.details.exception_type`.
The traceback can only be had by running the command by hand with `--verbose`. The agent's
invocation was not changed.

## Files changed

* `packages/debate_cli/src/debate_cli/output.py`:
  * `CommandFailure.from_exception` names an exception that is neither a `DomainError` nor a usage
    error by its class;
  * new `UNMODELLED_ERROR_HINT`;
  * the docstring says why.
* `packages/debate_cli/src/debate_cli/app.py`: the generic handler no longer passes its own hint,
  and a comment points at the rule. The traceback is still `output.detail`, so it prints only with
  `--verbose`.
* `packages/debate_cli/tests/test_unmodelled_error_prints_no_text.py` (new): the probe tests, 11
  in all.
* `packages/debate_cli/tests/test_app.py`: `test_the_traceback_of_a_bug_needs_verbose` asserted the
  message *was* in the default output. It now asserts that it is not, and that it is in the verbose
  traceback.
* `packages/debate_cli/tests/test_output.py`: `test_an_unmodelled_exception_is_an_internal_error`
  asserted `message == "off by one"` and now asserts the class. A new test checks that an
  unmodelled exception's own `hint` attribute is not used.
* `packages/debate_cli/README.md`: the exit-code section (ac3).
* `docs/runbooks/caselist-scheduled-sync.md`:
  * the exit-70 row of "What the exit code says" now says to report the class, and warns that a
    `--verbose` traceback can quote a path and a camp file's title, so it is not pasted as it is;
  * the pasting paragraph says an exit-70 line written before this change may quote a path.
* `plan_specs/v1/e01-repo-foundation/t25-unmodelled-errors-print-no-text.yaml`: Goal phase
  `Succeeded`.

## Deviations from the spec

None. The runbook edit is inside `docs`, which is in the task's packages. It follows from ac1:
before this change, the runbook's "can be pasted into an issue as they are" was untrue for an
exit-70 line.

## Decisions and assumptions

1. **The rule lives in `from_exception`, not only in the handler's `except` branch.** It is the one
   place a message is read off an exception, so the after-the-result line (sweep row 3) is covered
   without a second change. The branch is chosen by type: anything that is not a `DomainError` or a
   `typer.TyperException`. Those two are exactly what keeps its message, so the "Only the generic
   fallback changes" rule holds, and mutant 4 shows the boundary is tested.
2. **The class is `type(exception).__name__`**, the same name the run record's `error_class` and
   the envelope's `details.exception_type` already use. It is not module-qualified.
3. **This project's own non-`DomainError` exceptions lose their message by default too.** These are
   `SettingsNotConfigured`, `UnfollowableWiring`, and a `doctor` pin it cannot read. They are bugs
   by design (exit 70, tested in `test_doctor.py` and `test_app.py`). Their message is in the
   `--verbose` traceback, and the existing tests assert only the code and the "bug" hint, which are
   unchanged.
4. **The incomplete-installation report is unchanged.** It is exit 70 with its own message and fix
   (`v1-e01-t17`) and quotes nothing from the exception.
5. **The probe test uses `COLUMNS=200`.** Rich then does not wrap the probe path, so a probe that
   is present is found whole. Its absence is checked on letters and digits only, which no wrap can
   defeat.
6. **The README's example re-run is `caselist pull --dry-run`.** It needs no real slug. The runbook
   already offers "the same command by hand now" after a failed run.

## Operator follow-ups

None required. Nothing here needs credentials, and every command above finished well under two
minutes.

For information, about the agent being reinstalled today:

* A build with this change prints only the class on an exit 70.
* The installed build keeps printing the message until a build that contains this change is
  installed. Installing such a build is the usual step in `docs/runbooks/caselist-scheduled-sync.md`.
* Your data directory, AWS config, installed agent and its logs were not touched, and no AWS call
  was made.

## Follow-up work

1. **`store sync --apply` and `caselist publish` print an `OSError`'s text in `--json` `data`.**
   These are sweep rows A and B. A per-object failure's `message` and a manifest's `manifest_error`
   are `str(failure)`, path included. The same fix belongs on `ParsedObjectOutcome.error_message`,
   which nothing renders yet. The fix is the class name for a non-`DomainError`, as `_failure` does
   in `caselist_sync`. It belongs to the services in `debate_core.application` (`evidence_sync`,
   `caselist.publish_service`, `caselist.parsed_publish`), outside this task's packages. (E29 for
   `store sync`, E34 for the caselist publishes.)
2. **`RemovalIncomplete` and `RemovalCompletedUnlogged` put the stopping error's text into their
   own message** (sweep row C). When that error is an `OSError`, a path reaches the panel and the
   envelope through a modelled message. The removal log is clean: it records only `error_code`.
   (E34, removal.)
3. **Configuration errors quote the profile path and the `OSError`'s text** (sweep row D):
   `could not read {path}: {error}` in `settings.py` and `routing_config.py`. These are modelled
   messages that name the file the operator has to fix, so they may be right as they are. In an
   installed build, though, the path is under the home directory. This is for the PM to decide.
   (E01 or E02, settings.)

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

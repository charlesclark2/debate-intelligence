# Session report: v1-e40-t26-parses-owed-smoke-check

| | |
|---|---|
| Task | `v1-e40-t26-parses-owed-smoke-check` — A smoke check reads parses_owed from caselist runs and caselist status |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t26-parses-owed-smoke-check.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t26-parses-owed-smoke-check.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t26-parses-owed-smoke-check` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`tests/smoke/test_caselist_parses_owed.py` is the smoke check `v1-e40-t08` left owed. It has three
checks, in the recorded tier, on the S3 stand-in, with no network:

* **A parse-owed file in the data directory.** Two weeks published and not parsed, plus a full parse
  under `2026.10.27-docx-7`, are given whole as `parses_owed` in `caselist runs --json` and
  `caselist status --json`, and both captions carry the hand-written sentence.
* **The same file in the bucket.** `caselist runs --remote` gives it, which is Thursday's read of
  Wednesday's run. `caselist runs` without `--remote` says nothing is owed.
* **No file.** Both commands, and `--remote`, give the key with two empty lists, and no caption says a
  parse is owed. The same holds when the bucket holds the empty object a run saves for a removed file.

The file is written by t08's own writer, `ParseOwed.owe`, at `PARSE_OWED_FILENAME`, and the check
asserts that name is `caselist-sync-parse-owed.json`. The check passes on the checkout's script and on
an offline stamped and installed build. Ten mutants each failed it at an assertion: the PM's four
(split into seven), the file's name, and `--remote` reading this machine's file. Mutants 1 and 2 also
failed it on the installed build. Nothing outside `tests/smoke` changed. The affected set (57 files) ran past two minutes and was stopped at about 92% with nothing failed, so it is left to the pull request's `ci` check (working agreement 10).

**Please look at first:** `caselist status` refuses a store with no manifest on either side
(`NO_CASELIST_EVIDENCE`, exit 1). So the data-directory and nothing-owed checks first import and
publish two synthetic weeks, which takes about 4 s each
([Decisions](#decisions-and-assumptions)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parses-owed-smoke-check` — Parses-owed smoke | Done | The check, then its README row, then mutants on the checkout's script, then a stamped installed build, green and with mutants 1 and 2 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the check passes on the checkout's script and an installed build | PASS | Checkout's script: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/smoke -k parses_owed` → `3 passed in 10.33s`. Installed build (below): the same selection with `-m "not live and not in_process"` and `DEBATE_SMOKE_BIN` naming it → `3 passed in 11.47s`, and again after the mutant wheels were replaced → `3 passed in 10.65s` |
| ac1 — it fails against a break that drops `parses_owed` from either command's `--json` | PASS | Mutant 1 (`caselist runs`): 3 of 3 fail at `AssertionError: caselist runs --json gives no parses_owed`, on the checkout's script and on the installed build. Mutant 2 (`caselist status`): 2 of 3 fail at `AssertionError: caselist status --json gives no parses_owed`, on both. The bucket check does not run `status`. [Mutants](#mutants) has the rest |
| Node `parses-owed-smoke-check`: `uv run pytest tests/smoke -k parses_owed` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/smoke -k parses_owed`, the same selection without uv's sync, under the 115 s limit → `3 passed in 10.33s` |
| Forbidden: network or AWS access in any test | PASS | The checks use only `s3_stand_in`, moto on loopback, and are not marked `live`. The network guard's log fails a check if the build reaches anything else, and none failed. No AWS call was made. The installed build came from wheels built with `--offline` |

### The installed build

The installed build was HEAD at `da759b5`. It was built offline in the scratchpad, outside the
checkout, so the harness accepts it:

1. `git archive HEAD`, then `scripts/stamp_build.py stamp --version 0.0.1.dev26 --tag v0.0.1-dev.26
   --channel dev`.
2. `uv build --offline` for `debate-core` and for `debate-cli`.
3. A new uv venv on the managed CPython 3.12 with the two wheels installed `--no-deps`. A `.pth`
   holds one plain path, the worktree venv's `site-packages`, for third-party packages only.

In that venv, `debate_core.__file__` and `debate_cli.__file__` were in its own `site-packages`, and
no `packages/*/src` path was on `sys.path`. With `DEBATE_ENV` unset,
`debate-research --version --json` reported channel `dev`, commit `da759b5…` and tag
`v0.0.1-dev.26`. The harness checked the same through `DEBATE_SMOKE_EXPECT_SHA` and
`DEBATE_SMOKE_EXPECT_TAG`. For mutants 1 and 2, only the `debate-cli` wheel was rebuilt with the
change and reinstalled with `--reinstall`. A `grep` of the installed module confirmed each change, the
check was run, and the source was restored. The clean wheel was then rebuilt, its source
`diff -r` matched the worktree's, and the check ran green again.

### Mutants

Mutants were applied to the committed source one at a time by a scratch driver. Each was run against
`tests/smoke/test_caselist_parses_owed.py` (`-n 0 -p no:randomly --tb=line`) on the checkout's
script, whose package is the editable worktree source. Each run had a new empty
`HYPOTHESIS_STORAGE_DIRECTORY`, although the check uses no Hypothesis. Each mutant was restored with
`git checkout HEAD --`, and `git status --porcelain` was empty after every batch. "Caught" means a named
check failed at one of its own assertions.

| Mutant | Where | Result |
|---|---|---|
| (1) `parses_owed` dropped from `caselist runs --json` | `commands/caselist_runs.py` | Caught, 3 of 3: `caselist runs --json gives no parses_owed`. Also caught on the installed build |
| (2) `parses_owed` dropped from `caselist status --json` | `commands/caselist.py` | Caught, 2 of 3: `caselist status --json gives no parses_owed`. Also caught on the installed build |
| (3a) The caption sentence removed from both commands (`parses_owed()` returns no sentence) | `parses_owed.py` | Caught, 2 of 3: the data-directory sentence `not in` the `runs` table, and the bucket's sentence `not in` the `runs --remote` table |
| (3b) The sentence left off `caselist runs`'s caption | `commands/caselist_runs.py` | Caught, 2 of 3, as 3a |
| (3c) The sentence left off `caselist status`'s caption | `commands/caselist.py` | Caught, 1 of 3: the sentence `not in` the `status` table |
| (4a) An empty state captioned as owed (`parses_owed_sentence` says `Parse owed: none.`) | `caselist_sync.py` | Caught, 2 of 3: `'parse owed' not in …` for `caselist runs` |
| (4b) The bucket's empty object, a removed file, read as a file (no zero-size branch) | `caselist/run_state.py` | Caught, 1 of 3: `None == {'full_parses': [], 'snapshots': []}` |
| (4c) Nothing owed given as `null` | `parses_owed.py` | Caught, 2 of 3: `this machine owes nothing`, and the empty data directory's `caselist runs` |
| (5) The file renamed (`caselist-sync-parses-owed.json`) | `caselist_sync.py` | Caught, 2 of 3: the name assertion in `owed_file` |
| (6) `--remote` reading this machine's file, not the bucket's | `commands/caselist_runs.py` | Caught, 1 of 3: the bucket check's `parses_owed` comparison |

**The first version failed to catch two mutants cleanly, and was fixed.** In the first run
(`89662b9`), mutants 1 and 2 failed with `KeyError: 'parses_owed'` at the dictionary lookup, which is
a crash, not an assertion failure. `da759b5` added `parses_owed_in()`, which asserts that the key is
present before reading it. Every mutant above was run against `da759b5`.

### What was run

| Run | Result |
|---|---|
| The new file, checkout's script (`-n 0 -p no:randomly`) | `3 passed in 14.14s` |
| Neighbours: `test_caselist_runs.py`, `test_caselist_publish_smoke.py`, `test_smoke_harness.py` and the new file, `-m "not live"` | `20 passed, 1 warning in 13.15s`. The warning is `test_smoke_harness.py`'s own deliberate `getaddrinfo` probe |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | It chose 57 of 613 test files (9.3%) from 4 changed files: 2,558 tests on 11 workers. The 115 s limit stopped it at about 92% (33 full progress lines), with no failure, error or skip up to then, and no pytest process left over. The run takes more than two minutes, so under working agreement 10 the full affected set is left to the pull request's `ci` check, which runs the same selection. Within the limit: |
| The always-run list: `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` (`-n auto -m "not slow and not live"`) | `369 passed in 19.31s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1700 files already formatted` / `All checks passed!` |
| `.venv/bin/pyright tests/smoke/test_caselist_parses_owed.py` | `0 errors, 0 warnings, 0 informations`. No package changed, so no package to run it on |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 539 files, 41 epics, 476 tasks, 22 releases` |
| `scripts/check_command_blocks.py --base origin/dev`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | `OK: no '#' comments in 626 shell code blocks in 204 Markdown files` / `OK: 3170 relative links and anchors in 495 Markdown files` / `All 61 indexed documents under docs/ have a description` |

## Files changed

* **`tests/smoke/test_caselist_parses_owed.py`** (new): the three checks.
* **`tests/smoke/README.md`**: a row in "The checks" for the new file.
* **This report, and the spec's Goal phase**, set to `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

* **Two synthetic weeks are imported and published before `status` is read.** `caselist status`
  refuses a store with no manifest on either side (`NO_CASELIST_EVIDENCE`, exit 1), so a data
  directory holding only the parse-owed file cannot be read by it. The fixture imports the first two
  weeks from `tests/fixtures/caselist/`, the same archives `test_caselist_publish_smoke.py` imports,
  and publishes them, so `status` reports agreement and exits 0. The owed snapshots are those same
  two weeks: published and not yet parsed, which is what t08's entries mean. The nothing-owed check
  also shows that `caselist publish` owes no parse. Only a pull's publish stage does.
* **The file is written by t08's own writer, and its name and key are asserted.** `ParseOwed.owe`
  writes it. The data-directory file is at `PARSE_OWED_FILENAME`, which `owed_file` asserts equals
  `caselist-sync-parse-owed.json`. The bucket's copy is the writer's bytes, put at
  `reports/sync/state/caselist-sync-parse-owed.json`. That key is written out in the test because it
  is the contract with the cloud run. A change to the shape changes what the writer writes, and the
  hand-written `--json` expectation then fails.
* **What the commands print is written by hand** (working agreement 6): both `parses_owed` objects
  and both sentences, taken from t08's code and report (`parses_owed_sentence`, and
  `test_nothing_owed_is_said_as_nothing`, which pins two empty lists, not an absent key).
* **The bucket's empty object is written by hand.** `RunState` saves a removed state file as an
  empty object (`run_state.py`, "an empty object when it is gone"). Making one through a run's save
  would need a whole bucket-mode run, so the check puts `b""` at the key. Mutant 4b shows that this
  step is what tests the zero-size branch.
* **`--remote` is checked as well as the two commands.** Thursday's read of the cloud run is
  `caselist runs --remote`, and the bucket check is the one that catches mutant 6.
* **"No parse owed" is checked as `'parse owed' not in` the lower-cased table.** That covers both of
  t08's sentences ("Parse owed: …" and "Full parse owed …") and nothing else those tables print.

## Operator follow-ups

None.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

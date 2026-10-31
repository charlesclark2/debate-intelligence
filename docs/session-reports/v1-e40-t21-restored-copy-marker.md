# Session report: v1-e40-t21-restored-copy-marker

| | |
|---|---|
| Task | `v1-e40-t21-restored-copy-marker` — A restored working copy carries a marker, so leftover copies are found exactly |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t21-restored-copy-marker.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t21-restored-copy-marker.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t21-restored-copy-marker` |
| Session status | COMPLETE |

## Summary

`caselist restore-run-state` now writes a marker, `debate-research-restored-copy.json`, at the root of
every copy it makes. The marker holds the environment, the bucket, the time of the restore and the
build's tag, and nothing else. It is the restore's first write: it goes into a scratch directory inside
the copy and is moved into place, so a restore that stops part-way leaves a whole marker beside what it
restored. A write that is itself interrupted leaves no marker. RESTORED_SOURCES_INCOMPLETE and
TOO_LITTLE_ROOM_FOR_SOURCES leave the marker. RUN_LOCK_HELD and RUN_STATE_NOT_SEEDED are refused by the
lock before the restore runs, so they leave no directory.

The annual purge's step 1 and the landscape runbook's last step now run the same two searches. The
first lists every directory holding the marker, at any depth under `$HOME` and `/tmp`. The second,
labelled **restored before the marker**, is the old three-level `debate.sqlite3` search, minus
directories that hold a marker. Both still prune `~/Library` and `~/.Trash`, and both still exclude
the dev and prod data directories. Tests run the runbooks' own commands, in bash and zsh, over a
synthetic home folder.

What to look at first: the new search walks the whole home folder. It took **59 s and 73 s** on the
operator's Mac (load average 8 to 12), so both runbook steps now say "about a minute" instead of
"seconds". The affected set was 209 test files because `container.py` changed, so it is left to the PR's
`ci` check (agreement 10). See [Checks run before the report](#checks-run-before-the-report).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `restored-copy-marker` (Restored copy marker) | Done | Red at `80960b1`, green at `9854ef9`, the whole-or-none test strengthened at `26d95b7` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a restored copy holds the marker, and the runbooks' leftover checks find a copy at any depth by it, by tests shown failing first | PASS | Red at `80960b1`: 27 failed, 3 passed ([Red run](#red-run)). Green: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_restored_copy_marker.py tests/docs/test_restored_copy_search.py packages/debate_cli/tests/bucket_mode/test_restore_run_state.py` → `62 passed in 27.01s`. Seven mutants, seven caught ([Mutants](#mutants)) |
| Node `restored-copy-marker`: Restored copy marker tests pass (`uv run pytest packages/debate_core/tests -k restore`) | PASS | Run at `26d95b7` as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests -k restore -q` (agreement 10 puts the alarm on the interpreter) → `41 passed in 12.88s` |

## Red run

The tests were written against a skeleton (`80960b1`). In it, `RunStateRestore` took the marker's
environment, bucket, build tag and clock but wrote no marker, and the runbooks still had the
single three-level search. The four new or changed tests in
`test_restore_run_state.py` were run by node id beside the two new files:

```
27 failed, 3 passed in 16.06s
```

Grouped failure reasons, from the two new files alone (`23 failed, 3 passed`):

| Reason | Count |
|---|---|
| `AssertionError: each search names the home folder and /tmp`: the runbook block holds one search, not two | 16 |
| `FileNotFoundError` on the marker: no marker in the copy | 3 |
| `assert [False] == [True]`: no marker when the restore began | 1 |
| `DID NOT RAISE KeyboardInterrupt`: no marker write to interrupt | 1 |
| the purge block is not the two searches, and does not name the marker | 2 |

The four CLI tests failed on their marker assertions (`FileNotFoundError` on the marker, and `what the
stop left is found by the cleanup` three times). The three that passed are the core test's
refused-directory cases, which already held, since a refused restore writes nothing.

## Mutants

Each mutant was applied to the worktree, the tests were run with a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; none of these tests uses Hypothesis), and the file was
restored from `HEAD`. Code mutants ran the core marker test, the runbook-search test and the CLI
restore test. Runbook mutants ran the runbook-search test. `git status --porcelain` was empty after each
batch. Every catch is an assertion; none is a collection or import error.

| Mutant | Caught | By |
|---|---|---|
| 1. No marker written (the PM's 1) | Yes, 9 failed | every core marker test but the refusals; the CLI marker test; the three source-stop tests |
| 2a. The marker gains the caselist slug (the PM's 2) | Yes, 4 failed | the exact-fields tests, core and CLI |
| 2b. The marker gains the copy's path (the PM's 2) | Yes, 4 failed | the same four |
| 3a. The purge's marker search back to `-maxdepth 3` (the PM's 3) | Yes, 3 failed | the depth-five copy, in bash and zsh; the two runbooks' searches no longer match |
| 3b. The landscape runbook's marker search back to `-maxdepth 3` (the PM's 3) | Yes, 3 failed | the same, for the landscape runbook |
| 4. The marker written after the restore, not before | Yes, 3 failed | `in place before anything is restored`, `stops part-way`, `stop while the marker is written` |
| 5. The marker written in place rather than moved into place | Yes, 1 failed | `a stop while the marker is written leaves no marker` |

Mutant 5 is why `26d95b7` exists. The first version of the whole-or-none test interrupted inside
`as_json()`, before any file was opened, so a marker written in place would have passed it. The test now
stops `Path.write_text` after half the marker's bytes are on disk.

## Files changed

- **`packages/debate_core/src/debate_core/application/caselist/run_state_restore.py`**: adds
  `RESTORED_COPY_MARKER` and `RestoredCopyMarker`. The restore takes `environment`, `bucket`,
  `build_tag` and `clock`, and writes the marker first. The module docstring has a paragraph on the
  marker.
- **`packages/debate_cli/src/debate_cli/container.py`**: passes the settings' environment and bucket,
  `current_build_info().tag` and the container's clock to `RunStateRestore`.
- **`packages/debate_cli/src/debate_cli/commands/caselist_restore.py`**: one docstring sentence on the
  marker. Behaviour and output are unchanged.
- **`packages/debate_core/tests/application/test_restored_copy_marker.py`** (new): the marker's
  fields, its position as the first write, whole-or-none, and that refused directories get none.
- **`packages/debate_cli/tests/bucket_mode/test_restore_run_state.py`**: a test of the marker through
  the command against moto, with a deep copy and a pinned build tag. The three source-stop tests also
  assert that the marker is left.
- **`tests/docs/test_restored_copy_search.py`** (new): the runbooks' searches, run as written.
- **`docs/runbooks/annual-purge.md`**: step 1's search and success line, step 9's success line, and
  item 6 of "What has no command yet".
- **`docs/runbooks/landscape-report-from-the-cloud-run.md`**: step 5 runs the same searches in place of
  `ls -d …/landscape-copy-*`.

## Deviations from the spec

None. Every file changed is in `constraints.packages`. Nothing was changed in
`landscape_restored_copy.py` or `commands/landscape.py`, as the PM ruled.

## Decisions and assumptions

1. **The marker's name is `debate-research-restored-copy.json`.** No file a data directory holds is
   named after the tool. Its root files are `debate.sqlite3`, the `caselist-sync-*` state files, and the
   `objects/`, `parsed/`, `tub-index/` and `reports/` directories. So the name cannot collide with a
   data directory's own file. It is not hidden, so `ls` in a copy shows it. It is JSON, so `cat` shows
   where the copy came from.
2. **Exactly four fields, with no format version:** `environment`, `bucket`, `restored_at` (UTC,
   `YYYY-MM-DDTHH:MM:SSZ`) and `build_tag`. The PM said to hold the marker to these. A source checkout
   has no tag, so its marker has `"build_tag": null`. The tests treat that as the same four keys.
3. **Whole marker or none, written first.** The PM asked which of "no marker" and "one the runbooks
   find" a failed restore leaves. It leaves a whole marker for any stop after the directory is made,
   because the marker is the first write. A stop during the marker's own write leaves no marker and an
   empty directory with no data in it. Both are tested.
4. **What each refusal leaves.**
   - The target refusals (data directory, inside or holding it, not empty) write nothing.
   - RUN_LOCK_HELD and RUN_STATE_NOT_SEEDED are refused by the bucket write guard before `restore()`
     runs, so no directory is made. The existing tests already assert that.
   - TOO_LITTLE_ROOM_FOR_SOURCES and RESTORED_SOURCES_INCOMPLETE leave the directory, and the tests
     now assert that the marker is in it.
5. **One behaviour change to note.** A restore stopped before it wrote any data (for example
   `RunStateBundleMissing` once the lock is held) used to leave an empty directory, which a second
   restore into the same path accepted. That directory now holds the marker, so the second restore is
   refused as "not empty", and the copy has to be deleted first. That matches what the command already
   says after a stopped `--with-sources` restore. The landscape runbook refuses an existing `$COPY`
   anyway.
6. **The second list filters out marked directories.** The old three-level search would otherwise
   list a marked copy twice, for example `~/.debate-research/landscape-copy-<caselist>`, which is two
   levels down. So "restored before the marker" is the old search minus directories holding a marker.
7. **Both runbooks run identical searches**, and a test asserts it. Each search ends in an `awk` that
   prints its list and then its count, so neither runbook needs a scratch file. The landscape runbook
   has no `$PURGE`, and a file under `/tmp` would sit inside the search.
8. **No extra prunes.** I measured pruning `node_modules` and `.git` as well: 73 s against 59 s, which
   is no faster. The search keeps exactly the PM's prunes.
9. **Tests run the commands in bash, and in zsh where it is installed.** The operator pastes into zsh,
   and CI's runner may have only bash. The test replaces the literal `"$HOME" /tmp ` with a directory
   of its own, and asserts that the literal appears exactly once per search line. That way it never
   walks the real `/tmp`.
10. **The build tag comes from `current_build_info()`**, in the container. In a source checkout that
    runs `git rev-parse` (2 s timeout), once per restore.

**Should a later task remove the "restored before the marker" list?** Yes. Copies restored without a
marker are now only the ones builds before this task made, such as the hspolicy26 copy restored on
dev.200. The list can go once the operator's Mac runs a build carrying `v1-e40-t21` and one pass of
either block prints `restored before the marker: 0`. Until then it is the only way such a copy is
seen. One caution for whoever removes it: the list also shows a stray directory holding
`debate.sqlite3`, such as a scratch store left by a `DEBATE_STORAGE__DATA_DIR` override, under a label
that calls it restored. The purge's step 1 prose still says to report such a directory's last path part
to the PM.

## Checks run before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | `209 of 579 test files (36.1%) chosen in 15.1 s from 10 changed files`. That is more than a third of a selection that takes about six minutes, run while the load average was 10 to 20, so it is over the two-minute line. Under agreement 10 it is left to the PR's `ci` check, which runs the same set; no hand-off |
| Instead, within two minutes: the always-run list, `tests/docs`, `bucket_mode/test_restore_run_state.py`, `test_bucket_mode_restore.py`, `test_bucket_mode_lock.py`, the core marker, run-state-sources and landscape-restored-copy tests, `tests/smoke/test_caselist_restore_run_state.py`, `tests/scripts/test_compare_cloud_run.py`, with `-m "not slow and not live"` | `672 passed in 45.53s` |
| `packages/debate_cli/tests/test_landscape_command.py -k "runbook or RUNBOOK"` (it reads the landscape runbook) | `1 passed` |
| `tests/docs/test_annual_purge_runbook.py` and the neighbours above, earlier at green | `85 passed` |
| `uv run ruff format --check .` | `1626 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_command_blocks.py` | `OK: no '#' comments in 588 shell code blocks in 198 Markdown files` |
| `uv run scripts/check_links.py` | `OK: 3009 relative links and anchors in 464 Markdown files` |
| `uv run scripts/validate_specs.py` (after the phase change) | `OK: 512 files, 40 epics, 450 tasks, 22 releases` |
| Runtime of the new marker search on this Mac (reads only, 115 s alarm) | `59.0 s`, and `73.1 s` with extra prunes; it found no marker, since no build has written one yet |

## Operator follow-ups

None. The affected set runs in the PR's `ci` check.

## Follow-up work

1. **Should `landscape report --restored-copy` require the marker?** Named here, not built (the PM's
   ruling: `v1-e32-t30` is working in the landscape command). A copy restored by a build before this
   task has no marker, so requiring it would refuse the hspolicy26 copy on dev.200 until that copy
   is restored again. The ruling probably fits the same moment as removing the second list.
2. **Remove the "restored before the marker" list** from both runbooks and `test_restored_copy_search.py`,
   once one pass prints `restored before the marker: 0` on a build carrying this task. See
   Decisions.
3. **The other environment's data directory is not refused.** In dev, `restore-run-state --into
   ~/.debate-research/prod` is accepted while prod's data directory is absent or empty. The purge
   runbook says prod's data directory holds no store, so that can be true. The marker would then land
   in prod's data directory. Both searches exclude it, so nothing is mislisted, but the PM's "the live
   data directories never carry the marker" holds only for the environment's own directory. Refusing
   both environments' data directories would close it. That belongs to `run_state_restore.py`'s
   target refusal, in a task of this epic.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e29-t13-stale-parsed-note-without-blob-prefix

| | |
|---|---|
| Task | `v1-e29-t13-stale-parsed-note-without-blob-prefix` — store sync reports a stale parsed copy without needing a blob prefix |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t13-stale-parsed-note-without-blob-prefix.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t13-stale-parsed-note-without-blob-prefix.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t13-stale-parsed-note-without-blob-prefix` |
| Session status | COMPLETE |

## Summary

A dry run of `debate-research store sync` now looks for the stale `objects/parsed/` copy before it
plans the keyspaces, so the `STALE PARSED COPY` note prints even when the plan then refuses. That
refusal is the `UNSYNCABLE_KEYSPACE` one for blobs with no `--blob-prefix`, which is what hid the
note on 2026-10-22. The refusal's code, message and exit are unchanged, `--apply` is unchanged, and
nothing is deleted. The note keeps v1-e29-t12's rules: stderr only, never in `--json`'s payload or
the journal, the directory and a count, never a file name. If the check itself fails, it gets a
one-line note naming the error code (never the message) and the run goes on to the plan. The PM
should look first at that failure rule, under Decisions. The change is one function and its call
site in `packages/debate_cli/src/debate_cli/commands/store.py`; `debate_core` is untouched.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `stale-note` (Stale-copy note first) | Done | Red tests committed alone (`0e9a30a`), fix (`a01df97`), guide (`a510984`). 8 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a dry run over a store with blobs and no `--blob-prefix` prints the stale-copy note and then the same refusal as before, by a test shown failing first; with no stale copy it prints nothing about one | PASS | **Red** at `0e9a30a` against the unchanged command: `uv run pytest packages/debate_cli/tests/commands/test_store.py -k TestTheStaleCopyNoteComesBeforeThePlan -p no:randomly -n 0 -q --tb=line` → `4 failed, 4 passed`. Failing: `test_a_dry_run_refused_for_want_of_a_blob_prefix_still_reports_the_stale_copy` and `test_the_refusal_is_the_same_with_the_note_in_front_of_it` (`assert [] == ['STALE PARSE...jects/parsed']`, so no note); both `test_a_check_that_fails_neither_hides_nor_replaces_the_refusal` cases (a failing check after a successful plan ended the run with `STORE_ACCESS_DENIED`, exit 3, and `INTERNAL_ERROR`, exit 70). Passing at red, as regression guards for the mutants: the no-stale-copy refusal, the note-once pair, and the refused apply. **Green** at `a01df97`: the same file in full → `61 passed in 18.61s`. |
| Node `stale-note`, "Store tests pass": `uv run pytest packages/debate_cli/tests -k store` | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_cli/tests -k store -q` (the interpreter, not `uv`, so the time limit holds; agreement 10) → `218 passed in 75.39s`. |

### Tests added (`packages/debate_cli/tests/commands/test_store.py`, `TestTheStaleCopyNoteComesBeforeThePlan`)

All of them run through the real app and container against a moto bucket; nothing reaches the network or AWS.

* A dry run refused for want of a blob prefix prints the note exactly once on stderr, ahead of the
  `UNSYNCABLE_KEYSPACE` line, with nothing on stdout, no file name, and the copy still on disk.
* The same run under `--json`: the refusal's code, its whole message (written by hand from the
  refusal's source) and exit 1 (`DOMAIN_FAILURE`) are unchanged, the note is on stderr, and
  `objects/parsed` appears nowhere in stdout.
* With no stale copy, refused in both output modes: no line about a stale copy.
* A dry run that plans, with and without `--json`: the note exactly once, and nowhere on stdout.
* `--apply` refused for want of a blob prefix: the same refusal, no note, nothing uploaded, nothing deleted.
* The check fails (`LocalStoreAccessDenied`, or a `PermissionError` whose message quotes a path):
  the refusal and a successful plan both keep their outcome, with one line naming the code or the
  class, and the path never printed.

### Mutants (agreement 8)

Each mutant was applied to the committed code by a script, run against `TestTheStaleCopyNoteComesBeforeThePlan`,
`TestTheParsedStoreIsNotSynced` and `TestSyncPlansByDefault` (`-p no:randomly -n 0`, each run with a
new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, though these tests use no Hypothesis), then restored with
`git checkout HEAD --`. `git status --porcelain` printed nothing afterwards. Every mutant ran to a
result; none errored at collection.

| Mutant | Caught by (failed / 27) |
|---|---|
| (1) Note back after the plan, where v1-e29-t12 had it | 4: both refused-dry-run tests, both failing-check cases |
| (2) Note printed twice on a dry run that plans | 5: note-once (both modes), t12's quoting test, both failing-check cases |
| (3a) Refusal's code changed (`ERROR_CODE = "UNSYNCABLE_BLOBS"` on `UnsyncableKeyspace`) | 7, including the existing `test_blobs_need_the_corpus_prefix_that_says_where_they_belong` |
| (3b) Refusal's exit changed (plan's `DomainError` reported and exited `USAGE`) | 7, the same tests |
| (4a) Note sent to stdout (`print` instead of `cli.output.note`) | 9, five of them t12's |
| (4b) The stale directory put into the `--json` payload | 4: t12's console-only test, note-once under `--json`, both failing-check cases |
| Failing check not caught (the `except` narrowed to `ZeroDivisionError`) | 2: both failing-check cases |
| Failing check prints the exception's message instead of its code | 2: both failing-check cases |

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | `177 of 552 test files (32.1%) chosen in 19.0 s from 5 changed files`. **Not run** with `--run`: 177 files (bucket mode, caselist pull and parse, the API) is far past the two-minute line (an earlier 47-file set took 269 s), so it is left to the pull request's `ci` check, which runs the same affected set. |
| Always-run list, docs-check tests and the changed tests: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs/ tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_cli/tests/commands/test_store.py -q` | `632 passed in 34.71s` |
| `uv run ruff format --check .` | `1549 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_cli` (the only changed package) | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run python scripts/check_thin_handlers.py` (part of CI's import-boundaries job; the `sync` handler gained a statement) | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py` | `OK: no '#' comments in 530 shell code blocks in 191 Markdown files` |
| `uv run scripts/validate_specs.py` (after setting the Goal to Succeeded) | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |

Spec against `origin/dev` before measuring: only the phase differs (dev still has `Pending`), so no
amendment from the PM. Dev had moved two commits, neither touching a file this task changes, so
no sync was needed.

## Files changed

* `packages/debate_cli/src/debate_cli/commands/store.py`: `sync` calls `_note_a_stale_parsed_copy`
  before `service.plan` on a dry run. That function now takes the service, runs the check itself,
  and turns a check that fails into a one-line note.
* `packages/debate_cli/tests/commands/test_store.py`: `TestTheStaleCopyNoteComesBeforeThePlan`
  (8 tests), with two helpers and the refusal's message written by hand.
* `docs/guides/evidence-store-cli.md`: "A stale parsed copy" now says the note comes before the
  table or a refusal, and what a check that cannot be made prints.
* `plan_specs/v1/e29-cloud-evidence-store/t13-stale-parsed-note-without-blob-prefix.yaml`: the
  Goal is set to `Succeeded`.

## Deviations from the spec

None. One note on the node's criterion: its command (`uv run pytest packages/debate_cli/tests -k store`)
was run on `.venv/bin/python -m pytest` with the same arguments, so that agreement 10's time limit
could go on the interpreter. The tests selected are the same.

## Decisions and assumptions

* **A check that fails does not end the run.** The note is advice, and the plan is what the
  operator asked for. So `_note_a_stale_parsed_copy` catches `DomainError` (the local store's
  `LocalStoreAccessDenied` for an unreadable directory is one) and `OSError` (any other
  filesystem failure the adapter does not translate). It prints
  `STALE PARSED COPY: could not look for one (<code>); the plan below does not depend on it.` on
  stderr, then the run goes on to the plan. Whatever the plan does, the run reports it exactly as
  it would have without the check: refusal, success or a failure of its own. `<code>` is the
  `DomainError`'s error code, or else the exception's class name, never its message, because an
  `OSError` quotes the path (the same rule as `CommandFailure.from_exception`, v1-e01-t25).
  `--verbose` prints the traceback, as the root handler does for an unmodelled exception.
  Anything else, such as a bug, still propagates. Catching everything would hide a defect behind
  a note. Before this change a failing check ran after the plan and replaced even a successful
  plan's result (the red run shows `STORE_ACCESS_DENIED`, exit 3, and `INTERNAL_ERROR`, exit 70).
* **An unreadable `objects/parsed/` usually fails the plan as well.** The `objects` keyspace is
  listed before the `blobs` keyspace, and its listing descends into `parsed/`, so the plan reports
  `STORE_ACCESS_DENIED` itself before it reaches the blob-prefix refusal. That ordering was there
  before this task and is unchanged. The test that the refusal survives a failing check therefore
  makes the check fail by patching `EvidenceSyncService.stale_parsed_copy`, not with `chmod`.
* **The note goes before the verbose `listing <bucket> and <data_dir>` detail**, because the
  check reads only this machine's store, not the bucket.
* **No smoke check added.** `tests/smoke/test_store_cli.py` runs against the real dev and prod
  buckets in `validate-dev`, whose machine has no stale copy to report. v1-e29-t12 added none for
  the note either, and the spec has no smoke node. The CliRunner tests above cover the surface
  that changed.

## Operator follow-ups

None. The affected set (177 files) runs in the pull request's `ci` check.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

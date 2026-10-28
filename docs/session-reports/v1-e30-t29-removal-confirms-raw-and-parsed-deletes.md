# Session report: v1-e30-t29-removal-confirms-raw-and-parsed-deletes

| | |
|---|---|
| Task | `v1-e30-t29-removal-confirms-raw-and-parsed-deletes` — A removal lists raw/ and parsed/ again after deleting, and stops incomplete if a version survived |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t29-removal-confirms-raw-and-parsed-deletes.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t29-removal-confirms-raw-and-parsed-deletes.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t29-removal-confirms-raw-and-parsed-deletes` |
| Session status | COMPLETE |

## Summary

`caselist remove --execute` now lists every `raw/` and `parsed/` key it deleted a second time, under
the takedown credential, using the same exact-key filter as the delete. If any version or delete
marker survived, it raises the new `BucketObjectsLeft`: "N version(s) or delete marker(s) of M source
or parsed file(s) this removal reached are still in the bucket after it deleted them; run the same
removal again". The error carries counts only. It is raised at the end of `_delete_bucket_objects`,
so `execute()` stops there as it does for any other step's failure: an `INCOMPLETE` log entry with
`BUCKET_OBJECTS_LEFT`, `RemovalIncomplete`, suppressed. A re-run lists afresh and finishes the job.
This is v1-e32-t13's `SchoolViewsLeft` pattern, copied. The CLI needed no change: `SchoolViewsLeft`
has no handler of its own anywhere, both errors reach the envelope through `RemovalIncomplete`, and
a new CLI test pins that they end the command the same way. The affected set (235 files) runs past
two minutes, so it is left to the pull request's `ci` check (agreement 10). What I ran instead is
listed below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `relist-after-delete` — Re-list after deleting | Done | Red run against a skeleton (the error defined, nothing raising it), then the re-list; 9 mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — With a removal credential that answers a delete without doing it, a removal stops INCOMPLETE naming counts only, and a re-run that deletes finishes it; tests shown failing first, against moto | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_removal_confirms_raw_and_parsed_deletes.py -p no:randomly -n 0 --tb=line -q`. **Red**, at commit `3c64819` (the skeleton): `6 failed, 2 passed in 4.26s`, each failure `Failed: DID NOT RAISE RemovalIncomplete`. The two that passed are the plan-grounding test and the sibling-key test, which asserts the removal is *not* stopped. **Green**, at `bf9ee63`: `8 passed in 4.14s`. Moto only; no network, no AWS. |
| Node `relist-after-delete`: Removal tests pass (`uv run pytest packages/debate_core/tests -k removal`) | PASS | Run as written, with the time limit on the interpreter (agreement 10): `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests -k removal` → `409 passed in 99.39s`. With `-n auto -m "not slow and not live"`: `409 passed in 38.51s`. The selection includes v1-e32-t13's `test_removal_reaches_landscape_school_views.py`. |

### The tests (`test_removal_confirms_raw_and_parsed_deletes.py`)

The removed file is the Seaside Cup round 5 affirmative of the synthetic store: one `raw/` key with
one version. Its parsed cards are written into moto by hand, one `parsed/` key with two versions,
because the synthetic store is published but never parsed. The first test pins that the plan reaches
exactly those two keys, and every count below is worked out by hand from them.

* **A delete that deletes nothing (ac1)**, using `AnswersWithoutDeleting`, a copy of t13's
  `KeepsOneKey` widened to a rule. It stops `INCOMPLETE` with `BUCKET_OBJECTS_LEFT` on the error and
  the log entry, and the cause is `BucketObjectsLeft(versions=3, files=2)` with the exact sentence.
  None of the digest, `raw/`, `parsed/`, the caselist, the school or the team code appears in the
  error, its message, its facts, or either copy of the log line. The log names the removed digest by
  design (`removed_sha256`), so the log lines are checked for everything else. A second run with a
  real delete finishes the job: the log holds `(INCOMPLETE, BUCKET_OBJECTS_LEFT)` then
  `(COMPLETED, None)`, and both keys are gone.
* **Each side alone**: one survivor under `raw/` (1 of 1) and two under `parsed/` (2 of 1). Each stops
  the removal.
* **A delete marker left behind**: a plain delete before the removal puts a marker on the raw key,
  and the double deletes everything except markers. The removal stops with 1 of 1.
* **A sibling key**: `<raw key>.extra`, which no plan names. The removal completes and the sibling
  is still there.

### Mutants (agreements 8 and 10)

Each mutant was applied to `removal_service.py` and run against the new test file (`-n 0 -p no:randomly`) with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory. None of these tests uses Hypothesis, so
that changes nothing here. The source file was restored from the commit afterwards
(`git diff --quiet HEAD` → clean). Every mutant was caught by failed assertions. None was caught by a
collection error: the runs that failed fewer than all 8 tests prove the module still imported.

| Mutant | Result | Caught by |
|---|---|---|
| (1) No re-list | 6 failed, 2 passed | every stop-test |
| (2) Re-list `raw/` keys only | 2 failed | the ac1 counts test, the `parsed/`-alone test |
| (2) Re-list `parsed/` keys only | 3 failed | the ac1 counts test, the `raw/`-alone test, the delete-marker test |
| (2) Re-list the first key only | 2 failed | the ac1 counts test, the `parsed/`-alone test |
| (3) Key filter dropped from the re-list | 1 failed | the sibling-key test |
| (4) A key appended to the error's message | 2 failed | the ac1 counts test (exact sentence), the counts-only test |
| (4) A key among the error's facts (`vars`) | 1 failed | the counts-only test |
| Delete markers not counted by the re-list | 1 failed | the delete-marker test |
| File count = keys planned, not keys left | 3 failed | the `raw/`-alone, `parsed/`-alone and delete-marker tests |

### Checks run before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `235 of 554 test files (42.4%) chosen in 10.4 s from 5 changed files.` |
| The affected set, `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" -q <the 235 files>` | **Over two minutes.** The alarm stopped it at about 61% after 115 s, and no progress line up to that point showed an `F` or `E`. No orphaned xdist workers were left (`ps` showed none). Per agreement 10 it is left to the pull request's `ci` check and was not handed to the operator. |
| Always-run list + the CLI's removal tests: `tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_output.py packages/debate_cli/tests/commands/test_caselist_remove*.py` (8 files) `packages/debate_cli/tests/test_retryable_store_failures.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_removal.py` | `524 passed in 22.06s` |
| `uv run --frozen ruff format --check .` | `1551 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` (after setting the phase) | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 56 indexed documents under docs/ have a description` |

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/removal_service.py`:
  `BucketObjectsLeft` beside `SchoolViewsLeft`, exported. `_delete_bucket_objects` re-lists each
  distinct planned key after the deletes, through a new `_bucket_versions` helper that the delete
  loop uses too. The module docstring's step 2 now says both the `raw/`/`parsed/` keys and the school
  views are listed again after their delete.
* `packages/debate_core/tests/application/caselist/test_removal_confirms_raw_and_parsed_deletes.py`
  (new): the tests above.
* `packages/debate_cli/tests/commands/test_caselist_remove_bucket_objects_left.py` (new): a
  `RemovalIncomplete` raised from `BucketObjectsLeft` ends the command like one raised from
  `SchoolViewsLeft`: exit 1 (`DOMAIN_FAILURE`), code `REMOVAL_INCOMPLETE`, details
  `{"error_code": "BUCKET_OBJECTS_LEFT"}`, the whole message pinned, no key in it.
* The task spec's Goal phase, and this report.

## Deviations from the spec

None.

## Decisions and assumptions

* **M counts the files that still have a survivor**, not every file the removal reached. That
  matches the sentence: "N version(s) … of M … file(s) this removal reached are still in the
  bucket".
* **Each distinct key is re-listed once** (`dict.fromkeys`). Without that, a key the plan named
  twice would be counted twice.
* **The re-list covers every bucket object of the plan**, the parsed aggregates
  (`ObjectKind.PARSED_AGGREGATE`) included, because `_delete_bucket_objects` deletes all of them.
  "Source or parsed file(s)" covers them.
* **No CLI or `_facts_of`/`_what_to_correct` change.** I searched for `SchoolViewsLeft` and found no
  handler of its own: `_facts_of` and `_what_to_correct` are generic and run only for
  `TakedownPreflightFailed`, and the CLI reaches both errors through `RemovalIncomplete` in
  `STOPPED_BY_A_STORE`. A test pins this instead of code. Both end the command with exit 1, as
  `SchoolViewsLeft` already did, even though the advice is to run the command again: that matches the
  brief's "handle the new error the same way", and changing it is the PM's call.
* **The test double is a copy of t13's `KeepsOneKey`, widened from one key to a rule**
  (`AnswersWithoutDeleting`). The preflight deletes its probe through the same credential, so a
  double that refused every delete would fail the preflight before the removal began.
* **The existing order of `execute()` is unchanged.** The re-list runs inside
  `_delete_bucket_objects`, before the school views.

## Operator follow-ups

None. No removal was run against a real bucket.

## Follow-up work

* **Runbook (`docs/runbooks/caselist-removal.md`), for the PM's batch.** No sentence there says that
  only the school views are listed again, so nothing is wrong. But the runbook names neither
  `SCHOOL_VIEWS_LEFT` nor `BUCKET_OBJECTS_LEFT`; only the general "If it stops part-way it says so,
  logs `INCOMPLETE`, and the fix is to run the same command again" covers them. A sentence for the
  PM to place there, if wanted: "After deleting, `--execute` lists the `raw/` and `parsed/` keys and
  the school views again, and a version still there stops it `INCOMPLETE` with
  `BUCKET_OBJECTS_LEFT` or `SCHOOL_VIEWS_LEFT`, counts only: run the same command again."

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

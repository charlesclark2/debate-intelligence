# Session report: v1-e39-t19-identical-rebuild-records-its-suppression-list

| | |
|---|---|
| Task | `v1-e39-t19-identical-rebuild-records-its-suppression-list` — A rebuilt index identical to the published one records the suppression list it was checked against |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t19-identical-rebuild-records-its-suppression-list.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t19-identical-rebuild-records-its-suppression-list.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t19-identical-rebuild-records-its-suppression-list` |
| Session status | COMPLETE |

## Summary

When the weekly search index stage finds that `current.json` already names the index it built or
kept, it now checks what that run read against what the published index says it was checked
against. If the suppression list's digest or a store's occurrence digest differs, the publisher
writes `reports/tub/search/<index id>/checked-against.json` beside the manifest. It goes through
the same bucket client as the index, so in bucket mode it is written under the run's lock. No
object of the index is uploaded again, the pointer is not touched, and the index id is computed as
before. A run under the same list writes nothing.

**I chose a record beside the manifest, not an in-place update** (Decisions, first item). The
function checks the manifest's bytes against the pointer's digest at cold start, so an in-place
update would break it.

`caselist restore-run-state` now brings the record back beside the restored manifest.
`ops/caselist_run/compare_cloud_run.py` reads it there and says in its record which one it read.
A comparison like the cutover's then agrees for an identical rebuild under a longer list. The
evidence-search runbook has a section of its own for the record.

`v1.1.0-dev.200`'s own code ran against a bucket holding records. Its holder, `current()`, restore
and prune plan all ignore the record or keep it with its index (Decisions, third item).

Every acceptance criterion passed. The affected set (252 files) hit the 115-second limit at a load
near 12, so it is left to the pull request's `ci` check under agreement 10. The changed areas and
the always-run list were run instead and passed.

One slip to look at: I ran one `git ls-remote` against `origin`, a read-only network call that was
the operator's to make (Deviations).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `identical-rebuild-record` (Identical rebuild record) | Done | Tests written and shown failing first against a skeleton whose writer wrote nothing (`15f61df`), then the stage and publisher (`f2d4881`), the restore (`a73b453`), the comparison script (`d86322e`), the runbook (`77045eb`), and a test for a session that expires at the record's write (`dc11773`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: against moto, an identical rebuild under a longer suppression list updates the published record of the list it was checked against, without changing the index id or uploading an unchanged object; a rebuild under the same list writes nothing; tests shown failing first | PASS | **Red**, at `15f61df` (writer returns `None`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_search_index_refresh_checked_against.py -p no:randomly -n 0 -rA --tb=no -q` → `9 failed, 2 passed`. The 2 that passed are the guards today's code already met: the same list writes nothing, and a different index publishes as before. The restore's three tests, run against `f2d4881`'s restore before `a73b453` changed it (and committed with that change), were red the same way: `1 failed, 2 passed`. **Green** at `dc11773`: the same file → `15 passed`. PUTs are counted as versions of each key in moto's versioned bucket. After an identical rebuild the gzip object, the manifest and `current.json` each have 1 version and `checked-against.json` has 1. The id is unchanged and the manifest's bytes and the pointer are as they were. Under the same list, whether the manifest's or the record's, the version map is unchanged |
| ac2: the comparison script reads the new record, by test on synthetic manifests | PASS | Red: `... -m pytest tests/scripts/test_compare_cloud_run.py -p no:randomly -rA --tb=no -q` → `5 failed, 11 passed` (the 11 are the existing tests). Green → `16 passed`. Covered: a longer list with no record is `DIFFER` (the cutover's case), and with the record it is `AGREE`. A count that still differs is still a difference. A record naming another manifest, or one that is not JSON, is not read, and the record says so |
| Node: Index refresh tests pass (`uv run pytest packages/debate_core/tests/application -k index_refresh`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/application -k index_refresh` → `17 passed in 8.51s`: this task's 15 and the three settings tests whose names already matched |

### Mutants (agreement 8, each run with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`)

Each mutant was applied to the committed code, run against the stage's two test files
(`test_search_index_refresh_checked_against.py`, `test_search_index_stage.py`), or the comparison's
for mutant 8, and restored from `HEAD`. Every catch below is an `AssertionError`. Under mutant 1 a
few tests also failed reading the absent record (`NoSuchKey`); those are not counted.

| Mutant | Result | Caught by (among others) |
|---|---|---|
| 1. The record not written (the stage never asks the publisher) | 11 failed, 41 passed | `…records_a_longer_list_beside_the_manifest_without_uploading_the_index` |
| 2. An unchanged index object re-uploaded (the stage republishes the same index, then records) | 11 failed, 41 passed | `…records_a_longer_list…` ("the record is put once, and no object of the index, nor the pointer, again"), `…rebuilding_under_the_list_the_manifest_names_writes_nothing`, and `v1-e39-t09`'s `test_index_stage_builds_and_publishes_nothing_when_the_store_has_not_changed` |
| 3. A write under the same list (the publisher's equality check removed) | 5 failed, 47 passed | `…rebuilding_under_the_list_the_manifest_names_writes_nothing`, `…rebuilding_under_the_list_the_record_names_writes_nothing`, and two of `v1-e39-t09`'s |
| 4. The record written without the run's lock (through the stage's read client, which the run lock does not fence) | 2 failed, 50 passed | `…writes_the_record_under_the_runs_lock` (no renewal of the lease) and `…writes_no_record_once_the_runs_lease_was_taken` (the record landed after the lease was lost) |
| 5. A record beside another manifest is read | 1 failed, 51 passed | `…a_record_beside_another_manifest_is_not_read` |
| 6. The restore keeps a record beside another manifest | 1 failed, 51 passed | `…restore_leaves_out_a_record_beside_another_manifest` |
| 7. The restore brings no record | 1 failed, 51 passed | `…record_comes_back_beside_the_manifest_a_run_restores` |
| 8. The comparison reads a record without checking the manifest's digest | 1 failed, 15 passed | `test_a_record_beside_another_manifest_is_not_read` |
| 9. An expired session at the record's write fails the stage instead of pending | 1 failed, 52 passed | `…record_pends_when_the_session_expires_before_it_is_written` |

My first build of mutant 8 compared the index id with itself. That made it read no record at all,
not a stale one, so it was caught by the wrong tests. I rebuilt it to drop only the digest check;
the table gives that run.

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `252 of 593 test files (42.5%) chosen in 20.8 s from 9 changed files` |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | **Stopped at its 115-second limit** (exit 124) at 12% (load average 12.3). No failure before the stop. Left to the pull request's `ci` check, which runs the same affected set |
| The always-run list: `... -m pytest -n auto -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` | `369 passed in 27.80s` |
| The changed areas: `... -m pytest -n auto -m "not slow and not live" packages/debate_core/tests/application/test_search_index_*.py packages/debate_core/tests/application/test_caselist_sync_index_stage.py packages/debate_core/tests/application/test_caselist_sync_run_state.py packages/debate_core/tests/application/test_run_state_saves_held_digests.py tests/scripts/test_compare_cloud_run.py packages/debate_cli/tests/test_tub_index.py packages/debate_cli/tests/test_tub_index_prune.py packages/debate_cli/tests/bucket_mode/` | `510 passed in 100.72s` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1659 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core ops tests/scripts/test_compare_cloud_run.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 530 files, 41 epics, 467 tasks, 22 releases` |
| `scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | `OK: no '#' comments in 602 shell code blocks`; `OK: 3090 relative links and anchors`; `All 60 indexed documents under docs/ have a description` |

## Files changed

* `packages/debate_core/src/debate_core/application/search_index_publish.py`: `CHECKED_AGAINST_NAME`,
  `CheckedAgainstRecord` (the record's shape, and whether it stands beside the manifest the pointer
  names), `read_checked_against`, `RecordedCheck`, and two publisher methods.
  `checked_against()` returns what the published index was last checked against: the record when
  it stands beside the manifest, otherwise the manifest. `record_checked_against()` writes the
  record when that differs, checked as it lands, and writes nothing otherwise.
* `packages/debate_core/src/debate_core/application/search_index_refresh.py`: when `current.json`
  names this run's index, the stage asks the publisher to record. It reports `COMPLETED` with what
  changed, `PENDING` for an expired session ("the next run with a session writes it"), or `FAILED`
  with a hint that does not send the operator to `tub index publish`. The module docstring has the
  rule as its step 5.
* `packages/debate_core/src/debate_core/application/caselist/run_state.py`: the restore brings the
  record back beside the restored manifest when it names that manifest's digest, and otherwise
  leaves it out.
* `ops/caselist_run/compare_cloud_run.py`: reads the restored record and takes the cloud's stores,
  suppression list and counts from it. A new `Index checked against` row says what was read.
* `docs/runbooks/evidence-search.md`: a section of its own, "What an identical rebuild records
  beside the manifest", with a read-only command to read the record by hand. It sits after "What the
  function fetches, and when" and touches no other section, since `v1-e39-t10` edits this runbook too.
* Tests: `packages/debate_core/tests/application/test_search_index_refresh_checked_against.py` (new,
  15 tests, moto) and `tests/scripts/test_compare_cloud_run.py` (5 tests added, and the stand-in
  build's `tub index build` can report another suppression list).

## Deviations from the spec

* **One network call I should have handed over.** While finding which commit `v1.1.0-dev.200` is, I
  ran `git ls-remote --tags origin v1.1.0-dev.200`. It was read-only and returned the tag's commit,
  which the local tag also has. Under the PM's ruling (live network calls go to the operator), it
  should have been a hand-off or skipped for the local tag. Everything after it used local refs
  only, including the check of this spec against `origin/dev`.
* No change to the spec's scope. Every change is inside `constraints.packages`: the record's model
  is in `debate_core.application` rather than `debate_core.domain`, which the list does not name.

## Decisions and assumptions

* **A record beside the manifest, not the manifest updated in place.** The PM leaned to a record
  unless nothing the function or the holder reads at cold start depends on the manifest's bytes.
  Something does. `SearchIndexHolder._manifest` (and `current()`, the shrink guard's read, and the
  restore) refuses a manifest whose sha256 is not the pointer's `manifest_sha256`. So rewriting the
  manifest alone would make every cold start refuse the index ("its manifest is not the one the
  pointer names"); with nothing loaded, search is unavailable. Rewriting the pointer too would avoid
  that, but every warm environment would then see a new pointer and download the whole gzip object
  again for an index that has not changed. Both readers also take the manifest with
  `extra="forbid"`, so a new field in it is a refusal.

  The record names the manifest it stands beside by that same digest. A later publish of the same
  index writes a manifest with another digest, and a leftover record then says nothing about it.
  Neither the record's model nor its name is in `debate_core.domain` (above).
* **What the record holds.** The parts of a manifest a rebuild can change without changing a byte
  of the SQLite file: the parser version, the stores (version directory and occurrence digest), the
  snapshot, the suppression list, and the counts. Plus `index_id` and `manifest_sha256`. Counts and
  digests only, as the manifest. The trigger is any difference in those. That covers what the spec
  names (the suppression digest, or an occurrence digest), and the counts follow from them.
* **Older readers, run as that build's own code.** A bucket was written with this build: two
  indexes published in turn, each followed by an identical rebuild under a longer list, so each
  directory holds a record. `v1.1.0-dev.200`'s `packages/debate_core/src`, from
  `git archive v1.1.0-dev.200`, then read it in moto (scripts kept in the session scratchpad, not
  committed):
  * the holder loaded the current index and read exactly `current.json`, its `manifest.json` and its
    `search-index.sqlite.gz`;
  * `SearchIndexPublishService.current()` read the current index, its manifest as published;
  * the restore restored `manifest.json` and the marker, and no record;
  * the prune plan had no refusal, kept the current index's record with its other files, and would
    delete the superseded index's record with its other files and the older `current.json`.

  `search_index_holder.py`, its S3 source and `search_index_prune.py` are unchanged between
  `v1.1.0-dev.200` and this branch's start (`git log v1.1.0-dev.200..HEAD` on them is empty). The
  holder last changed in `v1-e39-t13` (`a257c5a`), which `v1.1.0-dev.200` contains. Which build
  the deployed function runs I did not check: that needs AWS. Any function since `v1-e39-t13` reads
  as the one above. The committed test
  `test_index_refresh_record_is_never_read_by_the_function_which_loads_the_index_as_before` pins
  the same three reads for the current holder.
* **The lock.** The record goes through the publisher's bucket, the one the index and the pointer go
  through, which the composition root fences in bucket mode. Every PUT renews the lease first. The
  tests run a real `BucketRunLock` against moto over a fenced write client and an unfenced read client:
  the record's write adds one version to the lock object, and once another runner has taken over
  the expired lease the write is refused (`RunLockLost`), no record lands, and the stage fails with
  its reason. On the Mac in local mode the record is written within `caselist pull`'s flock, as the
  publish is.
* **The restore and the comparison.** The comparison script runs the installed build and reads
  the restored copy; it cannot reach the bucket itself. So the restore has to bring the record back.
  A restore by an older build brings none, and the script then reads the manifest, as it did before.
* **The stage's JSON is unchanged.** The record's write is in the stage's reason only. A new
  `SearchIndexStageCounts` field would change the run record's pinned JSON shapes, and
  `caselist_sync.py` is a hub module that widens the affected set.

## Operator follow-ups

None that this session needs. The affected set is left to the pull request's `ci` check under
agreement 10.

Once the image with this change has run on dev, the runbook's new section reads the record. Since
dev's published manifest records five entries and the list holds six, the first run should write
it. That is optional; it closes no criterion of this task.

## Follow-up work

* **`docs/architecture/evidence-store-layout.md` and `docs/data/search-index.md` do not name
  `checked-against.json`.** Both are outside this task's packages. A line in each, for the E39
  epic.
* **The cloud still rebuilds an identical index every week while the manifest and the bucket's list
  disagree.** That is today's behaviour, unchanged: the restored manifest's suppression digest
  differs from the sources, so the stage rebuilds, gets the same id and now writes nothing after
  the first record. The restore now brings the record back, so the stage could treat a restored
  manifest plus a record that matches the sources as current, and skip the rebuild. A small change
  to `SearchIndexRefresh._reusable` with a test, for E39 or E40.
* **`tub index publish --newest` on an index `current.json` already names** republishes it whole:
  the gzip object and manifest again, and the pointer moved, so every environment downloads it
  again (`v1-e39-t02`'s behaviour). Since this task, the record is the cheaper answer for that case.
  The command could say so and record instead, for E39.
* **`docs/data/caselist-cloud-run-comparison.md` still says `DIFFER`** on the suppression list. It
  is the cutover's record and stays as measured. The next comparison agrees only after the cloud
  has run once with this change and written the record.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

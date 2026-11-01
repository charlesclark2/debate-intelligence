# Session report: v1-e39-t25-identical-rebuild-skipped-and-newest-records

| | |
|---|---|
| Task | `v1-e39-t25-identical-rebuild-skipped-and-newest-records` — The weekly index stage skips an identical rebuild its record already matches, and publish --newest on the current index records instead of republishing |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t25-identical-rebuild-skipped-and-newest-records.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t25-identical-rebuild-skipped-and-newest-records.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t25-identical-rebuild-skipped-and-newest-records` |
| Session status | COMPLETE |

## Summary

The weekly search index stage no longer rebuilds an index that its restored record already
describes. A bucket-mode run restores the published manifest and, since `v1-e39-t19`, the
`checked-against.json` beside it. `SearchIndexRefresh._reusable` now keeps that restored manifest
when the record names the manifest's own sha256 and matches what the stage would build from: each
store's version directory and occurrence digest, the suppression list's sha256, and the parser
version. The fingerprint version, format version and provenance limit come from the manifest. The
stage then reports `skipped` and says in its reason that it is not rebuilt, and it writes nothing,
not even the lock. Any difference rebuilds as before, and a record naming another manifest is not
read.

`tub index publish --newest` on the index `current.json` already names no longer republishes it.
It writes the record, when what this build of it read differs from what is recorded, or it is
refused with `SEARCH_INDEX_ALREADY_CURRENT` and writes nothing. It never uploads the gzip object,
the manifest or the pointer. On any other index it publishes as before, and so does `--index`.

Both criteria passed, by tests shown failing first and object versions counted in moto as t19 did.
All eight mutants (the PM's five and three of mine) were caught by assertion failures. The PM
should look first at one choice in Decisions: the publish's `--json` data is left exactly as it
was, because a smoke check pins its key set. Only the record's result carries one more key,
`recorded`. A smoke check for the new `--newest` path would need `tests/smoke`, which is outside
this task's packages (Follow-up work). The affected set (255 files) stopped at its 115-second limit
at 23% with no failure (load 18), so it is left to the pull request's `ci` check under
agreement 10. The always-run list and the changed areas passed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `identical-rebuild-skipped-and-newest-rec` (Identical rebuild skipped) | Done | Tests against a skeleton whose stage still rebuilt and whose `publish_newest` called `publish` (`031c9c1`, red); the stage's skip and `publish_newest` (`d8dc4a3`); the runbooks (`f5a5cde`); the publish's `--json` data kept as it was (`bab8836`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a weekly stage whose restored record matches the sources skips the rebuild and reports it, and `tub index publish --newest` on the current index writes the record or refuses, never the object, manifest or pointer, by tests shown failing first (object versions counted, as t19 counted them) | PASS | **Red** at `031c9c1`: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_search_index_identical_rebuild_skipped.py packages/debate_cli/tests/test_tub_index.py -p no:randomly -n 0 -rA --tb=line -q` → `8 failed, 25 passed`. 5 of the 13 new core tests failed: the skip, the skip writing nothing to the lock, the record from `--newest`, the refusal, and the record under the lock. 3 of the 4 new CLI tests failed. The 8 new core tests that passed are guards today's code already met: a longer list, a changed store or another parser in the record rebuilds; a record beside another manifest is not trusted; `--newest` on another index publishes; a restored directory is refused; a lost lease writes nothing. The new CLI guard that passed is that `--index` on the current index still publishes it whole. **Green** at `d8dc4a3`: the same files → `33 passed`; at `bab8836`, `test_tub_index.py` → `21 passed`. **Versions** (moto's versioned bucket, every PUT a version): the skipped stage leaves the version map exactly as it was. That is one version each of the gzip object, the manifest and `current.json`, and one of the record t19 wrote; nothing more, and no new version of the lock object. `--newest` on the current index under a longer list adds exactly one version of `checked-against.json`, and nothing of the gzip object, the manifest or `current.json`, whose bytes are unchanged. This is shown at the service in moto and through the CLI (`versions_in`). Under the same list it adds nothing and is refused. Under the run's lock (a real `BucketRunLock` over a fenced client), the record's write is one renewal of the lease, and after a takeover it raises `RunLockLost` with no record written |
| Node: Identical rebuild skipped tests pass (`uv run pytest packages/debate_core/tests -k search_index`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests -k search_index` → `310 passed in 48.59s` |

### Mutants (agreement 8, each run with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`)

Each was applied to `d8dc4a3`'s code by a scratch script and run against
`test_search_index_identical_rebuild_skipped.py`, `test_search_index_refresh_checked_against.py`,
`test_search_index_stage.py`, `debate_cli/tests/test_tub_index.py` and
`debate_cli/tests/bucket_mode/test_bucket_mode_restore.py` (93 tests, `-n auto -p no:randomly`),
then restored with `git checkout HEAD --`. Every catch is an `AssertionError` or pytest's
`DID NOT RAISE`, failing at the line it was written for. No hypothesis property is involved, but each
run still had its own empty database.

| Mutant | Result | Caught by |
|---|---|---|
| 1. The stage ignores the record and rebuilds (`recorded = None`) | 2 failed, 91 passed | `…skips_the_rebuild_a_restored_record_matches_and_writes_nothing` ("not rebuilt"), `…skipping_the_rebuild_writes_not_even_the_runs_lock` |
| 2. The stage skips when the suppression digest differs (the record's list replaced by the sources') | 1 failed, 92 passed | `…rebuilds_when_the_list_grew_past_what_the_restored_record_names` |
| 3. `--newest` re-uploads the gzip object before recording | 5 failed, 88 passed | `…records_a_longer_list_and_uploads_nothing_of_it`, `…writes_the_record_under_the_runs_lock`, `…is_refused_when_it_is_already_recorded_so`, and both CLI `--newest` tests |
| 4. `--newest` moves the pointer (puts `current.json`'s same bytes again) | 5 failed, 88 passed | the same five; only a version count can see a pointer rewritten with the same bytes |
| 5. A record naming another manifest digest is trusted (the `manifest_sha256` check dropped) | 1 failed, 92 passed | `…a_restored_record_naming_another_manifest_is_not_trusted` |
| 6. The skip keeps the restored manifest instead of the record's state | 2 failed, 91 passed | the two skip tests: the stage then wrote a record of the manifest's older list, setting the bucket's record back |
| 7. `--newest` republishes whole when there is nothing to record | 2 failed, 91 passed | `…is_refused_when_it_is_already_recorded_so` (`DID NOT RAISE`), the CLI refusal test |
| 8. `--newest` skips the index's check (reads the manifest alone) | 1 failed, 92 passed | `…never_records_from_a_restored_directory` (`DID NOT RAISE SearchIndexFilesDamaged`); without the check, a restored directory's older manifest would be recorded over the bucket's newer record |

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `255 of 614 test files (41.5%) chosen in 15.4 s from 9 changed files` |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | **Stopped at its 115-second limit** (exit 124) at 23%, 1,422 tests passed and none failed before the stop; load average 18 at the end. Left to the pull request's `ci` check, which runs the same affected set |
| The always-run list: `... -m pytest -n auto -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` | `372 passed in 14.99s` |
| Changed areas, core: `... -m pytest -n auto -m "not slow and not live" packages/debate_core/tests/application/test_search_index_*.py packages/debate_core/tests/application/test_caselist_sync_index_stage.py packages/debate_core/tests/application/test_caselist_sync_run_state.py packages/debate_core/tests/application/test_run_state_saves_held_digests.py` | `323 passed in 7.28s` |
| Changed areas, CLI: `... -m pytest -n auto -m "not slow and not live" packages/debate_cli/tests/test_tub_index.py packages/debate_cli/tests/test_tub_index_prune.py packages/debate_cli/tests/bucket_mode/ packages/debate_cli/tests/commands/test_doctor_search_index.py tests/scripts/test_compare_cloud_run.py` | `234 passed in 96.49s` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1704 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 543 files, 41 epics, 480 tasks, 22 releases` |
| `scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | `OK: no '#' comments in 625 shell code blocks`; `OK: 3181 relative links and anchors`; `All 61 indexed documents under docs/ have a description` |

## Files changed

* `packages/debate_core/src/debate_core/application/search_index_refresh.py`: `recorded_beside()` reads
  the record beside a local index's manifest only when its `index_id` and `manifest_sha256` are that
  manifest's own. `_reusable()` now returns the index to keep, or `None`. For a restored manifest that
  is not of the sources, it returns it kept as of a matching record, and `LocalSearchIndex` has a
  `recorded` field for this case. The stage's reason says the rebuild was skipped. Step 3 of the
  module docstring has the rule.
* `packages/debate_core/src/debate_core/application/search_index_publish.py`:
  `CheckedAgainstRecord.applied_to()` gives the manifest as of the record.
  `SearchIndexAlreadyCurrent` is the refusal, with its hint. `RecordedCheck.pointer` is
  `current.json` as read. `SearchIndexPublishService.publish_newest()` is new, and `publish()`
  shares its body with it through `_current_for()` and `_upload()`, with no change in what `publish`
  does. The module docstring has a section on the index `current.json` already names.
* `packages/debate_cli/src/debate_cli/commands/tub_index.py`: `--newest` calls `publish_newest`. The
  record's result has its own `--json` data (`recorded_summary`) and its own table. The module
  docstring says what `--newest` does on the current index.
* Tests: `packages/debate_core/tests/application/test_search_index_identical_rebuild_skipped.py` (new,
  13 tests, moto, reusing t19's world and lock fixture). `packages/debate_cli/tests/test_tub_index.py`
  gets 4 tests, with object versions counted in its versioned moto bucket.
* `docs/runbooks/evidence-search.md`: a section after t19's, "When the record means nothing is
  rebuilt or published again", with the stage's new row, `--newest`'s two outcomes, the lock, and
  older builds. `docs/runbooks/caselist-scheduled-sync.md`: one paragraph in "Publishing a pending
  index by hand", where `--newest`'s success is described, linking to it.

## Deviations from the spec

* **`docs/runbooks/caselist-scheduled-sync.md` is edited as well as `evidence-search.md`.** Both
  are under `docs/runbooks`, which the spec lists. The PM context named only the second, but the
  first is where the operator's `--newest` steps and their success lines live, and those lines would
  otherwise send them looking for a `current.json` row that this case no longer prints.
* No change to the spec's scope otherwise. Every change is inside `constraints.packages`.

## Decisions and assumptions

* **What the stage compares the record with.** `built_from` (the stage's existing rule), applied to
  the restored manifest as of the record (`CheckedAgainstRecord.applied_to`). The record supplies the
  stores, the suppression list, the parser version, the snapshot and the counts. The manifest
  supplies the fingerprint and format versions and the provenance limit, which the record does not
  hold and an identical index cannot change. Only a directory a restore wrote (its marker present)
  is read this way. Nothing on a Mac writes a record into a directory it built, and a Mac's rebuild
  replaces its own manifest anyway.
* **The kept index carries the record's state, not the manifest's.** The stage goes on to step 5,
  where t19 records what it was checked against when that differs from the bucket. Kept as the
  restored manifest alone, it would differ, and would write the manifest's older list over the
  bucket's record (mutant 6 shows it). Kept as of the record, it equals the bucket's record and
  nothing is written. A record could only be due here if the bucket's record had changed since the
  restore, which the run's lock prevents, and then it would be written through t19's path, fenced.
* **The skip reports `skipped`, in the reason, with no new counts field.** It is the stage's existing
  `unchanged since <id> … which current.json names: nothing to build or publish` with a clause saying
  why it is not rebuilt. The run records that reason in its details. A `SearchIndexStageCounts` field
  would change the run record's pinned shapes and widen the affected set through `caselist_sync.py`,
  the same reason t19 gave. The PM context allowed either.
* **The lock and the skip.** The skip only reads, so it does not renew the lease, and a run whose
  lease was lost skips without writing (pinned: the lock object's versions are unchanged). Where a
  write is due (`--newest`'s record, or t19's record in the stage), it goes through the fenced client,
  and a lost lease raises `RunLockLost` with nothing written. `tub index publish` already takes the
  lock in bucket mode (`test_bucket_mode_lock.py` runs it with `--newest`).
* **`--newest` runs the same checks as `publish` first.** That means versions, and the gzip object
  against the manifest. A restored directory, which has no gzip object, is therefore refused as
  before (`test_a_restored_index_directory_is_never_published_by_hand` still passes), and never
  recorded from. Recording from it would write the restored manifest's older state over the bucket's
  record (mutant 8). The check reads the local gzip object, as a publish always has.
* **The refusal is a `DomainError`, exit 1, `SEARCH_INDEX_ALREADY_CURRENT`**, with `index_id` in its
  details and a hint that nothing needs publishing. The PM context said "refuse with a hint". A
  success with nothing written was the alternative, but it would be easy to misread as a publish.
* **The `--json` data.** A publish's `data` keeps exactly its five keys, because
  `tests/smoke/test_tub_index_smoke.py` pins the set whole and `tests/smoke` is outside this task's
  packages. I first added `"recorded": null` to it and took that out again (`bab8836`). The record's
  result has the same five keys, with `written` the record's key alone, `pointer` the unchanged
  `current.json` and `replaced` `null`, plus `recorded`. So a script tells the two apart by
  `recorded`, and no key is removed or renamed.
* **`--index` is unchanged**: it publishes the directory it names whole even when `current.json` names
  it. The spec and the PM context speak of `--newest` only. A test pins the behaviour so that any
  change to it is deliberate.
* **Older readers: `v1.1.0-dev.200`.** This task writes no new object and no new field. The skip only
  reads, and `--newest` writes t19's `checked-against.json` with `CheckedAgainstRecord`'s fields
  unchanged; `applied_to` is a method, and `RecordedCheck.pointer` is in memory only. So dev.200 reads
  a bucket this writes exactly as t19 showed it reads one t19 wrote, by running that build's own
  code: its holder, `current()`, restore and prune ignore the record or keep it with its index. Its own
  `tub index publish --newest` still republishes the current index whole, which is safe and only
  wasteful. I did not re-run dev.200's code for this task, since nothing it reads changed.

## Operator follow-ups

None that this session needs. The affected set is left to the pull request's `ci` check under
agreement 10.

Once an image with this change runs on dev (the deploy after `v1.1.0-dev.251`), the first weekly run
after a record exists should report `skipped` with "not rebuilt" in the `search_index` row, and no
build. That is an observation, not a criterion of this task.

## Follow-up work

* **A smoke check for `--newest` on the current index**, in `tests/smoke/test_tub_index_smoke.py`
  against the installed build: build, publish, add a suppression entry that stops nothing, rebuild,
  `--newest` writes only `checked-against.json`, and once more is refused. Agreement 5 asks for one;
  `tests/smoke` is outside this task's packages and the spec has no smoke node. For E39, or a spec
  amendment to this task.
* **`docs/data/search-index.md` and `docs/architecture/evidence-store-layout.md`** still lack the
  record's line, as t19 filed; the PM has it in the next batch.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

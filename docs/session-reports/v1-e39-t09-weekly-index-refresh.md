# Session report: v1-e39-t09-weekly-index-refresh

| | |
|---|---|
| Task | `v1-e39-t09-weekly-index-refresh` — The weekly agent run rebuilds and publishes the search index when the parsed store changed |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t09-weekly-index-refresh.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t09-weekly-index-refresh.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t09-weekly-index-refresh` |
| Session status | COMPLETE (the Goal stays InProgress: ac4 is the operator's, after the merge) |

## Summary

The weekly `caselist pull` has a new optional stage, `search_index`, after parse and before
landscape. It runs for the run's configured caselists plus `openev`, in the PM's order:

1. With an AWS session, reconcile the suppression list's two copies.
2. Compute each store's `occurrences_sha256` and the list's `sha256`, through a new
   `SearchIndexBuildService.sources()` method that the build's own manifest is computed by.
3. Build offline with `v1-e39-t02`'s service, only when those digests (or the versions and the
   provenance limit) differ from the newest local index's manifest.
4. With a session, when `current.json` names another index, publish to the agent's own environment
   with `v1-e39-t02`'s service, pointer last.

Without a session the stage reports "built, publish pending". The next run with a session
publishes that same index without rebuilding it, unless reconciling changed the suppression
digest. The runbook gives `tub index publish --index <newest>` as the by-hand catch-up, for dev and
for prod.

A failed build or upload leaves the previous pointer and the previous local index, and the
stage's reason names them. A version mismatch skips the stage with its reason, and so does a failed
parse in the same run. Every build reports its SQLite bytes and bytes per document, with warnings
at ADR-0019's two lines. Turned off by `caselist.refresh_search_index`, the stage is shown as
skipped and is never absent from the run.

**The Goal stays InProgress.** ac4 is the operator's: the next agent install has to record one
weekly run that published an index. Every other criterion passed.

**Look at first:** the cross-build record comparison. It now reads the start commit's records with
the one stage entry this build adds (Deviation 6). Also look at the local disk growth of
`tub-index/` (Follow-up 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `refresh` (Weekly index refresh) | Done | Its command passes (below). It selects the two new stage test files and `test_tub_index.py`; the ac7 and Q6 tests live in the build and settings test files, run separately below. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `refresh`: Run stage tests pass | PASS | `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "index_stage or tub_index" -q -n auto` → `41 passed in 11.97s` at the time. With the tests added since, the stage files hold 27 + 11 tests. |
| ac1 builds and publishes only when the store changed, over a stubbed run, shown failing first | PASS | `test_search_index_stage.py` covers: first index built and published; unchanged store means no build and no upload; changed rows or suppression list mean rebuild and publish; a damaged local index is rebuilt. `test_caselist_sync_index_stage.py` is the stubbed run: stage order, the stores handed over (caselists plus `openev`), runs with nothing imported. Red against a refuse-nothing skeleton (always build, always publish): stage file `16 failed, 9 passed` (the 9 are the always-rebuild cases and the pure helpers a skeleton satisfies); run file `7 failed, 3 passed`. Green: 27 and 11 passed. |
| ac2 a failed build or upload leaves the previous pointer and local index, appears in the run summary and failure notification, reason names the index still current | PASS | `test_index_stage_a_failed_build_leaves_the_previous_index_and_pointer_and_names_them`, `…_a_failed_upload_leaves_the_previous_pointer_and_names_it` (hint carries `DEBATE_ENV=dev debate-research tub index publish --env dev --index <data_dir>/tub-index/<id>`), `…_a_session_that_expires_mid_publish_pends_and_leaves_the_pointer`, `…_with_an_unreachable_bucket_…_fails_its_publish`; run level `test_index_stage_failure_is_recorded_with_its_code_and_the_index_still_current_and_notified` (stage `failed` on `SEARCH_INDEX_STORE_NOT_READY`, record `incomplete`, run still `succeeded`, notification "caselist pull finished with a failed stage … the search_index stage failed on SEARCH_INDEX_STORE_NOT_READY" with the hint). All red under the skeleton, green now. |
| ac3 a version mismatch skips the stage with its reason | PASS | `test_index_stage_skips_a_store_parsed_by_another_parser[older]` and `[newer]`, and `…_whose_rows_carry_another_fingerprint_version`. Synthetic versions only (`2026.01.05-synthetic-a`, `2026.02.05-synthetic-b`, `2025.12.01-synthetic-0`, `card-fingerprint-synthetic-z`). Nothing built, nothing uploaded. Red under the skeleton, green now. |
| ac4 the next agent install records one weekly run that published an index | NOT RUN | The operator's, after the merge, at the next agent install; a session never runs the agent or a publish. See Operator follow-ups. |
| ac5 reconcile with a session; local copy without one, said in the summary; next run with a session publishes without rebuild unless reconciling changed the digest; both paths failing first | PASS | `test_index_stage_reconciles_the_suppression_copies_before_it_builds`, `…_without_a_session_builds_from_the_local_copy_and_the_publish_pends`, `…_told_there_is_no_session_does_not_try_the_bucket`, `…_publishes_an_index_built_without_a_session_at_the_next_run_without_a_rebuild`, `…_rebuilds_at_the_next_run_when_reconciling_changed_the_suppression_digest`; run level `…_is_told_there_is_no_session_when_the_publish_stage_pended` and `…_pending_publish_makes_the_run_publish_pending_and_the_login_banner_names_it`. Both paths red under the skeleton, green now. |
| ac6 SQLite bytes and bytes per document for every build; warnings past 900,000,000 SQLite and 400,000,000 gzip bytes naming ADR-0019 | PASS | `test_index_stage_reports_the_sqlite_bytes_and_bytes_per_document_of_every_build`; `test_index_stage_warns_past_each_of_adr_0019s_lines` at each boundary (equal: no warning; one more: the warning). |
| ac7 the method's digests equal a real build's manifest digests on the same store | PASS | `test_search_index_sources_digests_are_the_digests_a_real_build_records`, plus `…_built_from_sources_read_first_is_the_same_index` and `…_refuses_sources_read_for_other_stores` in `test_search_index_build.py`. Red first: `3 failed` (`no attribute 'sources'`); green: `47 passed`. |
| Q6: the setting stays on in the bundled profiles; turned off, the stage is skipped and never absent | PASS | `test_the_bundled_dev_and_prod_profiles_leave_the_weekly_index_refresh_on[dev-dev]` and `[stable-prod]` (the committed `config/` copied as the wheel bundles it, read from `$HOME`), `test_a_bundled_profile_is_what_decides_the_weekly_index_refresh`, `test_index_stage_turned_off_by_setting_is_skipped_with_the_settings_name_and_never_absent`, and the smoke world `test_a_pull_is_listed_by_caselist_runs_locally_and_from_the_bucket` asserting `skipped`, `turned off by setting`. Red with three planted faults (profile turned off, reason not used, container gate dropped): `3 failed, 2 passed`, each for its fault. |

### Mutation run

Mutation run: 24 hand-written mutants against `search_index_refresh.py`, the stage in
`caselist_sync.py`, `_outcome_of` in `sync_runs.py` and the newer-parser rule in
`search_index_build.py`. Each was run over the two stage test files and `test_search_index_build.py`.
The first pass killed 20. Two survivors were real gaps, and new tests kill them:

* **Provenance limit ignored:** `test_index_stage_rebuilds_an_index_built_by_hand_with_another_provenance_limit`.
* **A scratch directory counted as an index:** `test_index_stage_a_scratch_directory_holding_a_whole_index_is_never_the_newest`.

The other two are equivalent:

* **Parser version ignored in `built_from`:** a store's `version_directory` names the parser, so the
  stores already differ.
* **An expired session at reconcile not treated as no session:** the pointer read then meets the
  same expired session, and the stage pends all the same.

Final: 22 killed, 2 equivalent.

### The affected set and the whole-repo checks

1. `uv run scripts/affected_tests.py` selected 193 files (the caselist sync is imported widely).
   `perl -e 'alarm 150; exec @ARGV' uv run scripts/affected_tests.py --run` was meant to stop at
   150 s. The alarm stopped `uv` but not its pytest child, which ran on to the end:
   `36 failed, 4259 passed in 237.43s`. That is past the two-minute line, which I report as an
   over-run. The 36 were in 7 files, all caused by this change:
   * 27 in the cross-build record test, and 4 more pinning the stage list or the details dictionary
     (Deviation 6);
   * 2 from a bug of mine: a refused bucket copy was put in the login-only
     `suppression_list_local_copy_only` field. It is now said in the stage's reason alone, and
     `tests/smoke/test_caselist_pull.py` passes again;
   * 3 in smoke worlds that parse no camp store (PM ruling Q6).
2. After the fixes, under the two-minute line:
   `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -q -m "not slow and not live" <the 7 files, test_caselist_sync.py, test_caselist_sync_index_stage.py, test_sync_runs.py, test_search_index_{stage,build,publish}.py, test_settings*.py, test_landscape_staleness.py, test_caselist_pull_parses.py (core and CLI), test_sync_runs_banners_say_what_waits.py, test_pull_contains_unreadable_local_files.py, the CLI pull, runs and tub index tests, tests/smoke/test_caselist_pull*.py, tests/smoke/test_caselist_runs.py, tests/architecture, tests/specs, test_app.py, test_installation.py>`
   → `796 passed in 86.06s`. The rest of the selection is left to the pull request's `ci`, under
   agreement 10.
3. Whole-repo checks:
   * `uv run ruff format --check .` → `940 files already formatted`
   * `uv run ruff check .` → `All checks passed!`
   * `uv run pyright packages/debate_core packages/debate_cli` → `0 errors`
   * `uv run lint-imports` → `Contracts: 12 kept, 0 broken.`
   * `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`
   * `uv run scripts/check_command_blocks.py` → `OK`
   * `uv run scripts/check_links.py` → `OK: 1883 relative links and anchors in 275 Markdown files`

## Files changed

* `plan_specs/v1/e39-evidence-search-pilot/t09-weekly-index-refresh.yaml`: the PM's rulings (Q1 to
  Q6) and the t02 second-review amendments, each with its comment. The description is rewritten,
  ac2 is amended, ac5 to ac7 are added, and `tests/smoke` is added to the packages.
* `packages/debate_core/src/debate_core/application/search_index_refresh.py` (new): the stage, with
  `SearchIndexRefresh`, `newest_local_index`, `built_from`, `size_warnings` and the two ADR-0019
  lines.
* `packages/debate_core/src/debate_core/application/search_index_build.py`: adds the `sources()`
  method and `SearchIndexSources`. `build(…, sources=)` reads through that method. Adds
  `SearchIndexStoreVersionMismatch`, a `SearchIndexStoreNotReady` subclass under the same code,
  raised for another parser's or fingerprint's store and for one a newer parser wrote.
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `SyncStage.SEARCH_INDEX`,
  the stage's protocol and report types, the stage itself, and its dry-run and publish-pending
  rows. Also `RunSummary.search_index` (an additive key; the schema version stays 5) and the
  turned-off reason.
* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `SyncRunDetails.search_index` (`SearchIndexCounts`; the record stays frozen);
  * a pending index publish makes the outcome `publish_pending`, and the login banner names the
    index and the by-hand command;
  * the stage's reason gets parse's longer length limit.
* `packages/debate_core/src/debate_core/application/settings.py`: `caselist.refresh_search_index`,
  default true.
* `packages/debate_cli/src/debate_cli/container.py`: wires the stage where the environment names a
  bucket and the setting is on. One argument and one builder method.
* `packages/debate_cli/src/debate_cli/commands/tub_index.py`: the default `--out` directory name now
  comes from the stage module, so both write to one place.
* Tests, new:
  * `packages/debate_core/tests/application/test_search_index_stage.py`;
  * `packages/debate_core/tests/application/test_caselist_sync_index_stage.py`;
  * additions to `test_search_index_build.py` and `test_settings_environments.py`.
* Tests, pinned values updated:
  * `caselist/test_pull_run_record_is_read_by_every_build.py`;
  * `caselist/test_pull_contains_unreadable_local_files.py`;
  * `caselist/test_pull_pending_publish_keeps_earlier_findings.py`;
  * both `test_pull_refused_before_the_bucket_is_built.py`.
* `tests/smoke/test_caselist_runs.py` and `tests/smoke/test_caselist_pull_in_process.py`: three
  worlds that parse no camp store turn the stage off (PM ruling Q6).
* `docs/runbooks/caselist-scheduled-sync.md`: a new section, "The search index stage", with what
  each outcome means, the by-hand catch-up for dev and prod, and the one-importing-machine
  condition. `docs/runbooks/evidence-search.md` points at it.

## Deviations from the spec

1. **The spec itself was amended** on the PM's rulings of 2026-10-20 (Q1 to Q6) and the
   `v1-e39-t02` second-review amendments:
   * the agent publishes to its own environment, and prod stays the operator's step;
   * ac2's "stale-data warning" is now "failure notification (v1-e34-t03)";
   * ac5 to ac7 are new;
   * `tests/smoke` is in the packages.

   Each change carries its comment in the spec.
2. **`v1-e39-t02`'s build service changed** (Q2): a `sources()` method, used by the build itself.
   Through that rule, `tub index build` by hand now also refuses a store that a newer parser has
   written to. It is reported under the same code, `SEARCH_INDEX_STORE_NOT_READY` (accepted by
   the PM).
3. **The stage is wired in only where the environment names a bucket** (accepted). Elsewhere it is
   skipped with that reason.
4. **The digest comparison also checks the parser, fingerprint and format versions and the
   provenance limit** (accepted). Each of them changes an index's bytes.
5. **`tests/smoke` edited** (Q6, accepted): three worlds set
   `DEBATE_CASELIST__REFRESH_SEARCH_INDEX=false`. One of them now also asserts the stage is shown
   as skipped by the setting.
6. **Pinned values in existing tests.** The cross-build record test compares this build's records
   field for field with the start commit's. It now reads the stored records with the
   `search_index` entry this build adds after `parse`: skipped, with the reason each mode gives
   (`as_this_build_records_it`). Every written record is still validated against the older builds'
   schema, so the property it guards is unchanged. Expected details gain `"search_index": null`.
   One stage-list assertion gains the new stage, and one stage count goes from 7 to 8.

## Decisions and assumptions

* **"The newest local index"** is the index directory under `<data_dir>/tub-index` whose
  `manifest.json` was written last. Ties go by index id. A dot-directory (a build's scratch
  directory) and a directory without a readable manifest are never counted.
* **When "a session exists".** The run tells the stage there is none when its publish or parse
  stage pended for want of one; then the stage does not try the bucket. Otherwise the reconcile
  finds out: `StoreCredentialsExpired` means no session. Any other store error at reconcile means
  the build reads the local copy, says so in the reason, and the publish fails.
* **A reused index is checked first.** Before the newest local index is reused for a publish, its
  files are checked against its manifest (`SearchIndexPublishService.check`). A damaged one is
  rebuilt, so it cannot fail every week's publish.
* **"current.json is behind"** means it names another index id, or none, or one this build cannot
  read. Publishing replaces it.
* **The record stays frozen** (`v1-e34-t19`). The stage is a `StageEntry` by name, which every
  build reads; its counts go in the run's details. A pending index publish is in no file. What is
  owed is worked out again each run, as for the parsed store.
* **Reasons name no path,** since `redact` would take it out. The by-hand command, with
  `<data_dir>/tub-index/<id>`, is in the hint and the login banner, which keep relative paths.

## Operator follow-ups

**ac4, at the next agent install after this merges** (needs the operator's AWS session and the
agent). Where: your Mac. First reinstall the agent exactly as
[Reinstalling the agent](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent) says,
with a build that contains this task. After the next scheduled Wednesday run, with a live
`debate-dev-evidence` session, read what it did (a few seconds):

```bash
DEBATE_ENV=dev debate-research caselist runs --last 1
LATEST=$(ls -t "${HOME}/.debate-research/dev/caselist-sync-runs/"*.json | head -1)
jq '{stage: [.stages[] | select(.stage == "search_index")], search_index: .search_index}' "${LATEST}"
```

Success is the `search_index` stage `completed` with `published` in its reason, and `search_index`
showing `"published": true`, an `index_id`, `sqlite_bytes` and `bytes_per_document`, with no
warning. If the stage is `pending` (no session at 06:00), publish by hand as
[Publishing a pending index by hand](../runbooks/caselist-scheduled-sync.md#publishing-a-pending-index-by-hand)
says. ac4 then needs the next run that publishes. Record the run in
[`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md).

The whole default selection is left to the pull request's `ci` (agreement 10). No operator run is
needed.

## Follow-up work

1. **`tub-index/` grows on this Mac.** Every rebuild leaves the previous index directory, and nothing
   removes superseded local ones. At ADR-0019's estimate of 280 to 550 MB a directory (SQLite plus
   gzip), a few weeks of changed stores is several GB. Bucket pruning is `v1-e39-t07`'s; local
   retention (keep the newest two, say) belongs to the PM to place, perhaps in `v1-e39-t07` or a
   small E39 task.
2. **A fresh installation fails the stage until every store is parsed.** That includes `openev`,
   per the Q3 ruling. `debate-research doctor` could say so before the first Wednesday (E34 or E39).
3. **The by-hand catch-up picks the newest directory with `ls -t`.** A `tub index publish --newest`
   flag in `v1-e39-t02`'s command would remove that step.
4. **Pre-existing pyright errors.** `tests/smoke/test_caselist_pull_in_process.py` (lines 546, 727,
   957) and `tests/smoke/test_caselist_runs.py` (188 to 189) have pyright errors about boto3's
   optional TypedDict keys. They date from 2026-10-12 and 2026-10-14, are outside the packages CI
   type-checks, and are not this task's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

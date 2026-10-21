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
digest. The runbook gives `tub index publish --newest` as the by-hand catch-up, for dev and
for prod.

After a successful build the stage removes superseded local index directories. It never removes
the two newest, the one `current.json` named when it was read, a directory without a readable
manifest, or a dot-directory, and the summary gives the count removed and the bytes freed.
`tub index publish --newest` publishes the stage's own newest index, so the runbook's dev and prod
catch-ups need no `ls -t` (both added at the PM's review). A failed build or upload leaves the
previous pointer and the previous local index, and the stage's reason names them. A version mismatch skips the stage with its reason, and so does a failed
parse in the same run. Every build reports its SQLite bytes and bytes per document, with warnings
at ADR-0019's two lines. Turned off by `caselist.refresh_search_index`, the stage is shown as
skipped and is never absent from the run.

**The Goal stays InProgress.** ac4 is the operator's: the next agent install has to record one
weekly run that published an index. Every other criterion passed.

**Look at first:** the cross-build record comparison. It now reads the start commit's records with
the one stage entry this build adds (Deviation 6). Also look at the two review additions (ac8 and
ac9, and Deviations 7 and 8).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `refresh` (Weekly index refresh) | Done | Its command passes (below). It selects the two new stage test files and `test_tub_index.py`; the ac7 and Q6 tests live in the build and settings test files, run separately below. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `refresh`: Run stage tests pass | PASS | `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "index_stage or tub_index" -q -n auto` → `41 passed in 11.97s` at the time. With the tests added since, the stage files hold 27 + 11 tests. |
| ac1 builds and publishes only when the store changed, over a stubbed run, shown failing first | PASS | `test_search_index_stage.py` covers: first index built and published; unchanged store means no build and no upload; changed rows or suppression list mean rebuild and publish; a damaged local index is rebuilt. `test_caselist_sync_index_stage.py` is the stubbed run: stage order, the stores handed over (caselists plus `openev`), runs with nothing imported. Red against a refuse-nothing skeleton (always build, always publish): stage file `16 failed, 9 passed` (the 9 are the always-rebuild cases and the pure helpers a skeleton satisfies); run file `7 failed, 3 passed`. Green: 27 and 11 passed. |
| ac2 a failed build or upload leaves the previous pointer and local index, appears in the run summary and failure notification, reason names the index still current | PASS | `test_index_stage_a_failed_build_leaves_the_previous_index_and_pointer_and_names_them`, `…_a_failed_upload_leaves_the_previous_pointer_and_names_it` (hint carries `DEBATE_ENV=dev debate-research tub index publish --env dev --newest` and names the index id), `…_a_session_that_expires_mid_publish_pends_and_leaves_the_pointer`, `…_with_an_unreachable_bucket_…_fails_its_publish`; run level `test_index_stage_failure_is_recorded_with_its_code_and_the_index_still_current_and_notified` (stage `failed` on `SEARCH_INDEX_STORE_NOT_READY`, record `incomplete`, run still `succeeded`, notification "caselist pull finished with a failed stage … the search_index stage failed on SEARCH_INDEX_STORE_NOT_READY" with the hint). All red under the skeleton, green now. |
| ac3 a version mismatch skips the stage with its reason | PASS | `test_index_stage_skips_a_store_parsed_by_another_parser[older]` and `[newer]`, and `…_whose_rows_carry_another_fingerprint_version`. Synthetic versions only (`2026.01.05-synthetic-a`, `2026.02.05-synthetic-b`, `2025.12.01-synthetic-0`, `card-fingerprint-synthetic-z`). Nothing built, nothing uploaded. Red under the skeleton, green now. |
| ac4 the next agent install records one weekly run that published an index | NOT RUN | The operator's, after the merge, at the next agent install; a session never runs the agent or a publish. See Operator follow-ups. |
| ac5 reconcile with a session; local copy without one, said in the summary; next run with a session publishes without rebuild unless reconciling changed the digest; both paths failing first | PASS | `test_index_stage_reconciles_the_suppression_copies_before_it_builds`, `…_without_a_session_builds_from_the_local_copy_and_the_publish_pends`, `…_told_there_is_no_session_does_not_try_the_bucket`, `…_publishes_an_index_built_without_a_session_at_the_next_run_without_a_rebuild`, `…_rebuilds_at_the_next_run_when_reconciling_changed_the_suppression_digest`; run level `…_is_told_there_is_no_session_when_the_publish_stage_pended` and `…_pending_publish_makes_the_run_publish_pending_and_the_login_banner_names_it`. Both paths red under the skeleton, green now. |
| ac6 SQLite bytes and bytes per document for every build; warnings past 900,000,000 SQLite and 400,000,000 gzip bytes naming ADR-0019 | PASS | `test_index_stage_reports_the_sqlite_bytes_and_bytes_per_document_of_every_build`; `test_index_stage_warns_past_each_of_adr_0019s_lines` at each boundary (equal: no warning; one more: the warning). |
| ac7 the method's digests equal a real build's manifest digests on the same store | PASS | `test_search_index_sources_digests_are_the_digests_a_real_build_records`, plus `…_built_from_sources_read_first_is_the_same_index` and `…_refuses_sources_read_for_other_stores` in `test_search_index_build.py`. Red first: `3 failed` (`no attribute 'sources'`); green: `47 passed`. |
| ac8 after a build, superseded local indexes are removed and never the two newest, the one `current.json` names when read, a directory without a readable manifest or a dot-directory; count removed and bytes freed in the summary, each rule failing first | PASS | `test_index_stage_after_a_build_keeps_the_two_newest_and_removes_the_rest` (`removed 1 superseded index on this machine, <n> bytes freed`, and `bytes_freed` equals the removed directory's bytes), `…_never_removes_the_index_current_json_names`, `…_without_reading_current_json_keeps_only_the_two_newest`, `…_never_removes_a_directory_without_a_readable_manifest_or_a_dot_directory`, `…_that_builds_nothing_removes_nothing`. Red first: all 5 failed before retention existed. Then each rule failed under a planted fault breaking it alone: keep only the newest; `current.json` not protected; every directory a candidate; retention without a build. Each was caught by its own test (output below). |
| ac9 `tub index publish --newest` publishes the directory `newest_local_index` picks and is refused with `--index`; both runbook sections use it | PASS | `packages/debate_cli/tests/test_tub_index.py`: `…_newest_publishes_the_index_the_weekly_stage_calls_newest[False]` and `[True]` (two real builds, either one newer by manifest time, a dot-directory beside them), `…_refuses_newest_together_with_index` (usage error, nothing written), `…_needs_newest_or_index`, `…_newest_with_nothing_built_names_the_build` (`NO_BUILT_SEARCH_INDEX`, hint names `tub index build`). Red first: 4 failed before the option existed; `…_needs_newest_or_index` passed throughout, since `--index` was required before. Mutant `--newest` picks the oldest: killed by both parametrised cases. The runbook's dev and prod blocks in [Publishing a pending index by hand](../runbooks/caselist-scheduled-sync.md#publishing-a-pending-index-by-hand) use `--newest`, and `evidence-search.md` points at that section. |
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

**Review additions.** Four planted faults on the keep rules, run with `.venv/bin/python -m pytest -n 0`
over the retention tests:

* keep only the newest: killed by `…_never_removes_the_index_current_json_names` and
  `…_without_reading_current_json_keeps_only_the_two_newest`;
* `current.json` not protected: killed by `…_never_removes_the_index_current_json_names`;
* every directory a candidate: killed by `…_never_removes_a_directory_without_a_readable_manifest_or_a_dot_directory`;
* retention without a build: killed by `…_that_builds_nothing_removes_nothing`.

The first pass had "keep only the newest" caught by the `current.json` test alone. With a session,
the pointer read before the publish names the previous index, which masks the two-newest rule, so
the no-session test now pins which two directories stay. The first driver run reported all four as
surviving: `-p no:xdist` clashed with the project's `--numprocesses`, every run was a usage error,
and the driver read "no FAILED line" as a survivor. The driver now reports a run that errors as an
error. One CLI mutant: `--newest` picks the oldest, killed.

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
3. After the review additions, the same set plus `tests/docs` and `test_help_rendering.py`:
   `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -q -m "not slow and not live" <…>`
   → `860 passed in 97.02s`.
4. Whole-repo checks (rerun after the additions, chained bare):
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
  comes from the stage module, so both write to one place. `publish --newest` (review) makes
  `--index` optional; exactly one of the two is required.
* Review addition, local retention: `local_indexes`, `remove_superseded` and `KEEP_NEWEST` in
  `search_index_refresh.py`, and `removed` and `bytes_freed` on `SearchIndexStageCounts` and on the
  details' `SearchIndexCounts`.
* Tests, new:
  * `packages/debate_core/tests/application/test_search_index_stage.py`;
  * `packages/debate_core/tests/application/test_caselist_sync_index_stage.py`;
  * additions to `test_search_index_build.py`, `test_settings_environments.py` and
    `packages/debate_cli/tests/test_tub_index.py` (`--newest`).
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
7. **The stage's failure hint and the login banner now give `tub index publish --newest`** in place
   of `--index <data_dir>/tub-index/<id>`, still naming the index id in their sentence. This goes
   one step past the review's "update both runbook sections": I did it so that no message asks for
   a path.
8. **`tub index publish --index` is no longer a required option.** One of `--index` and `--newest`
   is required. A call with neither is still a usage error, as it was, and `--index` behaves as
   before.

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
* **Reasons name no path,** since `redact` would take it out. The by-hand command,
  `tub index publish --newest`, is in the hint and the login banner, each naming the index id in
  its sentence (Deviation 7).

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

1. ~~`tub-index/` grows on this Mac.~~ Closed in this session at the PM's review (ac8). Bucket
   pruning stays `v1-e39-t07`'s.
2. **A fresh installation fails the stage until every store is parsed.** That includes `openev`,
   per the Q3 ruling. `debate-research doctor` could say so before the first Wednesday (E34 or E39).
3. ~~The by-hand catch-up picks the newest directory with `ls -t`.~~ Closed in this session at the
   PM's review (ac9).
4. **Pre-existing pyright errors.** `tests/smoke/test_caselist_pull_in_process.py` (lines 546, 727,
   957) and `tests/smoke/test_caselist_runs.py` (188 to 189) have pyright errors about boto3's
   optional TypedDict keys. They date from 2026-10-12 and 2026-10-14, are outside the packages CI
   type-checks, and are not this task's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Accepted, with two small additions closed in this session before the pull request (below). The pull
request then opens with `--partial`, since ac4 is the operator's after the next agent install. No
task depends on this one, so nothing is held back. As before, if anything comes out differently
from what you expect, stop and ask for another review.

**What is good:**

* **The stage follows the ruled order exactly:** reconcile with a session, digests through the
  one `sources()` method, build only on a change, publish pointer-last only when `current.json` is
  behind.
* **The build and the check cannot disagree:** ac7's test pins that the method's digests are a real
  build's.
* **The failure paths name what is still current,** and the by-hand command is in the hint and the
  login banner rather than in a redacted reason.
* **Checking a reused index against its manifest before publishing it** (Decisions) is a good
  catch: a damaged directory cannot fail every week.
* **The mutation run found two real gaps** (the provenance limit, and a scratch directory counted
  as an index), and both now have tests. The two equivalents are argued.
* **Deviation 6 keeps the cross-build guarantee:** records are still validated against the older
  builds' schema, and the change is additive at schema version 5.

**The two additions:**

1. **Local retention, here rather than later.** Your Follow-up 1 underestimates the cost. The real
   index directory is about 1.03 GB (752 MB SQLite plus 282 MB gzip), so every week with a change
   adds a gigabyte to a Mac that had 54 GB free. After a successful build, the stage removes
   superseded directories under `<data_dir>/tub-index/`. It never removes:
   * the two newest;
   * the one `current.json` names, when it was read;
   * any directory without a readable manifest, or a dot-directory.

   The run summary says how many it removed and the bytes freed. Show each "never" failing first,
   and add a mutant or two on the keep rule. Write it into the spec with a comment
   `PM amendment 2026-10-20 (v1-e39-t09 review)`.
2. **`tub index publish --newest`.** Prod publishing stays the operator's by-hand step every week,
   so remove the `ls -t` step. `--newest` picks the directory by `newest_local_index`, the stage's
   own rule, and refuses together with `--index`. Update both runbook sections to use it, with a test.

**Rulings on the rest:**

* **Deviations 1 to 6:** accepted.
* **The affected-set over-run:** reported honestly. The lesson for every session is that an alarm
  on `uv` does not stop its pytest child, while your second form, the alarm on `.venv/bin/python -m
  pytest`, does. I am adding that to working agreement 10 in my next batch.
* **Follow-up 2** (doctor warns before a store is parsed): a p3, filed in the next batch.
* **Follow-up 4** (the pre-existing pyright errors in `tests/smoke`): this joins the E01 follow-up
  task I am filing.

**ac4 timing.** If this merges before the operator's agent reinstall after v1-e31-t24's re-parse,
that install carries it, and the next Wednesday run is ac4's evidence. Before that run, the
operator also applies v1-e39-t02's operator follow-up 2 (the dev listing grant), so the stage's
read of `current.json` is not refused for want of a list permission. The PM records ac4 in a
close-out.

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Both additions are closed as asked. Open the pull request with `--partial` (ac4 is the operator's).

**What I checked:**

* **Retention (ac8).** `remove_superseded` only ever sees what `local_indexes` lists, so a
  directory without a readable manifest and a dot-directory cannot reach `rmtree`.
  * The two newest and the id `current.json` gave are skipped before any size is read.
  * A directory that cannot be removed is named and left, not failed.
  * Each "never" failed first, and each planted fault was caught by its own test.
* **Retention, a finding worth keeping.** You noticed that, with a session, the pointer read
  masked the two-newest rule, and added a no-session test that pins which two stay.
* **Mutation driver.** You noticed it was reading usage errors as survivors, and fixed it to
  report them as errors. That is the right instinct: a mutation run that cannot fail proves
  nothing.
* **`--newest` (ac9)** uses the stage's own `newest_local_index`, is refused with `--index`, and
  names `tub index build` when nothing is built. The oldest-picking mutant is killed.
* **Deviations 7 and 8 are accepted.** No message asking for a path is better than one that does.

**Two stale lines, fixed in place before the pull request** (no change to the verdict):

* the Summary's "`tub index publish --index <newest>` as the by-hand catch-up";
* the Decisions bullet saying the hint carries `<data_dir>/tub-index/<id>`.

Both now read `--newest`, per Deviation 7.

**ac4** is recorded by the PM after the first Wednesday run, under an install that carries this
task, that published. Before that run: the dev listing grant (v1-e39-t02 operator follow-up 2) and a
live `debate-dev-evidence` session at 06:00.

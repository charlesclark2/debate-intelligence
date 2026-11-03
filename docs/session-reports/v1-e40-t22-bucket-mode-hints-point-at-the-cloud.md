# Session report: v1-e40-t22-bucket-mode-hints-point-at-the-cloud

| | |
|---|---|
| Task | `v1-e40-t22-bucket-mode-hints-point-at-the-cloud` — In bucket mode the login banner and the parse stage's other hints point at the cloud run, not the operator's Mac |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t22-bucket-mode-hints-point-at-the-cloud.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t22-bucket-mode-hints-point-at-the-cloud.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t22-bucket-mode-hints-point-at-the-cloud` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

In bucket mode, three more hints now point at the cloud run instead of the operator's Mac:

* **The login banner.** Its fix is now the cloud run's task role, the PM's to look into, and never
  `aws sso login && caselist pull --publish-pending`. Its message names no command either. The
  report stage's cut-short check and a waiting search index are said without `--publish-pending` or
  `tub index publish`.
* **The failure-rate hint** names the `failures.jsonl` the cloud run publishes with the parsed store,
  and says why the sources failed is the PM's to look into. It no longer names
  `caselist parse --failures`.
* **The newer-fingerprint hint** names a new image through `caselist-cloud-run.md`, "A new image,
  later". It no longer says "the weekly agent". This holds in the stage and in the monitor's details
  for a run that raised.

Bucket mode is decided as `v1-e40-t18` decides it: the service's `bucket_mode`, and the details'
`bucket_run`. No new environment check was added. Local mode keeps every word. The pending reason's
`").;` join is tidied. The record and details shapes are unchanged. `v1.1.0-dev.164` (the cloud
image) and `v1.1.0-dev.200` (the Mac's installed build) read every record and details line these
runs write. That is shown by the stored schemas and by each build's own reader.

**Look first at Follow-up 1.** Two more bucket-mode banners, outside the three, still name
`caselist pull --publish-pending`, and so does one CLI hint.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bucket-mode-hints-point-at-the-cloud` (Bucket-mode hints) | Done | Red tests (`337b2e9`), then the code, two runbook sections and two cross-build scenarios (`6418083`); 16 mutants plus mutant 3a against dev.164's and dev.200's own readers |

## Acceptance criteria

"dev.164" is `v1.1.0-dev.164` (`03b23e2`), the cloud image. "dev.200" is `v1.1.0-dev.200`
(`761b571`), the Mac's installed build, which is `v1-e40-t18`'s merge. "The start commit" is
`7272af9`. All three were already tags or commits in the local repository. Each was exported with
`git archive` into the session's scratch directory and put first on `PYTHONPATH`, and each reader
printed the path its `sync_runs` came from. No tag was fetched. "Red" means the tests of `337b2e9`
run against the unchanged source.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: in bucket mode the three hints name the cloud run's cure and no Mac-side publish, by tests shown failing first | PASS | `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`, run as `.venv/bin/python -m pytest <file> -p no:randomly -n 0 --no-cov`. **Red:** `7 failed, 7 passed in 4.08s`. The 7 failures: the login banner's fix was `aws sso login --profile debate-dev-evidence && debate-research caselist pull --publish-pending`, in both login tests; the failure-rate hint was the `--failures` sentence; the newer-table hint ended "install that build for the weekly agent", both in the stage and in the monitor's details for a run that raised (`[bucket]`); the pending reason held `stage").; this machine's copy`; and the runbook had no "A run that found no AWS session". The 7 that passed are the local-mode tests and the three cross-build schema cases, which hold on the unchanged source too. **Green:** `14 passed`. Every sentence is pinned whole and by hand. Each bucket-mode banner's whole text holds none of `--publish`, `--failures`, `caselist parse`, `caselist pull`, `aws sso login`, `tub index publish`, `weekly agent` |
| **ac1**: local mode is unchanged | PASS | The local tests pin each old sentence whole: the login fix, `THE_CHECK_WAS_CUT_SHORT`, the index sentence with its command, the `--failures` hint, and the weekly-agent hint in the stage and in the monitor's details. `cloud` is nowhere in a local banner. Earlier tasks' files pass unchanged, with one exception: `v1-e40-t18`'s pending-stage assertion (see Decisions) |
| **ac1**: dev.164 and the Mac's installed build read every record written | PASS | **By schema:** `test_the_cloud_image_and_the_macs_build_read_every_record_and_details_line_these_runs_write[login, failure_rate, newer_table]`. The record validates against `record_schema_of_the_cloud_image.json`, which dev.164 and dev.200 each print byte for byte (`cmp`). The details validate against dev.164's `details_schema_before_parsed_stores_owed.json` and dev.200's own, new here as `details_schema_of_the_macs_installed_build.json`. Every stage entry has exactly `stage`, `outcome`, `reason`, and no details key is one dev.200 does not define. **By each build's own reader:** see below. **The check can fail:** mutants 3a and 3b |
| Node: Bucket-mode hints tests pass (`uv run pytest packages/debate_core/tests/application -k caselist_sync`) | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application -k caselist_sync -n 4 --no-cov`: `258 passed in 40.72s` |
| Forbidden: a bucket-mode hint naming a command that publishes from the operator's working copy | PASS | ac1 above, and mutants 1a–1g. Two other bucket-mode banners still do; they are outside the three, see Follow-up 1 |
| Forbidden: a record shape an earlier build refuses to read | PASS | No model changed. Mutants 3a and 3b are caught by the schema tests and by `v1-e34-t19`'s every-build tests. 3a is also refused by dev.164's and dev.200's own readers |
| Forbidden: network or AWS access in any test | PASS | The core tests use moto under `tmp_path`, `v1-e34-t31`'s scripted parse stage and `v1-e40-t18`'s stand-in bracket. The schemas were printed offline from local exports |
| PM: mutants (1) to (3), each caught (agreement 8) | PASS | 16 mutants, all caught. See [Mutants](#mutants) |
| Closing checks (working agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Every build reads this build's files

`write_parsed_stores_owed_files.py` gains two bucket-mode scenarios: `cloud_failure_rate` and
`cloud_newer_table`. t18's `cloud_pending` already gives the login banner. `read_sync_run_files.py`
now also prints each banner's hint. `S` is the scratch directory:

```bash
WRITE_PARSED_STORES_OWED_FILES="${S}/files/this-build" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_parsed_stores_owed_files.py -p no:cacheprovider --no-cov -n 0 -q
.venv/bin/python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/dev164/packages/debate_core/src" .venv/bin/python "${S}/read_sync_run_files.py" "${S}/files/this-build" dev164
PYTHONPATH="${S}/dev200/packages/debate_core/src" .venv/bin/python "${S}/read_sync_run_files.py" "${S}/files/this-build" dev200
PYTHONPATH="${S}/start/packages/debate_core/src" .venv/bin/python "${S}/read_sync_run_files.py" "${S}/files/this-build" start
```

The three exported readers ran from the scratch directory, from a copy of the script, so that the
worktree's source was not on the path. The writer printed `7 passed`. Each of the four reads exited
0 with `refused or skipped: 0`, over seven scenarios. dev.200's output and the start commit's are
identical after the first line. Each build makes its own banners, so dev.164's login banner on
`cloud_pending` still says `aws sso login && debate-research caselist pull --publish-pending`. This
build's says `the PM looks into the cloud run's task role, which gave the run no AWS session
(caselist-cloud-run.md, "A run that found no AWS session"); never a login and a publish from the
operator's Mac`. Part of dev.200's output:

```text
cloud_failure_rate:
  record 20260916T060000Z: incomplete; ... publish completed, parse failed, search_index skipped, ...
    kept by this build: bucket_run kept; parse hint 'The cloud run\'s failed sources are listed in failures.jsonl ... (caselist-cloud-run.md, "A parse stage over its failure rate").'
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
cloud_newer_table:
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
    parse error_codes ['NEWER_FINGERPRINT_TABLE']; hint: The occurrence table of testcl26 2026.10.20-docx-6 in the bucket is stamped synthetic-fingerprint-v8, and the cloud run's image's fingerprint version is synthetic-fingerprint-v7. ...
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
```

**Mutant 3a with each build's reader.** The record gained `cloud_hints: bool = False`. The writer
ran on the mutant, and the source was then restored. dev.164's reader: exit 1, `refused or skipped:
21`, the first line `REFUSED in the bucket: reports/sync-runs/2026/20260916T060000Z.json: 1
error(s)`. dev.200's reader: the same.

### Mutants

Each mutant was a one-occurrence edit of the source, run on eight files with `-n 4`: the new core
file, t18's, `v1-e34-t31`'s, `test_pull_refuses_a_newer_fingerprint_table.py`,
`test_sync_runs_banners_say_what_waits.py`, `test_pull_run_record_is_read_by_every_build.py`,
`test_pull_notification_says_retry_or_person.py` and `test_pull_stage_failure_codes.py` (184
tests). Each run had a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis), a
hard stop, and `git checkout HEAD --` afterwards. The tree was clean at the end. Each took 8 to
21 s.

| # | Mutant | Result | Caught by (first few) |
|---|---|---|---|
| 1a | PM (1): the failure-rate hint ignores bucket mode | CAUGHT, 1 failed | the bucket-mode failure-rate test |
| 1b | PM (1): `fix_for` ignores bucket mode | CAUGHT, 2 failed | the bucket-mode newer-table test, the monitor's `[bucket]` case |
| 1c | PM (1): the stage's `_failure` does not pass bucket mode | CAUGHT, 1 failed | the bucket-mode newer-table test |
| 1d | PM (1): the login fix ignores `bucket_run` | CAUGHT, 2 failed | both bucket-mode login tests |
| 1e | PM (1): the cut-short sentence ignores `bucket_run` | CAUGHT, 1 failed | the login test with what waits |
| 1f | PM (1): the index sentence ignores `bucket_run` | CAUGHT, 1 failed | the same |
| 1g | PM (1): the monitor's failure details ignore bucket mode | CAUGHT, 1 failed | the monitor's `[bucket]` case |
| 2a | PM (2): the cloud failure-rate hint in local mode | CAUGHT, 2 failed | the local failure-rate test, `v1-e34-t17`'s `test_a_parse_over_the_failure_rate_carries_the_command_that_lists_what_failed` |
| 2b | PM (2): `fix_for` gives the cloud hint in local mode | CAUGHT, 4 failed | `v1-e34-t29`'s pull test, the local newer-table test, the monitor's `[local]` case |
| 2c | PM (2): the cloud login fix in local mode | CAUGHT, 8 failed | the local login test, `v1-e34-t26`'s and `t28`'s banner tests |
| 2d | PM (2): the cloud cut-short sentence in local mode | CAUGHT, 5 failed | the same files |
| 2e | PM (2): the cloud index sentence in local mode | CAUGHT, 1 failed | the local login test |
| 2f | PM (2): the monitor's failure details cloud in local mode | CAUGHT, 1 failed | the monitor's `[local]` case |
| 3a | PM (3): the record gains `cloud_hints: bool = False` | CAUGHT, 47 failed | this task's three schema cases, `v1-e34-t19`'s every-build tests |
| 3b | PM (3): a stage entry gains `cure: str = "cloud"` | CAUGHT, 39 failed | the same |
| 4 | the reason join keeps its full stop | CAUGHT, 2 failed | this task's join test, t18's pending-stage test |

### Closing checks

`uv run scripts/affected_tests.py` chose **298 of 583 test files** (51.1%) from 12 changed files.
`v1-e40-t18`'s 281 took more than two minutes on this Mac. Under agreement 10, the affected set is
left to the pull request's `ci`; it was not run whole and was not handed over. Load averages were
6 to 56 from other sessions. What ran:

| Run | Result |
|---|---|
| Always-run list plus the docs tests (`tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`, `-n 4`) | `652 passed in 44.31s` |
| The node criterion (`packages/debate_core/tests/application -k caselist_sync`) | `258 passed in 40.72s` |
| The files that pin this wording or read these records: the eight mutant files, `test_pull_parses_new_sources.py`, `test_inbox_retention.py`, `packages/debate_cli/tests/bucket_mode/test_bucket_mode_parse_fix_names_the_cloud_run.py` | `235 passed` after t18's one assertion was updated (before that, `1 failed, 234 passed`: that assertion) |
| `ruff format --check .` / `ruff check .` | `1634 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` (no `debate_cli` source changed) |
| `lint-imports` / `scripts/check_thin_handlers.py` | `19 kept, 0 broken` / `68 … handlers within 25 statements` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py` | `All 59 indexed documents under docs/ have a description` / `OK: no # comments in 592 shell code blocks in 198 Markdown files` |
| `uv run scripts/validate_specs.py`, after setting the Goal | `OK: 519 files, 40 epics, 457 tasks, 22 releases` |

**About the always-run row.** A first attempt under `perl -e 'alarm 115; exec @ARGV'` was not
stopped by the alarm. It ran for about 30 minutes at load averages near 50, and I killed it and its
workers by pid. Its output was lost to the `| tail`. The second attempt used a watchdog script that
kills the process group, and wrote to a file. It is the row above. Afterwards no pytest process from
this worktree was left running.

`git fetch origin dev` (read-only) showed that dev moved only by the generated ROADMAP refresh
(`bc0ad1a`). This spec on dev differs from mine only in its phase, so no sync was made.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/occurrence_table_guard.py`:
  `CLOUD_NEW_IMAGE_RUNBOOK` and `NewerFingerprintTable.cloud_fix`.
* `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  * `CLOUD_FAILURE_RATE_RUNBOOK` and `_CLOUD_FAILURE_RATE_FIX`, chosen by `self._bucket_mode`.
  * `fix_for(error, *, bucket_mode=False)`; the stage's `_failure` and `_camp_failure` pass it.
  * `_RunTally.add_to_reason` drops a trailing full stop before its `; `.
  * The module docstring.
* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `CLOUD_NO_SESSION_RUNBOOK`, `CLOUD_NO_SESSION_CURE` and `_THE_CLOUD_CHECK_WAS_CUT_SHORT`.
  * The login banner reads `details.bucket_run` for its fix, its cut-short sentence and its index
    sentence.
  * `details_for_failure(..., bucket_mode=False)`. `SyncRunMonitor.watch` asks `bucket_run()` first
    and passes `bucket_mode` from it.
* `docs/runbooks/caselist-cloud-run.md`:
  * New sections "A run that found no AWS session" and "A parse stage over its failure rate", with
    read-only operator blocks.
  * A paragraph in "A new image, later" on a refused newer occurrence table.
* Tests, new:
  * `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py` (14 tests).
  * `stored_run_records/details_schema_of_the_macs_installed_build.json` (printed by dev.200), with
    its README row and command.
* Tests, changed:
  * `write_parsed_stores_owed_files.py`: two scenarios.
  * `read_sync_run_files.py`: prints each banner's hint.
  * `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py`: one assertion, for the join.
* The spec: Goal phase `Succeeded`.

## Deviations from the spec

None. The spec's constraints allow `debate_cli`; nothing in it changed.

## Decisions and assumptions

* **The login banner's message changed in bucket mode too, not only its fix.** ac1 says "the login
  banner" names no Mac-side publish, and the forbidden list says the same of any bucket-mode hint.
  The message carried two such commands: `THE_CHECK_WAS_CUT_SHORT`'s `caselist pull
  --publish-pending after the login`, and the index's `tub index publish`. In bucket mode both
  sentences keep what waits and drop the command. They make no promise about what the next cloud run
  does. Its state files and bundle may not have been saved without a session, and I could not show
  that the next run makes that check or publishes that index.
* **The fix says the PM looks into the task role.** That follows the PM's "a task-role or secret
  problem goes to the PM". The role's session comes from ECS, not from a secret, so the sentence
  names the role alone. The runbook gives one read-only log command to send the PM.
* **The failure-rate hint says "once the run has published it".** A stage over its rate still
  publishes, but a refused publish leaves no `failures.jsonl` in the bucket. The runbook says that
  nothing printed means the publish did not finish.
* **The newer-table hint keeps `v1-e40-t18`'s condition**, "the next cloud run that imports into
  <caselist>", for the same reason t18 gave. It changes when `v1-e40-t08` lands.
* **The join tidy applies in both modes.** It is in `add_to_reason`, so a local pending reason's
  `does not.; this machine's copy` also becomes `does not; this machine's copy`. No hint's words
  change. This is the only change local mode sees, and no test pinned the old join. t18's
  bucket-mode assertion pinned it as a substring and now expects the semicolon. Mutant 4 shows both
  tests catch a revert.
* **dev.200's details schema is stored.** It is the first stored details schema that defines
  `parsed_stores_owed`, so dev.200 checks the type of that key too. Its record schema is the stored
  cloud-image one, by `cmp`.

## Operator follow-ups

None. The affected set (298 files) is left to the pull request's `ci`, per agreement 10. The cloud
run prints the new wording only from an image built after this merges (`caselist-cloud-run.md`, "A
new image, later"). Both new runbook sections say the rule holds for an older image's email too.

## Follow-up work

1. **Three more bucket-mode hints name `caselist pull --publish-pending`** (E40). They are outside
   this task's three and were left as they are:
   * a failed publish stage's banner (`fix_command=PUBLISH_PENDING_COMMAND` when only the publish
     failed, `sync_runs.notifications_for`);
   * the "manifest published again" banner (`MANIFEST_PUBLISHED_AGAIN_TITLE`);
   * the CLI's own next step for a failed publish stage (`caselist_pull.py`, "Re-run `caselist pull
     --publish-pending`").

   Question for the PM:

   > **v1-e40-t22, Follow-up 1: should the remaining bucket-mode `--publish-pending` hints point at the cloud run?**
   > (a) **One more p3 task (recommended):** the same treatment for the failed-publish banner, the published-again banner and the CLI's next step, decided by `bucket_run` and `bucket_mode` as here.
   > (b) Leave them: in the cloud a failed publish is retried by the next weekly run, and the runbook's rule covers it.
   > Why (a): each names a command that publishes from the operator's working copy, which this task's forbidden list rules out for a bucket-mode hint. The pattern is now settled, so it is about an hour's work.
2. **The bucket-mode login banner's message still says "kept everything it fetched"** and, for a
   manifest owed again, "the publish after the login uploads this machine's copy". Neither names a
   command, but neither is true of a cloud task, whose working copy ends with it. This could go into
   the same task as Follow-up 1.
3. **A failure-rate failure whose parsed store was published** still gets `v1-e40-t18`'s fix line,
   "the next cloud run that imports into a caselist the parse stage names publishes that caselist's
   parsed store". Nothing is owed there. In local mode the same case gives `PARSE_COMMAND`. This is
   pre-existing, and the PM asked that t18's cure not change; `v1-e40-t08` may be the place for it.
4. **A pending parse reason in bucket mode quotes `aws sso login --profile debate-dev-evidence`**
   inside the suppression list's fallback reason (the S3 adapter's message). It is a record reason,
   not a hint, and it was left as it is.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

In bucket mode the login banner, the failure-rate hint and the newer-fingerprint hint now point at
the cloud run, and local mode keeps every word.
1. **ac1 passes.**
   * Red: 7 failed, each one an old Mac-side sentence. Green: 14 passed, and the node criterion 258.
   * Every bucket-mode banner's whole text is checked against the seven forbidden phrases.
   * 16 mutants, all caught. Six of them each catch a leak of the cloud wording into local mode.
2. **The cross-build reads hold.** dev.164 and dev.200 read seven scenarios with nothing refused.
   * Mutant 3a makes both builds' own readers refuse 21, so the check can fail.
   * dev.200's details schema is now stored, the first that defines `parsed_stores_owed`. Good.
3. **Decisions accepted:**
   * the login banner's message as well as its fix, keeping what waits and dropping the command,
     with no promise about the next run;
   * the task role as the PM's;
   * "once the run has published it";
   * t18's import condition kept until v1-e40-t08;
   * the join tidy in both modes, the one local change and harmless.
4. **Follow-ups:**
   * **1, 2 and 4: (a).** One p3 task in the next PM batch, for the failed-publish banner, the
     published-again banner, the CLI's next step, the "kept everything it fetched" and "this
     machine's copy" sentences, and a look at the suppression fallback's quoted login.
   * **3:** an amendment to v1-e40-t08, so that a parse over its failure rate whose parsed store was
     published names no cure.
5. **The runaway always-run attempt.** `perl -e 'alarm 115; exec …'` did not stop a pytest that ran
   about 30 minutes at load near 50. Thank you for killing it by pid and reporting it. The PM files a
   p3 task for one shared hard-stop wrapper that kills the process group, named by agreement 10, so
   no session relies on the alarm again.
6. **Closing checks:** the affected set (298 files) is left to the PR's `ci` under agreement 10. The
   always-run list (652), the node criterion (258) and the wording and record files (235) pass, as
   do the whole-repo checks.
7. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`. The new wording reaches
   the email with the next image.

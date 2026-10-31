# Session report: v1-e40-t28-last-bucket-mode-wording-pass

| | |
|---|---|
| Task | `v1-e40-t28-last-bucket-mode-wording-pass` — The last bucket-mode wording pass: banners and the CLI name the next cloud run, and a cloud run's login hint names the task role |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t28-last-bucket-mode-wording-pass.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t28-last-bucket-mode-wording-pass.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t28-last-bucket-mode-wording-pass` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

In bucket mode, no banner of a run's email names `debate-research caselist pull` any more:

* A run that stopped on an error names the next cloud run.
* A failed-stage banner beyond the publish alone or the parse alone does too, and it ends with
  t25's "What the bucket confirmed is kept; …".
* The backlog banner names the next cloud run "once the day's downloads reset".

The CLI's "run the same command again" names the next cloud run as well. Every one of these uses
t25's words, through one helper (`next_cloud_run`) that t18's and t25's cures now share, byte for
byte.

The S3 adapters' login hint comes from the composition root:

* **The cloud run** gets `CLOUD_NO_SESSION_CURE`, the login banner's own fix: the task role and
  "A run that found no AWS session". The cloud run is bucket mode inside an ECS task, read from
  `ECS_CONTAINER_METADATA_URI_V4`, which the run lock already reads.
* **A hand run on the Mac and local mode** keep `aws sso login …`, word for word.

Local mode's words are unchanged, and tests pin each one. No record or details model changed.

**Look first at Deviations.** In bucket mode I also changed the CLI's two other "run the same
command again" lines, not only the one after a stage's own fix. The runbook gains two sections,
for the two new fix lines to point at.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `last-bucket-mode-wording-pass` (Last wording pass) | Done | Helper refactor alone (`4425426`), red tests with the adapter skeleton (`dad1ca7`), the change and the runbook (`f627ba9`), a docstring revert that narrowed `affected_tests`' reading of the container (`63d1903`). 25 mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: in bucket mode the three banners name the next cloud run | PASS | `test_caselist_sync_bucket_mode_banners_name_the_next_cloud_run.py`: stopped run, four failed-stage cases (import beside publish, download alone, report alone, parse beside publish), backlog. Each pins the message and the fix whole, by hand. Each banner's text holds none of t25's `POINTS_AT_THE_MAC` phrases and no `debate-research`. See [Red, then green](#red-then-green) |
| **ac1**: … and the CLI's rerun line | PASS | `test_bucket_mode_rerun_hint_names_the_cloud_run.py`: after a stage's own fix, after a failed download, after any other stage. See Deviations for the second and third |
| **ac1**: a cloud run's missing-session reasons name the task role and the cloud runbook's section | PASS | `test_bucket_mode_login_hint_names_the_task_role.py`, through the whole command over moto. When the session goes at the first state file, the run stops: the envelope's error, its hint and the details' hint name the task role. When it goes at the publish, the publish reason does: `0 object(s) published, 1 snapshot(s) left for a later run: the AWS session for [redacted] is not usable: the PM looks into the cloud run's task role, …`. No sentence the run printed or kept says `aws sso login`. The section exists: t25's test and this task's runbook test read it by its heading |
| **ac1**: local mode's words are byte for byte as before | PASS | Every local sentence pinned whole in the same files, beside its bucket-mode case: the stopped run, the four failed-stage cases, the backlog, the three CLI lines. These local words had no pin before: the backlog fix, and the CLI's download and other-stage lines. The hand-run and local login hints are pinned in both new login-hint files. They all passed red, against the old code. Earlier tasks' files pass unchanged; the one exception is below |
| **ac1**: tests shown failing first | PASS | `dad1ca7`: 25 failed, 41 passed, every failure an `AssertionError` (see below) |
| PM: `test_a_bucket_mode_publish_that_failed_beside_another_stage_keeps_its_fix` changed deliberately | PASS | Renamed `…_names_the_next_cloud_run`. It now expects the unfinished-run cure and "What the bucket confirmed is kept; …". "What was captured is kept." is not true in a cloud run (Decisions). The docstring says so |
| PM: one email banner and one CLI line before and after | PASS | [Before and after](#before-and-after) |
| PM: mutants (1) to (4) (agreement 8) | PASS | 25 mutants, all caught on an assertion. See [Mutants](#mutants) |
| Forbidden: a local-mode message changed | PASS | The local pins above; mutants 2a to 2h |
| Forbidden: a key removed or renamed in a `--json` envelope | PASS | No envelope key changed. `test_the_json_envelope_is_the_one_written_before` passes; it catches mutants 4a and 4b on its own |
| Forbidden: network or AWS access in any test | PASS | The core tests build records by hand. The S3 tests raise `NoCredentialsError` on moto's client at `before-sign`, before any request is sent. The CLI tests use the `bucket_mode` world (moto and respx) |
| Node: `uv run pytest packages/debate_core/tests -k bucket_mode` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k bucket_mode -n 4 --no-cov -q -p no:randomly`: `87 passed in 41.53s` |
| Closing checks (agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Red, then green

`dad1ca7` adds the tests and the adapter skeleton. Each of the four adapters takes `login_hint=` and
passes it to `S3Call.given_login_hint`, which `login_hint` did not yet read. So nothing failed on a
`TypeError`. Run over the five files (`-n 4 -p no:randomly --tb=line`):
`25 failed, 41 passed in 13.87s`, every failure an assertion.

| File | Failed | Passed | What failed |
|---|---|---|---|
| `test_caselist_sync_bucket_mode_banners_name_the_next_cloud_run.py` (new) | 8 | 7 | The stopped run, the four failed-stage cases, the backlog, the whole-text check, the runbook sections. The local cases and the parse-alone case passed |
| `test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud.py` (t25's) | 1 | 16 | The test this task changes on purpose |
| `test_s3_login_hint_for_a_bucket_mode_cloud_run.py` (new) | 10 | 10 | Every case with a hint given. The `aws sso login` cases passed |
| `test_bucket_mode_rerun_hint_names_the_cloud_run.py` (new) | 3 | 3 | The three bucket-mode next steps; the local ones passed |
| `test_bucket_mode_login_hint_names_the_task_role.py` (new) | 3 | 5 | The three cloud-run cases. The hand-run, local and local-in-a-task cases passed |

The red whole-command run showed the old wording in a cloud run's record:
`0 object(s) published, 1 snapshot(s) left for a later run: the AWS session for [redacted] is not usable: aws sso login (or set AWS_PROFILE to the evidence profile for this environment)`.

**Green** at `f627ba9`:

* The five files: `66 passed in 28.20s`.
* Core neighbours and the whole S3 adapter suite: `462 passed in 21.51s`. The neighbours are the
  files that pin these banners or read these records: `test_sync_runs_banners_say_what_waits.py`,
  `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`,
  `test_caselist_sync_owes_a_drifted_manifest_again.py`, `test_pull_stage_failure_codes.py`,
  `test_caselist_sync_publish_stage_loose_ends.py`, `test_pull_refuses_a_newer_fingerprint_table.py`,
  `test_pull_run_record_is_read_by_every_build.py`, `test_pull_parses_new_sources.py`,
  `test_pull_notification_says_retry_or_person.py`,
  `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`,
  `test_pull_refused_before_the_bucket_is_built.py`,
  `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py` and
  `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`, with
  `packages/debate_core/tests/integrations/s3`.
* CLI: `commands/test_caselist_pull.py`, t25's and t18's bucket-mode hint files,
  `test_bucket_mode_lock.py`, `test_container_factories.py`, `tests/docs` and
  `tests/scripts/test_check_command_blocks.py`: `368 passed in 59.65s`.
* `commands/test_publish_verify_parse_pull_panels.py`, the envelopes: `38 passed in 1.12s`.

The helper refactor (`4425426`) was run alone first, over t18's, t22's and t25's core files and
t18's and t25's CLI files: `48 passed in 11.11s`.

### Before and after

The same records and summary, through `notifications_for` and `_pull_failure`, at `dad1ca7` and
`f627ba9`. The script that printed them is in the session's scratch directory.

**An email banner** (bucket mode, the import and the publish failed on `STORE_UNAVAILABLE`), before:

> Run 20260916T060000Z (dev): the import stage failed on STORE_UNAVAILABLE; the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every failure here is one a later run may not meet. What was captured is kept.
>
> Fix: debate-research caselist pull

After:

> Run 20260916T060000Z (dev): the import stage failed on STORE_UNAVAILABLE; the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every failure here is one a later run may not meet. What the bucket confirmed is kept; the cloud run's working copy ends with its task.
>
> Fix: the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish from the operator's Mac

**A CLI line** (bucket mode, after a stage's own fix), before:

> This machine refused the inbox directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). Then run the same command again: what was captured is kept.

After:

> This machine refused the inbox directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). Then in bucket mode the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish from the operator's Mac.

**A record reason in a cloud run** (red run, then green run, of the same test). Before: `… is not
usable: aws sso login (or set AWS_PROFILE to the evidence profile for this environment)`. After:
`… is not usable: the PM looks into the cloud run's task role, which gave the run no AWS session
(caselist-cloud-run.md, "A run that found no AWS session"); never a login and a publish from the
operator's Mac`. The same pull run by hand on the Mac, before and after: `… is not usable: aws sso
login --profile debate-dev-evidence`.

### Mutants

How each one was run:

* One edit per mutant, applied by a script that checked the text occurred exactly once.
* Each run had a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis), the
  115-second hard stop, and `-n 4 -p no:randomly`.
* After each, `git checkout HEAD --` on the file. The tree was clean after every batch.
* Each run took 2 to 22 s.

The test sets:

* **Banner**: the new core file, t25's, `test_pull_notification_says_retry_or_person.py`,
  `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`,
  `test_pull_refused_before_the_bucket_is_built.py` and `test_sync_runs_banners_say_what_waits.py`
  (109 tests).
* **CLI**: the new CLI file, t25's CLI file, `commands/test_caselist_pull.py` and
  `commands/test_publish_verify_parse_pull_panels.py` (115).
* **Hint**: the two new login-hint files and `test_s3_error_mapping.py` (75).
* **JSON**: `commands/test_caselist_pull.py`, the envelopes file and t25's CLI file (109), and the
  envelopes file alone (38).

| # | Mutant | Result | Caught by (first few) |
|---|---|---|---|
| 1a | PM (1): the stopped run names the pull in bucket mode | CAUGHT, 2 failed | the stopped-run test, the whole-text check |
| 1b | PM (1): the failed-stage banner names the pull in bucket mode | CAUGHT, 6 failed | the four failed-stage cases, t25's changed test, the whole-text check |
| 1c | PM (1): the backlog banner names the pull in bucket mode | CAUGHT, 2 failed | the backlog test, the whole-text check |
| 1d | PM (1): a bucket-mode failed-stage banner keeps "What was captured is kept." | CAUGHT, 6 failed | the same as 1b |
| 1e | PM (1): the CLI's next step after a stage's own fix ignores bucket mode | CAUGHT, 1 failed | `[after_a_stages_own_fix]` |
| 1f | PM (1): the CLI's next step after a failed download ignores bucket mode | CAUGHT, 1 failed | `[a_failed_download]` |
| 1g | PM (1): the CLI's other next step ignores bucket mode | CAUGHT, 1 failed | `[any_other_stage]` |
| 2a | PM (2): the stopped run's cloud cure in local mode | CAUGHT, 3 failed | the local stopped-run test, two of `test_pull_notification_says_retry_or_person.py` |
| 2b | PM (2): the failed-stage cloud cure in local mode | CAUGHT, 5 failed | the four local failed-stage cases, and one more |
| 2c | PM (2): the backlog's cloud cure in local mode | CAUGHT, 1 failed | the local backlog test |
| 2d | PM (2): the local backlog fix loses "when the day's downloads reset" | CAUGHT, 1 failed | the local backlog test |
| 2e | PM (2): the cloud's last sentence in a local failed-stage banner | CAUGHT, 16 failed | the local failed-stage cases and earlier tasks' banner pins |
| 2f | PM (2): the CLI's cloud next step after a fix in local mode | CAUGHT, 6 failed | the local `[after_a_stages_own_fix]` case, and more |
| 2g | PM (2): the CLI's local next step after a fix reworded | CAUGHT, 2 failed | the local case, `test_the_json_envelope_is_the_one_written_before` |
| 2h | PM (2): the CLI's local next step after a failed download reworded | CAUGHT, 1 failed | the local `[a_failed_download]` case |
| 3a | PM (3): the hand-run bucket-mode hint is the task role's (no ECS check) | CAUGHT, 3 failed | `[bucket-mode-by-hand-on-the-mac]` of the adapter test and both whole-command cases |
| 3b | PM (3): any ECS task gets the task role's hint, local mode too | CAUGHT, 1 failed | `[local-mode-in-a-task]` |
| 3c | The takedown profile's adapters get the task role's hint | CAUGHT, 1 failed | the adapter test `[the-cloud-run]` |
| 3d | The run lock's object is built without the hint | CAUGHT, 1 failed | the adapter test `[the-cloud-run]` |
| 3e | The evidence bucket's object store is built without the hint | CAUGHT, 3 failed | the adapter test and both whole-command cloud cases |
| 3f | `S3Call.login_hint` ignores the hint given | CAUGHT, 12 failed | every given-hint case of the S3 test |
| 3g | The object store does not pass its hint to `S3Call` | CAUGHT, 3 failed | the object store's adapter case, both whole-command cloud cases |
| 4a | PM (4): the envelope's `run_details` renamed | CAUGHT, 4 failed | `test_the_json_envelope_is_the_one_written_before` (an assertion; alone, 1 failed of 38), plus three `KeyError`s |
| 4b | PM (4): the envelope's `summary_written_to` removed | CAUGHT, 5 failed | the same envelope test (alone, 1 failed of 38), plus `KeyError`s |

1e to 1g and 2f, 2h are caught only by this task's CLI file: `commands/test_caselist_pull.py` never
pinned these next steps. 3d is caught only by the test that records every adapter the container
builds. No whole-command test reaches the lock without a session, so that one test carries it.

### Closing checks

`uv run scripts/affected_tests.py` chose **329 of 607 test files** (54.2%) from 17 changed files, in
14.6 s. My first measurement was 330 with the container read whole: a changed module-level docstring
made it so. I reverted that docstring in `63d1903`, and the container is now read by part. The
size comes from the hub modules this task has to touch: `sync_runs.py`, `caselist_sync.py` and the
S3 errors module. t25's 297 took more than two minutes, so under agreement 10 the affected set is
left to the pull request's `ci`. It was not run whole and not handed over. Load averages were 5 to 38
from other sessions.

What ran, each under the hard stop:

| Run | Result |
|---|---|
| Always-run list plus the docs tests (`tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`, `-n 4`) | `653 passed in 29.09s` |
| The node criterion | `87 passed in 41.53s` |
| The five files of this task | `66 passed in 28.20s` |
| Core neighbours and `integrations/s3` | `462 passed in 21.51s` |
| CLI neighbours, container factories, docs tests | `368 passed in 59.65s` |
| The envelopes | `38 passed in 1.12s` |
| `bucket_mode/test_bucket_mode_lock.py` | `30 passed in 28.78s` |
| `bucket_mode/test_bucket_mode_restore.py`, `bucket_mode/test_parse_owed.py` | `21 passed in 42.00s` |
| `ruff format --check .` / `ruff check .` | `1686 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py --base <branch point>` | `All 61 indexed documents under docs/ have a description` / `OK: no # comments in 626 shell code blocks in 202 Markdown files (1 session reports changed since 66182c0…)` |
| `uv run scripts/validate_specs.py`, after setting the Goal | `OK: 537 files, 41 epics, 474 tasks, 22 releases` |

The whole `packages/debate_cli/tests/bucket_mode` directory, and then its first five files, were each
stopped by the hard stop at 115 s. Nothing was left running. The files the change reaches most were
run on their own (the lock, the restore, parse owed, and this task's and t25's files). The rest are
left to the PR's `ci`: backfile import, held sources and uploads, kills, removal and
restore-run-state. None of them sets `ECS_CONTAINER_METADATA_URI_V4`, so the S3 adapters get no hint
there and behave as before.

This spec on the local `origin/dev` ref (`59a5861`, not fetched) differs from mine only in its
phase. Dev has not touched any file this branch changes since the branch point.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `next_cloud_run(does,
  runbook=…)`, the one sentence every bucket-mode cure shares; `cloud_parse_cure` uses it.
* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `CLOUD_PUBLISH_CURE` and `CLOUD_PUBLISHED_AGAIN_CURE` through the helper, byte for byte.
  * New: `CLOUD_FAILED_RUN_RUNBOOK`, `CLOUD_UNFINISHED_RUN_CURE`, `CLOUD_BACKLOG_RUNBOOK` and
    `CLOUD_BACKLOG_CURE`.
  * `notifications_for`: the stopped run's fix, the failed-stage fallback's fix and last sentence
    (`cloud_kept`), and the backlog's fix, in bucket mode. Its docstring says so.
  * `CLOUD_NO_SESSION_CURE`'s docstring: it is the adapters' hint in a cloud run.
* `packages/debate_core/src/debate_core/integrations/s3/`:
  * `errors.py`: `S3Call.given_login_hint`, which `login_hint` returns when set; the module
    docstring says why.
  * `object_store.py`, `version_store.py`, `version_directories.py`, `run_lock_object.py`: a
    `login_hint=` keyword, passed to every `S3Call`.
* `packages/debate_cli/src/debate_cli/container.py`: `_ecs_task_metadata()` (the run lock now uses
  it) and `_s3_login_hint`. Six everyday-profile S3 adapter sites pass the hint. The takedown
  profile's two do not.
* `packages/debate_cli/src/debate_cli/commands/caselist_pull.py`: `_hint_for`'s three bucket-mode
  next steps.
* `docs/runbooks/caselist-cloud-run.md`:
  * New sections "A failed or stopped run" and "A backlog growing", which the new fix lines name.
  * In "A run that found no AWS session", one paragraph on the record reasons.
* Tests, new:
  * `packages/debate_core/tests/application/caselist/test_caselist_sync_bucket_mode_banners_name_the_next_cloud_run.py`
    (15 tests).
  * `packages/debate_core/tests/integrations/s3/test_s3_login_hint_for_a_bucket_mode_cloud_run.py`
    (20).
  * `packages/debate_cli/tests/bucket_mode/test_bucket_mode_rerun_hint_names_the_cloud_run.py` (6).
  * `packages/debate_cli/tests/bucket_mode/test_bucket_mode_login_hint_names_the_task_role.py` (8).
* Tests, changed: t25's mixed-failure test (renamed, new expectation, on purpose).
* The spec: Goal phase `Succeeded`.

## Deviations from the spec

1. **The CLI's other two "run the same command again" lines change too, in bucket mode.** The PM's
   context names the one after a stage's own fix. Two more lines are bucket-mode-blind: after a
   failed download, "Nothing that did download was lost: it is in the inbox and imported. Run the
   same command again — …"; after any other stage, "Run the same command again; every stage is
   idempotent." The spec's description says "the CLI's 'run the same command again'", which all
   three lines say. In a cloud run each is untrue: the inbox ends with the task (ADR-0020 (3)), and
   the command is the ended task's. This is the last pass, so leaving two would have meant a further
   task. All three now name the next cloud run in bucket mode, and local mode is unchanged and
   pinned. Reverting the two is one `if` each, and their tests drop with them.
2. **Two new runbook sections.** The PM said to change only the runbook lines that quote these
   messages. No line in the cloud runbook quoted any of them, and each new fix line names a section,
   as t18's, t22's and t25's do. So I added "A failed or stopped run" and "A backlog growing". Each
   quotes its fix line and says what happens next, what to do and what not to do. Neither has a
   command block. The other edit is one paragraph in "A run that found no AWS session", which quotes
   the record reasons.

## Decisions and assumptions

* **How the composition root tells the cloud task from a hand run.** It uses two things it already
  knows. One is bucket mode (`_in_bucket_mode`: `caselist.run_state = "bucket"` and a bucket named).
  The other is an ECS task: ECS sets `ECS_CONTAINER_METADATA_URI_V4` in every container it starts,
  and the run lock already reads it to choose `cloud` or `mac` as its holder (`v1-e40-t04`). Both
  together are the run task alone:
  * The login task (`login_task.tf`) is not in bucket mode.
  * A bucket-mode pull on the Mac has no ECS variable. Every dev build is in bucket mode since the
    cutover, so the mode alone would have given the Mac's hand runs the task role's hint (mutant 3a).

  There is no new setting. `_ecs_task_metadata()` is now shared with the run lock.
* **The hint is `CLOUD_NO_SESSION_CURE`, unchanged.** It is t22's login-banner fix: "the PM looks
  into the cloud run's task role, which gave the run no AWS session (caselist-cloud-run.md, "A run
  that found no AWS session"); never a login and a publish from the operator's Mac". It names the
  task role and the section the spec asks for, so the banner's fix and the record reasons say one
  thing. The section exists, and t25's test reads it by its heading.
* **Which adapters get it.** Every adapter the container builds with the everyday profile:
  * the evidence bucket's object store, both of its uses;
  * the version store, in `caselist status` and the removal planner;
  * the parsed store's version directories;
  * the run lock's object.

  The takedown profile's adapters get none anywhere: `DEBATE_REMOVAL_PROFILE` is an SSO profile an
  operator signs in to. Three other places get none either:
  * `build_s3_client`'s own `S3Call` (`CreateSession`). It only ever translates a profile the
    config lacks, and credentials resolve lazily, at an adapter's first call.
  * `S3SnapshotStore` and `StsCallerIdentity`. The CLI's container builds neither for a run.
* **"What was captured is kept." goes from every bucket-mode failed-stage banner but the parse
  alone.** The PM asked to keep it if still true. In a cloud run it is not, whenever an import or a
  publish failed. An archive downloaded and not imported, and a snapshot captured and not published,
  end with the task (ADR-0020 (3), "What is not saved"). t25's "What the bucket confirmed is kept;
  the cloud run's working copy ends with its task." is true in every case, so every such banner uses
  it. The parse alone keeps the old sentence and its t18 cure: its run published what it captured,
  and only the parsed store waits.
* **"More than the publish alone" covers every banner whose fix was the pull.** That is any
  failed-stage banner but the publish alone and the parse alone. The tests cover a download alone and
  a report stage alone as well as the mixed cases. Each named the pull, which mutant (1) forbids.
* **One sentence for every cure.** `next_cloud_run` keeps t25's "never a publish from the operator's
  Mac" for these cures too. It is still true, and it is the same words. The new cures do not say
  "never a pull from the operator's Mac": the cutover runbook keeps a fallback week on the Mac, and
  that decision is the PM's.
* **The CLI decides by the bracket's `bucket_mode`, the banners by the details' `bucket_run`**, as
  t22 and t25 do.
* **No record, details or envelope shape changed.** Earlier builds read these runs' files as before.
  The only difference is a free-text reason in a cloud run.
* **The new words reach the email only from an image built after this merges.** Both new runbook
  sections say an older image still names the pull, and that the rule holds for that email too.

## Operator follow-ups

None. The affected set (329 files) is left to the pull request's `ci`, per agreement 10.

## Follow-up work

1. **The OpenCaselist login banner in bucket mode** (E40). `caselist pull stopped: OpenCaselist login
   expired` names `debate-research caselist auth login` whatever the mode. A cloud run's token comes
   from the login task through Secrets Manager. The runbook knows (around "The task's own message
   still says to run `caselist auth login`; that wording is the Mac's"). The spec did not list it. It
   names no `caselist pull`, so this task's checks pass, but it is a Mac-side command for a cloud
   run's problem.
2. **The suppression list's fallback reason** says "could not be read without a login (…)". Its
   bracket now names the task role in a cloud run, but "without a login" is the Mac's word. It is a
   reason in a record, not a banner.
3. **The CLI and the banner disagree on one case, as t25 left it.** When a publish fails beside an
   import, the CLI's next step names t25's publish cure (`SyncStage.PUBLISH in stages`). The banner
   names the unfinished-run cure (a publish beside another stage). Both are true. If the PM wants
   them identical, it is one condition in `_hint_for`.

Questions for the PM:

> **v1-e40-t28: three questions**
> 1. **Deviation 1, the CLI's two extra next steps.** (a) **Keep them (recommended):** every bucket-mode "run the same command again" names the cloud run, and local mode is pinned unchanged. (b) Revert them to the PM's one line. Why (a): both are untrue in a cloud run (the inbox ends with the task), and this is the last pass.
> 2. **Follow-up 1, the OpenCaselist login banner in bucket mode.** (a) Leave it (recommended for now): it names no pull, and the runbook already says the task's wording is the Mac's. (b) A p3 task: in bucket mode its fix names the cloud's login task, not `caselist auth login`. Why (a): the PM files no more wording tasks unless a run's email shows one, and a cloud run has not sent this one.
> 3. **Follow-ups 2 and 3.** (a) Leave both (recommended): one is a record reason's word, the other two true hints that differ. (b) Fold them into the next task that touches `suppression.py` or `caselist_pull.py`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

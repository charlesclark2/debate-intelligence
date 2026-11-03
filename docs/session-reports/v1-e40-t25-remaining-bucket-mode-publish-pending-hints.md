# Session report: v1-e40-t25-remaining-bucket-mode-publish-pending-hints

| | |
|---|---|
| Task | `v1-e40-t25-remaining-bucket-mode-publish-pending-hints` — In bucket mode the failed-publish banners and the CLI's next step point at the cloud run, not a publish from the Mac |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t25-remaining-bucket-mode-publish-pending-hints.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t25-remaining-bucket-mode-publish-pending-hints.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t25-remaining-bucket-mode-publish-pending-hints` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

In bucket mode, the last hints that named a publish from the operator's Mac now point at the cloud
run:

* **A failed publish stage's banner.** Its fix is the next cloud run, which takes up what this run
  did not publish from the run state saved in the bucket. It no longer names `caselist pull
  --publish-pending`. Its last sentence is now "What the bucket confirmed is kept; the cloud run's
  working copy ends with its task." It used to say "What was captured is kept."
* **The "manifest published again" banner.** Its fix and its sentence say the same of what is owed
  again. It no longer says that "the publish uploads this machine's copy".
* **The CLI's own next step** for a failed publish says the same, starting "In bucket mode".
* **The login banner** starts "was left without an AWS session, and its working copy ends with its
  task", not "kept everything it fetched". A manifest owed again is said without "the publish after
  the login uploads this machine's copy".

The PM's amendment is done. The local parse fix now reads "The next pull does the same;
`caselist pull --publish-pending` does not." The bucket-mode newer-table hint now reads "The next
cloud run on an image whose fingerprint version is …". Both dropped "imports into", together with
the tests and the runbook paragraph that pin them.

Bucket mode is decided as `v1-e40-t22` decides it: the details' `bucket_run` for the banners, and
the bracket's `bucket_mode` for the CLI. Local mode keeps every word, apart from the amendment's
one sentence. No record or details model changed. `v1.1.0-dev.164` (the cloud image) and
`v1.1.0-dev.200` (the Mac's installed build) read every record and details line these runs write.
That is shown by the stored schemas and by each build's own reader.

**Look first at Decisions, "The suppression list's fallback reason".** It still quotes `aws sso
login`. That text comes from the S3 adapter, and three other record reasons quote it too. I left it,
for the reason given there.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `remaining-bucket-mode-publish-pending-hi` (Remaining bucket-mode hints) | Done | Red tests with a CLI skeleton (`a560256`); the code, the runbook and the amendment (`064fd7c`); three cross-build scenarios (`de0650f`). 19 mutants, plus mutant 3a against dev.164's and dev.200's own readers |

## Acceptance criteria

"dev.164" is `v1.1.0-dev.164` (`03b23e2`), the cloud image. "dev.200" is `v1.1.0-dev.200`
(`761b571`), the Mac's installed build. "The start commit" is `416951f`. All three were already
tags or commits in the local repository; no tag was fetched. Each was exported with `git archive`
into the session's scratch directory and put first on `PYTHONPATH`. Each reader printed the path
its `sync_runs` came from.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: in bucket mode the failed-publish banner, the published-again banner, the CLI's next step and the login banner's two sentences name the cloud run's cure and no Mac-side publish, by tests shown failing first | PASS | See [Red, then green](#red-then-green). Every sentence is pinned whole and written by hand. Each bucket-mode banner's whole text (`Notification.text`: message, hint and fix) holds none of `--publish`, `--publish-pending`, `caselist pull`, `aws sso login`, `imports into`, `this machine's copy`, `kept everything it fetched` or `What was captured is kept`. The CLI's next step and the banner of a whole bucket-mode `caselist pull` hold none of the first four or `this machine's copy` |
| **ac1**: local mode is unchanged | PASS | The local cases pin each old sentence whole: the failed-publish banner and its `--publish-pending` fix, the published-again banner and its fix, the login banner with a manifest owed again, and the CLI's `Re-run caselist pull --publish-pending`. Every one of them is in the same file as its bucket-mode case. `cloud` appears in no local banner. Earlier tasks' files pass unchanged, except where the amendment changes their pinned sentence |
| **ac1**: the cloud image and the Mac's installed build read every record written | PASS | **By schema:** `test_the_cloud_image_and_the_macs_build_read_every_record_and_details_line_these_runs_write[failed_publish, published_again, login_owed_again]`. Each run's record and details are in the bucket. The record validates against `record_schema_of_the_cloud_image.json`, which dev.164 and dev.200 both print. The details validate against dev.164's and dev.200's details schemas. Every stage entry has exactly `stage`, `outcome`, `reason`, and no details key is one dev.200 does not define. **By each build's own reader:** see [Every build reads this build's files](#every-build-reads-this-builds-files). **The check can fail:** mutants 3a and 3b |
| Node: Remaining bucket-mode hints tests pass (`uv run pytest packages/debate_core/tests/application -k caselist_sync`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application -k caselist_sync -n 4 --no-cov -q -p no:randomly` at the last commit: `275 passed in 47.54s` |
| PM amendment: the two "imports into" sentences, their tests and the runbook paragraph | PASS | The four core tests named in `v1-e40-t08`'s Follow-up 1 and t22's newer-table constant now pin the new sentences. A new test pins the "A new image, later" paragraph. Mutants 4a to 4c |
| Forbidden: a bucket-mode hint naming a command that publishes from the operator's working copy | PASS | ac1 above, and mutants 1a to 1h. See Follow-up work 1 for the bucket-mode banners outside this task that still name `debate-research caselist pull` |
| Forbidden: a record shape an earlier build refuses to read | PASS | No model changed. Mutants 3a and 3b are caught. dev.164's and dev.200's own readers refuse 3a |
| Forbidden: network or AWS access in any test | PASS | The core tests use moto under `tmp_path`, with t18's stand-in bracket. The CLI's whole-command test uses the `bucket_mode` world (moto and respx). The schemas and exports were read offline |
| PM: mutants (1) to (4), each caught (agreement 8) | PASS | 19 mutants, all caught. See [Mutants](#mutants) |
| Closing checks (working agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Red, then green

The tests were committed red in `a560256`, against the unchanged source. The commit also adds a
CLI skeleton: a `bucket_mode` keyword passed through `_pull_failure` to `_hint_for` and not used.
That way the CLI's unit test fails on its assertion, not on a `TypeError`. Every red failure below
is an `AssertionError` (`--tb=line`, grouped).

* **Core, 6 files** (`-n 4 -p no:randomly`): `19 failed, 100 passed in 5.91s`.
  * The new file has 9 failures. Each bucket-mode banner still had its Mac wording: `What was
    captured is kept.` with `--publish-pending` (2), the published-again sentence with `this
    machine's copy` (3), and `kept everything it fetched` (2). Both runbook tests failed: no section
    "A failed publish stage", and "that imports into" in "A new image, later".
  * t22's newer-table hint has 2 failures. `test_pull_parses_new_sources.py` has 5,
    `test_caselist_sync_names_publish_only_per_caselist.py` 2 and
    `test_pull_notification_says_retry_or_person.py` 1. All of these are the amendment's sentences.
  * The 8 of the new file that passed are the local cases, the mixed-stage case and the three schema
    cases. They hold on the unchanged source too.
  * `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`'s constant was updated for the
    amendment but passes either way. It is a hint written by hand into hand-made details, and the
    code never produces it there.
* **CLI** (`test_bucket_mode_publish_hint_names_the_cloud_run.py`): `2 failed, 1 passed in 5.25s`.
  The bucket-mode unit case and the whole-command case both still said "Re-run `caselist pull
  --publish-pending`". The whole command's premises held: exit `3`, and publish `failed` on
  `STORE_UNAVAILABLE`.

**Green** at the last commit:

* The new core file: `17 passed`.
* The CLI file with `test_bucket_mode_parse_fix_names_the_cloud_run.py` and `test_parse_owed.py`:
  `22 passed in 46.47s`.
* The ten core files that pin these banners or read these records, with
  `packages/debate_cli/tests/commands/test_caselist_pull.py`: `320 passed in 51.27s`. The ten are
  `test_sync_runs_banners_say_what_waits.py`,
  `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`,
  `test_caselist_sync_owes_a_drifted_manifest_again.py`, `test_pull_stage_failure_codes.py`,
  `test_caselist_sync_publish_stage_loose_ends.py`, `test_pull_refuses_a_newer_fingerprint_table.py`,
  `test_pull_run_record_is_read_by_every_build.py`, `test_pull_parses_new_sources.py`,
  `test_pull_notification_says_retry_or_person.py` and
  `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`.

### Every build reads this build's files

`write_parsed_stores_owed_files.py` gains three bucket-mode scenarios: `cloud_failed_publish`,
`cloud_published_again` and `cloud_login_owed_again`. `S` is the scratch directory. `W` is the
worktree; the three exported readers ran from a copy of `read_sync_run_files.py` in `S`, so that the
worktree's source was not on the path.

```bash
WRITE_PARSED_STORES_OWED_FILES="${S}/files/this-build" .venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_parsed_stores_owed_files.py -p no:cacheprovider --no-cov -n 0 -q
"${W}/.venv/bin/python" -I "${W}/packages/debate_core/tests/application/caselist/read_sync_run_files.py" "${S}/files/this-build" this-build
PYTHONPATH="${S}/dev164/packages/debate_core/src" "${W}/.venv/bin/python" "${S}/read_sync_run_files.py" "${S}/files/this-build" dev164
PYTHONPATH="${S}/dev200/packages/debate_core/src" "${W}/.venv/bin/python" "${S}/read_sync_run_files.py" "${S}/files/this-build" dev200
PYTHONPATH="${S}/start/packages/debate_core/src" "${W}/.venv/bin/python" "${S}/read_sync_run_files.py" "${S}/files/this-build" start
```

The writer printed `10 passed`. Each of the four reads exited 0 with `refused or skipped: 0`, over
ten scenarios. Between the start commit's output and this build's, exactly two lines differ. Both
are a banner this task moved, which each build makes from its own code:

```text
cloud_failed_publish   start: banner 'caselist pull failed: needs a person': fix 'debate-research caselist pull --publish-pending'
                       this:  banner 'caselist pull failed: needs a person': fix 'the next cloud run takes up what this run did not publish, from the run state saved in the bucket: ...'
cloud_published_again  start: banner 'caselist pull: publish a manifest again': fix 'debate-research caselist pull --publish-pending'
                       this:  banner 'caselist pull: publish a manifest again': fix 'the next cloud run takes up what is owed again, from the run state saved in the bucket: ...'
```

(The reader passes no retry rule to `notifications_for`, so every failed run is "needs a person"
there. The tests use the command's own rule.)

dev.200's output differs from the start commit's elsewhere as well. Those lines come from
`v1-e40-t22` and `v1-e40-t08`, which dev.200 predates. For every new scenario, dev.200 reads the
record as `SyncRunRecord` and the details as `SyncRunDetails`, in the bucket and on disk.

**Mutant 3a with each build's reader.** The record gained `cloud_publish_cure: bool = False`. The
three new scenarios were written on the mutant, and the source was then restored (`git checkout HEAD
--`; the record line held the key once). dev.164's reader: exit 1, `refused or skipped: 9`, starting
`REFUSED in the bucket: reports/sync-runs/2026/20260916T060000Z.json: 1 error(s)`. dev.200's reader:
the same.

### Mutants

Each mutant was a one-occurrence edit, applied by a script that checked the text occurred exactly
once. Each run used:

* a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis);
* the 115-second hard stop;
* `-n 4 -p no:randomly`;
* `git checkout HEAD --` on the file afterwards.

The tree was clean after each batch. Each took 6 to 34 s.

The test sets were chosen per mutant kind:

* **Banner** (1a–1f, 2a–2e): the new core file, t22's, `test_sync_runs_banners_say_what_waits.py`,
  `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`,
  `test_caselist_sync_owes_a_drifted_manifest_again.py`, `test_pull_stage_failure_codes.py`,
  `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py` and
  `test_pull_notification_says_retry_or_person.py` (154 tests).
* **CLI** (1g, 1h, 2f): the new CLI file and `commands/test_caselist_pull.py` (71).
* **Record** (3a, 3b): the new core file, t22's and `test_pull_run_record_is_read_by_every_build.py`
  (98).
* **Amendment** (4a–4c): the new core file, t22's, `test_pull_parses_new_sources.py`,
  `test_caselist_sync_names_publish_only_per_caselist.py` and
  `test_pull_notification_says_retry_or_person.py` (97).

| # | Mutant | Result | Caught by (first few) |
|---|---|---|---|
| 1a | PM (1): the failed-publish banner ignores bucket mode (`cloud_publish = only_publish and False`) | CAUGHT, 2 failed | the bucket-mode failed-publish test, the through-the-run `[bucket]` case |
| 1b | PM (1): its last sentence ignores bucket mode | CAUGHT, 2 failed | the same |
| 1c | PM (1): the published-again fix ignores bucket mode | CAUGHT, 3 failed | `[one]`, `[two]`, the through-the-run case |
| 1d | PM (1): the published-again sentence ignores bucket mode | CAUGHT, 3 failed | the same |
| 1e | PM (1): the login banner's start ignores bucket mode | CAUGHT, 2 failed | the login test with two owed, the through-the-run `[bucket]` case |
| 1f | PM (1): the login banner's owed-again clause ignores bucket mode | CAUGHT, 2 failed | the same |
| 1g | PM (1): the CLI's next step ignores `bucket_mode` | CAUGHT, 2 failed | the CLI unit `[bucket]` case, the whole-command case |
| 1h | PM (1): the command does not pass the bracket's `bucket_mode` | CAUGHT, 1 failed | the whole-command case |
| 2a | PM (2): the cloud failed-publish wording in local mode | CAUGHT, 9 failed | the local failed-publish test, the through-the-run `[local]` case, `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py` |
| 2b | PM (2): the cloud published-again fix in local mode | CAUGHT, 4 failed | the local published-again test, `test_sync_runs_banners_say_what_waits.py`, `test_sync_report_stage_keeps_what_it_found_and_its_kind.py` |
| 2c | PM (2): the cloud published-again sentence in local mode | CAUGHT, 4 failed | the same |
| 2d | PM (2): the cloud login start in local mode | CAUGHT, 11 failed | the login tests of `test_caselist_sync_owes_a_drifted_manifest_again.py` and `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`, the through-the-run `[local]` case |
| 2e | PM (2): the cloud owed-again clause in local mode | CAUGHT, 3 failed | the through-the-run `[local]` case, the owed-again login tests of the same two files |
| 2f | PM (2): the CLI's cloud next step in local mode | CAUGHT, 1 failed | the CLI unit `[local]` case |
| 3a | PM (3): the record gains `cloud_publish_cure: bool = False` | CAUGHT, 48 failed | this task's three schema cases, t22's, `test_pull_run_record_is_read_by_every_build.py` |
| 3b | PM (3): the details gain the same | CAUGHT, 16 failed | this task's three schema cases, t22's |
| 4a | PM (4): "imports into" back in the local parse fix | CAUGHT, 8 failed | `test_pull_parses_new_sources.py` (5), `test_caselist_sync_names_publish_only_per_caselist.py` (2), `test_pull_notification_says_retry_or_person.py` (1) |
| 4b | PM (4): "imports into" back in `NewerFingerprintTable.cloud_fix` | CAUGHT, 2 failed | t22's newer-table test and its monitor `[bucket]` case |
| 4c | PM (4): "imports into" back in the runbook paragraph | CAUGHT, 1 failed | `test_the_runbook_says_the_newer_table_cure_without_an_import` |

2f is caught by this task's unit case alone. `commands/test_caselist_pull.py` asserts only that a
stage's own fix is not followed by `--publish-pending`; it never pins the local next step.

### Closing checks

`uv run scripts/affected_tests.py` chose **297 of 590 test files** (50.3%) from 15 changed files, in
23.7 s. `v1-e40-t22`'s 298 took more than two minutes on this Mac. Under agreement 10 the affected
set is left to the pull request's `ci`. It was not run whole and not handed over. Load averages were
10 to 25 from other sessions. What ran, each under the hard stop:

| Run | Result |
|---|---|
| Always-run list plus the docs tests (`tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`, `-n 4`) | `653 passed in 78.66s` |
| The node criterion (`packages/debate_core/tests/application -k caselist_sync`) | `275 passed in 47.54s` |
| The files that pin this wording or read these records, and the CLI command's tests | `320 passed in 51.27s` |
| The bucket-mode CLI files for these hints | `22 passed in 46.47s` |
| `ruff format --check .` / `ruff check .` | `1652 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py` | `All 60 indexed documents under docs/ have a description` / `OK: no # comments in 601 shell code blocks in 199 Markdown files` |
| `uv run scripts/validate_specs.py`, after setting the Goal | `OK: 527 files, 41 epics, 464 tasks, 22 releases` |

A first run of the neighbouring files together with all of `packages/debate_cli/tests/bucket_mode`
was stopped by the hard stop at 115 s, at a load near 22. It left nothing running. It was split into
the two rows above, and `bucket_mode`'s other files, which this task does not reach except through
the publish hint, are left to the PR's `ci`.

This spec on the local `origin/dev` ref (`2c79cce`, not fetched) differs from mine only in its
phase.

## Files changed

* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `CLOUD_FAILED_PUBLISH_RUNBOOK`, `CLOUD_PUBLISH_CURE`, `CLOUD_PUBLISHED_AGAIN_RUNBOOK`,
    `CLOUD_PUBLISHED_AGAIN_CURE`, `_WHAT_THE_BUCKET_CONFIRMED_IS_KEPT` and
    `_LEFT_WITHOUT_A_SESSION`.
  * `_published_again(count, *, bucket=False)`.
  * `notifications_for` reads `details.bucket_run` for the failed-publish banner's fix and last
    sentence, the published-again banner's fix and sentence, and the login banner's start and
    owed-again clause. Its docstring says so.
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: the amendment's local
  sentence.
* `packages/debate_core/src/debate_core/application/caselist/occurrence_table_guard.py`: the
  amendment's `cloud_fix` and its docstring.
* `packages/debate_cli/src/debate_cli/commands/caselist_pull.py`:
  * `_pull_failure(..., bucket_mode=False)` and `_hint_for(..., bucket_mode=False)`; the command
    passes the bracket's `bucket_mode`.
  * The module docstring's "that imports into" goes too, for the amendment.
* `docs/runbooks/caselist-cloud-run.md`:
  * New sections "A failed publish stage", with a read-only block that reads the run's
    `bucket_run.bundle` from the bucket, and "A manifest published again".
  * "A run that found no AWS session" gives the login banner's new start.
  * "A new image, later" says the newer-table cure without "that imports into".
* Tests, new:
  * `packages/debate_core/tests/application/caselist/test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud.py`
    (17 tests).
  * `packages/debate_cli/tests/bucket_mode/test_bucket_mode_publish_hint_names_the_cloud_run.py`
    (3 tests).
* Tests, changed:
  * `write_parsed_stores_owed_files.py`: three scenarios.
  * The amendment's pinned sentences in `test_pull_parses_new_sources.py`,
    `test_caselist_sync_names_publish_only_per_caselist.py`,
    `test_pull_notification_says_retry_or_person.py`,
    `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py` and
    `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`.
* The spec: Goal phase `Succeeded`.

## Deviations from the spec

None. Everything changed is in the spec's packages.

## Decisions and assumptions

* **"Takes up", not "publishes".** A run saves its run-state bundle only when every snapshot it
  records is confirmed in the bucket (ADR-0020 (3), `RunState.save_bundle`). A run whose publish
  failed, or whose manifest differs from the bucket's, usually leaves the bundle it restored. The
  next run then publishes what that bundle holds and the pending-work file owes. A week after the
  bundle is fetched and imported again, within the day's downloads, so a run started by hand on the
  same day may leave it for later. "Publishes what this run did not" would promise something that
  run may not do. The runbook gives both paths, and the bundle line in the run's details that tells
  them apart.
* **"What the bucket confirmed is kept" replaces "What was captured is kept" on a bucket-mode
  failed publish alone.** The captured snapshots were in the cloud run's working copy, which ends
  with its task. On every other bucket-mode failed-stage banner the old sentence stays (Follow-up 1).
* **"this machine's" stays** in "differs from this machine's" and "found to differ from this
  machine's". In the cloud it is the run's task, which is literally true, and the drifted-again
  banners say the same. The forbidden phrase is "this machine's copy", the one that told the operator
  their Mac's copy would be uploaded. The new runbook section says "This machine" is the cloud run's
  task.
* **The login banner keeps "it is owed again" and "wait to be published"** and drops only the
  publish clause, as `v1-e40-t22` kept what waits and dropped the command. It makes no promise about
  what the next cloud run does: a run with no session may not have saved its state files either.
* **Titles are unchanged**, so `banner_words` and `caselist runs` are too. `caselist pull: publish a
  manifest again` is the existing title in both modes.
* **The CLI decides by the bracket's `bucket_mode`**, the composition root's own decision, as the
  service does. The banners decide by the details' `bucket_run`. That is t22's split.
* **The suppression list's fallback reason: left as it is, and here is why.**
  `LocalFallbackSuppressionList` writes `the bucket's copy could not be read without a login
  (<the error>)`. The error is the S3 adapter's `StoreCredentialsExpired`, whose message ends with
  `ErrorContext.login_hint` (`debate_core/integrations/s3/errors.py`). The cloud task sets
  `DEBATE_STORAGE__S3__AWS_PROFILE` empty, so the reason reads `… (no usable AWS credentials: aws sso
  login (or set AWS_PROFILE to the evidence profile for this environment))`. Four other places put
  the same text into a record reason:
  * the publish stage's `nothing more was attempted: …` and its pending reason (`caselist_sync.py`);
  * the parse stage's pending reason (`no_session = str(expired)`);
  * the report stage's pending reason;
  * the search index stage's (`search_index_refresh.py`).

  These are record reasons, not hints: `notifications_for` builds no banner from a reason. Rewriting
  the suppression list's alone would leave the other four. The one place to change it is the
  adapter's hint, which is `debate_core.integrations` and outside this task's packages. Follow-up 2
  proposes it.

## Operator follow-ups

None. The affected set (297 files) is left to the pull request's `ci`, per agreement 10. The cloud
run prints the new wording only from an image built after this merges (`caselist-cloud-run.md`, "A
new image, later"). Both new runbook sections say the rule holds for an older image's email too.

## Follow-up work

1. **Bucket-mode banners that still name `debate-research caselist pull`** (E40). They are outside
   this task's three and were left as they are:
   * `PULL_COMMAND` as the fix of a run that stopped on an error;
   * a failed-stage banner whose failed stages are more than the publish alone (pinned as it is by
     `test_a_bucket_mode_publish_that_failed_beside_another_stage_keeps_its_fix`, which also keeps
     "What was captured is kept." there);
   * the backlog banner's `debate-research caselist pull (again tomorrow, …)`.

   None publishes from the Mac by itself. In bucket mode the Mac's command restores the bucket's
   working copy first. But each names a Mac-side run for a cloud run's problem. The CLI's "Then run
   the same command again: what was captured is kept." after a stage's own fix is the same case.

   Question for the PM:

   > **v1-e40-t25, Follow-up 1: should the remaining bucket-mode banners that name `caselist pull` point at the cloud run?**
   > (a) **One more p3 task (recommended):** the stopped-run, mixed-failure and backlog banners and the CLI's "run the same command again" name the next cloud run in bucket mode, decided as here.
   > (b) Leave them: they name no publish from the Mac's working copy, and the runbook's rule covers a cloud run.
   > Why (a): every other bucket-mode banner now names the cloud run, and these name the Mac's command for a cloud run's failure. The pattern is settled; it is about an hour.
2. **The S3 adapter's login hint in a cloud run** (E40). Every record reason that names an expired
   session quotes `aws sso login (or set AWS_PROFILE …)`. A cloud run has a task role, not an SSO
   session. Suggested: the composition root passes the S3 adapter a hint for the run's environment.
   In bucket mode that names the task role and `caselist-cloud-run.md`, "A run that found no AWS
   session". This changes the one source of all four reasons. It is `debate_core.integrations` and
   the container, so a task of its own.
3. **`caselist-scheduled-sync.md`, `NEWER_FINGERPRINT_TABLE`** (local runbook, around its "Until then
   every pull that imports into the caselist fails its parse stage the same way") describes the rule
   before `v1-e40-t08`. A refused caselist stays owed, so every pull parses it and fails the same
   way, whatever it imports. The amendment named the cloud runbook's paragraph only, so I left this
   one. It is a one-line doc fix for whichever task touches that runbook next.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The last bucket-mode hints that named a publish from the Mac now point at the cloud run, and both
"imports into" sentences are gone.
1. **ac1 and the amendment pass.**
   * Red: 19 core and 2 CLI tests failed, every one an assertion. The CLI skeleton made the unit case
     fail on its assertion, not on a `TypeError`. Good.
   * Green: 17, 22, 320 and 275, across the new file, the CLI files, the neighbours and the node
     criterion.
   * Every bucket-mode banner's whole text is checked against the forbidden phrases.
   * 19 mutants were caught, including all three amendment ones, and 3a by dev.164's and dev.200's
     own readers.
2. **Decisions accepted:**
   * "takes up", not "publishes", because the bundle may not be saved;
   * "what the bucket confirmed is kept" on the bucket-mode failed publish alone;
   * "this machine's" kept where it is literally true of the task;
   * titles unchanged;
   * t22's split between the bracket and the details.

   Leaving the suppression fallback's quoted login was right: it comes from the S3 adapter's hint,
   which four other reasons share.
3. **Follow-ups:**
   * **1 and 2: (a), as one p3 task, the last pass on bucket-mode wording.** The stopped-run,
     mixed-failure and backlog banners, and the CLI's "run the same command again", name the next
     cloud run. The composition root also passes the S3 adapter a login hint for the run's
     environment, so every record reason in a cloud run names the task role and the runbook's "A run
     that found no AWS session", not `aws sso login`. After that task, the PM files no further
     bucket-mode wording tasks unless a run's email shows one.
   * **3:** the PM's next batch fixes the local runbook's `NEWER_FINGERPRINT_TABLE` line.
4. **Closing checks:** the affected set (297 files) is left to the PR's `ci` under agreement 10. The
   always-run list, the node criterion, the neighbours and the whole-repo checks pass.
5. **Merge:** once the PR's `ci` is green, ideally before Monday's image deploy so the new wording
   rides along. That is not required. It is a plain `scripts/task pr`.

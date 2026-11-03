# Session report: v1-e40-t18-cloud-parse-stage-cure

| | |
|---|---|
| Task | `v1-e40-t18-cloud-parse-stage-cure` — In bucket mode a failed parse stage names the cloud cure, never a publish from the operator's Mac |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t18-cloud-parse-stage-cure.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t18-cloud-parse-stage-cure.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t18-cloud-parse-stage-cure` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

In bucket mode, a parse stage that did not publish a caselist's parsed store now names the cloud
cure and no command. That holds in its hint (its reason, when pending), the failed-stage banner, the
login banner and what the run records. The cure is the next cloud run that imports into the
caselist, weekly or started by hand. Local mode keeps `v1-e34-t31`'s command for each caselist.

Bucket mode is decided from what is already known, with no new environment check. The pull is told
by the composition root (`bucket_mode=self._in_bucket_mode`, a new keyword beside
`working_copy_outlives_the_run`). The banners read the run's own details: `bucket_run` is set exactly
in bucket mode (`v1-e40-t04`). Nothing is added to `SyncRunRecord`, `StageEntry` or
`SyncRunDetails`.

`v1.1.0-dev.155`, `v1.1.0-dev.164` (the cloud image) and the start commit `650a655` read every record
and details line this build writes, by schema test and by each build's own readers.
`caselist-cloud-run.md`'s "A failed parse stage" now quotes what the run prints and keeps the
never-on-the-Mac rule.

**Look at Deviation 1 first.** "The next weekly run re-parses and publishes the caselist" holds only
for a run that imports into it: the run parses only the caselists it imported. The text says so,
and a run started by hand cures under the same condition. The question for the PM is about
`v1-e40-t08`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cloud-parse-stage-cure` (Bucket-mode parse cure) | Done | Red tests against a skeleton (`7eef4ff`), then the stage's fix text, the banners, the composition root, docstrings, two runbooks, dev.164's stored schema and two cross-build scenarios (`3b51850`); 11 mutants plus mutant 3a against dev.164's own reader |

## Acceptance criteria

"dev.155" is the tag `v1.1.0-dev.155` (`76b53e7`, the Mac's build at the cutover). "dev.164" is
`v1.1.0-dev.164` (`03b23e2`), the cloud run's image since 2026-10-29. "The start commit" is
`650a655`, this branch's start. Each was exported with `git archive` into the session's scratch
directory and put first on `PYTHONPATH`; each reader printed the path its `sync_runs` came from. No
tag was fetched and no installed build was opened. "Red" means the tests committed in `7eef4ff`, run
against that commit's skeleton: `cloud_parse_cure`, `CLOUD_PARSE_STAGE_RUNBOOK` and the service's
`bucket_mode` keyword exist there, and nothing uses them.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a bucket-mode run whose parse stage failed names the cloud cure and no Mac-side publish, in the fix text, the banner and the record, by tests shown failing first | PASS | `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py` and the renamed `bucket_mode/test_bucket_mode_parse_fix_names_the_cloud_run.py`, run as `.venv/bin/python -m pytest <both files> -p no:randomly -n 0 --no-cov`. **Red:** `7 failed, 7 passed`. The failures: the weekly's hint was `` `debate-research caselist parse --caselist testcl26 --publish` publishes a caselist's parsed store: … `` where the cloud sentence was expected; the same for two caselists; the pending reason held that command; bucket-mode details that name no caselist gave `debate-research caselist parse --caselist <slug> --publish`; the runbook's section still said the run names `--publish`; `service._bucket_mode` was `False` in bucket mode; and the end-to-end CLI pull's hint was the `--publish` sentence. The 7 that passed hold on the skeleton too: local mode's two tests, the two schema tests, and three wiring cases. **Green:** `14 passed in 6.88s`. Each sentence is pinned whole by hand. The hint is `The cloud run publishes the parsed store of testcl26, never the operator's Mac, whose working copy is not the one the cloud run owns: the next weekly run that imports into a caselist rebuilds its parsed store and publishes it, and so does a run started by hand that imports into it (caselist-cloud-run.md, "A failed parse stage").` The banner's fix is `the next cloud run that imports into testcl26 publishes that caselist's parsed store: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed parse stage"); never a publish from the operator's Mac`. Neither `--publish` nor `caselist parse` appears in the hint, the banner's whole text, the record's parse reason or the details' parse hint. Two caselists are named `testcl26 and openev` and `testcl26 or openev`. The login banner ends ` The parsed store waits too: <the fix>.` Details that name no caselist give the cure with `a caselist the parse stage names`. **Through the real command:** a seeded bucket, week three pulled in bucket mode with the parsed publish refused. The envelope's parse hint, the details kept (`bucket_run` set, `parsed_stores_owed` one entry) and the banner `notifications_for` builds from them all say the same |
| **ac1**: a local-mode run is unchanged | PASS | The same run on the Mac names `debate-research caselist parse --caselist testcl26 --publish-only; debate-research caselist parse --caselist openev --publish`, and `cloud` is nowhere in the banner. Local details naming no caselist give `PARSE_COMMAND`. Every `v1-e34-t31` test passes unchanged: `-k caselist_sync`, `244 passed`, and the neighbouring files below |
| **ac2**: the earlier builds read every record this build writes, by test | PASS | **By schema:** `test_the_earlier_builds_read_every_bucket_mode_record_and_details_line_this_build_writes`. A bucket-mode run owing two parsed stores writes one record line and one bucket record, which validate against dev.164's record schema (new, `record_schema_of_the_cloud_image.json`) and against `v1-e34-t19`'s start commit's. Its details, local and in the bucket, validate against `details_schema_before_parsed_stores_owed.json`, which dev.164 prints byte for byte too. Every stage entry has exactly `stage`, `outcome`, `reason`. The only details key the earlier schema does not define is `v1-e34-t31`'s `parsed_stores_owed`. A companion test shows the cloud image's schema refuses a stage entry with one more key. **By each build's own readers:** see [Every build reads this build's files](#every-build-reads-this-builds-files). dev.155, dev.164 and the start commit exit 0 with `refused or skipped: 0` on five scenarios, two of them new and in bucket mode. **The check can fail:** with mutant 3a applied, dev.164's reader exits 1 with `refused or skipped: 15` |
| **ac2**: `caselist-cloud-run.md`'s "A failed parse stage" names what the run now says | PASS | The section quotes the hint and the fix line with `<slug>`, says when nothing needs doing, says the run parses only what it imports, points to Step 8's "One run by hand", and keeps the rule: "**Never run `caselist parse --caselist <slug> --publish` on the operator's Mac**, nor `--publish-only`". `test_the_runbook_section_the_run_names_says_what_the_run_now_says` holds the section to the code's words and the Step 8 anchor to its heading. It was red against the PM's placeholder text |
| Node: Bucket-mode parse cure tests pass (`uv run pytest packages/debate_core/tests/application -k caselist_sync`) | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application -k caselist_sync -n 4 --no-cov` under a 115 s hard stop: `244 passed in 17.23s` |
| Forbidden: a bucket-mode fix text naming a command that publishes from the operator's working copy | PASS | ac1 above, and mutants 1a, 1b, 1c, 1d, each caught |
| Forbidden: a record shape an earlier build refuses to read | PASS | ac2 above. Mutants 3a (a stage entry gains `bucket_mode`) and 3b (the record gains `parse_cure`) are each caught by the new schema test and by `v1-e34-t19`'s every-build tests. 3a is also refused by dev.164's own reader |
| Forbidden: network or AWS access in any test | PASS | The core tests run against moto under `tmp_path`, with `v1-e34-t31`'s scripted parse stage and a stand-in bracket. The CLI tests use `bucket_mode/conftest.py`'s world (moto, respx, the fictional site). The stored schema was printed offline from a local export |
| PM: mutants (1) to (3), each caught (agreement 8) | PASS | 11 mutants, all caught. See [Mutants](#mutants) |
| Closing checks (working agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Every build reads this build's files

`write_parsed_stores_owed_files.py` (not collected) gains two scenarios, both runs in bucket mode as
the composition root builds it, whose details carry `bucket_run`:

* `cloud_one_of_each_failed`: the weekly's publish refused, and the camp file's rebuild read the
  run's own copy of the list.
* `cloud_pending`: a stage pending on a login.

`read_sync_run_files.py` now also prints, for files carrying `parsed_stores_owed`, whether the build
kept `bucket_run`, the parse hint as it kept it, and the login banner's sentence in either form. `S`
is the scratch directory:

```bash
WRITE_PARSED_STORES_OWED_FILES="${S}/files/this-build" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_parsed_stores_owed_files.py -p no:cacheprovider --no-cov -n 0 -q
.venv/bin/python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/dev155/packages/debate_core/src" .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" v1.1.0-dev.155
PYTHONPATH="${S}/dev164/packages/debate_core/src" .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" v1.1.0-dev.164
PYTHONPATH="${S}/start/packages/debate_core/src" .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit-650a655
```

The first wrote `5 passed`; the four reads each exited 0 with `refused or skipped: 0`. dev.155's
output and dev.164's are identical after the first line. Each build makes its own banners, as
`v1-e34-t31` found, so dev.164's of a cloud run still say `--publish`. Part of dev.164's output:

```text
cloud_one_of_each_failed:
  record 20260916T060000Z: incomplete; select completed, download completed, import completed, publish completed, parse failed, search_index skipped, landscape skipped, report completed, retention completed
  details 20260916T060000Z as written: parsed_stores_owed [{'caselist': 'testcl26', 'publish_only': False}, {'caselist': 'openev', 'publish_only': False}]
    kept by this build: parsed_stores_owed unknown here
    kept by this build: bucket_run kept; parse hint 'The cloud run publishes the parsed store of testcl26 and openev, never the operator\'s Mac, ...'
  banner 'caselist pull finished with a failed stage': fix 'debate-research caselist parse --caselist <slug> --publish'
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
```

This build, on the same files: `fix 'the next cloud run that imports into testcl26 or openev publishes
that caselist\'s parsed store: …; never a publish from the operator\'s Mac'`. For `cloud_pending` its
login banner reads `the parsed store waits too: the next cloud run that imports into testcl26 …`.

The record keeps the runbook name unredacted in a pending reason: `… (caselist-cloud-run.md, "A
failed parse stage").; this machine's copy of the suppression list alone was read: …`.

The schemas were printed by each build with the commands in `stored_run_records/README.md`. dev.164's
record schema differs from `record_schema_of_the_start_commit.json` only in two descriptions, and is
byte for byte dev.155's and `650a655`'s. Its details schema is byte for byte
`details_schema_before_parsed_stores_owed.json`.

### Mutants

Each mutant was a one-occurrence edit of the source, run on seven test files: the new core file,
`v1-e34-t31`'s file, `test_pull_run_record_is_read_by_every_build.py`, the two banner files,
`test_pull_parses_new_sources.py` and the CLI file. Each run used `-n 4`, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis), a 110 s hard stop on the
interpreter, and `git checkout HEAD --` afterwards. The tree was clean at the end. 16 to 21 s per
mutant.

| # | Mutant | Result | Caught by (first few) |
|---|---|---|---|
| 1a | PM (1): the stage ignores bucket mode (its fix names `--publish` again) | CAUGHT, 4 failed | failed stage, two caselists, pending stage, the CLI pull |
| 1b | PM (1): the banner ignores the details' `bucket_run` | CAUGHT, 5 failed | the same, and details that name no caselist |
| 1c | PM (1): the composition root never says bucket mode | CAUGHT, 2 failed | `test_the_pull_is_told_whether_it_runs_in_bucket_mode[bucket-True]`, the CLI pull |
| 1d | PM (1): the login banner's sentence takes local mode's form | CAUGHT, 1 failed | pending stage |
| 2a | PM (2): the stage names the cloud cure in local mode too | CAUGHT, 13 failed | `v1-e34-t31`'s local-list, one-of-each and other-way-round tests |
| 2b | PM (2): the banner names the cloud cure in local mode too | CAUGHT, 17 failed | the same, the entry that does not say, the unmodelled publish bug |
| 2c | PM (2): the composition root says bucket mode in local mode | CAUGHT, 1 failed | `test_the_pull_is_told_whether_it_runs_in_bucket_mode[local-False]` |
| 3a | PM (3): a stage entry gains `bucket_mode: bool = False` | CAUGHT, 36 failed | `v1-e34-t19`'s every-build tests, `v1-e34-t31`'s and this task's schema tests |
| 3b | PM (3): the record gains `parse_cure: str = "cloud"` | CAUGHT, 44 failed | the same |
| 4 | the banner's cure drops the caselists it owes | CAUGHT, 4 failed | failed stage, two caselists, pending stage, the CLI pull |
| 5 | the stage's cure names the first of several caselists | CAUGHT, 1 failed | two caselists |

**Mutant 3a, again, with each file and reader.** Against the new core file alone: `1 failed, 8
passed`, the failure being the bucket-mode schema test. Its files written and read by dev.164's own
reader: exit 1, `refused or skipped: 15`. Each scenario printed `REFUSED in the bucket:
reports/sync-runs/2026/20260916T060000Z.json: 9 error(s)`, and 10 warnings read `caselist run log:
line 1 is not a valid run record; skipped`.

### Closing checks

`uv run scripts/affected_tests.py` chose **281 of 575 test files** (48.9%) from 16 changed files.
`v1-e34-t31`'s 264 took more than two minutes on this Mac, so under agreement 10 the affected set is
left to the pull request's `ci` and was not handed over. Load averages were 15 to 39 from other
sessions throughout. What ran, each under a hard stop on the interpreter:

| Run | Result |
|---|---|
| Always-run list plus the docs checks (`tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`) | `626 passed in 48.18s` |
| The node criterion (`packages/debate_core/tests/application -k caselist_sync`) | `244 passed in 17.23s` |
| Files that pin this wording or read these records: `test_pull_parses_new_sources.py`, `test_pull_notification_says_retry_or_person.py`, `test_pull_refuses_a_newer_fingerprint_table.py`, the two banner files, `test_pull_run_record_is_read_by_every_build.py`, `test_inbox_retention.py`, `test_pull_stage_failure_codes.py`, `packages/debate_core/tests/integrations/sns`, `tests/docs`, `tests/scripts/test_check_command_blocks.py` | `468 passed in 24.28s` |
| `packages/debate_core/tests/application/caselist` (the test directory of what changed) | **Cut off** by the 115 s alarm: 1440 of 1668 passed and none failed before the cut. Left to CI |
| `packages/debate_cli/tests/bucket_mode` (the other) | **Cut off** by the 115 s alarm: 111 of 137 passed and none failed before the cut. The renamed file passed whole on its own (5 tests). Left to CI |
| `ruff format --check .` / `ruff check .` | `1614 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `scripts/check_thin_handlers.py` | `19 kept, 0 broken` / `68 … handlers within 25 statements` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py` | `All 59 indexed documents under docs/ have a description` / `OK: no # comments in 588 shell code blocks in 198 Markdown files` |
| `uv run scripts/validate_specs.py`, after setting the Goal | `OK: 509 files, 40 epics, 447 tasks, 22 releases` |

After each cut-off I checked that no pytest process from this worktree remained. `origin/dev` has
moved by `v1-e30-t30` and `v1-e37-t11`. Neither touches a file this branch changes (checked with
`git diff --name-only`), so no sync was made.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  * `CLOUD_PARSE_STAGE_RUNBOOK`, `cloud_parse_cure(caselists)`, `_or_listed` and `_and_listed`.
  * `CaselistSyncService(bucket_mode=False)`.
  * `_unpublished_parsed_store_fix(owed, *, bucket_mode)`, whose bucket-mode branch is the cloud
    sentence.
  * The module docstring: "A bucket-mode run names no command".
* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `parse_commands(details)` names the cloud cure when `details.bucket_run` is set.
  * `_the_parsed_store_waits_too` gives the login banner's sentence in either mode.
  * Docstrings of `PARSE_COMMAND` and `SyncRunDetails.parsed_stores_owed`.
* `packages/debate_cli/src/debate_cli/container.py`: `bucket_mode=self._in_bucket_mode`.
  `commands/caselist_pull.py`: its parse-stage paragraph.
* `docs/runbooks/caselist-cloud-run.md`: "A failed parse stage" rewritten. `caselist-scheduled-sync.md`:
  the bucket-mode sentence under "A failed parse stage" now points there.
* Tests, new:
  * `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py` (9 tests).
  * `stored_run_records/record_schema_of_the_cloud_image.json`, with its README row and commands.
* Tests, changed:
  * `bucket_mode/test_bucket_mode_parse_fix_names_publish.py`, renamed to
    `…_names_the_cloud_run.py`: its docstring, the `bucket_mode` wiring case and the end-to-end pull.
  * `test_inbox_retention.py`: `Installation.sync(bucket_mode=False)`.
  * `write_parsed_stores_owed_files.py` and `read_sync_run_files.py`: the two scenarios and the extra
    lines above.

## Deviations from the spec

1. **The cure holds only for a run that imports into the caselist, and the text says so.** The
   spec's description and the PM's context say "the next weekly run re-parses and publishes the
   caselist; if it can't wait, a run started by hand". In the code, a pull parses only the caselists
   it imported (`caselists_to_parse(tally.publish_targets)`). A weekly run with nothing new for a
   caselist parses nothing of it. So does a run started by hand straight after the failed run, which
   finds nothing new to import. When the next run does import into the caselist, it does cure it. The
   restore brings back the bucket's parsed store and the skip records with it. The pipeline then
   parses every source the store lacks, the failed week's included, rebuilds the aggregates and
   publishes. So the hint says "the next weekly run that imports into a caselist … and so does a run
   started by hand that imports into it". The runbook says plainly that `openev` waits for its next
   camp file and that a run by hand started straight away parses nothing. This is the gap
   `v1-e40-t08` (parse owed, Pending) describes for a killed run, but that spec clears its entry when
   a snapshot's *parse* completes, which a failed parsed-store publish would do. Question for the PM:

   > **v1-e40-t18, Deviation 1: what cures a failed cloud parse stage for a caselist with nothing new to import?**
   > The run parses only the caselists it imports into, so the cure this task names waits for the next import into that caselist (for `openev`, the next camp file), and a run by hand cures it only if it imports into it.
   > (a) **Amend `v1-e40-t08` (recommended):** clear its parse-owed entry only when the snapshot's parsed store is *published* complete, so that a failed parse stage leaves the entry, and the next cloud run, weekly or by hand, parses and publishes it whether or not it imports. Then the hint's "that imports into a caselist" can go, in `v1-e40-t08`.
   > (b) Keep it as built and as written: the cure is the next import into the caselist, said plainly in the hint, the email and the runbook.
   > (c) A new E40 task for a parse-only cloud run started by hand.
   > Why (a): `v1-e40-t08` already builds "the next run parses what is owed even when it imports nothing", and one condition there closes this case with no new mode. (c) would duplicate it.
2. **There is no section "Start one run by hand" in `caselist-cloud-run.md`.** The PM's context names
   it. The nearest is Step 8's bold "**One run by hand.**", part of the cutover. The fix text names
   `caselist-cloud-run.md, "A failed parse stage"`, which exists and is tested to exist. That section
   links to Step 8's heading, also tested. I did not add or rename a heading: the Step 8 blocks are
   the cutover's, and a heading of their own is the PM's call.

## Decisions and assumptions

* **A new `bucket_mode` keyword on the pull, not a second meaning for
  `working_copy_outlives_the_run`.** That keyword's default, `False`, is what every test world gets
  when it builds the service directly. Read as "bucket mode", it would put the cloud cure into every
  such world. Both keywords default to off: local wording, and `--publish` for everything.
* **The banners decide from the details' `bucket_run`,** which is what the run recorded. dev.164
  writes it too, so its bucket-mode details, which carry no `parsed_stores_owed`, also get the cloud
  cure, with `a caselist the parse stage names`. In the composition root, both inputs come from the
  same settings (`_in_bucket_mode`, and `BucketRun.bucket_mode`).
* **No `--publish` anywhere in a bucket-mode parse cure,** so its hint drops local mode's
  "`caselist pull --publish-pending` does not" sentence. The tests assert neither `--publish` nor
  `caselist parse` appears.
* **The fix line is a sentence, not a command.** `Notification.fix_command` already carries prose in
  one place (`caselist pull (again tomorrow, …)`). In the cloud it is the email's `Fix:` line, and the
  macOS banner is never shown there.
* `cloud_parse_cure` lives in `caselist_sync` beside `parse_command`, which `sync_runs` already
  imports from it, so the two banners and the stage share one wording.

## Operator follow-ups

None. The affected set (281 files) is left to the pull request's `ci`, per agreement 10. The cloud
run prints the new wording only from an image built after this merges (`caselist-cloud-run.md`, "A
new image, later"). Until then dev.164 names `--publish`, and the runbook says the rule holds for
that email too.

## Follow-up work

1. **Deviation 1's `v1-e40-t08` condition** (E40), if the PM chooses (a).
2. **The login banner's fix in bucket mode** is still `aws sso login && debate-research caselist pull
   --publish-pending`, a publish of snapshots from wherever it is run. It is not this task's parse
   stage, and the cloud task's role credentials make it unlikely there. Whether a bucket-mode login
   banner should also name the cloud cure is an E40 question.
3. **Two other parse-stage hints are Mac-worded in bucket mode.** `_FAILURE_RATE_FIX` names
   `caselist parse --caselist <slug> --failures`, which is read-only and lists the Mac's own store's
   failures, not the cloud run's. `NewerFingerprintTable.fix` says "install that build for the weekly
   agent". Neither publishes anything; both point the operator at the wrong machine (E40).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

In bucket mode, a failed parse stage now names the cloud cure and no command, everywhere it speaks.
1. **ac1 passes.**
   * Red was 7 failed, 7 passed, and every failure was the `--publish` sentence where the cloud's was
     expected. Green is 14 passed.
   * The hint, the banner, the login banner's sentence, the record's reason and the details' hint
     are each pinned whole. None of them holds `--publish` or `caselist parse`.
   * The real command, against a seeded bucket, says the same in its envelope, its details and its
     banner.
   * Local mode is unchanged: v1-e34-t31's 244 pass untouched, and mutants 2a to 2c catch any leak of
     the cloud wording into it.
2. **ac2 passes, by schema and by each build's own reader.**
   * dev.155, dev.164 and 650a655 read all five scenarios with `refused or skipped: 0`.
   * Mutant 3a makes dev.164's own reader refuse 15, so the check can fail.
   * dev.164's stored schema is a good addition: the cloud image is now a reader the tests hold to.
3. **Decisions accepted:**
   * a `bucket_mode` keyword of its own, both keywords off by default;
   * the banners deciding from the recorded `bucket_run`, which also gives dev.164's details the
     cloud cure;
   * the fix line as a sentence, and one wording shared from `caselist_sync`.
4. **Deviation 1: (a), amend v1-e40-t08.** I checked it: its entry clears "when that snapshot's
   parse completes", and a parse that completes but fails to publish would clear it, which is the
   gap you found. The PM's next batch amends it so that the entry clears only when the snapshot's
   parsed store is published complete. The next cloud run then parses and publishes what is owed,
   whether or not it imports, and the hint's "that imports into" goes in that task. Until then
   your wording is the true one, and it stays.
5. **Deviation 2 accepted.** The context named a section that does not exist. Pointing at "A failed
   parse stage", which links to Step 8, is right, and no heading is needed for now.
6. **Follow-ups 2 and 3:** one p3 task in the next batch, so that bucket mode's other parse and login
   hints point at the cloud run rather than the Mac:
   * the login banner's `--publish-pending`;
   * `_FAILURE_RATE_FIX`;
   * `NewerFingerprintTable.fix`;
   * the pending reason's `").;` join, which it can tidy.
7. **Closing checks:** under agreement 10, the affected set (281 files) is left to the PR's `ci`.
   * Each cut-off run had no failure before its cut, and the renamed file passed whole on its own.
   * The always-run list (626), the node criterion (244) and the wording and record files (468)
     pass, as do ruff, pyright, lint-imports, the thin handlers, the docs index, the command blocks
     and the specs.
   * Its Goal is Succeeded and nothing is left to the operator, so the PR is a plain `scripts/task pr`.
8. **Merge:** once the PR's `ci` is green. The new wording reaches the email only with the next
   image, as the report says.

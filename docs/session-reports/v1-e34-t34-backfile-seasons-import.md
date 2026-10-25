# Session report: v1-e34-t34-backfile-seasons-import

| | |
|---|---|
| Task | `v1-e34-t34-backfile-seasons-import` — Earlier seasons' complete archives, from 2021-22 on, imported and parsed as backfiles |
| Spec | [`plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml`](../../plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t34-backfile-seasons-import` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built and tested; the operator's two runs are done; waiting for the PM's review and amendment of ac3.** The counts
(ac1) went to the PM, who ruled on 2026-10-25. This session then built the backfile marker
(`caselist.backfile_caselists`, holding the four approved complete archives in the dev and prod
profiles) and `debate-research caselist backfile-import` (a dry run, then `--execute`). The import
keeps its ledger in the bucket and takes the weekly run's lock per step. It refuses inside Tuesday
06:00 to Thursday 00:00 Chicago, on a spent budget of one a day, and on too little free space.
`caselist pull` and `landscape report` refuse a backfile. Removal, the suppression list and a path
hold reach it, each by test. The tests ran red first against a refuse-nothing skeleton, and all 7
mutants of the rules were caught.

**Read Deviation 1 first.** A backfile is imported as its own dated snapshot,
`manifests/<slug>/<date>.jsonl`, not into `v1-e34-t04`'s `full/<date>` namespace as the ruling said.
The parse pipeline reads only the dated series, so a `full/` backfile parses to nothing. The Goal
stays **InProgress** until the PM amends ac3. As written it asks for an import in dev, which moved to the
E40 task. The dry run the ruling put in its place ran on the Mac and refused as expected. The node's
criterion passed in the operator's run.

## The counts step (ac1)

The survey's tests: `test_caselist_backfile_survey.py` (core, 12; CLI, 7) and four `archive_size`
tests in `test_client.py`. A mutant that took the `HEAD` out of the download window (`download=False`)
failed `test_archive_sizes_are_paced_in_the_download_window_with_downloads`.

* **The size comes from a `HEAD`**, because the downloads listing carries no sizes. Each `HEAD` is
  paced as a download (8 a minute) and none is counted against the day's five bulk downloads, since
  no file is sent.
* **Parse time per source**: a sample of 100 DOCX sources each from this Mac's hsld26 and hspolicy26
  complete archives, parsed in one process with nothing written (2026-10-25, load average about 5):
  **LD 0.087 s, Policy 0.257 s**, 0 failures. The full pipeline's recorded wall-clock, with rebuild
  and publish (`docs/data/caselist-parse-report.md`, dev, 2026-10-12): LD 0.109 s, Policy 0.295 s.
  The estimates use the pipeline's figures.
* **Sources per archive, estimated**: a complete archive's zip is 1.043 × its members (hsld26:
  571,706,321 bytes against 548,239,217). This Mac's manifests give a mean of 129,935 bytes per LD
  source and 284,623 per Policy source. The parsed store is 3.96 × (LD) and 3.88 × (Policy) its
  sources' bytes.

| Caselist | Archive | Sources (est.) | Parse, rebuild, publish (est.) | Parsed store (est.) | Kept locally (est.) |
|---|---|---|---|---|---|
| `hspolicy25` | 3.96 GB | 13,300 | 66 min | 14.7 GB | 18.5 GB |
| `hsld25` | 4.37 GB | 32,200 | 59 min | 16.6 GB | 20.8 GB |
| `hspolicy24` | 2.56 GB | 8,600 | 42 min | 9.5 GB | 12.0 GB |
| `hsld24` | 3.97 GB | 29,300 | 53 min | 15.1 GB | 18.9 GB |
| **All four** | 14.86 GB | 83,500 | 3.7 h | 55.9 GB | 70.2 GB, plus one archive (up to 4.4 GB) in the inbox while it imports |

  Download time is not measured here (the run summaries keep sizes, not times): 2 to 12 minutes per
  archive at 50 to 200 Mbit/s. Import and publish of the sources at run 5's rate (2,177 members in
  161.5 s): about 40 minutes for an LD season. So 1.5 to 2.5 hours per caselist end to end. The
  bucket holds the same again: about 70 GB in dev, and in prod at the promotion.

## PM rulings applied (2026-10-25)

| Ruling | Where it is |
|---|---|
| Q1: order `hspolicy25`, `hsld25`, `hspolicy24`, `hsld24`; one complete archive per rolling 24 h; no import from Tuesday 06:00 to Thursday 00:00 Chicago, at the start and at each locked step; the weekly ledger never touched; the backfile ledger in the bucket; earliest Thursday 2026-11-05 | `backfile_import.py` (`in_no_import_window`, `BACKFILE_LEDGER_KEY`, `_locked`); `docs/runbooks/caselist-backfiles.md` |
| Q2: the `caselist.backfile_caselists` setting; overlap with `sync_caselists` refused; pull and landscape refuse; the import refuses what is not listed or is before 2021-22; the annual purge reads the same setting | `settings.py`; `caselist/backfiles.py`; `CaselistSyncService.plan`; `LandscapeRunService.run`; `test_the_annual_purge_keeps_what_the_setting_names` (against the accessor: `v1-e30-t28` has no code yet) |
| Q3: the four complete archives only; PF and the three HTTP-500 seasons marked not imported, with reasons | `docs/data/caselist-backfile-seasons.md`, "What is imported, and what is not" |
| Q4: runs unchanged in the caselist image (settings only; the token backend the environment's; the bucket's ledger and lock); a free-space precheck with both numbers; ac3 becomes the Mac's dry run; reuse t04's downloader | The container builds everything from settings. The downloader is `ArchivesResource.download` with the complete archive's ceiling. `space_needed`. Deviation 1 for the namespace |
| Q5: restore locked; download, import and parse not locked; publish and bundle locked; parsed store locked; the weekly run's lock; the rebuild in the runbook; bundle growth recorded; no index | `BackfileImportService.run`; `caselist-removal.md` steps 5 and P1b; "Bundle growth" below |

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `backfile-import` | Done | Counts (ac1), then the build (ac2). Its criterion passed in the operator's run: 2,016 passed |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any import, sent to the PM with a proposed order | PASS | `DEBATE_ENV=dev uv run debate-research --json caselist backfile-survey` (operator, 2026-10-25) → exit 0: 65 caselists listed, 15 surveyed, 17 listing requests, 4 size requests. The re-run with `--first-season 2021-22 --last-season 2023-24 --no-sizes` → exit 0: 9 × `PROVIDER_UNAVAILABLE (HTTP 500)`. Counts in [`docs/data/caselist-backfile-seasons.md`](../data/caselist-backfile-seasons.md); estimates under "The counts step". Sent as a relay prompt; the PM ruled the same day |
| ac2: with stand-in API and bucket, a backfile caselist imports, parses and publishes; the weekly run's caselists and the landscape never include it; a removal and a hold reach its sources; tests shown failing first | PASS | `packages/debate_cli/tests/bucket_mode/test_backfile_import.py` (20 tests, moto + respx, real composition root) and `packages/debate_core/tests/application/test_caselist_backfile_rules.py` (23). Red first, details below. Green: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_backfile_rules.py packages/debate_cli/tests/bucket_mode/test_backfile_import.py -q -n 4` → `43 passed` |
| ac3: the operator imports the first backfile caselist in dev and records its counts (to be amended by the PM: the Mac's dry run only) | NOT RUN as written; the ruled dry run done | As written (an import in dev), not run: the imports move to the PM's E40 task. The dry run the PM ruled ac3 becomes: `DEBATE_ENV=dev uv run debate-research --json caselist backfile-import --caselist hspolicy25` (operator, 2026-10-25) → exit 1, `RUN_STATE_NOT_SEEDED` and `NOT_ENOUGH_FREE_SPACE` (11,044,614,144 bytes free, 29,687,044,928 needed); archive 2026-06-30, 3,958,272,657 bytes; 1 download left; outside the window. Recorded in `docs/data/caselist-backfile-seasons.md`. The Goal stays InProgress until the PM amends ac3 |
| Node: `uv run pytest packages/debate_core/tests/application -k caselist` | PASS | Run by the operator at `a1756fc`, 2026-10-25: `2016 passed in 165.47s (0:02:45)`. Over two minutes on this Mac, so handed over rather than run in the session |

### Red first

Committed red as `646b116`: tests plus a refuse-nothing skeleton. On the skeleton,
`.venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_backfile_rules.py packages/debate_core/tests/application/test_caselist_sync_run_lock.py packages/debate_cli/tests/bucket_mode/test_backfile_import.py -q -n 4 -p no:randomly`
→ `30 failed, 30 passed`. Every new behavioural test failed: the window (7 cases), its end, the three
space cases, the pull and landscape refusals, and 17 of the 18 CLI tests then written. The 18th, a
profile naming a backfile among the weekly caselists, rests on the setting, which was already
written. The setting and the
lock re-take were already written, so their five tests were run against the start commit's
`settings.py` and `run_lock.py` instead → `5 failed`. The failures were the overlap, the
pre-2021-22 slug, the slug pattern and the accessor (`ValidationError`, extra field), and "the
second lease renews in the background".

### Mutants

Seven, on `backfile_import.py`, each against the two test files above, each with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (no property tests here; agreement 8 followed anyway). All caught:

| Mutant | Caught by |
|---|---|
| The window not asked again in a locked step | `test_a_window_that_opens_during_the_import_stops_the_next_locked_step_and_the_run_resumes_after_it` |
| The bundle's change not compared | `test_a_bundle_a_removal_rewrote_during_the_import_is_never_overwritten` |
| The download's start not recorded | `…imports_parses_and_publishes_as_its_dated_snapshot`, `…one_complete_archive_a_day…` |
| The lock held through the download | `test_the_lock_is_the_weekly_runs_taken_for_each_step_and_free_during_the_download` |
| The window opening at 05:00 | two window cases |
| The parsed store counted three times | five space tests |
| The budget never spent in the plan | `test_one_complete_archive_a_day_from_the_buckets_ledger_whatever_machine_asks` |

### What was run

The affected set (`uv run scripts/affected_tests.py`) is 341 of 494 test files, about four minutes of
the whole selection. Under agreement 10 it was not run and is left to the pull request's `ci`. Run
instead, in the session:

* `tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_core/tests/integrations/opencaselist tests/smoke/test_caselist_backfile.py` → `498 passed in 30.24s`
* `packages/debate_cli/tests/bucket_mode` (every bucket-mode test, the lock classification included) → `96 passed in 80.99s` (before the last two tests were added; those two then passed)
* `test_landscape_run.py test_landscape_command.py test_caselist_sync.py test_caselist_sync_full_archive.py test_caselist_sync_run_lock.py` → `187 passed in 16.83s`
* `test_settings_environments.py test_settings.py test_config_command.py` → `116 passed in 1.78s`
* The survey's tests and the new ones together → `83 passed in 26.37s`
* `ruff format --check packages tests/smoke` → 869 files already formatted; `ruff check packages tests/smoke` → all checks passed; `pyright packages/debate_core packages/debate_cli tests/smoke/test_caselist_backfile.py` → 0 errors; `lint-imports` → 16 kept, 0 broken; `scripts/check_thin_handlers.py` → 57 handlers within 25 statements; `scripts/validate_specs.py` → OK; `check_command_blocks.py`, `check_links.py`, `docs_index.py --check-descriptions` → OK

## Files changed

* `debate_core.application.caselist.backfile_import` (new): the rules, the plan and the four-step import.
* `debate_core.application.caselist.backfiles` (new): the pull and landscape refusals.
* `debate_core.application.caselist.backfile_survey` (counts step): the survey.
* `debate_core.application.settings`: `caselist.backfile_caselists`, its validators, `is_backfile`, `FIRST_BACKFILE_SEASON_START`.
* `debate_core.application.caselist_sync`: the sync service refuses a backfile in `plan`; `archive_entries`, a public name for the reader the pull uses.
* `debate_core.application.landscape_run`: refuses a backfile.
* `debate_core.application.caselist.run_lock`: a lease taken again after a release renews again.
* `debate_core.integrations.opencaselist`: the `HEAD` size (counts step).
* `debate_cli`: `caselist backfile-import` and `backfile-survey`, their container builders, their rows in the bucket-mode classification.
* `config/profiles/dev.toml`, `prod.toml`: the four backfiles.
* Tests: `test_caselist_backfile_rules.py`, `test_backfile_import.py`, the re-take test in `test_caselist_sync_run_lock.py`, `tests/smoke/test_caselist_backfile.py`, and the counts step's.
* Docs: `docs/runbooks/caselist-backfiles.md` (new), `docs/runbooks/caselist-removal.md` (steps 5 and P1b), `docs/data/caselist-backfile-seasons.md`.

## Deviations from the spec

1. **The backfile is its own dated snapshot, not `full/<date>`** (the ruling Q4 said "t04's
   downloader and `full/<date>` namespace", as I had proposed). Building it showed the proposal was
   wrong. The parse pipeline reads only the dated series (`enumerate_sources`, which never passes
   `full_archives=True`: a current caselist's complete archive re-lists what its weeklies hold), and
   it dates every card by its snapshot's name, `date.fromisoformat(snapshot)`. A `full/` backfile
   parsed to nothing in the first green run (`parsed 0, cards 0`). Making the pipeline read `full/`
   for backfiles would change `enumerate_sources` and its eight callers, the occurrence table's
   provenance included, which the current season shares. So the import keeps t04's downloader and
   the complete archive's own size ceilings. It files the archive with the weekly importer as the
   backfile's one dated snapshot, `manifests/<slug>/<date>.jsonl`, where parse, provenance, removal,
   holds, status and publish all read it unchanged. A backfile has no weekly series, so nothing
   collides. A later complete archive of the same backfile imports as its next snapshot against the
   previous one. **The PM may prefer the pipeline change instead.** Say so and it is a separate,
   larger task.
2. **Outside `constraints.packages`:** `tests/smoke/test_caselist_backfile.py` (working agreement 5:
   a new user-facing command gets a smoke check), and `.../tests/application/test_caselist_sync_run_lock.py`
   for the lock re-take.
3. **The lock module changed.** `BucketRunLock.start_renewing` used to return at once when it had
   ever started a thread, so a lease taken again after a release never renewed, while the bucket
   client's write fence asks that same lock object. A command that locks per step needs it to. One
   test (`test_a_lease_taken_again_after_a_release_renews_again`) was red on the start commit.
4. **The node's own criterion was run by the operator**, not the session: it took 165 seconds here.

## Decisions and assumptions

* **A backfile import is bucket-mode only** (`NOT_IN_BUCKET_MODE`), because its ledger and its lock
  are the bucket's. Prod is in local mode, so an `--execute` there is refused anyway. `--confirm-prod`
  is asked as well, as every other prod write asks.
* **The suppression list is the weekly pull's own** (`LocalFallbackSuppressionList`): both copies
  read as one, and a held upload recorded in this machine's copy, which the everyday credential may
  write. I first read both copies strictly. A hold during the unlocked import then tried to write
  the bucket's held-digest record and was refused (`RUN_LOCK_NOT_HELD`). The pull's rule is also
  what "exactly as they reach the current season" asks.
* **A dry run's exit code is 1 when the import would be refused**, naming every refusal, so that the
  two-block hand-off stops on it. It reads the bucket (the ledger, the seed, the manifest) and writes
  nothing.
* **The free-space estimate** is the archive in the inbox, its blobs (the archive's size again; a
  complete archive's members came to 0.96 of it), and the parsed store, 4 times (measured 3.96 for LD
  and 3.88 for Policy), plus 25%, rounded up. For `hspolicy25` that is 29,687,044,928 bytes. An archive
  already imported, or already in the inbox, needs no room for the inbox's copy.
* **Running the import again is the post-removal rebuild**, with no download and no budget. It
  restores the backfile's parsed store, rebuilds the aggregates a whole-file removal deleted, and
  publishes them. Tested: `test_running_it_again_rebuilds_the_aggregates_after_a_removal_with_no_second_download`.
  A backfile's parsed store is never on the Mac, so `caselist parse --publish` there cannot rebuild it.
* **The search index is untouched.** The weekly stage indexes its own caselists and a backfile
  import has no index stage. `tub index build --caselist <backfile>` by hand is not refused: that is
  `v1-e39-t18`'s decision.
* **No run record.** A backfile import is not a weekly run. It writes nothing to `reports/sync-runs/`
  (tested) and sends no notification.
* **The API gate first.** The container builds the OpenCaselist client before any bucket adapter, so
  an installation without `caselist.api_enabled` refuses a backfile command with
  `CASELIST_API_DISABLED`, as the smoke check pins.

### Bundle growth

Each imported backfile adds its manifest to the run-state bundle that every cloud weekly run restores
and saves: an estimated 15 to 17 MB uncompressed for an LD season (about 32,000 rows at the dev
manifests' measured 480 bytes per row), 4 to 7 MB for Policy, and a few MB compressed. Estimates, not
measurements. The first import records the real figure. The weekly run restores only its own
caselists' parsed stores, so a backfile's parsed store (10 to 17 GB, estimated) never enters its
scratch storage.

## Operator follow-ups

Both done on 2026-10-25: (1) `2016 passed in 165.47s`; (2) `exit 1`, refusals `RUN_STATE_NOT_SEEDED`
and `NOT_ENOUGH_FREE_SPACE`, recorded in `docs/data/caselist-backfile-seasons.md`. The blocks as handed
over:

**1. The node's acceptance criterion** (expected runtime 3 to 4 minutes on this Mac). Where: your
Mac, in this task's worktree.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t34-backfile-seasons-import
uv run pytest packages/debate_core/tests/application -k caselist
```

Success looks like `2016 passed` (or `passed` with no `failed` and no `error`) on the last line;
paste the last 5 lines back.

**2. ac3 as the PM ruled it: the dry run on the Mac** (expected runtime under a minute, after the
login). Where: the same worktree. It needs the dev evidence SSO session to read the bucket's ledger.
It makes one downloads listing and one `HEAD`, and downloads, writes and locks nothing. The block
stops if a `DEBATE_*` variable is set or a `caselist pull` is running, and sets `DEBATE_ENV=dev` for
the one command.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t34-backfile-seasons-import
aws sso login --profile debate-dev-evidence
```

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t34-backfile-seasons-import
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else DEBATE_ENV=dev uv run debate-research --json caselist backfile-import --caselist hspolicy25 > /private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e34-t34-backfile-seasons-import/e6cc4772-8e35-4b16-8a97-d019baa128ba/scratchpad/survey/backfile-dry-run.json; echo "exit $?"; fi
```

Success looks like `exit 1`, the refusal the PM expects today. The file then holds
`NOT_ENOUGH_FREE_SPACE`, with this Mac's free bytes against 29,687,044,928 needed. Before the
cutover's seed it also holds `RUN_STATE_NOT_SEEDED`. The plan in it shows `archive_date` 2026-06-30,
`archive_bytes` 3,958,272,657, `backfile_downloads_left` 1 and `inside_no_import_window` false. Paste
back the `exit` line. The session records the counts in `docs/data/caselist-backfile-seasons.md`. Run
on a Tuesday after 06:00 or a Wednesday, it shows `INSIDE_NO_IMPORT_WINDOW` as well. The tests show
the window and the budget refusals on every run.

## Follow-up work

* **The E40 one-off import task** (the PM is filing it): the caselist image's task definition with
  larger scratch storage, running `caselist backfile-import --caselist <slug>` (dry run, then
  `--execute`) with the weekly run's environment. The free-space check needs about 30 GB for
  `hspolicy25` and 33 GB for `hsld25`. The same task is where a backfile's post-removal rebuild runs.
* **A held upload's record in a cloud task.** Like the weekly cloud run's importers, the import
  records a held upload in its working copy's suppression files. In a cloud task those vanish when
  the task stops, and the removal runbook's "run the removal again" finds held uploads through the
  inbox, which is gone too. This is shared with the weekly cloud run (ADR-0020), so it is E40's to
  look at, not this task's.
* **No alert on a failed backfile import.** It is not a weekly run, so nothing announces a failure.
  The E40 task may want one.
* **Whether the parse pipeline should read `full/` manifests for backfiles** (Deviation 1), if the
  PM prefers that to the dated snapshot.
* **`v1-e30-t28`'s purge** should call `CaselistSettings.is_backfile` when it gets code. The test here
  pins the accessor.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

A careful build of something that touches the weekly run's lock and its bucket, with the rulings
applied where they belong and the one ruling that was wrong caught by a green run rather than
argued for.
1. **ac1 and ac2 pass.**
   * The counts and estimates are sound, and the estimates are labelled as estimates.
   * The red runs are recorded: 30 failed against the skeleton, with the 30 passes explained, and 5
     failed against the start commit for what was already written.
   * All 7 mutants were caught, with a fresh Hypothesis directory.
   * The tests go through the real composition root with moto and respx.
2. **ac3 as amended passes.** The amendment merged in the PM batch of 2026-10-25 (p) and now asks
   for the Mac's dry run.
   * The dry run refused as expected (`NOT_ENOUGH_FREE_SPACE`, 11.0 GB free against 29.7 GB needed,
     and `RUN_STATE_NOT_SEEDED`), and it showed the archive, the download left and the window state.
   * The window and budget refusals are shown by the tests on every run, which is what the amendment
     asked for.
   * Merge `origin/dev` into the branch, record ac3 as PASS and set the Goal to `Succeeded`.
3. **Deviation 1 is accepted: a backfile is its own dated snapshot, not `full/<date>`.**
   * The PM's ruling was wrong, and the first green run's `parsed 0, cards 0` proved it.
   * Keeping the parse pipeline, its eight callers and the occurrence table's provenance unchanged
     for the current season is worth more than a cleaner namespace.
   * A backfile has no weekly series to collide with. Its cards are dated by the archive's date,
     which a backfile's season label (`v1-e39-t18`) makes plain.
   * No pipeline change is filed.
4. **Deviation 3, the lock re-take fix, is accepted:** a real bug, red on the start commit and
   tested.
   * It is in the weekly run's critical path, so **this PR merges after the cutover session, not
     before it.** The cutover's release then holds no change to the lock. Nothing here can run before
     2026-11-05 anyway.
5. **Deviation 2: amend.** The PM adds `tests/smoke` to `constraints.packages` in a PM batch. The
   run-lock test is already inside `packages/debate_core/tests`.
6. **Accepted as made:**
   * bucket mode only;
   * `--confirm-prod`;
   * the weekly pull's suppression list for holds during the unlocked import;
   * a dry run that exits 1 on refusal;
   * the free-space estimate;
   * running the import again as the post-removal rebuild;
   * no index stage;
   * no run record;
   * the API gate first;
   * the bundle growth estimates, with the real figure recorded at the first import.
7. **Follow-ups the PM takes:**
   * `v1-e40-t09` is amended to:
     * alert on a failed backfile import, as the weekly run does;
     * run the post-removal rebuild as the same task with no download;
     * note the dated-snapshot namespace and the free space each caselist needs (about 30 GB for
       `hspolicy25`, 33 GB for `hsld25`).
   * An E40 task is filed: a held upload recorded in a cloud task's working copy vanishes when the
     task stops, for the weekly run and the backfile import alike, so the removal runbook's "run
     the removal again" loses it. Those records need to reach the bucket.
   * `v1-e30-t28` already reads the setting by its amendment, and the accessor test here pins it.
8. **The affected set** (341 files, about four minutes) is left to the PR's `ci` under agreement 10.
   The bucket-mode suite, the sync and landscape tests, the settings tests, the always-run list and
   the static checks passed in the session. The node's criterion (`2016 passed`) was run by the
   operator.

No re-review is needed after the Goal is set.

# Session report: v1-e34-t04-full-archive-refresh

| | |
|---|---|
| Task | `v1-e34-t04-full-archive-refresh` — Periodic full-archive refresh |
| Spec | [`plan_specs/v1/e34-caselist-sync/t04-full-archive-refresh.yaml`](../../plan_specs/v1/e34-caselist-sync/t04-full-archive-refresh.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t04-full-archive-refresh` |
| Session status | COMPLETE |

## Summary

The weekly `caselist pull` now refreshes at most one caselist's complete archive
(`<slug>-all-<date>.zip`) per run. It plans the weeklies first, against the same download ledger,
and fetches the complete archive only from what they leave. It picks the least recently refreshed
caselist (none held counts as oldest), and only one whose newest held complete archive is more
than `caselist.full_archive_interval_days` (default 30) old. The precondition, ac0, comes first: a complete archive is
its own snapshot, `full/<date>`, with its manifest at `manifests/<slug>/full/<date>.jsonl`. The
importer writes it no `(caselist, date)` snapshot or disclosure record, so neither the importer's
`_previous_snapshot` nor the sync's `_latest_imported_snapshot` can ever see it. Each complete-archive
import counts **withdrawn** and **superseded** digests against every earlier snapshot, weekly and
complete. The counts go in the run summary and the complete archive's manifest summary row, apart
from the weeklies' path-level `REMOVED`. Every reader of `manifests/<slug>/` handles the new
namespace on purpose (table below). Removal reaches the complete archive's manifest on both sides,
its `raw/` objects and its inbox copy, tested against moto. `caselist pull --full-archive <slug>`
fetches one on demand and refuses, before fetching anything, when the allowance is gone. The PM
should look first at Deviations 1 (no repository records for a complete archive) and 3 (the size
ceiling, raised for the complete archive only), and at the clause 12 question under Decisions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| ac0, a namespace of its own (done first, inside `rotation-selection`) | Done | Layout `manifests/<slug>/full/<date>.jsonl`, snapshot name `full/<date>`. `CaselistImportService.import_full_archive` writes no repository snapshot or disclosure. Shown failing first against the naive path (below) |
| `rotation-selection` | Done | `decide_full_archives`: due, one per run, least recently refreshed first, after the weeklies. FULL_ARCHIVE_NOT_PULLED_WEEKLY is replaced by `full_archive_rotation_off`, `full_archive_not_due`, `full_archive_waits_its_turn`, `full_archive_deferred_for_weeklies` and `full_archive_not_newest`, plus `download`, `already_in_inbox` and `already_imported` as they apply. The reason is in the select stage and in the summary's `full_archive` every run |
| `withdrawal-count` | Done | New module `application/caselist/withdrawals.py`. Counts go in the run summary, the import stage's reason and the complete archive's manifest summary row |
| `on-demand-flag` | Done | `caselist pull --full-archive SLUG`, a dry-run caption, and a runbook section |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac0**: a complete archive imports into a namespace of its own; weekly series and its `previous_snapshot` diffs untouched; a later weekly is diffed against the weekly before it | PASS | `test_a_complete_archive_dated_with_a_weekly_collides_with_nothing`, `test_a_current_complete_archive_does_not_strand_the_weekly_back_catalogue`, `test_neither_baseline_reader_ever_returns_a_complete_archive`, `test_importing_a_complete_archive_leaves_every_weekly_diff_unchanged` (weekly manifests byte-identical with and without the complete archive; W2 against 09-08 `{NEW 1, UNCHANGED 2}`, W3 against 09-15 `{NEW 1, REMOVED 1, UNCHANGED 2}`, hand-written). Red first: see "Shown failing first" |
| **ac1**: due after more than the interval, not inside it, reason recorded either way; the interval and rotation are settings | PASS | `test_a_caselist_refreshed_more_than_the_interval_ago_is_due_and_one_inside_it_is_not` (31 days due, 30 not), `test_the_interval_is_a_setting`, `test_the_reason_is_in_the_run_summary_whether_or_not_one_is_fetched`, `test_with_the_rotation_off_none_is_fetched_and_the_summary_says_so`. Settings `caselist.full_archive_rotation` and `caselist.full_archive_interval_days` |
| **ac2**: at most one per run, least recently refreshed first, the others next run | PASS | `test_two_caselists_due_at_once_fetch_only_the_least_recently_refreshed` (two consecutive runs), `test_of_two_never_refreshed_the_first_configured_goes_first_and_never_refreshed_beats_old` |
| **ac3**: budgeted after the weeklies; allowance exactly the new weeklies means no complete archive, and the deferral is named | PASS | `test_weeklies_that_use_up_the_allowance_exactly_defer_the_complete_archive` (3 spent, 2 weeklies new: `full_archive_deferred_for_weeklies`, `allowance_after_weeklies` 0, reason names it, `archives_deferred` 0); `test_one_download_left_after_the_weeklies_buys_the_complete_archive` |
| **ac4**: own snapshot through the same importer; withdrawals counted apart from REMOVED; no school, team code or filename | PASS | `test_withdrawal_counts_split_withdrawn_from_superseded` (withdrawn 1, superseded 1, against 3 earlier snapshots, hand-written in the module docstring), `test_withdrawals_are_reported_apart_from_the_weekly_path_level_removed`, `test_withdrawal_summary_names_no_path_school_team_or_file`; smoke `test_a_weekly_run_fetches_one_complete_archive_after_its_weeklies_and_says_why` (1 withdrawn, 1 superseded, worked by hand from the synthetic fixture's tables) |
| **ac5**: `--full-archive` fetches outside the rotation from the same ledger and refuses when the allowance is gone; `--dry-run` reports without fetching | PASS | `test_full_archive_on_demand_ignores_the_interval_and_the_rotation_setting`, `test_full_archive_on_demand_refuses_when_the_allowance_is_gone`, `test_full_archive_on_demand_dry_run_reports_and_fetches_nothing`; CLI `test_full_archive_flag_*` (4) |
| Node `rotation-selection`: `uv run pytest packages/debate_core/tests/application/test_caselist_sync_full_archive.py` | PASS | `23 passed in 6.16s` |
| Node `withdrawal-count`: `… test_caselist_sync_full_archive.py -k withdrawal` | PASS | `3 passed in 5.32s` |
| Node `on-demand-flag`: `uv run pytest packages/debate_cli/tests/commands/test_caselist_pull.py -k full_archive` | PASS | `4 passed in 6.87s` |
| Node `on-demand-flag`: `uv run debate-research caselist pull --help` | PASS | exit 0; lists `--full-archive SLUG` |
| CI-equivalent checks | PASS | `ruff check .` all passed; `ruff format --check .` 551 formatted; `pyright` 0 errors; `lint-imports` 11 kept, 0 broken; `check_thin_handlers.py` OK; `docs_index.py --check-descriptions` OK; `check_command_blocks.py --base origin/dev` OK (211 blocks, this report included); `validate_specs.py` OK, 319 files, after the phase was set |
| Full default suite: `uv run --frozen pytest -n auto --cov -m "not slow and not live"` | PASS | `4778 passed, 1 skipped, 1 warning in 105.42s`, coverage 96%; measured 107 s wall clock, under the two-minute hand-off line |

### Shown failing first

Each red was run against code that lacked the rule, and failed at the assertion it is about
(`-n0 --tb=line`, the session's scratchpad holds the logs):

* **Same-date collision and stranded back-catalogue (ac0).** `_import_full_archive` was first
  written as the importer stood when `v1-e30-t06` found it: `import_archive` plus the weekly
  `manifest_key`. The collision test failed because the 09-15 weekly manifest's `archive_sha256` was
  the complete archive's digest: it had been overwritten. The stranding test failed with W2
  `already_imported` where `download` was expected. `_latest_imported_snapshot` returned 2026-09-22
  instead of 2026-09-08. The weekly manifests differed with and without the complete archive.
  14 failed, 5 passed. After the namespace import, all ac0 tests passed.
* **Two caselists due at once.** The first `decide_full_archives` marked every due caselist
  `download`. It fetched both, `['testcl26-all-…', 'testclb26-all-…']`, against the expected
  `['testclb26-all-…']`.
* **Allowance exactly used up by the weeklies.** The same first version ignored the allowance. It
  fetched the complete archive with 0 left, and the decision was `download` where
  `full_archive_deferred_for_weeklies` was expected.
* **A removal missing the complete archive's snapshot (moto).** Three removal tests, before any
  change to `removal_plan` or `inbox_purge`. The plan's manifest rewrites were `set()` where both
  copies of `manifests/testcl26/full/2026-09-15.jsonl` were expected. After a `--team` removal the
  team's rows were still in the complete archive's manifest. A waiting complete archive in the
  inbox was not treated as the caselist's archive. 3 failed. After the fix: 3 passed.
* **The run log's select reason.** With the select-stage limit removed, the four-caselist test
  failed: the run log cut the reason short. With it, the test passed.

### Mutation runs

Each mutant ran on a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` (a new temporary directory per
run). The driver applied the mutant to a clean, committed tree, ran its tests with `-n0 --no-cov`,
restored the file with `git checkout` and checked `git status --porcelain` was empty. There were
three batches, the longest 40 s. No test here uses Hypothesis, so the fresh database is for form;
every catch is an assertion failure, not a collection error.

| Mutant | Result | Caught by |
|---|---|---|
| `_previous_snapshot` allowed to return a complete archive: `import_full_archive` writes the repository snapshot and disclosures, as a weekly does | CAUGHT, 2.1 s, 5 failed | the collision, stranding, baseline-reader and weekly-diff tests |
| `_latest_imported_snapshot` reads complete archives | CAUGHT, 1.5 s, 4 failed | stranding, baseline-reader, weekly-diff and first-seen tests |
| Two complete archives allowed in one run | CAUGHT, 1.5 s, 3 failed | the two-caselists test, the ordering test, the run-log test |
| The complete archive budgeted before the weeklies | CAUGHT, 1.5 s, 2 failed | both allowance tests |
| Removal skipping the complete-archive namespace | CAUGHT, 1.8 s, 2 failed | the `--source` and `--team` moto tests |
| Superseded counted as withdrawn | CAUGHT, 36.6 s (the smoke check included), 3 failed | both withdrawal tests and the smoke check |
| After the t08 merge: first-seen reads complete archives (the flag only) | **NOT CAUGHT**, 23 passed | an equivalent mutant: see below |
| After the t08 merge: first-seen reads complete archives and compares by date | CAUGHT, 1.5 s, 2 failed | the first-seen test (W2 would be 0) and the weekly-diff test |

The flag-only first-seen mutant changes nothing observable. `digests_in_earlier_manifests` keeps
snapshots whose name sorts before the weekly's date, and `"full/…" < "2026-…"` is false. So a
complete archive is excluded twice: once on purpose by `full_archives=False`, and once by accident
of string order. The mutant a real refactor would produce reads complete archives *and* compares
dates. It is caught, but only after I strengthened the test. The first version dated its complete
archive 09-15, the same day as W2, so it was not "earlier" under any comparison. It now dates the
complete archive 09-08, holding W2's file: the realistic case, since a weekly is a window and an
old file touched again in W2's week is in the complete archive before it. I kept the explicit flag,
because it states the rule rather than leaning on string order.

## Every reader of `manifests/<slug>/`, and what it does with a complete archive

| Reader | Where | What it does with `manifests/<slug>/full/<date>.jsonl` |
|---|---|---|
| `snapshot_of_manifest_key` | `publish_plan.py` | Weekly series by default; `full/<date>` only when asked with `full_archives=True` |
| `read_local_snapshots` | `evidence_listing.py` | Weekly by default; complete archives with `full_archives=True` or when the snapshot asked for is `full/<date>` |
| `_latest_imported_snapshot` (sync) | `caselist_sync.py` | **Ignores it** (binding, ac0); docstring says why |
| `_previous_snapshot`, `_disclosures_in` (importer) | `import_service.py` | **Cannot see it**: they read the repository, and a complete archive writes no repository snapshot or disclosure |
| `digests_in_earlier_manifests` (t08 first-seen) | `evidence_listing.py` | **Ignores it**, explicitly (binding, PM decision); docstring divides first-seen (weekly series, new evidence over time) from withdrawals (every earlier snapshot) |
| `snapshots_before_full_archive` (new) | `evidence_listing.py` | Reads weekly and complete alike, before a complete archive: its baseline (previous complete archive) and the earlier snapshots its withdrawals are counted against |
| `_newest_full_archive` (new, rotation) | `caselist_sync.py` | Reads complete archives only, by key name: "last refreshed" |
| Publish (`CaselistPublishService.plan`) | `publish_service.py` | **Includes it**: a whole-caselist publish carries `full/<date>`, and `--snapshot full/<date>` works. Its sources are under the caselist's own `raw/` prefix |
| Status (`CaselistStatusService`) | `status_service.py` | **Includes it**, locally and bucket-only. Retention's confirmation depends on it |
| Removal planner (`_known_caselists`, `_manifest_copies`, `_holdings`, `_rows_to_drop`) | `removal_plan.py` | **Includes it** (binding): finds its rows, counts its holders, rewrites it on both sides. `_imported_weeks` excludes it; `imported_full_archives` is its own set |
| Removal executor's sweep of noncurrent versions | `removal_service.py` | Already lists `manifests/<slug>/`, which holds `full/` |
| Inbox purge (`plan_inbox`) | `inbox_purge.py` | A `-all-` zip is the caselist's archive: disclosure-scoped entries are dropped, deleted when imported, rewritten when waiting, read under the complete archive's ceilings |
| Retention (`_judge_locally`) | `caselist_sync.py` | **Same conditions as a weekly** (binding): imported (its own manifest's `archive_sha256` is the file's digest) and confirmed in the bucket; nothing loosened. Tested kept for `not_imported` and `not_confirmed` |
| Landscape staleness (`newest_snapshot`) | `landscape_staleness.py` | **Ignores it**, explicitly: staleness is about the weekly capture, and a complete archive is only fetched by a run that took its weeklies |
| `list_local_caselists`, `list_remote_caselists` | `evidence_listing.py` | Count a caselist known only from a complete archive |
| Backfill count functions (`snapshot_rows`, `dedupe_row`, `first_seen_rows`, the spot check) | `docs/runbooks/caselist-backfill.md` | Ignore it: `manifests/$1/*.jsonl` does not descend into `full/`. Noted in an appended section |
| `store sync` | `evidence_sync.py` | Copies the objects tree whole, `full/` included |
| t08's `caselist reimport-openev-metadata`, `OpenEvImportService.reimport_metadata` | `openev_metadata_reimport.py` | Read `manifests/openev/` only, never a caselist's directory. Untouched |
| `caselist import` (a writer) | `debate_cli/commands/caselist.py` | Refuses a file named `<slug>-all-<date>.zip` and points at `--full-archive` |

## Files changed

* `debate_core.application.caselist_sync`: the rotation (`decide_full_archives`, `FullArchiveRotation`, `FullArchivePlan`,
  `FullArchiveImport`, `FullArchiveRefused`), the complete-archive import queue and import,
  retention of complete-archive zips, the summary's `full_archive`, the on-demand path through
  `run_pull`, and the module docstring's "The complete archive".
* `debate_core.application.caselist`: `import_service` (`import_full_archive`,
  `FullArchiveBaseline`), `withdrawals` (new), `manifest` (key, summary row), `publish_plan`
  (snapshot names, validation, `snapshot_of_manifest_key`), `evidence_listing`, `publish_service`,
  `status_service`, `removal_plan`, `inbox_purge`.
* `debate_core.application`: `settings` (four settings), `sync_runs` (select-reason limit),
  `landscape_staleness` (explicit weekly-only).
* `debate_core.integrations.opencaselist`: a complete archive's own download ceiling (Deviation 2).
* `debate_cli`: `commands/caselist_pull.py` (flag, caption), `commands/caselist.py` (import
  guard), `container.py` (rotation, reader and rewriter ceilings).
* Tests: `test_caselist_sync_full_archive.py` (new, 23), `caselist/test_removal_reaches_full_archives.py`
  (new, moto, 3), additions to the client, CLI pull and CLI import tests, two expectations in
  `test_caselist_sync.py`, and `tests/smoke/test_caselist_pull.py`.
* Docs: `docs/runbooks/caselist-scheduled-sync.md` (new section, table row, Step 1 sentence);
  `docs/runbooks/caselist-backfill.md` (appended section only).

## Deviations from the spec

1. **A complete archive has no record in the repository.** ac4 says it "imports as its own snapshot
   through the same importer as a weekly". It does: `CaselistImportService`, the same pipeline,
   suppression and blob store. But the repository's `caselist_snapshots` and
   `caselist_disclosures` tables are keyed by `(caselist, date[, path])`, which is the weekly
   series' own key. Any row there is one the weekly series reads, and so a collision. A key the
   weekly series never sees would need a series column and a migration that rebuilds two primary
   keys, in `debate_core.domain`, `integrations.local`, the fake repository and the contract tests,
   all outside this task's packages. So a complete archive's record is its manifest. It still files
   each stored member's source document by digest, whose seen range widens to its date. **What
   this costs:** a file only the complete archive holds has no disclosure record. Removal finds it
   by its manifest rows (tested). `caselist_card_stats` and any future E31/E32 reader of disclosures
   will not see its school and team. If E32 needs that, it is a migration task.
2. **Outside `constraints.packages`.** `debate_core.integrations.opencaselist` (the download
   ceiling, Deviation 3); `debate_cli/container.py` (the rotation and ceilings, as `v1-e34-t06` and
   `t07` also needed); `docs/runbooks/` (the spec's own `on-demand-flag` output); tests and
   `tests/smoke/`, because the smoke check asserted the old behaviour and working agreement 5 asks
   for smoke checks of a changed surface.
3. **The complete archive got its own size ceiling.** The listing carries no sizes (`DownloadRecord`
   is a name and a URL; the recorded fixture `downloads.json` has none), so today's size cannot be
   read, and nothing live was called. The lower bound is measured: a complete archive holds at
   least the caselist's distinct files, and `docs/data/caselist-backfill-2026-09.md` records
   hspf26's 3,906 at **1,755,226,582 bytes** after 13 weeks, 82% of the 2 GiB `max_archive_bytes`
   that both the download and the reader enforce. It may already be over, since a complete archive
   can hold files older than the weekly back-catalogue. A refused download probably still spends
   one of the five. So `caselist.max_full_archive_bytes` is 8 GiB (about 5.4 GB projected for a
   ~40-week season at the measured rate, with headroom) and `max_full_archive_unpacked_bytes`
   16 GiB. They apply to the complete archive alone: download, read, and the removal's inbox
   rewrite. The weekly ceilings are unchanged. The first real fetch records the actual size in
   `full_archive.imported[].bytes`.
4. **The realised cadence is about five weeks, not four.** "More than 30 days" with Wednesday runs
   and a Tuesday-dated archive is due on day 36 (day 29 is not more than 30). The epic's "within a
   month" needs `full_archive_interval_days = 27`. I kept the spec's default and wording; the PM
   may want 27.

## Decisions and assumptions

* **Policy, E34 gate 4.** The clause: *"Politeness is enforced in code: a configurable minimum
  interval between requests, one download at a time, bounded backoff on 429/502/503/504 honouring
  `Retry-After`, and no HTML scraping. Weekly cadence at most — no polling faster than archives are
  published."* The rotation adds no schedule and no polling. It runs inside the weekly agent's one
  run, at most one complete archive per run, at most once per 30 days per caselist, through the same
  paced transport. The 5-per-day cap is upstream's, not the policy's; the complete archive only
  ever spends what the weeklies leave, and the setting cannot be below 7 days. **A question I
  cannot settle:** clause 12, the maintainer's confirmation, is worded for "scheduled downloads of
  the weekly archives". The complete archive is a different file, though listed by the same
  endpoint and stored by the site in the same `weekly/<caselist>/` folder (`downloads.py`'s
  docstring, from the upstream source). ADR-0017 decision 1 already planned to fetch one, so I
  have taken it as covered. The PM or Charlie may want that confirmed with the policy's owner
  before the first real fetch.
* **Layout `manifests/<slug>/full/<date>.jsonl`, snapshot name `full/<date>`.** It sits under the
  caselist's own prefix, so the existing IAM grant (`manifests/*`), `store sync`, the per-caselist
  listings and the removal's version sweep reach it unchanged. It is nested, so every reader written
  for the weekly series (`manifests/<slug>/<date>.jsonl`, one `/` after the slug) skips it without
  being told, and must opt in to see it. It is dated by the archive's own date, so a complete
  archive and the weekly of the same day are two keys. Rejected: a sibling `<date>-all.jsonl`, which
  a `*.jsonl` glob would read as a weekly; `manifests/<slug>-all/`, outside the caselist's prefix;
  `manifests/full/<slug>/`, which the per-caselist listings miss.
* **Classified against the previous complete archive.** Its `NEW` means "not present in the
  preceding complete archive", the same wording t08 gave a weekly against its preceding snapshot.
  Its summary row names `snapshot` and `previous_snapshot` as `full/<date>`, has no `first_seen`,
  and carries `withdrawn`, `superseded` and `earlier_snapshots` instead (PM decision). A weekly's
  summary row is byte for byte unchanged.
* **"Earlier" is strictly before the complete archive's date**, for both the baseline and the
  withdrawal count, so re-importing it counts the same. A weekly of the same date is not earlier.
* **Withdrawn and superseded, by path.** Superseded means one of the paths the digest was held at
  is in the complete archive with other bytes. Withdrawn means none of them is. A re-upload under
  a new sequence-numbered name therefore counts as withdrawn; the runbook and the module docstring
  say so.
* **A full-archive deferral is not weekly backlog.** `deferred_by_cap` is false for a complete
  archive, so the run log's growing-backlog warning stays about weeks waiting to be fetched.
* **On demand.** `--full-archive SLUG` adds the caselist to the run, takes the one slot whatever
  the interval or rotation setting, and is still budgeted after the weeklies. A real run that cannot
  fetch it raises `FullArchiveRefused` before any download: exit 1, recorded by the run monitor. A
  dry run reports the same decision and exits 0. With `--publish-pending` it is a usage error.
* **A complete archive already in the inbox** is imported from there, without a download and
  without taking the slot.
* **The service's default is the rotation off; the settings' default is on.** The existing sync
  tests' hand-written counts are for the weeklies alone, so the service takes the rotation as an
  argument. The container builds it from settings, where it is on. The CLI test module's
  installation turns it off for its old tests and back on for its four new ones. The smoke suite,
  which validate-dev runs, keeps the real default: its end-to-end check now expects four downloads,
  the complete archive's manifest in the bucket and its zip retired from the inbox.
* **The installed agent.** It runs the build it was installed with, which lists the complete archive
  and never fetches it. After a reinstall with a build containing this task, its next run fetches
  one complete archive if the weeklies leave a download, since none is held yet, and the following
  runs take the other caselists in turn.
* **`scripts/task sync`** was run after `v1-e30-t08` merged. The branch was not on origin, so it
  rebased and pushed nothing. The rebase was clean. Everything after it was built on t08's importer.

## Operator follow-ups

1. **The first real fetch, one caselist, in dev.** Run from this task's worktree before the merge,
   or with an installed build containing it after. About a minute plus the download: a complete
   archive is the site's largest file, and hspf26's is at least 1.7 GB, so start with hsld26
   (about 0.6 GB). The dry run first. Success is exit 0 and a caption saying
   `Complete archive: hsld26's would be fetched; N bulk download(s) left after the weeklies.`
   with N at least 1.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t04-full-archive-refresh
   git branch --show-current
   DEBATE_ENV=dev uv run debate-research caselist pull --caselist hsld26 --full-archive hsld26 --dry-run
   ```

   **Done 2026-10-10, before PM review** (read-only: nothing downloaded or written). Exit 0 on
   this branch. `select` listed 15 archives and 498 OpenEv files, with 1 to fetch: the complete
   archive alone, so hsld26's weeklies are up to date. It spent 0 of the day's 5 bulk downloads,
   and the rotation said `hsld26: fetched this run (never refreshed)`, interval 30 days, 5 left
   after the weeklies. Download, import, publish and report were `planned`, parse and landscape
   `skipped` (not shipped), and retention `skipped` because the inbox is empty. The caption ended
   `Complete archive: hsld26's would be fetched; 5 bulk download(s) left after the weeklies.`
   The real fetch below waits for the PM's verdict.

   Then the fetch, printing only what the session needs. Success is `succeeded: true`, every
   stage `completed` or `skipped`, and one entry under `full_archive.imported` with its `bytes`,
   `withdrawn`, `superseded` and `earlier_snapshots`. Paste that object back: it holds counts
   only.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t04-full-archive-refresh
   DEBATE_ENV=dev uv run debate-research --json caselist pull --caselist hsld26 --full-archive hsld26 | jq '{succeeded: .data.succeeded, stages: [.data.stages[] | {stage, outcome}], full_archive: .data.full_archive}'
   DEBATE_ENV=dev uv run debate-research caselist status --caselist hsld26
   ```

   Status should exit 0 with `full/<date>` among the snapshots and everything in sync. Check one
   caselist at a time: unscoped dev status exits 1 because of `testcl26`. If the dry run says
   `none fetched … first in turn but 0 bulk download(s) left`, the day's five are spent; run it
   tomorrow. The withdrawal and superseded counts, with the date, belong in a dated section of
   `docs/data/` by whoever records them.
2. **The prod publish, later**, once dev is in sync for that caselist. A whole-caselist publish
   includes the complete archive:

   ```bash
   aws sso login --profile debate-prod-evidence
   export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
   uv run debate-research caselist publish --caselist hsld26 --dry-run
   uv run debate-research caselist publish --caselist hsld26 --confirm-prod
   uv run debate-research caselist status --caselist hsld26
   unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
   ```

   Run it from the same worktree (the `cd` above), or with `debate-research` from an installed
   build after the merge. The dry run should upload the complete archive's manifest and only the
   sources no weekly holds; success is `prod status` in sync for hsld26.
3. **Reinstall the weekly agent** with a build containing this task (`caselist-scheduled-sync.md`,
   Step 2 and Step 3) when you want the rotation running. Until then it fetches none.

## Follow-up work

* **E32 / E30: disclosures for files only a complete archive holds** (Deviation 1). A series
  column on `caselist_snapshots` and `caselist_disclosures`, with a migration, if a landscape or
  card statistic must attribute those files to a school and team.
* **PM: the default interval** (Deviation 4): 27 days for a four-weekly refresh, or keep 30.
* **Policy: clause 12's wording** (Decisions): confirm it covers the `-all-` archive, or record
  that ADR-0017 decision 1 settled it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

Accepted in full, phase `Succeeded`.

* **ac0 was done first and proved against the real failure.** The red run used the naive path
  `v1-e30-t06` actually hit (`import_archive` plus the weekly key). It reproduced the overwrite,
  the stranded back-catalogue and the changed weekly diffs. A test written against an imagined
  bug would have proved much less.
* **The table of manifest readers is the deliverable I most wanted.** Every reader now handles
  the complete archive on purpose, and you said for each one whether it includes or ignores it.
  `v1-e31-t06` will adopt your `snapshot_of_manifest_key` as its single weekly-series rule after
  it syncs.
* **The equivalent first-seen mutant was handled well.** You explained why it can't fail: string
  order already excludes `full/…`. Then you changed the test to the realistic case (a complete
  archive dated before the weekly, holding the weekly's file), so the mutant a real refactor
  would produce is caught. You also kept the explicit flag, so the code states the rule rather
  than relying on string order.

**Rulings:**

* **Deviation 1, the complete archive's record is its manifest:** accepted. A series column and a
  migration of two primary keys would be a task of their own. Nothing needs them yet:
  `v1-e31-t06` parses only the weekly series and the OpenEv release. If E32 ever needs to
  attribute files that only a complete archive holds, it files the migration then.
* **Deviation 2, outside the packages:** accepted. The ceiling, the composition root, the runbook
  the spec itself names, and the smoke check of a changed surface.
* **Deviation 3, a ceiling for the complete archive alone:** accepted. 8 GiB packed and 16 GiB
  unpacked is a reasoned projection from the measured hspf26 figure. Leaving weekly ceilings
  unchanged keeps the safety margin where it already worked. The first real fetch records the
  actual size.
* **Deviation 4, the interval:** keep 30 days. A refresh roughly every five weekly runs is fine.
  The complete archive is the site's largest file, withdrawal detection is not time-critical,
  and fewer large downloads is the polite choice. The epic's "within a month" is approximate,
  and no spec change is needed.
* **Clause 12:** ADR-0017 does not settle it. That ADR is our own decision, and it says itself
  that the policy wins. The maintainer's confirmation, as recorded, covers "scheduled downloads
  of the weekly archives".
  * The operator's one-off `--full-archive` fetch is a manual download through the documented
    API. That is covered as any manual download is (terms clauses 4 and 7), so operator
    follow-up 1 may go ahead.
  * The scheduled rotation is not covered yet. Until Charlie confirms it, either from the
    maintainer's reply on file or by asking, the weekly agent is reinstalled with
    `caselist.full_archive_rotation` off. The PM records the confirmation in clause 12 when it
    arrives.

**Operator follow-ups:**

* Follow-up 1 needs `aws sso login --profile debate-dev-evidence` first, because the pull
  publishes to the dev bucket.
* Follow-up 3, the agent reinstall, waits for two things:
  * the 2026-10-14 scheduled run, which `v1-e34-t05` observes on the build installed now;
  * the clause 12 confirmation, or the rotation set off.

**Merge order:** this task merges before `v1-e31-t06`, which syncs onto it.

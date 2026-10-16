# Session report: v1-e30-t18-late-imports-re-measure-later-manifests

| | |
|---|---|
| Task | `v1-e30-t18-late-imports-re-measure-later-manifests` — A weekly imported late re-measures the weeks after it, and a re-import needs no flag |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t18-late-imports-re-measure-later-manifests.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t18-late-imports-re-measure-later-manifests.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t18-late-imports-re-measure-later-manifests` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**A weekly imported late now leaves every later manifest as a date-order run writes it.** After a
weekly's first import, `caselist import` and `caselist pull` hand its report to a new service,
`LaterManifests` (`application/caselist/later_manifests.py`). It measures each later weekly
manifest again from the disclosures and the earlier manifests, and never opens an archive. It also
recounts the newest complete archive's withdrawals when the weekly is dated before it. A manifest is
rewritten only if its bytes change, and the publisher uploads it as a changed manifest. A week
already imported is imported again with no flag, writes only its own manifest, and measures nothing
again. The first-seen filter now compares dates, so `full_archives=False` alone keeps complete
archives out: t17's surviving mutant is now caught. Nothing stored changes.

**What to look at first:** Decision 1, how I read rulings 1 and 2 together (a week never imported
and older than the newest still needs `--allow-out-of-order`). Then Decisions 2 and 3: re-measuring
on first import only, and moving first-seen by a difference rather than recounting it. Both keep a
removal's rewrite as the removal left it. My first version recounted, and it would have rewritten a
later manifest on the removal runbook's own Step 6. The removal tests in "Red, then green" show
that case.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `late-imports` — Late imports re-measure later manifests | Done | Hand-worked answers in t17's fixture and t17's tests turned to the rulings, red against a no-op interface; then the re-measure, the re-import, the recount and the date comparison; then removal cases, mutation runs, the two-build check and smoke checks |

## Acceptance criteria

Commit ids are after `scripts/task sync` rebased the branch onto `dev` at `311329b`. "The start
commit" is `53d1f98`, the branch's start before the rebase. Its source tree is `dev`'s `28e1a5b`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: on t17's window-order fixture, a weekly imported after a later one leaves every later weekly's manifest equal, byte for byte, to the date-order manifest, with no archive re-read; shown failing first with t17's own scenario | PASS | `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_import_window_ordering.py`. **Red** at `f0ca3c2` (no-op interface): `16 failed, 17 passed`, every failure an assertion except one re-import refused with `SnapshotOutOfOrder`. t17's own scenario, the week after a late one: `AssertionError: 2026-09-15` (bytes differ), `assert '2026-09-01' == '2026-09-08'` (previous week), and `assert [2, 3, 2] == [2, 3, 1]` (first-seen). **Green** now: `36 passed`. `test_every_later_week_is_measured_again_with_the_late_one_and_no_archive_is_read` deletes the archives of the weeks already imported before the late one arrives, for both late orders (the second week after the third, and the first after the other two), and compares all three manifests byte for byte. Through the command: `packages/debate_cli/tests/commands/test_caselist_import_late_weekly.py`, red against the start commit's exported source (`AssertionError: datetime.date(2026, 9, 15)`), green now |
| **ac2**: a re-import of a week already imported needs no flag and changes no other week's manifest, by test; the removal runbook no longer passes `--allow-out-of-order` for it | PASS | `test_an_older_week_imported_again_needs_no_flag` and `..._changes_no_manifest` (bytes and file mtimes of the other weeks unchanged, nothing rewritten). With a removal in the store: `test_an_older_week_imported_again_after_a_removal_changes_no_other_manifest`, which runs the runbook's Step 6 and then an older week. Through the command: `test_a_week_already_imported_is_imported_again_without_the_flag`, red against the start commit (`SNAPSHOT_OUT_OF_ORDER`). Smoke: `tests/smoke/test_caselist_import_smoke.py::test_a_week_already_imported_is_imported_again_without_the_flag`. Runbook: `docs/runbooks/caselist-removal.md` Step 6 and the un-suppress section drop the flag. `git grep -n allow-out-of-order -- docs/runbooks` now finds only the backfill runbook's two lines (Follow-up 1). `scripts/check_command_blocks.py --base origin/dev`: OK |
| **ac3**: after a later import of an earlier-dated weekly, the newest complete archive's withdrawal count, in its manifest summary and the run record, equals the date-order count; shown failing first | PASS | Application: `test_the_newest_complete_archive_is_recounted_to_the_date_order_manifest`, two orders. Every manifest, the complete archive's included, equals the date-order run's byte for byte, at withdrawn 1, superseded 1, 2 compared (the import counted 0, 1, 1). Red at `f0ca3c2`: `AssertionError: full/2026-09-12`. The pull: `packages/debate_core/tests/application/test_caselist_sync_late_weekly.py`. The run that imports the gap weekly writes the recount to the manifest summary, the import stage reason, the run record's import stage, and the run summary's new `full_archive_recounted`. It publishes the rewritten manifest to a moto bucket, byte for byte the date-order one. Red against the start commit: `assert (0, 1, 1) == (1, 1, 2)` and `AssertionError: manifests/testcl26/full/2026-09-12.jsonl` |
| **ac4**: the first-seen filter compares dates; a mutant that lets complete archives into first-seen through the flag alone is caught, where t17's run could not tell it apart | PASS | `digests_in_each_earlier_manifest` (which `digests_in_earlier_manifests` now unions) compares each snapshot's date, a complete archive's included. Mutant `full_archives=True`: **CAUGHT**, 1 failed (`test_each_import_reports_what_the_fixture_works_out_by_hand[a complete archive before any weekly, dated before them all]`). With t17's string comparison put back, the same mutant is **not caught** (`42 passed`), so the date comparison is what makes the flag load-bearing. Fresh Hypothesis database per run (below) |
| **ac5**: each rewritten manifest is read by the build at the start commit and by this build, each from its own code exported with `git archive`, and publishes as a changed manifest | PASS | See "Two builds read and publish the rewritten manifests" below. Both builds read all four manifests (`read_local_snapshots`, which refuses an unreadable row). Both see the same summary keys, with only the re-measured ones changed. Both publish `2026-09-15` and `full/2026-09-12` as `uploaded` over the bucket's earlier copies, end with `caselist status` in sync, and leave the bucket's bytes equal to the local ones. In the suite: `test_each_rewritten_manifest_publishes_as_a_changed_manifest` (`ManifestOutcome.UPLOADED`) |
| Node `late-imports`: `uv run pytest packages/debate_core/tests/application -k "import or order"` | PASS | `253 passed in 13.04s`, run as the spec writes it, after the sync. The lock file was unchanged |
| Full suite, four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | `1780 passed`; `1789 passed, 1 xfailed`; `1791 passed, 1 skipped`; `1785 passed, 1 xfailed`. 55, 43, 40 and 45 s at load averages 7 to 17, each under a hard stop. Run at `8f7a646`, before the sync (now `ad958e1`). The sync brought only version numbers, specs and docs (`git diff --stat 28e1a5b 311329b`: no code), and the task's tests passed again after it. The warnings are the network guard's own tests |
| Lint, types, import contracts, command blocks | PASS | `ruff format --check .`: 701 files formatted. `ruff check .`: clean. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `scripts/check_command_blocks.py --base origin/dev`: OK |
| Goal set to `Succeeded`; `uv run scripts/validate_specs.py` | PASS | `set-phase … Succeeded`, then `OK: 355 files, 38 epics, 297 tasks, 20 releases` |

## How a later manifest is measured again

After a weekly's first import, for each weekly manifest dated after it (`LaterManifests`):

| Part of the manifest | What it becomes |
|---|---|
| Member rows | The same rows. Only `classification` is decided again, by the importer's own rule (`pipeline.classify_stored`, which `_classify` now calls), against the new previous week's disclosures and the digests of the rows before it |
| `REMOVED` rows | The new previous week's paths the archive did not hold. "Held" is its member rows' paths plus each path of its *old* previous week that its old `REMOVED` rows leave out. A member the suppression list stopped has no row, but the import saw its path (Decision 4) |
| `previous_snapshot` | The latest weekly dated before it, from the snapshot records, as the importer finds it |
| `classifications` | Counted from those rows; `SUPPRESSED` kept as it was |
| `first_seen` | The old count, less each digest of its rows that the new weekly holds and no other earlier weekly does (Decision 3) |
| Everything else | Kept: `members`, `distinct_sha256`, `warnings`, `skipped`, `archive_sha256`, `event` |

Then, if the newest complete archive is dated after the weekly, its `withdrawn`, `superseded` and
`earlier_snapshots` are counted again as its import counts them, from its own stored rows and every
manifest dated before it. Its member rows are kept byte for byte. Every rewrite is rendered, and
checked against the suppression list, before the first is written.

## Red, then green

**The ordering tests**, against the no-op interface at `f0ca3c2`: `16 failed, 17 passed in 1.37s`.
The failures are t17's late scenario (bytes, previous week, first-seen sum `[2, 3, 2]`), the new
"first weekly imported last" scenario, the re-import (refused, `SnapshotOutOfOrder`), the two
complete-archive orders, the new refusal text, and the publish test (`assert () == ('2026-09-15',
'full/2026-09-12')`). Green at `84670ff`.

**The command and the pull**, this branch's tests over the start commit's source exported with
`git archive` and put first on `PYTHONPATH`: `5 failed, 1 passed`. That is 4 assertions, plus one
`AttributeError` on the run summary's new `full_archive_recounts`, in the test that checks a weekly
dated after the complete archive recounts nothing, which cannot fail on that build any other way.
The one that passes is the never-imported late week still being refused, which both builds do.
Green: `6 passed`.

**The removal cases** came after the first green. Working them out by hand
(`build_window_order_archives.py`, "After a removal") showed two flaws in `84670ff`, and
`ac5a7e0` fixes both:

* Recounting first-seen from the rows would have rewritten `2026-09-15` (first-seen 1 → 0) on the
  removal runbook's Step 6, which re-imports an older week. A removal keeps a first-seen count as
  the import recorded it when it drops a row.
* A later week's member that the suppression list stopped has no row. So a path it held could be
  reported `REMOVED`, where the import wrote nothing.

`test_a_late_week_after_a_removal_leaves_the_manifest_the_date_order_run_and_removal_leave` compares
the late order with the date-order run followed by the same removal, byte for byte. Mutants 10 and
12 below show it catching each flaw.

**The smoke checks** cannot be run against an exported build: the harness gives the console script a
fresh environment, so `PYTHONPATH` never reaches it. Mutants 3 and 19 run against them instead.

## Mutation runs

Each mutant was applied to the committed source and run against the three t18 test files
(`test_import_window_ordering.py`, `test_caselist_sync_late_weekly.py`,
`test_caselist_import_late_weekly.py`; 41 tests, 42 after the last was added). Each run had a new,
empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8; none of these tests uses Hypothesis). Each
mutant was restored with `git checkout`, and the tree was checked clean after every batch.

| # | Mutant | Result |
|---|---|---|
| 1 | First-seen reads complete archives (`full_archives=True`), t17's mutant 5 | CAUGHT, 1 failed |
| 2 | First-seen counts a snapshot of the same date as earlier (`<` to `<=`) | CAUGHT, 11 failed |
| 3 | A week already imported is refused again | CAUGHT, 6 failed; smoke: 1 failed |
| 4 | A late week never imported is not refused | CAUGHT, 6 failed |
| 5 | A re-import measures the later manifests again | CAUGHT, 4 failed |
| 6 | No later weekly is measured again | CAUGHT, 9 failed |
| 7 | The previous week is the latest held, whatever its date | CAUGHT, 1 failed |
| 8 | Member rows keep their old classification | CAUGHT, 4 failed |
| 9 | No `REMOVED` row is added against the new previous week | CAUGHT, 6 failed |
| 10 | No path is inferred for a member the list stopped | CAUGHT, 1 failed (the late week after a removal) |
| 11 | First-seen is not moved | CAUGHT, 6 failed |
| 12 | First-seen is counted afresh from the rows (my first version) | CAUGHT, 1 failed (the late week after a removal) |
| 13 | The complete archive is never recounted | CAUGHT, 7 failed |
| 14 | The complete archive is recounted whatever its date | First NOT CAUGHT (41 passed). It is not equivalent: after a removal it overwrites the counts the removal kept. I added `test_a_weekly_dated_after_the_complete_archive_leaves_its_count_as_a_removal_kept_it`; then CAUGHT, 1 failed |
| 15 | An unchanged manifest is written anyway | CAUGHT, 1 failed |
| 16 | The pull measures nothing again | CAUGHT, 2 failed |
| 17 | The pull does not publish what it rewrote | CAUGHT, 1 failed |
| 18 | The pull's import stage leaves the recount out | CAUGHT, 1 failed |
| 19 | `caselist import` measures nothing again | CAUGHT, 1 failed; smoke: 1 failed |

And for ac4, without a mutant on the flag's caller: the date comparison replaced by t17's string
comparison, flag kept, `42 passed`; the same with the flag mutated to `True`, `42 passed`. The string
comparison alone hid the flag, as t17 found.

## Two builds read and publish the rewritten manifests (ac5)

This build (`git archive` of `d48ba1b`, now `7d71d23` after the sync: the commit before the smoke checks, with the same code)
made two stores from t17's fixture: `2026-09-01`, `full/2026-09-12`, `2026-09-15` ("before"), and
the same plus `2026-09-08` allowed out of order ("after"). The late weekly rewrote `('2026-09-15',
'full/2026-09-12')`. Then a script ran under each build, from its own exported source
(`packages/*/src` put first on `PYTHONPATH`). It read the "after" store, then published "before" and
"after" in turn to one moto bucket with that build's `CaselistPublishService`. The output was
identical for both builds:

```text
  read 2026-09-01: 2 source(s), 2 stored row(s)
  read 2026-09-08: 4 source(s), 4 stored row(s)
  read 2026-09-15: 3 source(s), 3 stored row(s)
  read full/2026-09-12: 3 source(s), 3 stored row(s)
  2026-09-15: same summary keys: True; changed: ['classifications', 'first_seen', 'previous_snapshot']
  full/2026-09-12: same summary keys: True; changed: ['earlier_snapshots', 'withdrawn']
  publish before: succeeded=True {'2026-09-01': 'uploaded', '2026-09-15': 'uploaded', 'full/2026-09-12': 'uploaded'}
  publish after: succeeded=True {'2026-09-01': 'skipped', '2026-09-08': 'uploaded', '2026-09-15': 'uploaded', 'full/2026-09-12': 'uploaded'}
  status after: {'2026-09-01': True, '2026-09-08': True, '2026-09-15': True, 'full/2026-09-12': True}
  bucket 2026-09-15 == local after: True
  bucket full/2026-09-12 == local after: True
```

No key is added or removed. A rewritten manifest has the shape every build already writes, and
`schema_version` stays 1.

## Files changed

* **`debate_core.application`**
  * `caselist/later_manifests.py`, new: the re-measure and the recount.
  * `caselist/import_service.py`: the refusal only for a week never imported, and its new text.
    `ImportReport.imported_before`, and a read-only `caselist` property. The Ordering section and
    the complete-archive paragraph are rewritten.
  * `caselist/pipeline.py`: `classify_stored`, the one classification rule, split out of `_classify`.
  * `caselist/evidence_listing.py`: dates in the first-seen filter, and
    `digests_in_each_earlier_manifest`.
  * `caselist_sync.py`: the pull re-measures after each weekly, publishes what was rewritten, and
    reports the recount (`RunSummary.full_archive_recounts`, `full_archive_recounted`).
  * `ports/caselist.py`: one docstring.
* **`debate_cli`**: `commands/caselist.py`, where `caselist import` re-measures after writing and
  its summary gains `rewritten_manifests` and `complete_archive_recounted`; and `container.py`
  (`caselist_later_manifests()`).
* **Tests**:
  * `test_import_window_ordering.py`: t17's late and re-import tests turned to the rulings, and new
    tests for the re-measure, the recount, publishing and removals.
  * New: `test_caselist_sync_late_weekly.py` and `debate_cli/tests/commands/test_caselist_import_late_weekly.py`.
  * `test_import_service.py`: one docstring.
* **`tests/fixtures/caselist/build_window_order_archives.py`**: hand-worked answers for t18
  (`EXPECTED_REMEASURED`, `EXPECTED_AFTER_A_REMOVAL`), two new scenarios, and t17's text updated.
* **`tests/smoke/test_caselist_import_smoke.py`**: two checks (Deviation 1).
* **`docs/runbooks/caselist-removal.md`**: Step 6 and the un-suppress section drop
  `--allow-out-of-order`, and nothing else.

## Deviations from the spec

1. **`tests/smoke/` is outside `constraints.packages`.** Working agreement 5 asks every task that
   changes a user-facing surface to update its smoke checks, and `caselist import` changed: a
   re-import needs no flag, and a late weekly rewrites later manifests. I added two checks to the
   existing offline import smoke file and changed nothing else there.

## Decisions and assumptions

1. **A weekly never imported and older than the newest still needs `--allow-out-of-order`.** Ruling 1
   says "allow the late week", and ruling 2 drops the refusal only "when the week is already
   imported, since that writes only its own manifest". I read ruling 2's reason as saying that a
   week never imported does more: it rewrites other weeks' manifests. So it stays a deliberate act.
   The PM note's limit on the runbook edit points the same way, as does the backfill runbook's
   instruction never to pass the flag. With the flag, it is allowed and the later manifests are
   measured again. The refusal now says exactly that. If ruling 1 meant no refusal at all, the
   change is one condition in `_previous_snapshot` and two tests.
2. **Only a weekly's first import is measured in** (`ImportReport.imported_before`). A week already
   imported was there when the weeks after it were measured, so importing it again leaves them
   alone. That is ruling 2's premise, and it is what keeps a removal's rewrite intact on Step 6.
3. **First-seen moves by a difference, not a recount.** A removal drops rows but keeps first-seen
   as the import recorded it (`removal_plan._recounted_caselist_summary`). A recount from the rows
   would undo that. Mutant 12 shows the test that guards it.
4. **`REMOVED` rows infer the paths of stopped members from the old previous week**, rather than
   leaving out paths a removal holds, which was my first version. The inference reproduces the
   import's rows whenever the previous week has not changed.
5. **Only the newest complete archive is recounted, and only when the weekly is dated before it**
   (ruling 3). Nothing is held back behind a weekly gap; the forbidden list rules that out. The date
   condition also keeps a removal's counts (mutant 14).
6. **The run record.** `SyncRunRecord`'s fields are frozen (`extra="forbid"` in every installed
   build), so the recount goes in the import stage's reason, a free-text field every build reads.
   It also goes in the run summary's additive `full_archive_recounted`. The record's redaction turns
   `full/2026-09-12` into `[redacted]`, as it already did for t17's import sentence, so the record
   keeps the counts and loses the name (Follow-up 4).
7. **The pull publishes what it rewrote in the same run**, as publish targets beside the weekly. It
   re-measures before it counts the weekly as imported or queues it for publishing, so a failure
   there is that archive's failure, recorded as any import failure is. I did not test what
   retention then does with its inbox copy.
8. **`SnapshotOutOfOrder` lost t17's `already_imported` field**, which would always be false now.
   The CLI builds an error's `details` from its fields, so that key is gone from the refusal's JSON
   `details`.
9. **A dry run measures nothing again**, and the summary lists nothing rewritten.
10. **No AWS call, and nothing of the operator's touched.** The only network call was `git fetch`
    of `origin`. `dev` had moved two commits, and `scripts/task sync` rebased the branch.

## Operator follow-ups

None. Everything ran here, the full suite in four parts. Nothing needs a credential, and nothing
read a real store.

## Follow-up work

1. **The backfill runbook's reason for "do not pass `--allow-out-of-order`" is now out of date**
   (`docs/runbooks/caselist-backfill.md`, the paragraph after step 3; E30). It says the newer weeks'
   manifests "would keep the counts and first-seen numbers measured against the wrong week until
   each was imported again". Now they are measured again. The instruction itself still holds for
   that backfill. The PM's note limited the runbook edit to the removal runbook, so I left it.
   Proposed: "It means something newer is already held. Importing it would rewrite the newer weeks'
   manifests, which this backfill has no reason to do."
2. **Older complete archives dated after a late weekly keep their counts** (ruling 3: the newest
   only). Each is a dated record, and the newest is the one the pull reports.
3. **Manifests left stale by an earlier build are not healed.** A late import made with
   `--allow-out-of-order` under t17 or before left later manifests stale. Importing that week again
   now measures nothing, because it was imported before. The backfill runbook forbade the flag, so
   probably none exist. If one does, a `caselist remeasure` command would be the place (E30, small).
   A write that fails partway through a re-measure leaves the same gap.
4. **The run record redacts complete-archive names** (`full/<date>` becomes `[redacted]`, colon
   included) in every import-stage reason, t17's included (E34, `sync_runs.redact`). The counts
   survive.
5. **What a re-measure cannot see** (`later_manifests.py`, "What this cannot see"). A stopped member
   at a path its old previous week did not hold is reported `REMOVED` if the late week holds that
   path. And a complete archive's recount cannot see a member that was stopped at its import. Both
   need a removal and a late import together.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

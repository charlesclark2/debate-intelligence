# Session report: v1-e30-t17-weekly-window-wording-and-ordering

| | |
|---|---|
| Task | `v1-e30-t17-weekly-window-wording-and-ordering` — No text calls a weekly archive cumulative, and import ordering is checked against the window model |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t17-weekly-window-wording-and-ordering.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t17-weekly-window-wording-and-ordering.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t17-weekly-window-wording-and-ordering` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The ordering investigation found no import that does the wrong thing to what is stored.** A weekly
imported after a later one is classified against the weekly dated before it. That is the date-order
answer, so the old refusal message ("would mark current files as removed") described something that
does not happen. Bytes, source records, seen ranges, disclosures, holds and a removal's later uploads
all follow dates, not import order. Two outcomes are wrong under the window model, and each needs a
ruling, so I kept today's behaviour and propose a change for each (Follow-ups 1 to 3):

* **Stale manifests after a late weekly.** When a weekly arrives late, the manifests of the weeks
  after it are not written again. The next week keeps its old previous week and classification
  counts, and every later week keeps its first-seen count. The fixture's first-seen counts then sum to
  7 for 6 distinct files.
* **A low withdrawal count after a late weekly.** A complete archive counts withdrawals once, when it
  is imported. A weekly dated before it that arrives afterwards is never in that count.

The refusal is still the default. `SnapshotOutOfOrder` and the Ordering section now describe what
actually happens and give the remedy, which is tested: import each later week again. The line printed
for the requester no longer calls the weekly cumulative, and it states only what that removal
suppressed. 71 lines in 40 files said "cumulative". Every one that describes a weekly is corrected,
along with six variant phrasings on lines without the word. The ones kept describe the complete archive, the synthetic fixture
(which is cumulative by construction), history, the policy, or something else entirely.

**What to look at first:** the ordering table and its two rows marked wrong, then Deviation 1.
Deviation 1 covers files outside `constraints.packages`, docstrings and a new fixture only.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `window-model` — Weekly windows described and handled correctly | Done | Ordering fixtures and tests first, then the refusal wording (red, then green), then the requester line (red, then green), then the wording sweep |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the search for "cumulative" and its variants is in the report; every hit describing a weekly is corrected; every hit describing the complete archive is kept | PASS | The search list below: 71 lines in 40 files at `feedb9d`, plus six variant phrasings on lines without the word. `git grep -n -i cumulative -- packages docs scripts tests ops ':!docs/session-reports'` afterwards finds only the kept hits and this task's own tests and fixture. The data-use policy is left to the PM, as briefed |
| ac2 — the requester line is still true and no longer calls the weekly cumulative, by test | PASS | `uv run --frozen pytest packages/debate_cli/tests/commands/test_caselist_remove_requester_line.py`: `5 failed` before the change, all on the old line; `222 passed` for `packages/debate_cli/tests/commands/` after it. Covers `--source` (path held), `--team` (whole file plus a withdrawn shared copy), `--only-named`, a withdrawal only, and a plan that removes nothing |
| ac3 — the ordering investigation on synthetic fixtures; result in the report; any defect fixed, failing first; Ordering section and `SnapshotOutOfOrder` rewritten | PASS | `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_import_window_ordering.py`: before the rewrite `2 failed, 15 passed`, and the 2 were the message tests; after it, `17 passed`. The 15 behaviour tests passed against hand-worked answers on the first run. Table below. The two outcomes that need a ruling are diagnosed, the conservative behaviour is kept, and Follow-ups 1 and 3 say what I would change |
| Node `window-model`: Import tests pass (`uv run pytest packages/debate_core/tests/application -k "import or order or removal"`) | PASS | `430 passed in 49.48s` (run with `--frozen`) |
| Full suite, four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | `1673 passed`; `1681 passed, 1 xfailed`; `1686 passed, 1 skipped`; `1684 passed, 1 xfailed`. See "Full suite" below |
| Lint, types, import contracts, command blocks | PASS | `ruff format --check` and `ruff check` on the 28 changed Python files: clean. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `scripts/check_command_blocks.py`: OK |
| Goal set to `Succeeded`; `uv run scripts/validate_specs.py` | PASS | `uv run scripts/task_helper.py set-phase v1-e30-t17-weekly-window-wording-and-ordering Succeeded`, then `OK: 347 files, 38 epics, 289 tasks, 20 releases` |

### Full suite

Run on the final code (commit with this report's draft), one command each, after checking the load
average (8.6 to 16.9), each under a hard stop:

| Part | Command | Result |
|---|---|---|
| 1/4 | `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1673 passed in 32.84s` |
| 2/4 | `… --part 2/4` | `1681 passed, 1 xfailed in 50.28s` |
| 3/4 | `… --part 3/4` | `1686 passed, 1 skipped, 1 warning in 36.87s` |
| 4/4 | `… --part 4/4` | `1684 passed, 1 xfailed in 45.50s` |

The xfails are the cite-detection example marked "left as it is", and the skip is the parser eval's
uncorrected files: neither is this task's. An earlier part 1, run before the last two commits at a
load average of 27, took 135 s (`1673 passed`). `dev` had not moved at the end (`git fetch`, then
`HEAD..origin/dev` empty), so no sync was needed.

## The search list (ac1)

Searched at the start commit `feedb9d`: `git grep -n -i cumulative -- packages docs scripts tests ops
README.md ':!docs/session-reports'`, then the variants: "republishes every …", "every week until …",
"next week's/next Monday's archive", "superset", "contains everything", "whole caselist", "backwards".
Session reports are records and were not searched or edited. Line numbers are as at `feedb9d`.

**Corrected: they described a weekly as cumulative, or reasoned from it.**

| File | Lines | Now says |
|---|---|---|
| `debate_cli/commands/caselist_remove.py` | 703 | The requester line (ac2), below |
| `application/caselist/import_service.py` | 86, 177 (and the refusal message) | The Ordering section and `SnapshotOutOfOrder`, rewritten from the investigation |
| `application/caselist/openev_manifest.py` | 39 | A caselist manifest describes one archive because each is a dated snapshot: a weekly window or a complete archive |
| `application/caselist/pipeline.py` | 25, 65 | Undone by "the next archive that holds the file, weekly or complete"; `REMOVED` is reported for a caselist archive, though a window leaves out untouched files |
| `application/caselist/removal_plan.py` | 34 | "no later archive, weekly or complete, can record it as theirs again" |
| `application/caselist_card_stats.py` | 21 | "the same disclosure carried in three weekly archives" |
| `application/caselist_sync.py` | 134, 159 | The inbox grew by every week's windows; the claim that the newest weekly is the largest is removed |
| `application/ports/caselist.py` | 17, 94 | The same file arrives more than once (carried, re-uploaded, a second team, every complete archive); `latest_snapshot` names the real reason for the refusal |
| `application/ports/suppression.py` | 4–5, 42 (`v1-e30-t13`'s Follow-up 9) | The removed file comes back in every complete archive until taken down, and in any weekly that carries it |
| `domain/card_occurrence.py` | 20–21, 199 | One disclosure arrives more than once: carried between windows, held by every complete archive |
| `domain/caselist/entities.py` | 146, 173 | A weekly is a window dated by its snapshot; dedupe across windows and complete archives |
| `integrations/local/sqlite_caselist_repository.py` | 14–15 | As the port; "between which snapshots was this file seen" |
| `testing/fakes.py` | 429–430 | "the seen-range arithmetic" |
| `tests/application/caselist/test_import_paths_consult_suppression.py` | 3 | As `pipeline.py` |
| `tests/application/caselist/test_import_service.py` | 465, 715, and the out-of-order refusal test's "run the deduplication backwards" | Complete archive and carrying windows; an empty weekly is a quiet window or a broken download; the real reason for the refusal |
| `tests/application/caselist/test_inbox_retention.py` | 4 | As `caselist_sync.py` |
| `tests/application/caselist/test_removal_service.py` | 4, 117 | Every archive that held it still does, and every complete archive will |
| `tests/application/test_caselist_card_stats.py` | 138, 142 | Heading and test renamed: one disclosure held by several snapshots |
| `tests/application/test_caselist_fake_repository.py` | 3–4, 224 | "OpenCaselist republishes every disclosed file every week" replaced; "the seen-range arithmetic" |
| `tests/integrations/local/test_sqlite_caselist_repository.py` | 5, 240 | "the seen-range arithmetic" |
| `scripts/parser_corpus_health.py` | 15 | The same bytes in more than one snapshot: carried, or in a complete archive too |
| `scripts/survey_docx_styles.py` 777 and `docs/data/debate-file-style-survey.md` 211 | | "Point `caselist` at one snapshot: a weekly is one week's window …, a complete archive is the whole caselist" |
| `tests/fixtures/caselist/build_synthetic_archives.py` | 15 | "cumulative the way the real ones are" replaced: the fixture is cumulative, real weeklies are windows, and why it stays so |
| `tests/fixtures/caselist/test_build_synthetic_archives.py` | 96 | "Real weekly archives are cumulative" replaced |
| `tests/fixtures/debate_files/eval/MANIFEST.md` | 46 | Chosen "in the belief that the weeklies were cumulative"; the candidates are one week's files |
| `tests/smoke/test_caselist_remove_smoke.py` | 6, 193 | "a later archive that still holds the team's files" |
| `docs/runbooks/caselist-removal.md` | 15 (the introduction), 69, 212, Step 9's first check and closing paragraph | The introduction says what a weekly and a complete archive hold; "no later archive"; the next weekly may not hold the file; "other teams' disclosures" |
| `docs/runbooks/caselist-scheduled-sync.md` | 1013 | The newest-is-largest sentence removed |
| `docs/runbooks/caselist-backfill.md` | 194 | What a `SnapshotOutOfOrder` really means for the counts |

**Kept.**

| File | Lines | Why |
|---|---|---|
| `import_service.py` | 6–7 | Already says weeklies are windows and the complete archive is the cumulative copy (`v1-e30-t10`) |
| `docs/data/caselist-backfill-2026-09.md` | 260, 264 | Says weeklies are not cumulative; the source of the model |
| `tests/fixtures/caselist/build_revised_path_archives.py` | 4 | Says snapshots are windows, not cumulative |
| `tests/fixtures/caselist/build_synthetic_archives.py` | 1, 290, 373, 584; `expected_summary.json` 5; `test_build_synthetic_archives.py` 1, 7, 91 | Describe the synthetic three-week fixture, which is cumulative by construction. Its module docstring now says real weeklies are not (Decision 1) |
| `tests/fixtures/parse_pipeline/build_parse_world.py` | 14, 26 | The same kind of fixture; line 26 already says real weeklies are windows |
| `packages/debate_cli/tests/commands/test_caselist_pull.py` 108, `tests/smoke/test_caselist_pull.py` 187 | | "the synthetic weeklies are cumulative": true of the fixture |
| `test_import_service.py` 194; `test_removal_service.py` 224 (a test name) | | The synthetic archives. The test name is cited by `v1-e30-t07`'s session report, so it stays (Decision 2) |
| `docs/adr/0016-caselist-corpus-is-accumulated.md` | 19, 40 (and "superset", 20) | A superseded decision record, kept with its reasoning intact (working agreement 7) |
| `docs/policies/caselist-data-use.md` | 31, 65, 411, 578–579 | The policy is the PM's (brief). 578–579 is policy 1.6's own correction. 31, 65 and 411 are Follow-up 5 |
| `docs/process/working-agreements.md` | 141 | History: `v1-e30-t03`'s fixture and dedupe were cumulative |
| `docs/data/caselist-parse-report.md` 330, `docs/policies/website-publishing.md` 623 | | Another meaning: a cumulative distribution; a student's cumulative record |
| `docs/runbooks/caselist-removal.md` | 383 | "the store holds everything else in it": true of an imported archive's other members |

`plan_specs/` was not in the brief's search and is not this task's to edit. Follow-up 4 lists the
specs that still reason from cumulative weeklies.

## The requester line (ac2)

| Removal | Printed |
|---|---|
| Something removed whole, nothing withdrawn (`--source`, `--only-named`, a `--team` whose files are all its own) | `  - Suppressed, so no later archive, weekly or complete, can bring back a removed file.` |
| Removed whole and withdrawn (`--team` with a shared file) | `… can bring back a removed file, or this team's copy of a shared file at the path it was taken from.` |
| Withdrawn only | `… can bring back this team's copy of a shared file at the path it was taken from.` |
| Nothing removed or withdrawn (every file shared and kept) | `  - Nothing suppressed: no file was removed, and no copy withdrawn.` |

Each form is true for the removal it is printed for. A whole file is stopped by its bytes. A withdrawn
copy is stopped only at its path: a re-upload of the shared bytes at a new path is that team's
disclosure again, so the line does not claim more. The old line was printed even when nothing was
suppressed. Whether a path is held is the line before it, from `v1-e30-t13` (`Held: N path(s) …` for
`--source`, `Not held: …` for `--only-named`, and nothing for `--team`). The tests check both lines
for each kind of removal (Decision 4).

## The ordering investigation (ac3)

**Fixture.** `tests/fixtures/caselist/build_window_order_archives.py`: three weekly windows and two
complete archives of `testcl26`. One path is revised every week (`first-`, `second-`,
`third-version`). One file is carried in every window. One is first in the second window and carried
into the third. One is in the second window only and gone by the complete archive. Every answer was
written by hand in its docstring and as literals (`EXPECTED_IMPORTS`, `EXPECTED_HOLDS`,
`EXPECTED_LATER_UPLOADS`) before the tests ran. The paths are the invented ones of
`build_revised_path_archives.py`, and no new name is introduced.

**Tests.** `packages/debate_core/tests/application/caselist/test_import_window_ordering.py`. The
importer is built as the composition root builds it, first-seen reader included, and every manifest
is written as the commands write it. The held-path cases make the removal through the removal service
against moto, so the hold's date is the one a removal computes.

| Scenario | Outcome today (all matched the hand-worked answers on the first run) | Right under the window model? | What changed |
|---|---|---|---|
| Weeklies in date order (reference) | 09-01: NEW 2, first seen 2. 09-08 against 09-01: CHANGED 1, UNCHANGED 1, NEW 2, first seen 3. 09-15 against 09-08: CHANGED 1, UNCHANGED 2, REMOVED 1, first seen 1 | Right | — |
| A weekly after a later one, not allowed (09-01, 09-15, then 09-08) | Refused, `SnapshotOutOfOrder`: "would mark current files as removed" | The refusal is the conservative choice, but the message was **wrong**: nothing is marked removed | **Message rewritten** (red, then green) to say what the flag leaves stale and how to fix it |
| …the same, allowed out of order | 09-08 against 09-01: exactly the date-order answer (CHANGED 1, UNCHANGED 1, NEW 2, first seen 3) | Right | — |
| …and the week after the late one | 09-15's manifest is not written again. It still names 09-01 as its previous week, counts the carried file as NEW (date order: UNCHANGED), has no REMOVED row for the one-week file, and counts first seen 2. First-seen counts sum to **7 for 6 distinct files** | **Wrong**, as a description of the window series. Fixing it needs a ruling: refuse, or re-measure later weeks | Conservative: still refused by default, and the refusal and the Ordering section say this. The remedy is tested: importing 09-15 again (no flag needed) writes the date-order manifests byte for byte. Follow-up 1 |
| …what is stored | Blobs, source records, seen ranges and disclosures are identical to the date-order store | Right | — |
| An older week imported again, not allowed | Refused | Unnecessary (next row), but conservative | **Its own message**: "already imported too … writes its own manifest again, and no other week's". Follow-up 2 |
| An older week imported again, allowed | The same manifest bytes as before; the later week's manifest is not touched | Right | — |
| A complete archive between two weeklies, in date order | `full/09-12`: NEW 3; withdrawn 1, superseded 1, 2 snapshots compared. 09-15 then as in date order | Right | — |
| A complete archive imported before an earlier-dated weekly (09-01, `full/09-12`, 09-08, 09-15) | `full/09-12`: withdrawn 0, superseded 1, 1 compared. Date order gives 1, 1, 2. The weeklies are unaffected | **Wrong**: the count is low and is never recounted. The pull can reach this, because a complete archive is imported even when a weekly queue stopped (`v1-e34-t19`) | Conservative: kept, and the Ordering section says so. Follow-up 3 |
| A complete archive before any weekly, dated before them all (`full/08-29`, three weeklies, `full/09-12`) | `full/08-29`: NEW 2; 0, 0, 0. Weeklies as in date order: first-seen does not read complete archives (`v1-e34-t04`). `full/09-12` against `full/08-29`: CHANGED 1, UNCHANGED 1, NEW 1; 1, 1, 3 | Right | — |
| A complete archive before any weekly, dated after two of them | `full/09-12`: NEW 3; 0, 0, 0 compared. Date order gives 1, 1, 2 | **Wrong**, the same as the row above | As above |
| Held path: a weekly out of order, dated after the hold's date (09-01, 09-15, remove `--source first-version`, then 09-08) | Hold after 09-01; `third-version` a later upload, removed. 09-08: `second-version` SUPPRESSED, counted under the request; UNCHANGED 1, NEW 2; first seen 2 | Right: an upload at the path after the removed file first appeared there | — |
| Held path: a weekly out of order, dated before the hold's date (09-01, 09-15, remove `--source third-version`, then 09-08) | Hold after 09-15; `first-version` an earlier version, kept. 09-08: `second-version` imported, CHANGED 1, UNCHANGED 1, NEW 2, nothing held, first seen 3 | Right: an earlier version, not covered (`v1-e30-t13` Decision 1) | — |
| A removal after a late weekly (09-01, 09-15, 09-08 allowed, then remove `--source first-version`) | Hold after 09-01; later uploads `second-version` (09-08) and `third-version` (09-15); no earlier version. The same as in date order | Right: later uploads are read from manifests by date (`v1-e30-t11`) | — |

**A hold's date is fixed when the removal is made.** It is the earliest snapshot the removal could
read. Suppose a weekly that holds the removed file at the path, dated earlier than that, is imported
after the removal. Its copy of the file is stopped by its bytes, but the hold's date does not move.
Only a snapshot dated between the two could be affected. Weeklies are seven days apart, and a complete
archive is imported only when it is the newest listed, so I built no fixture for it. The Ordering
section says when the date is fixed.

### Red, then green

The refusal message. `uv run --frozen pytest
packages/debate_core/tests/application/caselist/test_import_window_ordering.py`, commit `c6d0778`:

```text
FAILED …::test_the_refusal_of_a_week_never_imported_says_what_importing_it_leaves_behind
FAILED …::test_the_refusal_of_a_week_already_imported_says_importing_it_again_changes_no_other_week
2 failed, 15 passed in 5.41s
```

Both failed on the old text (`… would mark current files as removed; pass --allow-out-of-order if
that is what you mean`). Commit `3a47744`: `17 passed in 4.95s`.

The requester line. `uv run --frozen pytest
packages/debate_cli/tests/commands/test_caselist_remove_requester_line.py`, commit `759a5e7`: `5
failed in 2.27s`, each on `'  - Suppres... of it back.'`, the old line. Commit `a7ccdea`:
`packages/debate_cli/tests/commands/` `222 passed in 17.26s`.

### Mutation runs

Each mutant was applied to the committed source, run against the named test file with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8; none of these tests uses Hypothesis), then
restored with `git checkout`, and the tree was checked clean afterwards.

| Mutant | Target | Result |
|---|---|---|
| The baseline is the latest weekly, not the latest dated before (the reasoning the old Ordering section assumed) | ordering tests | CAUGHT, 5 failed |
| No refusal at all | ordering tests | CAUGHT, 4 failed |
| A week already imported gets the never-imported message | ordering tests | CAUGHT, 1 failed |
| A hold covers every snapshot, whatever its date | ordering tests | CAUGHT, 1 failed (`dated before the hold's date`) |
| First-seen reads complete archives too (`full_archives=True`) | ordering tests | NOT CAUGHT, and **equivalent**: the filter compares snapshot names as strings, and `"full/2026-08-29" < "2026-09-01"` is `False`, so the name comparison alone still leaves every complete archive out |
| Withdrawals counted against snapshots of the same date (`>=` to `>`) | ordering tests | NOT CAUGHT: the fixture has no weekly on a complete archive's date. Against `packages/debate_core/tests/application` and `packages/debate_cli/tests`: CAUGHT, by `test_withdrawal_counts_split_withdrawn_from_superseded` and `test_withdrawals_are_reported_apart_from_the_weekly_path_level_removed` (`v1-e34-t04`). That run's third failure, `test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on`, is a timing test, run at a load average over 20 |
| Withdrawals counted against every snapshot, whatever its date | ordering tests | CAUGHT, 1 failed |
| Requester line reverted to the cumulative wording | requester tests | CAUGHT, 5 failed |
| Requester line always names the withdrawn copy | requester tests | CAUGHT, 3 failed |
| Requester line claims suppression when nothing was removed | requester tests | CAUGHT, 1 failed |
| Requester line drops the removed file | requester tests | CAUGHT, 3 failed |

## Files changed

* **`debate_core.application`**: `caselist/import_service.py`, with the Ordering section and
  `SnapshotOutOfOrder` (a new `already_imported` field and two messages). `_previous_snapshot` now
  reads the snapshot list before the refusal, so the message can tell a re-import apart, and the
  import itself is unchanged. Docstrings only in `openev_manifest.py`, `pipeline.py`,
  `removal_plan.py`, `caselist_card_stats.py`, `caselist_sync.py`, `ports/caselist.py` and
  `ports/suppression.py`.
* **`debate_cli`**: `commands/caselist_remove.py`, the requester line (`_suppressed_line`).
* **`debate_core.domain`, `.integrations.local`, `.testing`**: docstrings only (Deviation 1).
* **Tests**: new `test_import_window_ordering.py` and `test_caselist_remove_requester_line.py`.
  Prose in seven existing test modules, and one test renamed in `test_caselist_card_stats.py`.
* **`tests/fixtures/caselist/`**: new `build_window_order_archives.py`. The synthetic builder and its
  test say real weeklies are windows (Deviation 1).
* **`tests/fixtures/debate_files/eval/MANIFEST.md`, `tests/smoke/test_caselist_remove_smoke.py`,
  `scripts/`**: prose (Deviation 1).
* **`docs/runbooks/`**: `caselist-removal.md` (the introduction, Step 2's acknowledgement, Step 4,
  Step 9; not the two sections `v1-e30-t15` owns), `caselist-scheduled-sync.md`,
  `caselist-backfill.md`.
* **`docs/data/`**: `debate-file-style-survey.md`, one paragraph, the same as its generator.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The constraints list `debate_core.application`,
   `debate_cli`, their tests, `docs/runbooks` and `docs/data`. ac1 asks for every hit in packages and
   docs to be corrected, and the brief adds scripts and tests. So docstrings and comments outside that
   list were changed too: `debate_core.domain` (`card_occurrence.py`, `caselist/entities.py`),
   `debate_core.integrations.local` (`sqlite_caselist_repository.py`), `debate_core.testing`
   (`fakes.py`), `scripts/` (two module docstrings), `tests/fixtures/` (two builders' prose, the eval
   manifest, and the new fixture, which the brief asks to live there), and `tests/smoke/` (prose). No
   code outside the constraints changed. `v1-e30-t11` and `v1-e30-t13` had the same deviation for
   `tests/fixtures/` (their Deviation 4, accepted).
2. **`docs/data/debate-file-style-survey.md` was edited, not regenerated.** It is written by
   `scripts/survey_docx_styles.py` from the operator's corpus. I changed the same paragraph in both, so
   the next run reproduces it.

## Decisions and assumptions

1. **The synthetic three-week fixture stays cumulative.** `expected_summary.json`'s counts were worked
   out by hand for it, and what it tests (hashing, dedupe, classifying against the week before) does
   not depend on the model. Its docstring now says real weeklies are windows. The new fixture is built
   as windows.
2. **Test names were kept,** because `test_the_cumulative_archives_reimported_bring_back_nothing` is
   cited by `v1-e30-t07`'s session report and refers to the synthetic archives. The one renamed,
   `test_caselist_card_stats.py`'s, is cited nowhere.
3. **The refusal stays the default** (the brief's "conservative behaviour"). Both changes to it,
   importing a late week and re-measuring, or dropping the refusal for a re-import, need a ruling.
4. **The requester line does not repeat the hold.** The `Held:` and `Not held:` lines `v1-e30-t13`
   added already say it for each removal. The suppression line says what the list stops, and only what
   this removal put on it.
5. **The held-path cases use the real removal service on moto,** not a hand-written path entry, so the
   hold's date is what a removal computes from the manifests it finds.
6. **No AWS call and nothing of the operator's touched.** The only network call was `git fetch` of
   `origin`, to see whether `dev` had moved. It had not (`HEAD..origin/dev` empty), so no sync was
   needed.
7. **Coordination.** I did not edit `status_service.py`, the S3 version store, or the removal runbook's
   "When `caselist status` reports removal residue" (including "What the report does not see").

## Operator follow-ups

None. The full suite ran here in four parts. Nothing needs a credential, and nothing was run against
the real data directory.

## Follow-up work

1. **A weekly older than the newest: refuse, or import and re-measure (E30; a ruling first).** Under
   the window model a missed week holds evidence no other weekly has. Today the operator has to pass
   `--allow-out-of-order` and then import every later week again, from zips that retention has usually
   deleted. What I would change: allow the late week, then rewrite each later weekly's manifest
   from what the store already holds. Its member rows do not change, and its classifications and
   first-seen count can be recomputed from the disclosures and the earlier manifests without the zip.
   The rewritten manifests are then published as any changed manifest is.
2. **A re-import of a week already imported needs the flag (E30; a ruling).** It writes only its own
   manifest (tested), so the refusal protects nothing. The removal runbook's Steps 6 and "If you
   removed the wrong thing" tell the operator to pass the flag for exactly this. I would drop the
   refusal when the week is already imported.
3. **A complete archive's withdrawal count misses a weekly dated before it that is imported after it
   (E34, `caselist_sync.py`; a ruling).** The pull imports the complete archive even when a weekly
   queue stopped (`v1-e34-t19`). A weekly that failed or was deferred is then never in the count,
   which is in the manifest summary and the run record and is never recounted. Two options: hold the
   complete archive back behind a weekly gap in its caselist, as a newer weekly is held back; or
   recount the newest complete archive's withdrawals after a later import of an earlier-dated weekly.
4. **Specs that still reason from cumulative weeklies (the PM's).** The pending ones matter, because
   they are design premises:
   * `v1-e32-t02`: "reruns on cumulative archives only classify new items".
   * `v1-e32-t03`: "archives are cumulative, so 'new' means first …".
   * `v1-e32-t04`: "cumulative totals" and the weekly archives.
   * `v2-e35-t02`: "a later cumulative snapshot re-publishes the same key".
   * `v2-e35-t05`: "the next cumulative weekly snapshot".

   The finished specs (`v1-e30` t03, t06, t07, t09 and the epic's t09 line, `v1-e31-t04`, `v1-e34`
   t05, t07 and t11, and the E34 epic) are records.
5. **The data-use policy** still calls the weeklies cumulative at lines 31, 65 and 411 (the sources
   list, the sources table and a measured shape). Policy 1.6's note at 578 records the correction. The
   wording is the PM's, so I propose no sentence here.
6. **Two checks keep complete archives out of first-seen** (`evidence_listing.py`, mutation 5). One
   is the `full_archives=False` flag. The other is the "strictly before" filter, which compares
   snapshot names as strings and so happens to sort every `full/` name after every date. The new
   fixture's "dated before them all" scenario asserts the rule, but mutation cannot tell either check
   from its absence while the other is there. I would compare dates in that filter, so that the flag
   alone carries the rule and the scenario guards it (E30, small).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

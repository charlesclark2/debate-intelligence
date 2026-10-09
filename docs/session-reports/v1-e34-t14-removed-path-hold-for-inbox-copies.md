# Session report: v1-e34-t14-removed-path-hold-for-inbox-copies

| | |
|---|---|
| Task | `v1-e34-t14-removed-path-hold-for-inbox-copies` — A camp file already in the inbox is held if its path was removed |
| Spec | [`plan_specs/v1/e34-caselist-sync/t14-removed-path-hold-for-inbox-copies.yaml`](../../plan_specs/v1/e34-caselist-sync/t14-removed-path-hold-for-inbox-copies.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t14-removed-path-hold-for-inbox-copies` |
| Session status | COMPLETE |

## Summary

The removed-path hold (`same_path_as_a_removed_file`, `v1-e34-t07`) is now asked before the inbox
shortcut for every listed camp id the delivery record does not know. Before, a new id at a removed
file's path whose copy was already in the inbox was imported: the red run below stored the revised
bytes. Now that copy is held, and it is not imported, deleted or renamed. Retention keeps it as
`not_imported`, which a test checks. The next run after `caselist unsuppress` imports it from the
inbox with no download. The hold still asks about the old row's own bytes for a revision
(`v1-e34-t08`). When the hold has a question and the list cannot be read, the copy waits as
`suppression_list_unreadable` rather than being imported. All three mutations the PM named were
caught, each on a fresh Hypothesis database. The t07 and t08 test files are unchanged and pass.
**Look first at** Decisions 2 and 3: how I read "the unreadable-list wait" and "every summary names
the file `openev-<id> (sha256 …)`". Then Follow-up 1, a related gap I found and left alone.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `inbox-copy-hold` — The hold before the inbox shortcut | Done | `_judge_unrecorded` now asks the hold first, through a new `_removed_path_hold` method (the hold's logic moved there unchanged). The select stage names a held id by `label`. Docstrings and both runbooks updated. 9 new tests in `test_removed_path_hold_for_inbox_copies.py`, shown failing first, and three mutations, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a new id at a removed file's path whose copy is already in the inbox is held as `same_path_as_a_removed_file` and not imported, shown failing first; after `unsuppress` it is imported from the inbox without a download | PASS | **Red first**, on the unchanged code (the branch start, `f02037d`, which is `d917880` after the rebase): `uv run pytest packages/debate_core/tests/application/caselist/test_removed_path_hold_for_inbox_copies.py -q` → **7 failed, 2 passed**. The two that passed are the ac2 "imported as before" cases, as intended. The main case, `test_a_new_id_at_the_path_of_a_file_removed_here_is_held_with_its_copy_already_in_the_inbox`, run alone with `--no-cov -n0`: `AssertionError: the held copy was imported` / `assert (('openev 2026-policy',), 1) == ((), 0)`. Today's code imported the revised camp file and stored one new blob. The other six failed on `{640: ALREADY_IN_INBOX} != {640: SAME_PATH_AS_A_REMOVED_FILE}` (or `!= SUPPRESSION_LIST_UNREADABLE` for the unreadable-list case). **Green** after the fix: all 9 pass. Held, removal made here: no fetch, nothing imported, no blob for the revised bytes, the copy's bytes unchanged, `revision_of` null, the selection's JSON written out in full by hand, and the select reason contains `1 held back as a new id at a removed file's path (openev-640 (sha256 <first 12 hex>))`. Held, removal only in the bucket's copy, with the delivery record kept and with it lost: the same checks, and 512's old row is still in the manifest. **After unsuppress** (removal made here, and made on another machine): `openev_fetches` stays `[512]`, decision `already_in_inbox`, `blobs_stored 1`, `snapshots_imported ('openev 2026-policy',)`, the blob exists, and `revision_of` is null (removed here) or 512 (another machine). The run after that is `already_imported`. **Naming:** the summary JSON and `record_for_summary` (what `caselist runs` keeps) contain none of `Tamarack`, `TSF`, `Estuary`, `Solvency`, `Advocate`, or the copy's inbox file name, in every held and released run. |
| **ac2**: an inbox copy at a path nothing removed is still imported as before, and v1-e34-t07's and t08's tests pass unchanged | PASS | `test_an_inbox_copy_of_a_new_file_at_a_path_nothing_removed_is_imported_as_before`: 777, never seen, with nothing at its path → `already_in_inbox`, no fetch, `blobs_stored 1`. `test_an_inbox_copy_of_a_revision_of_a_file_nothing_removed_is_imported_as_before`: the hold asks the list and lets 640 through → `already_in_inbox`, `revision_of 512`, no fetch, imported. `git diff d917880 --stat -- …/test_sync_skips_suppressed_downloads.py …/test_sync_fetches_revised_camp_files.py` → empty, so those files are unchanged. `uv run pytest packages/debate_core/tests/application/caselist --no-cov -q` → **472 passed** (before rebasing). After `scripts/task sync`, that directory plus `test_caselist_sync.py`, `test_sync_runs.py`, `test_landscape_staleness.py`, the CLI `caselist pull` / `caselist runs` / retryable-failure tests and the three caselist smoke files → **631 passed in 20.78s**. |
| **ac3**: the hold's position is mutated (asked after the inbox return) and shown caught | PASS | See *Mutation runs* below: **caught by 7 of 9 tests**. The same mutant leaves all **36** t07 and t08 tests passing, so the new tests are the only thing that pins the hold's position. |
| Node `inbox-copy-hold`: Caselist tests pass, `uv run pytest packages/debate_core/tests/application/caselist -k "removed or inbox"` | PASS | Run on the rebased branch, with coverage as CI runs it: **73 passed in 9.68s** (11.1 s wall clock). |

### Mutation runs

Each mutant was applied by a script that refuses to run if its target text is missing. Each run set
`HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty directory created with `mktemp -d` and checked empty
first (working agreement 8). The source was restored with `git checkout` and checked clean with
`git diff --quiet` after every run. None of these tests is a Hypothesis property, so
`--hypothesis-show-statistics` does not apply; the fresh database is there to follow the agreement,
not because a property could replay. Command per run:
`HYPOTHESIS_STORAGE_DIRECTORY=<fresh dir> uv run pytest packages/debate_core/tests/application/caselist/test_removed_path_hold_for_inbox_copies.py --no-cov -q -n0 -p no:randomly`.
Each run took under 3 seconds.

| Mutation | Result | What caught it |
|---|---|---|
| **The hold moved back after the inbox return**: the inbox copy is read first, and the hold is asked only if no delivery was found (the pre-task order) | CAUGHT, 7 failed, 2 passed, 1.38 s (2.07 s wall clock) | Every held case: `AssertionError: the held copy was imported` / `assert (('openev 2026-policy',), 1) == ((), 0)`. Also the unreadable-list case (`ALREADY_IN_INBOX != SUPPRESSION_LIST_UNREADABLE`) and the retention case. The two "imported as before" tests pass, as they should. |
| **The hold's revision branch dropped**: the `earlier.extend(…digests_named_by_id…)` line deleted, so the old row's own bytes are no longer asked | CAUGHT, 1 failed, 8 passed, 1.69 s (2.37 s wall clock) | `test_a_revision_of_a_file_removed_on_another_machine_is_held_with_its_copy_already_in_the_inbox[delivery-record-lost]`: `the held copy was imported`. With the record lost, only 512's row can say which bytes it had. The `delivery-record-kept` variant still passes, because the record's entry for 512 finds the removal. That is why both variants exist. |
| **The unreadable-list wait removed for inbox copies**: `_judge_unrecorded` ignores the hold's `SUPPRESSION_LIST_UNREADABLE` when the id has an inbox copy | CAUGHT, 1 failed, 8 passed, 1.40 s (2.08 s wall clock) | `test_with_the_list_unreadable_an_inbox_copy_the_hold_must_ask_about_waits`: `{640: ALREADY_IN_INBOX} != {640: SUPPRESSION_LIST_UNREADABLE}`. In that test the importer reads a list it *can* read, so without the wait it would store 640. |

### Checks CI runs

`uv run --frozen ruff check .` → All checks passed. `uv run --frozen ruff format --check .` → 534
files already formatted. `uv run --frozen pyright` → 0 errors (5.7 s). `uv run lint-imports` → 11
kept, 0 broken. `uv run scripts/check_command_blocks.py` → OK, 201 blocks in 108 files.
`uv run scripts/validate_specs.py` → OK: 319 files, 38 epics, 261 tasks, 20 releases.

## Files changed

- `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  - `_judge_unrecorded` asks the hold before it reads an inbox copy, for every id the delivery
    record does not know. The hold's logic moved unchanged into `_removed_path_hold` (it now returns `None` for "no hold"), including its
    revision branch and its unreadable-list wait.
  - `_removal_sentence` names held ids by `OpenEvSelection.label`, so a held inbox copy reads
    `openev-640 (sha256 …)`. One with no copy still reads `openev-640`, so t07's and t08's
    assertions hold.
  - The docstrings of `_judge_unrecorded` and of the module's "A camp file that changed upstream"
    section say the hold covers inbox copies.
- `packages/debate_core/tests/application/caselist/test_removed_path_hold_for_inbox_copies.py`
  (new): 9 tests. It reuses the t07 and t08 helpers. The real removal service runs against moto,
  the camp files are synthetic fixtures, and every expectation was written by hand.
- `docs/runbooks/caselist-scheduled-sync.md`: the `same_path_as_a_removed_file` paragraph now says
  the hold covers copies already in the inbox. It also covers how such a copy is named, that
  retention keeps it and `caselist remove` leaves it, and that after `unsuppress` it is imported
  with no download. The `suppression_list_unreadable` paragraph now mentions such copies.
- `docs/runbooks/caselist-removal.md`: one sentence in the inbox step's "Left alone" bullet. A
  later upload at a removed path, downloaded before the removal, is left alone because its bytes are
  new, and the pull holds it.
- `plan_specs/v1/e34-caselist-sync/t14-removed-path-hold-for-inbox-copies.yaml`: Goal phase set to
  `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

1. **"Unrecorded" means the delivery record has no entry for the id.** The spec's case is an id
   with an inbox copy and no delivery entry. An id *with* a delivery entry is one this machine
   imported (the record is written after an import), and it is still judged on its own bytes as
   before. The hold has never applied to those, and changing that was not asked.
2. **The unreadable-list wait applies when the hold has a question.** It applies when some earlier
   id is at the path: a remembered entry, or a revision's old row. With an unreadable list, such a
   copy now waits as `suppression_list_unreadable`, as a download of it already did (t07, t08).
   A copy at a path nothing else has used still goes on to the import, as t07 decided, and the
   importer fails closed on the same unreadable list. Making every inbox copy wait would change
   t07's behaviour beyond this task, and the PM's "as t07 and t08 already do for a download" points
   to the hold's wait. If you meant every inbox copy, it is a one-line change, and I would add a
   test for it.
3. **Naming.** The select stage's reason names a held copy `openev-<id> (sha256 <12 hex>)`. The
   selection's JSON carries `openev_id` and `inbox_file: "sha256 <12 hex>"`. Retention's entry for
   the kept copy is `sha256 <12 hex>`, the form `v1-e34-t11` and `t12` set for every camp download,
   with the same digest prefix as the selection's `inbox_file`, so the two can be read together.
   None of these carries a path, title or inbox file name, and tests check that. I did not change
   retention's naming, which t11's tests pin.
4. **A copy whose own bytes are suppressed *and* whose path holds a removed earlier id** is now
   labelled `same_path_as_a_removed_file` instead of `skipped_as_removed`, because the hold is asked
   first. Neither label lets it be imported or fetched, and no existing test sets up this case.
5. **Proving retention keeps a held copy.** The t07 pull helper wires no status service, so
   retention is skipped there. The retention test builds the same pull with
   `CaselistStatusService` added. It shows the copy kept as `not_imported`, with `removed: []`,
   and a second run holds it again rather than fetching it.
6. **`scripts/task sync`** force-pushes only when the task branch already exists on origin. I
   checked with `git ls-remote --heads origin task/…` (empty) before running it, so it fetched and
   rebased and pushed nothing. The only new commit on dev was a generated-docs refresh, and the
   rebase was clean.

## Operator follow-ups

None.

## Follow-up work

1. **A revision imported before its old version was removed stays in the store** (E30 removal, or
   a policy question for you). Example: 640 (a revision of 512) was fetched and imported, and 512
   was removed later. 640's own row holds it as `already_imported`, so the sync never reaches the
   hold, and `caselist remove --source <512's sha256>` removes only 512's bytes. Under the t07
   ruling that a removal covers a later upload at the same path, 640's bytes arguably fall under the
   same request. This task's hold covers only files not yet imported. Removing imported material is
   the removal procedure's job (spec: forbidden), so I did not touch it. Whether a removal should
   offer to take down later uploads at the same path is your call.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-09

**Notes:**

Accepted. Merge with `scripts/task pr`; the Goal is `Succeeded`.

- **Checked against the branch:** `9473c8a`, tree clean, 0 commits behind `origin/dev`.
  - `_judge_unrecorded` asks `_removed_path_hold` before it reads an inbox copy. The hold's logic moved without changing, its revision branch included.
  - The red run stored the revised bytes, and the fix holds them.
  - All three mutants the PM named were caught. Moving the hold leaves all 36 t07 and t08 tests green, so these new tests are what pins its position. That is the right evidence.
  - The t07 and t08 test files are byte-for-byte unchanged.
- **Decisions 1–6 are accepted.**
  - Decision 2 reads the PM correctly. The wait applies when the hold has a question, as it already did for a download, and a copy at a path nothing else used goes on to an importer that fails closed on the same unreadable list. Making every inbox copy wait would have changed t07.
  - Decision 3: `inbox_file` and retention's entry share the same `sha256` prefix, so the two can be read together.
  - Decision 4's relabelling (`same_path_as_a_removed_file` taking precedence over `skipped_as_removed`) blocks the same things it blocked before.
  - Decision 5 proves retention keeps the held copy with a status service wired in, rather than assuming it.
- **Follow-up 1 is a real policy gap. The PM rules on it and files it.**
  - Under v1-e34-t07's ruling, a removal covers later uploads at the same path. So a revision imported before its old version was removed falls under the same request.
  - That is removal work, not sync work. The PM files an E30 task (priority 2): `caselist remove`'s plan lists every later upload at a removed source's path that the store holds, by id and digest, and includes it in the removal, so the operator confirms one plan that covers them all.

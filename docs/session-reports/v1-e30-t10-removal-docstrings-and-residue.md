# Session report: v1-e30-t10-removal-docstrings-and-residue

| | |
|---|---|
| Task | `v1-e30-t10-removal-docstrings-and-residue` — caselist status reports noncurrent versions a removal left behind |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t10-removal-docstrings-and-residue.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t10-removal-docstrings-and-residue.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t10-removal-docstrings-and-residue` |
| Session status | COMPLETE. The Goal is `Succeeded`. Read Deviation 1 before accepting that |

## Summary

`caselist status` now lists the bucket's object versions with the everyday profile and reports, per
caselist, what is left of every file the suppression list says was removed whole: current objects,
noncurrent versions and delete markers, by a twelve-character digest prefix and counts. Because it
works from the list, it covers later uploads taken down with the file a request named. Anything
found exits 1. A refused listing is reported as not checked, with `null` counts, and does not change
the exit code. The other five criteria are done: the grant docstrings, the import docstring, the
suppression list's path, the `--source` holder count (ac6, added first, verbatim) and the runbook.
30 mutations were run and 30 caught, one only after I added the test it showed was missing.

**Three things to look at first.**

1. **The report's reach is narrower than "a removable prefix" (Deviation 1).** It reports objects
   whose key is the file's sha256, under `raw/` and `parsed/`. It does not read noncurrent versions
   of manifests or of the parsed store's aggregates, and it cannot attribute a shared file that was
   withdrawn from one team. The command and the runbook say so. I set the phase to `Succeeded`
   because ac2 asks for digest prefixes of versions, which only a digest-named object has. If you
   read ac2 wider, the phase is yours to set back.
2. **I edited two tests of the pull (Deviation 3).** ac5 changes what this machine's suppression
   list is called, and two pull tests depended on the old value: one assertion and one line of
   set-up. No pull source changed, and the pull's runs list no versions.
3. **A finding ac1 turned up (Follow-up 3).** Since `v1-e29-t06`, the takedown preflight no longer
   stops the everyday profile named by mistake before it writes. By the policy's text it now writes
   its probe and is refused at the delete, leaving the probe. I corrected the docstring and the
   runbook sentence. I did not change the preflight.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `residue-report`: Docstrings and the residue report | Done | Its criterion passes: `189 passed`. All six Goal criteria pass. |

## Acceptance criteria

Commit ids are on the branch after `scripts/task sync`, on `origin/dev` at `c3f3cb6`. The sync
brought in only the generated `ROADMAP.md` and `docs/README.md` (#221) and rebased cleanly. The
branch is not on origin, so nothing was pushed.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: both docstrings describe the grant as applied, and say what happens where it is not | PASS | `removal_plan.py` and `integrations/s3/version_store.py` now say the everyday profile has read-only `ListBucketVersions` under the removable prefixes (`v1-e29-t06`, dev and prod, 2026-10-08), and that without the grant the listing is refused and the plan says "versions not counted". Other places said the same stale thing and are corrected: the version port's docstring, the takedown preflight's, the status service's, a comment in the composition root, and the docstrings of three test doubles that stand for the everyday profile. `grep -rn "does not have today\|until then (the session\|can do neither\|grant the everyday profile lacks\|may not list versions today\|not visible to the everyday" packages/*/src` → 0 lines. The four docstring-only files have the same AST as `origin/dev` with docstrings removed. Commit `82222cd`. |
| **ac2**: `caselist status` reports, per caselist, the count and digest prefixes of noncurrent versions left after a removal, everyday profile only, shown with moto failing first; a refused listing says not checked | PASS, within the reach Deviation 1 states | **Red first**, commit `f015a25`: `uv run pytest tests/smoke/test_caselist_remove_smoke.py` → `5 failed, 14 passed`. With two restorable versions of a removed later upload under a delete marker, status exited 0 (`assert 0 == 1`) and reported every snapshot in sync; the others failed on `KeyError: 'removal_residue'`. The core tests of the report did not collect at that commit (the module they import did not exist), so they are not red evidence. **Green**, commit `b3c759a`: 18 core tests and 6 command-level tests, all on moto. Later uploads: see "What the report covers" below. Refusal: `test_a_refused_version_listing_says_not_checked_and_never_that_nothing_is_left` (exit 0, `checked: false`, `not_checked_reason: STORE_ACCESS_DENIED`, counts and `files` all `null`, text says NOT CHECKED and does not say nothing is left). Everyday profile only: `test_status_reports_residue_with_the_everyday_profile_and_never_deletes_or_downloads_a_version`. |
| **ac3**: the runbook says what to do when the report shows residue | PASS | New section *When `caselist status` reports removal residue* in `docs/runbooks/caselist-removal.md`, commit `260595c`: the three things the command can say, what each count means, which later uploads are covered (in t11's terms), who runs what with which profile, and how to confirm it is gone. Both of its instructions are tests (see below). `uv run scripts/check_command_blocks.py --base origin/dev` → OK. `uv run scripts/check_links.py` → OK, 1399 links and anchors. |
| **ac4**: the opening paragraph of `import_service.py`'s docstring says a weekly archive is a window and the complete archive is the cumulative copy; no change to code | PASS | Commit `40fd090`. The paragraph cites the backfill report's section and its measured figure (2,374 members, 2,107 distinct files across three adjacent weeks). The module's AST with docstrings removed equals `origin/dev`'s. I also corrected two clauses below it that said the same wrong thing (Deviation 6). |
| **ac5**: the local copy is named by its role, never by path; a probe data directory shows the path gone from the message and the JSON envelope, failing first; exit code unchanged | PASS | **Red first**, commit `20d8820`: `7 failed` (4 through `caselist import`, 3 in core). The probe marker in the data directory's path was in the message and in `error.details.location`. **Green**, commit `7612e0d`: `39 passed` in the two files. The message is now `the local suppression list under storage.data_dir line 2 is not readable: …`, `details.location` is the same role, the code is still `UNREADABLE_APPEND_ONLY_RECORD` and the exit code is still 1. |
| **ac6**: a `--source` plan counts only teams other than the one removed; a file no other team holds says nothing about other teams; failing first for a one-holder and a two-holder file, in the text and the JSON; JSON keys unchanged | PASS | Added to the spec verbatim as the first commit, `ca57c41`. **Red first**, commit `ffd8c48`: `4 failed, 1 passed`. One holder: `assert 1 == 0`, and the text read `also held by 1 other team(s)`. Two holders: `assert 2 == 1`, and `2 other team(s)`. **Green**, commit `ec0502a`. Each source's JSON keys are asserted equal to the fourteen `v1-e30-t11` settled. |
| Node: `uv run pytest packages/debate_core/tests/application -k "removal or status"` | PASS | `189 passed in 20.24s` on the synced branch. |

### What the report covers, and the two shapes residue takes

S3 decides what a removal leaves, so both shapes are tested, in the service and through the command.

| Shape | How the test makes it | What is reported |
|---|---|---|
| A takedown stopped among a later upload's versions | A real `--source` removal whose plan adds the revision as a later upload. The revision's object has three versions. The takedown's version store deletes the first and loses the bucket. | S3 makes the next version current: 1 current object and 1 noncurrent version of the later upload, and nothing of the file the request named, which was fully deleted. The same command run again leaves none. |
| Versions hidden under a delete marker | After a complete removal, two versions are put back at the later upload's key and deleted without a version id. | 0 current objects, 2 noncurrent versions, 1 delete marker. No plain listing shows the key, every snapshot agrees, and before this task status exited 0. |

The first shape matters for how the report is worded. A takedown deletes each version by id, and
deleting the current version by id promotes the one beneath it. So what a stopped takedown leaves
is mostly a *current* object, not a noncurrent version. The report therefore counts all three
(Decision 2).

### The runbook's two instructions, as tests

| Status says | The runbook says | Test |
|---|---|---|
| Snapshots differ too (`CASELIST_DRIFT`), residue in the details | Run the same command again | `test_a_takedown_stopped_among_a_later_uploads_versions_shows_in_status_until_the_rerun` (command), `test_the_later_uploads_versions_are_reported_and_a_rerun_leaves_none` (service) |
| Every snapshot agrees (`REMOVAL_RESIDUE`) | Name the listed file by `--source`, same request | `test_residue_a_completed_removal_left_is_cleared_by_naming_the_file_under_the_same_request` (command), `test_the_original_command_no_longer_finds_a_later_upload_and_naming_the_file_does` (service) |

I wrote the second test before the runbook, to find out what clears that case. The original
command does not: once a later upload's manifest rows are gone, nothing shows it at the removed
path, and the plan says nothing is left to remove. Naming the file plans all three versions.

### Mutation runs

30 mutants, each one textual change to committed source. The driver refuses a dirty tree and a
target that does not occur exactly once, runs 101 tests (102 after the first survivor) with
`-n auto --no-cov -p no:randomly`, restores the file from a byte copy and checks its sha256 and
`git diff --quiet`. Each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`; none of these tests is
a Hypothesis property, so that is to follow working agreement 8. No mutant failed at collection.
The runs were made before the sync, which changed none of the files involved. Each run took 10 to
27 s. Seven batches, 32 runs; one batch of eight mutants ran 2 min 24 s, which is over the
two-minute line, and I cut the later batches to four or five.

| # | Mutation | Result | Caught by (first of the failing tests) |
|---|---|---|---|
| **The residue listing** | | | |
| R1 | Every digest-named object counts, suppressed or not | CAUGHT, 13 failed | `test_a_file_nobody_removed_is_never_residue_whatever_versions_it_has` |
| R2 | A file suppressed for one disclosure counts as removed whole | CAUGHT, 2 failed | `test_a_file_withdrawn_from_one_path_only_is_still_held_and_is_not_residue` |
| R3 | A delete marker is not told from a version | CAUGHT, 3 failed | `test_versions_hidden_under_a_delete_marker_are_found_where_the_plain_listing_sees_nothing` |
| R4 | Current and noncurrent swapped | CAUGHT, 5 failed | `test_a_current_object_with_versions_beneath_it_is_counted_as_one_and_the_rest` |
| R5 | `parsed/` is not listed | CAUGHT, 3 failed | `test_it_lists_versions_under_the_caselists_raw_and_parsed_prefixes_and_changes_nothing` |
| R6 | A current object is not counted | CAUGHT, 5 failed | the same test as R4, and the stopped-takedown test |
| R7 | A key with an extension is not matched | CAUGHT, 1 failed | `test_a_removed_files_parsed_cards_are_counted_with_it_and_the_aggregates_are_not` |
| R8 | Files are not sorted by digest | **SURVIVED, then CAUGHT** after a test was added | `test_a_file_left_only_under_parsed_is_listed_in_digest_order_with_the_rest` |
| R9 | The whole of `raw/` is listed, not the caselist's prefix | CAUGHT, 2 failed | the prefix test, and the camp-file test |
| R10 | A noncurrent version is not counted | CAUGHT, 8 failed | the same test as R4 |
| R11 | The twelve-character prefix is the whole digest | CAUGHT, 3 failed | `test_files_are_listed_in_digest_order_and_named_by_a_twelve_character_prefix` |
| **The refusal path, and what is reported** | | | |
| F1 | A refused listing is read as an empty one | CAUGHT, 3 failed | `test_it_says_not_checked_with_the_refusals_code_and_never_none` |
| F2 | A bucket that does not answer is "not checked" too | CAUGHT, 1 failed | `test_a_bucket_that_does_not_answer_is_an_error_not_an_unchecked_caselist` |
| F3 | An unchecked caselist counts zero | CAUGHT, 2 failed | the same test as F1 |
| F4 | The JSON gives an unchecked caselist an empty list of files | CAUGHT, 1 failed | `test_a_refused_version_listing_says_not_checked_and_never_that_nothing_is_left` |
| F5 | The text says nothing is left when nothing was checked | CAUGHT, 1 failed | the same test as F4 |
| F6 | An unchecked caselist fails the comparison | CAUGHT, 2 failed | `test_an_unchecked_caselist_does_not_fail_a_comparison_that_otherwise_agrees` |
| F7 | Residue does not fail the comparison | CAUGHT, 2 failed, then 3 | At first only the command-level tests. I added the assertion to the service test and ran it again. |
| F8 | Versions are listed whether or not the caller asked | CAUGHT, 1 failed | `test_a_status_that_does_not_ask_lists_no_versions` |
| F9 | The command does not ask for the check | CAUGHT, 6 failed | `test_status_after_a_complete_removal_says_it_checked_and_nothing_is_left` |
| F10 | The status's version store is built with the takedown profile | CAUGHT, 4 failed | `test_status_reports_residue_with_the_everyday_profile_and_never_deletes_or_downloads_a_version` |
| F11 | Residue beside drifted snapshots is reported as `REMOVAL_RESIDUE` | CAUGHT, 1 failed | the stopped-takedown command test |
| F12 | The JSON names a file by its whole digest | CAUGHT, 2 failed | `test_versions_of_a_later_upload_left_under_a_delete_marker_fail_status_by_prefix_and_count` |
| F13 | The message names a file by its whole digest | CAUGHT, 1 failed | the same test |
| F14 | The not-checked reason is dropped from the JSON | CAUGHT, 1 failed | the same test as F4 |
| F15 | Asking without a version store reports nothing instead of refusing | CAUGHT, 1 failed | `test_asking_without_a_version_store_is_refused_rather_than_reported_clean` |
| **The ac6 count** | | | |
| A1 | Every holding team is counted as another team (the old behaviour) | CAUGHT, 4 failed | the two planner tests and the two command tests |
| A2 | A file no team holds counts minus one | CAUGHT, 1 failed | `test_a_source_removal_of_a_file_no_team_holds_counts_no_other_team` |
| A3 | Two teams are left out, not one | CAUGHT, 2 failed | `test_a_source_removal_of_a_file_two_teams_hold_counts_one_other_team` |
| A4 | The `--team` count leaves one more team out | CAUGHT, 5 failed | `test_the_teams_own_files_are_removed_and_the_shared_one_withdrawn` |

Three notes on those results:

- **R8 was a real hole.** One prefix's listing is already sorted by key, so every test met its
  files in digest order. The sort matters only for a file left under `parsed/` alone. That case now
  has a test.
- **A2 is caught only by a test I wrote for it in advance.** I expected the mutant and added the
  no-holding-team case before running it. I did not run A2 against the suite without that test.
- **My first implementation failed 11 of the 16 core tests.** The new `residue` flag was shadowed
  by an existing local variable of the same name in `status()`, so the check never ran. Every
  hand-written count passed unchanged once that was fixed.

### Checks CI runs

On the synced branch, with the report and the phase change uncommitted:

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto --cov -m "not slow and not live" packages/debate_core` | `3757 passed in 102.13s` |
| `uv run --frozen pytest -n auto --cov -m "not slow and not live" packages/debate_cli/tests packages/debate_api/tests packages/debate_workers/tests tests` | `1742 passed, 1 skipped, 1 warning in 117.14s`. The skip is the parser eval waiting on human corrections; the warning is `pytest_socket`'s. |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `596 files already formatted` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | OK, this report included |
| `uv run scripts/docs_index.py --check-descriptions` | `All 34 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py --require-succeeded v1-e30-t10-removal-docstrings-and-residue` | `Succeeded` |

The two halves are 5,499 passed and 1 skipped, 37 more tests than `v1-e30-t11` recorded. The second
half took 117 s here, close to the line; the machine was busier than usual.

Coverage of the new module under its tests, with branches: `removal_residue.py` 100%.

## Files changed

- **`debate_core.application`**
  - `caselist/removal_residue.py` (new): counts what a version listing shows of a caselist's
    wholly suppressed files. Lists only.
  - `caselist/status_service.py`: an optional version store, `status(..., residue=True)`,
    `CaselistStatusReport.residue`, and `REMOVAL_RESIDUE`. `in_sync` is false when residue is found.
  - `caselist/removal_plan.py`: the `--source` holder count (ac6), and its module docstring (ac1).
  - `caselist/import_service.py`, `caselist/removal_service.py`, `ports/evidence_versions.py`,
    `ports/suppression.py`: docstrings only.
- **`debate_core.integrations`**: `s3/version_store.py`, docstring only (ac1).
  `local/suppression_list.py`: `location` is a role (ac5; Deviation 2).
- **`debate_cli`**: `commands/caselist.py`: the residue in the status table's caption, in
  `removal_residue` of the JSON, and in the failure. `container.py`: the status service gets a
  version store built with the everyday profile (Deviation 2).
- **Tests**: `test_removal_residue.py` (18, new), `test_removal_plan.py` (+3),
  `test_suppression_list.py` (+3), `test_unreadable_suppression_list_names_no_path.py` (5, new),
  `tests/smoke/test_caselist_remove_smoke.py` (+8) and its README row. Two pull tests, one line each.
- **Docs**: `docs/runbooks/caselist-removal.md`.
- **Spec**: ac6, and the phase.

## Deviations from the spec

1. **The report covers digest-named objects under `raw/` and `parsed/`, not everything a removal
   deletes.** The spec says "noncurrent object versions under a removable prefix whose current
   version a removal has deleted". Three things a removal deletes are not reported:
   - *Noncurrent versions of a manifest.* A removal rewrites a manifest and purges its old versions.
     A leftover one still holds the removed row, which is the most identifying thing in the bucket.
     Its key names no file, so finding it means downloading every noncurrent manifest version. The
     everyday profile may do that (`s3:GetObjectVersion`), but the status service's contract is that
     it downloads nothing, and the cost grows with every re-published manifest. A re-run of the
     removal sweeps them.
   - *Noncurrent versions of the parsed store's aggregates.* A removal deletes these outright, so
     they fit the spec's wording exactly. Their keys name no file either, and every
     `caselist parse --publish` leaves a noncurrent version in normal use, so a count of them would
     always be nonzero and would say nothing.
   - *A shared file withdrawn from one caselist and kept elsewhere.* It is suppressed for one path,
     not whole, and nothing in a key says which holder a version was for.

   The command says "noncurrent manifest versions are not read" on its clean line, and the runbook
   has a paragraph on all three. I did not build the manifest read without your say: it changes
   what `caselist status` does to the bucket and how long it takes (Follow-up 1).
2. **Three places outside `constraints.packages`.**
   - `debate_cli/container.py`: the status service cannot list versions unless the composition root
     gives it a store.
   - `debate_core/integrations/local/suppression_list.py`: ac5 names the error class in the port,
     but the path comes from this adapter's `location`. Fixing it there also takes the path out of
     `AppendOnlyViolation` and out of the "not written to …" clause of a removal that completed
     unlogged, which carried it the same way.
   - `tests/smoke/`: the command-level checks, where `v1-e30-t11` put its own.
3. **Two tests of the pull changed, one line each.** You said to stop if I ended up in pull code. I
   did not stop, because no pull source is involved and ac5 cannot be met without these two lines:
   - `test_pull_stage_failure_codes.py`: an assertion that a stage reason holds
     `suppression-list.jsonl line 1 is not readable`. It now holds
     `the local suppression list under storage.data_dir line 1 …`. The test's other assertions, that
     the reason names nothing of this machine, pass unchanged.
   - `test_sync_skips_suppressed_downloads.py`: set-up that used `location` as a path now uses
     `.path`.

   If `v1-e34-t17` edits either file, these are the lines to keep. The pull's own behaviour is
   unchanged: it calls `status()` without the flag, which `test_a_status_that_does_not_ask_lists_no_versions`
   and mutant F8 hold.
4. **Residue fails the status.** The spec does not say whether it should. It exits 1, as
   `REMOVAL_RESIDUE` when every snapshot agrees and inside `CASELIST_DRIFT`'s details otherwise,
   because the runbook's check after a removal is "`caselist status` is clean". An unchecked
   caselist does not fail it: an environment without the grant would otherwise fail every status.
5. **The report counts current objects and delete markers as well as noncurrent versions.** See
   "the two shapes" above: a count of noncurrent versions alone reads zero while a stopped
   takedown's promoted version sits in the bucket.
6. **ac4 went two clauses past the opening paragraph.** The same docstring's `REMOVED` entry said
   "The team took it down", and its `SUPPRESSED` entry said "the cumulative archives republish it".
   Both contradicted the new paragraph, so I corrected them from the backfill report's own wording.
   I left the *Ordering* section and `SnapshotOutOfOrder` alone (Follow-up 5).

## Decisions and assumptions

1. **The suppression list says what was removed.** A file is residue when its whole source is
   suppressed. That is what makes the report cover later uploads without knowing any request: a
   later upload the plan removed everywhere is suppressed whole, one withdrawn from a path or kept
   is not, and neither is one `--only-named` left in place. The runbook says this in t11's terms.
2. **Three counts per file**: `current_objects`, `noncurrent_versions`, `delete_markers`. A delete
   marker is counted because the takedown leaves none and it hides versions that can be restored.
3. **The check is asked for per call**, `status(..., residue=True)`, and only the command asks. The
   pull holds the same service and would otherwise list every version under each caselist several
   times a run. Whether the scheduled pull should report residue is a question for you (Follow-up 8).
4. **Prefixes**: `raw/caselist/<slug>/` or `raw/openev/`, and `parsed/<caselist>/`. Both are under
   prefixes the grant covers. `files/` and `quarantine/` are removable prefixes nothing writes to
   in V1, so they are not listed (Follow-up 9).
5. **Only `StoreAccessDenied` is "not checked".** An expired session or an unavailable bucket
   raises, as it does for the rest of the comparison, and exits 3.
6. **Twelve characters of the digest**, as the removal plan prints for a later upload. The runbook
   shows how to get from the prefix to the whole sha256 and the request id, with one `grep` of the
   suppression list. The report prints no request id, because you asked for prefixes and counts only.
7. **In the JSON**, `removal_residue` is a list with one object per caselist compared. Unchecked,
   every count and `files` are `null`.
8. **ac6 leaves one team out, not "the" team.** A `--source` removal has no requesting team, so
   "the one removed" is whichever one team holds the file. The count is `max(teams - 1, 0)`.
   `camp_file_holders` is unchanged: it is documented as holders, not other holders (Follow-up 4).
9. **A local record built without a role** is called by its file name alone, which carries no
   directory. Only tests build one that way.
10. **Nothing was run against a real bucket or the real data directory.** The cost of the version
    listing on the real corpus is not measured. It is two listings per caselist on top of what
    status already does.

## Operator follow-ups

None is required. One is worth doing once the run now in progress has finished, because it reads
the dev data directory. Both environments have had real removals, and this is the first check of
what they left. It does not need the merge: this worktree has the change. After
`scripts/task finish` the worktree is gone, and any checkout of `dev` does the same.

**Operator command** (read-only; runtime not measured, it adds two version listings per caselist to
the usual status)
Where: your Mac, in this task's worktree.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t10-removal-docstrings-and-residue
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist status
```

Success looks like: under the table, *No version of a removed file is left under raw/ or parsed/*.
If it says *REMOVAL RESIDUE*, the runbook's new section has the steps. If it says *NOT CHECKED*,
the grant is not reaching that profile. The lines under the table hold digest prefixes and counts
only, so they can be pasted back. Then the same for prod:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t10-removal-docstrings-and-residue
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod uv run debate-research caselist status
```

## Follow-up work

1. **Noncurrent manifest and aggregate versions are not checked** (E30; a ruling first). Deviation 1.
   Reading noncurrent manifest versions with the everyday profile would close the larger half. It
   needs a decision on status downloading from the bucket.
2. **A withdrawn shared file's leftover copy cannot be attributed** (E30). It would need the list,
   or the removal log, to say which caselist a withdrawal took the file from.
3. **The takedown preflight since `v1-e29-t06`** (E30 or E29). Its first step was "list versions,
   the one grant the everyday profile lacks", so naming that profile by mistake failed before
   anything was written. By the operator policy's text the everyday profile now lists under
   `manifests/`, writes the probe, and is refused only at the delete, so the probe is left under
   `manifests/_suppression/preflight/`. Nothing deletes a leftover probe. This is read from the
   policy and the code, not observed: moto does not enforce IAM. The code path has a test already,
   `test_removal_profile_without_delete_rights_fails_preflight_with_nothing_deleted[cannot_delete]`,
   whose sibling `[everyday]` is the state before the grant. A first step the everyday profile
   still cannot do would restore the old guarantee.
4. **Other removal output that names a holder wrongly** (E30). Seen in real plan text for 1 and 2;
   3 is read from the code.
   1. A `--source` plan of a file only one camp file holds says `also held by 1 camp file(s)`. It
      is ac6's defect for camp files. The JSON's `camp_file_holders` is right by its own definition;
      the text's "also" is not.
   2. A `--source` plan says "this team's" where there is no requesting team: `N of this team's
      path(s) to a shared file` above the suppression entries, and `this team's copies of 0 shared
      file(s)` in the facts for the confirmation to the requester.
   3. For a later upload withdrawn from a path, `other_teams` counts the teams at its other paths
      without leaving out the team at the removed path. When the other path is the same team's, the
      plan would say `1 other team(s)` and `another team there still holds it`. No fixture has that
      case, so I have not seen it.
5. **"Cumulative" weekly archives, in about twenty other places** (E30, E34, Charlie's for the
   policy). The ones a person outside the project could read: the line `caselist remove` prints for
   the confirmation to the requester ("next week's cumulative archive cannot bring any of it
   back"), the runbook's introduction, and `SnapshotOutOfOrder`'s message. In `import_service.py`
   the *Ordering* section still reasons from cumulative weeklies. I did not rewrite it because I
   could not confirm what an out-of-order import does under the window model.
6. **`caselist status` does not show `suppressed_rows` or `suppressed_objects`** (`v1-e30-t12`,
   which is already in this command). Neither is in the JSON. With only a current suppressed object
   and the residue unchecked, the failure reads "0 snapshot(s) differ". Where the residue is
   checked, a current suppressed object now shows as a current object in the residue.
7. **The grant's stated purpose** (E29). `operator_access.tf`'s comment and `evidence-store.md` say
   the listing is there so a dry run can count versions. `caselist status` uses it too now.
8. **Should the scheduled pull report residue?** (E34; your call.) It does not, by Decision 3.
9. **`files/` and `quarantine/`** join the check when something writes to them (`v2-e35-t05`).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

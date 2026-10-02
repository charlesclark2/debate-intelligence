# Session report: v1-e30-t09-removal-purges-inbox

| | |
|---|---|
| Task | `v1-e30-t09-removal-purges-inbox` — A removal leaves no removed bytes in the inbox |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t09-removal-purges-inbox.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t09-removal-purges-inbox.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t09-removal-purges-inbox` |
| Session status | COMPLETE |

## Summary

`caselist remove` now purges the sync's download inbox. The dry run lists every downloaded file
that holds something the suppression list will stop, and says whether it will be deleted or
rewritten and why. `--execute` then does that, after this machine's store and before the records.
After a `COMPLETED` run, no inbox file holds a removed sha256, as a file or as an archive member.

The rule for each file:
- **Deleted:** a removed camp document; a camp release whose every file is removed; and every
  weekly archive whose week is already imported.
- **Rewritten without the removed entries, never deleted:** an archive still waiting to be
  imported. The next pull imports exactly its other members from the inbox, and downloads
  nothing.
- **Recorded first:** before a camp file's copy is deleted, its digests go into v1-e34-t07's
  delivery record, so the pull does not fetch the file again.

The residue was shown first against the removal as v1-e30-t07 left it (commit `845a292`, 12
entries). Then 15 deliberate breakages of the guards were each caught on the final tree, every run
with a fresh Hypothesis database. The runbook's manual inbox step is gone.

**Read first:**
- "Decisions", for the delete-or-rewrite call and what a rewritten archive's manifest records.
- Deviations 3 to 5: three things a reviewer could reasonably read differently from me.
- Follow-up 2: hand-made copies of downloaded material outside the store, the buckets and the
  inbox. This task does not reach them.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `show-residue` — Show removed bytes left in the inbox | Done | `test_after_a_completed_removal_no_inbox_file_holds_a_removed_sha256`, committed red as `845a292` against unchanged removal code. Output under ac4. |
| `purge` — Plan and purge inbox copies | Done | New `application/caselist/inbox_purge.py` (rules, plan, purge). `ArchiveRewriter` port, with `ZipArchiveRewriter` beside the reader. The inbox is wired into `RemovalPlanner` and `CaselistRemovalService` as a required argument. The removal log records inbox counts and rewrite digest pairs. The CLI renders a `DOWNLOAD INBOX` section. 17 tests in `test_removal_purges_inbox.py`, plus one smoke check. |
| `runbook` — Retire the manual inbox step | Done | `docs/runbooks/caselist-removal.md`: step 8's manual block replaced by what the command does. Steps 4–7 and 10 and the recovery section follow from that. One sentence added to `caselist-scheduled-sync.md`. |

## Acceptance criteria

Results are from the final tree, `f4c5dee`, unless a row says otherwise.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — The plan lists every inbox file holding a removed sha256, as a file or as an archive member, and what will happen to each; the dry run changes nothing | PASS | `test_the_plan_lists_every_inbox_file_holding_a_removed_file_and_what_happens_to_it` checks a hand-derived list: (name, action, reason, digests, entries out, entries kept) for 09-01, 09-08 and 09-15 (`delete`, imported) and 09-22 (`rewrite`, waiting). The camp release is correctly absent, because `--team` without `--include-shared` leaves its copy of the shared file alone. `test_the_dry_run_changes_nothing_in_the_inbox_or_the_sync_state` plans with and without `--include-shared`, then checks: every inbox file's bytes and mtime are unchanged, the whole data directory is unchanged, and no delivery record was written. Smoke `test_the_download_inbox_is_listed_by_the_dry_run_and_purged_by_the_execution` checks the same through the installed command: JSON `inbox` list, the `DOWNLOAD INBOX (…): 4 file(s) hold removed files.` line, and the inbox tree unchanged. |
| **ac2** — After a COMPLETED removal no inbox file holds a removed sha256; a test removes a team's file that is in one camp download and three weekly archives, and scans the inbox | PASS | The team's Round 1 affirmative is in the camp release and in the 09-01, 09-08 and 09-15 weeklies; the test asserts that before removing. Then `--team … --include-shared --execute`. `removed_bytes_in_inbox`, which opens every file and every zip entry with `zipfile` and shares no code with the removal, finds `[]`. The same holds with an archive waiting to be imported (rewritten, deleted 4, rewritten 1) and for a removed single camp document. |
| **ac3** — An archive not yet imported keeps every member the list does not cover importable, shown by importing it after the removal and storing exactly its non-removed members | PASS | **Weekly:** 09-22 is in the inbox, not yet imported: the 09-15 archive plus ZaLu's new Lakeshore file. After `--team` removal, a pull downloads nothing (`archive_fetches == []`): 09-01 to 09-15 are `already_imported`, 09-22 `already_in_inbox`. The 09-22 manifest rows equal a hand-written table: 10 `UNCHANGED`, 1 `NEW` (Lakeshore), and 3 skipped (symlink, zip-slip, `.DS_Store`). That includes ZaLu's copy of the Round 1 bytes the team withdrew. The disclosures are exactly those 11 paths, and the Lakeshore blob is stored. **Camp:** a camp release no manifest records, holding the removed bytes and one new camp file, is rewritten. A pull imports it from the inbox (`already_in_inbox`, no fetch), stores the new file and not the removed one. |
| **ac4** — Shown failing first against the removal as v1-e30-t07 left it; each guard mutated and caught; the runbook's manual inbox step removed and the procedure describes what the command now does | PASS | Failing first: below. Mutations: 15 of 15 caught, table below. Runbook: `grep -c 'by hand until' docs/runbooks/caselist-removal.md` → `0`. Step 8 now says what was deleted, rewritten or left alone, and why. |
| Node `show-residue` (custom): after a COMPLETED removal under the current code, an inbox scan finds the removed sha256 in a camp download and in weekly archives | PASS | `845a292`: `1 failed` with 12 hits (below). |
| Node `purge`: `uv run pytest packages/debate_core/tests/application/caselist -k inbox` | PASS | `26 passed in 9.63s`: this task's 17, and the 9 of v1-e34-t07's tests whose names mention the inbox. |
| Node `runbook`: `docs/runbooks/caselist-removal.md` exists | PASS | Present, rewritten as described. |
| Whole Python suite, CI's selection: `uv run pytest -m "not slow and not live" packages tests` | PASS | `3628 passed, 1 skipped in 32.21s`. The skip is the pre-existing parser eval waiting on human corrections. |
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run lint-imports` / `uv run pyright` | PASS | `All checks passed!` / `458 files already formatted` / `Contracts: 11 kept, 0 broken.` / `0 errors, 0 warnings, 0 informations` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | PASS | `OK: 298 files, 38 epics, 240 tasks, 20 releases` |

### Shown failing first (ac4, node `show-residue`)

`845a292`, `uv run pytest packages/debate_core/tests/application/caselist/test_removal_purges_inbox.py -n0`
gave `1 failed`. That was after `caselist remove --team 'testcl26/Maple Grove/QX' --include-shared --execute`
had completed. All names are synthetic fixture names:

```
openev-701-openev-2026-policy.zip :: openev-2026-policy/Tamarack/TSF-Borrowed Grove Aff.docx
testcl26-weekly-2026-09-01.zip :: testcl26-0901/Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx
testcl26-weekly-2026-09-01.zip :: testcl26-0901/Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx
testcl26-weekly-2026-09-08.zip :: testcl26-0908/Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx
testcl26-weekly-2026-09-08.zip :: testcl26-0908/Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx
testcl26-weekly-2026-09-08.zip :: testcl26-0908/Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx
testcl26-weekly-2026-09-08.zip :: testcl26-0908/Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx
testcl26-weekly-2026-09-15.zip :: testcl26-0915/Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx
testcl26-weekly-2026-09-15.zip :: testcl26-0915/Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx
testcl26-weekly-2026-09-15.zip :: testcl26-0915/Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx
testcl26-weekly-2026-09-15.zip :: testcl26-0915/Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx
testcl26-weekly-2026-09-15.zip :: testcl26-0915/Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx
```

The same test passes from `1df844b` on. Mutation 15 below brings it back: it removes the new step
from the executor.

## Checks shown failing for their reason

The script is `mutate.py` in the session scratchpad, not the repository. It refuses to start
unless the files it mutates are committed. For each mutation it:
- applies the change by exact text replacement;
- runs `test_removal_purges_inbox.py` with `-n0 -p no:cacheprovider` and a **fresh, empty
  `HYPOTHESIS_STORAGE_DIRECTORY` per run** (working agreement 8; none of these tests uses
  Hypothesis, so there are no generation statistics to report);
- restores the file from a saved copy and checks it byte for byte against `HEAD`.

The final run was on `f4c5dee`. None of the runs errored before running.

| Guard | Mutation | Result | Failing for its reason |
|---|---|---|---|
| Pending-archive protection | A weekly archive waiting to be imported is deleted, like an imported one | CAUGHT, 7 failed | `rewritten, never deleted`. The pull: `nothing re-downloaded: imported weeks deleted, 09-22 kept`. The plan lists `delete` where `rewrite` was expected. |
| Pending-archive protection | A camp download no manifest records is deleted | CAUGHT | The waiting camp-download test: action `delete` / reason imported, where `rewrite` / waiting was expected |
| Dry run changes nothing | The plan writes the delivery record for a camp copy it will delete | CAUGHT | Dry-run test: the data-directory tree differs (the record appeared) |
| Dry run changes nothing | The plan carries out the purge it plans | CAUGHT, 15 failed | Dry-run test: the inbox state differs; every execution then meets files already gone |
| Suppressed-only rule | A withdrawal's disclosure scope ignored: every copy of a withdrawn file's bytes goes | CAUGHT, 6 failed | The plan wrongly lists the camp release. ZaLu's Round 3 is dropped, so the 09-22 import reports it `REMOVED`. The rewrite's entries differ. |
| Suppressed-only rule | Every piece of junk goes, not only junk shadowing a removed file | CAUGHT, 6 failed | Entry counts `9, 11` instead of `6, 14`; `.DS_Store` missing from the 09-22 manifest |
| Suppressed-only rule | A directory entry goes when *anything* under it goes, not everything | CAUGHT | The rewrite's entries differ: the wrapper directory entry is gone. This **survived at first**; see below. |
| Ordering | The inbox is purged before the suppression entries are appended | CAUGHT | `test_an_append_that_fails_leaves_the_inbox_untouched`: the inbox changed although the append failed |
| Delivery record before deletion | A camp copy is deleted without the record learning what it delivered | CAUGHT | `the removed camp file was requested again` (fetches `[512, 512]`) |
| Rewrite read back | A rewrite is put in place without being compared with the plan | CAUGHT | A rewriter that keeps everything: `DID NOT RAISE RemovalIncomplete` |
| Digest before acting | A file is acted on without checking it is the planned bytes | CAUGHT | A different archive under a planned name is deleted: `DID NOT RAISE` |
| The sync's run lock | The inbox is changed without the sync's run lock | CAUGHT | With a pull holding the lock: `DID NOT RAISE` |
| Unreadable zip | An unreadable zip is passed over and the run calls itself complete | CAUGHT | `DID NOT RAISE RemovalIncomplete` |
| No camp title in an error | An error names a camp download by its inbox name | CAUGHT | `'openev-512-TSF-Estuary_Solvency_Advocate.docx'` in the message |
| The inbox step itself | The executor skips the inbox (the removal as v1-e30-t07 left it) | CAUGHT, 13 failed | The 12-entry residue above, and the rest |

**One survived at first, and the test was too weak, not the code.** In the first run, "anything
under it" could not be told from "everything under it". The only directory entries in the test
archive were the team's, where everything goes, and ZaLu's, where nothing does. `935fd4f` gives the
archive its wrapper directory entry, which holds both, and the mutation is now caught. The smoke
check was also shown failing with the executor's inbox step removed: `assert (0, 0) == (3, 1)`.

**One check was deleted instead of tested.** The rewrite's read-back had a second check: re-run the
drop rule on the rewritten file. That is subsumed by the first, which compares the rewrite entry
by entry with the planned kept set, built by the same rule. So no mutation could tell it from its
absence, and it is removed (`a7e6b11`, working agreement 8).

## Files changed

`git diff --stat 5ee1e00..HEAD`, report aside: 15 files.

- **`debate_core.application.caselist`**:
  - `inbox_purge.py` (new): the rules, the plan, the purge, and the module docstring that justifies
    them.
  - `removal_plan.py`: a required `inbox`; `RemovalPlan.inbox`, `inbox_team_files_left` and
    `inbox_directory`; and which weeks and camp downloads this machine has imported.
  - `removal_service.py`: a required `inbox`; the inbox step between the local manifests and the
    records; inbox counts in the report, the log entry and the completed-but-unlogged message.
- **`debate_core.application`**: in `caselist_sync.py`, `OpenEvDeliveries.remember_if_unknown`,
  `openev_id_of_inbox_name`, and the delivery record's docstring (a removal writes it too).
- **`debate_core.application.ports`**:
  - `archive.py`: `InventoriedEntry` and the `ArchiveRewriter` port.
  - `suppression.py`: `InboxRewriteRecord`, and `inbox_files_deleted`, `inbox_files_rewritten`
    and `inbox_rewrites` on `RemovalLogEntry`.
- **`debate_core.integrations.local`**: in `archive_reader.py`, `inventory_zip`,
  `rewrite_zip_without` and `ZipArchiveRewriter`. They sit beside the reader and use its wrapper and
  junk rules, so a rewrite and an import read the same paths.
- **`debate_cli`** (Deviation 1): `container.py` (`caselist_inbox()`, the same directory the pull
  uses); `commands/caselist_remove.py` (the `DOWNLOAD INBOX` section, the `DONE` counts, the
  confirmation line, the JSON).
- **Tests**:
  - `test_removal_purges_inbox.py` (new, 17 tests).
  - `conftest.py`: `RemovalWorld.inbox`, and `removal_inbox` for a removal that cannot reach this
    inbox.
  - `test_sync_skips_suppressed_downloads.py`: its world gives the removal that separate inbox
    (Deviation 2).
  - `tests/smoke/test_caselist_remove_smoke.py`: one check.
- **Docs**: `docs/runbooks/caselist-removal.md` (steps 4–8, 10, recovery);
  `docs/runbooks/caselist-scheduled-sync.md` (one sentence).
- **Spec**: Goal set to `Succeeded`.

## Deviations from the spec

1. **Outside `constraints.packages`: `debate_cli` and tests.**
   - The removal has to be told where the inbox is, which only the composition root knows.
   - ac1's plan is rendered by the command.
   - `container.py` gains one method, and the pull now takes its inbox from the same method, so
     the two cannot point at different directories.
   - The CLI renders the new plan fields.
   - The smoke check is the only test of the real wiring.
2. **Finished tasks' behaviour and tests changed.**
   - **v1-e30-t07.** `RemovalPlanner` and `CaselistRemovalService` take a required `inbox`, with
     no default, as the suppression list is required everywhere. The executor has a new step.
     `RemovalLogEntry` gains three defaulted fields. I did not bump
     `SUPPRESSION_SCHEMA_VERSION`: its rule is "bumped only by a change an old reader breaks on",
     and no production code parses removal-log lines. Appends merge them as text, and only tests
     call `entries()`. A plan with inbox work is no longer `nothing_to_do`.
   - **v1-e34-t07.** A removal now also writes the delivery record, through
     `remember_if_unknown`. It adds what an id delivered and never replaces what an import wrote.
     So the record still holds no removal, and the "cannot disagree with the list" property
     stands.
   - **v1-e34-t07's tests** stage the inbox's state after a removal by hand: copy kept, or copy
     gone. Since a removal here now purges this inbox, their world gives the removal an inbox it
     cannot reach, the way a removal made on another machine leaves this one. Each test still
     tests the state it names. Without that, 10 of them failed on files the removal had already
     deleted.
3. **Two new ways a removal stops `INCOMPLETE`.** Both keep `COMPLETED` meaning what ac2 says, and
   both are finished by re-running.
   - **A zip in the inbox that cannot be opened.** Nothing can say whether it holds removed bytes.
     The pull cannot import it either, and its runbook already says to delete such a file by hand.
   - **A `caselist pull` holding the sync's lock.** The inbox is changed only under that lock.
4. **The purge works from the whole suppression list, not only this request's entries.** That is
   the manifests rewrite's own rule ("anything else the list already stops"), and it stays within
   the forbidden list. It is also what lets a removal made before this task be finished by running
   it again. The runbook says so, and a test does it.
5. **Junk and directory entries are dropped from a rewrite when they name only removed files.**
   - Junk follows the importer's own withholding rule (`withheld_skipped_paths`). A Word `~$` lock
     file stores the name of whoever had the document open, and an AppleDouble `._` file names the
     removed file. Leaving them would leave the team's name in an archive whose files were taken
     out. Their bytes are not on the list, though, so a reviewer could read the forbidden "deleting
     from the inbox anything the suppression list does not cover" as covering them. I read it as I
     believe t07 did for manifest rows: the list covers what its own rule withholds.
   - A directory entry goes only when every file under it goes.
6. **Outside `constraints.packages`: one docstring in `debate_core.domain`** (after PM review,
   authorised by the PM). `ArchiveSnapshot.archive_sha256` said "the downloaded archive file
   itself", which is false for a week imported from a rewritten inbox copy. See "Changes after PM
   review".

## Decisions and assumptions

- **Imported archive: deleted, not rewritten** (the call ADR-0017 left to this task).
  - It is dated on or before the newest imported snapshot, so `_decide_archive` calls it
    `ALREADY_IMPORTED` whether or not it is in the inbox. I checked the code and the pull test:
    `archive_fetches == []`.
  - Everything else it held is in the store with its manifest. That manifest's `archive_sha256`
    names the upstream archive, which the site keeps in its back-catalogue (ADR-0017).
  - A rewritten copy would be bytes nothing reads, whose digest matches neither that manifest nor
    upstream.
  - Recovering from a mistaken removal needs the original bytes. A rewrite would not hold them
    either, because the removed file is the one thing it leaves out. So deleting costs recovery
    nothing extra, and the runbook's recovery section now says to fetch the archive again.
- **Archive waiting to be imported: rewritten, never deleted.**
  - A weekly is "waiting" when this machine holds no manifest for its date. That is
    conservative: a week older than the newest that was never imported is also rewritten, never
    deleted.
  - A camp download is "waiting" when no local OpenEv manifest row came from its digest and the
    delivery record does not name it. A camp download whose every real file is removed is deleted
    in either state, which is the sync's own `skipped_as_removed` test. A rewritten camp release
    holding only junk would otherwise be imported on every run.
  - Any other zip, one the pull did not name, is rewritten, because nothing says it was imported.
- **What a rewritten archive's manifest records.** It records the rewritten file's digest, because
  that is what `archive_sha256` means: the file imported. For a camp download, the sync also
  matches the inbox copy against it, so recording the upstream digest would break the sync's own
  "already imported" check. Provenance stays traceable:
  - the removal log entry pairs each rewrite's digest before and after (`inbox_rewrites`, both
    copies, append-only);
  - the zip's own comment names the request and the digest it was rewritten from.
  A test checks all three against each other.
- **The OpenEv delivery record before a deletion.** I checked what happens when the copy is gone:
  `_delivery_in_inbox` is not reached, the record decides, and with no record entry the pull
  fetches the file again. A camp file imported before v1-e34-t07, or whose record was lost, is in
  exactly that state, so the record is written first. Without it the mutation brings back the
  download.
- **Execution.** The steps, in order:
  - suppression entries first, as t07 does;
  - then the bucket and this machine's store;
  - then the inbox, under the sync's run lock;
  - records last.

  For each inbox file:
  - its digest is checked against the plan;
  - a rewrite is staged under the same file name in a dot directory beside it, because the reader's
    wrapper rule reads the archive's name;
  - it is read back entry by entry against the original less the dropped entries, then renamed over
    the original.

  A run cut short leaves each file as it was or rewritten, never half-written.
- **Not checked:** `<inbox>/.partial/`, dot files and symlinks, as the sync skips them.
- **The `--team` gap, reported rather than widened.** A file the team discloses for the first time
  in a week not yet imported has bytes the store has never seen, so no selector resolves it. The
  plan says so (`NOTE`), and the runbook says to pull and then run the same removal again. A test
  checks that this works.
- **Errors never name a camp file's title.** They name a file by its weekly name (a caselist and a
  date) or `openev-<id>`. The plan, read in the operator's own terminal, shows full inbox names, as
  it already shows disclosure paths.
- **Measured on the real dev inbox, read-only.** `~/.debate-research/dev/inbox` holds 25 weekly zips,
  527 MB. The inbox scan with an empty list ran in 1.1 s over 2,685 entries and found 0 unreadable
  zips, so the inbox adds about a second to a real dry run. Prod has no inbox. Nothing was written.

## Operator follow-ups

None required: nothing here needs credentials, a device, or more than seconds. **Optional:** see the
new section on the real dev environment with a dry run that removes nothing (about 10 s). It needs
the everyday SSO session:

```zsh
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t09-removal-purges-inbox
DEBATE_ENV=dev uv run debate-research caselist remove --source 0000000000000000000000000000000000000000000000000000000000000000 \
    --request RM-2026-91 --reason POLICY
```

Success looks like:
- `DRY RUN: nothing was changed.`
- `DOWNLOAD INBOX (/Users/charlesclark/.debate-research/dev/inbox): nothing in it holds a removed
  file.`
- one suppression entry *planned*: it is a dry run, so it is not appended.

Do **not** add `--execute`: it would append a permanent entry.

## Follow-up work

1. **Policy text (Charlie).** `docs/policies/caselist-data-use.md`, "What removal does", does not
   mention the downloaded copies in the sync's inbox. The runbook now does. I did not edit an
   approved policy. A line such as "Deletes or rewrites the downloaded archives and camp files in
   the sync's inbox that hold it" would make it match.
2. **Downloaded material on disk that no removal reaches.** You asked where; this task does not
   widen to it. Existence checked read-only; file counts only:
   - `~/Documents/debate/2026-2027/LD Debate/Opencaselist/`: 2,407 files. The hand-downloaded
     hsld26 0901/0908/0915 archives, unpacked: the backfill's source and the parser evaluations'
     input.
   - `~/Documents/debate/2026-2027/Policy Debate/Camp Files/`: 106 files. The OpenEv camp files,
     downloaded by hand.
   - `~/Documents/debate/cardmirror-sample/`: 38 files, caselist and camp samples (v1-e31-t01/t02).
   - `~/Documents/debate/cardmirror-roundtrip-out/`: 39 files, v1-e31-t01's round-trip outputs
     derived from those samples.
   - `~/.debate-research/dev/backfill-imports/` holds four saved `caselist import --json` summaries:
     counts and digests, no member path and no material.

   The runbook now tells the operator to clean hand copies by hand. Whether these copies should be
   retired now that the store holds them, or become places the removal procedure covers, is the
   PM's and Charlie's call.
3. **`--team` resolving from an archive waiting in the inbox** (E30). The `NOTE` and re-running
   after a pull close the gap by procedure. The planner could instead resolve the team's paths in
   waiting archives directly. That needs those archives in the shared-holder check too, or a file
   the team shares with another team in the same waiting week would be removed for both.
4. **A camp release holding only junk is imported on every run** (E34, `v1-e34-t07` code, found
   while reading it, not caused here). Its delivery entry has no member digests. So
   `_judge_unrecorded` falls through to `already_in_inbox`, and nothing marks it imported. This task
   never creates one: it deletes rather than rewrites a camp download with no real files left.
5. **`ArchiveSnapshot.archive_sha256`'s description** says "the downloaded archive file itself". For
   a week imported from a rewritten inbox archive, it is the rewritten file, as Decisions explains.
   That is a domain-model docstring, outside this task's packages.

## Changes after PM review

Both requested changes are made, in `4a50811`, on top of `e2124cd`.

**1. A removal where there is no inbox.** Prod does not pull, so it has no inbox, and every takedown
runs there after dev. `_inbox_files` already returned nothing for a missing directory, and
`purge_inbox` returns before it takes the lock when nothing is planned, so no code path creates
the directory. But no test said so, and the CLI would have printed *nothing in it holds a removed
file*, which implies a directory was checked. Now:
- The plan records `inbox_exists`, and the `--json` plan carries it.
- The CLI prints, for example: `DOWNLOAD INBOX (/Users/charlesclark/.debate-research/prod/inbox):
  does not exist, so there is nothing to check or change (an environment that has never pulled
  has none).`
- `test_a_removal_where_there_is_no_inbox_completes_and_creates_none` plans and executes
  `--team … --include-shared` with no inbox directory. It checks that:
  - the plan says `inbox_exists` False, with no inbox files;
  - the run is `COMPLETED`, with 0 deleted and 0 rewritten;
  - there is still no inbox directory, no sync lock file and no delivery record.
- The smoke checks already run without an inbox. Two cheap assertions were added:
  - the human-readable dry run shows that line;
  - the executed removal reports `inbox_exists` false and creates no `<data_dir>/inbox`.

Shown failing for their reasons (`mutate_no_inbox.py` in the scratchpad, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` per run, files restored and checked against `HEAD`):

| Mutation | Result | Failing for its reason |
|---|---|---|
| The purge creates the inbox before finding nothing to do | CAUGHT, 2 failed | `nothing created where the inbox would be`; smoke `none created` |
| A missing inbox stops the run | CAUGHT, 4 failed | `RemovalIncomplete … (INBOX_FILE_UNREADABLE)`; smoke: the command fails |
| The plan says an inbox exists whether or not it does | CAUGHT, 3 failed | `(True, (), …) == (False, (), …)` |
| The CLI says nothing in a missing inbox holds a removed file | CAUGHT | the smoke check's expected line is missing |

**2. `ArchiveSnapshot.archive_sha256`** (Deviation 6). The class docstring and the field's
description now say it is the digest of the archive file imported. That is the archive as
downloaded, except for a week imported from a copy a removal rewrote in the inbox. Then it is the
rewritten file's digest, and the removal log entry's `inbox_rewrites` pairs it with the digest of
the archive as downloaded. Nothing pins the old wording: a search of code, fixtures and docs finds
it only in this report.

**Follow-ups, as the PM decided them.**
- 1, the policy line: lands as version 1.4 in a separate PM PR, merged after this one.
- 2, the hand copies: go to Charlie as a decision.
- 3, the `--team` gap: accepted as a procedural gap, not filed.
- 4, the junk-only camp release: folded into `v1-e34-t08` as ac5.
- 5: done above.
- The inbox measurement and the imported-week argument are the basis of `v1-e34-t11`, inbox
  retention.

**Checks on the final tree (`4a50811`, report commit aside).**

| Command | Result |
|---|---|
| `uv run pytest -m "not slow and not live" packages tests` | `3629 passed, 1 skipped in 37.45s` (the skip is the pre-existing parser eval) |
| `uv run ruff check .` / `uv run ruff format --check .` | `All checks passed!` / `458 files already formatted` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 11 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 298 files, 38 epics, 240 tasks, 20 releases` |

Not pushed. Next, for the operator: `scripts/task sync v1-e30-t09-removal-purges-inbox`, then
`scripts/task pr v1-e30-t09-removal-purges-inbox`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-01

**Notes:**

Accepted, phase `Succeeded`, with two small additions before the pull request opens (the last two
items below). I read `container.caselist_inbox` and `inbox_purge._inbox_files` on the branch for the
one case the report does not mention: a removal run where there is no inbox.

**The delete-or-rewrite call is right, and argued the way I want these calls argued.** An imported
week is `ALREADY_IMPORTED` whether or not its zip is in the inbox, which you checked in the code and
in a pull test rather than assuming. Its other contents are in the store under a manifest that
names the upstream archive. And a rewrite would not help recovery, because the removed file is the
one thing it leaves out. Each step closes off the objection to the next. The pending case gets the
opposite answer for the opposite reason, which is what the kickoff asked for.

**Recording the rewritten digest, with the before/after pair in the log and the zip's comment, is
the honest answer to provenance.** `archive_sha256` means "the file imported", and keeping the
sync's own already-imported check working matters more than a digest that names bytes nobody
holds. Three records that a test checks against each other is better than one that has to be
trusted.

**Writing the delivery record before deleting a camp copy is the find of the task.** A camp file
imported before v1-e34-t07, or whose record was lost, would have been fetched again the moment its
inbox copy went. You established that by reading `_delivery_in_inbox`'s path, not by testing the
happy case, and a mutation proves it.

**The first-run survivor was the test's weakness, not the code's, and you said so.** "Anything under
it" and "everything under it" were indistinguishable because the only directories in the fixture
were all-or-nothing. Giving the archive a mixed wrapper directory is the right fix, and so is
deleting the subsumed read-back check rather than inventing a test for it.

**Deviations 1 to 5 are accepted.** The composition root is the only place that knows where the
inbox is, and the pull now takes its inbox from the same method, so the two cannot drift. A
removal on this machine purging this inbox is exactly why v1-e34-t07's tests needed an inbox the
removal cannot reach. Both new INCOMPLETE conditions keep COMPLETED meaning what ac2 says. Purging
from the whole list is the manifest rewrite's own rule and lets an earlier removal be finished by
re-running. Dropping junk and directory entries that name only removed files follows
`withheld_skipped_paths`, and a `~$` file holding a person's name is exactly what a takedown must
not leave behind.

**Follow-ups, PM decisions.** 1: the policy line is added as version 1.4; it tightens, so under the
policy's change control it takes effect on merge. 2: the hand copies outside the store are put to
Charlie as a decision, with the parser evaluation's dependence on them noted. 3: accepted as a
procedural gap; the plan's `NOTE` and re-running after a pull close it, and it is not filed. 4: the
junk-only camp release is folded into `v1-e34-t08`, which owns the same `_judge_unrecorded` path.
5: below. Separately, your measurement (25 weekly zips, 527 MB) and your argument for deleting an
imported week are together the case for a retention rule; that is filed as `v1-e34-t11`, built on
your reasoning.

**Change 1: test the removal with no inbox.** Prod has no inbox, and every takedown runs against
prod after dev. `_inbox_files` returns nothing when the directory does not exist, which is right,
but no test says so. Add one that plans and executes a removal whose inbox directory does not exist:
the plan says there is no inbox, the run is COMPLETED rather than INCOMPLETE, and nothing is created
on disk where the inbox would be. Check the CLI's `DOWNLOAD INBOX` line reads sensibly for that case.

**Change 2: correct `ArchiveSnapshot.archive_sha256`'s description** (your Follow-up 5). It says
"the downloaded archive file itself", which is now false for a week imported from a rewritten
archive. One docstring in `debate_core.domain`; I am authorising the edit, so list it as a deviation.

# Session report: v1-e34-t11-inbox-retention

| | |
|---|---|
| Task | `v1-e34-t11-inbox-retention` — Imported downloads leave the inbox |
| Spec | [`plan_specs/v1/e34-caselist-sync/t11-inbox-retention.yaml`](../../plan_specs/v1/e34-caselist-sync/t11-inbox-retention.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t11-inbox-retention` |
| Session status | COMPLETE |

## Summary

`caselist pull` now has a **retention** stage. It runs after the report stage and inside the run
lock, and it removes an inbox file only when all three of these hold:

- **Imported:** a manifest on this machine came from these exact bytes.
- **Confirmed:** the bucket holds that snapshot in sync, as this run checked it. For a week this
  run published, that is the report stage's comparison. For a week an earlier run imported, the
  retention stage runs the same comparison afresh.
- **Recorded:** for a camp download, the OpenEv delivery record has an entry for its id.

Everything else stays, and the summary names it with the reason. It runs on every real run,
including one that downloaded nothing, so the first run after this ships clears the backlog. A dry
run removes nothing and lists what a real run would remove. Nothing is kept longer, the newest week
included. The run log's record, and the bucket's copy of it, carry the stage's sentence: every
file, by `<caselist> <date>` or by count and sha256 prefix, and the bytes freed.

ac1 was committed red first. Eleven guard mutants, plus one combined pair, were each caught on the
final tree, every run with a fresh Hypothesis database. The phase is `Succeeded`. The two runs
against your real inbox are operator follow-ups for after the merge.

**Read first:**
- Decisions 1 and 2. I applied your two "what qualifies" rules more strictly than written: a
  weekly's *bytes* must be the ones its manifest names, and a camp download needs a manifest row
  from its bytes as well as the record. The second is what the retry hold actually is. Your camp
  rule alone would delete a camp file waiting for its retry, and the mutation table shows it.
- Mutation findings: one check was deleted because mutation could not tell it from its absence,
  and one guard is caught only by the reason a kept file is given.
- Follow-up 1: a camp file's name already reaches the JSON run summary, through the existing
  `openev_selections[].inbox_name`. I found it while checking your "unless t03 already allows
  their file names" condition. I did not change it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `retention` — Remove imported, confirmed downloads from the inbox | Done | The stage, its summary and its record sentence are in `caselist_sync.py` and `sync_runs.py`. The dry-run listing and caption are in `caselist_pull.py`. 17 tests in `test_inbox_retention.py` and 3 in the CLI tests. The runbook section is "The download inbox". |

## Acceptance criteria

All results are from the final tree, rebased onto `origin/dev` by `scripts/task sync`
(code at `5171d5d`; `c71425c` is a runbook sentence), unless a row says otherwise.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — After a run that imports and publishes a week, that week's zip is gone and the summary names it; a following run downloads nothing for it. Shown failing first | PASS | Red first: `e2ceeda` (`62a3767` before the rebase), output below. Green: `test_retention_removes_the_weeks_a_run_imported_and_confirmed_and_names_them`. 09-01 and 09-08 are fetched, imported, published and confirmed, and both zips are gone. `inbox_retention.removed` is `["testcl26 2026-09-01", "testcl26 2026-09-08"]`, and `bytes_freed` equals the two fixture files' sizes. The record built by `record_for_summary` carries the same retention sentence. The next run fetches nothing: both weeks are `already_imported`, and the run is `nothing_new`. Also `test_retention_clears_a_backlog_on_a_run_that_downloads_nothing`: three weeks earlier builds left behind are removed by a run that downloads, imports and publishes nothing. |
| **ac2** — A week downloaded but not imported or not published stays and is finished by the next run; a dry run removes nothing and lists what a run would | PASS | **Import failed:** 09-08's zip is refused. It stays as `not_imported`, the next run imports it from the inbox with no fetch, then removes it. **Publish pending** (expired SSO): both weeks stay as `not_confirmed`. After login, the next run drains the publish, its report confirms them, and they go. **Publish succeeded but the report found drift:** kept. **An earlier run's week whose manifest has since left the bucket:** retention's own comparison keeps it, and after `caselist publish` the next run removes it. **Dry run:** the inbox's bytes and mtimes are unchanged and nothing is fetched. `would_remove` lists the two backlog weeks with `bytes_would_free`, and `would_remove_once_imported` lists 09-15. The real run that follows removes exactly those three. |
| **ac3** — A camp download is removed only once the delivery record holds its digests, and the next pull does not fetch it again | PASS | A single document (512) and a release zip (901) are imported, recorded, published and confirmed. Both are removed, named `2 camp download(s), sha256 2b912c191a8a, sha256 accbabd08dee`, and no camp title appears in the summary or the record. The next pull fetches neither. With the record deleted, both stay as `no_delivery_record`, and the next pull fetches neither. |
| **ac4** — Each guard (import, publish confirmation, delivery record, run lock, dry run) mutated and caught, fresh Hypothesis database each run; the runbook says what the inbox holds and when things leave it | PASS | 12 of 12 caught on `5171d5d` (table below). One check that survived was deleted (working agreement 8). The runbook section is [The download inbox](../runbooks/caselist-scheduled-sync.md#the-download-inbox). |
| Node `retention`: `uv run pytest packages/debate_core/tests/application/caselist -k retention` | PASS | `17 passed in 6.88s` |
| CI's Python selection: `uv run pytest -m "not slow and not live" packages tests` | PASS | `4300 passed, 1 skipped in 74.01s`. The skip is the existing parser eval waiting on human corrections. Measured at 74 s, so run in the session. |
| `uv run ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | PASS | `512 files already formatted` / `All checks passed!` / `0 errors, 0 warnings, 0 informations` / `Contracts: 11 kept, 0 broken.` |
| `uv run scripts/check_links.py` / `uv run python scripts/docs_index.py --check-descriptions` | PASS | `OK: 1259 relative links and anchors in 171 Markdown files` / `All 30 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | PASS | `OK: 309 files, 38 epics, 251 tasks, 20 releases`; `--require-succeeded v1-e34-t11-inbox-retention` → `Succeeded` |

### ac1, shown failing first

`e2ceeda`, against the unchanged sync. Command:
`uv run pytest packages/debate_core/tests/application/caselist/test_inbox_retention.py -n0 -p no:cacheprovider --no-cov`

```
E       AssertionError: an imported, confirmed week stayed in the inbox
E       assert {'testcl26-we...26-09-08.zip'} == set()
E         Extra items in the left set:
E         'testcl26-weekly-2026-09-01.zip'
E         'testcl26-weekly-2026-09-08.zip'
============================== 1 failed in 0.37s ===============================
```

The run before that assertion succeeded, with the report stage `completed`. The zips stayed only
because nothing removes them.

## Checks shown failing for their reason

The harness is `mutate.py` in the session scratchpad, not the repository. It refuses to start
unless the target is committed. For each mutant it:
- makes exact text replacements in `caselist_sync.py`;
- runs `test_inbox_retention.py` with `-n0 -p no:cacheprovider --no-cov --tb=line` and a **new,
  empty `HYPOTHESIS_STORAGE_DIRECTORY` per run** (working agreement 8). None of these tests uses
  Hypothesis, so there are no generation statistics to report;
- restores the file from a saved copy and checks it byte for byte against `HEAD`.

Three batches ran on `5171d5d`, taking 27.6 s, 11.7 s and 3.7 s. No run errored before running.
"Deleted" in the last column means the test saw the file gone that it expected kept.

| Guard | Mutant | Result | Failing for its reason |
|---|---|---|---|
| Import guard | M1: a weekly's manifest bytes not compared (a manifest for its week suffices) | CAUGHT | Deleted: a weekly whose week was imported from another copy |
| Import guard | M2: a weekly counts as imported with no manifest at all | CAUGHT, 2 failed | Deleted: the other-copy weekly. In the failed-import test, **by its reason alone** (`not_confirmed` where `not_imported` is expected), because confirmation also keeps it; see below |
| Import guard | M3: a camp download counts as imported with no manifest row from its bytes | CAUGHT | Deleted: the camp file waiting for its retry |
| Retry hold | R1: a camp download is taken as imported into any release this machine holds, not the one a row from its bytes is in | CAUGHT | Deleted: the camp file fetched again after an `unsuppress`, whose import failed, while its release stays published and the record holds it |
| Publish confirmation | P1: none; imported is enough | CAUGHT, 4 failed | Deleted: pending-publish weeks, report-drift weeks, the earlier week the bucket lost, and the copy `--publish-pending` leaves |
| Publish confirmation | P2: an earlier run's snapshot trusted when nothing is owed for it, not compared | CAUGHT, 2 failed | Deleted: the week whose manifest left the bucket after an earlier run published it |
| Publish confirmation | P3: the publish stage's success taken for the report stage's comparison | CAUGHT | Deleted: weeks the publish uploaded and the comparison found missing |
| Delivery record | D1: the record not consulted | CAUGHT, 2 failed | Deleted: camp downloads with no record entry, in the record test and in the removal-then-retention test |
| Run lock | L1: retention runs after the run released the lock | CAUGHT | `lock free` where `lock held` is expected, observed at each inbox `unlink` |
| Dry run | DR1: the dry run removes what it judged removable | CAUGHT | `the dry run changed the inbox` |
| Import and confirmation together | M2+P1 | CAUGHT, 6 failed | Deleted: the failed-import week (`removed == [09-01, 09-08]`) and five others |

**The retry hold is not a separate check, and why.** `v1-e34-t06`'s retry imports exactly the inbox
files that no manifest came from, so the import guard keeps exactly the retry set. A separate hold
based on the run's own selection would be redundant on every reachable state, and blind on a run
whose listing was rate-limited. So there is none. The "retry hold" mutants are the ways the import
guard could stop holding that set (R1, M3).

- **A weekly in the retry set is held twice.** It has no manifest, so the bucket cannot confirm its
  snapshot either. M2 alone therefore changes only the reason the file is kept. M2+P1 deletes it.
- **A camp file is held once.** Its release can be confirmed because of other camp files, so the
  import guard alone holds it (M3, R1).

**One check was deleted instead of tested.** I had a guard that never confirms a file with no
snapshot (an empty set is a subset of anything). Run alone as mutant V, it **survived** (17
passed). No reachable state gives a removable file an empty snapshot set. Its only effect was to
make M3 change a label instead of a deletion (M3+V: caught by a deletion). Deleted in `5171d5d`, as
working agreement 8 says, and the invariant is written on `_JudgedLocally.snapshots` instead.

## Files changed

`git diff --stat 88d92e2..HEAD`, report aside: 8 files.

- **`debate_core.application`, `caselist_sync.py`:**
  - the module docstring's new section, "What leaves the inbox";
  - `SyncStage.RETENTION`, `RetentionDecision`, `InboxFileKind`, `InboxFileVerdict` and
    `InboxRetention` (its JSON and its sentence);
  - `RunSummary.inbox_retention`;
  - the stage, with `_judge_inbox`, `_judge_locally`, `_confirm_in_bucket`,
    `_imported_archive_digest` and `_openev_releases_by_download`;
  - the report stage now remembers which snapshots it confirmed;
  - `--publish-pending` records retention as skipped;
  - `weekly_archive_of_inbox_name` and `inbox_files`, moved here from `inbox_purge.py`;
  - `_recorded_openev_at`, so a release manifest can be read by its key.
- **`debate_core.application.caselist`, `inbox_purge.py`:** uses those two helpers. The removal and
  retention now classify the inbox by one rule. Behaviour is unchanged:
  `pytest packages/debate_core/tests/application/caselist -k "inbox and not retention"` (t09's and
  t07's inbox tests) gives `27 passed`.
- **`debate_core.application`, `sync_runs.py`:** `redact()` takes a length limit. The retention
  stage's reason is kept up to 8,000 characters instead of 500, so a backlog's names are not
  truncated. Nothing else in the record changed (Decision 5).
- **`debate_cli.commands`, `caselist_pull.py`:** the caption's inbox sentence for a run and for a
  dry run. The table's `retention` row already carries the full listing.
- **Tests:** `packages/debate_core/tests/application/caselist/test_inbox_retention.py` (new, 17
  tests). `packages/debate_cli/tests/commands/test_caselist_pull.py` (3 tests: the no-bucket skip
  through the command, and both captions).
- **Docs:** `docs/runbooks/caselist-scheduled-sync.md`. The new section "The download inbox" covers
  what it holds, the three conditions, why nothing is kept longer, the dry run, naming, a reason
  table, and removal against retention. There is also a summary-field row, and two corrected
  sentences: "A download failed", and Step 1's "listing calls only". `v1-e34-t10`'s edits to the
  same file came in with `scripts/task sync`, without conflicts, and both are present.
- **Spec:** `constraints.packages` amended with the comment "added on the PM's instruction,
  2026-10-08"; Goal `Succeeded`.

## Deviations from the spec

1. **Packages beyond `debate_core.application` and `docs`:** `debate_cli.commands`, both packages'
   tests and `docs/runbooks`, as you authorised. The spec says so.
2. **No smoke check added.** `tests/smoke/` was not in the authorisation. The existing pull smoke
   checks run with a bucket, so they exercise retention, and all of them pass. See Follow-up 3.
3. **The backfill runbook was read, not edited.** `docs/runbooks/caselist-backfill.md` is not on
   `dev`; it lives on `task/v1-e30-t06-initial-backfill`. I read its "Resuming and recovering"
   table from there. Its hand-import row still works with retention, because a file not imported is
   never removed. Its "A re-run will **not** import it" has been out of date since `v1-e34-t06`
   (Follow-up 2).

## Decisions and assumptions

1. **A weekly goes only when its manifest names its bytes.** Your rule was "its snapshot's manifest
   is in the local store". I also require that manifest's `archive_sha256` to be the zip's digest.
   An inbox zip with other bytes than the ones imported (for example, the week was imported by
   hand from another copy) was never imported, and the forbidden list says not to delete a download
   that is not yet imported. Such a file stays as `not_imported`, and the runbook says it can be
   deleted by hand. I expect none in your inbox: t06 found every inbox archive had a manifest, and
   the backfill imports from the inbox copies. If you would rather a week's manifest be enough,
   it is one line, and M1's test pins the difference.
2. **A camp download needs more than the record.** It also needs a release manifest row from its
   bytes, and that release confirmed in the bucket, because the forbidden list's import and publish
   conditions apply to it too. The record alone is not proof of an import *now*. After a removal and
   an `unsuppress`, the record still holds the file's digests, while the file sits in the inbox
   waiting for a retried import. That is R1's test, and the record rule alone would delete that
   file. The record check itself is "an entry for this id", because the next pull looks the record
   up by id (`_judge_unrecorded`). Comparing the record's digests too was a check no test could
   reach, so I dropped it.
3. **Confirmation runs per caselist.** A fresh check compares the one snapshot asked about, or the
   whole caselist when several are asked about. The weeklies are cumulative and share most sources,
   and the comparison heads each source once, so the backlog run's cost is about one comparison of
   each caselist, not one per week. Snapshots this run's report already confirmed are not checked
   twice. A bucket that cannot be read (an expired session, a denial) confirms nothing, and the
   files wait.
4. **Nothing is kept longer.** This is your decision, and the justification is in the runbook and
   in the module docstring.
5. **The run record's schema is unchanged.** The names travel in the `retention` stage's reason,
   which the record already carries as a free-form `StageEntry`. That is because `SyncRunRecord`
   forbids extra fields, and the backfill still runs an installed build against the same
   `~/.debate-research/dev` run log; a new field would make that build skip every new record (the
   reason `v1-e34-t06` gave). Only the reason's length limit changed, for this stage. The JSON
   summary gains `inbox_retention`, an additive key, without a version bump (`v1-e34-t07`'s rule).
6. **Naming.** Weeklies are named `<caselist> <date>`. Camp downloads, hand-placed files and
   unreadable files are named by count and `sha256 <first 12 hex>`. t03 does not allow camp file
   names: its record carries no selection, and the sync's own docstring forbids a camp title.
   Retention never names the inbox path.
7. **A dry run reads the bucket**, read-only, to list what would go. Without a session it lists
   every imported file as `not_confirmed`.
8. **`--publish-pending` removes nothing** ("complete the publishes, and nothing else"). The next
   pull removes what it confirmed, and a test shows it.
9. **Removal against retention:**
   - `caselist remove` deletes or rewrites inbox files that hold removed bytes, imported or not;
   - retention deletes imported, confirmed files, whatever they hold;
   - both take the run lock, and retention judges the inbox as a removal left it.

   `test_a_removal_then_retention_each_removes_only_its_own_files` runs a `--source` removal of a
   file found only in 09-15: the removal reports 1 inbox file deleted. The next pull fetches
   nothing and removes 09-01 and 09-08. It keeps the camp release, which was imported before the
   delivery record existed.
10. **Your real inbox and the agent were not touched.** Every test uses a temporary data folder and
    moto.

## Operator follow-ups

Two optional runs after this merges into `dev`. Run them only on a day with download cap to spare,
and **never between Tuesday evening and Wednesday 06:00**: that is when the week's archives appear
and the scheduled run is due. The real pull may also fetch new weeklies the backfill is planning
around, so check the dry run's `select` row (`N of 5 bulk download(s) spent … M left`) first.

**1. Dry run: list what would be removed** (expected runtime about 1–3 min: listing calls, hashing
about 1 GB of zips, and one bucket comparison per caselist)

Where: the main checkout, once it is on `dev` and includes this task's merge (if
`git log --oneline -1 --grep v1-e34-t11` prints nothing, pull `dev` first).

```zsh
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git log --oneline -1 --grep v1-e34-t11
uv sync --all-packages
aws sso login --profile debate-dev-evidence
du -sh ~/.debate-research/dev/inbox
DEBATE_ENV=dev uv run debate-research --json caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --dry-run | jq '.data.inbox_retention | {would_remove: [.would_remove[].name], bytes_would_free, kept, would_remove_once_imported}'
```

Success looks like:
- the branch prints `dev`;
- `would_remove` lists the imported weeklies by `<caselist> <date>`, with `bytes_would_free` close
  to the `du` figure;
- `kept` is empty, or names only what is still waiting to be imported or published.

Paste the jq output back. A long `not_confirmed` list means the bucket check could not run, so look
at the SSO login first.

**2. A real pull that clears the backlog** (expected runtime about 2–6 min, longer if it downloads
new weeklies)

Same place and session, after follow-up 1:

```zsh
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
du -sh ~/.debate-research/dev/inbox
DEBATE_ENV=dev uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26
du -sh ~/.debate-research/dev/inbox
DEBATE_ENV=dev uv run debate-research --json caselist runs --last 1 --remote | jq '.data.runs[0].stages[] | select(.stage == "retention")'
```

Success looks like:
- exit `0`, with `retention | completed | N file(s) removed, B bytes freed: …` in the table and
  `Inbox: N file(s) removed (B bytes freed)` in the caption;
- the second `du` far below the first, about 1 GB down to whatever was kept;
- the bucket's copy of the record shows the same retention sentence.

Paste both `du` lines and the caption back.

## Follow-up work

1. **A camp file's name reaches the JSON run summary** (E34, `v1-e34-t02`/`t07` code, found here
   rather than caused here). `OpenEvSelection.as_json()` carries `inbox_name`, which is
   `openev-<id>-<file name>`, for example `openev-512-TSF-Estuary_Solvency_Advocate.docx`. It
   reaches `<data_dir>/caselist-sync-runs/*.json`, `caselist pull --json` and the launchd stdout
   log. The sync's docstring says a summary never carries a camp file's title, and the runbook says
   the log can be pasted into an issue as it is. The run record and the bucket do not carry it.
   Naming the selection by id alone would fix it, if you read rule 4 as covering camp titles.
2. **The backfill runbook's recovery table** (`v1-e30-t06`, on its own branch). The "exited 1 at
   import" row says a re-run will not import the archive, which has been untrue since `v1-e34-t06`.
   A line could also say that imported, published weeks now leave the inbox at the end of each
   pull.
3. **A smoke assertion** (`tests/smoke/test_caselist_pull.py`, if you authorise it): after the
   confirmed pull, the inbox holds no weekly and the `retention` stage is `completed`. That would
   cover the real composition root.
4. **Camp downloads imported before `v1-e34-t07`** have no record entry, so they stay forever,
   named as `no_delivery_record`. Your dev inbox held no camp downloads when `v1-e30-t09` measured
   it. If that changes, retention could write the entry from the inbox copy first, as a removal
   does (`remember_if_unknown`).

## Changes after PM review

**Follow-up 3, the smoke assertion** (authorised; `tests/smoke` is now in `constraints.packages`).
After the confirmed pull in `test_a_weekly_pull_downloads_imports_publishes_and_then_finds_nothing_new`,
through the installed command, respx and moto, it asserts that:
- no `*-weekly-*.zip` is left in the inbox;
- the `retention` stage is `completed`;
- `inbox_retention.removed`'s weekly entries are exactly `testcl26 2026-09-01`, `testcl26 2026-09-08`
  and `testcl26 2026-09-15`, written by hand from the fixture's three weeks.

`uv run pytest tests/smoke/test_caselist_pull.py` gives `6 passed in 7.82s`.

**Shown failing with the stage switched off.** The call to `_retention_stage` was removed from
`CaselistSyncService.run`, and the test was run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`
(0 entries at start), then the file was restored and checked equal to `HEAD`:

```
E   AssertionError: a confirmed week stayed
E   assert ['testcl26-we...26-09-15.zip'] == []
E     Left contains 3 more items, first extra item: 'testcl26-weekly-2026-09-01.zip'
1 failed in 4.95s
```

Committed with the PM's edits: this section's PM review, the spec's package list, and
`t12-summary-names-no-camp-file.yaml` with its `epic.yaml` entry.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-08

**Notes:**

Accepted, phase `Succeeded`, with one small addition before the PR (below).

* **Decisions 1 and 2, the stricter rules: accepted. They are better than what I specified.**
  * A weekly goes only when its manifest names its bytes.
  * A camp download needs a manifest row from its bytes, and its release confirmed, as well as the
    delivery record.

  R1 shows my record-only rule would have deleted a camp file waiting for its retry after an
  `unsuppress`.
* **The retry hold as the import guard, not a separate check: accepted.** The explanation of why
  M2 alone changes only the reason (a weekly is held twice) is exactly what the mutation table
  should say.
* **Deleting check V, which mutation could not tell from its absence:** that is working agreement 8
  applied properly.
* **Decision 5 (the run record schema unchanged so the installed build still reads the run log):
  accepted.** Retention reaches the agent with its next reinstall, after the 2026-10-14 run.
* **Decisions 3, 6, 7, 8 and 9: accepted.**

**Before the PR: Follow-up work 3, the smoke assertion, is authorised** (`tests/smoke` added to
`constraints.packages` in this branch). After the confirmed pull in
`test_a_weekly_pull_downloads_imports_publishes_and_then_finds_nothing_new`, assert that:
* the inbox holds no weekly;
* the `retention` stage is `completed`;
* the summary's `inbox_retention.removed` names the weeks.

Show it failing with the stage switched off.

**Follow-up work:**

1. **A camp file's name in the JSON summary:** filed as **v1-e34-t12-summary-names-no-camp-file**
   (in this branch, with its epic entry). Thank you for checking the condition rather than assuming
   it.
2. **The backfill runbook's recovery table:** the PM fixes it on the `v1-e30-t06` branch when that
   task closes.
3. **The smoke assertion:** done here, as above.
4. **Camp downloads from before t07, with no record entry:** waits for the operator's dry run. If
   its `kept` list shows any as `no_delivery_record`, the PM decides then.

**Operator follow-ups:** Charlie will run them together with the backfill's last pull (two hspf26
weeks waiting on the cap) on Thursday 2026-10-08 after 21:00 Central, from the main checkout once
this has merged. One pull then fetches the last weeks and clears the inbox.

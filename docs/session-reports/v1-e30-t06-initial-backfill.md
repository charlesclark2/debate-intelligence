# Session report: v1-e30-t06-initial-backfill

| | |
|---|---|
| Task | `v1-e30-t06-initial-backfill` — Initial caselist and camp-file backfill |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t06-initial-backfill` |
| Session status | PARTIAL: runbook and template done; backfill day 1 of 6 run by the operator on 2026-09-26; days 2–6, the spot check and the prod publish remain |


## Summary

This session wrote the backfill runbook (`docs/runbooks/caselist-backfill.md`) and the summary
(`docs/data/caselist-backfill-2026-09.md`). The runbook is built around `caselist pull`, which
shipped after the spec was written. `pull` does every download and handles the 5-per-day cap;
`caselist import` / `import-openev` handle only files already on the Mac. That brings the plan to
**29 downloads over six days**, three fewer than the spec's arithmetic, because the three HS LD
weeklies on hand are imported instead of downloaded again. The session itself ran no pull, import
or publish. Every download, import and publish below was the operator's, and the session read the
results back with read-only commands.

**Where the backfill stands (day 1 of 6, run 2026-09-26).** HS LD goes first, at the operator's
request, because the first tournament is 3 October. It was complete through 09-22 after day 1, and
after day 2 it is **complete through 09-29**, the newest listing: 13 weeklies, 4,456 stored members,
3,612 distinct files (an 18.9% saving), 487 MB. Day 2 ran on Monday 28 September at 11:44 pm
Central (04:44 UTC on the 29th) instead of Sunday. It fetched 5 weeklies and published all 619
new files, with none pending. The first Policy
weekly and the 105 Policy camp files are in. Dev `caselist status` agreed on all 14 snapshots,
and the dev bucket holds the 09-15 manifest the node criterion names. The Policy
and PF weeklies continue. After run 5 (Thu 1 October, 8:17 pm Central) **Policy is complete
through 09-29** (11 weeklies, 2,350 stored members, 1,843 distinct files, a 21.6% saving), and
**4 PF downloads are left**, one run on the evening of Friday 2 October. The site's cap
turned out to be per date rather than a rolling 24 hours; a run 20½ hours after the previous day's
five was granted all five.

**Three things for the PM, in order:**

1. **Deviation 1 is resolved** by PM ruling #93: the backfill is the weekly series alone, and the
   withdrawal figure is deferred to `v1-e34-t04`. The runbook and summary now say so. Nothing in
   the daily plan changed.
2. **The camp files all imported as camp `UNKNOWN`** (Follow-up work). The bytes and manifest are
   correct; the importer reads the camp from the wrong end of the filename.
3. **A weekly import's NEW is not "new evidence"** (Follow-up work). It is measured against the
   week before only: day 1's three August weeks reported 25 NEW but stored 16. The summary reports
   files first seen instead.

**The Goal stays `InProgress`.** Days 2–6, the final dev check, the coach's spot check and the prod
publish are still to run.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `runbook-and-template` — Backfill runbook and summary template | Done | Both files, plus the five hsld26 weeks already held, read from their manifests and pre-filled. The runbook's reporting commands were tested against the synthetic fixture archives in a scratch data directory. |
| `local-import` — Operator-run local import | In progress (operator) | Day 1 run 2026-09-26: HS LD complete through 09-22 (the three on-hand weeklies imported in order 0901 → 0908 → 0915), Policy camp files imported, first Policy weekly pulled. Policy and PF weeklies continue on days 2–6. |
| `dev-publish` — Operator-run publish to dev and drift check | In progress (operator) | `pull` publishes as it goes; the hand imports were published on day 1 (steps 4 and 6: 2,097 HS LD sources and 102 camp files uploaded, 0 failed). Day 1 `status`: 14 of 14 snapshots agree. The final check follows day 6. |
| `dev-spot-check` — Coach spot check in dev | Not started (operator) | Runbook, *Spot check in dev*. |
| `prod-publish` — Operator-run publish to prod | Not started (operator) | Runbook, *Publish the same store to prod*. |

## Acceptance criteria

The session ran its checks from the task worktree on 2026-09-26. Operator results are from the
day 1 run the same afternoon (21:34–21:40 UTC), pasted into the session.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — the runbook gives the exact operator commands (import order 0901 → 0908 → 0915, OpenEv import, dev publish, status, prod publish with `--confirm-prod`) and expected durations | PASS, with Deviation 2 | Every item is in `docs/runbooks/caselist-backfill.md`. The 0901 → 0908 → 0915 imports are day 1 step 3; `pull` fetches 08-11 to 08-25 before them, because the importer enforces order (Deviation 2). The durations are estimates scaled from the measured 34 s, five-weekly run of 2026-09-24 and marked as estimates. |
| **ac2** — per-snapshot member and classification counts, dedupe rate, PDF/.doc and unparsed counts, bytes stored; path-level REMOVED labelled as such; withdrawals against the full archive reported separately; the measured 11% stated | NOT RUN (partly recorded) | Recorded from real runs so far: 13 per-snapshot rows (hsld26 07-07 to 09-22, hspolicy26 07-07) with every required column, the OpenEv row, the hsld26 dedupe rate (3,629 → 3,036, 16.3%), and bytes on disk after day 1 (460,988 KiB). The path-level column is headed **Paths no longer present** and never called removals (685 for 09-15, matching `v1-e30-t03`; 1,462 for 09-22). The 11% measurement is stated. Still to come: Policy/PF rows (days 2–6) and final bytes. The withdrawal figure is out of scope under the amended ac2 (ruling #93) and is named in the summary as deferred to `v1-e34-t04`. |
| **ac3** — hsld26 09-01/09-08/09-15 and OpenEv manifests in the dev bucket; dev `caselist status` shows no drift | NOT RUN (evidence in hand, final check after day 6) | Day 1, 2026-09-26, operator: `caselist status` → exit 0, **Every snapshot agrees**, 14 snapshots including hsld26 09-01 (59/59), 09-08 (678/678), 09-15 (1,487/1,487) and openev 2026-policy (102/102), 0 missing, 0 mismatches. Left NOT RUN until the whole backfill is published and checked again, which is when the summary records its status line. |
| **ac4** — coach spot-checked at least 20 disclosures in dev | NOT RUN | Coach. |
| **ac5** — the same manifests in prod; prod `caselist status` shows no drift, with the date | NOT RUN | Operator, after ac3 and ac4. |
| Node: Backfill runbook exists (`contentMatch: --confirm-prod`) | PASS | `grep -c -- "--confirm-prod" docs/runbooks/caselist-backfill.md` → `4` |
| Node: Summary template exists (`contentMatch: Dedupe rate`) | PASS | `grep -c "Dedupe rate" docs/data/caselist-backfill-2026-09.md` → `1` |
| Node: Local import counts recorded (`contentMatch: 2026-09-15`) | PASS (the match); node still in progress | The template left out `2026-09-15` until the import ran, so the match could not pass early. After day 1, step 3 (2026-09-26), the 09-15 row is recorded from the operator's import: `grep -c 2026-09-15 docs/data/caselist-backfill-2026-09.md` → `3`. The node's Policy/PF weeklies are still to come. `dev status: in sync` and `prod status: in sync` are still deliberately absent (both `0`). |
| Node: Dev publish recorded (`dev status: in sync`) | NOT RUN | Operator. |
| Node: Latest LD manifest in the dev bucket (`store ls manifests/hsld26/2026-09-15.jsonl`) | PASS | `DEBATE_ENV=dev uv run debate-research store ls manifests/hsld26/2026-09-15.jsonl` → exit 0, `1 object(s), 930.7 KB`, run by the session on 2026-09-26 after day 1. The bucket's `manifests/` now holds 12 hsld26, 1 hspolicy26 and 1 openev manifest. The baseline before day 1 was 5 hsld26 manifests only, all in sync. |
| Node: Coach accepts the dev spot check | NOT RUN | Coach. |
| Node: Prod publish recorded (`prod status: in sync`) | NOT RUN | Operator. |
| Node: Latest LD manifest in the prod bucket | NOT RUN | Operator. |
| Node: Session report committed | PASS | This file. |

**What the session measured, and how.** These were read-only commands over files already on the
operator's machine, each finishing in seconds (working agreements §2):

* `ls ~/.debate-research/dev/objects/manifests/hsld26/` → five manifests, 07-07 to 08-04. That is
  the store the spec describes, and it fixes which weeklies are still wanted.
* The trailing `summary` row and format counts of those five manifests, through the runbook's
  `snapshot_rows` and `dedupe_row`: 255 members, 242 distinct, a 5.1% saving, 49,107,328 bytes.
  These match run `20260924T042300Z` (`files_imported 255`, `files_duplicate 12`,
  `blobs_stored 242`).
* The three 2026-09-24 run summaries: `openev_seen 498`, all `no_event_configured`, 0 downloaded.
  This is why `pull` fetches no camp files while `caselist.openev_event` is unset.
* File counts in the on-hand folders: 64, 745 and 1,597 files in the three HS LD weeklies, and
  105 `.docx` plus one `.DS_Store` in the camp files. These match the spec. No Policy or PF
  archives are on hand.

## Files changed

* `docs/runbooks/caselist-backfill.md` (new): the operator's runbook. After day 1 it also has
  `first_seen_rows`, and a recovery row for a failed import inside `pull`.
* `docs/data/caselist-backfill-2026-09.md` (new): the summary. The five held weeks were filled in
  by the session; day 1's results (8 more snapshots, the camp files, two pull runs, the dev publish
  and a mid-backfill status check) from the operator's run.
* `docs/README.md`: an index line for each (Deviation 3).
* `docs/session-reports/v1-e30-t06-initial-backfill.md`: this report.
* `plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml`: unchanged. The Goal stays
  `InProgress`.

## Deviations from the spec

1. **The complete archive cannot be imported. Resolved by PM ruling #93 (2026-09-26), option (b):
   the backfill is the weekly series alone.** The spec says "the run downloads `<caselist>-all-<date>.zip` first and
   imports it as the corpus" (ADR-0017 decision 1), and ac2 asks for withdrawals measured "against
   the complete archive". With the code on `dev`:
   * a snapshot is a (caselist, date) pair, and the complete archive has the same date as that
     week's weekly, so both would claim `manifests/<slug>/<date>.jsonl`;
   * the importer compares each archive with the latest snapshot strictly before it
     (`CaselistImportService._previous_snapshot`). A weekly imported after a complete archive
     would therefore report nearly every file in the corpus as `REMOVED`;
   * `pull` skips every weekly dated on or before the newest manifest held (`_decide_archive`). A
     complete archive imported first would stop the back-catalogue being fetched at all;
   * `pull` never fetches a complete archive (`FULL_ARCHIVE_NOT_PULLED_WEEKLY`). Importing one "as
     its own snapshot" and counting withdrawals is `v1-e34-t04` ac4, and `v1-e34-t04` depends on
     this task.

   I raised this with Charlie. Of the three options offered (download and hold the archives, and
   measure withdrawals read-only by hashing; weeklies only, with the complete archive moved to
   t04; stop and let the PM decide), he chose **stop and let the PM decide**. The runbook
   therefore plans only the weeklies, says not to download a `-all-` archive or pass one to
   `caselist import`, and explains why. The weekly plan does not depend on the ruling: under every
   option, the weeklies go in oldest first. Options for the PM: (a) move ac4 of `v1-e34-t04`
   (full archive as its own snapshot kind, plus the withdrawal count) ahead of this task, and add
   a complete-archive stage here; (b) take the complete archive and the withdrawal half of ac2 out
   of this task and let `v1-e34-t04` own both; (c) amend ADR-0017 decision 1, which has the order
   the wrong way round for the importer as it stands.

   **Ruling (#93, 2026-09-26):** option (b), together with (c). ADR-0017 gained a revision saying
   the backfill is built from the weekly series alone, the spec's description and ac2 now name the
   withdrawal figure as deferred to `v1-e34-t04`, and `v1-e34-t04` gained ac0 (a snapshot
   namespace of its own). The runbook's complete-archive section and the summary's withdrawal
   section were updated to match. The daily plan is unchanged, because it already covered only the
   weeklies. Deviation 1 no longer blocks anything.

2. **ac1 and the `local-import` node describe a manual sequence; the runbook uses `pull`.** The
   spec was written before `v1-e34-t02` shipped. The runbook uses `pull` for every download,
   because it is the only path that budgets the cap, records runs and publishes as it goes. The
   manual commands are kept for what is already on disk: `caselist import` for the three HS LD
   weeklies, and `import-openev` for the camp files. Two consequences the spec did not foresee:
   * **0901 → 0908 → 0915 cannot be the first imports.** The store already holds 07-07 to 08-04,
     and the importer refuses an archive older than one already imported. `pull` skips anything
     on or before the newest manifest. So 08-11, 08-18 and 08-25 must be pulled first, with the
     allowance lowered to 3 for that one run (`DEBATE_CASELIST__BULK_DOWNLOADS_PER_DAY=3`) so it
     stops before the weeks already on disk. Only then do the on-hand weeks go in, and 09-22 is
     pulled after them.
   * **The manual imports need their own `caselist publish`**, because `pull` publishes only what
     it imported itself.

3. **`docs/README.md` is outside `constraints.packages`.** It gains one index line per new file,
   which working agreements §3 requires of every new document.

4. **The five held weeks' counts come from their manifests, not from the run summaries.** The
   spec says they come from the run summaries under `caselist-sync-runs/`. Those carry run totals
   only, not per-snapshot classifications. Each manifest's trailing `summary` row carries the
   per-snapshot numbers, is deterministic, and was written by the same run. The run summary's
   totals serve as the cross-check, and they agree.

5. **The spot check samples local manifests, not copies downloaded from the bucket.** The node
   says "sample from the dev manifests". The runbook samples the local manifests after
   `caselist status` has confirmed they match the bucket's checksum for checksum. This avoids
   downloading files carrying personal data for no gain.

## Decisions and assumptions

* **HS LD first** (Charlie's choice, because of the 3 October tournament). All of LD is in on
  day 1, 09-29 on day 3, Policy by day 5, and PF on day 6. The runbook says how to put PF ahead
  of Policy if its recent weeks matter more for 3 October.
* **The on-hand HS LD weeklies are taken to be the site's 09-01, 09-08 and 09-15 weeklies.** Their
  dates and file counts match the spec and ADR-0017's listing. Comparing their bytes with the
  site's would cost three downloads, and those are what the plan saves.
* **The day-by-day table assumes day 1 is Sunday 27 September.** Day 1 was actually Saturday 26
  September, which moves every row a day earlier: the 09-29 weeklies join on day 4, and PF should
  finish on Thursday 1 October. The total of 29 downloads is unchanged.
* **Durations are estimates**, from the measured 2026-09-24 run (34 s for five weeklies, 255
  files, with the publish) and the local synthetic imports (about 0.7 s per archive). The operator
  records the real ones.
* **The template leaves out the strings the operator-run criteria match on**, so those criteria
  cannot pass before the runs they are meant to evidence.

## Operator follow-ups

1. ~~Before day 1~~ and ~~day 1, steps 0–7~~: **done 2026-09-26.** All results match the plan.
2. **Days 2–6, a few minutes each.** One run a day, each on a new UTC date and no earlier in the
   day than the last (day 2: Sunday 27 September after about 21:40 UTC):

   ```bash
   export DEBATE_ENV=dev
   uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26
   uv run debate-research caselist runs --last 1
   ```

   Day 2 expects 3 Policy + 2 PF. Paste back the run table after each.
3. **After day 6:** the dry run that wants nothing, `snapshot_rows`, `first_seen_rows` and
   `dedupe_row` for all three caselists, `du -sk ~/.debate-research/dev/blobs`, and
   `caselist status`. Record `dev status: in sync`.
4. **Coach spot check:** 20 disclosures, tallies only.
5. **Prod publish:** runbook section, with `DEBATE_STORAGE__DATA_DIR` naming the dev store and
   `--confirm-prod`. Record `prod status: in sync` and the date.
6. **Set the Goal to `Succeeded`** only once every criterion has passed: `uv run scripts/task_helper.py set-phase v1-e30-t06-initial-backfill Succeeded`.

## Follow-up work

* **E34 (`v1-e34-t02` code): the download ledger is keyed by the UTC date, but its docstring says
  local time.** `DownloadLedger` says "in local time", but `CaselistSyncService` defaults its
  clock to `datetime.now(UTC)` and the CLI container does not pass one. An evening run in the US
  lands on the next day's ledger. The runbook works around it; the code or the docstring should
  change.
* **E34 (`v1-e34-t02` code): an archive whose import failed is never retried.** It stays in the
  inbox, and the next run marks it `already_in_inbox`, which is neither fetched nor imported:
  `_import_stage` imports only what the same run downloaded. `caselist-scheduled-sync.md` says to
  "run the same command again", which does not recover it. This runbook gives the manual
  recovery. The fix belongs in `pull`, or at least in that runbook.
* **`v1-e34-t05-enable-schedule`: the schedule and the backfilled store must be the same store.**
  The scheduled-sync runbook installs the agent with `--env prod`, whose profile reads
  `~/.debate-research/prod`. The backfill builds `~/.debate-research/dev`, the one store `v1-e30-t05`
  and this spec settled on. A prod-profile schedule would start an empty second store and
  re-download the whole back-catalogue into it. t05 needs to pass `DEBATE_STORAGE__DATA_DIR` or
  settle the split.
* **E34: `pull`'s OpenEv selection does not recognise camp files imported by hand.** It matches on
  the inbox name (`openev-<id>-…`), not on sha256. Setting `caselist.openev_event` would therefore
  re-download all 498 listed files, which would go into the manifest as `DUPLICATE` rows beside the
  105 imported here.
* **Filed by the PM as `v1-e30-t08-import-metadata-defects` (#102, 2026-09-26)**, which owns the
  next two items, including the metadata re-import of the 105 camp files from the local store:
* **E30 (`v1-e30-t03` code or docs): a weekly import's NEW means "not in the previous week", not
  "never stored".** `CaselistImportService` does not pass `find_existing` to the pipeline (the
  OpenEv importer does), so a file stored in an earlier, non-adjacent week is NEW again. The
  module docstring says NEW is "bytes not seen before, under this path or any other", which is
  true only against the week before. Measured on backfill day 1: 08-11 to 08-25 reported 25 NEW
  and stored 16 new blobs. The summary therefore adds a *First seen here* table, from the
  runbook's `first_seen_rows`, and says NEW is not new evidence. Adjacent-window comparison is what
  ADR-0016 and the epic asked for, so the fix may only be the docstring. Either way, a later
  report that sums NEW across weeks would overstate new evidence.
* **E30 (`v1-e30-t04` OpenEv importer): no camp is recognised in the real camp files.** On
  2026-09-26 all 105 on-hand Policy camp files imported with camp `UNKNOWN` (`unknown_camps 105`).
  The alias table has the camps they name. The files carry the camp at the end of the filename,
  after the title and before the year, with the lab's initials after it, in folders named for
  argument type. `camp_metadata` reads the camp only from the folder or the start of the filename.
  The bytes and manifest are correct; the camp and title fields are not. The fix belongs in the
  importer, followed by a re-import of the release. How a re-import rewrites rows already in the
  release manifest needs checking first. No filename is quoted here, per policy rule 5.
* **`v1-e34-t04`**: see Deviation 1.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

## Closing session, 2026-10-08/09

This section is the closing session's: the operator's work was finished, and what remained was the
record and the branch. Everything above it is unchanged. The criteria table below supersedes the
earlier one, which shows the state after backfill day 1.

## Summary

**The backfill is complete, and the Goal is `Succeeded`.** Every weekly the site lists for
`hsld26`, `hspolicy26` and `hspf26`, from 07-07 to 10-06, is imported: 14, 13 and 13 snapshots,
plus the one OpenEv release (`2026-policy`), 41 snapshots in all. It was published to dev and
checked in sync there. The coach spot-checked 20 disclosures (20 correct). It was then published to
prod from the same local store: 11,126 sources, 0 failed, all 41 snapshots in sync.

| Caselist | Weeklies | Stored members | Distinct files | Saving | Prod sources |
|---|---|---|---|---|---|
| hsld26 | 14 | 5,647 | 4,461 | 21.0% | 4,461 |
| hspolicy26 | 13 | 3,465 | 2,657 | 23.3% | 2,657 |
| hspf26 | 13 | 5,347 | 3,906 | 26.9% | 3,906 |
| openev `2026-policy` | 1 | — | 102 | — | 102 |

The distinct-file counts, computed by this session from the dev store, equal the prod upload
counts the PM recorded, caselist for caselist. The local store holds 3,083,588 KiB, and the inbox
is at 0 B after the final run's retention.

This session also did four things:

* Rebased the branch onto `origin/dev`, which was 211 commits ahead (`scripts/task sync`). The
  only conflict was `docs/README.md`, resolved to dev's generated version.
* Brought the two new documents up to the rules that landed meanwhile: the docs-index line, and no
  `#` comments in shell blocks.
* Recorded the missing rows and runs, using read-only commands against the operator's dev store.
* Corrected the runbook where `v1-e34-t06` and `v1-e34-t11` had made it stale.

## Acceptance criteria (final)

Session commands ran from the task worktree, after the final pull (2026-10-09 UTC). Rows marked
*PM* are facts the PM supplied, recorded as given.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — the runbook gives the exact operator commands (import order 0901 → 0908 → 0915, OpenEv import, dev publish, status, prod publish with `--confirm-prod`) and expected durations | PASS, with Deviation 2 | `docs/runbooks/caselist-backfill.md` has every item. The hand imports are day 1 step 3, after the pulls the importer's ordering forced first (Deviation 2). Day 1 was run from it as written. The runbook now also says what `v1-e34-t06` and `v1-e34-t11` changed. |
| **ac2** — per-snapshot counts, dedupe rate, PDF/.doc and unparsed counts, bytes stored; path-level REMOVED labelled; withdrawal figure named as deferred to `v1-e34-t04`; the measured 11% stated (as amended by #93) | PASS | `docs/data/caselist-backfill-2026-09.md` has all 40 weekly rows, each with every column, from `snapshot_rows` against `~/.debate-research/dev`, plus the OpenEv row. It gives per-caselist dedupe rates (21.0% / 23.3% / 26.9%) from `dedupe_row`, and bytes on disk of 3,083,588 KiB from `du -sk`. REMOVED is headed **Paths no longer present**, and the withdrawal section says "Deferred to `v1-e34-t04-full-archive-refresh`; … The blank here is not a zero." The 11% measurement is stated. The rows cross-check against every run summary's members, duplicates and blobs. |
| **ac3** — hsld26 09-01/09-08/09-15 and OpenEv manifests in the dev bucket; dev `caselist status` reports no drift | PASS | `DEBATE_ENV=dev uv run debate-research --json caselist status --caselist <slug>`, for each of hsld26, hspolicy26, hspf26 and openev → exit 0, `in_sync: true`. Per caselist: 14 snapshots 5,247/5,247, 13 3,156/3,156, 13 4,564/4,564, 1 102/102; 0 missing; 0 mismatches. `manifest_present: true` for hsld26 2026-09-01, 2026-09-08, 2026-09-15 and openev 2026-policy. *PM*: the dry run `20261009T023844Z` after the final pull wanted nothing, and all four caselists were in sync. Recorded as `dev status: in sync`. |
| **ac4** — the coach spot-checked at least 20 random disclosures in dev, with the results in the summary | PASS (*PM*) | 2026-10-08: 20 compared, 20 correct, 0 flagged, 0 wrong. Recorded in the summary's spot-check table with the coach's acceptance. |
| **ac5** — the same manifests in prod, prod `caselist status` reports no drift, with the date of the prod publish | PASS (*PM*) | Published 2026-10-09 UTC (the evening of 8 October Central), from the dev data directory with `--confirm-prod`: hsld26 14 / 4,461, hspolicy26 13 / 2,657, hspf26 13 / 3,906, openev 2026-policy 1 / 102; 11,126 sources, 0 failed, 0 blocked. The dry runs planned the same counts. Prod `caselist status` → all 41 in sync ("Every snapshot agrees"). Recorded as `prod status: in sync`. |
| Node: Backfill runbook exists (`--confirm-prod`) | PASS | `grep -c -- "--confirm-prod" docs/runbooks/caselist-backfill.md` → 4 |
| Node: Summary template exists (`Dedupe rate`) | PASS | `grep -c "Dedupe rate" docs/data/caselist-backfill-2026-09.md` → 1 |
| Node: Local import counts recorded (`2026-09-15`) | PASS | The 09-15 row is recorded from the operator's hand import of 2026-09-26. |
| Node: Dev publish recorded (`dev status: in sync`) | PASS | Present in the summary, written after the final check above. |
| Node: Latest LD manifest in the dev bucket (`store ls manifests/hsld26/2026-09-15.jsonl`) | PASS | Run by the session on 2026-09-26 → exit 0, 930.7 KB (earlier table). This session did not run `store ls`, which was not among the reads it was cleared for. `caselist status` shows the manifest still present (ac3). |
| Node: Coach accepts the dev spot check | PASS (*PM*) | ac4. |
| Node: Prod publish recorded (`prod status: in sync`) | PASS | Present in the summary. |
| Node: Latest LD manifest in the prod bucket (`DEBATE_ENV=prod … store ls manifests/hsld26/2026-09-15.jsonl`) | PASS (*PM*) | Returned 930.7 KB. The session ran no prod command. |
| Node: Session report committed | PASS | This file. |

Checks this session ran, all from the task worktree:

| Check | Result |
|---|---|
| `uv run scripts/validate_specs.py` | `OK: 310 files, 38 epics, 252 tasks, 20 releases` |
| `uv run scripts/validate_specs.py --require-succeeded v1-e30-t06-initial-backfill` | `Succeeded` |
| `uv run scripts/check_links.py` | `OK: 1292 relative links and anchors in 183 Markdown files` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 32 indexed documents under docs/ have a description`. It failed for both new documents before their first lines were added. |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 202 shell code blocks in 109 Markdown files (1 session reports changed since origin/dev)`. Before the fix it reported 13 comments, all in the runbook. |
| Package tests | None run: the branch changes only documents and the spec's phase (`git diff origin/dev --stat`: four files, no code), so no package test exercises this task's work. |

## What this session changed

* **Sync.** `scripts/task sync v1-e30-t06-initial-backfill` stopped on `docs/README.md`. The
  branch's first commit had added two index lines by hand, and the index is now generated
  (`v1-e01-t16`). Resolved to dev's version, and `docs/README.md` is otherwise untouched. The
  branch is 0 behind `origin/dev` and has not been pushed.
* **Docs-index lines.** `docs/runbooks/caselist-backfill.md` and
  `docs/data/caselist-backfill-2026-09.md` now start with `<!-- docs-index: … -->`, worded as their
  old index lines were. The session report needs none: `docs/session-reports/` is indexed by its
  README.
* **Command blocks.** Every `#` comment in the runbook's shell blocks moved into the prose. The
  count-function block is split: one block defines `snapshot_rows`, `dedupe_row` and
  `first_seen_rows`, described in a list before it, and a second block runs them. The functions
  used for this session's counts were extracted from those two blocks as committed, so the
  documented commands are the ones that produced the numbers.
* **Recovery table.** The row "A re-run will **not** import it" was stale since `v1-e34-t06`. It
  now says the next run imports the archive from the inbox (`already_in_inbox`) without a download,
  oldest first, stopping at the first gap. A new row, "The inbox is empty after a run", explains
  `v1-e34-t11`'s retention: when it removes a download, what it keeps and why, and why a removed
  weekly is never fetched again. The opening passage that said `pull` never imports an inbox
  archive now says what was true when the backfill ran and what is true now.
* **Ledger notes.** The runbook's UTC-date warnings describe how the backfill ran. Each is
  followed by what is true now: `pull`'s ledger has counted starts over a rolling 24 hours since
  `v1-e34-t06`. The runs show it: `20261008T030658Z`, 80 minutes after five downloads, was granted
  none.
* **Summary.** Added the rows for hsld26 10-06, hspolicy26 10-06 and hspf26 09-08 to 10-06, both
  per-snapshot and first-seen. Added the four pull runs from 2 October, the final dedupe rates,
  bytes on disk, the final dev status table, the spot check, and the prod publish. Moved back a
  sentence ("The withdrawal figure is deferred…") that an earlier edit had attached to the
  cap-measurement paragraph.

## Deviations (closing session)

* **`store ls` against dev was not rerun.** The node's evidence is the 2026-09-26 run, plus
  `caselist status` now. The brief cleared `caselist runs`, `caselist status` and the count
  functions, and `store ls` was not among them.
* **The completed criteria table is here, not in place.** The brief asked for the table to be
  completed and for nothing above the earlier PM review to be edited. The earlier table stays as
  the record of day 1.

## Decisions and assumptions (closing session)

* **The two retention figures reconcile exactly**, and the summary says so. The pre-pull dry run
  listed 35 files, 2,439,954,953 bytes. The run removed 37 files, 3,527,154,833 bytes. The
  difference, 1,087,199,880 bytes, is the combined size of the two archives that run fetched (the
  run summary's `inbox_retention`).
* **Times are given in both UTC and Central.** Run ids and the ledger are UTC; the operator's
  evenings are Central. The final pull ran on 8 October Central and 9 October UTC, and both
  dates are stated wherever it is cited.
* **One unplanned run is listed.** `20261002T012228Z`, five minutes after run 5 and for hsld26
  only, is in the pull-runs table. It found nothing to fetch and changed nothing.

## Operator follow-ups (closing session)

None. The backfill, the spot check and the prod publish are done. Pushing the branch and opening
the pull request are the operator's, after the PM's review (`scripts/task pr`).

## Follow-up work (closing session)

No new items. Those listed earlier stand: the importer metadata defects are filed as
`v1-e30-t08`, and the full archive is `v1-e34-t04`. The two `pull` defects listed earlier, the
UTC-date ledger and the failed import that was never retried, were fixed by `v1-e34-t06`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-09

**Notes:**

Accepted. Merge with `scripts/task pr`; the Goal is `Succeeded`. This review covers the whole task, including the first session's work, whose own review was never filled in and stays as written.

- **Checked against the branch:** clean, four files changed and no code, 1 commit behind `origin/dev` (the PM's close-out PR, which touched `e30`'s `epic.yaml`). Run `scripts/task sync` again before the PR.
  - Both new documents carry their docs-index line.
  - The command-block check passes; it found 13 comments in the runbook before the fix.
  - Spec validation and the links check pass.
- **ac1–ac5 pass**, with the evidence in the final table.
  - The distinct-file counts the session computed from the dev store (4,461 / 2,657 / 3,906) equal the prod upload counts caselist for caselist. That is an independent cross-check, not a copy.
  - The retention reconciliation is exact: 37 removed against 35 planned, and the 1,087,199,880-byte difference is the two archives that run fetched.
- **Deviations accepted:**
  - The first session's Deviations 1–5. Deviation 1 was resolved by ruling #93; 2 and 4 were forced by `pull` and the importer as they stood.
  - The closing session's two:
    - `store ls` against dev was not rerun, which is right, because it wasn't cleared. `caselist status` shows the manifest present.
    - The final table is appended, not edited in place, which follows v1-e01-t18's rule.
- **The runbook corrections are right.**
  - The recovery row now describes v1-e34-t06's import from the inbox, and the new row describes v1-e34-t11's retention.
  - The ledger notes say what was true during the backfill and what is true now (rolling 24 hours since v1-e34-t06).
- **Follow-up work: nothing new to file.**
  - The camp `UNKNOWN` defect and NEW's meaning are `v1-e30-t08`.
  - The complete archive and withdrawals are `v1-e34-t04`.
  - The ledger and import-retry defects were fixed by `v1-e34-t06`.
  - The store-split concern for the agent was settled when v1-e34-t05/t10 installed it against the dev store.

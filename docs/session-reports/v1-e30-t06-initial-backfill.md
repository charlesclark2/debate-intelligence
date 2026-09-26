# Session report: v1-e30-t06-initial-backfill

| | |
|---|---|
| Task | `v1-e30-t06-initial-backfill` — Initial caselist and camp-file backfill |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t06-initial-backfill` |
| Session status | PARTIAL: session deliverables done; the backfill is operator-run, and the complete-archive step is blocked on a PM decision |


## Summary

This session wrote the backfill runbook (`docs/runbooks/caselist-backfill.md`) and the summary
template (`docs/data/caselist-backfill-2026-09.md`). It ran no pull, import or publish, and made
no call to the live site. The runbook is built around `caselist pull`, which now exists: `pull`
does every download and handles the 5-per-day cap, and `caselist import` / `import-openev` handle
only what is already on the Mac. That brings the plan to **29 downloads over six days**, three
fewer than the spec's arithmetic, because the three HS LD weeklies on hand are imported rather than
downloaded again. HS LD goes first and finishes on day 1, at the operator's request, because the
first tournament is 3 October.

**The PM should look first at the first Deviation.** The complete archive, which ADR-0017 says the
backfill starts from, cannot be imported correctly by any code that exists today. At Charlie's
direction the runbook stops at that point and leaves the decision to the PM.

**The Goal stays `InProgress`.** Every criterion except the runbook, the template and this report
needs the operator's runs. The ac2 withdrawal figure also needs the PM's ruling.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `runbook-and-template` — Backfill runbook and summary template | Done | Both files, plus the five hsld26 weeks already held, read from their manifests and pre-filled. The runbook's reporting commands were tested against the synthetic fixture archives in a scratch data directory. |
| `local-import` — Operator-run local import | Not started (operator) | Runbook day 1, steps 2–6, then days 2–6. |
| `dev-publish` — Operator-run publish to dev and drift check | Not started (operator) | `pull` publishes as it goes; runbook steps 4, 6 and 7 cover the manual imports and `status`. |
| `dev-spot-check` — Coach spot check in dev | Not started (operator) | Runbook, *Spot check in dev*. |
| `prod-publish` — Operator-run publish to prod | Not started (operator) | Runbook, *Publish the same store to prod*. |

## Acceptance criteria

The session ran its checks from the task worktree on 2026-09-26.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — the runbook gives the exact operator commands (import order 0901 → 0908 → 0915, OpenEv import, dev publish, status, prod publish with `--confirm-prod`) and expected durations | PASS, with Deviation 2 | Every item is in `docs/runbooks/caselist-backfill.md`. The 0901 → 0908 → 0915 imports are day 1 step 3; `pull` fetches 08-11 to 08-25 before them, because the importer enforces order (Deviation 2). The durations are estimates scaled from the measured 34 s, five-weekly run of 2026-09-24 and marked as estimates. |
| **ac2** — per-snapshot member and classification counts, dedupe rate, PDF/.doc and unparsed counts, bytes stored; path-level REMOVED labelled as such; withdrawals against the full archive reported separately; the measured 11% stated | NOT RUN | Needs the operator's imports. The template has every column, heads the path-level REMOVED column **Paths no longer present**, and states the 11% measurement. Five of the per-snapshot rows are already filled in from a run that happened (below). The withdrawal figure is also blocked on Deviation 1. |
| **ac3** — hsld26 09-01/09-08/09-15 and OpenEv manifests in the dev bucket; dev `caselist status` shows no drift | NOT RUN | Operator. |
| **ac4** — coach spot-checked at least 20 disclosures in dev | NOT RUN | Coach. |
| **ac5** — the same manifests in prod; prod `caselist status` shows no drift, with the date | NOT RUN | Operator, after ac3 and ac4. |
| Node: Backfill runbook exists (`contentMatch: --confirm-prod`) | PASS | `grep -c -- "--confirm-prod" docs/runbooks/caselist-backfill.md` → `4` |
| Node: Summary template exists (`contentMatch: Dedupe rate`) | PASS | `grep -c "Dedupe rate" docs/data/caselist-backfill-2026-09.md` → `1` |
| Node: Local import counts recorded (`contentMatch: 2026-09-15`) | NOT RUN | The template deliberately does **not** contain `2026-09-15`: `grep -c` → `0`. With it, this criterion would pass before any import happened. The same goes for `dev status: in sync` and `prod status: in sync` (both `0`). |
| Node: Dev publish recorded (`dev status: in sync`) | NOT RUN | Operator. |
| Node: Latest LD manifest in the dev bucket (`store ls manifests/hsld26/2026-09-15.jsonl`) | NOT RUN | Not imported yet, and the dev SSO session had expired: a read-only `caselist status --caselist hsld26` returned `STORE_CREDENTIALS_EXPIRED`. |
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

* `docs/runbooks/caselist-backfill.md` (new): the operator's runbook.
* `docs/data/caselist-backfill-2026-09.md` (new): the summary template, with the five held
  weeks filled in.
* `docs/README.md`: an index line for each (Deviation 3).
* `docs/session-reports/v1-e30-t06-initial-backfill.md`: this report.
* `plan_specs/v1/e30-caselist-ingestion/t06-initial-backfill.yaml`: unchanged. The Goal stays
  `InProgress`.

## Deviations from the spec

1. **The complete archive cannot be imported, so the "complete archive first" step is blocked.
   PM decision needed.** The spec says "the run downloads `<caselist>-all-<date>.zip` first and
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
   the wrong way round for the importer as it stands. ac2 is FAIL as written until one of these
   is chosen.

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
* **The day-by-day table assumes day 1 is Sunday 27 September** and the 09-29 weeklies are listed
  by day 3's run. Either shift only moves the table; the total of 29 downloads is the same.
* **Durations are estimates**, from the measured 2026-09-24 run (34 s for five weeklies, 255
  files, with the publish) and the local synthetic imports (about 0.7 s per archive). The operator
  records the real ones.
* **The template leaves out the strings the operator-run criteria match on**, so those criteria
  cannot pass before the runs they are meant to evidence.

## Operator follow-ups

1. **Before day 1:** read the runbook's *Before day 1* section and run its checks. That section
   covers the dev SSO login, `caselist auth status --check`, no `DEBATE_CASELIST__*` variables
   set, and the launchd agent not installed.
2. **Day 1, about 45 minutes, in one sitting that does not cross midnight UTC:** runbook day 1,
   steps 1–7. Paste back the dry-run counts, the output of `snapshot_rows hsld26`, the
   `import-openev` JSON counts, and `caselist status`.
3. **Days 2–6, a few minutes each:** one `caselist pull --caselist hsld26 --caselist hspolicy26
   --caselist hspf26` a day. Paste back `caselist runs --last 1` after each.
4. **After day 6:** the dry run that wants nothing, `snapshot_rows` and `dedupe_row` for all three
   caselists, `du -sk ~/.debate-research/dev/blobs`, and `caselist status`. Record
   `dev status: in sync`.
5. **Coach spot check:** 20 disclosures, tallies only.
6. **Prod publish:** runbook section, with `DEBATE_STORAGE__DATA_DIR` naming the dev store and
   `--confirm-prod`. Record `prod status: in sync` and the date.
7. **Set the Goal to `Succeeded`** only once every criterion above has passed and the PM has
   ruled on Deviation 1: `uv run scripts/task_helper.py set-phase v1-e30-t06-initial-backfill
   Succeeded`.

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
* **`v1-e34-t04`**: see Deviation 1.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

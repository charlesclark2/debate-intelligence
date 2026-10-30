# Session report: v1-e30-t28-annual-purge-runbook

| | |
|---|---|
| Task | `v1-e30-t28-annual-purge-runbook` — The annual purge, as one runbook |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t28-annual-purge-runbook.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t28-annual-purge-runbook.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t28-annual-purge-runbook` |
| Session status | COMPLETE |

## Summary

[docs/runbooks/annual-purge.md](../runbooks/annual-purge.md) is the annual purge for today's setup:
the cloud run in bucket mode, both buckets under the takedown credential, this Mac's data directory
and any working copy restored here. It opens with a coverage table, one row per row of the policy's
retention table plus the inbox, the local classifier and the cassettes. Then it gives one window per
environment. In it, `purge_guard` refuses a Wednesday, a held run lock, a `DEBATE_` override and a
running pull or import before every block that reaches a bucket. The steps are: leftover working
copies; the school views (moved from the removal runbook); an inventory that judges every caselist in
the bucket, the run-state bundle, this Mac's stores and the inbox by `caselist.backfile_caselists` and
its dates; a caselist to purge; the pilot's index and P4; expired noncurrent versions; built files;
the September backfile review; and the record. Policy 1.17 keeps every aged-out season from 2021-22
on, so in an ordinary year the runbook deletes only school views and superseded index versions. Where
no command exists (a whole caselist or camp year before 2021-22, this Mac's own index builds, one
caselist's cassettes), the runbook says so and stops for the PM; six gaps are under Follow-up work.
Each Python listing in the runbook runs in `tests/docs` on synthetic stores, and nine mutants were
each caught. **Read first:** question 3 below. The dev data directory's local landscape bundle holds
two files that neither list names, so step 2's dry run, and any removal that touches that caselist,
stops on this Mac today.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `purge-runbook` (Annual purge runbook) | Done | Runbook written; removal runbook section replaced by a pointer; `tests/docs/test_annual_purge_runbook.py` added (20 tests) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the runbook covers every store in the retention table, locally and in each bucket, each step a dry run, the delete and a check; the removal runbook's school-view section moves into it and links to it; check_command_blocks and check_links pass | PASS | Coverage: `test_the_runbook_covers_every_row_of_the_policys_retention_table` maps all 15 policy rows to runbook rows and fails on a new one (shown by mutant). Each deleting step (school views, P4, the local classifier and cassettes) has a dry run, a delete block of its own and a re-run as the check. Where no command exists, the step lists counts and names the gap, as the spec's description allows. Move: `test_the_removal_runbook_points_here_and_keeps_no_purge_code` passes. `uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 543 shell code blocks in 193 Markdown files`; `uv run scripts/check_links.py` → `OK: 2838 relative links and anchors in 428 Markdown files` |
| Node `purge-runbook`: Docs tests pass (`uv run pytest tests/docs`) | PASS | `uv run pytest tests/docs` → `120 passed` (see Checks run) |

## Checks run

| Command | Result |
|---|---|
| `uv run pytest tests/docs` | `120 passed` |
| `.venv/bin/python -m pytest tests/docs/test_annual_purge_runbook.py -p no:randomly -n 0` | `20 passed in 1.08s` |
| Parse of each of the runbook's 15 `bash` blocks, `zsh -n` and `bash -n` | zsh: 15 of 15 parse. bash: 14 of 15; the school-view delete block uses zsh's `(N)` glob qualifier, as the section it moved from and P4 do, and bash rejects it. The operator's shell is zsh |
| Nine mutants of the runbook, policy and removal runbook, each committed state restored with `git checkout HEAD --` | All caught: backfiles judged by slug year (2 failed), the purge line moved a season (1), the window boundary off by a day (1), school views taking circuit-wide files (1), expiry counted from the older write (1), a bucket block without `purge_guard` (1), the guard without its Wednesday check (1), a new retention row in the policy (1), purge code left in the removal runbook (1) |
| `uv run scripts/docs_index.py --check-descriptions` | `All 57 indexed documents under docs/ have a description`, `runbooks/annual-purge.md` among them |
| `uv run ruff format --check` / `ruff check` on the test file | clean / `All checks passed!` |
| `uv run pyright tests/docs/test_annual_purge_runbook.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` (after setting the Goal to Succeeded) | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |
| Affected set: `uv run scripts/affected_tests.py` lists 80 files. I ran it as `--run` does, on the interpreter: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 80 files>` | Stopped at the 115 s limit (130 s elapsed) with no failure reported before the stop. Over two minutes, so it is left to the pull request's `ci` check (agreement 10). The stop left nine xdist workers running in this worktree; I killed them |
| Within the two minutes instead: the ten test files that read `caselist-removal.md`, `caselist-backfiles.md` or `annual-purge.md` by path, with `tests/docs` and `tests/specs` (`-n 4`), then the ten alone (`-n 0`) | Both stopped at their limit (110 s) with no failure and no error printed: about 80% of the first, and 61 tests of the second. The load average was 40, then 175, from other sessions on the Mac. Neither left workers behind. The one file that splits the removal runbook by its headings, `packages/debate_api/tests/test_removal_runbook_index_prune.py`, ran alone: `4 passed in 0.18s`. The rest is left to the pull request's `ci` check |

## Files changed

* `docs/runbooks/annual-purge.md` (new): the runbook.
* `docs/runbooks/caselist-removal.md`: the section "The annual purge: landscape school views" (91
  lines) is replaced by a three-line pointer to step 2 of the new runbook. Following the PM, it does
  not add `v1-e30-t29`'s `BUCKET_OBJECTS_LEFT` / `SCHOOL_VIEWS_LEFT` sentence.
* `docs/runbooks/caselist-backfiles.md`: the "What is a backfile" table's annual-purge row links to
  the new runbook.
* `tests/docs/test_annual_purge_runbook.py` (new): runs the runbook's four heredoc scripts
  (`INVENTORY`, `SCHOOLVIEWS`, `EXPIRED`, `SIDECARS`) on synthetic stores. It also checks the guard on
  every bucket block, that no block holds a `!`, the removal runbook's pointer, and coverage of the
  retention table.

## Deviations from the spec

None. The spec's description asks for "a dry run listing counts, then the delete, then a check" for
every store. For stores that policy 1.17 keeps (backfiles, built files, circuit-wide reports, the
suppression list), and for deletes no command makes yet, the runbook lists, checks and names the gap
without deleting. The spec allows this for missing commands, and the PM's context asked for it.

## Decisions and assumptions

* **One date, `WINDOW_START`** (1 August of the year before the purge), decides what has aged out.
  The moved school-view script now deletes views dated *before* it rather than inside one season's
  bounds, so a season a past purge missed is caught too. Its other logic is unchanged, apart from
  `!=` written as `not … ==` and its guards moved into `purge_guard`.
* **Which season a thing is of comes from its date; which caselist is a backfile comes from the
  setting.** Dates are a snapshot's, a bundle's snapshot, an inbox archive's, or a camp release's
  topic year. A test pins that two caselists of one aged-out season are judged apart by the setting
  alone. A caselist that aged out from 2021-22 on and that the setting does not name stops the
  inventory: making it a backfile is a reviewed profile change.
* **Prod's settings are prod's.** Prod's profile has no `sync_caselists`, so the inventory judges a
  current caselist by its dates, not by the sync list. Prod's own data directory holds no manifests,
  so its local stores are dated by the bucket's.
* **The run-state bundle is read with `tar -t`, never restored**, so the purge makes no working copy
  of its own. Step 1 looks for leftovers by finding any `debate.sqlite3` three levels down in the home
  folder and `/tmp`, other than dev's and prod's data directories.
* **Expired noncurrent versions are checked, not deleted.** The lifecycle rule deletes them. One past
  its age means the rule is not working, which goes to the PM rather than to a hand delete. The check
  counts from the time a version became noncurrent (the newer version's write), with two days' grace.
* **P4 runs in a window of its own**, because its blocks set `BUCKET` and `PRUNE` themselves and
  would otherwise point the purge window at another environment's bucket.
* **Timing.** A season ages out on 31 August, and the purge runs in September, as the policy's
  "Retention" bullets say. The spec's "deletes … on 31 August" is read as the date it ages out.

## Questions for the PM

Paste-ready:

> v1-e30-t28 (annual purge runbook) has three questions:
>
> 1. **OpenEv camp years.** The retention row "OpenEv camp files … Same rule" can be read with or
>    without 1.17's backfile exception. The runbook follows your list of what the purge deletes: camp
>    topic years from 2021 on are kept once aged out ("KEEP … aged out, kept as a backfile"), and
>    earlier years are purged. `caselist.backfile_caselists` cannot name `openev`, so the topic year
>    alone decides. Recommendation: confirm, and add "from 2021 on, kept as backfiles" to the OpenEv
>    row in the next policy version.
> 2. **The leaving season's classifications.** Backfiles are "never classified into positions", but a
>    season that leaves the window was classified while it was current. Its classification cache,
>    review queue, plan and analytic texts, scan acceptances and local classifier files stay on this
>    Mac, and its cassettes may hold its cards. The runbook deletes the local classifier and cassettes
>    only for a purged (pre-2021-22) season, as the spec says. Recommendation: rule whether a season
>    becoming a backfile also loses its classification artefacts. If yes, it needs the per-caselist
>    command of follow-up 1 for the caches.
> 3. **Files in a local landscape bundle that neither list names.** The dev data directory's newest
>    `hspolicy26` bundle holds a rendered `report.html` and an R session history `.Rhistory` beside the
>    bundle's own files (read by name only; their contents were not opened). Step 2's dry run stops on
>    them by design, and `caselist remove` would stop with `UNKNOWN_LANDSCAPE_FILE` for a removal that
>    touches `hspolicy26`. Recommendation: the operator moves both out of the data directory (the
>    history file may hold school or team names) before the next removal or purge. Otherwise, rule that
>    `report.html` joins `CIRCUIT_WIDE_FILES`.

## Operator follow-ups

None. Nothing in this task ran against a bucket, AWS or the network. The runbook is first run at
the September 2027 purge.

## Follow-up work

The runbook's "What has no command yet", for the PM to file:

1. **A retention purge of one caselist** (E30): sources, manifests and disclosure records, parsed
   store, its rows in the run-state bundle and the bundle's noncurrent versions, inbox archives, and
   this Mac's landscape caches, in each bucket and here, without suppressing, logging a request or
   holding a path. `caselist remove` does each of these for a takedown only. Needed only if a
   pre-2021-22 caselist is ever found, or if question 2 rules that classifications go.
2. **The same for an OpenEv camp release** by topic year (E30).
3. **Pruning this Mac's own search-index builds** (`<data dir>/tub-index/`), which only a local
   build prunes (it keeps the newest two). Since the cutover the Mac does not build weekly, and the
   dev data directory holds four builds today. Each holds card text (E39, beside `v1-e39-t15`'s
   `tub index prune`).
4. **Cassettes filed by caselist** (E32): `<data dir>/landscape/model-cassettes/<prompt>/<key>.json`
   does not say which caselist a recording came from, so one caselist's recordings cannot be deleted
   alone.
5. **Listing versions under the rest of `reports/`, `uploads/` and `exports/`** (E29): no profile
   may, so the expired-version check cannot see them.
6. **A marker in a restored working copy** (E40): step 1 finds leftovers by their `debate.sqlite3`,
   three levels down, so a copy restored deeper is not seen. A marker file written by `caselist
   restore-run-state` would let the check be exact.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-29

**Notes:**

The annual purge is one runbook, written for the cloud setup, with every listing tested on
synthetic stores.
1. **ac1 passes.**
   * Every row of the policy's retention table maps to a runbook row, and a new policy row fails the
     test.
   * Each deleting step has its dry run, its delete and its check. Where no command exists, the step
     lists counts and names the gap, as the spec allows.
   * The removal runbook's section moved and points here, and the e30-t29 sentence was rightly left
     out.
   * check_command_blocks and check_links pass.
2. **Tested runbook code is the strongest part.** The four heredoc scripts run in `tests/docs`, and
   nine mutants are each caught: slug-year judging, the window off by a day, a bucket block without
   `purge_guard`, and the guard without its Wednesday check among them. Only the school-view block
   fails `bash -n`, because of zsh's `(N)`, as the section it moved from and P4 do.
3. **Decisions accepted:**
   * one `WINDOW_START`, so a season a past purge missed is caught too;
   * season by date and backfile by setting, with an unnamed aged-out caselist stopping the inventory;
   * the bundle read with `tar -t` and never restored;
   * expired versions checked, not deleted, since a survivor means the lifecycle rule is broken;
   * P4 in its own window;
   * September, after the 31 August ageing out.
4. **Question 1, OpenEv camp years: confirmed as written.** Topic years from 2021 on are kept as
   backfiles once they age out, and earlier years are purged. The sentence goes into data-use policy
   1.19, which the coach approves with the zero-retention sentence.
5. **Question 2, the leaving season's classifications: yes, they go, with the coach's approval in
   policy 1.19.** A backfile is "never classified into positions", and the per-school views it loses
   are rebuilt from exactly these caches. Its classification cache, review queue, plan and analytic
   texts, scan acceptances, local classifier files and cassette entries are deleted with its school
   views. That needs follow-up 1's command, so follow-up 1 is filed at p2. The first purge is
   September 2027, so there is time.
6. **Question 3: the operator moves both files out of the data directory now.** `report.html` does not
   join `CIRCUIT_WIDE_FILES`: the list names what the build writes, not what a person leaves. The
   PM gives the operator the move.
7. **Follow-up work, filed in the PM's next batch:**
   * 1, a retention purge of one caselist (E30, p2 by question 2);
   * 2, the same for a camp release (E30, p3);
   * 3, pruning this Mac's index builds (E39, p3, beside `v1-e39-t15`);
   * 4, cassettes filed by caselist (E32, p3; question 2 needs it);
   * 5, listing versions under the rest of `reports/`, `uploads/` and `exports/` (E29, p3);
   * 6, a marker in a restored working copy (E40, p3).
8. **The affected set** (80 files) ran past two minutes at load 40 to 175 from other sessions, with no
   failure before the stop. The rest is the PR's `ci`. The docs tests, the purge tests, the
   index-prune runbook test, the docs index, ruff, pyright and the specs pass.
9. **Merge:** any time, docs and tests only. The PM adds the e30-t29 sentence to the removal runbook
   in a batch after this merges.

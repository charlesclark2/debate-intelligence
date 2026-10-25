# Session report: v1-e32-t15-advantages-per-aff

| | |
|---|---|
| Task | `v1-e32-t15-advantages-per-aff` — The advantages each affirmative's teams read |
| Spec | [`plan_specs/v1/e32-argument-landscape/t15-advantages-per-aff.yaml`](../../plan_specs/v1/e32-argument-landscape/t15-advantages-per-aff.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t15-advantages-per-aff` |
| Session status | PARTIAL, waiting on the PM's ruling on ac1 <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**ac1 is done; nothing is built yet.** The counts below were sent to the PM with a proposed
cut-off (top 5 per aff and per mechanism), and the session waits for the ruling before it writes
any code, test or golden file. The Goal stays **InProgress**.

On hspolicy26 through 2026-10-20 under taxonomy 1.2.0:
* **1,093 of the 1,426 assigned affirmative rounds (76.6%) read at least one advantage.** They are
  read by 279 of the 354 teams with an assigned round.
* **All 16 advantages are read under some assigned aff.** 11 of them are read under more than one
  top-level aff, and all 16 under more than one aff or mechanism.
* **328 affirmative rounds with an advantage read have no assigned aff.** These are 591
  round-advantage reads by 104 teams. 25 of those rounds are aff rounds that only a placed card
  identifies (t03's `PLACED_CARD`).
* **A top 5 per section shows 73.1% of the aff-advantage-team entries; a top 3 shows 52.8%.**

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| advantages-per-aff | In progress | Counts sent to the PM (ac1); building waits on the ruling |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule (assigned aff rounds with placed advantage reads, distinct advantages per aff and mechanism, advantages shared across affs, advantage reads with no assigned aff), sent to the PM with a proposed cut-off | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-120); sent to the PM on 2026-10-24 |
| ac2: report.md's section on the synthetic fixture, matching a hand-written golden file, tests failing first | NOT RUN | Waits on the PM's ruling on the cut-off |
| advantages-per-aff node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN | Waits on the ruling |

## The counts (hspolicy26, through 2026-10-20, taxonomy 1.2.0)

**How they were read.**
* **Read-only.** Before each run, the guards were checked: no `DEBATE_*` variable was set and no
  `caselist pull` was running (load average 4.1).
* **One scratch script, outside the repository.** It built the CLI's own `landscape_run` service
  (the container, `config/landscape` of this worktree, no bucket) and ran it as a **dry run** with
  snapshot 2026-10-20, without publishing.
  * It captured the inputs the run hands `LandscapeReportService` and called t03's `count()` on them.
  * The advantage reads are therefore t03's own `CountedReads`: READS, at or above the review
    threshold, on the round's side.
  * The affs are the run's own t09 assignments: 1,426, which are `PLAN_TEXT` 1,172 and
    `TEAM_CARRY` 254, the same as t09's report.
  * Neither rule was re-implemented, and nothing was taken from an advantage's name or its
    taxonomy parent (every advantage's `parent` is empty in 1.2.0).
* **Time limits.**
  * The interpreter ran in its own process group under `perl -e 'setpgrp(0,0); alarm 115; exec @ARGV'`.
  * Inside it, a 100 s `SIGALRM` handler kills every pool worker before the process exits.
  * After each run, `pgrep` found no worker left from this worktree.
* **Printed counts only.** The output held taxonomy ids and numbers, never a school, team code,
  tag or cite.
* **Nothing was written.**
  * The 15 files under `~/.debate-research/dev/landscape/` and `reports/` had the same SHA-256
    before and after.
  * The run returned `written=False`, and no bucket was built.
* **Runtimes.**
  * The first attempt stopped in a few seconds. The spawn-context workers re-imported the script,
    which had no `__main__` guard, so the run broke at the pool's start (t11's quoting step, which
    parses on every run). It wrote nothing (checksums unchanged) and left no worker running.
  * The run that counted took **70.8 s** for the dry run and 71.1 s in all.

**Definitions.**
* **A round's advantages** are the advantage positions whose t03 reads include the round.
* **A round's aff** is t09's assignment. A mechanism's round counts under the mechanism and once
  under its parent, because the parent's rounds are a set.
* **A team** is t03's (school, team code), counted once per aff-advantage pair.
* **An aff-advantage-team entry** is one team reading one advantage under one section, which is the
  unit the coverage below is measured in.

**Every advantage read is on the aff side.**
* 1,421 affirmative rounds read an advantage.
* No negative round counts as reading one, because t03 counts a negative round's advantage cards as
  answers.
* No round is on no readable side.

### Assigned affirmative rounds with an advantage read

| | Rounds | Teams |
|---|---|---|
| Assigned (t09) | 1,426 | 354 |
| **With one or more advantage reads** | **1,093 (76.6%)** | **279** |
| of which `PLAN_TEXT` | 935 | |
| of which `TEAM_CARRY` | 158 | |

### Distinct advantages per aff and per mechanism

The "teams per advantage" column lists the team count of each advantage the section reads, from
most to fewest teams. Single payer's row counts its mechanisms' rounds once, with its own rounds.

| Aff or mechanism | Assigned rounds | With an advantage read | Teams | Teams with an advantage read | Distinct advantages | Teams per advantage |
|---|---|---|---|---|---|---|
| **single-payer-aff** (with its mechanisms) | 1,266 | 1,020 | 313 | 263 | 16 | 102, 85, 74, 64, 59, 39, 32, 19, 17, 17, 15, 9, 8, 8, 7, 5 |
| single payer's own rounds (no mechanism) | 840 | 679 | 203 | 170 | 16 | 63, 57, 47, 40, 32, 30, 26, 13, 12, 12, 6, 4, 4, 3, 2, 2 |
| mechanism global-budgets-aff | 119 | 105 | 53 | 50 | 11 | 33, 17, 8, 8, 8, 7, 3, 3, 1, 1, 1 |
| mechanism value-based-reimbursement-aff | 89 | 76 | 14 | 12 | 10 | 8, 4, 2, 2, 2, 2, 1, 1, 1, 1 |
| mechanism single-public-authority-aff | 79 | 69 | 26 | 23 | 11 | 15, 14, 5, 5, 3, 3, 3, 2, 1, 1, 1 |
| mechanism disparate-impact-enforcement-aff | 41 | 37 | 5 | 5 | 10 | 5, 3, 3, 2, 2, 1, 1, 1, 1, 1 |
| mechanism medicare-for-all-aff | 40 | 5 | 15 | 5 | 4 | 3, 1, 1, 1 |
| mechanism lower-payment-rates-aff | 24 | 24 | 9 | 9 | 6 | 8, 6, 4, 1, 1, 1 |
| mechanism degrowth-aff | 16 | 15 | 3 | 3 | 2 | 3, 1 |
| mechanism prescription-drug-coverage-aff | 11 | 10 | 2 | 2 | 4 | 1, 1, 1, 1 |
| mechanism nanomedicine-coverage-aff | 7 | 0 | 2 | 0 | 0 | |
| nhi-aff | 56 | 30 | 15 | 9 | 7 | 4, 3, 3, 2, 1, 1, 1 |
| public-option-aff | 36 | 35 | 8 | 8 | 8 | 5, 3, 2, 2, 2, 1, 1, 1 |
| reproductive-health-aff | 8 | 1 | 6 | 1 | 1 | 1 |
| tiered-nhi-aff | 8 | 2 | 2 | 1 | 1 | 1 |
| voucher-aff | 5 | 5 | 1 | 1 | 2 | 1, 1 |
| indigenous-aff | 15 | 0 | 5 | 0 | 0 | |
| ucc-aff | 14 | 0 | 7 | 0 | 0 | |
| incarceration-aff | 9 | 0 | 3 | 0 | 0 | |
| eco-nhi-aff | 4 | 0 | 3 | 0 | 0 | |
| human-enhancement-aff | 2 | 0 | 1 | 0 | 0 | |
| medicaid-expansion-aff, aca-reform-aff, childrens-coverage-aff | 1 each | 0 | 1 each | 0 | 0 | |

Seven affs and one mechanism have assigned rounds but no advantage read: none of their files holds
a card t02 placed under one of the topic's 16 advantages.

### Advantages read under more than one aff

* **All 16 advantages are read under at least one assigned aff.**
* **11 are read under more than one top-level aff.** With mechanisms rolled into single payer, the
  affs per advantage are 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 1, 1, 1 and 1.
* 5 are read under one top-level aff only.
* **Counting each mechanism as its own aff, all 16 are read under more than one.**

### Advantage reads from rounds with no assigned aff

| Affirmative rounds with an advantage read | Rounds | Round-advantage reads | Teams |
|---|---|---|---|
| All | 1,421 | 2,546 | 371 |
| With an assigned aff | 1,093 | 1,955 | 279 |
| **With no assigned aff** | **328** | **591** | **104** |
| of which identified only by a placed aff card (t03's `PLACED_CARD`) | 25 | 42 | 12 |
| of which with no identified aff at all | 303 | 549 | 94 |

* 92 teams read advantages only in rounds with no assigned aff.
* So 23.1% of affirmative rounds with an advantage read, and 23.2% of round-advantage reads, fall
  outside every aff's section.

### What a cut-off would show

The sections are the 23 that report.md would have: each top-level aff, with single payer's
mechanisms rolled into it, and each mechanism. 14 of them read an advantage. The unit is the
aff-advantage-team entry, 818 in all.

| Cut-off | Entries shown | Sections cut | Advantage rows behind "and N more" |
|---|---|---|---|
| Top 3 | 432 of 818 (52.8%) | 10 | 57 |
| Top 4 | 520 (63.6%) | 8 | 47 |
| **Top 5 (proposed)** | **598 (73.1%)** | **8** | **39** |
| Top 6 | 653 (79.8%) | 7 | 31 |

Under a top 5, the sections cut are:
* single payer (11 more), global budgets (6), single public authority (6);
* value-based reimbursement (5), disparate impact enforcement (5);
* public option (3), `nhi-aff` (2) and lower payment rates (1).

Counting the top-level affs alone (mechanisms rolled up), a top 5 shows 415 of 596 entries (69.6%)
and a top 3 shows 285 (47.8%).

**Proposed cut-off: top 5 per aff and per mechanism.**
* It equals t03's top cards per position (`DEFAULT_TOP_CARDS` 5).
* It shows about three quarters of the entries.
* Every list it cuts has its tail at 1 to 8 teams per advantage; the single-payer list's sixth
  advantage has 39 teams.
* A top 3 hides 57 rows, among them single payer's fourth and fifth advantages (64 and 59 teams)
  and global budgets' fourth (8).

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

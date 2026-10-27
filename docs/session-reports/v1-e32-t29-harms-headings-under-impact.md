# Session report: v1-e32-t29-harms-headings-under-impact

| | |
|---|---|
| Task | `v1-e32-t29-harms-headings-under-impact` — Harms headings counted under Impact, the word the coach's debaters use |
| Spec | [`plan_specs/v1/e32-argument-landscape/t29-harms-headings-under-impact.yaml`](../../plan_specs/v1/e32-argument-landscape/t29-harms-headings-under-impact.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t29-harms-headings-under-impact` |
| Session status | BLOCKED <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**I stopped at the PM's stop condition (b) after the counts, and built nothing. The Goal stays
`InProgress`.**

* **ac1, the counts, are done** ([below](#the-counts-ac1)), on the synthetic caselist and on
  hspolicy26 through 2026-10-20. They are counts only, read-only.
* **Harms is small on hspolicy26.** Only 1 of 16 advantages has a Harms row in its link-chain table.
  That advantage carries all 16 harms cards, which come from 3 documents. The other 15 advantages
  print an empty "Harms | no labelled card" row.
* **Stop condition (b) holds, 1 of 1.** Only one advantage has both a Harms row and an Impact row,
  and the fold changes its impact rank-1 card.
* **How it changes is narrow.** The new rank 1 is not a harms-only card. It is an impact cluster
  that was already counted, at rank 4: tied on 2 teams and kept off the 3-row table by the
  cluster-id tie-break. One copy of it, read under a `harm` heading, gives it a third team.
  * The old rank 1 becomes rank 2.
  * The old rank 3 drops off the table.
* **Stop conditions (a) and (c) do not hold.**
  * (a): no counted DA, CP, K or aff card has a harms heading anywhere in its headings.
  * (c): no taxonomy or override in `config/landscape` uses `harm` or `harms` as a whole word.
* **The build also needs code outside the spec's packages:** `debate_core/domain` and
  `debate_core/application` ([Deviations](#deviations-from-the-spec)).
* **ac2 is NOT RUN.** The relay prompt for the PM is [below](#question-for-the-pm). It bundles the
  stop with three smaller questions the build would otherwise decide on its own.

## The counts (ac1)

**What ran:**
* A read-only script in the session's scratchpad, wired by hand as t28's counts were:
  * over `~/.debate-research/dev`;
  * no container, no worker pool, no aff assignments and no analytic texts;
  * the classification cache read through the run's read-only view.
  * It captures the report's own `_LinkChains`, so a card's roles, sub-headings and impact cards are
    read exactly as the report reads them.
* The script:
  `/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e32-t29-harms-headings-under-impact/9212a325-8372-4c2e-ae27-200339aed9b5/scratchpad/counts/count_harms.py`.
  The synthetic count is `count_synthetic.py` beside it.
* **Code:** HEAD `40f9d3d`, which already holds t28 (`414ad95`). No sync was needed.
* **Input:** hspolicy26 through 2026-10-20, taxonomy 1.4.0.
* **Runs:** three runs of 49.1 s, 51.2 s and 68.6 s, each under a 115 s alarm on the interpreter.
  The later two added detail fields only. Every count they share is the same in all three.
* **The store was unchanged:** `debate.sqlite3`'s SHA-256 was `feac070d…` before and after. No
  `DEBATE_` variable was set, no `caselist pull` was running, and no process outlived a run.
* **The published bundle:** the counts below match the report.md published at 01:13 on 2026-10-27
  (78,897 B). It has 16 `| Harms |` rows, 15 of them empty, and the line `harms 15 of 16`.

### Harms rows and what they carry

| | Synthetic caselist | hspolicy26 |
|---|---|---|
| Advantages with a link-chain table | 2 | 16 |
| … with a Harms row (a labelled card) | 0 | **1** |
| … of those, also with an Impact row | 0 | **1** |
| Advantages with an Impact row | 1 | 15 |
| Counted cards in the Harms role (all advantages) | 0 | 16 |
| … distinct clusters | 0 | 12 |
| … documents | 0 | 3 |
| … heading blocks (a document and its headings down to the harms one) | 0 | 5 |
| … already impact cards today (tag or heading) | 0 | 1 |
| Harms sub-headings by form: `harms` / `harm` | 0 / 0 | 8 / 8 |
| Harms sub-headings holding other words besides the label (distinct / card headings) | 0 / 0 | 2 / 8 |
| … of those word sets used by two or more teams | 0 | 0 |
| Advantage cards with a harms heading at or above the placing heading | 0 | 0 |
| **Stop condition (a):** counted non-advantage cards with a harms word in any heading | 0 | **0** |

All 16 harms cards on hspolicy26 are under one advantage.

### Where "Harms" reaches the output today

| Place | Synthetic caselist | hspolicy26 |
|---|---|---|
| report.md link-chain tables, `Harms` rows | 2 (both "no labelled card") | 16 (15 "no labelled card") |
| report.md per-kind line "Positions with no labelled card, by role: … harms N of M" | 1 (`harms 2 of 2`) | 1 (`harms 15 of 16`) |
| report.md header bullet "**The link chain** … for an advantage harms, inherency and solvency" | 1 | 1 |
| report.md lines under "What each impact runs through" | 0 | 0 |
| report.md, every whole-word `harm`/`harms` (the three places above, no tag holds one) | 4 | 18 |
| impact_cards.csv (it has no role column; no tag holds the word) | 0 | 0 |
| The dry run, `scripts/landscape_dry_run_by_section.py` (it prints no role) | 0 | 0 |
| The guide, `docs/guides/landscape-taxonomy.md` line 586 | 1 | 1 |

`ChainRole.HARMS` is never persisted. No stored report, cache or CSV holds the value `harms`, so
removing the role leaves nothing to migrate.

### What-if: harms read as impact

I took the what-if over the same reading. Each advantage's impact reads became its impact cards
today, plus every card in its Harms role. They were then ranked by the report's own `_ranked`, the
rule both the impact table and the chain's Impact row use.

| Advantages (hspolicy26) | Count |
|---|---|
| Unchanged (no harms card) | 15 |
| Same rank 1, counts added | 0 |
| **A new rank 1** | **1** |
| Impact rank 1 where there was none | 0 |

**Stop condition (b):** one advantage has both rows, and its rank 1 changes. That is 1 of 1, over
half.

The one advantage that changes, before → after:

| | Before | After |
|---|---|---|
| Impact card reads | 47 | 62 |
| Impact clusters | 12 | 22 |
| Documents with an impact card | 43 | 45 |
| Clusters read by two or more teams | 4 | 4 |
| Teams of the three ranks shown | 2, 2, 2 | 3, 2, 2 |
| Rank-1 card | its old rank 1 | its **old rank 4** (2 teams before, 3 after) |
| Where the old rank 1 goes | — | rank 2 |
| Old shown ranks still shown | — | 2 of 3 (the old rank 3 drops off) |
| Is the new rank 1 the card in today's Harms row? | — | no |
| Harms reads in the new rank-1 cluster | — | 1 |

**Why the rank changes:** all four 2-team clusters were tied, and the cluster id decided their
order. The one harms read adds a team to the one cluster that was just off the table. No count is
lost: every harms read lands under Impact (47 + 15 new reads = 62; the 16th harms card was already
an impact card).

**Scenario names.** The scenario names shown would not change. Two harms sub-headings hold words
besides the label, on 8 card headings, but no team pair shares one.

## Question for the PM

Paste this to the PM:

````text
v1-e32-t29 (harms headings under Impact): stopped at your stop condition (b), counts only, nothing built.

Facts (hspolicy26 through 2026-10-20, taxonomy 1.4.0, read-only; synthetic caselist has no harms heading):
- 1 of 16 advantages has a Harms row; all 16 harms cards (12 clusters, 3 documents) are under it. The
  other 15 print an empty "Harms | no labelled card" row. No DA, CP, K or aff card has a harms heading
  (condition a: no). No taxonomy or override uses "harm"/"harms" (condition c: no).
- That one advantage is also the only one with both rows, and the fold changes its impact rank 1: 1 of 1,
  so condition (b) holds.
- How: the new rank 1 is NOT a harms-only card. It is an impact cluster already counted at rank 4, tied
  with three others on 2 teams and kept off the 3-row table by the cluster-id tie-break. One copy read
  under a "harm" heading gives it a third team. Old rank 1 -> rank 2; old rank 3 drops off. Impact reads
  47 -> 62, clusters 12 -> 22, documents 43 -> 45; no count lost.
- "Harms" reaches report.md in 18 places (16 chain rows, the "harms 15 of 16" gap line, the header
  bullet), the guide once, and nothing else (not impact_cards.csv, not the dry run, no lead-in line).

Question 1, the stop:
  (A) Build as pre-ruled. The rank-1 change is the fold doing what it says: one more team read that card
      as its impact. The trigger is a 1-advantage denominator and a 4-way tie.   <- recommended
  (B) Build, but leave the impact ranking as today and only drop the Harms row, label and line. This loses
      the 15 harms reads from Impact, so it breaks "no count lost".
  (C) Hold the task; tell the coach what changes first.
Recommendation: (A). The rule (b) guards against the fold reshuffling impacts widely, and here it moves
one tied cluster up from just off the table on one advantage. I would name the change in the report and
in the republish's pilot check.

Question 2, scope: the build cannot stay inside constraints.packages. Impact cards are picked kind-blind
in debate_core/application/landscape_report.py (`_is_impact`, before the matcher is built), and the roles
an advantage's table shows are CHAIN_ROLES / ChainRole.HARMS in debate_core/domain/landscape_report.py.
The guide line you asked for is in docs/guides/landscape-taxonomy.md. May I add those three paths to
constraints.packages? (Recommended: yes. Nothing persists ChainRole.HARMS, so I would remove the member,
not leave it unused.)

FYI, what I'll do unless you say otherwise:
- One rule, in link_chains.heading_roles: for an advantage, `harms`/`harm` label Impact. An advantage's
  impact cards become the cards whose roles hold Impact, so the impact table, impact_cards.csv, the
  chain's Impact row and the "no labelled impact" counts all read the same set. Harms is read only where
  the Harms role read it today (a sub-heading below the placing heading, not an answer, naming no other
  role), so no card is gained or lost beyond that.
- t14's "words beside an impact label" names a scenario from "Dome harms" as from "Dome impact"; a bare
  "Harms" names none. On hspolicy26 this shows no new name (no two teams share the words).
- t25's "card above, unless it is an impact card" treats a harms card above as an impact card. I'll
  count the lead-in changes in the build's report.

Reply with: Q1 A/B/C, Q2 yes/no, and any FYI you want changed.
````

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `harms-under-impact` (Harms under Impact) | Pending | Counts taken. The build is held at stop condition (b) for the PM's ruling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, where harms reaches the report and what it carries, in the report | PASS | `count_harms.py config/landscape` (hspolicy26, 49.1 / 51.2 / 68.6 s) and `count_synthetic.py tests/fixtures/landscape` (synthetic), each run with the session's `.venv/bin/python` → [the counts](#the-counts-ac1) |
| ac2: no "Harms" section on the synthetic fixtures, its cards counted under Impact, hand-written goldens, tests red first | NOT RUN | Stopped at the PM's stop condition (b) before any build or test |
| Node: Landscape tests pass, `uv run pytest packages/debate_core/tests/arguments/landscape` | NOT RUN | No code changed. The node waits on the build |

## Before the report (working agreement 10)

The branch changes this report only. With no code changed, I ran no ruff, pyright or lint-imports.

* **`uv run scripts/validate_specs.py`** → `OK: 491 files, 40 epics, 429 tasks, 22 releases`.
* **`uv run python scripts/check_command_blocks.py --base origin/dev`** → `OK: no # comments in 530 shell
  code blocks in 192 Markdown files (1 session reports changed since origin/dev)`.
* **The affected set** (`uv run scripts/affected_tests.py`) is the always-run list alone: 22 files.
  * I ran it once as `.venv/bin/python -m pytest -n auto -m "not slow and not live"` under a 115 s
    alarm. Another session's test run had the load average at 54.
  * The alarm stopped it at 1:55, before it finished, so it is **not a result**.
  * It left nine orphaned collect-only `pytest` children of `test_ci_workflow_test_job.py`, from
    this worktree. I stopped them, and none is left.
  * Per agreement 10, the set goes to the pull request's `ci`.
* **Within the two minutes**, the tests of what this branch touches:
  `.venv/bin/python -m pytest -n 4 -p no:randomly -m "not slow and not live" -q tests/specs
  tests/scripts/test_check_command_blocks.py` → `165 passed in 5.72s`.

## Files changed

* `docs/session-reports/v1-e32-t29-harms-headings-under-impact.md`: this report.

## Deviations from the spec

* **The build needs code outside `constraints.packages`.** The spec lists `debate_core.arguments`, but
  the code that has to change is also in two other places:
  * `debate_core/application/landscape_report.py` picks an advantage's impact cards with a
    kind-blind `_is_impact`. It does this before the position matcher exists, and the harms role
    needs the matcher's placing heading.
  * `debate_core/domain/landscape_report.py` holds `CHAIN_ROLES` and `ChainRole.HARMS`. The
    link-chain table and the "Positions with no labelled card, by role" line both iterate
    `CHAIN_ROLES`.

  The guide line the PM asked for is in `docs/guides/landscape-taxonomy.md`. It is also outside the
  packages. This is Question 2 of the relay prompt.

## Decisions and assumptions

* **"Cards and headings under it."**
  * A card under harms is a counted read whose roles held `HARMS`. That is the role's own rule: a
    non-answer sub-heading below the placing heading, naming harms and no other role.
  * A heading is counted as a heading block: a document, with its headings down to the harms one.
* **The what-if's impact set:** today's impact cards plus every Harms-role card, ranked by the
  report's own `_ranked`. It is the set the PM's pre-ruling describes ("every card and heading they
  carried is counted under Impact … ranked together as one role by the existing rule").
* **Reading stop condition (b):** I read "the advantages that have both rows" as the advantages
  whose link-chain table has both a Harms and an Impact card. There is 1, and its rank 1 changes.
  If the PM meant something wider, every advantage with a harms card is also that one advantage, so
  the answer is the same.

## Operator follow-ups

None yet. The republish block (after the merge, any day but Wednesday, a dry run first, then the
pilot check) comes with the build, once the PM rules.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

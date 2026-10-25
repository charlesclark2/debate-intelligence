# Session report: v1-e32-t15-advantages-per-aff

| | |
|---|---|
| Task | `v1-e32-t15-advantages-per-aff` — The advantages each affirmative's teams read |
| Spec | [`plan_specs/v1/e32-argument-landscape/t15-advantages-per-aff.yaml`](../../plan_specs/v1/e32-argument-landscape/t15-advantages-per-aff.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t15-advantages-per-aff` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Every criterion passes, and the Goal is Succeeded.** report.md now has an **Advantages by
affirmative** section. It covers each aff v1-e32-t09 assigned rounds to, and each mechanism under it:
* its advantages, ranked by distinct teams;
* the top 5, then "and N more, read by M teams", where M counts distinct teams;
* one closing line naming the affs and mechanisms with no advantage read, with their rounds;
* the line "N advantage reads in R affirmative rounds, by T teams, have no assigned aff", saying how
  many of those rounds only a placed card identifies.

It follows the PM's six rulings of 2026-10-24, which are recorded above the spec's
`acceptanceCriteria`. No other bundle file changes: positions.csv, top_cards.csv, impact_cards.csv,
trends.csv and the school view are byte-identical against their goldens, and t04's file lists and
t13's removal selection are untouched.

**What to look at first:**
* the hand-written golden,
  [`report_section.md`](../../tests/fixtures/landscape/advantages_per_aff/report_section.md), and the
  fixture table in its README;
* [the mutants](#mutants): all seven were caught, the PM's four among them;
* [the live check](#the-section-on-hspolicy26): a dry run on hspolicy26 gives the section exactly
  ac1's numbers, 591 reads in 328 rounds by 104 teams, 25 of the rounds identified by a placed card.

**The affected set was too long for a session.** It is 180 files and was stopped by the 115 s limit
at 89%, with nothing failed up to then. Under agreement 10 it is left to the pull request's CI. The
test directories of what changed, with the always-run list, ran instead: 5,584 passed in 110.3 s.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| advantages-per-aff | Done | Counts sent (ac1), the PM ruled the same day, the section built with its golden file and tests shown failing first (ac2) |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule (assigned aff rounds with placed advantage reads, distinct advantages per aff and mechanism, advantages shared across affs, advantage reads with no assigned aff), sent to the PM with a proposed cut-off | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-120), sent on 2026-10-24 with top 5 proposed; the PM ruled (a) on all six questions the same day |
| ac2: after the ruling, on the synthetic fixture, report.md shows each aff's and mechanism's advantages with team counts and the cut-off, and the reads with no identified aff, matching a hand-written golden file; an advantage read in a round assigned to another aff is never counted under this one; tests shown failing first | PASS | `test_advantages_report_md_section_matches_the_hand_written_golden_file` against [`report_section.md`](../../tests/fixtures/landscape/advantages_per_aff/report_section.md), and the t03 whole-file golden `report.md` with the section added by hand. `test_advantages_a_read_in_a_round_assigned_to_another_aff_is_never_counted_under_this_one`, with its mutant caught. [Red first](#tests-shown-failing-first) |
| advantages-per-aff node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_report.py` under `perl -e 'alarm 100'` (agreement 10: the limit goes on the interpreter) → 76 passed in 1.93 s |

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

## The PM's rulings, applied

All six were (a), on 2026-10-24. They are recorded as a comment above the spec's
`acceptanceCriteria`:

1. **Top 5 per aff and per mechanism**, ranked by distinct teams, ties by id, then "and N more, read by
   M teams" (`DEFAULT_ADVANTAGES_PER_AFF` 5, a `LandscapeReportService` parameter).
2. **A round whose aff only a placed card identifies counts with the no-assigned-aff reads**, and the
   report says how many such rounds there are. t09's assignments are the only source of a section's
   rounds.
3. **The line is "591 advantage reads in 328 affirmative rounds, by 104 teams, have no assigned aff"**,
   with the live numbers, followed by "A placed card identifies the aff of 25 of those rounds, and their
   advantages are not counted under it."
4. **One closing line** names each aff and mechanism with assigned rounds but no advantage read, with
   its rounds (Nanomedicine coverage, a mechanism of Single payer, among them). None of them has a section.
5. **No section for single payer's rounds that name no mechanism.** They count only in Single payer's
   section, where every round is one member of a set, so it counts once.
6. **M is the distinct teams reading any hidden advantage** under that aff or mechanism.

## What was built

| Change | Where |
|---|---|
| The count: each round's advantages from t03's own `CountedReads` (affirmative rounds only), each section's rounds from t09's assignments, a mechanism's rounds added once to its top-level aff, the ranking, the cut-off and the distinct hidden teams, the closing line, and the reads with no assigned aff | `application/landscape_advantages.py` (new), called from `LandscapeReportService.count` with the assigned rounds and the rounds t03 identified by a placed card |
| The values | `domain/landscape_report.py`: `AdvantagesByAff`, `AffAdvantages`, `AffAdvantage`, `AffWithoutAdvantages`, `UnassignedAdvantageReads`, and `LandscapeReport.advantages_by_aff`, which is None when the taxonomy has no advantage, so an LD report has no section |
| The section | `arguments/landscape/render.py`: `_advantages_section`, after the positions and before the analytic texts. Nothing else in the file changed except the docstring, so a merge with v1-e32-t18's school-view edits keeps both sides |
| The fixture and its golden | `tests/fixtures/landscape/advantages_per_aff/` (new): taxonomy, round table, README, and `report_section.md` written by hand. In the t03 golden `report.md`, the section was added by hand from that fixture's table: 9 reads in 7 rounds by 6 teams, 4 of the rounds with a placed card |
| The tests | 11 in `test_landscape_report.py`, named `test_advantages_*` |
| The coach guide | `docs/guides/landscape-taxonomy.md`, "The advantages under each aff": what puts a round under an aff, the mechanism rule, and that an advantage's `parent` cannot move it |

**Nothing is taken from an advantage's name or its taxonomy `parent`.** The fixture gives
`costs-advantage` the parent `public-option-aff`, and a test shows costs is not under Public option.

## Tests shown failing first

**Against a skeleton that counted nothing:** the domain values, the wiring and the renderer were in
place, but `advantages_by_aff` returned no sections and zero reads.
* Command: `.venv/bin/python -m pytest -p no:randomly -n 0 packages/debate_core/tests/application/test_landscape_report.py -k advantages`.
* **10 of the 11 new tests failed**, each for its reason:
  * the golden section did not match;
  * the counts were zero;
  * `_section` found no aff (`StopIteration`);
  * the no-advantage taxonomy still got a section.
* **The guard against a cut-off below one passed.** The service already refused it.
* The `-k` also picked up t10's existing `test_impact_cards_are_listed_for_das_and_advantages_only`,
  which passed.
* `test_render.py`: the t03 whole-file golden `report.md` failed (1 failed, 31 passed).

**After the implementation:** both files, 108 passed in 2.58 s.

## Mutants

Each mutant was applied to the committed `landscape_advantages.py` by a scratch script, then
`test_landscape_report.py` and `test_render.py` ran (108 tests). After each run the file was restored
from git, and the last restore was checked with `git diff --quiet`. Each run had a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8), though none of these tests uses Hypothesis. Every catch
is an assertion failure; nothing errored at collection.

| Mutant | Caught by |
|---|---|
| **Another aff's round counted here**: a section reads every round of its teams, whatever aff the round is assigned | 4: the golden section, the other-aff test, the mechanism test, the distinct-teams test |
| **A mechanism round counted twice under its parent**: rounds kept as a list, and the mechanisms' rounds added again to the parent | 2: the golden section, the mechanism test (6 rounds became 9) |
| A team counted once per round rather than once per aff-advantage pair | 3: the golden section, the other-aff test, the cut-off test |
| **The cut-off one too many** (6 shown) | 4: the golden section, the other-aff test, the cut-off test, the distinct-teams test |
| The cut-off one too few (4 shown) | 4: the same four |
| **M as a sum** of the hidden advantages' teams | 4: the golden section, the other-aff test, the cut-off test (3 became 5), the distinct-teams test (1 became 2) |
| The placed-card rounds left out of the no-aff reads | 4: the golden section, the no-aff test, the t03-fixture test, the t03 whole-file golden |

## The section on hspolicy26

This check was not a criterion. The scratch script built the run as in ac1 and ran it as a dry run
through 2026-10-20.
* **Guards:** no `DEBATE_*` variable, no `caselist pull`, load average 15.3.
* **Limits:** the same process group, a 115 s `alarm` and a 100 s pool-killing handler.
* **Output:** the new section's counts only, no team code.
* **Runtime:** 82.4 s, `written=False`.
* **Nothing was written.** The 15 files under `landscape/` and `reports/` had unchanged checksums,
  and no worker was left.

It gives ac1's numbers exactly:
* **Single payer:** 1,266 rounds, 313 teams, 263 reading an advantage. Its top 5 are 102, 85, 74, 64
  and 59 teams, and then 11 more, read by 128 teams.
* **Global budgets:** 33, 17, 8, 8 and 8 teams, and then 6 more, read by 16 teams.
* **Public option:** 5, 3, 2, 2 and 2 teams, and then 3 more, read by 1 team. Here a sum would say 3.
* **The closing line:** Nanomedicine coverage (7 rounds), ucc (14), indigenous (15), incarceration
  (9), eco-NHI (4), human enhancement (2), and ACA reform, children's coverage and Medicaid expansion
  (1 each).
* **The no-aff line:** 591 advantage reads in 328 affirmative rounds, by 104 teams, have no assigned
  aff; a placed card identifies the aff of 25 of those rounds.

## Before the report (working agreement 10)

* **The affected set.** `uv run scripts/affected_tests.py` selected 180 test files.
  * They were run as `.venv/bin/python -m pytest -n auto -m "not slow and not live"` over that list,
    in their own process group under `perl -e 'setpgrp(0,0); alarm 115'`.
  * **The alarm stopped them at 89%,** with no failure up to then.
  * No process from this worktree was left running.
  * Over two minutes, the set is left to the pull request's CI (the PM's ruling of 2026-10-19). It is
    not handed to the operator.
* **The test directories of what changed and the always-run list ran in 110.3 s, 5,584 passed.**
  * `packages/debate_core/tests/application`, `tests/arguments/landscape` and `tests/domain`;
  * `packages/debate_cli/tests/test_landscape_command.py`;
  * `tests/architecture`, `tests/specs` and `tests/docs`;
  * `test_app.py` and `test_help_rendering.py`.
  * After the guide's edit, `tests/docs` and `tests/architecture` ran again: 254 passed in 14.70 s.
* **The static checks:**
  * `uv run --frozen ruff format --check .` → 1297 files already formatted;
  * `uv run --frozen ruff check .` → all checks passed;
  * `uv run --frozen pyright packages/debate_core` → 0 errors;
  * `uv run --frozen lint-imports` → 16 kept, 0 broken;
  * `scripts/check_thin_handlers.py` → OK, 51 handlers;
  * `scripts/docs_index.py --check-descriptions` → all 47 documents have a description;
  * `scripts/check_command_blocks.py` → OK;
  * `uv run scripts/validate_specs.py` → OK, 445 files.

## Files changed

* **`debate_core.application`:**
  * `landscape_advantages.py` (new): the count;
  * `landscape_report.py`: the call, the cut-off parameter, and the placed-card rounds collected;
  * the module docstring.
* **`debate_core.domain`:** `landscape_report.py`, the section's values and the report's field.
* **`debate_core.arguments`:** `landscape/render.py`, the section in report.md.
* **`packages/debate_core/tests`:** `application/test_landscape_report.py`, the 11
  `test_advantages_*` tests and the fixture reader.
* **`tests/fixtures/landscape`:**
  * `advantages_per_aff/` (new);
  * `golden/report.md`, the section added by hand.
* **`docs/guides`:** `landscape-taxonomy.md`, "The advantages under each aff".
* **Spec:** the PM's rulings as a comment above `acceptanceCriteria`, and the Goal Succeeded.
* **This report.**

## Deviations from the spec

None.

## Decisions and assumptions

* **The golden for ac2 is the section, not a whole report.md, on the new fixture.** Writing a whole
  report by hand for it would mean its header, positions and trends, which this task does not touch.
  The section is compared byte for byte, from its heading to the next `##`. The whole-file golden of
  t03's fixture, which every report test already builds, has the section added by hand too, so the
  section is also checked in place in a full report.
* **The fixture's inputs are a table read in the test module**, not a generator in `scripts/`. Both
  `scripts/` and `debate_core.testing` are outside this task's packages.
* **Sections are ordered** by teams, then rounds, then id, as report positions are. A mechanism
  follows its aff, in the same order, and the closing line uses the same order.
* **Only affirmative rounds are counted.** t03 already counts an advantage card in a negative round
  as an answer. A round on no readable side could count as reading an advantage, but it is no
  affirmative round, so it is in neither the sections nor the no-aff line. On hspolicy26 there are none
  (ac1).
* **A deeper taxonomy is handled.** A mechanism of a mechanism counts under each aff above it, once
  each, and is listed under its top-level aff. A parent that is not an active aff ends the line.
  Taxonomy 1.2.0 has one level.
* **Each advantage row shows its teams only.** That is the PM's "team counts only"; rounds are not
  shown.
* **The section is in report.md only.** No CSV and no metadata line changed, so positions.csv and
  the rest are byte-identical against their goldens.

## Operator follow-ups

None. Republishing the hspolicy26 report with the section is the PM's to coordinate after the merge.

## Follow-up work

* **The 303 affirmative rounds with no identified aff** hold 549 of the 591 no-aff advantage reads.
  `v1-e32-t17` (kritikal affirmatives) is the task that identifies more of them, and the section's
  closing line will fall as it does.
* **When v1-e32-t18 merges**, a sync of `render.py` should keep both sides. `_advantages_section` is
  one new function and one line in `render_markdown`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

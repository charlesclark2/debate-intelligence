# Session report: v1-e32-t56-analytic-texts-take-the-own-side-rule

| | |
|---|---|
| Task | `v1-e32-t56-analytic-texts-take-the-own-side-rule` — An analytic text under an answer heading in its own side's file reads its position |
| Spec | [`plan_specs/v1/e32-argument-landscape/t56-analytic-texts-take-the-own-side-rule.yaml`](../../plan_specs/v1/e32-argument-landscape/t56-analytic-texts-take-the-own-side-rule.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t56-analytic-texts-take-the-own-side-rule` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The Goal is Succeeded.** `v1-e32-t49`'s own-side rule now reaches the analytic texts. An overview, CP
text, plank, alternative or role of the ballot placed under an answer heading, in a file disclosed only
on its position's own side, reads that position. Where the rule sits is as the PM ruled on 2026-11-07
([the ruling](#the-pms-ruling-2026-11-07)):

* **It is applied after the cache**, where each file's cached readings meet that file's sides, before the
  texts to quote are chosen.
* **It goes through t49's one rule.** The new `readings_on_own_side` calls `side_role` on each placed
  reading; it is not a second copy of the rule.
* **The cache keeps the matcher's role**, and the analytic-texts rules version is not bumped.

**What it changes on hspolicy26, counted before building as sent to the PM:** **1 text changes role**, an
overview under a DA, from ANSWERS to READS, in 1 file, for 1 position. Nothing else changes.

The tests use invented texts and were shown failing first, against a skeleton that changed nothing. Ten
mutants on the call site and the helper were all caught, each by an assertion.

## The count (2026-11-06, as sent to the PM)

**How it was taken.** The operator ran it read-only, from this worktree, over the dev data directory
(`~/.debate-research/dev`).

* **Source.** hspolicy26 through its newest snapshot, 2026-11-03.
* **Readings.** The analytic-text cache's readings: 5,132 entries, all under parser `2026.11.03-docx-9`
  and rules digest `af440c70526d`, which is the digest this checkout's taxonomy, overrides and actors
  produce.
* **Sides.** Each file's sides come from its on-topic live disclosures through the snapshot (the weekly
  manifests and the suppression list), as `read_seed_sources` gives a source's teams.
* **Rule.** Each placed reading went through `side_role`.
* **Output.** Counts only, written nowhere. The script is the session's own, kept in its scratchpad
  (`count_own_side_analytic_texts.py`), not in the repository.

Its output, as the operator returned it:

| Count | Value |
|---|---|
| On-topic files through 2026-11-03 | 5,190 |
| Of them, with a cached readable reading | 5,132 |
| Analytic texts read / placed under a position | 3,360 / 1,832 |
| **Texts that change role** | **1**: OVERVIEW, ANSWERS → READS |
| Files / positions / position-and-file pairs touched | 1 / 1 / 1 |
| Kind of position | da |
| What the report does with it | moves from "elsewhere" to counted, so that DA's overview count gains its file's teams |

Every placed text, by its file's side and the role cached for it:

| Kind | Own side, READS | Own side, ANSWERS | Other side, READS | Other side, ANSWERS | Both sides, READS |
|---|---|---|---|---|---|
| CP text | 220 | 0 | 12 | 0 | 1 |
| CP plank | 561 | 0 | 32 | 0 | 6 |
| K alternative | 100 | 0 | 24 | 1 | 0 |
| Role of the ballot | 2 | 0 | 0 | 0 | 0 |
| Overview | 801 | **1** | 71 | 0 | 0 |

Only 2 placed texts carry ANSWERS at all. One is the overview that changes. The other is an alternative in
a file on the other side, which keeps ANSWERS.

## The PM's ruling (2026-11-07)

1. **Built as proposed.** `side_role` is applied after the cache, where readings meet their file's sides,
   before the texts to quote are chosen, through t49's one rule. The cache key has no sides in it, and a
   file can later be disclosed on the other side, so the rules version is not bumped. The tests use
   invented texts and were shown failing first. Then mutants on the call site.
2. **A CP text read by its place: (a), left out and not filed** ([decision 2](#decisions-and-assumptions)).
3. **The count is recorded as sent.** The operator republishes hspolicy26 when the next snapshot is
   published, not for this change alone.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `analytic-texts-take-the-own-side-rule` (Analytic texts' side) | Done | Counted first (above), then ruled on. Then the skeleton and its red runs, the rule and its call site (`6f090d9`), the per-file seam case (`b103977`), and ten mutants. Its criterion passes (114 tests) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: analytic texts in a file on their position's own side read it, through side_role, with the count of texts that change role reported, by tests on invented texts shown failing first | PASS | The count: [above](#the-count-2026-11-06-as-sent-to-the-pm), 1 text, sent before any code. Through `side_role`: `readings_on_own_side` calls it, and `report_inputs` calls that. Failing first: [the red runs](#how-ac1-was-shown). Green: below |
| Node: Analytic texts' side tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape -k analytic`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape -k analytic` → `114 passed in 25.87s` |

### How ac1 was shown

**Red, against a skeleton.** `readings_on_own_side` first returned its readings unchanged, and
`report_inputs` did not call it.

* **The pure tests** (`test_analytic_texts_own_side.py`, `-n 0`): `5 failed, 6 passed`. All 5 failures
  are the same assertion, ANSWERS where READS is expected:
  * the own-side case, for `NEG`, `CON`, `NEG` twice, and `NEG` with `UNKNOWN`;
  * an affirmative overview in an affirmative file.

  The 6 that pass are expected to pass on a skeleton that changes nothing:
  * keeps-its-role, for the other side, pro, both sides, no readable side and no disclosure;
  * the only-the-role-changes guard.
* **The seam tests** (`test_analytic_texts.py -k "own_side or other_side or sides_of"`): `2 failed,
  2 passed`. Both failures are role assertions: the own-side file, and a cached reading meeting a later
  run's sides. The other-side and both-sides cases pass.

**Green.** Both files pass, 33 tests at that point. The per-file seam case was added before the mutants:
34.

**What the tests hold.** Each test's texts are an overview, a CP text and an alternative, all invented, each
under an `AT:` heading naming a negative position. Whenever a test reads the texts, it first checks that the
matcher gives each one ANSWERS.

* In a file disclosed only on the negative side, all three read.
* In a file on the affirmative side, on both sides, on no readable side, or with no disclosure, all three
  keep ANSWERS.
* An affirmative overview reads in an affirmative file and answers in a negative one.
* At the seam, the texts to quote are chosen after the rule. In the own-side file the CP text and the
  alternative are quoted; in the others nothing is.
* The cache still holds ANSWERS for all three.
* A reading cached while its file was on both sides reads once the run's sides are negative only.
* In one run, a negative file's texts read while an affirmative file's text keeps ANSWERS.

### Mutants

Ten mutants, run against `test_analytic_texts_own_side.py` and `test_analytic_texts.py` (34 tests, `-n 0`),
each restored with `git checkout HEAD --`. **All ten caught, each by an AssertionError**; no catch was a
crash.

| Mutant | Tests failing |
|---|---|
| The call site removed | 3 |
| The rule applied after the texts to quote are chosen | 2 |
| No sides given to the rule | 3 |
| The sides of every file of the reading, not the file's own | 1 (the per-file seam case, added for it) |
| The report given the cached roles, the quote the rule's | 3 |
| The rule's readings written into the cache | 3 |
| The helper keeps every role (`side_role` not called) | 8 |
| The helper makes every placed text read | 10 |
| The helper drops unplaced texts | 1 |
| The helper changes more than the role | 1 |

The helper-drops-unplaced-texts mutant first failed with an IndexError in the test's own indexing. The test
now compares the tail whole (`868c59d`), and the mutant fails on that assertion.

### Checks run before this report

* **The affected set.** `uv run scripts/affected_tests.py --run` (177 files) was stopped at its 115-second
  limit and is left to the pull request's `ci` (agreement 10). Within the limit, these ran instead:
  * `tests/arguments/landscape`, `test_analytic_texts.py`, and the suites that call `report_inputs` or
    `classify` (`test_landscape_run.py`, `test_landscape_dry_run_text_caches.py`, `test_aff_assignment.py`,
    `test_position_classification.py`), with the always-run list (`tests/architecture`, `tests/specs`,
    the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`): `1771 passed in
    30.12s`.
  * `test_landscape_report.py`: `106 passed in 5.73s`.
* `ruff format --check packages/debate_core` (914 files already formatted); `ruff check .` (all checks
  passed); `pyright packages/debate_core` (0 errors); `lint-imports` (20 kept, 0 broken);
  `scripts/check_thin_handlers.py` (OK); `uv run scripts/validate_specs.py` (OK: 643 files).

## Files changed

* **`debate_core.arguments.landscape.analytic_texts`**: `readings_on_own_side`, which sends each placed
  reading's role through `side_role`; and the module docstring's paragraph on a file's side.
* **`debate_core.application.analytic_texts`**: `AnalyticTextService.report_inputs` applies it to each
  file's readings, with the disclosing teams' sides, between the cache and the quote. Docstrings.
* **`debate_core.arguments.landscape.side_role`**: its docstring names the second place the rule is
  applied.
* **Tests:**
  * new: `tests/arguments/landscape/test_analytic_texts_own_side.py`;
  * `tests/application/test_analytic_texts.py`: the own-side section at the seam.
* **The spec:** the Goal set to Succeeded.

## Deviations from the spec

1. **The count's script lives outside the repository**, in the session's scratchpad. The PM asked for counts
   only, and it is a one-off read. The operator ran it, read-only, over the dev data directory. It wrote
   nothing and printed counts only.
2. **A wrong run, stopped by its limit.** One closing test run meant for `test_landscape_report.py` started
   pytest with no paths: a zsh no-match error in a glob emptied the path list. So it began the whole default
   selection, which agreement 10 says a session never runs. `scripts/hard_stop.py` stopped it at 115 seconds,
   and no process outlived it. Its result is not counted anywhere. The file was then run by name (above).
3. **The affected set** (177 files) was stopped at 115 seconds and is left to the pull request's `ci`
   (agreement 10). The test directories of what changed, the suites that call the changed seam, the report's
   suite and the always-run list ran instead.

## Decisions and assumptions

1. **The rule sits after the cache, and the rules version is not bumped** (the PM's ruling 1). A reading is
   cached with the matcher's role under (source digest, parser version, rules digest). Its file's sides are
   not in that key, and the same file can later be disclosed on another side. A role decided by side would
   go stale in the cache, so the cache keeps the matcher's role, as t49's classification cache does. The
   readings already stored are correct, so nothing needs reading again.
2. **A CP text read by its place is left out, and not filed** (the PM's ruling 2, option (a)). Such a text is
   admitted only where the matcher's role is READS, and that check runs while the file is read. So the rule
   never adds an unlabelled CP text under an answer heading in a CP's own file. Extending it would need sides
   at read time: a new cache key and a full re-read of hspolicy26. The cache cannot count what that would
   add. The count shows **only 2 of 1,832 placed texts carry ANSWERS at all**. A `should` paragraph under an
   `AT:` heading in a CP's own file is more likely an answer to a permutation than the CP's text.
3. **A file's sides are its disclosing teams' sides in the run's reading.** These are the on-topic live
   disclosures through the snapshot, which `classify` gives `side_role` for cards
   (`[team.side.value for team in source.teams]`). So a file's cards and its analytic texts take the same
   side.
4. **Every placed reading goes through the rule, whatever its kind**: overviews, CP texts, planks,
   alternatives and roles of the ballot. One rule for every placement, as t49 applied it to sections too.
   The report then counts each as it already does: an overview on either side, a quoted kind only under a
   position of its kind.
5. **Only the role changes.** A reading keeps its place, digest and everything else, and an unplaced one is
   returned as it is; a test holds both. Unlike a card's result, a reading has no rationale to note the
   change in.

## Operator follow-ups

None. By the PM's ruling, hspolicy26 is republished when the next snapshot is published, not for this
change alone.

## Follow-up work

None. The CP text read by its place was ruled (a), not filed.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-07

**Notes:**

Small in effect (1 text on hspolicy26) and right in shape: one rule, applied where a reading meets its
file's sides, with the cache left holding what the matcher saw.

1. **ac1 passes.** The count was taken from the cache read-only and sent before any code. Red against
   a skeleton was 5 and 2 failures, each a role assertion, and the expected passes are explained.
   Green: 114 tests on the node's command.
2. **Mutants.** All ten are caught by assertions. The per-file seam case was added to catch the
   "every file's sides" mutant, and the helper-drops-unplaced mutant's IndexError was turned into a real
   assertion.
3. **Decisions accepted.** 1, no rules-version bump, because sides are not in the cache key and a file's
   side can change. 2, the CP text read by its place, ruled (a) with the count. 3, a file's sides are its
   disclosing teams' sides, the same as for its cards. 4, every placed kind goes through the one rule.
4. **Deviations accepted.** 1, the count's one-off script kept in the scratchpad, with counts only. 2,
   noted: a zsh glob that matched nothing emptied the path list and started the default selection, and
   `hard_stop.py` stopped it at 115 s. Check a path list is non-empty before running pytest on it. 3, the
   affected set is left to `ci`.
5. **No operator follow-up.** hspolicy26 is republished with the next snapshot, alongside
   `v1-e32-t57`'s republish.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

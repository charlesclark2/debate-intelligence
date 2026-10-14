# Session report: v1-e01-t24-partial-open-items-current-session

| | |
|---|---|
| Task | `v1-e01-t24-partial-open-items-current-session` — A partial merge's open items are read from the current session's sections |
| Spec | [`plan_specs/v1/e01-repo-foundation/t24-partial-open-items-current-session.yaml`](../../plan_specs/v1/e01-repo-foundation/t24-partial-open-items-current-session.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t24-partial-open-items-current-session` |
| Session status | COMPLETE |

## Summary

`scripts/task pr --partial` now reads the open-item markers (NOT RUN, NOT APPLICABLE, PARTIAL,
FAIL) only from the current session's part of the report. That part is found from the verdict
lines that `report_verdict` already reads:

* with one review or none, the whole report is current;
* with two or more, the current part starts at the first `## ` heading after the last-but-one
  `**Verdict:**` line and runs to the end.

`report_verdict` and the new `current_session` share one compiled pattern, so there is one
boundary, not two. Which verdict line is read is unchanged; t18's walk of 93 accepted reports still
passes.

Before the change, a resumed report whose earlier session said NOT RUN, and whose own sections
recorded nothing open, made `pr --partial` push and open a pull request. It is now refused. The
change also updates three documents:

* `docs/process/task-workflow.md` says which part of the report is read (ac3).
* The resumed-session prompt and the template tell a resumed session to restate its open items in
  its own sections.

**What the PM should look at first:**

* **Deviation 1:** v1-e30-t06 and v1-e30-t08 flip when the marker check is applied to the report
  alone. Both are `Succeeded`, so `--partial` never reads their markers. The brief said to stop on a
  flip. I stopped and asked, and the operator chose to go on with a walk that models the command,
  phase included.
* **The boundary, case by case:** one case lands on the less-right side. It is a `##` section the
  PM appends after an *earlier* review, which is t15's "Sandbox attempt" shape if t15 is ever
  resumed.
* **Follow-up work 1:** the template's own HTML comment satisfies the marker check. Five existing
  reports match it only there.

## Existing reports under the new boundary, measured before any change

Measured at the start commit `4dadf6a`, before any code changed, by a scratch script that applied
today's grep and the proposed boundary to every report in `docs/session-reports/`. The proposed
boundary: the current part starts at the first `## ` heading after the last-but-one `**Verdict:**`
line, found with `report_verdict`'s own pattern.

* 99 reports; today's grep (`NOT RUN\|NOT APPLICABLE\|PARTIAL\|FAIL`, whole file) matches 61.
* 5 reports have more than one line the verdict pattern matches, so the boundary applies to them.
  (The first draft of this section said 7; that count included two renamed labels, which the
  pattern does not match.)

  | Report | Verdict lines | Today's grep | Current part only |
  |---|---|---|---|
  | `v1-e01-t19-paste-safe-command-blocks` | 2 | no match | no match |
  | `v1-e30-t06-initial-backfill` | 2 | match | **no match** |
  | `v1-e30-t08-import-metadata-defects` | 3 | match | **no match** |
  | `v1-e31-t06-parse-pipeline` | 2 | match | match (FAIL, NOT RUN, PARTIAL) |
  | `v1-e31-t09-first-corpus-parse-findings` | 3 | match | match (FAIL, NOT RUN, PARTIAL) |

  v1-e03-t05 and v1-e31-t05 renamed their earlier verdict label, so the pattern sees one review in
  each, and the whole report is current, for the verdict and for this check alike.
* **Two reports flip on the marker check alone: v1-e30-t06 and v1-e30-t08.** Both are ac1's case
  on real data. Each ends with a closing section in which every criterion is PASS ("Acceptance
  criteria (final)"; "Operator results and close-out (2026-10-09)"). Today's grep matches them only
  through an earlier session's NOT RUN or PARTIAL. Both Goals are `Succeeded`, and both merged with a
  plain `scripts/task pr`.
* **Neither flips under `scripts/task pr --partial` as it runs.** The command reads the markers only
  when the spec's phase is not `Succeeded`. For a `Succeeded` task it takes the ordinary path, which
  reads no markers, before and after this change. The 8 InProgress tasks with an ACCEPTED report
  are the reports whose markers `--partial` actually reads. All 8 are still accepted:
  t15, t23, v1-e29-t08, v1-e31-t05, v1-e31-t11, v1-e31-t12, v1-e34-t17 and v1-e37-t05.

The brief said to stop if a report flipped. I stopped and asked the operator, who chose to proceed.
ac2's walk now models `pr --partial` as it runs, phase included. A second test pins the two
`Succeeded` reports as refused by the marker check alone. No report was edited. See Deviation 1.

## The boundary, case by case

`current_session` in `scripts/task_helper.py` defines it.

* **The reviews** are the lines `VERDICT_LINE` matches. `report_verdict` now uses the same compiled
  pattern, `` ^\*\*Verdict:\*\*[ \t]*`?([A-Z_]+)`? ``, unchanged from t18.
* **A review's section** ends at the next `## ` heading, the rule t18's `section()` uses.

| Case | Lines the verdict pattern matches | Current part | Pinned by |
|---|---|---|---|
| First session, one review | 1 | The whole report | `test_a_first_session_report_with_one_review_is_current_throughout`; through the script, `test_pr_partial_accepts_a_first_session_report_that_records_an_open_criterion` |
| The same, with a `###` record the PM adds under the review (t23) | 1 | The whole report, record included | The walk: t23 is InProgress and still accepted |
| The same, with a `##` section appended after the review (t15) | 1 | The whole report, section included | `test_a_section_the_pm_appends_after_the_only_review_is_current`; the walk (t15) |
| Resumed, before its own review is appended | 1 | The whole report | `test_a_resumed_report_before_its_own_review_is_appended_is_current_throughout` |
| Resumed, after its own review is appended (PENDING, CHANGES_REQUESTED or ACCEPTED) | 2 or more | From the resumed session's first `##` section to the end | `test_a_resumed_report_after_its_own_review_is_appended_starts_at_its_own_sections` × 3 |
| The earlier review's notes, and a `###` record under the earlier review | 2 or more | Not current | `test_the_earlier_reviews_notes_and_a_record_the_pm_adds_under_it_stay_with_that_review` |
| A record under, or a section after, the current review | 2 or more | Current | `test_a_record_the_pm_adds_under_the_current_review_is_current` |
| A `##` section after an earlier review (t15's, if t15 were resumed) | 2 or more | Current | `test_a_section_the_pm_appends_after_an_earlier_review_is_read_with_the_next_sessions` |
| An earlier review with a renamed label (v1-e03-t05, v1-e31-t05) | The renamed one is not matched | As if that review were absent | `test_an_earlier_review_whose_label_was_renamed_is_not_a_review_to_either_check`; the walk (v1-e31-t05) |
| Two reviews in one section (`### Second review`, the pre-t18 layout) | 2 | Empty: nothing counts as open | `test_two_reviews_with_no_section_between_them_leave_no_current_part` |

Why each case is on the side it is:

1. **One review: the whole report is current.** There is no earlier session. Anything the PM appends
   after the only review is the latest record of this session's criteria.
   * t15's "Sandbox attempt" records that ac5 is still NOT RUN after the review that authorised
     `--partial`.
   * t23's "### Operator follow-up 1, recorded" closes follow-up 1 and leaves follow-up 2 open.

   Both tasks are InProgress, and both are still accepted.
2. **Resumed, before its own review: the whole report is current.** With one review line, nothing
   tells this report apart from case 1. The verdict reads the earlier ACCEPTED in this state too. A
   different rule for the open items would be the second, slightly different boundary the brief ruled
   out, and the verdict would still be exposed. The workflow makes the empty review the resumed
   session's last step, and the resumed prompt says so. From then on the two checks move together.
3. **Resumed, after its own review: from the end of the earlier review.** The resumed session's
   sections, its review, and anything appended after that review are what this merge covers. The
   earlier review's notes stay behind, and they often restate the open items: the fixture's "ac2
   stays NOT RUN", and much of t15's review. Cutting at the verdict line instead would count them
   (mutant 3 below). Three or more reviews (v1-e30-t08, v1-e31-t09) work the same way, from the
   last-but-one.
4. **Records the PM adds.**
   * **Under or after the current review: current.** They record the criteria this merge leaves open.
   * **A `###` under an earlier review (t23's shape): not current.** It belongs to the earlier
     review's cycle, and the resumed session restates whatever is still open.
   * **A `##` after an earlier review (t15's shape, if t15 is resumed): current, which is the
     less-right side.** By its content it is history. But the resumed session's own sections are
     also `##` sections, and the boundary cannot tell who wrote one. Telling them apart would take
     either a heading heuristic or git history (the lines added since `origin/dev`), and git history
     is a different boundary from the verdict's.

     The cost runs one way only. A stale NOT RUN in such a section can satisfy the check for the
     resumed session, which is how today's script treats every resumed report. It never refuses a
     report that should pass. `task-workflow.md` says to put a record that belongs with the earlier
     review under it, as a `###` heading (Decision 3).
5. **A renamed label is not a review to either check.** The verdict pattern does not match it, so
   v1-e03-t05 and v1-e31-t05 read as one-review reports for the verdict and for the open items. Both
   stay accepted.
6. **Two reviews in one section leave an empty current part, and `--partial` refuses.** No `## `
   heading follows the earlier review before the later one, so nothing marks the current session's
   sections. Refusing is the safe direction. This is the layout from before t18, when a session's
   changes went above the review. Since t18 a later review is always a new `## PM review`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `current-session-open-items` (Open items from the current session only) | Done | The flip list was measured and committed before any code (`8e51df8`). The tests were committed and run against the start commit's scripts (`575c12b`). Then the implementation, docs, prompt and template (`7ca93a5`), and two tests added after the mutation run (`7f891fa`). |

## Acceptance criteria

Every test run used a fresh `HYPOTHESIS_STORAGE_DIRECTORY`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a resumed report whose earlier session recorded NOT RUN and whose current sections record nothing open is refused by `pr --partial`, shown failing first with a hand-written fixture | PASS | **Fixture:** `tests/scripts/fixtures/task_restart/resumed_nothing_open.md`, written by hand. Its first session has ac2 NOT RUN and status PARTIAL. The first review is ACCEPTED, with the note "ac2 stays NOT RUN". Under that review is `### Operator follow-up 1, recorded (PM, …)` reading FAIL. Then comes a resumed section with every criterion PASS, and a second review, ACCEPTED. **Before:** today's script pushed the branch and ran `gh pr create` (see "Shown failing first"). **After:** `test_pr_partial_refuses_a_resumed_report_whose_current_sections_record_nothing_open` passes. Exit 1, with `error: --partial needs the current session's sections of … to record which criteria are still open …`. No push and no `gh pr create`. |
| ac2: a first-session report and a resumed report with an open criterion in their current sections are accepted, and every existing report `--partial` accepts today is still accepted, by a test that walks them | PASS (see Deviation 1) | **Through the real script:** `test_pr_partial_accepts_a_resumed_report_whose_current_sections_record_an_open_criterion` (hand-written `resumed_still_open.md`, ac3 NOT RUN in the resumed section) and `test_pr_partial_accepts_a_first_session_report_that_records_an_open_criterion` (t18's `first_session_accepted.md`) each push and open the PR. Each marker counts alone: `test_each_open_item_marker_counts_in_the_current_sections` × 4. **The walk:** `test_an_existing_report_partial_accepts_is_still_accepted` × 98. That is every report `pr --partial` accepted before this change, computed with the old grep and the command's phase branch, both copied by hand. Each is still accepted with `open_items`. `test_the_walk_over_reports_partial_accepts_is_not_vacuous` requires at least 60 reports and at least 5 InProgress ones, t15 and t23 among them. `test_the_reports_the_marker_check_alone_now_refuses_are_all_of_succeeded_tasks` pins v1-e30-t06 and v1-e30-t08 among the reports the marker check alone now refuses, and requires every such report to belong to a `Succeeded` task. |
| ac3: `docs/process/task-workflow.md` says which part of the report the check reads | PASS | § "When a task is reviewed but not finished" has a new paragraph, "The open items are read from the current session's part of the report only", covering one review, two or more, records under and after a review, and a `##` section after an earlier one. § "Coming back to a partly merged task" says the open items go in the resumed session's own sections. |
| Node: Task tooling tests pass (`uv run pytest tests/scripts`) | PASS | `uv run pytest tests/scripts` → `888 passed in 35.38s` |
| The default selection, in four parts | PASS | Each part was one command, `uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`, with the load average checked first. Part 1 (load 9.01): `1714 passed in 53.86s`. Part 2 (load 16.29): `1725 passed, 1 xfailed in 40.32s`. Part 3 (load 15.33): `1728 passed, 1 skipped, 1 warning in 37.78s`; the warning is `pytest_socket` in `test_pytests_own_process_has_no_network_in_an_offline_check`, which provokes it on purpose. Part 4 (load 13.87): `1725 passed, 1 xfailed in 43.59s`. Total: 6,892 passed. |
| Static checks | PASS | `ruff format --check` → `660 files already formatted`. `ruff check` → `All checks passed!` `pyright` → `0 errors, 0 warnings`. Named directly, `pyright scripts/task_helper.py tests/scripts/test_task_restart.py` gives 2 errors, both in `task_helper.py` and both present at `4dadf6a` (t18's Follow-up 4). The test file has none. `lint-imports` → `12 kept, 0 broken`. `scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 248 shell code blocks in 116 Markdown files`. `scripts/check_links.py` → `OK: 1525 relative links and anchors in 214 Markdown files`. `shellcheck scripts/task` → clean. |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 348 files, 38 epics, 290 tasks, 20 releases`, after `set-phase … Succeeded`. |

### The property

`test_only_the_current_part_of_a_report_decides_whether_anything_is_open` builds a report of 1 to 4
review cycles. A cycle is a session's section, a review with notes, and optionally a `###` record
under the review and a `##` section after it. Each part records one of the four markers or none. The
expected open items come from the cycles, not from the text. With one cycle, they are every part's.
Otherwise they are the last cycle's, plus the `##` section after the last-but-one review.

`--hypothesis-show-statistics` on a fresh database gave 100 passing examples. Reviews per example:
7.48% one, 32.71% two, 28.04% three, 25.23% four. **17.76% had open items only before the
boundary**, the case today's grep accepts.

## Shown failing first

The tests were committed with `scripts/` identical to the start commit
(`git diff --quiet 4dadf6a -- scripts` → no difference) and run as
`uv run --frozen pytest tests/scripts/test_task_restart.py`, giving `22 failed, 99 passed in
13.73s`.

* 21 of the 22 are `AttributeError: module 'task_helper_under_test' has no attribute
  'open_items'` (or `current_session`). They show only that the functions are new.
* The red that matters is the shell test: `assert result.returncode != 0` →
  `AssertionError: assert 0 != 0`.

To show what today's script did, a scratch script built the test's throwaway repository and ran the
real `scripts/task` in it, with the stubbed `uv`, `gh` and `pbcopy`. It loaded
`tests/scripts/test_task_restart.py`, called the `repo` fixture's function, committed
`resumed_nothing_open.md` in the rebuilt worktree, and ran `pr --partial`. At the start commit's
scripts:

```text
$ scripts/task pr v1-e99-t01-partly-merged --partial   (resumed_nothing_open.md)
==> Quick checks (spec validation)
==> Pushing task/v1-e99-t01-partly-merged
==> Opening pull request into dev

After the PR is squash-merged into dev: scripts/task finish v1-e99-t01-partly-merged
warning: partial merge: v1-e99-t01-partly-merged stays InProgress; the report must name the criteria left open
exit: 0
pushed task branch to origin: True
stub log:
gh pr create --base dev --head task/v1-e99-t01-partly-merged --title v1-e99-t01-partly-merged: A task merged with --partial --body-file …/.task/pr-body.md
```

The same script at `7f891fa`:

```text
$ scripts/task pr v1-e99-t01-partly-merged --partial   (resumed_nothing_open.md)
warning: partial merge: v1-e99-t01-partly-merged stays InProgress; the report must name the criteria left open
error: --partial needs the current session's sections of docs/session-reports/v1-e99-t01-partly-merged.md to record which criteria are still open (NOT RUN, NOT APPLICABLE, PARTIAL or FAIL); an earlier session's, before the last-but-one PM review ends, do not count
exit: 1
pushed task branch to origin: False
stub log:
```

## Mutation testing

Method:

* Each mutant was applied to the committed source (`7ca93a5`; the re-runs used `7f891fa`). The
  runner first checked that the original text occurred exactly once.
* For each mutant, the whole of `tests/scripts/test_task_restart.py` ran on a new, empty
  `HYPOTHESIS_STORAGE_DIRECTORY`.
* The file was then restored with `git checkout --`, and `git status --porcelain` was checked empty
  before and after every mutant. The tree was clean after each batch.
* The shell tests copy `scripts/task` and `scripts/task_helper.py` from the worktree, so they ran the
  mutant.
* A mutant counts as caught only from pytest's `N failed` summary line. None errored before running.
* Times are the whole file's wall time. The batches ran at load averages of 14.23 and 9.31.

| Mutant | Result | Caught by |
|---|---|---|
| 1. Boundary: two reviews read whole (`len(reviews) < 3`) | CAUGHT, 9.3 s, 15 failed | The ac1 shell test, the property, the case tests |
| 2. Boundary at the last review instead of the last-but-one | CAUGHT, 10.2 s, 13 failed | The ac2 shell test, `test_pr_opens_once_the_current_review_is_accepted`, the property |
| 3. Cut at the earlier verdict line (its notes and `###` records counted) | CAUGHT, 9.2 s, 9 failed | The ac1 shell test, `…notes_and_a_record_the_pm_adds_under_it…`, the property |
| 4. A `###` heading ends the earlier review (`^##` for `^## `) | CAUGHT, 9.0 s, 9 failed | The ac1 shell test, the property |
| 5. No `## ` heading after the earlier review reads the whole report | **SURVIVED**, 9.0 s, then CAUGHT, 8.8 s, 1 failed | `test_two_reviews_with_no_section_between_them_leave_no_current_part`, added after this run (`7f891fa`) |
| 6. A second, looser verdict pattern (renamed labels count as reviews) | CAUGHT, 8.8 s, 2 failed, by the walk alone (v1-e31-t05); then 3 failed | `test_an_earlier_review_whose_label_was_renamed_is_not_a_review_to_either_check`, added so a fixture catches it too |
| 7. Markers: FAIL dropped | CAUGHT, 9.2 s, 3 failed | `test_each_open_item_marker…[FAIL]`, the property |
| 8. Markers: NOT APPLICABLE dropped | CAUGHT, 9.2 s, 2 failed | `test_each_open_item_marker…[NOT APPLICABLE]`, the property |
| 9. Markers matched case-insensitively | CAUGHT, 8.9 s, 9 failed | `test_the_markers_are_matched_in_upper_case_as_the_grep_matched_them`, and others |
| 10. `open-items` exits 0 when nothing is open | CAUGHT, 9.0 s, 1 failed | The ac1 shell test |
| 11. Shell: the refusal removed (`\|\| true`) | CAUGHT, 9.9 s, 1 failed | The ac1 shell test |

The old whole-file grep is not listed: it is the start commit's script, and "Shown failing first"
runs it.

## Files changed

* `scripts/task_helper.py`:
  * `VERDICT_LINE`, now used by `report_verdict` (same pattern, same line read);
  * `current_session`, `open_items`, and the `open-items <task>` subcommand (exit 1 when nothing is
    open);
  * a sentence in the resumed-session prompt.
* `scripts/task`: `cmd_pr --partial` calls `helper … open-items` instead of `grep`, and prints the
  markers it found; a line in the help text.
* `tests/scripts/test_task_restart.py`: the new section and its tests; one t18 test switched to a new
  fixture (Deviation 2); the module docstring.
* `tests/scripts/fixtures/task_restart/resumed_nothing_open.md` and `resumed_still_open.md`, both
  written by hand.
* `docs/process/task-workflow.md`: ac3's paragraph, and a clause in "Coming back to a partly merged
  task".
* `docs/process/session-report-template.md`: one sentence in the appended-review rule.
* `plan_specs/v1/e01-repo-foundation/t24-partial-open-items-current-session.yaml`: phase
  `Succeeded`.

## Deviations from the spec

1. **ac2's "every existing report that `--partial` accepts today" is walked as the command decides,
   phase included, not as the marker check alone.** Measured before any change (above), the marker
   check alone flips two reports from accepted to refused: v1-e30-t06 and v1-e30-t08.
   * **Both are ac1's case in real reports.** A closing section records every criterion PASS after
     an earlier session's NOT RUN or PARTIAL.
   * **Both tasks are `Succeeded`.** For a `Succeeded` phase, `pr --partial` takes the ordinary path
     and reads no markers, before and after this change. So the command accepts both, then and now.

   Read the second way, ac2 would contradict ac1 on these two reports: ac1 requires exactly this
   shape to be refused. The brief said to stop if a report flipped and to say so rather than edit
   it. I stopped and asked the operator, offering three options:
   * go on with the phase-aware walk;
   * stop with the report BLOCKED;
   * go on and mark ac2 FAIL as written.

   The operator chose the first. Neither report was edited. The PM may want ac2's wording to say
   "accepts" means the command's decision, or to rule otherwise.
2. **One t18 test now uses a different fixture.** `test_pr_opens_once_the_current_review_is_accepted`
   ran `pr --partial` on t18's `resumed_review_pending.md` with its last verdict set to ACCEPTED.
   That fixture's resumed section closes ac2 and records nothing open. The test passed only through
   the first session's NOT RUN, so it depended on the behaviour this task removes, and it failed
   once the check changed. It now uses `resumed_still_open.md`. Its assertions are unchanged: the PR
   opens, and its body quotes the last review, not the 2026-09-23 one. t18's fixture is not edited,
   and its other tests still use it.

## Decisions and assumptions

1. **The check moved from `grep` into the helper** (`open-items <task>`), because the boundary lives
   in Python with the verdict. The marker set and the match are what the grep did: four alternatives,
   case-sensitive substrings. So `FAILED` still counts as FAIL (Follow-up work 1). One platform
   detail goes away: the old `\|` alternation in a basic `grep` pattern is a GNU extension that macOS
   grep happens to accept.
2. **Where the earlier review ends.** It ends at the next `## ` heading, not at its verdict line, so
   that the earlier review's own notes stay with it. The PM's notes are where earlier open items are
   most often restated.
3. **`task-workflow.md` tells the PM how to keep a record with an earlier review**: under it, as a
   `###` heading, as v1-e01-t23's report does. That follows from the boundary rather than adding a
   rule, but it is guidance on the PM's practice, so the PM may prefer to word it differently.
4. **The resumed-session prompt and the template now say** that a criterion still open is marked
   again in the resumed session's own section. ac3 asked only for `task-workflow.md`. Without this, a
   resumed session following its prompt could end correctly and still be refused by `--partial`.
   Both files are in `constraints.packages` (`scripts`, `docs/process`). The `start` prompt is
   unchanged.
5. **`pr --partial` prints what it found**: `==> Open items recorded by the current session: NOT RUN`.
   That way the operator sees what the check accepted.
6. **A missing report** makes `open-items` exit 2 with `no session report at …`. That path is
   unreachable through `pr`, whose verdict check reads `MISSING` and refuses first, so it has no test.
7. **The new tests are a section of `test_task_restart.py`** rather than a new file, to share its
   throwaway-repository fixture. `tests/scripts` is not a package, so importing a fixture from one
   test module into another would load it twice.
8. **The walk reads each task's phase from the spec YAML itself**, not through the helper, and copies
   the old grep and `cmd_pr`'s phase branch by hand, so the expectation does not come from the code
   under test.

## Operator follow-ups

None. The full default selection ran here in four parts, each under a minute.

## Follow-up work

1. **The template's own comments satisfy the marker check.** A new report carries
   `<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->` and
   `<!-- COMPLETE / PARTIAL / BLOCKED -->`. A first-session report that leaves either comment in place
   passes `--partial`'s check whether or not it records anything open. Five existing reports match
   the markers only inside HTML comments: v1-e01-t05, v1-e03-t02, v1-e03-t03, v1-e31-t01 and
   v1-e34-t10, all `Succeeded`.

   Reading the markers outside HTML comments would close it, and so would reading them only from a
   criteria table's status cell. That would also end `FAILED` and `PARTIALLY` counting as markers.
   Either changes the marker match, which this task kept as it was. Belongs to E01 tooling; the PM
   decides.
2. **A `##` record the PM appends after an earlier review counts as current** (the boundary, case
   4). If the PM wants it on the other side, there are two ways: a convention the tooling can read,
   such as a fixed heading for PM records, or a boundary taken from git history. Neither is the
   verdict's boundary.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. I have amended ac2 in this branch to the reading the
operator chose: "accepts" is the command's decision, phase included.

**Deviation 1: stopping and asking was right, and so was the answer.** Read as the marker check
alone, ac2 would contradict ac1 on v1-e30-t06 and t08, which are ac1's own case in real reports.
Neither flips under `pr --partial` as it runs, because a `Succeeded` task never reaches the check.
Measuring the flip list and committing it before any code changed is what made the question
answerable in one exchange.

**The work itself:**

* **One boundary, not two.** `report_verdict` and `current_session` share one compiled pattern, as
  the brief asked, and t18's walk of 93 reports still passes.
* **The case table is the clearest statement of a rule in this repository.** Every case has a side
  and a reason, and the one on the less-right side (a `##` record after an earlier review) is named,
  costed in the safe direction, and given a convention.
* **The red evidence is the real script,** in a throwaway repository: today's `pr --partial` pushed
  and opened a pull request for the ac1 report; the new one refuses and pushes nothing.
* **The property** generated one to four review cycles, and 17.8% of its examples were the case
  today's grep accepts.
* **The mutation run:** 11 of 11 caught. Mutant 5 found the two-reviews-in-one-section case and got
  its test; mutant 6 made a fixture catch what only the walk caught.

**Rulings:**

* **Deviations 1 and 2:** accepted. ac2 amended.
* **Decisions 1 to 8:** accepted. Decision 3, keeping a record with an earlier review as a `###`
  heading under it, is how I will append records from now on. Decision 4, the prompt and template
  telling a resumed session to restate its open items, was needed for the change to work.

**Follow-up work:**

* **Your 1, the template's HTML comments satisfying the check:** a real gap, filed by the PM as an
  E01 tooling task **after the v1.0 tag**, so that it does not hold the release. Until then the PM's
  review of every partial merge is the backstop.
* **Your 2:** no task. The `###` convention covers it.

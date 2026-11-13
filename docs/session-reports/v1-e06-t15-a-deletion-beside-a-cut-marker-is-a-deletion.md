# Session report: v1-e06-t15-a-deletion-beside-a-cut-marker-is-a-deletion

| | |
|---|---|
| Task | `v1-e06-t15-a-deletion-beside-a-cut-marker-is-a-deletion` — A whole-word deletion right after a cut's marker is read as a deletion, not a manual edit |
| Spec | [`plan_specs/v1/e06-card-cutting/t15-a-deletion-beside-a-cut-marker-is-a-deletion.yaml`](../../plan_specs/v1/e06-card-cutting/t15-a-deletion-beside-a-cut-marker-is-a-deletion.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t15-a-deletion-beside-a-cut-marker-is-a-deletion` |
| Session status | COMPLETE |

## Summary

`verify`'s .docx body diff (`debate_core.evidence.docx_verify`) now treats the format profile's whole
omission marker, `" … "` with its spaces, as one unit of the Myers diff, in the body and in the card
alike. Its tokens are put back after the diff, and each hunk is then trimmed. The marker's spaces can
no longer be paired with the card's spaces either side of the word after a cut. That pairing was the
tied edit script that read a deleted word as the word before it moved across the marker. So a
whole-word deletion beside a cut is a deletion wherever it sits, and t07's reproduction ("biologists ")
is the deletion [121, 132). A changed or added word beside a cut is still MANUAL_EDIT. A manual edit
beside a cut also no longer counts the card's own marker in its body range. No existing test's
expectation changed: all 51 tests in `test_docx_verify.py` from before this task pass untouched. The
`v1-e06-t10` smoke check is in `tests/smoke/test_cut_smoke.py`. It passed on a stamped, installed
build of this branch, built offline. The PM may want to look first at the rule for which space a
deletion beside a marker includes (Decisions 2). Follow-up 1 is a separate false failure on an
*untouched* export that this session found and did not fix.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-deletion-beside-a-cut-marker-is-a-dele` (Marker-side deletions) | Done | 36 tests in the node's `-k marker` selection pass; red run, mutants and the alternatives the PM named are recorded below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: "Marker-side deletions tests pass" (`uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k marker`) | PASS | `scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k marker` → `36 passed in 2.66s`. The selection holds the 33 new `test_marker_*` cases and t07's three tests with "marker" in their names |
| ac1: a whole-word deletion immediately before or after an omission marker, and one word further on, is a deletion with its ranges, while a changed word beside a marker is still MANUAL_EDIT, by tests on synthetic exports shown failing first, with a mutant on the tie-break | PASS | Red runs, green run and mutants below. Tests use an invented four-piece source exported by ExportService and edited through python-docx, checking both `compare_body`'s ranges and `VerifyManifest`'s verdict |
| ac2: a smoke check on the installed build reports NEGATION_REMOVED as a warning with exit 0 on an exported .docx whose body deletes a negating word | PASS | `test_verify_warns_negation_removed_on_a_docx_whose_body_deletes_never_and_exits_0_offline`: on a stamped installed build of `9274f94` (0.0.1.dev915, built offline) → `3 passed in 6.61s` with `test_an_installed_build_carries_the_prompts…` (which takes its installed-build branch) and t07's verify check; on the checkout's script → `2 passed`. Against a mutant with `removed_negations` returning nothing → `AssertionError: assert [] == [('NEGATION_R...` at line 278 |

### ac1: red runs (tests before the fix)

* The first 33 new tests against the unchanged module: `-k marker -n 0` → `7 failed, 26 passed`.
  The failures: the deletion one word after cut 1, after cut 2 and after cut 3, the body with two
  deletions, t07's own "biologists " reproduction, the negation one word after cut 2, and
  `letters-altered-right-after-cut-1` (the old code put the card's marker into the manual edit's body
  range: [12, 16) for "A" at [15, 16)).
* After the marker split was added (Decisions 3), against the pre-task module (`git show a4a1d16:…`
  into place, then `git checkout HEAD --`) → `9 failed, 25 passed`. The two new failures are
  `a-word-added-right-after-cut-3` and `a-word-added-right-before-cut-2`, the card's marker inside the
  edit's range again.
* The two cases added after the mutants (a marker typed where nothing was cut, below), with the
  whole file, against the pre-task module → `10 failed, 77 passed`. The marker-first case fails on the
  old code too; the word-first case passes on it. That case pins a range that both versions get
  right; it is there for the mutant.
* Tests that pass on the old code, as the PM's list expects: deletions right before a cut, or right
  after one (the old code read "The " as "The" too), the first and last words of the body, the whole
  piece between two cuts, the negation right after cut 3, and most changed-word cases.

### ac1: green

`scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py -n 0`
→ `87 passed` (51 from before, 36 new). No Hypothesis test is in the file, so agreement 8's fresh database does
not apply to these runs.

### ac1: mutants (each over the whole file, 87 tests, restored from HEAD)

| Mutant | Result |
|---|---|
| The tie-break off: no marker units | caught, 6 failed: the three deletions one word after a cut, the two-deletion body, t07's reproduction, the negation one word after cut 2 |
| Units only on the body side | **survived** (equivalent, Decisions 4) |
| No trim after expanding the units | caught, 12 failed, among them t07's `typing_the_marker_in_their_place` (31, 61) and t10's `replaced-by-the-marker` |
| Trim on units before expanding | caught, 8 failed |
| No marker split off a manual edit | caught, 3 failed |
| Split only at a hunk's start | caught, 1 failed (`a-word-added-right-before-cut-2`) |
| Split only at a hunk's end | caught, 2 failed |
| Split a marker where nothing was cut, at the start | survived at first; caught (1 failed) after adding `a-marker-then-a-word-where-nothing-was-cut` |
| Split a marker where nothing was cut, at the end | survived at first; caught (1 failed) after adding `a-word-then-a-marker-where-nothing-was-cut` |

### Before the report

* Affected set: `scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` chose `122 of 754
  test files` and was stopped at its 115-second limit at 48%, with no failure in the 30 progress lines it
  printed. Per agreement 10 it is left to the pull request's `ci`, which runs the same set. Within the
  limit, instead:
  * the changed test directory, the cut smoke file and the always-run list
    (`packages/debate_core/tests/evidence tests/smoke/test_cut_smoke.py tests/architecture tests/specs`,
    `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, `-n auto -m "not slow and
    not live"`) → `2218 passed in 42.76s`;
  * every other test that reads the body diff (`test_verify_docx.py`, `test_verify_manifest.py`,
    `test_verify_command.py`, `test_cut_command.py`, `tests/cli/test_verify_cli.py`, the two e2e
    files, `tests/smoke/test_cli_smoke.py`) → `187 passed in 15.87s`.
* `uv run ruff format --check .` → `2089 files already formatted`; `uv run ruff check .` → `All checks
  passed!`
* `uv run --frozen pyright`, whole project as CI runs it → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → `OK: 74
  … handlers within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 676 files, 41 epics, 613 tasks, 22 releases`
* The spec against the local `origin/dev` ref (not fetched): it differs only in the phase.

## Files changed

* `packages/debate_core/src/debate_core/evidence/docx_verify.py`: marker units in the diff
  (`_units`, `_expanded`), the trim moved after expanding, the marker split off a manual edit
  (`_Classifier._without_the_cards_marker`), and a module docstring paragraph stating the rule.
* `packages/debate_core/tests/evidence/test_docx_verify.py`: the new `test_marker_*` section on an
  invented source. t10's helpers are generalized and renamed so both sections share them
  (`NegationExport` → `VerifiedExport`, `negation_verdict` → `docx_verdict`, a new
  `verified_export`), and t10's comment that put "have" before "never" to avoid the tie now says the
  tie is fixed. Its source is unchanged, as the PM allowed.
* `tests/smoke/test_cut_smoke.py`: the NEGATION_REMOVED smoke check.
* The task spec: the Goal's phase.

## Deviations from the spec

None. The marker split (Decisions 3) changes only the body range that a manual edit beside a cut
reports, never whether one is reported. It changed no existing test's expectation, so I did not stop
for the PM.

## Decisions and assumptions

1. **The fix: the whole marker is one unit of the diff.** Myers ties in the PM's case because the body's
   `␣ … ␣` can give up its spaces to match the card's spaces around "Conservation". The script that
   takes them deletes "Conservation", turns "biologists" into "…" and inserts "Conservation ␣":
   a word *moved* across the marker. As one unit the marker matches only a marker, so that script
   costs more and the only shortest script is "insert the marker, delete the word". It is done on both
   sides, so a source that prints " … " itself is tokenized the same way in the card and in the body
   (`test_marker_an_ellipsis_the_source_itself_prints_is_quoted_text`). Measured alternatives, each on
   the pre-task module against the final 87 tests:
   * **Merge only across removed whitespace** cannot work. The tied script inserts a word,
     "Conservation", so its hunk is a MANUAL_EDIT whatever is merged with it. Turning merging off
     entirely fails 21 tests, and merging only when both hunks only remove fails 20, among them
     t07's `deleting_a_whole_sentence` (3 cases), `typing_the_marker_in_their_place`,
     `words_replaced_by_an_interpolation` and `deleting_the_space_between_two_words`. The merge holds
     those together; it was never the cause.
   * **Prefer the marker's hunk by flipping Myers' tie toward insertions** (`<` to `<=` in the
     frontier test) fails 12 tests. It still misreads the word one further after each cut, and it newly
     misreads `right-before-cut-3-between-two-cuts` and `letters-altered-one-word-after-cut-1`: the
     tie moves rather than goes. A tie-break in Myers is a choice between scripts the algorithm happens
     to find first. The unit rule removes the tie.
2. **Which space a deletion beside a marker includes.** Where a space beside the marker can be the
   card's own space, it is read as the card's. Deleting "The " right after a cut leaves `. … levee`,
   whose one space after the marker stands for the card's space after "The", so the deletion is "The"
   [12, 15), not [12, 16). The same holds for t07's "Conservation " [108, 120). This is the rule t07
   and t10 already pin for a marker typed over words: (31, 61) for "failed … edited", and "not"
   (15, 18) for "… " typed over "not ". It keeps each deletion as small as the body allows. A deletion
   one word further on keeps its own space ("levee " [16, 22), as t07's "who " [132, 136)). Implemented
   by trimming the hunks after the units are expanded: the trim-on-units and no-trim mutants fail it.
   If the PM prefers [12, 16), the trim would stop at a marker's edge. That is a different rule, and
   t07's (31, 61) and t10's (15, 18) would change.
3. **A manual edit beside a cut does not claim the card's marker.** "The" changed to "A" right after
   cut 1 was ManualEdit(evidence [12, 15), body [12, 16)), the marker included. The marker is the
   renderer's at the card's own cut, so the edit is now body [15, 16). Only a hunk the policy already
   refuses is narrowed, and only by a whole marker at a cut offset. What is left still holds the word
   that made it refused, so this can change a range but never whether a MANUAL_EDIT is reported. A
   marker typed where nothing was cut stays in the edit's range (two cases pin it, at each end).
4. **An equivalent mutant kept.** Grouping the marker only in the body passes all 87 tests: an unmatched
   source `␣…␣` in the card becomes a hunk that removes it and adds the body's marker unit, and the
   trim cancels it to nothing. No input I could build tells the two apart. I kept the grouping on both
   sides anyway, so that one rule tokenizes both texts and an untouched source ellipsis is never a
   difference in the first place. The PM may rule it should go (agreement 8).
5. **Test fixture shape.** The invented card has three cuts at sentence ends, so its body shows three
   markers: a two-word first piece (the body's first word is one word before cut 1), a piece of three
   words between cuts 2 and 3, and a last piece that ends mid-sentence ("wall", the body's last word).
   This covers each position the PM listed: immediately before and after a marker, one word further
   on each side, beside two markers (and the whole piece between them deleted, which leaves the two
   markers together), and the very start and end of the body. Its omissions hold "nothing" and its
   pieces "never" and "Nobody", so the negation cases sit at the old bug's position and right after a
   cut. Every offset is counted by hand in the section's comment block.
6. **The smoke check deletes "never "**, away from the news card's cut. ac2 asks only that an installed
   build warns NEGATION_REMOVED and exits 0. The node's `-k marker` cannot select a smoke test (a
   different file), so ac2's command is its own:
   `uv run pytest tests/smoke/test_cut_smoke.py -k negation_removed`. It reads `warnings` with
   `.get`. The report leaves the key out when there are none, and a first mutant run failed as a
   KeyError instead of at the assertion.

## Operator follow-ups

None.

## Follow-up work

1. **An untouched export can be a MANUAL_EDIT when a cut joins two words with no space** (E06, the
   same module). `evidence_text` joins kept pieces with nothing, so a card whose kept range ends at a
   word and whose next one starts at a word has, for example, "holdflood" in its evidence. The body
   shows `hold … flood`. Reproduced with `VerificationWorld` on an invented source, ranges
   ((0, 23), (39, 45)) of "The levee will not hold another spring flood, engineers said." →
   ManualEdit(evidence [19, 28), body [19, 31)) on the untouched rendering; ranges ((0, 24), …), with
   the space kept, follow the policy. Every card in the existing fixtures is cut at a sentence end or
   keeps a space, so no test reaches it. A likely fix is to tokenize `evidence_text` with the card's
   omission offsets as token boundaries. Whether CardService's selections ever produce such a join is
   unmeasured. This task's fixture keeps its cuts at sentence ends to stay clear of it.
2. **A marker typed with other spacing** (`…` with one space, or a non-breaking space) is not the
   profile's whole marker, so it is still compared token by token, and the old tie can still occur
   beside it. A student who keeps the rendered marker, as every test here does, is covered.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted. ac1, ac2 and the node pass, and the Goal is `Succeeded`.

* **Decision 1, the fix, is better than either option the PM named,** and the report shows why with
  measurements, not argument.
  * Treating the profile's whole marker as one diff unit removes the tie rather than moving it.
  * Flipping Myers' tie failed 12 tests and moved the misreading.
  * Merging only across removed whitespace failed 20, because the tied script inserts a word.
  * t07's reproduction is now the deletion [121, 132).
* **No existing expectation changed:** all 51 earlier tests in the file pass untouched, so there was
  no reason to stop.
* **Decision 2 is accepted:** a space beside a marker is read as the card's own space. It is the rule
  t07's (31, 61) and t10's (15, 18) already pin, and it keeps each deletion as small as the body allows.
* **Decision 3 is accepted.** It narrows only the body range of a MANUAL_EDIT the policy already
  refuses, and only by the card's own marker at a cut offset. It never changes whether one is
  reported, and a marker typed where nothing was cut stays in the range, pinned at both ends.
* **Decision 4's equivalent mutant is accepted** as kept: one rule tokenizes both texts.
* **The evidence is enough.**
  * The red runs: 7, then 9, then 10 failed at their assertions.
  * The mutant table caught every non-equivalent mutant. The two that survived first got their tests,
    and the report says so.
  * ac2's smoke check failed against a mutant that returns no warning.
  * The smoke check ran against a build stamped from this branch and handed to the smoke harness, as
    validate-dev does. The PM takes that to be a scratch build, not a replacement of the operator's
    installed `debate-research`.
* **The affected set** goes to `ci` under agreement 10.
* **Follow-ups, into the next PM batch:**
  1. An untouched export reads as MANUAL_EDIT when a cut joins two words with no space ("holdflood").
     It is a false failure of the same kind, so it becomes a new E06 task at p2. It first measures
     whether CardService's selections ever produce such a join, then fixes the tokenization if they do.
  2. A marker typed with other spacing: a note on the same task. A student who keeps the rendered
     marker is covered.

`scripts/task pr`

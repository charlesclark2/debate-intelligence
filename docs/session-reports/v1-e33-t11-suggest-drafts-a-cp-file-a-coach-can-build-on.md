# Session report: v1-e33-t11-suggest-drafts-a-cp-file-a-coach-can-build-on

| | |
|---|---|
| Task | `v1-e33-t11-suggest-drafts-a-cp-file-a-coach-can-build-on` — files suggest drafts a CP file a coach can build on: a CP text slot first, no other position's blocks, and plank-dependent blocks marked |
| Spec | [`plan_specs/v1/e33-file-builder/t11-suggest-drafts-a-cp-file-a-coach-can-build-on.yaml`](../../plan_specs/v1/e33-file-builder/t11-suggest-drafts-a-cp-file-a-coach-can-build-on.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t11-suggest-drafts-a-cp-file-a-coach-can-build-on` |
| Session status | COMPLETE |

## Summary

`files suggest` now drafts a counterplan's file the way a CP file is built. A position whose taxonomy
kind is `PositionKind.CP` gets a draft whose first block opens with the analytic placeholder
`[the counterplan text: write it here]`. Blocks whose heading the position matcher places under
another position are left out with their cards, and the result counts them in one additive `--json`
key, `other_positions_left_out`, and in the table's caption. Blocks whose heading names a plank or
mechanism of the plan get a comment above them telling the coach to check them against the
affirmative's plan. Every other position's draft is byte for byte as before, pinned by a hand-written
expected text over the existing suggest fixture. Counted first on the Mac's hspolicy26 store: the
13 CP drafts (top 10) have 83 blocks, and 15 of them, holding 16 cards, are placed under other
positions. The plank rule marks 1 of the 68 kept blocks, and it does **not** catch the preemption or
waiver blocks the coach named. Look first at PM questions 1 and 2 below: question 2 is whether the
plank rule needs a coach-edited word list, and question 1 is whether an unreplaced placeholder should
warn.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `suggest-drafts-a-cp-file-a-coach-can-bui` (CP draft structure) | Done | Counts first, then tests red against a skeleton (`5462a36`), then the implementation (`aaa31d9`, `17ef4d6`, `04ae7a8`) and the guide (`72c7034`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a CP position's draft opens with a placeholder CP text slot | PASS | `test_a_counterplans_draft_opens_its_first_block_with_the_cp_text_slot`: first block `states cp`, first item `{"analytic": "[the counterplan text: write it here]"}`, then rank 1's card. `test_the_cp_text_slot_is_the_drafts_only_analytic_and_no_team_wrote_it`: the slot is the draft's only analytic, and no tag or cite of any planted card is in the text |
| ac1: holds no block another position's heading places | PASS | `test_a_block_another_positions_heading_places_is_left_out_with_its_cards`: blocks are `states cp`, `solvency`, `global budgets`, `plank 2 waivers`; the `t usfg` block's card (rank 3) is nowhere in the draft; `other_positions == OtherPositionsLeftOut(blocks=1, cards=1)`; `left_out == ()`. `test_a_block_whose_heading_places_nothing_stays_in_a_counterplans_draft`. `test_a_counterplan_whose_every_card_is_in_another_positions_block_is_refused` |
| ac1: marks the plank-dependent blocks it names with a comment | PASS | `test_blocks_naming_a_plank_or_mechanism_of_the_plan_are_marked_and_no_others`: the comment is directly above `global budgets` (an affirmative's tag keyword) and `plank 2 waivers` (a t16 plank label), above no other block, and appears twice. The rule and its counts are under "Counts on hspolicy26" |
| ac1: reports what it left out | PASS | The service result's `other_positions`, as above. `packages/debate_cli/tests/test_files_suggest_presenter.py`: `--json` carries `other_positions_left_out: {"blocks": 2, "cards": 3}` for a CP draft and `null` for any other; the caption says `2 block(s) holding 3 card(s)`, or `0 block(s) holding 0 card(s)` when nothing was left out, and says nothing of it for a non-CP draft |
| ac1: a non-CP draft is byte for byte as before | PASS | `test_a_draft_that_is_not_a_counterplans_is_byte_for_byte_as_before`: politics-da's whole draft, written by hand from the fixture's table and the t03 format, compared as bytes; it passed against the start commit's code as well (see "Red run"). `test_a_draft_of_a_position_that_is_not_a_counterplan_keeps_another_positions_block`: t-usfg's draft keeps its `states cp` block, with no slot and no comment |
| ac1: tests shown failing first | PASS | See "Red run" |
| Node: `uv run pytest packages/debate_core/tests -k suggest` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k suggest -q` (the same pytest without uv's sync, under the time limit): `56 passed in 14.42s` on the final code |

The placeholder builds as written: `test_a_ready_recipe_still_holding_the_cp_text_slot_builds_the_placeholder_as_written`
(in `test_file_build_service.py`) builds a `ready` recipe whose block opens with the slot and finds
the slot's text as the paragraph after the block heading in the `.docx`, with the quality report
`PASS`: nothing refuses or warns about it today; see PM question 1.

## Counts on hspolicy26

Read-only, counts only, no heading text. **Method:** through the pure functions, not a scratch copy:
a dry `LandscapeRunService` wired by hand over `~/.debate-research/dev` with no plan-text and no
analytic-text service (so neither cache is written), `top_cards=10`, then the suggest service's own
grouping (`_ranked`) and, for the second run, its own `_without_other_positions` and
`_naming_the_plan`. Snapshot through 2026-10-20 (the store's newest weekly), taxonomy 1.4.0. Each run
took 52 to 61 s. Before each I touched a marker file. After each,
`find ~/.debate-research/dev -newer <marker> | wc -l` printed `0`, blobs included.

| | Blocks | Cards |
|---|---|---|
| CP drafts with a card (13 CP positions) | 83 | 127 |
| Placed under another position, left out | 15 | 16 |
| ...by a T | 6 | 6 |
| ...by an advantage | 5 | 6 |
| ...by a DA | 3 | 3 |
| ...by another CP | 1 | 1 |
| Placing this CP | 9 | |
| Placing nothing | 59 | |
| Kept (this CP or nothing) | 68 | |

Of the 68 kept blocks, the candidate plank rules mark:

| Candidate rule | Blocks marked |
|---|---|
| (a) The topic config's plank words: there is no plank-word list in `config/landscape`. The nearest are the taxonomy's 24 affirmatives (`kind: aff`, each "one plan, named by its mechanism"); their aliases and tag keywords give 49 phrases, matched as whole words | 1 |
| (a2) The plan-text config's `frame_words` and `resolutional_words`, any one word | 1 (rejected: these are words every plan text holds, such as "states", so they say nothing about a plank) |
| (b) Headings `v1-e32-t16` reads as planks: a heading that opens with its plank label (`plank_words(heading) != heading`) | 0 |
| (a) and (b) together | 0 overlap, so 1 |
| Probe: a heading containing "preempt" (the PM's example) | 1, in the states-cp draft, marked by neither rule |
| Probe: a heading containing "waiver" (the PM's example) | 1, in the states-cp draft, marked by neither rule |

**Chosen rule:** (a) or (b). A kept block in a CP draft is marked when its heading holds an active
affirmative's alias or tag keyword as whole words, or opens with a t16 plank label. Both checks are
cheap and neither guesses. On hspolicy26 they mark 1 block, and they miss the two the coach named
(PM question 2).

## Red run

The skeleton (`5462a36`) adds `CP_TEXT_SLOT`, `CHECK_AGAINST_THE_PLAN`, `OtherPositionsLeftOut` and
`SuggestResult.other_positions` (always None), with no change to any draft. Against it:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly -q -rA --tb=no packages/debate_core/tests/application/test_file_suggest_service.py packages/debate_cli/tests/test_files_suggest_presenter.py "packages/debate_core/tests/application/test_file_build_service.py::test_a_ready_recipe_still_holding_the_cp_text_slot_builds_the_placeholder_as_written"`
→ `8 failed, 24 passed`. Failing, each at an assertion (a wrong block list, a missing slot, `DID NOT
RAISE`, a missing key, a caption without the counts):

* `test_a_counterplans_draft_opens_its_first_block_with_the_cp_text_slot`
* `test_the_cp_text_slot_is_the_drafts_only_analytic_and_no_team_wrote_it`
* `test_a_block_another_positions_heading_places_is_left_out_with_its_cards`
* `test_blocks_naming_a_plank_or_mechanism_of_the_plan_are_marked_and_no_others`
* `test_a_counterplan_whose_every_card_is_in_another_positions_block_is_refused`
* the three tests of `test_files_suggest_presenter.py`

Passing at red, as intended, because they pin behaviour that must not change or already exists:
the byte-for-byte test, the places-nothing test, the CP draft validating, t-usfg keeping its block,
and the placeholder building as written.

## Mutants

Each mutant applied to `file_suggest_service.py` alone, then
`packages/debate_core/tests/application/test_file_suggest_service.py` and
`packages/debate_cli/tests/test_files_suggest_presenter.py` were run (`-n 0 -p no:randomly`, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` each, though no test here uses Hypothesis), and the file was restored.
The code is final (`17ef4d6`'s placement).

| Mutant | Result | Caught by |
|---|---|---|
| 1. The CP slot missing (`if counterplan and first` → `if False and first`) | 2 failed | the slot test, the only-analytic test |
| 2. A T-like block kept (no block counted as another position's) | 3 failed | the left-out test, the marking test (block list), the all-left-out refusal |
| 3. A heading that places nothing dropped (`not in (None, id)` → `!= id`) | 3 failed | the left-out test, the places-nothing test, the marking test |
| 4a. A non-CP draft changed (every position read as a CP) | 7 failed | the byte-for-byte test and t-usfg's test, at assertions; five t03 tests fail too, with a `KeyError` on the slot item, which I do not count |
| 4b. A non-CP draft changed (the slot in every draft) | 7 failed | the same two at assertions |
| 5. The plan-dependent comment missing (`if block in marked` → `if False`) | 1 failed | the marking test |
| 6. The plank-label half of the rule off | 1 failed | the marking test |
| 7. The affirmative-words half of the rule off | 1 failed | the marking test |

## Files changed

* `packages/debate_core/src/debate_core/application/file_suggest_service.py`: the CP draft. It
  places a block heading through `PositionMatcher.place` on a section under that heading alone (the
  overrides and aliases, with no tag). It also holds the plank rule, the slot and the comment
  constants, and `OtherPositionsLeftOut`.
* `packages/debate_core/src/debate_core/application/landscape_run.py`: `LandscapeRunResult.overrides`,
  the overrides the report placed under, beside `taxonomy`, so suggest places a heading exactly as the
  run did. It is additive, with a default of None.
* `packages/debate_cli/src/debate_cli/presenters/files_presenter.py`: the `other_positions_left_out`
  key and the caption sentence.
* Tests: `test_file_suggest_service.py` (a CP world: seven synthetic teams, invented names; `plant`
  takes a heading path and a taxonomy), `test_file_build_service.py` (the slot builds as written),
  `packages/debate_cli/tests/test_files_suggest_presenter.py` (new).
* `docs/guides/file-recipes.md`: "Drafting a counterplan file".

## Deviations from the spec

1. **No smoke check change.** Working agreement 5 asks a task that changes a user-facing surface to
   update its smoke checks, but `tests/smoke` is not in this task's `constraints.packages` and the
   plan has no smoke node. The change to the command's output is one additive `--json` key.
   `tests/smoke/test_files_cli.py` still runs `files suggest` for politics-da, which is not a CP, so
   its draft is unchanged. A smoke assertion that a CP draft opens with the slot would need a CP in
   `tests/fixtures/file_builder/example_corpus.py`, also outside the packages. Follow-up 2 below.
2. **The node's command ran as `.venv/bin/python -m pytest` under `scripts/hard_stop.py 115`**, not
   `uv run pytest`: the same pytest and selection without uv's sync, as the session brief requires
   for every test run.

## Decisions and assumptions

* **The placeholder** is the spec's form, `[the counterplan text: write it here]` (the PM's brief had
  `[Counterplan text: ...]` as an example). A YAML comment above it says to replace it with the text
  the team reads. Nothing in it comes from a team's file or from the landscape's quoted CP texts.
* **"Another position"** is any position id other than the CP's own, whatever its role. A child CP's
  heading would count as another position. No CP in the hspolicy26 taxonomy has a child, so this
  changes nothing today.
* **Placing a heading:** I first added a `heading_position` method to `PositionMatcher`. That one
  edit put 144 more test files into the affected set, because `debate_cli.exit_codes` reaches the
  matcher. So the service calls the matcher's own `place()` instead, on a section item whose only
  heading is the block heading. That is the same override-then-alias reading with no tag, and the
  matcher is unchanged (`17ef4d6`). The affected set went from 237 files to 104.
* **Left-out cards are not replaced** by the next-ranked card, so a CP draft can hold fewer cards than
  `--top`. The header comment counts the cards the draft holds. If every card is left out, the
  command refuses (exit 2, the existing `SuggestRefused`) rather than writing a draft that holds
  only the slot.
* **The `--json` key is always present:** null for a non-CP draft, which means the rule was not
  applied, and `{"blocks": n, "cards": n}` for a CP draft, with zeros when nothing was left out.
* **The plank rule applies only to kept blocks of a CP draft.** A heading equal to an affirmative's
  alias would be placed under that affirmative and left out, so in practice (a) marks headings that
  *contain* an alias, or hold a tag keyword.

## PM questions

Paste-ready for the PM:

```text
v1-e33-t11 (files suggest CP drafts), three questions from the session, 2026-10-31.

1. Should anything warn about an unreplaced CP text slot?
   Today `files build` on a ready recipe still holding "[the counterplan text: write it here]"
   builds it as written and its quality report is PASS, with no warning (tested).
   Options: (A) nothing, as now; (B) a WARN in the file quality checks (files build's report and
   files check), naming the block, so publish still goes ahead; (C) a FAIL, so `files publish`
   refuses the file until the coach writes the text.
   Recommendation: B, filed after v1-e33-t12 merges (it is changing files check's warnings). A
   file with the placeholder is unusable in a round, but a coach may build one to look at it.

2. The plank rule misses the coach's examples.
   On hspolicy26 (top 10, 13 CP drafts, 68 kept blocks): the affirmatives' aliases/tag keywords
   mark 1 block, t16's plank labels 0. The states-cp draft has one block whose heading contains
   "preempt" and one containing "waiver": neither rule marks them. There is no plank-word list
   in the topic config.
   Options: (A) keep the rule as built; (B) a follow-up task adds a coach-edited list of plan
   mechanism words to the topic config (config/landscape, outside this task's packages), seeded
   by the coach, and the rule reads it too; (C) mark every kept block whose heading places
   nothing (59 of 68: too many to mean anything).
   Recommendation: B. The rule's function already takes a word set; the list is a config file
   and a loader.

3. Blocks placed under an advantage.
   Of the 15 blocks left out on hspolicy26, 5 (6 cards) are placed under an advantage (T 6, DA 3,
   CP 1). In a CP file a block under an advantage's heading can be the CP's solvency for that
   advantage, which the coach may want.
   Options: (A) leave them out, as the spec says (built); (B) keep blocks placed under an
   affirmative-side position (aff or advantage) and mark them with the check-against-the-plan
   comment instead.
   Recommendation: B is worth asking the coach about; A is what is built.
```

## Operator follow-ups

None. `uv run scripts/affected_tests.py --run` selected 104 of 604 test files, and its run reached
62% with no failure before `scripts/hard_stop.py` stopped it at 115 s (load average 9 to 15 from
other work on the Mac). Per agreement 10 I am leaving the whole affected set to the pull request's
`ci` check, with no operator hand-off. Within the limit I ran the test files of what changed plus the
always-run list:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_core/tests/application/test_file_suggest_service.py packages/debate_core/tests/application/test_file_build_service.py packages/debate_core/tests/application/test_file_recipes.py packages/debate_core/tests/application/test_file_recipes_attributed_and_held.py packages/debate_core/tests/application/test_landscape_run.py packages/debate_core/tests/application/test_landscape_dry_run_text_caches.py packages/debate_cli/tests/commands/test_files.py packages/debate_cli/tests/test_files_suggest_presenter.py tests/docs/test_check_links.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`
→ `710 passed in 23.15s`.

Whole-repo checks, on the final code: `ruff format --check .` (1682 files already formatted),
`ruff check .` (All checks passed), `pyright packages/debate_core packages/debate_cli` (0 errors),
`lint-imports` (19 kept, 0 broken), `scripts/check_thin_handlers.py` (68 handlers within 25
statements), `scripts/check_command_blocks.py` (OK), `uv run scripts/validate_specs.py` (OK: 537
files).

## Follow-up work

1. PM question 2's word list, if B: config/landscape plus its loader (an E32 or E33 task).
2. A smoke check for a CP draft: a CP in `tests/fixtures/file_builder/example_corpus.py` and an
   assertion in `tests/smoke/test_files_cli.py` that the draft opens with the slot (E33).
3. PM question 1's WARN, if B, after `v1-e33-t12` (E33).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

A CP draft now opens where a CP file opens and drops the other positions' blocks. And the count is
honest about what the plank rule cannot see.
1. **ac1 passes.**
   * Red against a skeleton: 8 failed at assertions. The guards that must not change passed at red:
     the byte-for-byte non-CP draft, places-nothing, t-usfg keeping its block, and the slot building
     as written.
   * Seven mutants were caught. 4a's `KeyError`s were rightly not counted, since the two
     assertion-level catches carry it.
   * The node criterion passes (56).
2. **The count is the standard the gate asked for.**
   * It went through the pure functions with neither cache wired. `find -newer` printed 0 after each
     run, so nothing was written to the dev data directory.
   * Counts only, no heading text.
   * 15 of 83 blocks (16 cards) are placed elsewhere, broken down by kind. The plank rule's candidates
     were each measured before one was chosen.
   * The probes show plainly that the rule misses the coach's two examples. Saying so is worth more
     than a rule tuned to pass.
3. **Decisions accepted:**
   * the spec's placeholder;
   * "another position" meaning any id but the CP's own;
   * placing a heading through the matcher's own `place()`, which keeps the matcher unchanged and
     takes the affected set from 237 to 104 files;
   * left-out cards not backfilled;
   * refusing a draft that would hold only the slot;
   * the `--json` key null for a non-CP draft;
   * `LandscapeRunResult.overrides` as an additive field.
4. **Deviation 1 (no smoke change):** accepted, since `tests/smoke` and the example corpus are outside
   the packages. It joins question 1's task below. **Deviation 2:** the brief's own form, accepted.
5. **PM questions:**
   * **Q1: B.** A WARN in the quality checks for an unreplaced CP text slot, naming the block. Publish
     still goes ahead. One p3 E33 task after v1-e33-t12, which is changing files check's warnings. It
     also takes Follow-up 2: a CP in the example corpus, and a smoke assertion that its draft opens
     with the slot.
   * **Q2: B.** A coach-edited list of plan-mechanism words in the topic config, which the rule also
     reads. One p3 task (config/landscape and its loader). The coach seeds it; preempt and waiver are
     the first two.
   * **Q3:** put to the coach. A (as built) stands until he answers. If he chooses B (keep
     advantage-placed blocks, marked), it is a small follow-up on this service.
6. **Closing checks:** the affected set (104 files) reached 62% at its limit with nothing failing,
   and is left to the PR's `ci` under agreement 10. The changed areas and the always-run list (710),
   ruff, pyright, lint-imports, thin handlers, the command blocks and the specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. v1-e32-t35 is running in the landscape. If
   `landscape_run.py` conflicts with it, whichever merges second rebases.

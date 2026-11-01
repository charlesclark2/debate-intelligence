# Session report: v1-e33-t13-cp-draft-keeps-aff-side-blocks-marked

| | |
|---|---|
| Task | `v1-e33-t13-cp-draft-keeps-aff-side-blocks-marked` — A CP draft keeps a block an affirmative-side position places, marked to check against the plan |
| Spec | [`plan_specs/v1/e33-file-builder/t13-cp-draft-keeps-aff-side-blocks-marked.yaml`](../../plan_specs/v1/e33-file-builder/t13-cp-draft-keeps-aff-side-blocks-marked.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t13-cp-draft-keeps-aff-side-blocks-marked` |
| Session status | COMPLETE |

## Summary

A counterplan's draft (`files suggest` for a position of kind `PositionKind.CP`) now keeps a block
whose heading the position matcher places under an `aff` or an `advantage`. The block gets t11's
`CHECK_AGAINST_THE_PLAN` comment directly above it, keeps its cards in rank order, and stays where
t11's ordering puts it (by its most-read card). A block placed under any other kind is still left out
as t11 built it: `da`, another `cp`, `k`, `t`, `theory`, and LD's and PF's `value`, `criterion`,
`contention` and `response`. `other_positions_left_out` now counts only what is still left out. A new
additive count, `affirmative_side_kept` (blocks and cards), is in the result, the caption and
`--json`, and is null for a non-CP draft. On hspolicy26 (top 10, 13 CP drafts) the left-out blocks go
from 15 (16 cards) to 10 (10 cards). All 5 advantage-placed blocks (6 cards) are now kept and marked,
and no block was placed under an aff. Marked blocks go from 1 to 6. Look first at Decision 3: the
comment's wording ("its heading names a plank or mechanism of a plan") is t11's, as the brief asked,
but it is not quite true of an advantage block.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cp-draft-keeps-aff-side-blocks-marked` (Aff-side blocks kept) | Done | Counted before on the start code, then tests red against a skeleton (`bbb393a`), then the implementation, presenter and guide (`5082381`), then mutants and the after count |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: in a CP draft, a block an aff or advantage places is kept with the check-against-the-plan comment | PASS | `test_a_block_an_advantage_or_an_aff_places_is_kept_in_rank_order_and_others_are_left_out`: blocks are `states cp` (slot, fiat), `cost advantage` (costs rank 2, premiums rank 5), `federal payer` (payer, rank 4), `solvency`. `test_each_kept_affirmative_side_block_has_the_check_against_the_plan_comment_directly_above_it`: the comment is the line directly above `cost advantage` (an advantage, by alias) and `federal payer` (the aff, by a coach's override, so t11's plank rule cannot mark it), above neither other block, and appears exactly twice |
| ac1: a block any other kind places is still left out | PASS | Same first test: the cards of `t usfg` (T), `politics da` (DA) and `consult cp` (another CP) are nowhere in the draft; `left_out == ()`. t11's own left-out, refusal and marking tests pass unchanged |
| ac1: the counts say which | PASS | `test_the_counts_say_what_was_left_out_and_what_was_kept_as_affirmative_side`: `other_positions == OtherPositionsLeftOut(blocks=3, cards=3)`, `affirmative_side_kept == AffirmativeSideKept(blocks=2, cards=3)`. `test_a_counterplans_draft_with_no_affirmative_side_block_counts_none_kept`: t11's world gives `(1, 1)` and `(0, 0)`. `test_files_suggest_presenter.py`: `--json` carries `affirmative_side_kept: {"blocks": 2, "cards": 5}` beside `other_positions_left_out`, and the caption says `2 block(s) holding 5 card(s) kept under an aff's or advantage's heading`, or `0 block(s) holding 0 card(s) ...`; for a non-CP draft the key is present and null and the caption says nothing of it |
| ac1: a non-CP draft is byte for byte as before | PASS | t11's hand-written `test_a_draft_that_is_not_a_counterplans_is_byte_for_byte_as_before` passes unchanged (not edited). New: `test_a_draft_that_is_not_a_counterplans_keeps_an_advantages_block_unmarked_as_before`: politics-da's draft in the new world holds `politics da` and `cost advantage` (an advantage's block), with no slot and no comment, and `other_positions` and `affirmative_side_kept` are both None |
| ac1: hspolicy26 counts before and after | PASS | See "Counts on hspolicy26" |
| ac1: tests shown failing first | PASS | See "Red run" |
| Node: `uv run pytest packages/debate_core/tests -k suggest` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k suggest -q` (the same pytest without uv's sync, under the time limit) → `62 passed in 18.26s` |

## Counts on hspolicy26

Read-only, counts only, no heading text. **Method:** exactly as t11 counted. A dry `LandscapeRunService`
wired by hand over `~/.debate-research/dev` with no plan-text and no analytic-text service (so neither
cache is written), `top_cards=10`, then the suggest service's own `_ranked`, `_without_other_positions`
and `_naming_the_plan`, plus, after, `_affirmative_side_kept`. **Before** ran on the start commit's
code (`ebbb58e`) and **after** on the final code. Both were through 2026-10-20 (the store's newest
weekly), taxonomy 1.4.0. Runs took 57.3 s (before) and 52.1 and 54.6 s (after, run twice: the second
added the block positions). Before each run I touched a marker file. After each,
`find ~/.debate-research/dev -newer <marker> | wc -l` printed `0`.

Like t11's, these counts come before the pins are resolved. No card was refused at resolution in t11's
run, and the result's `affirmative_side_kept` counts the draft as written (after resolution).

| | Before (t11) | After (t13) |
|---|---|---|
| CP drafts with a card | 13 | 13 |
| Blocks / cards in them | 83 / 127 | 83 / 127 |
| Placed under another position | 15 blocks, 16 cards | 15 blocks, 16 cards |
| ...by a T | 6 blocks, 6 cards: left out | 6, 6: left out |
| ...by a DA | 3, 3: left out | 3, 3: left out |
| ...by another CP | 1, 1: left out | 1, 1: left out |
| ...by an advantage | 5, 6: left out | 5, 6: **kept, marked** |
| ...by an aff | 0 | 0 |
| ...by a K, a theory argument or any other kind | 0 | 0 |
| **Left out** (`other_positions_left_out`) | **15 blocks, 16 cards** | **10 blocks, 10 cards** |
| **Aff-side kept and marked** (`affirmative_side_kept`) | (none: not kept) | **5 blocks, 6 cards** |
| Kept blocks / cards | 68 / 111 | 73 / 117 |
| Marked by t11's plank rule | 1 | 1 |
| Marked by both rules | | 0 |
| **Total marked blocks** (the comment) | **1** | **6** |

Where the 5 kept advantage blocks fall in their drafts (block position in file order): 2 of 7, 4 of 7,
5 of 7, 4 of 6, and 6 of 6 (the last block). None is a draft's first block, so none holds the CP text
slot. The taxonomy has 16 advantages, 24 affs, 14 CPs, 20 DAs, 14 Ks, 8 Ts and 7 theory positions.

The count script is in the session scratchpad:
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e33-t13-cp-draft-keeps-aff-side-blocks-marked/ccfc4327-01c9-4eee-80f6-c21372df7c0c/scratchpad/counts/cp_draft_counts.py`
(run as `... cp_draft_counts.py config/landscape <scratch> before|after`).

## Red run

The skeleton (`bbb393a`) adds `AffirmativeSideKept` and `SuggestResult.affirmative_side_kept` (always
None), with no change to any draft and no presenter change. Against it:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly -q -rA --tb=line packages/debate_core/tests/application/test_file_suggest_service.py packages/debate_cli/tests/test_files_suggest_presenter.py`
→ `7 failed, 33 passed`. Each failed at an assertion. A first version of three tests failed with a
`KeyError` instead; I changed them to check the block list or the key's presence first, so they fail at
an assertion, and that is the run quoted. Failing:

* `test_a_block_an_advantage_or_an_aff_places_is_kept_in_rank_order_and_others_are_left_out` (a block list without `cost advantage` and `federal payer`)
* `test_each_kept_affirmative_side_block_has_the_check_against_the_plan_comment_directly_above_it`
* `test_the_counts_say_what_was_left_out_and_what_was_kept_as_affirmative_side`: the skeleton counted `OtherPositionsLeftOut(blocks=5, cards=6)`, which is every block the new world plants under another position, so the world is built as its docstring says
* `test_a_counterplans_draft_with_no_affirmative_side_block_counts_none_kept`
* the three new tests of `test_files_suggest_presenter.py`

These passed at red, as intended, because they pin behaviour that must not change: t11's
byte-for-byte test and all of t11's CP tests, the new non-CP test
(`..._keeps_an_advantages_block_unmarked_as_before`), and the new world's draft validating.

## Mutants

Each mutant was applied to one file alone. Then `test_file_suggest_service.py` and
`test_files_suggest_presenter.py` were run with `-n 0 -p no:randomly` and a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` each (no test here uses Hypothesis), and the file was restored.
`git status` was clean afterwards. This is the final code (`5082381`). All 13 were caught, every one at
an assertion.

| Mutant (the brief's numbering) | Result | Caught by |
|---|---|---|
| 1a. An advantage block still left out (`_AFFIRMATIVE_SIDE_KINDS` without `ADVANTAGE`) | 3 failed | the kept/left-out test, the comment test, the counts test |
| 1b. An aff block still left out (without `AFF`) | 3 failed | the same three |
| 2a. A T block kept (`T` added to the kinds) | 7 failed | the same three, plus four of t11's (left-out, marking, refusal `DID NOT RAISE`, and the zero-kept count) |
| 2b. A DA block kept | 3 failed | the kept/left-out test, the comment test, the counts test |
| 2c. Another CP's block kept | 3 failed | the same three |
| 3. A kept aff-side block without the comment (`marked` from the plank rule only) | 1 failed | the comment test (the override-placed `federal payer` block) |
| 4a. The left-out block count still including the kept blocks | 1 failed | the counts test |
| 4b. The left-out card count still including the kept cards | 1 failed | the counts test |
| 5a. A non-CP draft changed: aff-side blocks marked in every draft | 1 failed | the new non-CP test (politics-da's `cost advantage` block) |
| 5b. A non-CP draft changed: the CP block rules in every draft | 3 failed | t11's byte-for-byte test, t11's t-usfg test, the new non-CP test |
| 5c. A non-CP draft's `affirmative_side_kept` zero instead of null | 1 failed | the new non-CP test |
| 6a. The caption silent on what was kept (presenter) | 1 failed | the caption test |
| 6b. The `--json` key with blocks and cards swapped (presenter) | 1 failed | the `--json` test |

## Files changed

* `packages/debate_core/src/debate_core/application/file_suggest_service.py`: the rule.
  `_AFFIRMATIVE_SIDE_KINDS` (`aff`, `advantage`). `_without_other_positions` now looks up the kind of
  the position each block's heading places and returns the kept aff-side headings beside what it left
  out. `_affirmative_side_kept` counts them in the draft as written. `AffirmativeSideKept` and
  `SuggestResult.affirmative_side_kept` are additive, with a default of None. The module docstring
  says which kinds are kept and which are left out.
* `packages/debate_cli/src/debate_cli/presenters/files_presenter.py`: the `affirmative_side_kept`
  `--json` key and the caption sentence.
* Tests: `test_file_suggest_service.py` gets a new section with a "sides world" of ten synthetic teams
  (invented school names and codes), a taxonomy with an aff, an advantage, a T, a DA and a second CP,
  and one coach's override. A table in its docstring, written by hand, gives each card's copies and
  block. Six new cards were added to `CARDS`. `test_files_suggest_presenter.py` gets three tests.
* `docs/guides/file-recipes.md`: one sentence in "Drafting a counterplan file".
* The spec's Goal phase, set to Succeeded.

## Deviations from the spec

1. **The node's command ran as `.venv/bin/python -m pytest` under `scripts/hard_stop.py 115`**, not
   `uv run pytest`. It is the same pytest and selection without uv's sync, as the session brief
   requires for every test run.
2. **No smoke check change**, as in t11. The change to the command's output is one additive `--json`
   key. `tests/smoke` is outside this task's packages, and v1-e33-t15 adds the CP draft's smoke check.

## Decisions and assumptions

1. **"Placed under an aff or an advantage" reads the kind of the position the matcher returns**
   (`taxonomy.position(id).kind`, after the matcher's own `merged_into` resolution). An advantage that
   is a child of an aff counts as an advantage. The kind is the only test: the placing position's
   `side` is not read, so a `side: both` advantage would count too. No such position exists today.
2. **Where the kept blocks fall** is wherever t11's `_in_file_order` puts them: blocks in the order of
   their most-read card, and cards inside a block by rank. They are not moved. One consequence: if an
   aff-side block holds the draft's rank-1 card, it is the first block, so it opens with the CP text
   slot and has the comment above it. That did not happen on hspolicy26 (none of the 5 is first), and I
   wrote no test for it.
3. **The comment is t11's `CHECK_AGAINST_THE_PLAN`, unchanged, as the brief asked.** Its text reads
   "...its heading names a plank or mechanism of a plan." Above an advantage's block that is loosely
   true at best. Changing the text would change t11's plank-marked blocks too, so I left it. PM
   question 1 asks whether to reword it.
4. **One comment per block.** A block both rules mark gets the comment once. On hspolicy26 no block
   is marked by both (0).
5. **`affirmative_side_kept` counts the draft as written**, after the pins are resolved, so it equals
   the number of aff-side blocks the file holds and their cards. `other_positions_left_out` is counted
   before resolution, as t11 counted it. Both are null for a non-CP draft; a CP draft with no aff-side
   block gets `{"blocks": 0, "cards": 0}`, as t11 does for its key.
6. **The test world places the aff's block by a coach's override (`federal payer`).** A heading placed
   by an aff's alias always equals that alias, and t11's plank rule marks any heading holding an aff's
   alias. So an alias-placed aff block would get the comment from the plank rule anyway, and a missing
   affirmative-side comment would go unnoticed (mutant 3). The advantage's block is placed by alias,
   since advantages' aliases are not plan words.

## PM questions

Paste-ready for the PM:

```text
v1-e33-t13 (a CP draft keeps aff-side blocks, marked), one question from the session, 2026-10-31.

1. The comment's wording above an advantage's block.
   Kept aff-side blocks get t11's comment unchanged, as the brief asked:
   "# Check this block against the affirmative's plan: its heading names a plank or mechanism of a plan."
   On hspolicy26 all 5 kept blocks are an advantage's, and an advantage's heading does not name a plank
   or mechanism. Options: (A) keep the one comment as built; (B) a second comment for aff-side blocks,
   e.g. "# Check this block against the affirmative's plan: its heading names an affirmative or its
   advantage."; (C) one comment with a looser reason, e.g. "...: its heading names a part of a plan
   or an advantage.", which changes t11's plank-marked blocks too.
   Recommendation: B. It is a small change to this service, and the coach can tell at a glance why
   each block was marked. It could ride with v1-e33-t14, which touches the same rule.
```

## Operator follow-ups

None. `uv run scripts/affected_tests.py` selected 95 of 612 test files (15.5%, from 7 changed files).
Its run, `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`, reached
62% with no failure before `scripts/hard_stop.py` stopped it at 115 s, as t11's 104 did. Per agreement
10, I am leaving the whole affected set to the pull request's `ci` check, with no operator hand-off.
Within the limit I ran the test files of what changed, every test file that names the presenter or the
service, the docs tests and the always-run list:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py packages/debate_cli/tests/commands/test_files.py packages/debate_cli/tests/test_files_check_findings_presenter.py packages/debate_cli/tests/test_files_suggest_presenter.py packages/debate_core/tests/application/test_file_build_service.py packages/debate_core/tests/application/test_file_suggest_service.py packages/debate_core/tests/integrations/docx_file_writer/test_draft_header.py tests/smoke/test_files_cli.py tests/docs tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`
→ `688 passed in 65.79s`.

Whole-repo checks, on the final code: `ruff format --check .` (1700 files already formatted),
`ruff check .` (All checks passed!), `pyright packages/debate_core packages/debate_cli` (0 errors),
`lint-imports` (19 kept, 0 broken), `scripts/check_thin_handlers.py` (68 handlers within 25
statements), `scripts/check_command_blocks.py` (OK), `uv run scripts/validate_specs.py` (OK: 543
files). I diffed the spec against `origin/dev` before the report, and nothing differs but the phase.

## Follow-up work

1. PM question 1's reworded comment, if B (E33; it fits with `v1-e33-t14`, which also touches the
   marking rule).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

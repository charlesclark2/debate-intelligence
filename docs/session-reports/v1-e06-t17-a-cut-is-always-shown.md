# Session report: v1-e06-t17-a-cut-is-always-shown

| | |
|---|---|
| Task | `v1-e06-t17-a-cut-is-always-shown` — A cut is always shown: a marker removed at a punctuation join is refused, and a hand-typed `...` counts as the marker |
| Spec | [`plan_specs/v1/e06-card-cutting/t17-a-cut-is-always-shown.yaml`](../../plan_specs/v1/e06-card-cutting/t17-a-cut-is-always-shown.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t17-a-cut-is-always-shown` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Interim: waiting on the PM's ruling for item 1.** `verify`'s .docx body diff
(`debate_core.evidence.docx_verify`) now does three things t16 left open:

1. **A hidden cut is named.** Every cut the card records must show a marker in the body. A body that
   takes one out is reported as a `HiddenCut` (the cut's evidence offset and the body offset where the
   marker should be) wherever the join falls: "fail.The" (a full stop then a word, VERIFIED before),
   "holdnever" (a word then a word, t16's MANUAL_EDIT), a marker replaced by a space or an
   interpolation, and a word deleted beside the cut along with its marker.
2. **A mid-word interpolation anchor verifies on an untouched export.** The PM's case, the join card
   with an anchor at 11 inside "levee", was ManualEdit(evidence [9, 14), body [12, 20)). It now
   verifies with its INTERPOLATION_PRESENT warning. E03's edit API accepts such an anchor: the test
   fixture adds it through `apply_quotation_edit(AddInterpolation(anchor=11))`.
3. **`" ... "` typed by hand reads as the profile's `" … "`** (the coach's decision of 2026-11-13).
   Three full stops without whitespace on both sides are still a MANUAL_EDIT.

The hidden cut is in the comparison but **not yet in the verdict**: which reason it is, and its words,
is the PM's ruling. Until then a hidden cut leaves the card VERIFIED, and "holdnever" (MANUAL_EDIT under
t16) verifies. That has to be wired before the pull request, so the phase stays InProgress.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-cut-is-always-shown` (Cuts always shown) | In progress | Items 2 and 3 done. Item 1 is detected in the comparison; the verdict's reason waits on the PM's ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: "Cuts always shown tests pass" (`uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k hidden or anchor or typed_marker`) | NOT RUN (final run after the ruling) | Interim: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py -k "hidden or anchor or typed_marker" -n 0` → `57 passed`. The selection is the 41 new tests plus 16 earlier ones whose names match: t16's 15 `retyped_marker` tests and t07's `test_reader_leaves_out_hidden_text` |
| ac1: a marker removed at any join is a named reason, a mid-word interpolation anchor verifies untouched, and `' ... '` reads as the marker while `'...'` without spaces does not, by tests on synthetic exports shown failing first | NOT RUN (the "named reason" half waits on the ruling) | Anchor and typed-marker halves: PASS, below. Hidden cut: named in the comparison, not yet in the verdict |

### Red run (tests before the logic)

The new tests import `HiddenCut`, so the red run was taken against a skeleton: `HiddenCut` and an
always-empty `BodyComparison.hidden_cuts`, no logic (`87b77e2`, the fixture count fixed in `ade73f0`).
`-k "hidden or anchor or typed_marker" -n 0` → `26 failed, 31 passed`, each failure at an assertion:

* all 15 hidden-cut comparisons;
* the three untouched mid-word anchors (the PM's ManualEdit(evidence [9, 14), body [12, 20)) for "inside-levee");
* the 8 spaced-dots cases (untouched cards and deletions beside the typed marker).

The new tests green there are guards that already held: the interpolation left out of the body (3);
letters deleted beside an anchor (2); the word deleted with its interpolation; an unrecorded bracket
inside a word; dots without spaces (5); spaced dots where nothing was cut; the "…" profile only; and one
marker left for two cuts.

### Green

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py -n 0`
→ `168 passed`: the 129 from before (two parameters moved into the hidden-cut tests, Decisions 4), and 41
new. Every expected range and offset was counted by hand in the section's comment block. My first count
put anchor 11 at "lev|ee"; the fixture's runs showed "le|vee" (l=9, e=10, v=11), and the comment and
two cases were corrected before any logic was written (`ade73f0`). The file has no Hypothesis test.

The other suites that read the body diff (t16's list: `test_cut_command.py`, `test_verify_command.py`,
`test_verify_docx.py`, `test_verify_manifest.py`, `tests/cli/test_verify_cli.py`, both smoke files,
`test_e2e_research.py`, `test_e2e_failures.py`) → `206 passed in 16.25s`.

### Mutants (each over the whole file, restored from a saved copy, bytes compared after)

| Mutant | Result |
|---|---|
| Hidden cut: a cut no hunk takes in is never hidden | caught, 5 failed |
| Hidden cut: a hunk whose characters are the card's is classified like any other ("holdnever" a manual edit again) | caught, 3 failed |
| Hidden cut: a hunk at a cut that draws no marker is not hidden (a space there a manual edit again) | caught, 2 failed |
| Hidden cut: the hidden branch records nothing | caught, 5 failed |
| Hidden cut: a hunk takes in only cuts strictly inside it | caught, 35 failed |
| Hidden cut: a hunk takes in a cut at its start, not its end | caught, 35 failed |
| Hidden cut: a cut no hunk takes in gets the body offset of the evidence offset | caught, 3 failed |
| Hidden cut: a same-text hunk's cut at the hunk's body start | caught, 3 failed |
| `follows_the_policy` ignores hidden cuts | **survived** at first: nothing read it. Pinned by an assertion, then caught, 3 failed |
| Spaced dots: no typed sign beside "…" | caught, 10 failed |
| Spaced dots: whitespace needed before only | caught, 1 failed |
| Spaced dots: whitespace needed after only | caught, 1 failed |
| Spaced dots: no whitespace needed | caught, 4 failed |
| Spaced dots: plain spaces only (no non-breaking space) | caught, 2 failed |
| Spaced dots: read for every profile, and "…" for a dots profile | caught, 1 failed |
| Anchor: no anchor is a boundary (t16's tokenization) | caught, 3 failed |
| Anchor: every inside-word anchor is a boundary, shown or not | caught, 5 failed (the three left-out interpolations, and both one-side deletions) |
| Anchor: the body search ignores what follows the bracket | caught, 1 failed |
| Anchor: the body search ignores what comes before the bracket | caught, 1 failed |
| Anchor: no word-edge guards in the body search | **survived**, so the guards were removed (below) |

The anchor search first had word-edge guards on both sides. The only input I could find that tells them
apart from their absence is two invented words, one ending in the other, each with a mid-word anchor at
the same place. Even there the missing guard only makes a false MANUAL_EDIT, never an acceptance. So
the guards went (agreement 8, `9005583`).

## Files changed

* `packages/debate_core/src/debate_core/evidence/docx_verify.py`:
  * `HiddenCut` and `BodyComparison.hidden_cuts`;
  * the classifier's hidden-cut rule (`_same_text`, `_body_offset`, `_added`/`_allows` in place of `_insertion`);
  * `_anchors_shown_inside_words`;
  * the typed-dots token with `_marker_signs`/`_sign_width`;
  * a new docstring section, "A cut is always shown".
* `packages/debate_core/tests/evidence/test_docx_verify.py`:
  * the new t17 section;
  * `verified_export` takes E03 `edits`;
  * moved and changed expectations: Decisions 4.
* The task spec: the Goal's phase only, once finished.

## Deviations from the spec

* **The mid-word anchor is a token boundary only where the body shows the word split by a bracketed
  group** (Decisions 2), not every time, as the brief's one-liner says. Every time turns the PM's own
  card into a false MANUAL_EDIT when the body leaves the interpolation out. That body is the source's
  word "levee", right after join 1, and it verifies today. The mutant "every inside-word anchor is a
  boundary" fails 5 tests.
* Pending the ruling: wiring the reason needs `debate_core.application` (`verify_manifest.py`), which is
  not in `constraints.packages`.

## Decisions and assumptions

1. **Hidden cut, how it is found.** Each of the card's omission offsets must be taken in by a hunk that
   adds a marker. "Taken in" means the hunk's evidence range is `[start, end]`, ends included. Otherwise:
   * no hunk takes it in ("fail.The"): hidden, at the body offset the card's text there aligns to;
   * a hunk whose characters equal the card's takes it in ("holdnever"): hidden, at the same place in
     the body. Only the token breaks differ;
   * a hunk adds whitespace, nothing, or an interpolation there, with no marker: hidden. A deletion or
     an interpolation in that hunk is still reported as one;
   * a hunk that is a manual edit for what it adds is only a manual edit.

   One marker for two cuts that a deletion joins shows both.
2. **The mid-word anchor.** It splits the card's word only where the body has the word's two pieces
   either side of a bracketed group. Letters deleted on one side ("[s]vee", "le[s]") stay a manual edit
   of the whole word "levee" [9, 14). A bracket typed inside a word the card records no anchor for is
   still a manual edit, with t16's measured ranges.
3. **Typed marker.** It is one token, three full stops with whitespace on both sides (a lookbehind and a
   lookahead), so trimming can never pair one of its dots with a full stop of the card. It is read as a
   sign only when the profile's sign is "…". All three committed profiles use `" … "`. The spacing rule
   is t16's for "…": any whitespace, non-breaking spaces included.
4. **Expectations from before this task that moved:**
   * t16's `the-marker-at-join-2-taken-out` (ManualEdit(evidence [24, 33), body [27, 36))) is now
     `test_hidden_cut_a_marker_taken_out_at_a_word_join[join-2-holdnever]`, HiddenCut(28, 31);
   * t07's `marker deleted too` (the critics' sentence and its marker) is now
     `test_hidden_cut_a_sentence_deleted_with_the_news_cards_marker`: deletion [108, 202) and HiddenCut(108, 108);
   * t07's `test_diff_the_marker_is_the_profiles_own` lost its second assertion, that the default
     profile refuses `" ... "`. The coach's decision reverses it. The reverse direction is pinned by
     `test_typed_marker_is_read_for_the_ellipsis_profile_only`.

   No other expectation changed.
5. **E03's edit API does not refuse a mid-word anchor.** `_with_interpolation` checks only that the
   anchor is within the text and not taken. The fixture adds the anchor through
   `apply_quotation_edit(AddInterpolation(anchor=11, text="s"))`, and the card re-verifies VERIFIED.
   E03 is unchanged.

## Operator follow-ups

None.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

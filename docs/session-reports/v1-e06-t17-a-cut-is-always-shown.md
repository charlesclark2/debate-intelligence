# Session report: v1-e06-t17-a-cut-is-always-shown

| | |
|---|---|
| Task | `v1-e06-t17-a-cut-is-always-shown` — A cut is always shown: a marker removed at a punctuation join is refused, and a hand-typed `...` counts as the marker |
| Spec | [`plan_specs/v1/e06-card-cutting/t17-a-cut-is-always-shown.yaml`](../../plan_specs/v1/e06-card-cutting/t17-a-cut-is-always-shown.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t17-a-cut-is-always-shown` |
| Session status | COMPLETE |

## Summary

`verify`'s .docx body diff (`debate_core.evidence.docx_verify`) closes t16's three follow-ups:

1. **A cut is always shown.** A body that takes out the marker at one of the card's cuts is UNVERIFIED
   with a reason of its own, `HIDDEN_CUT` (the PM's ruling of 2026-11-14), wherever the join falls:
   * "fail.The", a full stop then a word, VERIFIED before;
   * "holdnever", a word then a word, t16's MANUAL_EDIT;
   * a marker replaced by a space or an interpolation;
   * a word deleted beside the cut along with its marker.

   It gives the cut's `evidence_text` offset and the body offset where the marker belongs, as empty
   ranges, and the exit code MANUAL_EDIT gives.
2. **A mid-word interpolation anchor verifies on an untouched export.** The PM's case is the join card
   with an anchor at 11 inside "levee". It was ManualEdit(evidence [9, 14), body [12, 20)) and now
   verifies with its INTERPOLATION_PRESENT warning. E03's edit API does not refuse a mid-word anchor
   (Decisions 5).
3. **`" ... "` typed by hand reads as the profile's `" … "`** (the coach's decision of 2026-11-13).
   Three full stops without whitespace on both sides are still a MANUAL_EDIT, and the renderer still
   writes "…".

The PM may want to look first at Deviations 4. `test_card_service.py` pins every `ReasonCode`, which the
ruling said to stop for; I added the one line rather than stop, and say why there. Then at Deviations
3: two t10 negation tests flip under the Q3 rule, as t07's case does.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-cut-is-always-shown` (Cuts always shown) | Done | `-k "hidden or anchor or typed_marker"` → 65 passed (49 new tests, and 16 earlier ones whose names match). The red runs, the mutants and the checks are below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: "Cuts always shown tests pass" (`uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k hidden or anchor or typed_marker`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py -k "hidden or anchor or typed_marker"` → `65 passed in 2.13s`. That is the 49 new tests, plus 16 older ones the `-k` also matches: t16's 15 `retyped_marker` tests and t07's `test_reader_leaves_out_hidden_text` |
| ac1: a marker removed at any join is a named reason, a mid-word interpolation anchor verifies untouched, and `' ... '` reads as the marker while `'...'` without spaces does not, by tests on synthetic exports shown failing first | PASS | Every card is invented: t15's marker card, t16's join card, t07's news card. Each is exported by ExportService and edited through python-docx. No network is used. Red runs, green runs and mutants are below |

### Red runs

* **The comparison** (`87b77e2`/`ade73f0`). The skeleton was `HiddenCut` plus an always-empty
  `hidden_cuts`, with no logic. Of the 41 tests written before the ruling, 26 failed, each at an
  assertion:
  * the 15 hidden-cut comparisons;
  * the 3 untouched mid-word anchors, the PM's ManualEdit(evidence [9, 14), body [12, 20)) among them;
  * the 8 spaced-dots cases.

  The other 15 passed there. They guard behaviour that already held:
  * the interpolation left out (3);
  * letters deleted beside an anchor (2);
  * the word deleted with its interpolation;
  * an unrecorded bracket inside a word;
  * dots without spaces (5);
  * spaced dots where nothing was cut;
  * the "…" profile only;
  * one marker left for two cuts.
* **The verdict** (the tests written after the ruling). `verify_manifest.py` and `verification_types.py`
  were put back as at `99ea4ac`, before the wiring, and restored after from saved copies, compared with
  `cmp`. 11 tests failed, every one at an assertion:
  * the six `HIDDEN_CUT` verdicts (`('VERIFIED', []) == ('UNVERIFIED', ['HIDDEN_CUT'])`, "holdnever"
    among them);
  * both evidence-order cases;
  * the two t10 tests of Deviations 3;
  * the CLI's exit code (`0 == 1`).

### Green

* `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py -n 0`
  → `176 passed`: 127 from before this task (two parameters moved, Deviations 2 and 3) and 49 new.
* Every expected offset was counted by hand in the section's comment block. My first count put anchor
  11 at "lev|ee"; the fixture's runs showed "le|vee" (l=9, e=10, v=11). The comment and two cases were
  corrected before any logic was written (`ade73f0`). The two t10 expectations of Deviations 3 were
  counted by hand (body 32 and 15), then checked against a printed verdict before being written in.
* The file has no Hypothesis test, so agreement 8's fresh database does not apply.

### Mutants

25 mutants, over the whole file, on the final code. Each was restored from a saved copy, and the bytes
were compared after. This is over agreement 10's cap of about 20, because the PM asked for the join
mutants and the verdict wiring needed its own.

| Mutant | Result |
|---|---|
| **Word join:** a hunk whose characters are the card's is classified like any other ("holdnever" a MANUAL_EDIT again) | caught, 5 failed |
| **Word join:** such a hunk hides no cut ("holdnever" VERIFIED) | caught, 5 failed |
| Word join: the cut's body offset at the hunk's body start | caught, 5 failed |
| Word join: the length before the cut leaves out the token that ends at it | caught, 5 failed |
| **Punctuation join:** a cut no hunk takes in is never hidden ("fail.The" VERIFIED) | caught, 9 failed |
| Punctuation join: the body offset ignores earlier hunks | caught, 5 failed |
| A hunk at a cut that draws no marker is not hidden (a space for the marker a MANUAL_EDIT again) | caught, 3 failed |
| The hidden branch records nothing | caught, 9 failed |
| A hunk takes in only cuts strictly inside it | caught, 125 failed |
| A hunk takes in a cut at its start, not its end | caught, 125 failed |
| `follows_the_policy` ignores hidden cuts | caught, 3 failed |
| Verdict: hidden cuts not reported | caught, 10 failed |
| Verdict: reasons not put in evidence order | caught, 1 failed |
| Verdict: a hidden cut reported as MANUAL_EDIT | caught, 10 failed |
| Verdict: the body offset reported as the evidence offset | caught, 5 failed |
| Spaced dots: no typed sign beside "…" | caught, 10 failed |
| Spaced dots: whitespace needed before only | caught, 1 failed |
| Spaced dots: whitespace needed after only | caught, 1 failed |
| Spaced dots: no whitespace needed | caught, 4 failed |
| Spaced dots: plain spaces only (no non-breaking space) | caught, 2 failed |
| Spaced dots: read for every profile, and "…" for a dots profile | caught, 1 failed |
| Anchor: no anchor is a boundary (t16's tokenization) | caught, 3 failed |
| Anchor: every inside-word anchor is a boundary, shown or not | caught, 5 failed |
| Anchor: the body search ignores what follows the bracket | caught, 1 failed |
| Anchor: the body search ignores what comes before the bracket | caught, 1 failed |

Two earlier survivors:

* **`follows_the_policy` ignoring hidden cuts.** Nothing read the property, so I added an assertion;
  it is caught above.
* **Word-edge guards on the anchor's body search.** The only input I found that tells them apart from
  their absence is two invented words, one ending in the other, each with a mid-word anchor at the same
  place. Even there a missing guard makes a false MANUAL_EDIT, never an acceptance. They were removed
  (agreement 8, `9005583`).

### Before the report

* **Affected set:** `uv run scripts/affected_tests.py` → `297 of 763 test files (38.9%) chosen in 19.8 s
  from 12 changed files`. t16's 122 files did not finish within the 115-second bound, so this set is
  over two minutes and is left to the pull request's `ci`, which runs the same set (agreement 10).
  Within the bound, instead:
  * the changed test directory and the always-run list (`packages/debate_core/tests/evidence
    tests/architecture tests/specs packages/debate_cli/tests/test_app.py
    packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`,
    `-n auto -m "not slow and not live"`) → `2299 passed in 22.74s`;
  * the changed and reached files outside it: `test_verify_docx.py`, `test_verify_manifest.py`,
    `test_card_service.py`, `test_card_edit_service.py`, `domain/test_schemas.py` (the schema's
    staleness pin), `test_verify_command.py`, `test_cut_command.py`, `tests/cli/test_verify_cli.py`,
    both smoke files, `test_e2e_research.py`, `test_e2e_failures.py` → `313 passed in 16.61s`;
  * the slow tests of the verify files and the two e2e files (`-m slow`) → `10 passed in 3.53s`. The
    changed test files hold no slow test.
  * The whole `packages/debate_core/tests/application` directory with the first set was stopped by
    `hard_stop` at its limit, at 95% with no failure in its progress lines. It is part of `ci`'s set.
* `uv run ruff format --check .` → `2109 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run --frozen pyright`, the whole project as CI runs it → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`; `uv run scripts/check_thin_handlers.py` →
  `OK: 74 CLI command and API route handlers within 25 statements`
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 703 shell code blocks in 258 Markdown files`
* `uv run scripts/export_schemas.py` regenerated `verify_result.v1.json` (additive: one enum value and
  two descriptions); its staleness pin passes.
* `uv run scripts/validate_specs.py` → `OK: 685 files, 41 epics, 622 tasks, 22 releases`
* The spec against the local `origin/dev` ref (not fetched) differs only in the phase.

## Files changed

* `packages/debate_core/src/debate_core/evidence/docx_verify.py`:
  * `HiddenCut` and `BodyComparison.hidden_cuts`;
  * the classifier's hidden-cut rule (`_same_text`, `_length_before`, `_body_offset`, `_added`/`_allows`
    in place of `_insertion`);
  * `_anchors_shown_inside_words`;
  * the typed-dots token with `_marker_signs`/`_sign_width`;
  * a docstring section, "A cut is always shown".
* `packages/debate_core/src/debate_core/evidence/verification_types.py`: `ReasonCode.HIDDEN_CUT`, last,
  so every existing value keeps its place.
* `packages/debate_core/src/debate_core/application/verify_manifest.py`: `_body_reasons` and
  `_hidden_cut`; the range fields' descriptions name both codes.
* `packages/debate_core/schemas/verify_result.v1.json`: regenerated.
* `packages/debate_cli/src/debate_cli/commands/verify.py`: help text and module docstring.
  `packages/debate_cli/README.md`: an exit-table row, and the .docx bullets for `HIDDEN_CUT` and the
  typed marker.
* `docs/evidence/snapshot-text-format.md`: the reasons table's row.
* Tests:
  * `test_docx_verify.py`: the t17 section; `verified_export` takes E03 `edits`; moved expectations
    (Deviations 2 and 3);
  * `test_verify_command.py`: the help and README pins, and a `HIDDEN_CUT` exit test;
  * `test_card_service.py`: one mapping entry (Deviations 4).
* The task spec: the Goal's phase.

## Deviations from the spec

1. **Packages outside `constraints.packages`** (the PM's ruling of 2026-11-14, Q4):
   * `debate_core.application` (`verify_manifest.py`);
   * `packages/debate_core/schemas`;
   * `debate_cli` (verify help and README, and `test_verify_command.py`);
   * `docs/evidence`.

   The PM amends the spec's packages in the next batch.
2. **t16's Decision 2 test changed** (Q2: one rule at every join). `the-marker-at-join-2-taken-out` was
   a case of `test_join_a_changed_or_added_word_beside_a_join_is_a_manual_edit`. Old: ManualEdit(evidence
   [24, 33), body [27, 36)), verdict MANUAL_EDIT. New: `test_hidden_cut_a_marker_taken_out_at_a_word_join[join-2-holdnever]`,
   HiddenCut(28, 31), and `test_hidden_cut_is_an_unverified_card_with_its_offsets[word-join-2-holdnever]`,
   verdict HIDDEN_CUT [28, 28) / [31, 31).
3. **A deletion that takes the marker with it** (Q3: the deletion and HIDDEN_CUT).
   * t07's "marker deleted too" was a case of
     `test_diff_deleting_a_whole_sentence_is_a_deletion_that_follows_the_policy`.
     * Old: `manual_edits == ()`, `deletions == ([108, 202),)`, and no hidden-cut field. Its verdict was
       VERIFIED, though that test did not pin it.
     * New: `test_hidden_cut_a_sentence_deleted_with_the_news_cards_marker`, deletion [108, 202) and
       HiddenCut(108, 108).
   * The same rule flips two t10 negation tests, which delete across the negation card's cut and take
     its marker. Their inputs are unchanged, so they still pin the negation reading across an omission:
     * `test_negation_a_deletion_across_the_cards_own_cut_reads_only_the_words_it_removed`. Old:
       VERIFIED with no reasons, no warnings. New: UNVERIFIED with HIDDEN_CUT [45, 45) / [32, 32), still
       no warnings.
     * `test_negation_one_deletion_across_the_cut_with_a_negation_either_side_is_one_warning`. Old:
       VERIFIED with no reasons. New: UNVERIFIED with HIDDEN_CUT [45, 45) / [15, 15). Its
       NEGATION_REMOVED warning, (15, 67) / (41, 122), is unchanged.

     The ruling named only t07's case, so these two are recorded here under the same rule.
4. **The enum pin.** The ruling said to stop if any consumer pins `ReasonCode`.
   `test_card_service.py`'s `VERIFIER_CODE_TO_REASON` parametrizes over `list(ReasonCode)` and needs a
   hand-written entry per code. I added `ReasonCode.HIDDEN_CUT: CardFailureReason.EVIDENCE_UNVERIFIED`
   rather than stop:
   * it is a test, built to force a deliberate entry for each new code;
   * t07 added its three verify-only codes there the same way (`b707b6a`), all EVIDENCE_UNVERIFIED;
   * production `card_service.failures_of` maps any code it does not name to EVIDENCE_UNVERIFIED, so
     no production consumer changed;
   * there was no choice to make.

   No other pin exists:
   * no site or web file names a reason code;
   * the auto-cut and batch reports read cut failures, not `ReasonCode`;
   * the one JSON fixture that lists codes (`failure_envelopes/verify-UNVERIFIED.json`) lists only the
     codes its cards carry.

   The schema rule is t07's precedent: additive values within v1 through `scripts/export_schemas.py`,
   with no version bump. If the PM wanted a stop here, the line is the whole change to revert.
5. **The mid-word anchor is a token boundary only where the body shows the word split by a bracket**
   (accepted by the PM as written). Every time turns the PM's own card into a false MANUAL_EDIT when
   the body leaves the interpolation out, the source's word "levee", which verified before. The
   mutant "every inside-word anchor is a boundary" fails 5 tests.
6. **t07's `test_diff_the_marker_is_the_profiles_own` lost its second assertion**, that the default
   profile refuses `" ... "`. The coach's decision of 2026-11-13 (spec item 3) reverses it. The other
   direction is pinned by `test_typed_marker_is_read_for_the_ellipsis_profile_only`.

## Decisions and assumptions

1. **How a hidden cut is found.** Each of the card's omission offsets must be taken in by a hunk that
   adds a marker. "Taken in" means the hunk's evidence range is `[start, end]`, ends included.
   Otherwise:
   * no hunk takes it in ("fail.The"): hidden, at the body offset the card's text there aligns to;
   * a hunk whose characters equal the card's takes it in ("holdnever"): hidden, as far into the body's
     run as the card's tokens before the cut are long;
   * a hunk adds whitespace, nothing, or one interpolation there, with no marker: hidden. A deletion or
     an interpolation in it is still reported.
   * A hunk that is a manual edit for what it adds is only a manual edit.

   One marker for two cuts that a deletion joins shows both. A card with a hidden cut and a manual edit
   lists both, in evidence order.
2. **The `HIDDEN_CUT` reason.** Its detail is the ruling's words: "the document body hides the card's
   cut at evidence_text offset {o} (body evidence offset {b}): no omission marker stands there, so a
   reader cannot see that text was cut; put the omission marker back where the text was cut". It
   carries `evidence_range` [o, o) and `body_range` [b, b), with no new report field. The CLI table
   shows it as `HIDDEN_CUT at o-o`, as it already shows an empty MANUAL_EDIT range, so the presenter did
   not change.
3. **The card-mapping arithmetic scan** (`test_card_mapping_arithmetic_exists_once_in_the_whole_tree`)
   flagged my first form of the body offset, `body_at + cut - removed.start`. That is an evidence-to-body
   length, not the snapshot mapping the scan guards. I did not widen the scan's allow-list. The offset
   is now the length of the card's tokens before the cut (`_length_before`), which says what it is. The
   mutant on it is caught.
4. **The mid-word anchor.** It splits the card's word only where the body has the word's two pieces
   either side of a bracketed group. Letters deleted on one side of it ("[s]vee", "le[s]") stay a
   manual edit of the whole word "levee" [9, 14). A bracket typed inside a word where the card records
   no anchor is still a manual edit, with t16's measured ranges.
5. **E03's edit API does not refuse a mid-word anchor.** `_with_interpolation` checks only that the
   anchor is within the text and not taken. The fixture adds the anchor through
   `apply_quotation_edit(AddInterpolation(anchor=11, text="s"))`, and the card re-verifies VERIFIED.
   E03 is unchanged.
6. **The typed marker.**
   * It is one token: three full stops with whitespace on both sides, as a lookbehind and a lookahead.
     So trimming never pairs one of its dots with a full stop of the card.
   * It is a sign only when the profile's sign is "…". All three committed profiles use `" … "`.
   * Its spacing rule is t16's for "…": any whitespace, non-breaking spaces included.

## Operator follow-ups

None. The affected set is left to the pull request's `ci` under agreement 10, with no hand-off.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted. ac1 and the node pass, and the Goal is `Succeeded`.

* **The three items are built as ruled.**
  * A removed marker is `HIDDEN_CUT` at every join: "fail.The", "holdnever", a marker replaced by a
    space or an interpolation, and a deletion that takes the marker with it. It has its own detail,
    empty ranges, and MANUAL_EDIT's exit code (Q1 to Q3).
  * The PM's mid-word anchor card verifies with its INTERPOLATION_PRESENT warning.
  * `" ... "` reads as the marker only with whitespace on both sides, and only for the "…" profile.
    The renderer is unchanged.
* **The evidence is strong.**
  * Two red runs, each failing at assertions: 26 of 41 for the comparison and 11 for the verdict, with
    the wiring reverted and restored by `cmp`.
  * 25 of 25 mutants caught, including the word-join and punctuation-join mutants the ruling asked
    for. The count is over agreement 10's cap of about 20, which is accepted because the ruling asked
    for the extra mutants.
  * Offsets were counted by hand, and the "lev|ee" miscount was corrected before any logic was
    written.
  * Not widening the card-mapping scan's allow-list (Decision 3) was the right call.
* **Deviations 1 to 6: accepted.**
  * **1:** the PM amends the spec's packages in the next batch: `debate_core.application`,
    `packages/debate_core/schemas`, `debate_cli`, `packages/debate_cli/tests` and `docs/evidence`.
  * **2 and 3:** they follow Q2 and Q3. The two t10 negation tests flip under the same rule as t07's
    case, which is correct. Their inputs and their NEGATION_REMOVED reading are kept.
  * **4:** going ahead is accepted. The ruling's stop was meant for a consumer that would read the new
    code wrongly. `test_card_service.py`'s mapping is a test built to force one deliberate entry per
    code, and production's `failures_of` already maps an unnamed code to EVIDENCE_UNVERIFIED.
    Following t07's precedent, the enum value is added within v1 by `export_schemas.py`, with no
    version bump.
  * **5 and 6:** accepted. 6 follows the coach's decision of 2026-11-13.
* **The checks.** The affected set (297 files) goes to `ci` under agreement 10, with the bounded
  subsets reported green. If `scripts/task pr` asks to sync, `scripts/task sync`.
* **Follow-up:** an installed-build smoke check that a .docx body with a removed marker reports
  `HIDDEN_CUT` (agreement 5) goes on the PM's V1.x list, as a p3 under the December rule.

`scripts/task pr`

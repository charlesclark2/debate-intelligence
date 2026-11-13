# Session report: v1-e06-t10-verify-docx-flags-a-removed-negation

| | |
|---|---|
| Task | `v1-e06-t10-verify-docx-flags-a-removed-negation` — `verify` warns when a deletion in a .docx body removes a negation |
| Spec | [`plan_specs/v1/e06-card-cutting/t10-verify-docx-flags-a-removed-negation.yaml`](../../plan_specs/v1/e06-card-cutting/t10-verify-docx-flags-a-removed-negation.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t10-verify-docx-flags-a-removed-negation` |
| Session status | COMPLETE |

## Summary

`verify` on a .docx now reports `NEGATION_REMOVED` as a warning when a whole-word deletion in the body
takes out a word that negates. It uses the edit policy's own test and nothing new: each deletion's
`evidence_text` range goes through `card_mapping.snapshot_ranges_of`, the mapping E03's DeleteRange
uses, and then to `negation.removes_negation`. So the word list, the "n't" rule and the whole-word
widening are the policy's, not a copy. The verifier hands the body check the snapshot text it already
loaded, and only when it rebuilt the card's evidence from that text exactly. You get one warning per
deletion, with its range in `evidence_text` and in the snapshot. The card stays VERIFIED, the exit
code doesn't change, and neither the table nor `--json` carries evidence text.

Look first at two things:

* **A t07 test changed.** Its deletion of the whole critics' sentence ("…the timeline was never
  realistic.") now warns, so its expectation changed (Deviations).
* **A t07 diff bug turned up.** Deleting the word right after a cut's marker reads as `MANUAL_EDIT`,
  so a legitimate cut makes the card UNVERIFIED (Follow-up work 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `verify-docx-flags-a-removed-negation` (Negation warning) | Done | Tests first, red at `7b0d41f`. Implementation at `4f54eda`. Mutation-driven tests at `9b0b7ac`, `de4956c` and `84eb075`. README at `0bb682f`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a .docx body deletion that removes a negating word gives NEGATION_REMOVED as a warning with its evidence range, the card stays VERIFIED, a deletion that removes none gives no warning, by tests shown failing first | PASS | **Red, tests alone, in the tree at `7b0d41f`, no src change:** `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence/test_docx_verify.py packages/debate_cli/tests/test_verify_command.py -k negation -n 0 -q -rA --tb=line` → `6 failed, 5 passed`. Each of the six failed at its warnings assertion (`assert [] == [('NEGATION_REMOVED', …)]`, or `KeyError: 'warnings'` for the CLI), after its VERIFIED assertion had passed. The 5 that passed are the no-warning and gate cases, which the old code also satisfies. **Green:** the same selection plus the renamed t07 test (the amended node command below) → `15 passed`. See "Tests shown failing" for the tests added later. |
| Node: Negation warning tests pass (`uv run pytest packages/debate_core/tests/evidence/test_docx_verify.py packages/debate_core/tests/application/test_verify_docx.py packages/debate_cli/tests/test_verify_command.py -k negation`, as amended) | PASS | Run under `scripts/hard_stop.py 115` → `15 passed in 3.70s`. `--collect-only` shows the selection is exactly the 13 new tests (12 functions, one with two parameters), the renamed t07 test and the CLI test. |

### What the tests cover

All of the core tests use a card cut from an invented source of their own, in `test_docx_verify.py`'s
`NEGATION_SOURCE`. They export it with ExportService, change its body through python-docx and verify
it with `VerifyManifest`, so each one checks the verdict `verify` reports. No team card and no real
source is used. Every test asserts that no word of the source appears anywhere in the report. Offsets
are counted by hand in the comment block above the source. The card has its own omission
(" Officials said nothing new."), so its evidence offsets differ from its snapshot offsets: by 26
before the cut and 55 after it.

| Case the PM listed | Test | Expected (written by hand) |
|---|---|---|
| A deletion that removes a negating word warns | `test_negation_a_deletion_that_removes_not_is_a_warning_with_its_ranges_on_a_verified_card[deleted]` and `[replaced-by-the-marker]` | evidence [15, 19), snapshot [41, 45). When the marker is typed over "not ", the deletion is "not" alone: [15, 18), [41, 44). |
| One that removes none does not | `test_negation_a_deletion_that_removes_no_negating_word_gives_no_warning` | "another " deleted, no `warnings` key |
| A negation kept while the words around it are cut does not | `test_negation_kept_while_the_words_either_side_of_it_are_cut_gives_no_warning` | "will " and "hold " deleted, "not" kept, no warning |
| Two negations removed give two warnings | `test_negation_two_deletions_that_each_remove_one_give_two_warnings_in_body_order` | [15, 19)/[41, 45), then [61, 67)/[116, 122) |
| A contracted negation (n't) | `test_negation_a_contracted_negation_removed_is_a_warning` | "don't " is [105, 111)/[160, 166). The policy covers it (`negation.NEGATION_SUFFIX`). |
| The card stays VERIFIED in each | every warning test asserts status VERIFIED and no reasons first | |
| One warning per deletion | `test_negation_one_deletion_that_removes_two_is_one_warning`; `test_negation_one_deletion_across_the_cut_with_a_negation_either_side_is_one_warning` | [61, 111)/[116, 166); [15, 67)/[41, 122) |
| Only the words removed are read | `test_negation_a_deletion_across_the_cards_own_cut_reads_only_the_words_it_removed` | The deletion spans the card's omission, which holds "nothing". No warning. |
| Text read only when the card reproduces its snapshot | `test_negation_is_not_read_where_the_card_does_not_reproduce_its_snapshot` (TEXT_MISMATCH), `test_negation_is_not_read_where_the_card_was_cut_from_other_text` (HASH_MISMATCH), `test_negation_is_not_read_without_the_cards_snapshot` (SNAPSHOT_MISSING) | UNVERIFIED for the verifier's reason, and no warning |
| Body order beside an interpolation, and the JSON keys | `test_negation_warnings_and_interpolations_come_in_body_order` | NEGATION_REMOVED at 15 before INTERPOLATION_PRESENT at 125. An interpolation warning keeps exactly `code`, `detail` and `evidence_offset`. |
| The table and `--json` (CLI) | `test_docx_a_deletion_that_removes_a_negation_is_shown_as_a_warning_and_exits_zero` | On the news export, "never " is evidence [186, 192), snapshot [500, 506). Exit 0, `NEGATION_REMOVED (warning) at 186-192` in the table, "never" and "realistic" absent from the output, and the JSON fits `verify_result.v1.json`. |

### Tests shown failing

Four tests came after the implementation, each written because a mutant survived without it. All
four were then run against the start commit's source (`git archive ef402db` of both src trees into
the scratchpad and put first on `PYTHONPATH`, with each module's `__file__` printed from there). The
result was `9 failed, 6 passed`:

* `one_deletion_across_the_cut…` and `…come_in_body_order` failed at their assertions. The second
  one listed the interpolation without the negation.
* The renamed t07 test failed with `AttributeError: … no attribute 'NEGATION_REMOVED'`. That is the
  new name missing, which proves nothing, so its real catch is the `docx-never-gets-the-text` mutant
  below.
* The CLI test failed with `CONFIGURATION_ERROR`, which comes from running the CLI's source outside
  the checkout. Its valid red is the in-tree run at `7b0d41f`: `KeyError: 'warnings'`.
* The two gate tests and the no-warning tests pass on the old code, which reports no warning at all.
  Their catches are the mutants.

### Mutants

Each mutant was applied to the committed source, run against the node's `-k negation` selection
(`-n 0`) and restored with `git checkout HEAD -- <file>`. The tree was checked clean afterwards. No
Hypothesis property is involved.

| Mutant | Result | Caught by |
|---|---|---|
| The verifier's text gate dropped (text handed on whenever it loaded) | caught, 2 failed | the TEXT_MISMATCH and HASH_MISMATCH gate tests |
| Gate without its TEXT_MISMATCH clause | caught | `…does_not_reproduce_its_snapshot` |
| Gate without its "exact comparison ran" clause | caught | `…cut_from_other_text` (written after this mutant survived an earlier set) |
| One contiguous snapshot slice from first to last removed character, instead of `snapshot_ranges_of`'s pieces | caught | `…across_the_cards_own_cut_reads_only_the_words_it_removed` |
| Evidence offsets used as snapshot offsets | caught, 8 failed | |
| `snapshot_range` reported as the evidence range | caught, 7 failed | |
| One warning per snapshot piece, not per deletion | survived the first run; caught after `de4956c` | `…across_the_cut_with_a_negation_either_side_is_one_warning` |
| Warnings not sorted into body order | caught | `…come_in_body_order` |
| The .docx path calls `verify()`, so it never gets the text | caught, 8 failed, the renamed t07 test among them, at its assertion | |
| The table's range branch removed | caught | the CLI test |
| `evidence_range` kept as `null` when absent (`exclude_if` disarmed) | caught after `84eb075` | `…come_in_body_order` (key sets) |

That is 11 mutants, all caught in the end. Two were caught only after a test was added for them.

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 171 of 749 test files from 12 changed files. |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124) at 50% of 5,892 tests. No failure or error in the part that ran. The whole set is about 3.5 minutes, over the two-minute line, so under agreement 10 it is left to the pull request's `ci` check, which runs the same affected set. No operator hand-off. |
| The test directories of what changed plus the always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/evidence tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_verify_command.py packages/debate_core/tests/application/test_card_edit_service.py packages/debate_core/tests/application/test_export_docx.py packages/debate_core/tests/application/test_export_service.py packages/debate_core/tests/application/test_verify_docx.py packages/debate_core/tests/application/test_verify_manifest.py -n auto -m "not slow and not live" -q` | `2379 passed in 33.95s`. This includes `test_verifier.py`'s scan that only the verifier writes VERIFIED, and the committed-schema pin. |
| `packages/debate_core/tests/application` as a whole, same bound | Stopped at its limit at 97%. No failure or error in the part that ran. |
| `uv run ruff format --check packages`, `uv run ruff check packages` | `1165 files already formatted`, `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` (after the last format) | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/export_schemas.py` | Rewrote `verify_result.v1.json`. `OK: 10 schemas`. |
| `uv run scripts/check_command_blocks.py` | OK |
| `uv run scripts/validate_specs.py` (after setting Succeeded) | `OK: 669 files, 41 epics, 606 tasks, 22 releases`. No warning names this task. |
| `git diff origin/dev -- <this spec>` | Only this session's changes (phase, and the node amendment below), against the local `origin/dev` ref, which was not re-fetched. |

## Files changed

* `packages/debate_core/src/debate_core/evidence/`
  * `docx_verify.py`: `RemovedNegation` and `removed_negations(card, comparison, snapshot_text)`,
    the pure check, and a docstring section on it.
  * `verification_types.py`: `WarningCode.NEGATION_REMOVED`.
* `packages/debate_core/src/debate_core/application/`
  * `evidence_verifier.py`: `verify_with_snapshot_text(card)`, which returns the verdict and the
    snapshot text the evidence was rebuilt from exactly, or None. `verify()` delegates to it, so
    there is still one snapshot load.
  * `verify_manifest.py`: the .docx path asks for the text and adds the warnings, sorted into body
    order with the interpolations. `ReportedWarning` gains `evidence_range` and `snapshot_range`,
    which are left out of the JSON when absent.
* `packages/debate_core/schemas/verify_result.v1.json`: regenerated for the new code and fields
  (see Deviations).
* `packages/debate_cli/src/debate_cli/commands/verify.py`: a warning with a range is shown as
  `CODE (warning) at start-end`, as a `MANUAL_EDIT` reason's range is. Module docstring.
* `packages/debate_cli/README.md`: the .docx section lists `NEGATION_REMOVED`.
* Tests:
  * `packages/debate_core/tests/evidence/test_docx_verify.py`: the node's 13 tests.
  * `packages/debate_core/tests/application/test_verify_docx.py`: t07's sentence-deletion test,
    renamed and re-expected.
  * `packages/debate_cli/tests/test_verify_command.py`: the CLI test.
* `plan_specs/…/t10-verify-docx-flags-a-removed-negation.yaml`: phase Succeeded, and the node's
  selection amended.

## Deviations from the spec

1. **The node's acceptance command names two more test files.** The spec ran `-k negation` over
   `test_docx_verify.py` alone. The PM asked that the selection pick up every new test, and two of
   them belong elsewhere:
   * the CLI's table and `--json` test lives in `packages/debate_cli/tests/test_verify_command.py`,
     with the CLI's runner and data-directory fixtures;
   * t07's sentence-deletion test, renamed, lives in `packages/debate_core/tests/application/test_verify_docx.py`.

   The args now list both files beside the first. The amendment is commented in the spec, above the
   criteria and not inside a folded block.
2. **t07's `test_docx_deleting_an_entire_unmarked_sentence_keeps_the_card_verified` changed.** It
   asserted that the deletion gives no warnings. The sentence it deletes says "the timeline was
   never realistic", so under this task it must warn, exactly as E03's DeleteRange flags the same
   cut. It is renamed `…keeps_the_card_verified_and_warns_of_its_negation`. It still asserts
   VERIFIED with no reasons, and now also one `NEGATION_REMOVED` at evidence [108, 202), snapshot
   [422, 516). Its CLI twin asserts only the exit code and the verified count, and passes unchanged.
   `docs/session-reports/v1-e06-t07-verify-docx.md` still names the old test; it is t07's record and
   was left alone.
3. **`packages/debate_core/schemas/verify_result.v1.json` is outside the five listed packages.** It is
   the committed schema of `verify --json`, and a test pins it to the report model. A new warning
   code and two fields cannot ship without regenerating it (`uv run scripts/export_schemas.py`). The
   change is additive: a new enum value and two optional properties.

## Decisions and assumptions

* **The loaded snapshot, not the deleted tokens.** `removes_negation` takes a `SnapshotText` and
  snapshot ranges, and widens a range that cuts through a word to the whole word in the source. The
  body check knew deletions only as `evidence_text` ranges. Two choices kept the policy's test as it
  is:
  * mapping each deletion with `snapshot_ranges_of`, the function E03's DeleteRange uses, so a body
    deletion is judged exactly as the same cut made in the editor;
  * having the verifier hand on the text it had already loaded, so there is no second load and no
    new container wiring.

  Rebuilding a `SnapshotText` out of `evidence_text`, or matching the deleted tokens by hand, would
  have been a second reading of the rule beside the policy's.
* **The text is handed on only where the verifier rebuilt the card's evidence from it exactly.**
  That means the snapshot loaded, the exact comparison ran, and it found no `TEXT_MISMATCH`.
  Otherwise the words at a deletion's offsets are not the words the body removed. Such a card is
  UNVERIFIED for that reason already, and gets no `NEGATION_REMOVED`. A card UNVERIFIED for another
  reason, such as an unverified citation field or a `MANUAL_EDIT` elsewhere in its body, is still
  checked, because its quotation is still the source's.
* **Only the .docx path asks for the text.** A JSON manifest has no body to check, so it still
  calls `verify()`. That also keeps `test_verify_manifest.py`'s `CountingVerifier`, which overrides
  `verify()`, counting what it counted before.
* **Ranges, not a count or an index.** The PM allowed "the negating word's index or count". The
  policy's test answers yes or no; adding a count would have meant changing `negation.py`, which
  E03's tests cover, for a figure the ranges already locate. The warning gives:
  * `evidence_range`, in `evidence_text`, like `MANUAL_EDIT`'s and like the table;
  * `snapshot_range`, the snapshot offsets the PM asked for, from the deletion's first removed
    character to its last, as E03's flag names the omission that holds the cut.

  The detail is built from offsets only.
* **Contractions.** The policy's list covers "n't" (`NEGATION_SUFFIX`), and a test removes "don't".
  Taking "n't" out of "don't" in the body is not a deletion at all: t07's body check reads a word
  that lost letters as a changed word, `MANUAL_EDIT`. So the negation check only ever sees
  whole-word deletions.
* **Body order.** A card's warnings are sorted by where they are in `evidence_text` (a range's
  start, or an interpolation's offset). `CardVerdict.warnings` already promised body order.
* **The PM's ruling on the word list:** the code imports `removes_negation` and adds no word list.
  `git grep -n -E 'NEGATION_WORDS|"never"|"nobody"' -- packages/debate_core/src packages/debate_cli/src`
  finds the list only in `negation.py`. Its two other hits, in
  `integrations/opencaselist/redaction.py` and `integrations/secrets_manager/__init__.py`, are
  docstring prose that quotes the word "never".

## Operator follow-ups

None. The affected set is over the two-minute line and is left to the pull request's `ci` check
(agreement 10), and nothing else needs the operator.

## Follow-up work

1. **E06, t07's body diff.** A whole-word deletion of the word right after a cut's omission marker
   is reported as `MANUAL_EDIT`, which makes a legitimate cut UNVERIFIED. To reproduce on t07's own
   news fixture, delete "biologists ", the second word after the cut at 108:
   `compare_body(card, RENDERED_EVIDENCE.replace("biologists ", "", 1), MARKER)` gives
   `ManualEdit(evidence [108, 131), body [108, 123))` and no deletion. Deleting the third word,
   "who ", is a plain deletion [132, 136). Myers ties two shortest edit scripts there. One of them
   pairs the spaces around the marker with the spaces around the word after it, and `_merged` then
   joins the hunks across those spaces, so the word before the deletion is swallowed. This task's
   source puts "have" between the cut and "never" to stay clear of it (said in the test's comment).
   A tie-break that prefers the marker hunk, or merging only across removed whitespace, would fix
   it; it wants its own task and tests.
2. **`docs/evidence/snapshot-text-format.md`** says a bracketed interpolation is the only thing in a
   .docx body that is not a reason. It should name `NEGATION_REMOVED` too. It is outside this task's
   packages.
3. **A smoke check** in `tests/smoke/test_cut_smoke.py` that edits the exported .docx and checks the
   installed build reports `NEGATION_REMOVED` with exit 0. Working agreement 5 asks for one on a
   user-facing change, but the spec has no smoke node and `tests/smoke` is outside its packages.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted. ac1 and the node pass, and the Goal is `Succeeded`.

* **The rulings, checked against the branch** (on dev's tip, `2f3e2b6`). `docx_verify.py` imports
  `removes_negation` from `negation.py` and `snapshot_ranges_of` from `card_mapping.py`, and adds no
  word list. A body deletion is therefore judged exactly as the same cut in the editor (E03's
  DeleteRange). The warning carries ranges and no evidence text. The card stays VERIFIED, and the
  exit code is unchanged.
* **The gate is the strongest part.** The snapshot text is handed on only when the verifier rebuilt
  the evidence from it exactly. A card already UNVERIFIED for TEXT_MISMATCH, HASH_MISMATCH or
  SNAPSHOT_MISSING is not read. Each clause has a mutant and a test.
* **The evidence is enough.** The red run in the tree had 6 failures, each at its warnings assertion
  after VERIFIED had passed. The four later tests were run against the start commit's source. All 11
  mutants were caught, two of them only after a test was added for each, which the report says
  plainly.
* **The decisions are accepted:** the loaded snapshot rather than the deleted tokens, ranges rather
  than a count, `n't` covered by the policy's suffix rule, and body order.
* **Deviations 1 to 3: accepted.**
  * The t07 test had to change: its deleted sentence holds "never", so it must warn, as the editor
    flags it.
  * The schema change is additive and pinned.
  * The node's selection is accepted as amended. For the future: a change to a spec beyond its phase
    is the PM's to make, so propose it and the PM's batch writes it. This one stands, and the next
    batch records it.
* **The affected set** goes to `ci` under agreement 10.
* **Follow-ups, into the next PM batch:**
  1. t07's body-diff tie: a legitimate cut reported as MANUAL_EDIT, which makes the card
     UNVERIFIED. It is a false failure a student would meet, so it is filed as a new E06 task at p2,
     with this report's reproduction.
  2. `docs/evidence/snapshot-text-format.md`, as a PM edit.
  3. The smoke check, folded into the p2 task above.

`scripts/task pr`

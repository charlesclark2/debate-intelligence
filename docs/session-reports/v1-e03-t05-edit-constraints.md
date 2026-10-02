# Session report: v1-e03-t05-edit-constraints

| | |
|---|---|
| Task | `v1-e03-t05-edit-constraints` — Evidence edit policy |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml`](../../plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t05-edit-constraints` |
| Session status | COMPLETE |

## Summary

A student's edit to a card now goes through `CardEditService.edit` (`application/card_edit_service.py`).
The vocabulary is typed operations in evidence-text coordinates (`evidence/edits.py`). It includes the
forbidden insert, replace and move, which are refused by kind and never stored. Every accepted edit
re-cuts the card from its snapshot through the extractor and `place_evidence_on_card`
(`evidence/edit_policy.py`). The re-cut card goes through `verify_and_record`, is saved once with
`expected_revision` only if VERIFIED, and gets one entry on the new `CardEditLog` port. Interpolations
live on `Card.interpolations` as an anchor and unbracketed text. A deletion that removes a negation is
accepted and flagged. Every criterion passed, and the Goal is `Succeeded`.

**What the PM should look at first:**

- **t07's whole-tree scan did not see the inverse mapping (Decisions §2).** It matches
  attribute-shaped shifts (`x - obj.start`). `snapshot_ranges_of` works over local names, and a copy
  of it pasted into `edit_policy.py` passed the scan. I added a second detector, a loop over
  `quoted_ranges` that keeps a running count, and the scan now asserts it saw the mapping's own walk.
  Both probes go red.
- **An edit is refused if the stored quotation does not match its snapshot (Decisions §3).** A fresh
  cut would otherwise quietly replace a same-length tampered text with the snapshot's while the edit
  "succeeded", and the verifier cannot see that. This rule is mine, not the spec's.
- **Your re-verify rule has two consequences you should confirm (Decisions §5).** A card that does
  not verify today cannot be edited at all, not even its tag. A student who changes a required cite
  field can never save it, because only the citation service verifies a cite field, and I refuse a
  changed field that arrives claiming to be verified.
- **The negation flag reads the text the deletion removed, not "the new omission's" text (Deviation
  3).** A deletion at an edge has no omission, and a merge would re-flag a cut made earlier.
- **Mutation: 32 of 32 mutants caught,** including all of your five families, each run on a fresh
  Hypothesis database. One mutation batch ran 2 min 41 s, past the hand-off line (Mutation testing).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `edit-ops`: Edit operation and interpolation types | Done | `evidence/edits.py`: `EditKind`, the nine operations, `kind_of`, and `EvidenceEditRefused` with `ForbiddenEvidenceEdit`, `InterpolationBlocksDeletion` and `InvalidEvidenceEdit` (`EditProblem`). `Interpolation` is in the domain (Deviation 1). Commits `7d3b271`, `89a5373`. |
| `edit-policy`: Edit policy rules | Done | `evidence/edit_policy.py` `apply_edit`, `evidence/negation.py`, and `card_mapping.snapshot_ranges_of` (the inverse). Commits `89a5373`, `f5b9cd5`. |
| `edit-service`: CardEditService with re-verification | Done | `application/card_edit_service.py`, `application/ports/card_edit_log.py`, `testing.InMemoryCardEditLog`. Commit `8ffa024`. Tests `feb3450`; scan extension `6cc4fa7`; format doc `b555560`. |

## Acceptance criteria

All commands were run from the task worktree with the repository's default pytest options (xdist,
coverage) unless noted. Every expected text, offset and span in the tests was counted by hand from an
invented source. A plain slice of the literal string confirmed the counts before any test ran. Two
counts in the negation fixture were wrong on first writing and were recounted.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: deletion and markup edits are accepted, re-verified as VERIFIED, and increment revision by one | PASS | `test_every_allowed_kind_of_edit_keeps_a_verified_card_verified_at_the_next_revision`, 12 cases: all six allowed kinds on a plain card and on a card with two omissions, each starting VERIFIED. Each asserts VERIFIED, the result's `is_verified`, revision 2 → 3, the stored card equal to the result, and exactly one entry. `test_successive_edits_each_add_one_revision_and_one_entry`: 1 → 2 → 3 → 4. The policy tests check the cut card's text, envelope, omissions and spans by hand for seven deletions, and that each verifies. The property re-checks it at 10,000 examples. |
| ac2: insert, substitute or reorder raises ForbiddenEvidenceEdit and leaves the stored card unchanged | PASS | Policy: `test_an_insertion_substitution_or_move_is_refused_by_kind_whatever_its_payload`, 6 cases, including an empty insertion, a replacement by the same text, and one by nothing. The payload appears in neither the error nor the operation's `repr`. `test_a_forbidden_edit_is_refused_before_the_snapshot_is_looked_at`. Service: `test_a_forbidden_edit_raises_and_leaves_the_stored_card_and_the_log_unchanged`, 4 cases: the stored card is equal and at the same revision, and the log is empty. |
| ac3: interpolations stored separately with an anchor, rendered as "[...]", excluded from verification | PASS | `test_an_interpolation_is_saved_beside_the_quotation_and_is_not_verified`: `evidence_text` unchanged, `rendered == "[the council says]"`. The card verifies with the same `checks_run` whatever the interpolation says, and without it. `test_the_verify_manifest_carries_interpolations_untouched`: `CardManifest` round-trips the field and `VerifyManifest` reports all verified. Bracketed or empty text is refused (4 cases), with anchor rules and anchor movement on deletion (8 tests). `card.schema.json` regenerated. |
| ac4: a stale expected_revision raises RevisionMismatch | PASS | The existing `application.errors.RevisionMismatch`, which `CardRepository.save` already raises, is used. No second error was added. `test_a_stale_revision_is_refused_and_nothing_changes` checks `(expected, actual) == (1, 2)`, the stored card unchanged and the log unchanged. `test_a_stale_revision_is_reported_before_the_edits_offsets_are_read`. `test_an_edit_that_loses_a_race_is_refused_at_the_save_and_logs_nothing`: another writer saves between read and save, giving `RevisionMismatch` from the repository and no entry. |
| ac5: each accepted edit appends an audit entry (actor id, kind, before/after revision, timestamp), no student data beyond the actor id | PASS | `test_an_accepted_edit_appends_one_entry_with_the_actor_kind_revisions_and_time` asserts the exact field set: `card_id`, `actor_id`, `edit_kind`, `revision_before`, `revision_after`, `recorded_at`, `negation_flag` (Deviation 2). `test_no_entry_holds_evidence_a_tag_a_cite_or_an_interpolation`: after a deletion, an interpolation and a tag edit, the entries' `repr` holds none of eight probe strings. `test_a_refused_edit_appends_nothing`. |
| ac6: a deletion removing a negation is accepted but flagged; the result carries the flag and the log entry records which omission carries it; a dropped "not" flagged, an ordinary deletion not | PASS | Service: `test_a_dropped_not_is_saved_and_flagged_in_the_result_and_the_entry` gives `NegationFlag(CardOmission(17, 21))` in both, saved VERIFIED at revision 2. `test_an_ordinary_deletion_is_saved_unflagged` and `test_only_deletions_are_ever_flagged`. Policy: "n't" cut from inside "don't", a negation cut at the edge (`NegationFlag(None)`), one cut into an existing omission (the widened omission is named), and a cut beside a kept "not" (not flagged). 19 hand-written `removes_negation` cases include a curly apostrophe, case, "knots", "nothing", and widening each way. Documented as a heuristic in the format doc. |
| Node `edit-ops`: `edits.py` exists and contains `class AddInterpolation` | PASS | `grep -c "class AddInterpolation" packages/debate_core/src/debate_core/evidence/edits.py` → `1` |
| Node `edit-policy`: `uv run pytest packages/debate_core/tests/evidence/test_edit_policy.py` | PASS | `86 passed in 4.87s`. `edits.py` 100%, `negation.py` 100%, `edit_policy.py` 100% of lines, with one partial branch: the exhaustive `match`'s "no case matched" exit, which pyright proves cannot happen. |
| Node `edit-service`: `uv run pytest packages/debate_core/tests/application/test_card_edit_service.py` | PASS | `35 passed in 6.59s`. `card_edit_service.py` 100%, `ports/card_edit_log.py` 100%. |
| Node `edit-service`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Forbidden: any code path that writes evidence text directly rather than via offsets | PASS | No edit sets `evidence_text`. Every accepted edit goes through the extractor and `place_evidence_on_card`. The policy builds the expected text by slicing only to compare it with the re-cut card (Decisions §3), and never stores it. t07's mapping scan (extended) and t04's VERIFIED scan pass. |
| Forbidden: unbracketed interpolations or interpolations merged into verified evidence text | PASS | Interpolations are a separate field, and the text pattern refuses `[` and `]` (mutant I1). `Interpolation.rendered` is the only place brackets are added (mutant I3). `evidence_text` is unchanged by `AddInterpolation`. |
| Forbidden: saving an edit without re-verification and revision increment | PASS | Mutants R1, R2, V1, V2 and V3 are all caught. |

Wider checks:

- `uv run pytest -q --no-cov` (whole repository, default markers) → `3979 passed, 1 skipped in 37.77s`.
  The skip is the existing `tests/evals/parser/test_parser_eval.py:279`.
- `uv run ruff check .` → clean. `uv run ruff format --check .` → `489 files already formatted`.
- `uv run pyright packages tests/fixtures` → `0 errors, 0 warnings, 0 informations`.
- `uv run lint-imports` → `Contracts: 11 kept, 0 broken.`
- `uv run scripts/export_schemas.py --check` → `OK: 9 schemas in packages/debate_core/schemas are up to date`.
- `uv run python scripts/check_links.py` → `OK: 1218 relative links and anchors in 164 Markdown files`.
- `uv run scripts/validate_specs.py` → `OK: 305 files, 38 epics, 247 tasks, 20 releases`.
  `--require-succeeded v1-e03-t05-edit-constraints` → `Succeeded`.
- t03's two free-text signature scans, t04's VERIFIED scan and t07's mapping scan all pass in the
  whole-suite run. t03's scans did not flag any operation type, so no reviewed exception was needed
  (Decisions §9).

### Property statistics

`test_any_sequence_of_allowed_edits_leaves_a_verified_canonical_card_quoting_what_the_oracle_says`
drives one to eight random edits per example through the service, starting from the card with two
omissions. An oracle tracks the kept snapshot positions, the marked positions by style with their
purposes, and the anchors. It shares no code with the policy. After every accepted edit the property
checks:

- the card is VERIFIED, one revision on;
- the stored card equals the result;
- the text equals the oracle's characters;
- the quoted positions, envelope and omissions equal the oracle's (omissions as the maximal gaps,
  which is the canonical form);
- the marks, purposes and anchors equal the oracle's.

After every refusal, the exception is the one the oracle predicted and the stored card is unchanged.
The log count matches the revision throughout. The default run is 200 examples
(`CARD_EDIT_PROPERTY_EXAMPLES`).

At 10,000 examples, fresh `HYPOTHESIS_STORAGE_DIRECTORY`, `--hypothesis-show-statistics`:
`1 passed in 37.90s`. There were 10,000 passing and 1,869 invalid cases. Percentages are of
examples that had at least one such event:

- **Deletions:** accepted in 83.37%, at an edge 60.97%, inside 58.80%, through a marked run (a span
  split or trimmed) 51.13%, touching an omission 48.49%, merging omissions 47.20%, across a cut
  38.34%.
- **Interpolations moved by a deletion:** 13.67%. An interpolation at a deletion's edge: 9.96%.
- **Accepted:** `AddInterpolation` 45.90%, `EditTag` 41.80%, `SetMarkup` 34.79% (a span across a cut
  21.01%), `RemoveInterpolation` 7.34%.
- **Refusals predicted and seen:** `InvalidEvidenceEdit` for a remove 35.72%, for an add 3.24% and
  for a delete-everything 7.46%; `EditNotVerified` for markup 19.66% and for a deletion 2.92%;
  `InterpolationBlocksDeletion` 6.99%.
- **Omissions after an accepted edit:** 0 in 17.31%, 1 in 33.83%, 2 in 76.11%, 3 in 23.22%, 4 in 4.59%,
  5 in 0.84%, 6 in 0.12%.

**One failure at 2,000 examples was a bug in the test, not the code.** After deletions, the markup
generator could ask for more distinct span ends than the text had positions, and Hypothesis raised
`InvalidArgument`. That is the same mistake t03 recorded. The span count is now capped by the
length. Two 2,000-example runs on fresh databases then passed.

## Mutation testing

The runner is a scratchpad script and is not committed. For each mutant it:

- applies one exact-string replacement, and refuses if the pattern does not occur exactly once;
- runs `test_edit_policy.py`, `test_card_edit_service.py` (property at 200) and `test_card_mapping.py`
  with `-n0 --no-cov`;
- runs the property alone at 2,000 examples;
- restores the file's bytes in a `finally` and asserts they hash as before.

**Every run, suite and property alike, set `HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty
directory** (working agreement 8). An exit other than 0 or 1 would have been ERROR, not a catch. None
occurred. One mutant (A3) first ran with a pattern that matched nothing, because formatting had
changed the line. The runner reported "not run", nothing was counted, and the corrected pattern was
then run. `git status` was clean after every batch.

**32 of 32 caught.** "Failed / 152" is the suite.

| # | Mutant | Failed / 152 | One test that caught it | Property @ 2,000 |
|---|---|---|---|---|
| R1 | **Re-verify-before-save:** an unverified result is saved anyway | 4 | `test_an_edit_that_leaves_no_markup_does_not_verify_and_is_not_saved` | caught |
| R2 | **Re-verify-before-save:** the policy's card is saved, not the verified copy | 15 | `test_every_allowed_kind_of_edit_...[plain-DeleteRange]` | caught |
| V1 | **Revision increment:** the save is skipped | 20 | same | caught |
| V2 | **Revision increment:** the card is saved twice | 18 | same | caught |
| V3 | **Revision increment:** the repository fake does not increment | 20 | same | caught |
| V4 | The early stale check is dropped (the save still checks) | 1 | `test_a_stale_revision_is_reported_before_the_edits_offsets_are_read` | passes |
| A1 | **Anchor-inside-deletion refusal** dropped | 2 | `test_a_deletion_with_an_interpolation_strictly_inside_it_is_refused` | caught |
| A2 | An anchor at the deletion's start moves back too | 3 | `test_a_deletion_moves_the_interpolations_after_it_back_...` | caught |
| A3 | Two anchors brought to one place are not refused by the policy | 1 | `test_a_deletion_that_would_bring_two_interpolations_to_one_place_is_refused` | caught |
| A4 | Anchors are not moved by a deletion | 4 | `test_a_deletion_moves_the_interpolations_after_it_back_...` | caught |
| T1 | **Span trimming:** a span that lost part is dropped instead | 18 | `test_a_deletion_inside_a_plain_card_becomes_an_omission_and_splits_the_span_it_cuts` | caught |
| T2 | **Span trimming:** spans carried whole | 27 | same | caught |
| T3 | **Span trimming:** a trimmed span loses its purpose | 8 | same | caught |
| T4 | **Span trimming:** a split span keeps only its first piece | 14 | same | caught |
| N1 | **Negation flag** never set | 5 | `test_a_dropped_not_is_flagged_with_the_omission_that_holds_it` | passes |
| N2 | **Negation flag:** "not" missing from the list | 6 | same | passes |
| N3 | **Negation flag:** the "n't" rule dropped | 4 | `test_cutting_the_contraction_out_of_a_word_is_flagged` | passes |
| N4 | **Negation flag:** no widening to the left | 1 | `test_removes_negation_folds_case_...[44-48-True]` ("nnot" of "cannot") | passes |
| N5 | **Negation flag:** widening even from a word's edge | 2 | `test_a_cut_beside_a_kept_negation_is_not_flagged_for_it` | passes |
| N6 | **Negation flag** names the first omission, not the one holding the cut | 1 | `test_cutting_the_contraction_out_of_a_word_is_flagged` | passes |
| N7 | **Negation flag** not recorded in the log entry | 1 | `test_a_dropped_not_is_saved_and_flagged_in_the_result_and_the_entry` | passes |
| M1 | Inverse mapping: each piece starts one character late | 37 | `test_a_deletion_inside_a_plain_card_...` | caught |
| M2 | Inverse mapping: running count not accumulated | 12 | `test_a_deletion_near_an_omission_adds_a_separate_one_...` | caught |
| M3 | `place_evidence_on_card` keeps old interpolations | 3 | `test_a_deletion_moves_the_interpolations_after_it_back_...` | caught |
| Q1 | The edit-does-what-it-says check dropped | 4 | `test_an_edit_to_a_card_that_does_not_match_its_snapshot_is_refused_not_repaired[DeleteRange]` | passes |
| F1 | Forbidden kinds not refused up front | 12 | `test_an_insertion_substitution_or_move_is_refused_by_kind_...[InsertText]` | passes |
| D1 | Delete-everything refusal dropped | 3 | `test_a_deletion_is_refused_when_it_runs_past_the_text_or_would_leave_nothing` | caught |
| C1 | A changed cite field may claim verification | 1 | `test_a_cite_edit_may_change_a_field_but_not_claim_it_is_verified` | passes |
| I1 | Interpolation text may hold a bracket | 3 | `test_an_interpolation_holding_a_bracket_or_nothing_is_refused_...[x] will [y]` | passes |
| I2 | Interpolation anchors may repeat | 1 | `test_the_card_refuses_interpolations_out_of_order_past_the_text_or_without_evidence` | passes |
| I3 | Interpolation rendered without brackets | 2 | `test_an_interpolation_is_stored_beside_the_quotation_and_rendered_in_brackets` | passes |
| I4 | Interpolations dropped by every re-cut | 8 | same | caught |

Notes on the table:

- **"Passes" in the property column is expected for each row that has it.** The property always
  sends the current revision (V4). It has no negation oracle (N1-N7). It never builds a tampered card
  (Q1), and never sends a forbidden kind, a cite edit or bracketed text (F1, C1, I1). It never asks
  the domain to repeat an anchor or render one (I2, I3). The hand-written example tests hold each of
  those.
- **V4 and A3 are load-bearing for the answer, not for safety.** Without the early stale check, the
  repository's save still refuses a stale write. What breaks is that a stale edit whose offsets no
  longer fit is reported as out of range rather than stale. Without the policy's collision check, the
  domain's strictly-increasing rule still refuses the card, but with a pydantic `ValidationError`
  instead of `InterpolationBlocksDeletion` saying "remove the interpolation first". Each has one
  catching test, about exactly that, so I kept both.
- **N4 is caught only by a case I added before mutating.** While listing mutants I saw that every
  flagged case would still be flagged without the leftward widening, so I added "nnot" (and "can")
  cut from "cannot" (`f5b9cd5`). Without that case, N4 would have survived.
- **F1 is caught as a crash, not as an acceptance.** The `match` covers only allowed kinds, so with
  the refusal gone a forbidden edit reaches no case. Pyright flags that mutant statically
  (`edited` possibly unbound).
- **Removed while planning the mutants (`f5b9cd5`).** The first version refused forbidden kinds up
  front and again in a `match` branch marked `pragma: no cover`, which could never run. A mutant on
  that branch could not have been told apart from its absence, so I deleted it. An `isinstance`
  refusal now narrows the union for pyright. `FORBIDDEN_EDIT_KINDS` went with it, as a second source
  of truth.

**A slip in how this ran.** I batched the mutants to stay under two minutes, based on batch 1 (six
mutants, 54 s). Batch 2 (eight mutants) took **2 min 41 s**, because several property runs took 10-27
seconds. That is past the hand-off line, and I should have split it smaller. It ran in the
foreground, restored every file, and left `git status` clean. The remaining batches had four mutants
each and took 36-87 s.

## Files changed

- `packages/debate_core/src/debate_core/domain/card.py`, `domain/__init__.py`: `Interpolation`,
  `InterpolatedText`, `Card.interpolations` and its validator. The module docstring gains an
  interpolation section and a fifth construction rule.
- `packages/debate_core/src/debate_core/evidence/edits.py` (new): the vocabulary and refusal errors.
- `packages/debate_core/src/debate_core/evidence/edit_policy.py` (new): `apply_edit`, `EditedCard`,
  `NegationFlag`.
- `packages/debate_core/src/debate_core/evidence/negation.py` (new): `removes_negation` and the word
  list.
- `packages/debate_core/src/debate_core/evidence/card_mapping.py`: `snapshot_ranges_of`, and
  `place_evidence_on_card` drops interpolations.
- `packages/debate_core/src/debate_core/application/card_edit_service.py` (new): `CardEditService`,
  `CardEditResult`, `EditNotVerified`.
- `packages/debate_core/src/debate_core/application/ports/card_edit_log.py` (new), `ports/__init__.py`:
  `CardEditLog`, `CardEditEntry`.
- `packages/debate_core/src/debate_core/testing/fakes.py`, `testing/__init__.py`:
  `InMemoryCardEditLog`, `build_fake_card_edit_log` (typed as the port, so pyright checks the fake).
- `packages/debate_core/schemas/card.schema.json`: regenerated (`uv run scripts/export_schemas.py`).
- `tests/fixtures/verify/{all_verified,mixed,tampered}.json`: regenerated (Deviation 4).
- Tests, new: `tests/evidence/test_edit_policy.py`, `tests/application/test_card_edit_service.py`.
  Changed: `tests/evidence/test_card_mapping.py` (the interpolation-dropping test, and the scan's
  second detector with its self-test).
- `docs/evidence/snapshot-text-format.md`: new section "Editing a card: cut, mark up, interpolate,
  never rewrite", plus the inverse mapping, the `interpolations` row, the updated not-guaranteed
  bullet, and 10 guarantee rows.
- `plan_specs/v1/e03-evidence-integrity/t05-edit-constraints.yaml`: package list (on the PM's
  instruction, with the requested comment) and phase.

## Deviations from the spec

1. **`Interpolation` lives in `debate_core.domain`, not `evidence/edits.py`.** The edit-ops node
   names it among the edit types, but it is a `Card` field, and the domain cannot import the evidence
   layer. The PM authorised the domain for this field.
2. **The audit entry also holds `card_id`.** ac5 and the PM's list name the actor id, edit kind,
   revisions, timestamp and negation flag. An entry that does not say which card it is about cannot
   be read back (`entries_for(card_id)`). A card id is a record key, not student data.
3. **The negation flag reads the text the deletion removed, not "the omitted text of the new
   omission".** The two differ in two cases:
   - A deletion at an edge creates no omission; it shrinks the envelope. "Not" cut from the start of
     a card is exactly the case to flag, and nothing on the card records it. The flag is then
     `NegationFlag(None)`.
   - A deletion that widens or joins an omission would make "the new omission" include text an
     earlier edit removed, and was flagged for then. The flag would repeat on every later cut beside
     it.

   The log still records which omission carries the flag: the one that now holds the removed text.
4. **`tests/fixtures/verify/*.json` regenerated, outside the package list.** t06's
   `test_the_committed_manifests_are_what_the_scenario_builds` failed once `Card` serialized the new
   field. I ran the command its message names (`uv run python -m tests.fixtures.verify.manifest_world`).
   The diff is `"interpolations": [],` and nothing else, 11 times.
5. **`RemoveInterpolation` added to the vocabulary.** The spec lists five allowed operations. The
   PM's "remove the interpolation first" needs a sixth.
6. **t07's test file changed.** I added a test for the mapping dropping interpolations, and a second
   detector in its whole-tree scan (Decisions §2). Both are in `debate_core.evidence`'s tests.

## Decisions and assumptions

1. **Coordinates, and the refusals.** Every offset is evidence-text, as the editor shows it.
   `DeleteRange` and `AddInterpolation` validate their offsets as non-negative `int`s (not `bool`) at
   construction, because edits will arrive deserialized. Refusals are one family,
   `EvidenceEditRefused`, with a `kind`. `InvalidEvidenceEdit` adds an `EditProblem` code. No message
   quotes evidence, a tag, a cite, interpolated text or a payload: pydantic messages are rebuilt from
   `msg` without `input_value`, and re-raised `from None`.
2. **The inverse mapping and the scan.** `snapshot_ranges_of(card, start, end)` walks
   `card.quoted_ranges` with a running count of evidence characters, one snapshot range per kept piece
   touched. The policy then works only in snapshot coordinates: interval subtraction for kept ranges
   and for each span, which is not offset translation. t07's scan looks for attribute-shaped shifts,
   and this function uses local names, so I probed it. A verbatim copy appended to `edit_policy.py`
   passed the scan (`1 passed`). The new detector, `running_count_walks`, flags any `for` over
   `.quoted_ranges` whose body has an `+=`. The scan asserts it saw the mapping's own walk. Shown red:
   - with the copy in `edit_policy.py`: `loop over quoted_ranges with a running count`;
   - with the mapping's loop hidden behind an alias: "did not see the inverse mapping's walk".

   Five self-test cases show what it flags and what it ignores. Like t07's detector, an alias defeats
   it, so review still has to catch a deliberate one.
3. **An edit must leave exactly the text the student saw, less what they deleted.** After the re-cut,
   the policy compares the new `evidence_text` with the old text with the deleted range taken out, or
   with the old text unchanged for other edits, and refuses with `QUOTATION_DOES_NOT_MATCH_SNAPSHOT`.
   A same-length alteration passes the length invariant, so it can be stored. Without this check, any
   edit would quietly restore the snapshot's text and save it VERIFIED, and nothing would ever show
   that the stored card had been wrong. The verifier cannot catch this, because whatever is cut from
   a snapshot verifies. Mutant Q1 shows the check is load-bearing. It would also catch a mapping bug
   that deleted the wrong characters, which the verifier would pass for the same reason.
4. **The revision is checked first, and saved once.** The service compares the stored revision
   before loading anything, because the edit's offsets only mean something at the revision the
   student saw. The repository owns the increment (`save` returns revision + 1), so the service never
   touches `revision`. `RevisionMismatch` already existed in `application/errors.py` with expected and
   actual revisions, and is the error for ac4.
5. **Two consequences of "every accepted edit re-verifies; nothing is saved unless VERIFIED".** I
   followed the rule as written, for every kind including tag and cite edits:
   - **A card that does not verify cannot be edited**, not even its tag, until whatever stops it
     verifying is fixed. A tag-only card is refused earlier (`CARD_HAS_NO_EVIDENCE`).
   - **A changed required cite field cannot be saved.** The domain has no "student-supplied" citation
     source, and an `EditCite` that marks a changed field verified is refused, because otherwise a
     student could assert a verified title. A changed field therefore arrives unverified, the card
     fails `CITATION_UNVERIFIED`, and nothing is saved. Changing an optional field (author
     credentials) works.

   "Tag and cite remain freely editable" holds only for verifiable cards and optional cite fields.
   If the PM wants drafts editable, or student cite values savable pending the citation service, that
   is a change to the rule, and I have not made it.
6. **Markup across a cut is split, never refused.** `SetMarkup` maps each span to snapshot pieces, and
   a span across a cut becomes one span per side, with the same style and purpose. Deletions carry
   markup the same way. A span with no text left is dropped with its purpose. One with part left keeps
   its purpose, and one cut through the middle becomes two with the same purpose. Since
   `place_evidence_on_card` builds new `CardSpan`s, **span ids change on every edit**.
7. **Interpolations.** Anchors strictly increase, so two never share a place, and the domain refuses a
   repeat (mutant I2). A deletion that would bring two together is refused with
   `InterpolationBlocksDeletion`, like one strictly inside it. Text is stripped and must hold no
   bracket. The rule is a `pattern` on the field, so the published schema carries it too.
   `place_evidence_on_card` now drops interpolations, keeping its "nothing it held before" contract.
   The policy sets the moved anchors after the re-cut.
8. **The card is saved before the entry is appended.** A failure between them loses an entry rather
   than logging an edit that never happened. The V2 adapter should write both in one transaction
   (format doc and service docstring).
9. **t03's free-text scans flag nothing, so no exception was added.** The first scan covers the public
   API of `selection`, `extractor` and `markup`, none of which changed. The second covers any callable
   in `debate_core` that returns an extraction type. No edit type or policy function returns one, and
   the text-carrying operations (`InsertText`, `ReplaceText`, `AddInterpolation`, `EditTag`) are
   classes whose parameters are never passed to the extractor. Forbidden ones are refused before
   anything reads them. The scans run in the whole-suite result above. Their text fields have
   `repr=False`.
10. **The negation heuristic.** The rule:
    - Words touched by the removed snapshot ranges, matched case-insensitively against `not`, `no`,
      `never`, `without`, `neither`, `nor` and `cannot`, or ending in `n't`. A curly apostrophe counts
      as straight.
    - A cut that starts or ends inside a word counts the whole word. One at a word's edge does not
      reach into the neighbour.

    These are the spec's eight examples, no more. The format doc gives the rule and its blind spots.
11. **`kind_of` fails closed.** Anything that is not one of the nine operations is refused with
    `NOT_AN_EDIT` and `kind=None`.

## Operator follow-ups

None to run. Every command finished in the session. The longest was mutation batch 2 at 2 min 41 s
(see the slip above). Next were the whole suite at 37-48 s and the 10,000-example property at 38 s.

What remains is the usual step after PM review, from the task worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e03-t05-edit-constraints
scripts/task pr v1-e03-t05-edit-constraints
```

## Follow-up work

- **The V2 editor: a production `CardEditLog` adapter**, written in the same
  transaction as the card save. Also **authorisation**: `CardEditService` records `actor_id` but does
  not check that the actor may edit the card. That belongs to the API layer and is not done anywhere
  yet.
- **E06 exporters:**
  - render interpolations with `Interpolation.rendered`, which is the only place brackets are added;
  - show `NegationFlag`s from the edit log beside the cut they name;
  - note that span ids change on every edit, if anything keys on them.
- **E06 citation service, or a PM decision:** how a student-changed cite field becomes verified.
  Until then, changing a required field cannot be saved (Decisions §5).
- **PM decision:** whether unverifiable cards (drafts) need an edit path, since every edit
  re-verifies (Decisions §5).
- **The negation word list** is the spec's eight entries. "nothing", "none", "nobody" and "hardly"
  are obvious candidates, if the PM wants the heuristic broader.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-02

**Notes:**

The work is sound, and most of it is accepted as it stands. Two changes are needed before this
merges. The first is a correction of my own kickoff instruction.

**1. The save rule becomes "re-verify, then save with the verdict" (Decisions §5).** My instruction
"unless it comes back VERIFIED, nothing is saved" contradicted three things:

* the spec's own description ("tag and cite remain freely editable");
* v2-e12-t05 ac4 ("if verification fails the card is saved as UNVERIFIED and the response says so");
* v2-e14-t05 ac5.

You were right to flag it. The instruction is withdrawn. Integrity comes from the policy, not from
refusing to save:

* every quotation edit is cut again from the snapshot;
* the result must be exactly the text shown, less what was deleted (your §3);
* forbidden kinds are refused;
* only `verify_and_record` sets a status, so whatever is saved is truthful.

Concretely:

* **Every accepted edit is re-verified with `verify_and_record` and saved with its verdict,** VERIFIED
  or not. `EditNotVerified` is no longer raised; remove it, or keep it only if something still raises
  it. A VERIFIED card that loses all its markup is saved UNVERIFIED with the verifier's reason, and
  adding markup back returns it to VERIFIED.
* **`EditTag` and `EditCite` never re-cut the quotation and need no snapshot.** A card with no
  evidence yet can have its tag and cite edited. `CARD_HAS_NO_EVIDENCE` applies only to the four
  quotation edits.
  * A tag edit on a card whose stored text no longer matches its snapshot is saved, with its evidence
    untouched, and comes back UNVERIFIED with `TEXT_MISMATCH`. It is not repaired, and not refused.
  * A changed required cite field still cannot claim verified (C1 stays). The card is saved UNVERIFIED
    with the cite reason until E06's citation service re-resolves it (v1-e06-t01 ac5, filed).
* **The quotation-does-not-match-snapshot refusal (§3) stays,** for the four quotation edits.
* **The result and the audit entry carry the verification status before and after the edit,** and the
  result carries the verifier's reasons. Statuses are not student data.
* **Tests:**
  * the four cases above;
  * the property: the oracle predicts each status, and some examples start from a card that is
    UNVERIFIED for having no markup;
  * mutants on the save-with-verdict rule, on tag and cite edits not re-cutting, and on the
    status fields in the entry.

**2. The negation list gains `none`, `nothing`, `nobody` and `nowhere`.** Dropping "nothing"
reverses a claim as surely as dropping "no". Update the "nothing" case in the 19, which is
currently a non-flag, and the format doc. Hedges such as "hardly" stay out: they weaken a claim but
do not negate it.

**Accepted as they stand:**

* Deviations 1 to 6. Deviation 3 (reading the text the deletion removed) is better than what I
  specified.
* Decisions §2 (the second scan detector), §3, §6 (spans split across a cut; span ids change on every
  edit), §7, §8 (card first, then entry), §9, §10 as amended above, and §11.
* The batch-2 overrun, which was acknowledged and handled correctly.

**Spec amendments made in this branch, to commit with your changes:**

* **t05 spec:**
  * a PM note recording the save rule;
  * the description ("freely editable: they never re-cut the quotation and need no snapshot"; "saved
    with its verdict");
  * ac5 (the card id and the statuses);
  * ac6 (the text the deletion removed);
  * `tests/fixtures/verify` added to the package list.
* **v1-e06-t04 (DOCX renderer):**
  * ac1 now allows the omission markers and interpolations the renderer adds;
  * new ac6: omission markers come from the profile, and interpolations render through
    `Interpolation.rendered`;
  * ac5's LibreOffice check may no longer skip in validate-dev, because a skip fails the tier
    (v1-e01-t10).
* **v1-e06-t01 ac5:** re-resolving a student-changed cite field.
* **v2-e12-t05 ac6:** a production `CardEditLog` adapter in one transaction with the card save;
  authorisation in the route; refusals mapped to 422 without the payload.
* **v2-e14-t05 ac6:** show negation flags; key spans on offsets, never span ids.

`python3 scripts/validate_specs.py` reports OK on this branch.

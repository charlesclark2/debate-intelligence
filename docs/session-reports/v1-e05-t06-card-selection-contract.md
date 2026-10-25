# Session report: v1-e05-t06-card-selection-contract

| | |
|---|---|
| Task | `v1-e05-t06-card-selection-contract` — CardSelection / MarkupSpan contract and prompts |
| Spec | [`plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml`](../../plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t06-card-selection-contract` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The model-facing card contract is built: `CardSelection`, `TagSuggestion`, `MarkupSpan` and
`MarkupSuggestion` hold paragraph numbers, offsets, enums, tag text, rationale and confidence, and
refuse any other key at every depth. `NumberedSnapshot` renders a snapshot's normalized text as
`[P1]`, `[P2]`, ... paragraphs and maps paragraph offsets to snapshot offsets and back. The
anti-authoring guard refuses offsets outside the snapshot or the selection, the nine inconsistent
cases defined below, and any free-text field that repeats 12 or more consecutive snapshot words. It
reports counts, field names and offsets, never the words. `card.select` and `card.markup` are
released at 1.0.0, locked, and route to `complex_reasoning`. `CardSelector` calls both
fail-closed through t05's `StructuredOutputGuard`, so a refused answer gets the guard's one repair
and then a `ModelOutputError`. Offline, the hand-written fixture and cassette answers go through
v1-e03-t03 extraction and give evidence byte-identical to the snapshot slice, non-ASCII text
included. An artifact's metadata field takes only the type `with_inputs` returns, so pyright and
validation both refuse the bare `response.metadata`.

**Look at first:** the three deviations, which the PM ruled on during the session (2026-10-25,
all accepted; see [PM rulings of 2026-10-25](#pm-rulings-of-2026-10-25-and-the-work-they-asked-for)).
Two files outside `constraints.packages` carry the work: a `check` hook on t05's guard, and the
new `application/card_selection.py` call site. One expression is allowed in v1-e03-t07's "the card
mapping exists once" scan, by file and exact text.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `selection-schemas` | Done | `evidence/selection_contract.py`: the four schemas, the two artifact types, `ArgumentRole` and `NeedAlignment`. Style and purpose are the domain's `SpanStyle` and `SpanPurpose`, as `CardSpan` uses. `domain/provenance.py` adds `SourcedArtifactMetadata` (ac5). |
| `numbered-snapshot` | Done | `evidence/numbered_snapshot.py`: rendering, the offset map both ways, passage and span resolution, and conversion to `EvidenceSelection` and `EvidenceMarkupSpan`. |
| `card-prompts` | Done | `prompts/card/select.md` and `prompts/card/markup.md` at 1.0.0, `released`, locked with `uv run scripts/lock_prompts.py` (`locked card.markup@1.0.0`, `locked card.select@1.0.0`). |
| `anti-authoring-guard` | Done | `evidence/selection_guard.py`, plus the `check` hook in `application/structured_output.py` and the fail-closed call site `application/card_selection.py` (Deviations 1 and 2). |
| `offline-round-trip` | Done | Fake router over `tests/fixtures/model_outputs/card.*`, replay router over `tests/fixtures/model_cassettes/card.*`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the three models are Pydantic with `extra=forbid`, holding only ids, offsets, enums, tag text, rationale and confidence; no evidence or quote field | PASS | `uv run pytest packages/debate_core/tests/evidence/test_selection_contract.py -k schema` → `25 passed`. Pins each model's field set by hand, that the only free-text fields are `TagSuggestion.text`, `CardSelection.rationale` and `MarkupSuggestion.rationale`, that an evidence key is refused at the top level, in the tag, in a passage and in a span (by the schema and by t05's strict validator), the enums shared with `CardSpan`, and strict bounds. |
| ac2: `card.select` and `card.markup` registered with semver, rendering `[P1]`, `[P2]`, ... plus the need, routed to `complex_reasoning` | PASS | `... -k prompt` → `6 passed`: both registered at 1.0.0, released, `complex_reasoning`, the schema classes, their variables, both in `prompts.lock.json`, and the rendered user turn written by hand. `uv run scripts/lock_prompts.py --check` passes inside `packages/debate_core/tests/integrations/models/test_prompt_lock.py` (in the 508-test run below). |
| ac3: the guard refuses out-of-bounds or inconsistently overlapping offsets and 12-word verbatim runs in the tag or rationale, raising `ModelOutputError` | PASS | `... -k guard` → `56 passed`. Covers each of the nine offset cases and each accepted boundary, 11 words passing and 12 and 13 refused, case, punctuation, whitespace, a straight apostrophe against a curly one, a run across a paragraph break and NFD input, every free-text field. Through the guard with `fail_closed=True`: one repair, then `ModelOutputError` with `attempts == 2` and `fail_closed is True`. The sentinel phrase is in the snapshot and the tag, and appears in no error string, repr, problem, attempt record, log message or log extra, and not in the repair's problem list. |
| ac4: recorded selection offsets passed to v1-e03-t03 extraction reproduce evidence byte-identical to the snapshot slice | PASS | `... -k round_trip` → `5 passed`. For both the fake fixture and the replayed cassette: segments `[163, 238)` and `[299, 360)`, omitted `[238, 299)`, and each segment's UTF-8 bytes equal to the hand-written text and to `SOURCE[a:b]`. The five marked spans, built into v1-e03-t03's `CardMarkup`, slice the hand-written words. Curly quotes, em and en dashes, `é`, `É`, 🌍 and 😬 all sit before offsets that matter (the first segment starts at code point 163, which is UTF-8 byte 177). |
| ac5: a generated artifact cannot be built or stored without its response metadata and inputs | PASS | `... -k artifact` → `12 passed`: bare metadata refused (`model_type`), metadata missing (`missing`), stored metadata without `snapshot_ids` or without `retrieval_ids` does not load, metadata naming no, another or an extra snapshot is refused, metadata for the other prompt is refused, and the JSON round-trips. **By type:** with the `# pyright: ignore` removed from the line passing bare metadata, `uv run pyright packages/debate_core/tests/evidence/test_selection_contract.py` → `error: Argument of type "GeneratedArtifactMetadata" cannot be assigned to parameter "metadata" of type "SourcedArtifactMetadata"`, `1 error`. Restored afterwards. |
| Node `selection-schemas`: schema tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_selection_contract.py -k schema` → `25 passed in 1.90s` |
| Node `numbered-snapshot`: offset map tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_numbered_snapshot.py` → `42 passed in 6.72s` |
| Node `card-prompts`: `prompts/card/select.md` contains `prompt_id: card.select` | PASS | `grep -c "prompt_id: card.select" prompts/card/select.md` → `1` |
| Node `anti-authoring-guard`: guard rejection tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_selection_contract.py -k guard` → `56 passed in 1.74s` |
| Node `offline-round-trip`: round-trip test passes offline | PASS | `uv run pytest packages/debate_core/tests/evidence/test_selection_contract.py` → `99 passed in 1.71s` |
| Node `offline-round-trip`: import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 16 kept, 0 broken.` |

### Shown red first

Tests were written after a first implementation existed. To show them red, I swapped the
committed implementation (`b574e2e`) for a refuse-nothing skeleton: open, unfrozen, unbounded
schemas; an offset map with no bounds or ordering checks; a guard whose three functions return
`()`; the structured-output guard ignoring `check`; `SELECTION_POLICY` with `fail_closed=False`;
artifacts accepting any metadata or none; `with_inputs` returning the bare type. Against it, the
two new test files gave **`81 failed, 60 passed`**. The 60 that passed are the ones a
refuse-nothing skeleton should pass: accepting valid answers and boundaries, conversions of valid
input, rendering, prompt registration and locking, the round trip on valid recorded data, field-name
and enum pins, and the strict-type refusals that t05's validator makes, which the skeleton did not
touch. Restored with `git checkout -- packages/debate_core/src`: `141 passed`.

### Mutation run

20 mutants, each applied alone to the committed code and run against the two new test files
(`.venv/bin/python -m pytest <both files> -p no:randomly -n 0`), **each run with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory** (agreement 8), restored after each.
No mutant errored at collection. The PM's six are in bold.

| Mutant | Result | Caught by (among others) |
|---|---|---|
| **An evidence field accepted** (`evidence_text: str \| None` on `CardSelection`) | caught, 5 failed | `test_schema_fields_are_only_ids_offsets_enums_tag_rationale_and_confidence`, the free-text field pin, the no-evidence-names pin |
| Extra keys ignored on `SelectedPassage` | caught, 1 failed | `test_schema_refuses_an_evidence_field_at_every_depth[in-a-passage]` |
| **An offset one past the end** accepted by the offset map | caught, 9 failed | `test_guard_refuses_a_selection_whose_offsets_name_no_characters_or_overlap[end-one-past-the-end]`, `[end-one-past-the-last-paragraph]`, the markup `end-one-past-the-paragraph` case, the offset-map tests and both properties |
| A passage may start at its paragraph's end | caught, 2 failed | `...[starts-at-the-end]`, `test_passage_range_refuses_what_names_no_characters[start-at-end]` |
| **An offset outside the selected paragraphs** (markup containment check removed) | caught, 8 failed | the six `outside_selection` cases, `test_guard_markup_outside_the_selection_is_refused_fail_closed`, the message test |
| Markup checked against whole paragraphs, not passages | caught, 4 failed | `partly-before-the-selection`, `one-character-before`, `across-the-cut`, `past-the-selection-end` |
| Overlapping passages accepted | caught, 2 failed | `[overlapping]`, `[one-inside-another]` |
| Same-style overlap accepted | caught, 2 failed | `two-underlines-overlap`, `two-highlights-overlap` |
| Highlight need not be underlined | caught, 2 failed | `highlight-runs-past-its-underline`, `highlight-with-no-underline` |
| **12-word threshold at 11** | caught, 3 failed | `test_guard_allows_eleven_consecutive_snapshot_words`, `test_guard_counts_whole_words_only` (and the constant pin) |
| **12-word threshold at 13** | caught, 6 failed | `test_guard_refuses_twelve_or_more_consecutive_snapshot_words_and_counts_them[12]`, the `punctuation`, `whitespace`, `across-a-paragraph-break` and `decomposed` cases, all exactly 12 words (and the constant pin) |
| Snapshot words not case-folded | caught, 8 failed | the 12 and 13 cases (the sentinel starts with a capital), `case`, `punctuation`, ... |
| Field not put in NFC | caught, 1 failed | `test_guard_word_runs_ignore_case_punctuation_and_whitespace[decomposed]` |
| **The guard's message quotes the matched snapshot words** | caught, 2 failed | `test_guard_quoted_text_problem_never_holds_the_words`, the sentinel test through `ModelOutputError` |
| The guard's message quotes the field | caught, 2 failed | the same two |
| **`fail_closed` dropped** (`SELECTION_POLICY` with `fail_closed=False`) | caught, 4 failed | the sentinel test, `test_guard_markup_outside_the_selection_is_refused_fail_closed`, `test_guard_an_answer_that_does_not_fit_the_schema_is_refused_fail_closed`, the policy pin |
| `select` passes no check to the guard | caught, 2 failed | the sentinel test, `test_guard_out_of_bounds_selection_is_repaired_once_and_a_good_repair_is_kept` |
| The structured-output guard ignores `check` | caught, 3 failed | the same, and the markup test |
| `with_inputs` returns the bare metadata type | caught, 18 failed | every test that builds an artifact |
| Artifact provenance not checked | caught, 4 failed | `test_artifact_metadata_must_record_exactly_its_snapshot` (3 cases), `test_artifact_metadata_must_be_for_its_own_prompt` |

The offset-map properties were checked for what they generate
(`--hypothesis-show-statistics`, fresh database): 200 examples each, 1 to 5 paragraphs, and an
astral character (an emoji) in 69 to 75% of them.

### Checks before the report (agreements 8 and 10)

* **Affected set: not run, left to CI.** `uv run scripts/affected_tests.py` selects 459 of the
  repository's 478 test files. The root `conftest.py` imports
  `debate_core.integrations.models.fake_router`, which imports
  `debate_core.application.structured_output`, which this task changed. That is the whole selection
  in effect, about six minutes, so under agreement 10 it is the pull request's `ci` check, with no
  hand-off.
* **Instead, within two minutes**, the test directories of what changed and the always-run list:
  * `.venv/bin/python -m pytest packages/debate_core/tests/evidence packages/debate_core/tests/domain packages/debate_core/tests/integrations/models tests/scripts/test_lock_prompts.py -n auto -m "not slow and not live"`
    under `perl -e 'alarm 115'`. The first run gave `1 failed, 2920 passed`: v1-e03-t07's
    `test_card_mapping_arithmetic_exists_once_in_the_whole_tree` flagged the numbered snapshot's
    inverse map (Deviation 3). After the fix, that test passes, and fails again for both a planted
    second subtraction and a removed allowed one.
  * `.venv/bin/python -m pytest packages/debate_core/tests/application tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py -n auto -m "not slow and not live"`
    under `perl -e 'alarm 115'` → `4179 passed in 109.64s`.
  * The two suites that log through the structured-output guard's logger, in one process after
    each other: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_structured_output.py packages/debate_core/tests/evidence/test_selection_contract.py -n 0 -p no:randomly`
    → `149 passed`.
  * t04's and t05's suites: `packages/debate_core/tests/application/test_structured_output.py`,
    `packages/debate_core/tests/integrations/models` and `tests/scripts/test_lock_prompts.py` →
    `508 passed in 4.04s`.
* `uv run ruff format --check .` → `1326 files already formatted`; `uv run ruff check .` →
  `All checks passed!`; `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0
  informations`; `uv run lint-imports` → `Contracts: 16 kept, 0 broken.`;
  `uv run python scripts/check_thin_handlers.py` → `OK: 54 CLI command and API route handlers
  within 25 statements`; `uv run python scripts/check_command_blocks.py` → `OK`;
  `uv run python scripts/check_links.py` → `OK: 2344 relative links and anchors in 353 Markdown
  files`; `uv run scripts/validate_specs.py` → `OK: 451 files, 40 epics, 389 tasks, 22 releases`.

## Files changed

* **`packages/debate_core/src/debate_core/evidence/`** (in `constraints.packages`):
  `selection_contract.py` (the schemas and artifact types), `numbered_snapshot.py` (the renderer and
  offset map), `selection_guard.py` (the anti-authoring guard).
* **`packages/debate_core/src/debate_core/domain/provenance.py`** (in `constraints.packages`):
  `SourcedArtifactMetadata`, which `with_inputs` now returns. Both of `with_inputs`' arguments are now
  required.
* **`prompts/card/`** (in `constraints.packages`): `select.md` and `markup.md`.
* **Outside `constraints.packages`** (Deviations 1 to 3): `application/structured_output.py` (the
  `check` hook), `application/card_selection.py` (the call site), `prompts/prompts.lock.json` (the
  two new entries, written by `lock_prompts.py`), `prompts/README.md` (two lines now point at the
  real prompt), the two new test files under `packages/debate_core/tests/evidence/`, the allowance
  in `packages/debate_core/tests/evidence/test_card_mapping.py` (its scan is now a function, with
  four tests of the allowance), a new section in
  `packages/debate_core/tests/application/test_structured_output.py` (the optional check), and
  four fixture files under
  `tests/fixtures/model_outputs/card.{select,markup}/` and `tests/fixtures/model_cassettes/card.{select,markup}/`.
* **`plan_specs/.../t06-card-selection-contract.yaml`**: phase `Succeeded`, and the PM's rulings
  of 2026-10-25 as a comment above `acceptanceCriteria`.

## Deviations from the spec

1. **A `check` hook on t05's `StructuredOutputGuard.generate`** (`debate_core.application`,
   outside `constraints.packages`). The PM asked for the anti-authoring guard to raise
   `ModelOutputError` "through the guard's path". The guard's check needs the snapshot, which schema
   validation never sees. So `generate` takes an optional `check(output) -> problems`, and treats
   its problems exactly as validation problems: one repair, then `ModelOutputError`, the same
   attempt records, logs and policy. With `check` unset nothing changes: t05's suite passes
   unchanged (`508 passed` with t04's). A consequence the PM should agree to: **an answer the
   guard refuses gets the one repair**, whose prompt lists the guard's problems (counts, field
   names, offsets). It is not refused on the first answer. **PM ruling, 2026-10-25: keep the
   repair**, with the two-sentinel test extended to this path and the no-check behaviour pinned.
2. **The call site `debate_core/application/card_selection.py`** (outside `constraints.packages`).
   The spec puts the guard in `debate_core.evidence`, but the layers contract keeps `evidence` below
   `application`, where `StructuredOutputGuard`, `ModelOutputError` and `OutputProblem` live. So the
   evidence module returns its own `GuardProblem` values, and `CardSelector` in the application
   layer converts them, runs both prompts with `SELECTION_POLICY = ValidationPolicy(fail_closed=True)`,
   and builds the artifacts. It is the only code that calls `card.select` or `card.markup`, which is
   how "never without fail_closed=True" is held. **PM ruling, 2026-10-25: accepted.** The PM adds
   `debate_core.application` to `constraints.packages` in a PM batch; until then it stays recorded
   here.
3. **One allowance in v1-e03-t07's "the card mapping exists once" scan**
   (`test_card_mapping_arithmetic_exists_once_in_the_whole_tree`). The scan flags every `x - y.start`
   in the tree outside `card_mapping.py`. The numbered snapshot's inverse map,
   `snapshot_offset - self.source.paragraphs[position].start`, has that shape: it makes a snapshot
   offset relative to its paragraph and never touches `evidence_text`. The spec's renderer node
   requires it ("tested both ways"). I could have reshaped the line to slip past the scanner, which
   would silently weaken the check. Instead I allowed that one expression by its exact text in the
   test. Shown: a planted second subtraction in `numbered_snapshot.py` fails the check, and so does
   removing the allowed line. **PM ruling, 2026-10-25: accepted, with conditions**: the allowance
   names the file and the exact expression with a comment citing the ruling, and both failing cases
   are kept as tests. Both are done.
4. **Names the spec did not give.** The spec names `CardSelection`, `MarkupSpan` and
   `TagSuggestion`. `card.markup` needs an output schema of its own, so `MarkupSuggestion` (spans
   and a rationale) is added, and the kept artifacts are `GeneratedCardSelection` and
   `GeneratedCardMarkup`. The README's illustrative schema path,
   `debate_core.evidence.card_selection`, became the spec's output file, `selection_contract`.
5. **`with_inputs` changed shape** (v1-e05-t04's API, in `debate_core.domain`): it returns
   `SourcedArtifactMetadata`, and `snapshot_ids` and `retrieval_ids` have no defaults. Nothing in
   `src` called it; t04's one test passes both and still passes.

No schema needed coercion. Validation stays t05's strict JSON with extra keys forbidden.

## PM rulings of 2026-10-25 and the work they asked for

The PM answered the three questions during the session. The rulings are recorded as a comment
above the task's `acceptanceCriteria` (it parses as a comment: the criteria and context are
unchanged, and no ruling text is in the loaded document).

1. **Keep the repair.** No code change was needed: the guard's refusals already took t05's path.
   * **The two-sentinel test, extended to the check path.**
     `test_guard_quoted_tag_is_refused_after_one_repair_and_nothing_quotes_it` now follows
     t05's `test_repair_sentinels_the_answers_reaches_nothing_and_the_calls_reaches_only_the_repair`.
     `SENTINEL` sits in the snapshot (P4) and in the refused tag. `NEED_SENTINEL` sits in the
     call's research need. In the rendered repair, `SENTINEL` occurs once, exactly as often as in
     the original prompt, and only inside the rendered `[P4] ...` block. No sentinel word remains
     once that block is removed, and `failed_user` equals the original rendered user turn.
     `NEED_SENTINEL` occurs once. No repair variable other than `failed_user` holds either
     sentinel. Neither is in the error's traceback, args, problems or attempt records, the error has
     no `__cause__` or `__context__`, and neither is in any log record's message or
     `repr(vars(record))`.
   * **The optional hook, pinned** in t05's suite:
     `test_check_is_optional_and_unset_by_default` (keyword-only, default `None`);
     `test_a_call_without_a_check_behaves_as_t05s_guard_does`, for a valid, a repaired and a
     refused call, where omitting `check`, passing `None` and passing a check that finds nothing
     give the same router calls and the same result or error, matching the hand-written prompt
     sequence and ending; and
     `test_check_problems_are_repaired_then_refused_like_validation_problems`, which checks both
     answers, puts the check's problem in the repair prompt, and ends with `attempts == 2` and
     `fail_closed`.
2. **The two application files are accepted**, and recorded in Deviations until the PM batch.
3. **The allowance is accepted, with conditions.** The allowance in `test_card_mapping.py` now
   carries a comment citing the ruling, and names `PARAGRAPH_MAP_MODULE` and the exact
   expression. The scan is a function (`_scan`, `_strays`), so the cases I had shown by hand are
   kept tests: the module as it is passes; a second subtraction in the same file fails; the
   allowed expression in any other file fails; the allowed line removed fails. ac4's round trip
   (the numbered snapshot's map, then v1-e03-t03's extraction and `CardMarkup`) is the evidence
   the two maps agree on non-ASCII text.

### Mutation run on the new tests

Six more mutants, the same way: each alone, a fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run,
restored after, run against `test_structured_output.py`, `test_selection_contract.py`,
`test_numbered_snapshot.py` and `test_card_mapping.py`. All six were caught, and none errored at
collection.

| Mutant | Result | Caught by |
|---|---|---|
| The repair's answer is not checked (check on the first attempt only) | caught, 3 failed | `test_check_problems_are_repaired_then_refused_like_validation_problems`, the card-path sentinel test, `test_guard_markup_outside_the_selection_is_refused_fail_closed` |
| A call without a check gets a default check that finds nothing | caught, 1 failed | `test_check_is_optional_and_unset_by_default` only. That mutant behaves the same as no check, so only the signature pin can see it, as "optional" requires. |
| The allowance no longer requires its exact line | caught, 2 failed | `test_the_allowance_refuses_a_second_subtraction_in_the_paragraph_map_module`, `test_the_allowance_fails_when_the_allowed_line_is_gone` |
| The allowance admits the expression in any file | caught, 1 failed | `test_the_allowance_refuses_the_allowed_expression_in_any_other_file` |
| The quoted-text problem quotes the matched words | caught, 2 failed | `test_guard_quoted_text_problem_never_holds_the_words`, the card-path sentinel test |
| The guard's problems carry the research need | caught, 2 failed | the card-path sentinel test, `test_guard_out_of_bounds_selection_is_repaired_once_and_a_good_repair_is_kept` |

### Checks after the rulings

* `.venv/bin/python -m pytest packages/debate_core/tests/evidence packages/debate_core/tests/application/test_structured_output.py packages/debate_core/tests/integrations/models tests/specs tests/architecture -n auto -m "not slow and not live"`
  under `perl -e 'alarm 115'` → `2260 passed in 16.86s`.
* The logging suites in one process,
  `.venv/bin/python -m pytest packages/debate_core/tests/application/test_structured_output.py packages/debate_core/tests/evidence/test_selection_contract.py -n 0 -p no:randomly`
  → `154 passed`.
* `uv run ruff format --check .` → `1326 files already formatted`; `uv run ruff check .` →
  `All checks passed!`; `uv run pyright packages/debate_core` → `0 errors` (a first run found an
  untyped lambda in the new t05 test, committed before pyright ran; fixed in the next commit);
  `uv run lint-imports` → `16 kept, 0 broken`; `uv run scripts/validate_specs.py` → `OK`.
* The affected set is still the whole selection in effect, and is left to the pull request's `ci`.

## Decisions and assumptions

The PM asked for the 12-word rule, the offset unit and "overlap inconsistently" to be defined
here before anything was built. These three definitions were written and committed first, and the
code and tests implement them as written.

### The 12-word rule (the anti-authoring guard, ac3)

* **Words.** A word is a maximal run of characters that Python's `re` matches as `\w` (Unicode
  letters, digits, combining marks and `_`). Everything else separates words and is otherwise
  ignored: spaces, line breaks and paragraph breaks, punctuation, straight and curly quotes, dashes,
  emoji. So `Senate’s` is the two words `senate` and `s`, and `52–48` is `52` and `48`, the same
  way on both sides.
* **Normalization before comparing.** The free-text field is put in Unicode NFC (the snapshot's
  normalized text already is, by `evidence-normalizer-v1`), and every word on both sides is
  compared case-folded (`str.casefold`). Case is therefore normalized, punctuation and whitespace
  are not compared at all, and nothing else is folded (no accent stripping, no quote folding).
* **The rule.** A field is refused when 12 consecutive words of it are equal to 12 consecutive
  words of the snapshot's normalized text, anywhere in the snapshot, across paragraph breaks too.
  11 consecutive shared words pass. A run counts whole words only: a field that starts in the
  middle of a snapshot word shares that word only if the whole token matches.
* **Fields checked.** Every string value anywhere in the answer, found by walking the validated
  output, not a list of field names: today that is the tag's `text` and each `rationale`. A string
  field added later is covered without anyone remembering to add it.
* **What the refusal says.** A problem of type `quoted_snapshot_text` at the field's location,
  naming how many consecutive words matched and the snapshot offsets they span. Never the words.

### Offsets

* **What the model gives:** a paragraph number `N`, the one shown as `[PN]` in the prompt (the Nth
  paragraph of the snapshot's paragraph map, counted from 1), and offsets into **that paragraph's
  normalized text**, half-open `[start, end)`, where 0 is the first character after the `[PN] `
  label.
* **The unit is Python `str` indices, which count Unicode code points**, into the snapshot's
  normalized text (`SnapshotText.text`). A paragraph offset becomes an absolute one by adding the
  paragraph's `start`, which is the unit `v1-e03-t03`'s `OffsetRange` and the normalizer's
  `OffsetMap` already use, so nothing converts between the contract and extraction.
* **Why code points.** It is what Python slices, so `text[start:end]` is the evidence with no
  conversion step to get wrong. UTF-8 bytes would make an `é` two units and an emoji four; UTF-16
  units (what JavaScript counts) would make an emoji two. Paragraph-relative rather than absolute
  because the `[PN] ` labels would otherwise shift every offset the model reads, and because a model
  counts more reliably within one paragraph than across a document.
* **The limit of the check.** A model that miscounts (say, an emoji as two) but stays in bounds
  selects different words of the real snapshot, never words it wrote. The guard cannot detect
  that; the selection is still sliced from the snapshot and is what a reviewer sees.

### "Overlap inconsistently", and the other offset refusals

The guard refuses an answer, with a named problem type, in each of these cases. Each one has a
test.

Selection (`CardSelection.passages`):

1. A paragraph number above the snapshot's paragraph count (`paragraph_out_of_bounds`; 0 and
   negatives are refused by the schema).
2. A passage whose `last_paragraph` comes before its `first_paragraph` (`reversed_range`).
3. A `start_offset` at or past the end of its first paragraph, or an `end_offset` past the end of
   its last paragraph: one past the end is refused, the end itself is allowed, since `end` is
   exclusive (`offset_out_of_bounds`).
4. A passage that selects nothing once resolved (`empty_range`).
5. Two passages that share a character (`overlapping_passages`). Passages that only touch are
   allowed: extraction joins them into one segment.

Markup (`MarkupSuggestion.spans`, checked against the selection it marks up):

6. A span in a paragraph the snapshot does not have, or ending past its paragraph's end
   (`paragraph_out_of_bounds`, `offset_out_of_bounds`), or marking nothing (`empty_range`,
   `reversed_range`).
7. A span that is not wholly inside one selected passage, after touching passages are joined:
   a span in a paragraph outside the selection, one that runs partly outside it, or one that crosses
   the gap between two passages (`outside_selection`).
8. Two spans of the same style that share a character (`overlapping_same_style`).
9. A highlighted character that no underline covers (`highlight_not_underlined`).

An underline and a highlight overlapping is the convention (what is read aloud is underlined), not
an inconsistency. Rules 7 to 9 are the ones `v1-e03-t03`'s `CardMarkup` enforces after extraction.
The guard checks them first, on the model's answer, so the model gets its one repair with the
problem named, and `CardMarkup` checks them again on the extracted evidence.

### Other choices the spec left open

* **What a passage looks like.** `first_paragraph`, `last_paragraph`, `start_offset` (default 0)
  and `end_offset` (default `null`, the end of `last_paragraph`). One passage can run across
  paragraph breaks, so a contiguous cut never shows a false ellipsis. Several passages are a card
  with cuts, which v1-e03-t03 records as omitted ranges.
* **The tag's alignment** is two enums: `argument_role` (uniqueness, link, internal link, impact,
  the debate-need guidance the plan names) and `need_alignment` (direct, partial, tangential).
  Each has its own confidence beside the selection's.
* **Quoted text is checked against the whole snapshot**, not only the selected range, so a tag
  cannot quote a paragraph the card did not select either.
* **`card.markup` is shown only the paragraphs the selection touches**, numbered as in the whole
  snapshot, with the passages as resolved numbers. Offsets mean the same in both prompts.
* **Prompt versions are pinned in code** (`CARD_SELECT_VERSION`, `CARD_MARKUP_VERSION`, both
  1.0.0, overridable when a `CardSelector` is built), because t05's `PromptCatalog` resolves exact
  versions only. Promotion of `latest` is v1-e09-t04's.
* **The fixtures are hand-written answers filed under computed keys.** The scratch step ran
  `CardSelector` once against a `ScriptedModelRouter` holding the two hand-written answers, only to
  capture the exact requests. It then filed each answer with `FixtureDirectory.write` and
  `CassetteDirectory.write_structured`, as `tests/fixtures/model_cassettes/README.md` says to. The
  cassette's route (`example-recorded-model`, `example-region-1`) is invented. No record mode was
  used.
* **Replay reports provider `fake`**, as t03 designed: a recorded answer never passes for a
  billed one. The round-trip test asserts that and the recorded model id.

## Operator follow-ups

None. The affected set is the whole selection in effect, which the pull request's `ci` runs
(agreement 10).

## Follow-up work

* **PM batch:** add `debate_core.application` to this spec's `constraints.packages` (ruling 2).
* **v1-e06-t02-card-service** consumes this: `CardSelector.select` then `mark_up` on a
  `LoadedSnapshot`, `NumberedSnapshot.evidence_selection` and `markup_spans` into extraction and
  `CardMarkup`, and a `ModelOutputError` (with `fail_closed=True`) mapped to an UNVERIFIED card.
* **Long sources.** `card.select` renders the whole snapshot, and `SnapshotWords` indexes every
  12-word run of it. Both are fine for an article; a book-length snapshot would want a
  paragraph window chosen before the call, which belongs with v1-e06-t02.
* **A model that miscounts within bounds** selects real but wrong words (see *Offsets*). Only the
  quality evals can measure how often (v1-e09-t03). A cheap aid would be to print each paragraph's
  length beside its label, which is a prompt version bump.
* **Source text that contains a literal `[P3]`** is rendered as it is and could confuse a model,
  though never an offset. If evals show it matters, a later renderer version could mark labels
  more distinctly.
* **Real cassettes** for `card.select` and `card.markup` need record mode to keep invalid answers
  (v1-e05-t10) and an operator recording run.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

The contract ADR-006 needed: the model selects, it never authors, and every refusal is named
without quoting.
1. **ac1 to ac5 pass.** The three definitions the PM asked for (the 12-word rule, the offset unit,
   and "overlap inconsistently" as nine named cases) were committed before the code, and the tests
   implement them as written.
   * Code points, paragraph-relative, are the right unit: they are what Python slices and what
     v1-e03-t03 already uses. ac4's round trip proves it byte for byte on curly quotes, dashes,
     accents and emoji.
   * ac5 is enforced by type as well as by test, as asked. Pyright refuses the bare metadata.
2. **Red and mutants.** The tests were written after a first implementation, and shown red by
   swapping in a refuse-nothing skeleton: 81 failed and 60 passed, each pass of the expected kind.
   That is accepted. 26 of 26 mutants were caught, including the PM's six and six more on the
   rulings' work.
3. **The rulings of 2026-10-25 are done as asked:**
   * the two-sentinel test extended to the check path;
   * the optional hook pinned three ways (absent, `None`, a check that finds nothing);
   * the allowance named by file and exact expression, with a citing comment, and its four failure
     cases kept as tests.
   The default-check mutant being caught only by the signature pin is correct, and saying so was
   right.
4. **Accepted as made:**
   * Deviations 1 to 5. The PM's batch of 2026-10-25 (o) adds `debate_core.application` to
     `constraints.packages`;
   * walking every string in the answer rather than a list of fields, so a later field is covered;
   * checking quotes against the whole snapshot;
   * `card.markup` shown only the touched paragraphs, numbered as in the whole snapshot;
   * versions pinned in code until v1-e09-t04;
   * hand-written answers filed under computed keys, with no record mode.
5. **The affected set** is the whole selection in effect, so it is left to the PR's `ci` under
   agreement 10. Everything that changed passed within the limit (4,179 and 2,260), with the logging
   suites run in one process.
6. **Follow-ups:** v1-e06-t02 consumes this, with `ModelOutputError` mapped to an UNVERIFIED card.
   Long sources need a paragraph window there. Miscounting within bounds is for v1-e09-t03's evals.
   Real cassettes need v1-e05-t10.

No re-review is needed.

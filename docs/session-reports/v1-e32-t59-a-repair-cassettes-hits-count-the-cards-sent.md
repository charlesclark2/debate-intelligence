# Session report: v1-e32-t59-a-repair-cassettes-hits-count-the-cards-sent

| | |
|---|---|
| Task | `v1-e32-t59-a-repair-cassettes-hits-count-the-cards-sent` — A repair cassette's scan counts a hit as input only when its words come from the cards the failed call sent |
| Spec | [`plan_specs/v1/e32-argument-landscape/t59-a-repair-cassettes-hits-count-the-cards-sent.yaml`](../../plan_specs/v1/e32-argument-landscape/t59-a-repair-cassettes-hits-count-the-cards-sent.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t59-a-repair-cassettes-hits-count-the-cards-sent` |
| Session status | COMPLETE |

## Summary

A repair cassette's scan hit is now `in_input` only when its words occur in the cards the failed call
sent, as the PM ruled on 2026-11-06 (v1-e32-t55, point 2(A)). Before this change, every word of the failed
call's rendered prompt counted as sent. `repair_cassette_hits` (in
`debate_core.arguments.landscape.scan_hits`) now reads the cards from the cassette's own recorded request:
every JSON list in the failed call's rendered turns that holds a card (an object with a heading path, tag,
cite or excerpt key). It takes their words the same way a first call's cassette takes the words of its
`items`. A hit found only in the classify prompt's own instructions or preamble, in the cards' JSON keys,
in the repair call's answer, or in the metadata is no longer `in_input`. So its trusted mark sets it aside,
as it would in a first-call cassette. A failed prompt that holds no card list keeps the rule from before
this task: every word of it counts as sent. That keeps the forbidden case (a hit in the cards sent set
aside) out of reach even when the cards cannot be read. The first-call cassette, the prompt-input scan,
the team's-name mark and every other rule are unchanged.

**The PM should read this first:** t55's point 2 says a repair cassette's input "includes the model's own
failed answer". It does not: the repair prompt never carries the failed answer (see
[the first decision](#decisions-and-assumptions)). The 63 hits were `in_input` because the failed prompt's
own instructions hold their words. The rule as ruled covers that case anyway.

[The 63 hits, derived](#v1-e32-t55s-63-repair-cassette-hits-under-this-rule): under this rule, all 63
would have been set aside and the repair scan would have read clean, unless one of them is a phrase of two
or more words that spans two adjacent fields of a card. Neither report says whether any is.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-repair-cassettes-hits-count-the-cards` (Repair cassette scan) | Done | Tests first, committed alone (`c3d9e7c`, counts corrected in `716f039`). Shown red against the pre-task rule and against a skeleton that marked nothing in a repair cassette as in the input. Then the rule (`1a254f6`), then 8 mutants. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a repair cassette's hit from the failed answer alone is not in_input, while one from the cards sent still is, by tests on invented cassettes shown failing first | PASS | 18 new tests on invented cassettes: 17 in `test_repair_cassette_scan.py` and 1 in `test_landscape_model_stage.py`. All cassettes are invented, and written as the recorder writes one: `repair_prompt`, then a `ModelRequest` dumped as JSON. **Red, against the pre-task rule** (the tests' commit `716f039`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape/test_repair_cassette_scan.py <the new evaluation test> <t44's repair evaluation test> -n 0 -q --tb=line` → **12 failed, 7 passed**, every failure an assertion. The rule's own tests failed, each where an instruction word or answer word was pinned as not in the input, or where the scan was pinned clean. **Red, against a skeleton that marked nothing in a repair cassette as in the input** (`sent=""`, applied to the same commit and restored with `git checkout HEAD --`) → **12 failed, 7 passed**, every failure an assertion. This time the guards failed: a word in a card's tag, heading, cite or excerpt kept; a school spelled like a key kept when a card sent it; the second card of a batch read; no card list or only the positions list keeps the old rule; the counts; the registry-rendered prompt; t44's prose-only repair test. Three tests pass under both, because neither rule changes what they check: a team code in the answer is kept (no trusted mark), and the two first-call tests. **Green:** below. **Mutants:** 8 of 8 caught at an assertion ([Mutants](#mutants)). |
| Node: Repair cassette scan tests pass (`uv run pytest packages/debate_core/tests -k "cassette and scan"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests -k "cassette and scan" -q` → 26 passed in 59 s (most of it collecting debate_core's tests at a load average of about 10) |

### Green, and the checks before the report

Every test run was bounded by `scripts/hard_stop.py 115`.

| Command | Result |
|---|---|
| The four scan test files: `test_repair_cassette_scan.py`, `test_scan_marked_hits.py`, `test_evaluation_scan_hits.py`, `test_landscape_model_stage.py` | 111 passed in 4 s |
| The other readers of repair hits: `test_landscape_evaluation_breakdown.py`, `packages/debate_cli/tests/test_landscape_command.py`, `tests/smoke/test_landscape_evaluate_smoke.py` | 159 passed in 15 s |
| `uv run scripts/affected_tests.py --run` | 122 of 734 test files (16.6%) from 5 changed files. **Stopped by `hard_stop` at its 115-second limit**, at a load average of 13 from other work on the Mac. It is over two minutes, so it is left to the pull request's `ci` (agreement 10), with no hand-off. The parts below ran instead. |
| The always-run list: `tests/architecture/ tests/specs/` and the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | 378 passed in 20 s |
| The affected set's landscape, coach-sample and evaluation files (`packages/debate_core/tests/arguments/landscape/`, `application/test_landscape_*`, `application/test_coach_*`, `debate_cli/tests/test_landscape_*`, `tests/smoke/test_landscape_*`) | 411 passed in 20 s |
| The whole changed module's directory, `packages/debate_core/tests/arguments/landscape/` | 1293 passed in 5 s |
| The affected set's other `packages/debate_cli/tests/` files | 506 passed in 78 s |
| `uv run ruff format --check .`, `uv run ruff check .` | 2032 files already formatted; all checks passed |
| `uv run pyright packages/debate_core` | 0 errors |
| `uv run lint-imports`, `uv run python scripts/check_thin_handlers.py` | 20 contracts kept, 0 broken; 73 handlers within 25 statements |
| `uv run scripts/validate_specs.py` (after the phase was set) | OK: 655 files, 41 epics, 592 tasks, 22 releases |
| `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py` | OK; OK (3732 relative links and anchors) |

The affected set's `tests/scripts/` (31 files) and `tests/docs/` (13 files) did not run here. They are
reached by the spec's phase change and this report, not by the code.

### Mutants

Each mutant was applied to the committed rule (`1a254f6`), and both test files were run with `-n 0`. Then
the file was restored with `git checkout HEAD --`. Each mutant was caught by a FAILED assertion, none by an
error. No Hypothesis property is involved.

| Mutant | Failed | Caught by (first named) |
|---|---|---|
| The pre-task rule: the whole repaired prompt is sent | 12 | `test_repair_cassette_scan_marks_no_hit_outside_its_cards_as_in_the_input` |
| Nothing in a repair cassette is in the input | 12 | `test_repair_cassette_scan_keeps_a_word_its_cards_sent[tag]` |
| No fallback: a prompt with no card list sends nothing | 3 | `test_repair_cassette_scan_with_no_card_list_counts_its_whole_failed_prompt_as_sent`, and t44's prose-only evaluation test |
| Cards read from the system turn alone | 12 | `test_repair_cassette_scan_marks_no_hit_outside_its_cards_as_in_the_input` |
| Any JSON list counts as cards (the positions too) | 2 | `test_repair_cassette_scan_with_only_the_positions_list_counts_its_whole_failed_prompt_as_sent` |
| The cards' JSON keys count as their words | 1 | `test_repair_cassette_scan_counts_a_cards_key_as_structure_not_a_card_sent` |
| Only the first card of a list is read | 1 | `test_repair_cassette_scan_reads_the_cards_in_every_card_of_the_list` |
| A first call's cassette also counts the positions it sent as input | 2 | `test_first_call_cassette_scan_marks_as_before_t59` |

## v1-e32-t55's 63 repair-cassette hits under this rule

This is derived from the rule and the figures recorded in v1-e32-t55's report only. No cassette was read,
and nothing was replayed.

**What t55 recorded.** It recorded 63 hits in 2 repair cassettes: 45 in the repaired prompt, 17 in the
model's rationale and 1 in the cassette metadata. Every hit carried a trusted mark, 53 a JSON key's name
and 10 a taxonomy word. None was a team's name, and all 63 were `in_input`. 53 + 10 = 63 and every hit
carries a trusted mark, so each hit carries exactly one. In the same recording the prompt inputs (every
batch's cards as sent) read **0 hits**. The operator judged all 63 to be ordinary words.

**Which of them the new rule keeps `in_input`.** A repair hit is now `in_input` only when its words occur in
the words of the cards its failed call sent. The repair prompt carries the failed call's rendered prompt
unchanged, so those cards are that batch's cards. The prompt-input scan read those cards field by field and
found no school, team-code word or tournament in any of them. So no hit's words occur within one field of
those cards. The one way a hit could still be `in_input` is a phrase of two or more words that spans two
adjacent fields of one card: the cards' words are joined field to field, as the first-call rule joins them.
t55's report does not say whether any of the 63 is a phrase like that. A single-word hit cannot be one.

**Unless such a phrase is among them, the outcome would have been:**

| | t55 as recorded | Under this rule |
|---|---|---|
| Repair-cassette hits `in_input` | 63 | 0 |
| Hits set aside (`sets_aside`) | 0 | 63: 53 a JSON key's name, 10 a taxonomy word |
| Texts set aside, texts left | 0, 2 | 2, 0 |
| `set_aside` | `{texts 0, hits 0, json_key 0, in_taxonomy 0}` | `{texts 2, hits 63, json_key 53, in_taxonomy 10}` |
| Repair cassettes `clean` | false | true |
| `scans_clean` (prompt inputs and cassettes were clean) | false | true |

This assumes each text's listing has a hit of every kind the scan counted in it, which the listing is built
to ensure (`v1-e32-t39`). The scan's counts and the hit listing are unchanged. Only the `in_input` mark, and
so `clean` and `set_aside`, would differ.

## Files changed

* **`debate_core.arguments.landscape.scan_hits`**: `repair_cassette_hits` reads the cards the failed call
  sent with the new `_cards_sent`, which finds every JSON list holding a card in the failed call's rendered
  turns (`_holds_a_card`, `_CARD_KEYS`). Their words become `in_input`'s sent text, and the whole repaired
  prompt is used only when no turn holds a card list. The docstrings of `in_input`, `MARKS_THAT_KEEP_A_HIT`
  and `repair_cassette_hits` now say so. `repair_cassette_hits`' docstring also dropped a stale sentence
  saying that the evaluation does not read repair cassettes; it has read them since `v1-e32-t40`.
* **Tests**: `packages/debate_core/tests/arguments/landscape/test_repair_cassette_scan.py` (new, 17 tests,
  all invented). In `packages/debate_core/tests/application/test_landscape_model_stage.py`: one new
  evaluation test (the bar reads a repair cassette whose marked words no card sent as clean, and one whose
  card sent the word as unclean), and the docstring of t44's repair test. That test's cassette holds no
  card list, so it now checks the fallback. Its assertions are unchanged and it still passes.
* **Spec**: the Goal's phase, `Succeeded`.

## Deviations from the spec

None. The rule, the tests and the files are within `constraints.packages`. The runbooks and
`docs/data/landscape-model-evaluation.md` already describe `in_input` as "in the cards sent", which is now
exactly what it means for a repair cassette too, so neither needed a change.

## Decisions and assumptions

* **The failed answer is never in a repair cassette.** t55's report and the spec's description both say a
  repair cassette's input "includes the model's own failed answer". The code says otherwise. `model.repair`
  1.0.0's changelog says "Nothing from the failed answer itself", and `repair_prompt` carries only
  `failed_prompt`, `failed_system`, `failed_user`, `schema_name`, `json_schema` and `problems`. A problem
  carries a location, a type and pydantic's message, never the value (`OutputProblem`). The recorder writes
  the repair call's request and its response, and nothing else (`record_replay.write_structured`). What
  made all 63 `in_input` was the rest of the failed call's rendered prompt: the classify prompt's own
  instructions (which name `confidence` and `rationale`, and use many common words), its user turn's
  preamble, and the cards' JSON keys. The model words in a repair cassette are the repair call's own
  answer. The rule as ruled ("only the cards the failed call sent") excludes all of these, so the build is
  exactly the ruling. The tests put the "answer's" key and taxonomy word in the repair call's recorded
  answer and in the failed prompt's instructions, which are the two places such words really are.
* **The cards are found in the recorded request, by shape.** `_cards_sent` reads every JSON list in
  `failed_system` and `failed_user` whose entries include an object with a card's free-text key (headings,
  tag, cite, excerpt). It reads them with `_fields_of_items`, the reader a first call's `items` already
  uses, so "in the cards sent" means the same in both kinds of cassette. The classify prompt's `positions`
  list holds no such key, so the taxonomy never counts as cards, as in a first call's cassette. A test
  renders the failed prompt through the committed classify prompt 1.3.1 and the stage's own answer schema,
  and shows that the cards are found in its real user turn.
* **No card list means the old rule (fail toward keeping).** A failed prompt from which no card list can be
  read keeps every word of itself as sent. Otherwise a cassette whose cards the scan could not parse would
  set aside a hit that is in those cards, which the spec forbids. Following the memory note "fallbacks mask
  mutants", the fallback has its own tests (prose only, positions only), and the no-fallback mutant is
  caught.
* **Keys are structure.** A school spelled like a card's key (`cite`) is found in the rendered cards' JSON
  as a key. It is not a card's words, so it is not `in_input`, and its JSON-key mark sets it aside. A first
  call's cassette never reads keys either (`v1-e32-t40`).
* **Where the hits are found is unchanged.** The repaired prompt is still scanned as one text per turn, and
  only the `in_input` mark changed: "every other rule is unchanged". A hit inside a card's field is always
  `in_input`, because its words are the card's.
* **The invented schema has no docstring.** Pydantic writes a model's docstring into its JSON schema's
  `description`, which the repair cassette carries as metadata. The test schemas' explanations are
  comments, so the metadata hits are the two that pydantic's rules give for a `confidence` field: its title
  and its `required` entry. The first hand count missed both and was corrected (`716f039`) before the rule
  was written.

## Operator follow-ups

None. The next repaired recording reports `in_input` by the new rule. If the operator wants the 63 settled
rather than derived, a replay of t55's recording would show it with no model call, but nothing here needs
one.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

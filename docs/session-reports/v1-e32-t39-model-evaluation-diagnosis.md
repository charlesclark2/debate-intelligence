# Session report: v1-e32-t39-model-evaluation-diagnosis

| | |
|---|---|
| Task | `v1-e32-t39-model-evaluation-diagnosis` — Why the model stage scored 36.8%: the evaluation broken down, and the scan's hits listed in the operator's terminal |
| Spec | [`plan_specs/v1/e32-argument-landscape/t39-model-evaluation-diagnosis.yaml`](../../plan_specs/v1/e32-argument-landscape/t39-model-evaluation-diagnosis.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t39-model-evaluation-diagnosis` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`landscape evaluate --breakdown` is built and tested (ac1), and the operator's replay of the kept
cassettes ran on 2026-11-01. It made no model call and reproduced the recording exactly. Its counts are
in [`docs/data/landscape-model-evaluation.md`](../data/landscape-model-evaluation.md).

**Why 36.8%:** the model's answers, not the batch or the sample.

* **The batch and the sample are not the cause.** The failed call was repaired and lost no card. The
  headings place none of the 47, so the bar's set is all 47. Weighted to the strata, the accuracy is
  37.9%.
* **Neighbouring positions.** All 9 wrong positions of the label's kind are neighbours on the same side
  (`rates-da` answered `economy-da`). Only 1 of the 34 positions involved has a description.
* **The other side.** 10 of the 11 other-kind answers name a position of the other side: the model names
  what a card is about, not the argument it is read in.
* **The weak spots.** Topicality is 1 of 7, and `generic-k` is refused 3 of 3.
* **Confidence does not separate them.** No threshold reaches the bar; the best is 66.7% at 0.85.

**The scan:** of 647 hit lines, 178 are one JSON key word and 445 are words of the committed taxonomy.
The 24 others are 9 real names in heading paths, which the scrub leaves in (other teams' tournaments and
codes), counted again in the cassettes and the repair cassette. The options for the PM are
[below](#questions-for-the-pm).

**The Goal stays `InProgress`.** ac2's run is done and its counts are recorded, but the spec says ac2 is
recorded by the PM, so the PM sets it on review. Also: the operator pasted the terminal hit listing into
this session. [Nothing from it was written down](#the-terminal-listing-reached-the-session).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-evaluation-diagnosis` (Evaluation breakdown) | Done | Its criterion passes; ac2's replay is the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the breakdown and the terminal-only hit listing work on synthetic fixtures and replay cassettes. Every labelled card falls in exactly one outcome, and the outcomes sum to the labelled count. The deterministic placement is shown beside each. Nothing hit-bearing reaches JSON output, a log or a file. Shown by tests that failed first | PASS | See [Tests](#tests-and-checks-run-before-this-report): `test_landscape_evaluation_breakdown.py` (12) records nine synthetic cards through the record-replay router, then replays them with no router behind it. Every outcome but `not_asked` is planted once or twice; `not_asked` has its own test. The outcomes are written out by hand and sum to 10. Stage one's placement is pinned per sample row. `test_evaluation_scan_hits.py` (13) covers the fields, kinds and synthetic scrub cases. The CLI tests (4) plant a distinctive hit: it is absent from `--json` stdout, from caplog at DEBUG and from every file under `tmp_path`, and it is shown only when stdout is a terminal. Red run: 22 failed against the skeleton; 20 mutants all caught |
| ac2: the operator's replay over the kept cassettes (operator, recorded by the PM) gives the counts recorded in `docs/data/landscape-model-evaluation.md`, and the PM has the options | PASS, for the PM to record | The operator's `--json … --breakdown` run (2026-11-01) exited 1 `EVALUATION_BELOW_BAR` with labelled 47, found 47, asked 47, calls 4, counted 38, correct 14 and tokens 30,460 / 3,881, the recording's counts exactly. `breakdown.outcomes` sum to 47. A second JSON-only run gave the hits' marks. Both are recorded in `docs/data/landscape-model-evaluation.md`, and the options are [below](#questions-for-the-pm). The spec marks ac2 as recorded by the PM, so the Goal phase is left for the PM to set |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 6 packages/debate_core/tests packages/debate_cli/tests -k evaluat` → **52 passed** in 9.97 s, after the last code commit |

## Checks shown failing for their reason

### The red run against a refuse-nothing skeleton

Before the implementations, a skeleton was swapped in (copies kept in the scratchpad, restored after):

* `card_outcome` called every card correct, and `deterministic_placement` placed nothing and sent
  everything;
* the model set's score was taken over every card, and the strata were not weighted;
* the scan found no hit;
* the stage recorded no batch;
* `--breakdown` ran the plain evaluation, and did not refuse record mode.

`hard_stop.py 115 … pytest -p no:randomly -n 0 --tb=line <the three test files> -k evaluat` → **22
failed, 20 passed**. The 20 that passed:

* t07's existing evaluate tests;
* new tests whose behaviour the skeleton kept: the coach sample's rows and strata, the replay's refusal
  of an unrecorded request, and the cases that expect no hit.

All four CLI tests failed. The skeleton's plain evaluation called `evaluate` on a stub that has only
`break_down`, so they ended `INTERNAL_ERROR`, the wiring the tests are for being absent. Two tests then
failed on their own mistakes, and I fixed the tests:

* `NormalizedHeading` needs `answer`;
* the stop test read a field the batch record does not have.

### Mutants

20 mutants, each run alone and restored from `HEAD`, over the three test files with `-k evaluat`. **All
20 caught**, each on an assertion. Two were redone so that they really mutated:

* "read from the previous card" first handed back the current card;
* "labelled none" first crashed in `related()` on `resolve("none")`, and a crash is not a catch.

The four the PM named are the first five rows (the first of them in two forms).

| Mutant | First test to fail |
|---|---|
| An outcome counted twice (the counted cards added again) | `…gives_every_labelled_card_one_outcome_summing_to_the_labelled` |
| An outcome dropped (the card the store no longer holds left out) | the same |
| A hit's words in the JSON (`matched` in `scan_hits`) | `test_evaluate_breakdown_json_counts_the_hits_and_holds_none_of_their_words` |
| Stage one's placement read from the previous card | `…puts_each_cards_own_deterministic_placement_beside_it` |
| The model-set score over all cards | `…agrees_with_the_evaluation_and_scores_the_model_set_alone` |
| A refused batch's cards counted as refusals, not lost | `…one_outcome_summing…` |
| A wrong position of the label's kind counted as a wrong kind | the same |
| The threshold not checked | the same |
| A placement labelled none scored correct | the same |
| Every card sent to the model | `…deterministic_placement_beside_it` |
| The strata weighed alike | `…weighs_the_strata_by_their_populations` |
| A refused batch recorded as answered | `…says_what_the_guard_did_with_each_batch` |
| A match across fields not listed | `…has_a_hit_of_every_kind_the_scan_counts[…]` |
| A taxonomy word not marked | `…code_word_in_the_committed_taxonomy…` |
| A tournament hit naming a team not marked | `…lists_the_scans_hits_by_text_field_and_kind` |
| The hits listed when stdout is not a terminal | `test_evaluate_breakdown_withholds_the_hits_when_stdout_is_not_a_terminal` |
| Another caselist's repair cassette read | `…reads_only_this_prompts_repairs_filed_under_the_caselist` |
| Rationales read as metadata | `…lists_the_scans_hits_by_text_field_and_kind` |
| Refusals put under the wrong label class | `…one_outcome_summing…` |
| A wrong answer naming the label's parent not marked related | the same |

Two marks added after the replay are covered the same way. Disabling `json_key` fails
`test_evaluation_scan_marks_a_school_whose_name_is_a_key_of_the_prompt_input`, and disabling `in_input`
fails `test_evaluation_scan_marks_a_rationale_hit_that_repeats_the_cards_sent`: 22 mutants in all, all
caught.

No test here uses Hypothesis, so agreement 8's database rule does not apply.

## Tests and checks run before this report

Run after the last code commit (the hit marks):

* **The affected set is over two minutes, so it is left to the pull request's `ci`** (agreement 10).
  `scripts/affected_tests.py` selects **231 files**: the model stage reaches the container. Before the
  marks were added, `hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` was 18% through
  its 222 files when the limit stopped it.
* Within two minutes, over the changed areas and the always-run list:
  * the command: `hard_stop.py 115 … pytest -q -n 6 -m "not slow and not live" tests/architecture/
    tests/specs/ packages/debate_cli/tests/test_app.py …/test_help_rendering.py
    …/test_container_factories.py packages/debate_core/tests/arguments/landscape
    …/application/test_landscape_model_stage.py …/test_position_classification.py
    …/test_landscape_evaluation_breakdown.py …/test_landscape_run.py
    packages/debate_cli/tests/test_landscape_command.py`;
  * the result: **1732 passed** in 43.77 s.
* The node's criterion: `hard_stop.py 115 … pytest -q -n 6 packages/debate_core/tests
  packages/debate_cli/tests -k evaluat` → **52 passed** in 9.97 s.
* `ruff format --check .` → 1789 files already formatted. `ruff check .` → all checks passed.
* `pyright packages/debate_core packages/debate_cli` → 0 errors.
* `lint-imports` → 20 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 70 handlers within 25 statements (`evaluate` was 26 before a
  helper took its read).
* `scripts/validate_specs.py` → OK.
* `scripts/docs_index.py --check-descriptions`, `scripts/check_links.py`, and
  `scripts/check_command_blocks.py --base origin/dev` → OK.

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/evaluation_breakdown.py` (new, pure): the
  one outcome per card, stage one's placement beside it, and the tallies. Those are the outcomes, the
  refusals by label class, the label kinds, the confusion table, the model-set score, and the strata
  with their weighting.
* `…/arguments/landscape/scan_hits.py` (new, pure): the scan's hits, field by field, by `name_scan`'s
  own lists. A match no field holds alone is listed across fields. A hit withholds its words from its
  `repr`.
* `…/application/landscape_model_evaluation.py`: the evaluation is split into asking and scoring, so the
  breakdown asks exactly as it does. Adds `break_down_labelled_cards` and `LandscapeModelEvaluationService.break_down`.
  The coach's row and stratum are kept on each labelled card, and the strata's populations are read
  from the rows file.
* `…/application/landscape_model_stage.py`: `ModelStageOutcome.batches`, one `BatchRecord` per batch
  answered or refused, holding its fingerprints and the guard's attempts.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: `--breakdown`, `data.breakdown`, the display,
  and the terminal-only hit listing.
* `packages/debate_cli/src/debate_cli/container.py`: one line, the repair cassettes' texts for the
  breakdown.
* Tests: `packages/debate_core/tests/application/test_landscape_evaluation_breakdown.py`,
  `packages/debate_core/tests/arguments/landscape/test_evaluation_scan_hits.py`, four tests at the end of
  `packages/debate_cli/tests/test_landscape_command.py`, and one row-number pin in
  `test_landscape_model_stage.py`.
* Docs: `docs/data/landscape-model-evaluation.md` (new: the first evaluation, the sample, the cassettes,
  the replay's breakdown and the hits' marks) and `docs/runbooks/landscape-model-evaluation-replay.md`
  (new).

## Deviations from the spec

None to the spec's scope.

### The terminal listing reached the session

The operator pasted step 3's terminal output, the scan's hit lines, into this session along with step
2's JSON. The runbook said not to. Nothing from those lines was written to any file, commit, document,
test, memory or reply.

The counts recorded come from the JSON alone. The one judgement this report takes from the lines is that
the 9 heading-path hits are tournament and team names, and it says so where it uses it. Whether this
needs a note under the data-use policy is the PM's to decide.

The runbook now puts step 3's warning in bold, before its command. The hit marks were added so that a
JSON run can answer what the lines were needed for.

## Decisions and assumptions

1. **Shape: a `landscape evaluate` option.** It shares the command's reading, scoring and exit codes, so
   a breakdown below the bar exits 1 as the evaluation does. It replays only, and its JSON adds one key
   (`breakdown`) to the evaluation's summary, so the pinned summary keys are unchanged without it.
2. **"Counts by item kind" is read as the kind of the coach's label** (`aff`, `advantage`, `da`, `cp`,
   `k`…, and `none`). Every labelled item is a card, so the matcher's item kind would be one row.
3. **Two outcomes beyond the PM's list** make the sum hold whatever happens:
   * `not_asked`: a stop left the card unasked;
   * `not_found`: the store no longer holds it.

   The refusals are split by reason and then by whether the coach labelled a position or none.
4. **Two fields beyond the PM's list.**
   * `taxonomy positions`: a cassette also holds the taxonomy the prompt sent.
   * `across fields`: a match only two fields make together (the scan reads a cassette whole).

   The repair cassettes are listed as texts of their own, with a `repaired prompt` field. Their counts
   are reported apart from the evaluation's cassette scan, which does not read them.
5. **Each hit carries four marks**, all counted in JSON by field (`marks_by_field`):
   * *A team's name*: a tournament-list hit whose words are a school or team code. The scan's third
     list holds every disclosing team's school and code as well as its tournament.
   * *A taxonomy word*: its words also occur in the committed taxonomy.
   * *A JSON key*: every word of it is a word of a key of the text.
   * *In the cards sent*: its words occur in the cards the text sent.

   I added the last two after the first replay, so that what a hit is could be counted rather than read.
   Before them, only the terminal listing could tell the operator, or the session, that the school in
   every text was a key word.
6. **The hits print only when stdout is a terminal.** `> file` or `| tee` would make a file of them, so
   then the command prints how many it withheld.
7. **The strata's weighting is by stratum alone.** Each labelled card stands for `population ÷ labelled`
   of its stratum. t21 also weighted by the proxy's predicted kind; the stratum is the coarser and
   sturdier cut at 47 cards.

## Operator follow-ups

None outstanding. The operator ran the replay ([the runbook's](../runbooks/landscape-model-evaluation-replay.md)
steps 2 and 3) and then this JSON-only run of the hits' marks, both on 2026-11-01, from this worktree:

```bash
uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown
```

## Questions for the PM

> **v1-e32-t39: why the model stage scored 36.8%, and the options, in counts.** Every count is in
> `docs/data/landscape-model-evaluation.md`. None of the six options below is made here; the fix is
> filed from them.
>
> 1. **The labels (relabel or drop).** The 7 cards labelled none: 4 placed, 1 below the threshold, 2
>    answered none.
>    * Dropping them: 14 of 34, 41.2%.
>    * Counting the 9 same-side neighbour answers as right: 23 of 38, 60.5%.
>    * Both: 23 of 34, 67.6%.
>
>    None reaches the bar. **Recommended:** keep the labels as the measure. Ask the coach to look again at
>    the 13 rows in question (the 9 neighbours and the 4 placed none, by sample row) only to say whether
>    those positions should be told apart at all, which is a taxonomy question.
> 2. **The bar, or the set it applies to.**
>    * The headings place none of the 47, so the set is all 47.
>    * Weighted to the strata, 37.9%.
>    * By threshold, accuracy rises only to 66.7%, at 0.85 (15 counted) or 0.9 (6). The mean confidence
>      is 0.836 on right answers and 0.768 on wrong ones.
>    * The sample leaves out the below-threshold cards (about 1,638 of 58,299 in the set).
>
>    **Recommended:** no change to the bar, the set or the threshold. Neither explains the gap.
> 3. **The prompt (what the wrong answers have in common).**
>    * All 9 same-kind wrong answers are same-side neighbours, and only 1 of the 34 positions involved has
>      a description.
>    * 10 of 11 other-kind answers name a position of the other side; 7 are negative cards answered with
>      an affirmative.
>    * T is 1 of 7, and `generic-k` is refused 3 of 3.
>
>    **Recommended:** a prompt 1.1.0 that says to name the argument the card is read as, not its subject.
>    Send the position's side and a one-line description per position (a taxonomy edit, the coach's).
>    Re-record the same 47 to measure it.
> 4. **The batch size or the schema.** 1 of 3 calls failed: a rationale over the schema's 280 characters.
>    Its repair cost 1 call that carried all 20 cards again, and the repaired batch scored no worse (7 of
>    15). **Recommended:** state the 280-character limit in the prompt, and keep 20 a batch.
> 5. **The scrub.** 9 real names reached the prompt inputs, all in heading paths: other teams' tournaments
>    and codes, which the heading scrub does not remove (it removes the disclosing team's own names and
>    the caselist's schools). **Recommended:** take the scan's whole third list (every disclosing team's
>    school, code and tournament) out of headings, tags, cites and excerpts too. Its everyday words cost
>    a word, as code words do in tags today (1 such hit here).
> 6. **The scan.** 623 of 647 hit lines are structure or vocabulary:
>    * 178 are one JSON key word that a school's name spells. It is why every text counts "a school".
>    * 445 are committed taxonomy words. They are why every cassette counts "a team code".
>
>    The repair cassette (182 hits, holding the repaired batch again) is not scanned at all.
>    **Recommended:**
>    * scan field values, not JSON keys;
>    * leave the committed `positions` text out;
>    * hold only tournaments on the third list;
>    * scan the repair cassettes.
>
>    Then only the 24 heading-name lines would remain, and those are the scrub's to fix. No accept-list is
>    needed. If one is still wanted, it is kept locally, keyed by a keyed digest.
>
> Also: the operator pasted the terminal hit listing into the session; nothing from it was recorded (the
> report's Deviations). And ac2 is marked "recorded by the PM", so I left the Goal `InProgress` for you
> to set.

## Follow-up work

* A smoke check for `landscape evaluate --breakdown`: `tests/smoke` has none for `landscape evaluate` at
  all. It would need a synthetic labelled sample and cassettes in the smoke world (E32, or the fix task
  filed from this one).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

This is the diagnosis the PM asked for, and it settles where the gap is. The batch and the sample are
not the cause; the model's answers are. Wrong answers name a same-side neighbour, or what the card is
about instead of the argument it is read in. Most of the "school in every text" scan result was a JSON
key word. Both criteria pass, so the Goal is `Succeeded`.

1. **ac1:**
   * One outcome per card, summing to labelled, with stage one's placement beside each, on synthetic
     cards recorded and then replayed with no router behind them.
   * The hits are withheld from `--json`, from the logs at DEBUG and from every file. They print
     only to a terminal, and the command says how many it withheld otherwise.
   * 22 tests failed against the skeleton; 22 mutants were caught, the PM's four among them. The two
     mutants redone so that they really mutated are noted honestly.
2. **ac2, recorded by the PM:** the operator's replay (2026-11-01) made no model call and reproduced
   the recording exactly: labelled 47, asked 47 in 4 calls, counted 38, correct 14, and 30,460 / 3,881
   tokens. The outcomes sum to 47. The counts are in `docs/data/landscape-model-evaluation.md`. PASS.
3. **The rulings on the six options.** The PM files one fix task from them (E32, p1: it blocks the
   landscape stage in the cloud run and the cheaper-model work).
   1. **Labels:** kept as the measure. The coach looks at the 13 rows in question (the 9 neighbours
      and the 4 placed none), only to say whether those positions should be told apart at all. That
      is a taxonomy question, asked in the fix task.
   2. **The bar, the set and the threshold:** unchanged.
   3. **The prompt:** 1.1.0 says to name the argument the card is read as, not its subject. Each
      position is sent with its side and a one-line description. The session drafts the
      descriptions and the coach approves them (a taxonomy edit). Then re-record the same 47; the
      live call is the operator's.
   4. **The schema:** the prompt states the 280-character rationale limit; batches stay at 20.
   5. **The scrub:** the scan's whole third list (every disclosing team's school, code and
      tournament) comes out of headings, tags, cites and excerpts too.
   6. **The scan:** field values, not JSON keys; the committed `positions` text left out; tournaments
      only on the third list; the repair cassettes scanned. No accept-list.
4. **Decisions accepted:** the `--breakdown` shape; kind by the coach's label; `not_asked` and
   `not_found`; the two extra fields; the four marks; terminal-only printing; weighting by stratum.
5. **The pasted terminal listing** (Deviations). Handled correctly: nothing was written down, the
   counts came from the JSON, and the runbook's warning is now bold and comes before the command. The
   lines named tournaments and team codes with a few words of card text around them, and they reached
   a model session outside the ModelRouter. The PM records this in the next batch as a note under the
   data-use policy's model-provider rules: what happened, that nothing was persisted, and the
   safeguard (the JSON marks now answer what the listing was needed for). With the scan fixed (option
   6), the listing will be about 24 lines. The operator reads it in the terminal and pastes only the
   counts.
6. **Closing checks:** the affected set (231 files) is left to `ci` (agreement 10). The bounded groups
   (1,732 and 52 passed), ruff, pyright, lint-imports, thin handlers, the specs and the doc checks are
   clean.
7. **Follow-up:** a smoke check for `landscape evaluate` goes into the fix task.
8. **Before the PR:** set the phase with `uv run scripts/task_helper.py set-phase
   v1-e32-t39-model-evaluation-diagnosis Succeeded`, run validate_specs and commit.
9. **Merge:** a plain `scripts/task pr` once `ci` is green.

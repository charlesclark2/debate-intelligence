# Session report: v1-e32-t39-model-evaluation-diagnosis

| | |
|---|---|
| Task | `v1-e32-t39-model-evaluation-diagnosis` — Why the model stage scored 36.8%: the evaluation broken down, and the scan's hits listed in the operator's terminal |
| Spec | [`plan_specs/v1/e32-argument-landscape/t39-model-evaluation-diagnosis.yaml`](../../plan_specs/v1/e32-argument-landscape/t39-model-evaluation-diagnosis.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t39-model-evaluation-diagnosis` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`landscape evaluate --breakdown` is built and tested (ac1). It replays only: the router it builds holds
no model, so an unrecorded request fails as `MISSING_FIXTURE` and is never sent. With `--model-mode
record` it is refused.

It gives each labelled card exactly one outcome, and puts beside each card what the headings alone place
and whether a real run would send it. It also gives:

* each batch's calls, and what the structured-output guard did with it;
* a confusion table of position ids, with counts by the label's kind;
* the score on the cards a real run sends to the model, by the sample's strata, and weighted to them;
* the scan's hits, one line each, in a terminal only. `--json` holds their counts by kind and field.

Three findings come from the files alone, before any replay (counts only, in
[`docs/data/landscape-model-evaluation.md`](../data/landscape-model-evaluation.md)):

* The coach sample is 60 cards, 47 labelled, all of them cards stage one left **unplaced**.
* The sample is stratified unevenly: 30 of the 60 come from the stratum holding 22.5% of the unplaced
  cards.
* The failed call was a batch of 20. One rationale was over the schema's 280 characters, and the guard
  **repaired** it, so no card was lost. Its repair cassette holds all 20 cards' inputs, and the
  evaluation's scan never reads it.

**ac2 waits on the operator's replay run** (the block is under [Operator follow-ups](#operator-follow-ups)),
so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-evaluation-diagnosis` (Evaluation breakdown) | Done | Its criterion passes; ac2's replay is the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the breakdown and the terminal-only hit listing work on synthetic fixtures and replay cassettes. Every labelled card falls in exactly one outcome, and the outcomes sum to the labelled count. The deterministic placement is shown beside each. Nothing hit-bearing reaches JSON output, a log or a file. Shown by tests that failed first | PASS | See [Tests](#tests-and-checks-run-before-this-report): `test_landscape_evaluation_breakdown.py` (12) records nine synthetic cards through the record-replay router, then replays them with no router behind it. Every outcome but `not_asked` is planted once or twice; `not_asked` has its own test. The outcomes are written out by hand and sum to 10. Stage one's placement is pinned per sample row. `test_evaluation_scan_hits.py` (13) covers the fields, kinds and synthetic scrub cases. The CLI tests (4) plant a distinctive hit: it is absent from `--json` stdout, from caplog at DEBUG and from every file under `tmp_path`, and it is shown only when stdout is a terminal. Red run: 22 failed against the skeleton; 20 mutants all caught |
| ac2: the operator's replay over the kept cassettes (operator, recorded by the PM) gives the counts recorded in `docs/data/landscape-model-evaluation.md`, and the PM has the options | NOT RUN | It waits on the operator's run of [the replay blocks](#operator-follow-ups). The first evaluation's counts, the sample's and the cassettes' are recorded already |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 6 packages/debate_core/tests packages/debate_cli/tests -k evaluat` → **50 passed** in 14.30 s |

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

No test here uses Hypothesis, so agreement 8's database rule does not apply.

## Tests and checks run before this report

* **The affected set is over two minutes, so it is left to the pull request's `ci`** (agreement 10).
  `scripts/affected_tests.py` selects **222 files**: the model stage reaches the container.
  `hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` was 18% through when the limit
  stopped it.
* Within two minutes, over the changed areas and the always-run list:
  * the command: `hard_stop.py 115 … pytest -q -n 6 -m "not slow and not live" tests/architecture/
    tests/specs/ packages/debate_cli/tests/test_app.py …/test_help_rendering.py
    …/test_container_factories.py packages/debate_core/tests/arguments/landscape
    …/application/test_landscape_model_stage.py …/test_position_classification.py
    …/test_landscape_evaluation_breakdown.py …/test_landscape_run.py
    packages/debate_cli/tests/test_landscape_command.py`;
  * the result: **1730 passed** in 25.78 s.
* The node's criterion: 50 passed (above).
* `ruff format --check .` → 1787 files already formatted. `ruff check .` → all checks passed.
* `pyright packages/debate_core packages/debate_cli` → 0 errors.
* `lint-imports` → 20 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 70 handlers within 25 statements (`evaluate` was 26 before a
  helper took its read).
* `scripts/validate_specs.py` → OK.
* `scripts/docs_index.py --check-descriptions`, `scripts/check_links.py`, `scripts/check_command_blocks.py` → OK.

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
* Docs: `docs/data/landscape-model-evaluation.md` (new) and
  `docs/runbooks/landscape-model-evaluation-replay.md` (new).

## Deviations from the spec

None.

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
5. **Each hit carries two marks.**
   * *A team's name*: a tournament-list hit whose words are a school or team code. The scan's third
     list holds every disclosing team's school and code as well as its tournament.
   * *A taxonomy word*: its words also occur in the committed taxonomy.

   Both are counts in JSON.
6. **The hits print only when stdout is a terminal.** `> file` or `| tee` would make a file of them, so
   then the command prints how many it withheld.
7. **The strata's weighting is by stratum alone.** Each labelled card stands for `population ÷ labelled`
   of its stratum. t21 also weighted by the proxy's predicted kind; the stratum is the coarser and
   sturdier cut at 47 cards.

## Operator follow-ups

**The replay, broken down** (expected runtime about a minute each, no model call). Where: your Mac, in
this task's worktree. The blocks come from
[the runbook](../runbooks/landscape-model-evaluation-replay.md). Each refuses a leftover `DEBATE_*`
override or a running pull, and writes nothing to the repository or a bucket.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t39-model-evaluation-diagnosis
```

**1. The counts, as JSON: paste this output back.** It holds counts and taxonomy ids only.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

What success looks like:

* exit 1, `EVALUATION_BELOW_BAR`;
* in `error.details`, `labelled` 47, `found` 47, `asked` 47 and `calls` 4, matching the recording;
* `breakdown.outcomes` summing to 47.

`MISSING_FIXTURE` means a request differs from the recorded ones, and no model was called. Paste the
error code and stop.

**2. The hits, in your terminal only: do not paste this output.**

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

Reply with how many hits it lists, and for each hit number whether its words name a team, a school or a
tournament there, or are an ordinary word sharing them (a surname, a city, a journal, a common word).
Send numbers and judgements, never the words.

## Follow-up work

* A smoke check for `landscape evaluate --breakdown`: `tests/smoke` has none for `landscape evaluate` at
  all. It would need a synthetic labelled sample and cassettes in the smoke world (E32, or the fix task
  filed from this one).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

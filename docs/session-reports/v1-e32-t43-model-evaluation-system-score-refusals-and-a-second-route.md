# Session report: v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route

| | |
|---|---|
| Task | `v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route` — The model stage is scored as students meet it, its refusals are explained, and a second model route is measured on the same cards |
| Spec | [`plan_specs/v1/e32-argument-landscape/t43-model-evaluation-system-score-refusals-and-a-second-route.yaml`](../../plan_specs/v1/e32-argument-landscape/t43-model-evaluation-system-score-refusals-and-a-second-route.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route` |
| Session status | PARTIAL: rulings 1 and 2 done; ruling 3 waits on the PM's choice of route and of how the second recording is kept apart |

## Summary

The evaluation now scores the coach's 47 cards two ways: **the pipeline**, as students meet them (a card
the headings place surely is scored on that placement, a card a coach's override decides is no position
is not counted, every other card on the model's answer), and **the model alone**, as before. Both give
counted, correct, refused, below-threshold, accuracy and coverage (counted over labelled), in the JSON
(`pipeline`, `model_alone`, `bar_reads`) and the display; the bar reads the pipeline's accuracy, the PM's
ruling. The replay of the 1.1.0 cassettes gives the pipeline **21 of 33, 0.636** (the PM's estimate),
beside the model alone's 19 of 32, 0.594. The 10 refusals of labelled cards are explained from counts
below, with a proposed prompt change for the PM to rule on; the refusals cost coverage, and even all 10
answered rightly would make the pipeline 0.721, so the wrong answers are what keep it under the bar.
**The PM's decision is needed** on ruling 3 (the [relay](#the-pm-relay-route-mechanism-and-the-refusal-proposal)):
the cassette key does not separate routes or models, so a second recording on any route would overwrite
the three 1.1.0 cassettes; the session recommends dev's `deep_audit` route (Claude Sonnet 4.6, $0.175 at
this evaluation's tokens) and a small router change to keep its cassettes apart. The Goal stays
`InProgress`: ac3 is the operator's recording, recorded by the PM.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-evaluation-system-score-refusals-a` (System score) | IN PROGRESS | Rulings 1 and 2 done and committed; ruling 3's code and recording block wait on the PM |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the pipeline's score beside the model's own, in the JSON and the breakdown, by tests shown failing first, with the PM's ruling on which the bar reads | PASS | Red run against a skeleton: 14 failed at their assertions, 1 passed ([below](#ruling-1-the-pipelines-score)). Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 <the 5 evaluation test files>` → 200 passed in 19.03s. Replay `landscape evaluate --breakdown --json` → pipeline 21 of 33 (0.636), model alone 19 of 32 (0.594), `bar_reads` `pipeline`, exit 1 `EVALUATION_BELOW_BAR`. The ruling (the bar reads the pipeline) is the PM's of 2026-11-02, in `TARGET_ACCURACY`'s docstring, `BAR_READS`, the CLI help and both runbooks |
| ac2: the 10 refusals of labelled cards explained from ids and counts, with a proposed change and its evidence | PASS | [Ruling 2](#ruling-2-the-10-refusals-of-labelled-cards) below and `docs/data/landscape-model-evaluation.md`; the proposal is the PM's to rule on and is not built |
| ac3: the operator's recording on the second route the PM approved, and the side-by-side counts and cost, in docs/data | NOT RUN | Waits on the PM's choice of route and mechanism ([relay](#the-pm-relay-route-mechanism-and-the-refusal-proposal)), then the operator's recording, then the PM's record |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat -q --tb=short -n 4` → 97 passed in 46.58s |

## Ruling 1: the pipeline's score

**What is scored.** `evaluation_breakdown.pipeline_score` partitions the labelled cards by stage one's
placement: placed surely (not sent) → scored on that placement, right when it names the label or the
second label (`by_headings`); decided none by an override → not counted (`decided_none`); sent or not
found → the model's outcome. `model_alone_score` is every card's model outcome. `LandscapeModelEvaluation
Service.evaluate` now places the cards with the topic's overrides, as `break_down` did, through one
function both use (`labelled_card_breakdowns`), so the evaluation and the breakdown cannot disagree.
`FormatEvaluation.meets_target` reads `pipeline.accuracy`.

**Red first.** The skeleton had the new types, fields and parameters, counting nothing, and the bar
still reading the model. `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p
no:randomly --tb=line -q <the new tests>` → **14 failed, 1 passed in 2.35s**. Every failure was an
assertion (a zero score against the hand count, `meets_target` against the expected verdict, a JSON key
absent so `data` was `null` on exit 1, a display line absent). The one pass is the empty-score test,
which the skeleton's zeros satisfy by construction.

**Mutants.** Each applied to the committed code, the evaluation tests run (`-k evaluat` over the five
test files, fresh Hypothesis directory), then restored from HEAD:

| Mutant | Caught by |
|---|---|
| PM: a deterministic placement scored on the model's answer | 6 tests |
| PM: a refused card counted as wrong | 9 tests |
| PM: coverage over counted rather than labelled | 3 tests |
| PM: the bar reads the model-alone score | 5 tests (core and CLI) |
| A card an override decides is none taken as a headings placement | 5 tests |
| A second label ignored for a headings placement | 2 tests |
| The pipeline counts every refusal, headings-placed cards' too | 3 tests |
| `break_down` scores without the overrides | 2 tests |
| The JSON's `pipeline` reads the model's score | 1 test |
| The service evaluates without the topic's overrides | **survived** the first run (no test ran the service with an override); caught by the test added in `b6c484b`, `test_evaluation_service_scores_the_pipeline_with_the_topics_overrides` |

**The replay** (the session's, read-only and offline, from this worktree, 113 s):

| | Model alone | Pipeline |
|---|---|---|
| Counted / correct | 32 / 19 | 33 / 21 (4 by the headings) |
| Accuracy (bar 0.85) | 0.594 | **0.636** |
| Refused / below the threshold | 12 / 3 | 12 / 2 |
| Coverage | 32 of 47, 0.681 | 33 of 47, 0.702 |

The other counts match the PM's record of the re-record: labelled, found and asked 47, 3 calls, 38,881
and 3,882 tokens, weighted accuracy 0.491, the model's set 17 of 29. The cassette scan is not clean (its
27 marked hits, `v1-e32-t44`'s subject), which the exit code also reflects.

## Ruling 2: the 10 refusals of labelled cards

Rows 14, 16, 17, 20, 25, 35, 39, 46, 50 and 56 (labels: midterms-da 2, generic-k 2, inequality-advantage,
data-advantage, pharma-advantage, coverage-advantage, states-cp, advantage-cp). Counted with two scratch
scripts that read the cards through the evaluation's own path (`ask_labelled_cards` over the replay, so
exactly what was sent), and the three 1.1.0 cassettes' answers. **What the session read**, under policy
1.22: the 12 refused cards' tags as sent, printed in the session's terminal and written nowhere. Headings,
cites, excerpts, evidence and rationales were read by the scripts to count words and terms and never
printed; the evidence was read for its word count only. The counts are in `docs/data`; the patterns:

1. **No heading.** 6 of the 10 reached the model with no heading: 5 sit under no heading in their file and
   1 had its only heading emptied by the scrub (it held names alone). Of the 14 cards labelled a position
   with no heading sent, 6 were refused; of the 30 with one, 4. None of the 10 had a speech or structure
   heading (the answered: 6 of 34).
2. **No position's words.** A word of the label's position was in the headings or tag of 3 of the 10
   (all three in a heading: rows 20, 25, 35) against 22 of the 34 answered. The tags are present (all 10),
   a little shorter (mean 10.5 words against 14.3), and name no kind of argument.
3. **Not the length, the cite or the batch's end.** Evidence under 300 words for 4 of 10 against 6 of 34;
   a cite for 6 of 10 against 22 of 34; positions in the batch from 1 to 17. Batches 1 and 2 hold 5 each,
   batch 3 (7 cards) none. Strata: 6 at-or-above, 2 just-below, 2 far-below. Stage one left all 10
   unplaced. 8 of the 10 sit in a file read by their label's side.
4. **What the cards are**, by kind of claim: 3 an impact or framing claim naming no position (rows 16,
   20, 35), 2 a link or internal link of an election story naming a party (14, 17), 2 a kritik's claim
   (46, 50), 2 a counterplan's solvency (39, 56), 1 a numbered answer in a frontline (25).
5. **The recorded answers.** Each is `position_id` null, which `judge` records as `NO_POSITION` (confidence
   0, a fixed rationale). The model's own confidence on them is 0.15 to 0.3 in batch 1 and 0.5 to 0.7 in
   batch 2, so a null's confidence means nothing steady. 6 of 10 rationales call the card general or
   generic; both `generic-k` cards' rationales name a kritik or philosophy.
6. **The prompt asks for these nulls.** 1.1.0 says to answer null "when the card is general (framing, an
   impact with no story, a claim about the round) and you cannot tell which position it serves", beside
   the rule that a card of a kind no named position fits goes to that kind's generic position "rather than
   answering null". The refused cards are the general kinds that clause lists, and the K cards show the
   null clause winning over the generic rule.

**The proposal (for the PM to rule; not built).** A prompt instruction change, same variables, as prompt
1.2.0:

* (a) A card of a kind the list has a generic or named position for (a kritik's link, framework or
  alternative; a counterplan's plank or solvency) goes to that position even when it reads as general:
  the null clause no longer applies to it. Evidence: rows 46 and 50, whose rationales name a kritik, and
  rows 39 and 56, counterplan solvency in negative files, 4 of the 10.
* (b) A general card (an impact, a framing claim, an answer) under a heading that names a word of a
  position serves that position. Evidence: rows 20, 25 and 35, 3 of the 10, each with such a heading and
  refused anyway.
* Null stays for a general card under no heading that names a position (rows 14, 16, 17): nothing sent
  says which position it serves. The one of them that file context would answer (row 17, whose file's
  other cards stage one places under its label 13 times) is not worth a new input: the label is among the
  file's placements for 1 of the 10 and 8 of the 34 answered.
* The refusal rule stays: a null is refused because only the coach decides a card is none, and counting
  nulls would raise no accuracy.

What it can win, bounded: at most 7 more counted cards. All 7 right makes the pipeline 28 of 40 (0.700);
the 4 of (a) alone, 25 of 37 (0.676); answered wrongly, they lower it. An input the session considered
and does not propose first: the file's side (`aff`/`neg`, from the disclosing team, not a name). 8 of the
10 and 33 of the 44 cards labelled a position sit in a file read by their label's side, but the other 11
are what the coach labels with the position the card answers, and 4 of the pipeline's 5 wrong-kind
answers are among them: telling the model the side could push those further from the coach's labels.

## Ruling 3: the second route

**The routes the committed routing policy defines** (`config/model_routing.dev.yaml`, the operator's
environment, and `config/model_routing.prod.yaml`), each priced from `config/model_pricing.yaml` at this
evaluation's 38,881 input and 3,882 output tokens, the whole evaluation (3 calls) and per call:

| File | Route | Model | Price per 1K in / out (as of) | The evaluation | Per call |
|---|---|---|---|---|---|
| dev | `high_volume` (the 1.1.0 recording) | `anthropic.claude-haiku-4-5-20251001-v1:0` | $0.001 / $0.005 (2026-10-27) | $0.058291 | $0.019430 |
| dev | `complex_reasoning` | `anthropic.claude-haiku-4-5-20251001-v1:0` (the same model) | $0.001 / $0.005 (2026-10-27) | $0.058291 | $0.019430 |
| dev | `deep_audit` | `anthropic.claude-sonnet-4-6` | $0.003 / $0.015 (2026-10-27) | **$0.174873** | $0.058291 |
| prod | `high_volume` | `anthropic.claude-haiku-5-5` | $0.0001 / $0.0005 (2026-10-26) | $0.005829 | $0.001943 |
| prod | `complex_reasoning` | `anthropic.claude-sonnet-5-5` | $0.002 / $0.01 (2026-10-26) | $0.116582 | $0.038861 |
| prod | `deep_audit` | `anthropic.claude-opus-5-5` | $0.004 / $0.02 (2026-10-26) | $0.233164 | $0.077721 |

`embeddings` and `rerank` are not generative. Another model writes a different number of output tokens,
so these are estimates at today's counts.

**Recommendation: dev's `deep_audit`, Claude Sonnet 4.6, about $0.17.** It is the one route on the
operator's environment with a different model (dev's `complex_reasoning` is the same Haiku 4.5), and the
dev routing file records that this account's Sonnet 4.6 quota is non-zero and that it answered a first call
on 2026-10-27 (v1-e05-t08's PM record). The prod routes' 5.5 models had their quotas held at
zero (the dev routing file's comment, 2026-10-27); whether that has changed is an AWS read the session
does not make.

**The cassette key does not separate routes or models.** `fixture_key` covers the prompt's id and
version, its variables and the schema's name only (`integrations/models/fixture_key.py`). Record mode
writes `<prompt>/<key>.json` with no check for a file already there (`record_replay.py`,
`generate_structured`), and replay serves whatever file is there, marking the route `fake` and keeping
the recorded model id. The same 47 cards under prompt 1.1.0 make the same three keys, so **a second
recording on any route would overwrite the 1.1.0 cassettes, and a later replay would serve the second
route's answers as the first's**. Also, the structured-output guard refuses a call whose task class is
not the prompt's (`high_volume`), so the second route cannot be reached by asking for another task class
without changing the prompt, which is forbidden.

So the recording needs code that is not built yet: for this evaluation only, the chosen route's model
and parameters stand in for `high_volume`'s, and its cassettes go under a directory of their own that
`landscape evaluate` replays and scans and `landscape cassettes` lists and deletes (the data-use policy's
deletion of cassettes must reach them). The options are in the relay. The recording block follows the
PM's answer.

### The PM relay: route, mechanism and the refusal proposal

> **v1-e32-t43 asks the PM three things** (2026-11-02).
>
> Done: the evaluation scores the pipeline beside the model alone, and the bar reads the pipeline (your
> ruling). The replay of the 1.1.0 cassettes: pipeline 21 of 33 (0.636), model alone 19 of 32 (0.594).
> All four of your mutants are caught.
>
> **1. The second route.** Priced from `config/model_pricing.yaml` at 38,881 in and 3,882 out:
> dev `deep_audit` Claude Sonnet 4.6 $0.175; dev `complex_reasoning` is the same Haiku 4.5 as the 1.1.0
> recording ($0.058); prod `complex_reasoning` Sonnet 5.5 $0.117, `deep_audit` Opus 5.5 $0.233,
> `high_volume` Haiku 5.5 $0.006, all three on 5.5 quotas last recorded at zero.
> *Recommendation: dev `deep_audit` (Sonnet 4.6)*, the one other model the operator's environment can
> call.
>
> **2. How the second recording is kept apart.** The cassette key holds no route or model: a second
> recording of the same cards would overwrite the three 1.1.0 cassettes, and replay would serve it as
> theirs. Options:
> - **(A, recommended)** `landscape evaluate --route <task class>`: the named route of the environment's
>   routing file stands in for `high_volume` for that evaluation, for the router and the budget guard
>   alike, and its cassettes go under `<data dir>/landscape/model-cassettes-<route>/`, which the same
>   option replays and scans and `landscape cassettes --route` lists and deletes. Needs a route
>   substitution in `debate_core.integrations.models.factory.build_model_router`, so the spec's packages
>   gain `debate_core.integrations.models` (an amendment).
> - **(B)** The same, in `debate_cli` only (in today's packages), but the budget guard then prices each
>   call at `high_volume`'s ceiling (Haiku 4.5, 2,048 output tokens): $0.154 for the three calls against
>   Sonnet's true ceiling of $1.106, about 7 times under (computed from the 1.1.0 cassettes' variables as
>   `RoutePricing` counts them). Dev's $2 daily budget still covers the true ceiling, and a fourth call
>   for a repair (about $1.49), if nothing else spent that day.
> - **(C)** No code: the operator moves the 1.1.0 cassettes aside and records with a one-off routing file.
>   Not recommended: two hand renames and a hand-written routing file in a block that writes shared state.
>
> **3. The refusals** (the report's ruling 2). Proposal, not built: prompt 1.2.0, same variables, (a) a
> kritik or counterplan card goes to its named or generic position even when it reads as general (4 of the
> 10), (b) a general card under a heading naming a word of a position serves that position (3 of the 10);
> null stays for a general card under no such heading (3). At best +7 counted: pipeline 28 of 40 (0.700).
> Rule here, or file it with the wrong answers, which decide the bar (12 of the 33 counted).
>
> Answer 1 and 2 and the session builds the option, then writes the operator's one recording block.

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/evaluation_breakdown.py`: `LabelledScore`,
  `model_alone_score`, `pipeline_score`, `placed_by_headings`.
* `packages/debate_core/src/debate_core/application/landscape_model_evaluation.py`: `FormatEvaluation`
  gains `model_alone` and `pipeline`, and `meets_target` reads the pipeline (`BAR_READS`); the evaluation
  places cards with the overrides through `labelled_card_breakdowns`, which the breakdown shares; the
  service passes the topic's overrides.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: `bar_reads`, `model_alone` and `pipeline`
  in the JSON; the display's two score lines; the below-the-bar message; the command's help.
* Tests: `packages/debate_core/tests/arguments/landscape/test_evaluation_pipeline_score.py` (new, pure, 12
  hand-built cards), `packages/debate_core/tests/application/test_landscape_evaluation_pipeline.py` (new,
  the scripted model through the real prompt, and the service over `synthetic26` with an overrides file),
  `test_landscape_evaluation_breakdown.py` (passes the overrides to the evaluation it compares),
  `packages/debate_cli/tests/test_landscape_command.py` (the JSON, the bar and the display; the stub's
  scores follow its counts; the pinned key set gains the three keys), `tests/smoke/test_landscape_evaluate_smoke.py`
  (the pipeline's counts, by hand: 4 of 4, 2 by the headings).
* Docs: `docs/data/landscape-model-evaluation.md` (the replay's two scores and the refusal counts), both
  evaluation runbooks (what the bar reads).

## Deviations from the spec

* **`tests/smoke/test_landscape_evaluate_smoke.py`** is outside `constraints.packages`. Agreement 5 asks a
  task that changes a user-facing surface to update its smoke checks, and `landscape evaluate`'s JSON and
  exit code changed. The smoke file was not run here (it needs an installed build); validate-dev runs it.
  Its new figures were checked in-process: the service over the same world gives model alone 4 of 4 and
  pipeline 4 of 4 with 2 by the headings.
* **The replay and the two counting scripts were run by the session**, not the operator: read-only,
  offline, over this Mac's store and cassettes, 113 s, 33 s and 32 s (agreement 2). The replay runbook
  calls the replay the operator's.
* **Ruling 3 needs code the spec's packages may not hold** (the router factory is in
  `debate_core.integrations.models`); the relay asks.

## Decisions and assumptions

* **Coverage is counted over labelled**: a card "answered" is a counted one, placed at or above the
  threshold, what a report shows. A card labelled none that is rightly left unplaced lowers coverage too.
* **A card an override decides is none is not counted** by the pipeline and is counted apart
  (`decided_none`), as a run never sends it and never reports it.
* **The pipeline's refusals and below-threshold cards are the model's, on the cards it is sent**; a card
  placed below the threshold by the headings is sent, so it is scored on the model's answer.
* **The top-level `counted`, `correct` and `accuracy` stay the model alone's**, unchanged in meaning, so
  `v1-e32-t07` to `t40`'s recorded figures still read the same; `bar_reads` names the score the bar reads.
* **`overrides` is optional** in `evaluate_labelled_cards` and `score_labelled_answers` (None: no coach
  decisions), so the many direct callers in tests stay unchanged; the service always passes the topic's,
  and a test proves it.

## Operator follow-ups

None yet. The recording block for ac3 follows the PM's answer to the relay.

## Follow-up work

* **The wrong answers decide the bar** (12 of the pipeline's 33 counted: 6 a same-kind neighbour, 5 another
  kind, 1 placed though labelled none). 4 of the 5 other-kind answers are of cards in a file read by the
  side opposite the label's, where the coach labels the position the card answers: a labelling convention
  the prompt's "the argument the card is read as" does not state. E32, the PM's to file.
* **A null answer's confidence** carries no steady meaning (0.15 to 0.3 in one batch, 0.5 to 0.7 in the
  next); the stage discards it. Nothing to change unless a later rule reads it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

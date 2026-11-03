# Session report: v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route

| | |
|---|---|
| Task | `v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route` — The model stage is scored as students meet it, its refusals are explained, and a second model route is measured on the same cards |
| Spec | [`plan_specs/v1/e32-argument-landscape/t43-model-evaluation-system-score-refusals-and-a-second-route.yaml`](../../plan_specs/v1/e32-argument-landscape/t43-model-evaluation-system-score-refusals-and-a-second-route.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route` |
| Session status | COMPLETE for the session: ac1 and ac2 pass; ac3 is the operator's recording on dev's `deep_audit` route and the PM's record of it |

## Summary

The evaluation now scores the coach's 47 cards two ways: **the pipeline**, as students meet them (a card
the headings place surely is scored on that placement, a card a coach's override decides is no position
is not counted, every other card on the model's answer), and **the model alone**, as before. Both give
counted, correct, refused, below-threshold, accuracy and coverage (counted over labelled), in the JSON
(`pipeline`, `model_alone`, `bar_reads`) and the display; the bar reads the pipeline's accuracy, the PM's
ruling. The replay of the 1.1.0 cassettes gives the pipeline **21 of 33, 0.636** (the PM's estimate),
beside the model alone's 19 of 32, 0.594. The 10 refusals of labelled cards are explained from counts
below, with a proposed prompt change, which the PM files as its own task after ac3's result; the refusals cost coverage, and even all 10
answered rightly would make the pipeline 0.721, so the wrong answers are what keep it under the bar.
**Ruling 3, after the PM's rulings of 2026-11-03**: dev's `deep_audit` route (Claude Sonnet 4.6, about
$0.17) and mechanism (A). `landscape evaluate --route <task class>` makes the named route stand in for
`high_volume` in `build_model_router`, for the real router and the budget guard alike, and records to,
replays and scans `<data dir>/landscape/model-cassettes-<route>/`, never the default directory (a test
records on `deep_audit` and finds the default directory untouched); `landscape cassettes --route` lists
and deletes them. The operator's one block is under [Operator follow-ups](#operator-follow-ups). The
Goal stays `InProgress`: ac3 is that recording and the PM's record of it in docs/data. A test that
fails on this Mac at the task's start commit too is noted under [Checks](#checks-run-before-this-report).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-evaluation-system-score-refusals-a` (System score) | IN PROGRESS | Rulings 1, 2 and 3's code and block done and committed; ac3 is the operator's recording and the PM's record |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the pipeline's score beside the model's own, in the JSON and the breakdown, by tests shown failing first, with the PM's ruling on which the bar reads | PASS | Red run against a skeleton: 14 failed at their assertions, 1 passed ([below](#ruling-1-the-pipelines-score)). Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 <the 5 evaluation test files>` → 200 passed in 19.03s. Replay `landscape evaluate --breakdown --json` → pipeline 21 of 33 (0.636), model alone 19 of 32 (0.594), `bar_reads` `pipeline`, exit 1 `EVALUATION_BELOW_BAR`. The ruling (the bar reads the pipeline) is the PM's of 2026-11-02, in `TARGET_ACCURACY`'s docstring, `BAR_READS`, the CLI help and both runbooks |
| ac2: the 10 refusals of labelled cards explained from ids and counts, with a proposed change and its evidence | PASS | [Ruling 2](#ruling-2-the-10-refusals-of-labelled-cards) below and `docs/data/landscape-model-evaluation.md`; the proposal is the PM's to rule on and is not built |
| ac3: the operator's recording on the second route the PM approved, and the side-by-side counts and cost, in docs/data | NOT RUN | The operator recorded the 47 cards on dev `deep_audit` on 2026-11-03 (3 calls, the default cassette directory untouched); the [side-by-side figures](#the-second-routes-recording-2026-11-03) are computed below. Open: the PM's record of them in docs/data, and the operator's judgement of the cassette scan's 42 hits ([follow-up 2](#2-only-if-a-scan-count-in-the-recording-is-above-zero-the-hits-in-the-terminal)). No session can close it |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k evaluat -q --tb=short -n 4` → 97 passed in 46.58s after rulings 1 and 2; 103 passed in 12.20s after ruling 3 (the route tests are named `test_evaluate_…`) |

### Checks run before this report

* `.venv/bin/ruff format --check .` → 1884 files already formatted; `.venv/bin/ruff check .` → all checks
  passed; `.venv/bin/pyright packages/debate_core packages/debate_cli` → 0 errors; `.venv/bin/lint-imports`
  → 20 contracts kept; `scripts/check_thin_handlers.py` → OK; `scripts/check_command_blocks.py --base
  origin/dev` → OK; `uv run scripts/validate_specs.py` → OK: 599 files, 41 epics, 536 tasks, 22 releases.
* **The affected set is over two minutes**, so it is left to the pull request's `ci` (agreement 10):
  `scripts/affected_tests.py` chose 125 of 671 test files (4,440 tests); `--run` under `hard_stop.py 115`
  stopped at 58% (exit 124). **It showed one failure** (an `F` at 11%) and was stopped before pytest named
  it. Two reruns of the same span did not reproduce it: the same selection with `--maxfail=1` reached 30%
  with none, and the first 45 files (1,126 tests, the span xdist's first batches hand out) passed, 680 in
  105.04s and 446 in 19.35s, under a load of 10 to 12. So a test in this selection failed once and
  passed twice since; CI's run will name it if it fails again.
* The test files changed, and the always-run CLI wiring tests among the first 45 files, passed in those
  runs; the evaluation tests passed as recorded above.

**After ruling 3** (the route): `ruff format --check .`, `ruff check .` → all checks passed (after one
commit, `73f6516`, went in with a line one character over the limit: its check was piped to `tail`,
which hid the exit code; fixed in the next commit); `pyright packages/debate_core packages/debate_cli`
→ 0 errors; `lint-imports` → 20 kept; `check_thin_handlers.py` → OK; `check_command_blocks.py` → OK;
`validate_specs.py` → OK. The affected set is now 455 of 672 test files (the router package reaches
most of the suite): CI's. Within two minutes the session ran the always-run list, both changed
packages' router and evaluation tests, the Bedrock adapter's, the budget's, the routing-file checks and
the two runbook tests: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m
"not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py … ` →
**1 failed, 1387 passed in 48.53s**.

**The one failure, noted as the PM asked**:
`packages/debate_cli/tests/test_container_factories.py::test_every_factory_builds_and_between_them_they_import_every_wired_integration`,
on its planted break: `debate_core.integrations.discovery.feed_config: discovery_providers() under the
test profile built without it`. It is not this branch's: with `packages/` checked out at the task's start
commit (`807ab22`) it fails the same way, alone (`-n 0`) and under `-n 4`. It passed at 21:40 inside the
first 20 affected files' run, and has failed on every run since about 21:45 (2026-11-02, this Mac), so it
looks like this machine's state rather than code; it may be the 11% failure above. It is on the
always-run list, so CI's run will say whether it fails there too.

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

### What was built, after the PM's rulings (2026-11-03)

* **`RoutingPolicy.standing_in(route, for_class=…)`** and **`build_model_router(…, stand_ins=…)`**: the
  policy is changed once, before the real router and the budget guard's `RoutePricing` are given it, so
  the calls go to the named route's model and the guard prices that model's ceiling. Only a generative
  route stands in for a generative class (`RoutingConfigError` otherwise). The prompt keeps the task class
  it declares; replay and the fake read no route.
* **The container**: `landscape_evaluation(…, route=…)`, `landscape_model_stage(…, route=…)` and
  `landscape_cassettes(route)`; the directory is `cassette_directory_name(route)`,
  `model-cassettes-<route>` beside `model-cassettes`.
* **`landscape evaluate --route <task class>`**: record, replay and `--breakdown` all read the route's
  directory, and so does the cassette scan; `data.route` names the route that answered (`high_volume`
  without the option). `embeddings` and `rerank` are refused, exit 2 `ROUTE_NOT_GENERATIVE`, before
  anything is built; `--check-sample` takes no `--route`.
* **`landscape cassettes --route <task class>`** counts and deletes that directory's cassettes, naming it
  as `<data dir>/landscape/model-cassettes-<route>/`.
* **Docs**: the record runbook's section "Recording on another route" holds the block; the purge and
  removal runbooks say where a route's cassettes are and to tell the PM before closing (see Deviations).

**Red first.** The new tests at HEAD against the five source files at the commit before the route
(`8125592`): **11 failed, 21 passed in 2.58s**. The reasons show the interface absent rather than a
behaviour wrong: the CLI tests got a usage error (no `--route` option) or a `KeyError: 'route'`, and the
factory tests a `TypeError` (no `stand_ins` parameter). The mutants below are what test the behaviour.

**Mutants of the route**, each against the committed code, the four route test files run, restored from
HEAD; all ten caught:

| Mutant | Caught by |
|---|---|
| The factory ignores the stand-ins | 5 tests |
| The budget guard prices the file's own route (the stand-in reaches the router only) | `test_the_budget_guard_prices_the_stand_in_routes_ceiling` |
| A route that answers no prompt stands in | 2 tests |
| A route records to the default directory | 3 tests, among them the PM's: `test_evaluate_record_on_a_route_writes_only_that_routes_directory` |
| The container passes no stand-in (the directory changes, the model does not) | `test_evaluate_record_on_a_route_writes_only_that_routes_directory` |
| The evaluation scans the default directory | the same test's scan assertion, added for it before the run |
| `evaluate` drops `--route` | 3 tests |
| `evaluate` takes any route | 2 tests (the factory's own refusal stands behind it, with another code) |
| `--check-sample` takes `--route` | 1 test |
| `landscape cassettes` ignores `--route` | 1 test |

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

**The PM's answer (2026-11-03)**: 1, dev `deep_audit`; 2, (A), with the spec amended (packages gain
`debate_core.integrations.models`) and a test that a `--route` recording never writes the default
directory; 3, not built here: the PM files prompt 1.2.0 as its own task after ac3's result, carrying (a),
(b) and the labelling convention (the first item under Follow-up work), if the coach confirms it.

## The second route's recording (2026-11-03)

The operator's block, from this worktree: the sample check (labelled 47, by kind advantage 16, cp 6, da 5,
k 10, none 3, t 7; 2 second labels), then the recording and the breakdown on `--route deep_audit`. The
recording and its replay agree on every count. Figures from the pasted JSON; costs from
`config/model_pricing.yaml` at each run's own tokens. For the PM to record in docs/data.

| | `high_volume`, Claude Haiku 4.5 (2026-11-02) | `deep_audit`, Claude Sonnet 4.6 (2026-11-03) |
|---|---|---|
| Calls; input / output tokens | 3; 38,881 / 3,882 | 3; 38,884 / 4,347 |
| Cost | $0.058291 | $0.181857 (3.12 times) |
| Model alone: correct of counted | 19 of 32, **0.594** | 27 of 36, **0.750** |
| Pipeline: correct of counted (bar 0.85) | 21 of 33, **0.636** | 27 of 36, **0.750** |
| Refused `NO_POSITION` | 12 | 0 |
| Below the threshold (model / pipeline) | 3 / 2 | 11 / 11 |
| Coverage (pipeline) | 33 of 47, 0.702 | 36 of 47, 0.766 |
| Wrong: same kind / other kind / placed though none | 6 / 6 / 1 | 3 / 4 / 2 |
| The model's set (the 43 sent) | 17 of 29, 0.586 | 23 of 32, 0.719 |
| Weighted to the strata | 0.491 | 0.718 |
| Batches | 3 answered | 3 answered, none repaired |

* **Neither meets the bar.** Sonnet 4.6 raises the pipeline from 0.636 to 0.750, 11 points short.
* **The pipeline equals the model alone on Sonnet.** The headings place rows 11, 30, 31 and 59, each
  naming the label, and Sonnet answered all four rightly, so stage one changes no count.
* **The refusals become low confidences.** Sonnet answered every card. Of Haiku's 10 refusals of labelled
  cards, 3 are now counted and right (rows 14, 17 and 39) and 7 fall below the 0.6 threshold. Of all 11
  below-threshold answers, 1 names the label (row 46, `generic-k`), so the threshold is holding back the
  wrong ones.
* **What is still wrong** (9 of the 36 counted): advantages 5 (3 same kind, 2 other kind), a kritik
  answered `kritikal-aff`, a CP answered `should-t`, and 2 cards labelled none placed. Both cards
  labelled `pharma-advantage` were answered `pharma-da`, one counted and one below the threshold.
* **Second labels**: 2 cards, 0 correct on the second label (row 34 correct on its first, as under Haiku).
* **The scan of the prompt inputs is clean** (3 texts, 0 hits). The cassette scan is not: 3 texts naming
  a school, 2 a team code and 1 a tournament, so the command exits 1 for the scan before the bar. Its 42
  hits are all marked: 38 a JSON key's name in a model rationale, 3 taxonomy words in a rationale, 1 a
  taxonomy word in the cassette metadata; none copied from a card and none naming a team. The same kind
  as the 1.1.0 cassettes' 27, `v1-e32-t44`'s subject. The operator reads them in the terminal
  (follow-up 2) and judges them before the PM decides whether these cassettes are kept.

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
* Ruling 3: `debate_core/integrations/models/routing_policy.py` (`standing_in`) and `factory.py`
  (`stand_ins`); `debate_cli/container.py` (the route through the evaluation, the stage and the
  cassettes; `cassette_directory_name`); `commands/landscape.py` (`--route`, `data.route`,
  `ROUTE_NOT_GENERATIVE`); `commands/landscape_cassettes.py` (`--route`). Tests: `test_factory.py`
  (the stand-in reaches the real router and the guard's pricing; generative only),
  `packages/debate_cli/tests/test_landscape_evaluate_route.py` (new: record, replay, the default
  directory untouched and finding nothing, `landscape cassettes --route`, refusals),
  `test_container_factories.py` (values for `route`), `test_landscape_command.py` (the stubs take
  `route`; `data.route`). Docs: the record runbook's route section; a paragraph each in
  `annual-purge.md` and `caselist-removal.md`. Spec: the packages amendment, the ruling as a comment
  above it.

## Deviations from the spec

* **`tests/smoke/test_landscape_evaluate_smoke.py`** is outside `constraints.packages`. Agreement 5 asks a
  task that changes a user-facing surface to update its smoke checks, and `landscape evaluate`'s JSON and
  exit code changed. The smoke file was not run here (it needs an installed build); validate-dev runs it.
  Its new figures were checked in-process: the service over the same world gives model alone 4 of 4 and
  pipeline 4 of 4 with 2 by the headings.
* **The replay and the two counting scripts were run by the session**, not the operator: read-only,
  offline, over this Mac's store and cassettes, 113 s, 33 s and 32 s (agreement 2). The replay runbook
  calls the replay the operator's.
* **Ruling 3 needed code outside the spec's packages** (the router factory); the PM amended the spec on
  2026-11-03, and this branch carries the amendment.
* **The purge and removal runbooks get a paragraph, not blocks.** Their cassette blocks are pinned by
  `tests/docs/test_annual_purge_runbook.py` and `tests/docs/test_removal_runbook_cassettes.py` (one
  listing and one delete; a dry run and a delete), outside the spec's packages, and a block for each route
  directory needs its own code per directory. So each says where a route's cassettes are, that
  `landscape cassettes --route` reaches them, and to tell the PM before closing if a `model-cassettes-`
  directory exists. Blocks for them are under Follow-up work.
* **The recording runs from this task's worktree** (the block's `cd`), since `--route` is not on `dev`
  until this branch merges; the runbook's copy says to run it from a checkout that has the option.

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

### 1. The second route's recording (ac3): done 2026-11-03

The operator ran this block; the JSON is summed up [above](#the-second-routes-recording-2026-11-03).

**Operator command** (expected runtime 3 to 5 minutes; about $0.17 on Bedrock)
Where: your Mac, in this task's worktree, which has `--route` before it reaches `dev`. In order: the
sample check, the Bedrock login check, the recording on `deep_audit`, then the breakdown replaying it. A
`STOP:` line stops it before any model call. It is the record runbook's "Recording on another route"
block, with the `cd` first.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Success looks like three JSON objects: the sample check with `labelled` 47; the recording with `route`
`deep_audit`, `prompt_version` `1.1.0`, `labelled`, `found` and `asked` 47 and `calls` 3 or 4 (exit 0
when the pipeline meets the bar and every scan is clean, otherwise exit 1 `EVALUATION_BELOW_BAR` with the
counts in `error.details`); and the breakdown with the same counts and `breakdown.outcomes` summing to
47. **Paste the three JSON objects back, and nothing else.** A stop before any answer
(`MODEL_ACCESS_DENIED`, a budget refusal) recorded nothing: paste it and do not run it again before the
PM has read it. Nothing under `~/.debate-research/dev/landscape/model-cassettes/` changes; the recording
lands in `model-cassettes-deep_audit/`.

### 2. Only if a scan count in the recording is above zero: the hits, in the terminal

**Needed**: the recording's cassette scan counted 3 schools, 2 team codes and 1 tournament (42 marked
hits).

**Do not paste or copy this output anywhere**, a Claude session included. Give each hit's number and
whether its words name a team, a school or a tournament, or are an ordinary word that shares them.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t43-model-evaluation-system-score-refusals-and-a-second-route
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Then the PM records the side-by-side table in `docs/data/landscape-model-evaluation.md`: accuracy for
the model alone and the pipeline, refusals and cost, `high_volume` (Haiku 4.5) beside `deep_audit`.

## Follow-up work

* **The wrong answers decide the bar** (12 of the pipeline's 33 counted: 6 a same-kind neighbour, 5 another
  kind, 1 placed though labelled none). 4 of the 5 other-kind answers are of cards in a file read by the
  side opposite the label's, where the coach labels the position the card answers: a labelling convention
  the prompt's "the argument the card is read as" does not state. E32, the PM's to file.
* **Purge and removal blocks for a route's cassettes**: the two runbooks' cassette steps run the default
  directory only, and say in a paragraph to tell the PM when a `model-cassettes-<route>` directory exists.
  A block per route directory (with its own confirmation code) and its runbook tests belong in E32, the
  PM's to file; `landscape cassettes --route` already does the work.
* **A null answer's confidence** carries no steady meaning (0.15 to 0.3 in one batch, 0.5 to 0.7 in the
  next); the stage discards it. Nothing to change unless a later rule reads it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

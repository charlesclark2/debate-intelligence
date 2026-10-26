# Session report: v1-e32-t07-model-classification-stage

| | |
|---|---|
| Task | `v1-e32-t07-model-classification-stage` — Model classification of what headings cannot place |
| Spec | [`plan_specs/v1/e32-argument-landscape/t07-model-classification-stage.yaml`](../../plan_specs/v1/e32-argument-landscape/t07-model-classification-stage.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t07-model-classification-stage` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The model stage is built and tested on fake and replay routers, and nothing in it has called a real
model.

* **What reaches the model.** Cards that headings and tags leave unplaced, or place below the review
  threshold, go to `landscape.classify_position` 1.0.0 (released and locked). They go in batches of 20,
  on the `high_volume` route, through the `StructuredOutputGuard`. Each card is asked about once per
  fingerprint, and the most shared fingerprints go first.
* **What a card sends.** Its normalized headings, tag, short cite, and the first 120 words of its
  evidence. Every school, team code and tournament of the caselist is taken out first.
* **What is refused.** An answer is refused, and its card stays in the review queue, when its position
  id is unknown or retired, when its rationale repeats 12 or more consecutive words of the card, or
  when it names no position.
* **Caching.** Results are cached with method MODEL, `prompt_id`, `prompt_version` and `model_id`.
  Refusals are cached too, so a second run asks nothing, and a prompt version bump asks again only
  about MODEL results.
* **The cap.** A run asks about at most `max_model_items` cards (default 2,000). A run that held cards
  back exits 1 after caching what it asked.
* **The commands.** `landscape report --model-mode` gains `replay` and `live`. `live` is refused while
  the data-use policy leaves open question 4 open. A new `landscape evaluate` scores the stage against
  the coach's labels and scans the prompt inputs and cassettes for names (ac4).

**The Goal stays InProgress, and the PR merges `--partial`, as the PM's brief said.** Two criteria are
NOT RUN, and no session can close either one:

* ac4 needs the coach's labels and the operator's one recording, after open question 4;
* ac5 is the live run, after open question 4.

**Look at first:** [the count for the PM](#the-count-the-pm-asked-for-first) and
[the questions](#questions-for-the-pm).

## The count the PM asked for first

Read-only on 2026-10-25, with no model call. It covers hspolicy26 through 2026-10-20, 3,825 sources on
`policy-2026-27-nhi` (taxonomy 1.2.0), placed from scratch over an empty in-memory cache. It took
54.5 s, and the full record is in
[first-run-policy.md](../data/landscape/first-run-policy.md#the-model-stage-counted-before-its-first-run-v1-e32-t07).
The stage-one counts match t21's to the card: 63,494 counted, 56,928 unplaced, 1,371 below the
threshold.

| | Count |
|---|---|
| Cards that would reach the model (56,928 unplaced + 1,371 below the threshold) | **58,299** |
| Distinct fingerprints among them, each asked about once | **39,516** |
| Fingerprints standing for one card only | 32,432 |

| First N fingerprints, most shared first | 100 | 500 | 2,000 | 5,000 | all 39,516 |
|---|---|---|---|---|---|
| Cards they place or queue | 3,749 | 7,610 | 14,413 | 21,699 | 58,299 |
| Calls at 20 a batch | 5 | 25 | 100 | 250 | 1,977 |

**Prompt size.** I measured it on about an eighth of the candidates: those from sources whose digest
starts with `0` or `1`, 6,676 cards. I rendered their batches through the prompt registry exactly as
sent:

* 12,329 characters of system turn a call, which holds the 102 active positions;
* 19,512 characters of cards a call;
* 892 characters for the median card.

**Cost at dev routing** (Claude Haiku 5.5). I assumed 4 characters a token and the first-party list
price of $0.10 a million input and $0.50 a million output tokens. I did not read Bedrock's price.
Output runs from 60 tokens an answer up to the route's 2,048-token cap a call, which the model's
default thinking could fill.

| | Input | Output | Cost |
|---|---|---|---|
| First 2,000 fingerprints, 100 calls | 0.79 M tokens | 0.12 to 0.20 M | $0.14 to $0.18 |
| All 39,516, 1,977 calls | 15.7 M | 2.4 to 4.05 M | $2.76 to $3.60 |

So even the whole backlog fits in two days of the $2 daily dev budget. **The cap I propose is 2,000.**
That number is not about cost. It keeps the first live run small enough to check: 14,413 cards, a
quarter of the leftovers, before the next 37,000 fingerprints are spent.

**The scan of the sampled inputs.** No school and no team-code word of three or more letters remained
(0 of 6,676). The first count found 32 cards with a code word in a heading, because t01's heading rule
keeps another team's code when it stands alone. The stage now takes code words out of headings too
(`sent_headings`), and the second count found none.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-stage`: Model stage, cache entries and replay evaluation | Built and tested; its criterion passes | Everything in the node's description is built: the prompt and guard, post-validation, MODEL cache entries, `max_model_items`, `--model-mode replay\|live`, and the evaluation. What is left is outside a session: the labelled set's labels, the recorded cassettes and the live run (ac4, ac5) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: only items the deterministic stage left unmatched or below threshold reach the model; with the fake router, a fixture where every card carries an alias makes zero model calls | PASS | `test_model_stage_asks_nothing_when_every_card_carries_an_alias`: `router.calls == []`. `test_model_stage_asks_only_about_cards_stage_one_left_unplaced_or_below_the_threshold`: one call holding exactly the 5 hand-counted leftover tags, no section, no placed card. Mutants M1 (every card sent), M2 (below-threshold cards not sent) and M3 (a stage under `none`) are caught |
| ac2: a rationale repeating 12+ consecutive words of the evidence, or an unknown position_id, is rejected and the item goes to the review queue | PASS | `test_model_a_rationale_repeating_twelve_words_…_goes_to_the_review_queue`: card back to UNPLACED, `model_refused == {"ECHOES_EVIDENCE": 1}`, `queued_cards == 2`. The 11-word boundary is accepted. `test_model_an_unknown_position_id_goes_to_the_review_queue` covers an invented id, another topic's id and a non-id, and `…a_retired_position_id…` covers a retired one: each leaves stage one's result, which needs review. Mutants M4 to M10 are caught |
| ac3: MODEL results record prompt_id, prompt_version and model_id; a second run over an unchanged snapshot makes zero model calls; a prompt version bump re-runs only MODEL results; exceeding max_model_items exits 1 after writing what it has | PASS | `test_model_results_name_prompt_and_model_…` checks `(landscape.classify_position, 1.0.0, fake-model)` on all six MODEL cards. `test_model_a_second_run_…_makes_no_model_call`: no calls, no placements, `model_hits == 5`, the cache unwritten. `test_model_a_prompt_version_bump_asks_again_about_model_results_only`: the matcher places nothing, the model is asked about all 5 again, and the cache keeps `none` and `1.1.0` only. `test_replay_over_its_card_limit_exits_1_after_caching_what_it_asked` (CLI): exit 1, `MODEL_BUDGET_EXCEEDED` with sent 1, allowed 1, held_back 1, the queue written, no report; the next run asks about the rest and exits 0. Mutants M11 to M15 and M19 are caught |
| ac4: replay evaluation against a coach-labelled 60-item set (Policy and LD de-extinction, cassettes recorded once by the operator) reports per-format accuracy ≥ 85% for classified items, and a scan of the prompt inputs and cassettes finds no school name, team code or debater name | NOT RUN | No session can close it. The coach has labelled 0 of t21's 60 cards (counted 2026-10-25 from the file, no content read). The cassettes are recorded once, after open question 4 (the PM's brief). LD has no de-extinction taxonomy yet (`v1-e32-t06` is Pending). What is built and tested: `landscape evaluate` and `evaluate_labelled_cards`. `test_a_recorded_evaluation_replays_to_the_same_score_with_no_model_behind_it` records scripted answers through the record-replay router, replays them with no router behind it, and gets the same hand-worked score (4 counted, 2 correct, 50%, under the bar). The scan's positive control finds a planted school, team code and tournament. The reader joins all 60 rows of t21's real files. On the real sample, the input scan was clean ([above](#the-count-the-pm-asked-for-first)) |
| ac5: operator-run in dev after open question 4: a live run over the newest hspolicy26 snapshot, with model calls, cost and coverage before and after recorded in first-run-policy.md, and the coach's review | NOT RUN | It waits on open question 4 (Bedrock's no-retention terms and the account's logging check) and on `v1-e05-t08`'s Bedrock access, as the PM's brief says. The "before" coverage and the cost estimate are recorded. The blocks are under [Operator follow-ups](#operator-follow-ups), for after the answer |
| Node `model-stage`: `uv run pytest packages/debate_core/tests/application/test_position_classification.py -k model` | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests/application/test_position_classification.py -k model` → **21 passed** in 8.94 s |

## Checks shown failing for their reason

### The red run against a refuse-nothing skeleton

A scratch script swapped in a stage that refuses nothing:

* every card is sent, and no MODEL result is read from the cache;
* tag, cite, headings and excerpt are sent raw and whole;
* there is no cap, and a dry run asks too;
* there is no echo check, no taxonomy check on an answer's id, and no check that the batch is
  answered whole.

**Result:** 33 of this task's tests failed (`-n 0 -p no:randomly`, a fresh Hypothesis directory).
I restored the three source files with `git checkout`; their SHA-1s matched the committed ones and
the tree was clean.

* **14 failed at their own assertions.** Examples:
  * `assert [ModelRequest…] == []`, the alias fixture;
  * `assert None is <Refusal.ECHOES_EVIDENCE>`;
  * `assert () == (BatchProblem…)`;
  * `AssertionError: maple`, a school in the prompt;
  * `assert {'MODEL': 9} == {'ALIAS': 7, 'MODEL': 2}`.
* **19 failed with a `KeyError` in the test's scripted router**, which answers by tag. The skeleton sent
  it cards it should not have, placed or unscrubbed (`KeyError: 'Deficits rise'`). That is the right
  cause, but not each test's own assertion, so the mutants below prove each check one at a time.
* **What passed** were the pure helpers the skeleton leaves intact, and the CLI tests over a stub
  service. The helpers are the echo rule, headings, ordering, batches, prompt variables, the evidence
  reader, the gate and the sample reader. Each helper's protection is shown by a mutant.

My first skeleton was malformed: it made `judge` return a tuple. I fixed it and ran it again; the
counts above are from the second run.

### Mutants (working agreement 8)

I applied each one alone, ran the tests covering it with `-x -n 0 -p no:randomly`, and gave each run
a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`. No property test is involved. Each file was restored
from its bytes and its SHA-256 checked. **21 of 21 were caught**, each at an assertion except where
noted.

| Mutant | Caught by |
|---|---|
| M1 every card goes to the model *(deterministic-only path)* | `test_model_stage_asks_nothing_when_every_card_carries_an_alias`: `assert [ModelRequest…] == []` |
| M2 only unplaced cards, none below the threshold | `…asks_only_about_cards_stage_one_left_unplaced_or_below_the_threshold` |
| M3 a stage is built under `--model-mode none` | `test_report_writes_the_bundle_and_json_…` (CLI): `none` was refused for held-back cards |
| M4 the echo run is 13 words *(echo)* | `…repeating_twelve_words…`: `('spending-da', 'MODEL', 0.9) == (None, None, 0.0)` |
| M5 the echo run is 11 words | `…repeating_eleven_words…_is_accepted` |
| M6 no echo check against the tag | `test_a_rationale_repeating_the_tag_places_nothing` |
| M7 no echo check against the evidence (a first, malformed version that refused everything was discarded and redone) | `…repeating_twelve_words…` |
| M8 the echo check reads raw text, not words | `test_twelve_consecutive_words_of_the_evidence_are_an_echo` |
| M9 no taxonomy check on an answer's id *(unknown ids)* | `test_model_an_unknown_position_id_goes_to_the_review_queue` |
| M10 retired ids count as the taxonomy's | `test_model_a_retired_position_id_goes_to_the_review_queue` |
| M11 no cap *(item cap)* | `test_model_max_items_asks_about_the_most_shared_cards_first…`: `5 == 2` |
| M12 the cap is one too many | the same: `3 == 2` |
| M13 fingerprint order, not most shared first | `…asks_only_about_cards…`: `'no cliff' == 'federal action key'` |
| M14 cards held back do not stop the run | `test_replay_over_its_card_limit_exits_1_…` (CLI) |
| M15 a dry run asks the model | `test_model_a_dry_run_stage_counts_and_asks_nothing` |
| M16 headings keep team-code words | `test_sent_headings_lose_team_code_words_and_empty_headings` |
| M17 the excerpt is the whole evidence | `test_model_a_card_sends_no_school_…`: `207 == 120` |
| M18 a refusal replaces stage one's result | `…repeating_twelve_words…`: `(None, 'MODEL', 0.0) == (None, None, 0.0)` |
| M19 cached MODEL results are not read | `test_model_a_second_run_…_makes_no_model_call` |
| M20 the gate ignores an `Open` status | `test_the_gate_refuses_while_question_four_is_open` |
| M21 an unanswered card is not a batch problem | through the service, by a `KeyError` (the stage crashed on the unanswered card); run again against the pure test alone (M21b), caught at its assertion in `test_a_batch_missing_duplicating_or_inventing_items_names_each_by_label` |

## Tests and checks run before this report

`uv run scripts/affected_tests.py` chose **241 of 501 test files (48.1%)** from 24 changed files,
because the CLI container and the classification service are hub modules. That is about half the
roughly six-minute suite, so over the two-minute line. Under working agreement 10 I did not run it and
leave it to the PR's `ci`. What I ran instead, with the alarm on the interpreter:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape packages/debate_core/tests/domain/test_landscape_classification.py packages/debate_core/tests/integrations/models packages/debate_core/tests/integrations/test_local_parsed_store.py tests/architecture tests/specs tests/scripts/test_compare_local_classifier.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py -m "not slow and not live"` | 1,858 passed, 24.2 s |
| `.venv/bin/python -m pytest packages/debate_core/tests/application -m "not slow and not live"` | 3,798 passed, 80.4 s |
| `.venv/bin/python -m pytest packages/debate_cli/tests/test_landscape_command.py packages/debate_cli/tests/test_installation.py packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py tests/smoke/test_landscape_smoke.py -m "not slow and not live"` | 139 passed, 17.5 s |
| `uv run ruff format --check .` / `uv run ruff check .` | 1,393 files formatted / all checks passed |
| `.venv/bin/pyright` (the whole repository, as CI runs it) | 0 errors |
| `uv run lint-imports` | 18 kept, 0 broken |
| `uv run python scripts/check_thin_handlers.py` | 62 handlers within 25 statements |
| `uv run scripts/lock_prompts.py --check` | exit 0 |
| `uv run python scripts/check_command_blocks.py` and `scripts/docs_index.py --check-descriptions` | OK; 49 documents described |
| `uv run pre-commit run check-merge-conflict --all-files` | Passed |
| `uv run scripts/validate_specs.py` | OK: 464 files, 40 epics, 402 tasks, 22 releases |

The rest of `packages/debate_cli/tests` imports the container, and `ci` runs it.

## Files changed

* **`debate_core.domain.landscape_classification`:** `ModelPositionAnswer(s)`, the prompt's output
  schema. Per card it holds an `item-N` label, a position id or null, a confidence and a rationale, and
  nothing else.
* **`debate_core.arguments.landscape`:**
  * `model_stage.py` (new), the pure half:
    * the candidate and item;
    * `sent_headings`, `bounded_words`, `model_order`, `batches`, `prompt_variables`;
    * `answer_problems`, `echoes`, `judge`, `refusal`, `name_scan`.
  * `tag_scrub.py` (new): t21's `card_tag` and `code_words`, moved unchanged out of
    `local_classifier.py`, which imports scikit-learn. `local_classifier.py` now imports them.
* **`debate_core.application`:**
  * `landscape_model_stage.py` (new): the stage, with batches through the guard, the cap, the plan-only
    dry run and the interruption. Also `ParsedStoreCardTexts`, which reads each stored card's
    `evidence_text`, and `model_use_gate`.
  * `position_classification.py`: a second pass with an optional stage, MODEL cache keys,
    `model_candidate`, and the new counts.
  * `landscape_run.py`: `LandscapeModelMode` `replay` and `live`, the stage factory,
    `max_model_items`, `ModelBudgetExceeded` for held-back cards, and `ModelStageInterrupted`.
  * `landscape_model_evaluation.py` (new): the coach-sample reader, the scoring and the scans.
* **`prompts/landscape/classify_position.md`** (new, released 1.0.0) and **`prompts/prompts.lock.json`**.
* **`packages/debate_cli`:**
  * `commands/landscape.py`: the `report` options and the `evaluate` command, its JSON and its gate;
  * `commands/__init__.py`: the command's registration;
  * `container.py`: `landscape_model_stage` and `landscape_evaluation`, and the cassette directory
    under the data directory;
  * tests: `test_landscape_command.py` (the old "replay is a usage error" test now checks `record`),
    and the integration pins in `test_installation.py`, `commands/test_doctor.py` and
    `bucket_mode/test_bucket_mode_lock.py`.
* **Tests in `debate_core`:**
  * 21 `model` tests in `test_position_classification.py`;
  * `arguments/landscape/test_model_stage.py` (new);
  * `application/test_landscape_model_stage.py` (new).
* **`docs/policies/caselist-data-use.md`:** the two citations of `v1-e32-t02` (model-use rule 3, E32
  gate item 3) now name `v1-e32-t07`, as the spec asks. It is a correction that loosens nothing; the
  version and approval table are untouched ([question 6](#questions-for-the-pm)).
* **`docs/data/landscape/first-run-policy.md`:** the pre-run count, aggregates only.

## Deviations from the spec

1. **Cards only, never sections.** The spec says "items", and stage one also places sections. But a
   section has no tag, cite or evidence to send, and the report counts cards only. A section the model
   placed would change nothing a report shows.
2. **Real cassettes live under the data directory, not in the repository.** Policy model condition 6
   says committed cassettes are synthetic, so the operator's ac4 recordings of real cards go to
   `<data dir>/landscape/model-cassettes/`, under its retention and removal. CI replays only cassettes
   that the tests record from scripted answers (`test_a_recorded_evaluation_replays…`).
3. **The evidence excerpt comes from the parsed store, not the source files.** t21 reported that
   evidence text needs every source parsed again. In fact each stored card keeps its `evidence_text`; I
   checked the keys of one real record, not its text. Only the documents holding candidates are read
   again.
4. **A new command, `landscape evaluate`.** The spec names `--model-mode` on `report` only. ac4's
   evaluation and its recording need an entry point, and `packages/debate_cli` is in this task's
   packages. It writes no bucket and is classified so.
5. **I moved two functions in t21's `local_classifier.py`** (to `tag_scrub.py`), so the stage reads
   names by t21's rule without scikit-learn, which an installed build does not have. Behaviour is
   unchanged, and t21's tests pass (`packages/debate_core/tests/arguments/landscape`, in the first run under [Tests and checks](#tests-and-checks-run-before-this-report)).

## Decisions and assumptions

1. **The prompt's schema is static and the id check comes after.** The guard requires the registered
   schema class itself, so the per-taxonomy `Literal` of t02's `classification_schema` cannot be the
   prompt's schema. `position_id` is any short string in the answer, and `checked_against` judges each
   answer. That way one unknown id sends one card to the queue rather than failing a batch of 20.
2. **The role is not asked for.** It comes from the headings, as the matcher's TAG_KEYWORD-alone rule
   decides it: ANSWERS under an answer heading. The model returns ids, confidence and a rationale only.
3. **Refusals are kept in the cache as MODEL results placing nothing.** They never reach a
   classification: stage one's result stands. Without them, a second run would ask again about every
   refused card. The same goes for a batch refused after its one repair: its 20 cards are cached as
   refused, and a prompt bump is the way to ask again.
4. **The echo check also covers the tag**, which the forbidden list names beside the evidence. Words
   are compared as lowercase words, so punctuation and case cannot hide a quotation.
5. **Batches of 20.** Twenty answers fit the `high_volume` route's 2,048 output tokens with room left.
   The system turn, which holds the positions, is the same on every call, ready for prompt caching if
   the adapter ever sends it.
6. **`--model-mode none` ignores cached MODEL results**, so a `none` report is stage one's alone and the
   report header's prompt version says so.
7. **The live gate reads the policy's open-questions row 4** from the checkout, and refuses while its
   status says `Open` or when there is no policy to read. An installed build has no checkout and no
   prompts, so its model stage is refused anyway.
8. **A provider error stops the stage.** That covers a model that cannot be reached, or that refuses
   the call for rate or access. What was answered is cached, and the run ends with
   `ModelStageInterrupted` (exit 1) before any report is written.
9. **Tokens per run** (policy condition 7) are reported in `--json`'s `classification.model` and on the
   human output's model line. They cover the calls whose answers were used: the guard keeps no usage
   for a refused first attempt.

## Questions for the PM

Paste-ready:

> **v1-e32-t07: the model stage is built on fakes; seven rulings before its first live run**
>
> The count (hspolicy26 through 2026-10-20, read-only, no model call): **58,299 cards** would reach the
> model (56,928 unplaced, 1,371 below the threshold). They are **39,516 distinct fingerprints**, each
> asked about once. Most shared first, the first 2,000 fingerprints cover 14,413 cards in 100 calls.
> Estimated at Haiku 5.5's first-party list price: **$0.14 to $0.18 for 2,000**, and **$2.76 to $3.60
> for all of them**. Bedrock's price was not read, and the range is the model's thinking.
>
> 1. **`max_model_items`.** I propose **2,000 a run** (the default now). Options:
>    * (a) 2,000: the first live run is small enough for the coach to check *(recommended)*;
>    * (b) 10,000 (about $0.90): the backlog in four runs;
>    * (c) no practical cap: the whole backlog in one run, just over the $2 day.
>
>    It is not about cost: (a) puts a quarter of the cards in front of the coach before the rest is
>    spent.
> 2. **Ordering.** I propose **most shared first**: the cards that stand for the most rounds go first.
>    That places the most cards a call, and it is deterministic. t26's proxy confidence is the other
>    option, but it needs scikit-learn and its trained model at run time, and t26 is Pending. Recommend
>    most shared first now, and revisit after t26.
> 3. **Below-threshold cards and policy rule 3.** The spec's ac1 sends the 1,371 cards placed by a tag
>    keyword alone (0.5). Rule 3 says "only items the deterministic stage could not match". Do those
>    cards count as "could not match"? Options:
>    * (a) yes, send them, as the code does, and the next policy version could say "could not place at
>      or above the review threshold" *(recommended: the review threshold is the line the report counts
>      at)*;
>    * (b) send only unplaced cards. That is a one-line change, and mutant M2 shows the test that would
>      change.
> 4. **The labelled set.** Use t21's 60-card coach sample as **the Policy half**, so the coach labels
>    once. `landscape evaluate` reads t21's CSV and rows file directly (all 60 rows join; 0 labelled
>    today). Note that t21's sample holds unplaced cards only, none below the threshold. For **LD**, draw
>    30 de-extinction cards when two things are true:
>    * `v1-e32-t06`'s taxonomy is released;
>    * the first weekly snapshot after Badgerland (Nov 13–14) is in, with MinneApple (Nov 7–9) before it.
>
>    Draw them the way t21 drew Policy's: one per document, seeded. Accept 60 Policy plus 30 LD, or
>    hold the set at 30 and 30?
> 5. **Dev routing effort.** The `high_volume` dev route sets no effort, so Haiku 5.5 thinks at its
>    default, `medium`. That is up to the 2,048-token cap a call, and it is the top of each cost range.
>    I propose `effort: low` on `high_volume` in `config/model_routing.dev.yaml` (and prod). That file
>    is outside this task's packages; it could be a follow-up, or the PM's batch.
> 6. **The policy correction.** The two citations now name `v1-e32-t07` (rule 3, E32 gate item 3), and
>    loosen nothing. I left the version and approval table alone, as sessions do. Record them as 1.19 at
>    the next close-out?
> 7. **Retention of the cassettes.** `<data dir>/landscape/model-cassettes/` will hold scrubbed real
>    excerpts once the operator records. That is the same gap as t21's question 3: the removal runbook
>    and the annual purge do not name it yet. Add one line to each in a follow-up?
>
> I will proceed on nothing further: this branch stops here for review and merges `--partial`.

## Operator follow-ups

None to run now. Every step below waits until the data-use policy records open question 4 as
answered, Bedrock access exists (`v1-e05-t08`), and the coach has filled the `position` column of
`~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.csv`.
The blocks are written now so they can be reviewed.

**1. Record the Policy evaluation once** (expected runtime about 1 minute, 3 calls, a few cents).
Where: your Mac, in this task's worktree, or in dev after the merge. The block refuses a leftover
`DEBATE_*` override or a running pull. It writes cassettes under
`~/.debate-research/dev/landscape/model-cassettes/`, and nothing in the repository or a bucket.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t07-model-classification-stage
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape evaluate --caselist hspolicy26 --sample ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --model-mode record; fi
```

Success looks like:

* a `Labelled N, found N` line with N above zero;
* a `Counted …: …%` line;
* `Scan … 0 naming a school, 0 a team code, 0 a tournament` for both the prompt inputs and the
  cassettes.

Exit 0 means at or over 85% with clean scans; exit 1 means under the bar or a name found. Paste the
four lines back. `MODEL_USE_NOT_YET_ALLOWED` means the policy row still says `Open`.

**2. Replay it** (seconds, no model call). Same command with `--model-mode replay`. It should print
the same counts.

**3. The live run of ac5** is two blocks. Paste the second only after reading the first's model line.
The first is a dry run: it asks nothing and writes nothing.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape report --caselist hspolicy26 --model-mode live --dry-run --max-model-items 2000; fi
```

Read its `Model stage (1.0.0): asked about … card(s)` line. Stop when `asked about` is 0, which means
there is nothing to ask. Stop also when it is over 2,000, which means the cap was not applied. The
second block makes the calls, caches them, and writes the report locally. It publishes nothing.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape report --caselist hspolicy26 --model-mode live --max-model-items 2000 --no-publish; fi
```

Success looks like:

* exit 1 with `MODEL_BUDGET_EXCEEDED`, `held_back` above zero, and `sent` 2000, which is expected
  while the backlog is larger than the cap;
* or exit 0 with the model line's tokens above zero.

Paste the model line and the `cards … counted` line back for `first-run-policy.md`.

## Follow-up work

* **Dev and prod routing:** `effort: low` on `high_volume` ([question 5](#questions-for-the-pm)), for
  `v1-e05`'s routing owner.
* **Retention:** name `<data dir>/landscape/model-cassettes/` in `docs/runbooks/caselist-removal.md`
  and the annual purge ([question 7](#questions-for-the-pm)), with t21's local-classifier directory.
* **The LD half of the labelled set** after `v1-e32-t06` and the mid-November snapshot
  ([question 4](#questions-for-the-pm)).
* **`docs/guides`:** the coach's review-queue guide does not describe the model stage yet: that a card
  the model placed below 0.6 still comes to the queue, and that a refused answer leaves its card there.
  `docs/guides` is outside this task's packages.
* **t21's note** that evidence text needs a re-parse is wrong for the parsed store (Deviation 3). A
  t21 follow-up measuring tags plus evidence could read it directly.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

The model stage built the right way round: counted before anything is spent, scrubbed before
anything is sent, and gated on the policy rather than on good intentions.
1. **ac1 to ac3 and the node's criterion pass.**
   * The tests were red against a refuse-nothing skeleton: 33 failed. The 19 that failed through the
     scripted router's `KeyError` are honestly separated from the 14 that failed at their own
     assertions.
   * All 21 mutants were caught, M21 at its own assertion on a second run.
2. **ac4 and ac5 are NOT RUN, as the brief said.** They wait on the policy's open question 4, on
   `v1-e05-t08`'s Bedrock access, and on the coach's labels. ac4's LD half also waits on `v1-e32-t06`.
   The PR merges `--partial`.
3. **The count is what the PM asked for.**
   * 58,299 cards, 39,516 distinct fingerprints, and $2.76 to $3.60 for all of them.
   * The stage-one counts match t21's to the card.
   * The first scan's 32 team-code words in headings were found and fixed (`sent_headings`) before the
     report, which is the scan doing its job.
4. **Rulings on the seven questions:**
   1. **`max_model_items`: (a), 2,000 a run.** The first live run is small enough for the coach to
      check.
   2. **Ordering: most shared first,** revisited after `v1-e32-t26`.
   3. **Below-threshold cards: (a), send them, as built.** The review threshold is the line the report
      counts at, and a tag keyword alone (0.5) is not a match the report trusts. The policy's rule 3
      is reworded in the PM batch that follows ("items the deterministic stage could not place at or
      above the review threshold"), with the coach's approval on merge, before any live run.
   4. **The labelled set: 60 Policy plus 30 LD.** Policy is t21's 60-card sample, labelled once.
      Thirty LD de-extinction cards are drawn the way t21 drew Policy's, after `v1-e32-t06` is
      released and the first snapshot after the mid-November tournaments is in.
   5. **Effort:** not changed now. `high_volume` is shared, and the whole backlog costs under $4 at
      its default. A per-prompt effort setting is filed as an E05 follow-up.
   6. **The policy's two citations:** recorded in the same PM batch's policy version, with rule 3's
      wording.
   7. **The cassettes' retention: yes.** The PM adds `<data dir>/landscape/model-cassettes/` to the
      removal runbook and to `v1-e30-t28`'s amendment.
5. **Deviations 1 to 5 accepted:**
   * cards only;
   * real cassettes under the data directory, never committed (policy condition 6);
   * the excerpt from the parsed store's `evidence_text`, which corrects t21's note;
   * `landscape evaluate`, classified as writing no bucket;
   * t21's two scrub functions moved out of the scikit-learn module unchanged.
6. **Decisions 1 to 9 accepted:**
   * a static schema with the id checked after, so one bad id costs one card, not a batch;
   * no role asked;
   * refusals cached as MODEL results placing nothing;
   * the echo check over the tag as well, and by words;
   * batches of 20;
   * `none` ignoring cached MODEL results;
   * the live gate reading row 4;
   * a provider error stopping the stage after caching;
   * tokens per run in `--json`.
7. **The affected set** (241 files, about half the suite) is left to the PR's `ci` under agreement 10.
   The application suite (3,798 tests), the landscape, models and architecture tests, the CLI's pinned
   lists and the static checks passed.

No re-review is needed. The PM records the evaluation and the live run when the operator runs them.

# Session report: v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances

| | |
|---|---|
| Task | `v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances` — Prompt 1.2.0: the refusal fixes and the coach's answering stance |
| Spec | [`plan_specs/v1/e32-argument-landscape/t46-prompt-1-2-0-refusal-fixes-and-answering-stances.yaml`](../../plan_specs/v1/e32-argument-landscape/t46-prompt-1-2-0-refusal-fixes-and-answering-stances.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances` |
| Session status | COMPLETE (the Goal stays InProgress: ac1's sitting and ac3's re-record are the operator's) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Prompt `landscape.classify_position` 1.2.0 is released and is the stage's default. It carries the refusal
fixes (a) and (b) and the coach's answering stance (c), with 1.1.0's variables and user turn. Its answers
use a new schema, `ModelStancedPositionAnswers`, which requires a `stance` (`reads` or `answers`) that sets
the result's role. 1.0.0 and 1.1.0 keep `ModelPositionAnswers`, so their recordings keep their keys and
replay as recorded. The coach's sample reads `at:<id>` in `position` and `also`, and `--check-sample`
counts `by_stance`. A placement's stance is scored the way the report counts it, and the label's position
with the other stance is the new outcome `wrong_stance`, counted and wrong. The relabelling sitting is
`scripts/relabel_coach_sample.py`, over `debate_core.application.coach_sample_relabel`. All of it was built
on the PM's ruling of 2026-11-05, with tests on invented cards shown failing first; 15 mutants were all
caught.
**The Goal stays InProgress:** ac1's sitting and ac3's re-record on both routes are the operator's (two
blocks under [Operator follow-ups](#operator-follow-ups)). The PM should look first at the 1.1.0 figures
under the stance rule ([ruling 3](#the-pms-ruling-2026-11-05)): without the relabel, Haiku's pipeline score
falls from 0.636 to 0.515.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prompt-1-2-0-refusal-fixes-and-answering` (Prompt 1.2.0) | Done | Its criterion passes (455 tests). ac1 and ac3 wait on the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the stance label's format and the relabelling ruled by the PM, and the coach's relabelled sample reads with `--check-sample` (operator) | NOT RUN (operator) | The PM ruled both on 2026-11-05 ([the ruling](#the-pms-ruling-2026-11-05)). The sitting and its `--check-sample` are the first block under [Operator follow-ups](#operator-follow-ups); the PM records the result |
| ac2: prompt 1.2.0 carries (a), (b) and the stance; a wrong stance is its own outcome; tests on invented cards shown failing first; the version bumped with its cassettes keyed by it | PASS | Red against a skeleton that changes nothing: 65 failed, 70 passed. Then 2 failed for `shown_rows` and `sample_sides`, then 1 for the byte-kept rows; each failure was an assertion, a missing 1.2.0 prompt, or `at:` still refused. Green: 4,033 passed over the changed test directories and the always-run list. 1.2.0 is locked (`scripts/lock_prompts.py`). 1.1.0's key is kept and 1.2.0 never finds it: `test_1_1_0_recordings_replay_unchanged_and_1_2_0_finds_none_of_them`. All 15 mutants caught ([below](#mutants)) |
| ac3: the operator's re-record of the 47 under 1.2.0 on the PM's route, its breakdown and scans, recorded in docs/data (operator, recorded by the PM) | NOT RUN (operator) | The PM ruled both routes. The second block under [Operator follow-ups](#operator-follow-ups); the PM records it |
| Node: Prompt 1.2.0 tests pass (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "evaluat or prompt or stance"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k "evaluat or prompt or stance"` → 455 passed in 26 s |

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 324 of 693 test files (46.8%) from 29 changed files. Over two minutes, so it is left to the pull request's `ci` (agreement 10) |
| The changed test directories and the always-run list: `packages/debate_core/tests/{arguments/landscape,domain,integrations/models,integrations/landscape}`, every `test_landscape_*`, `test_coach_sample_*` and `test_position_classification.py` in `debate_core/tests/application`, `debate_cli/tests/test_landscape*.py`, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | 4,033 passed in 58 s |
| `tests/integration/test_e2e_caselist.py` and `tests/smoke/test_landscape_evaluate_smoke.py`, with `-m "slow or not slow"` | 4 passed |
| `tests/fixtures/caselist/test_synthetic_archive.py` | passed (the re-recorded cassette is what its script writes) |
| `uv run ruff format --check .`, `uv run ruff check .` | 1,944 files formatted; all checks passed |
| `uv run pyright packages/debate_core packages/debate_cli` and the script, smoke and fixture files | 0 errors |
| `uv run lint-imports`, `uv run python scripts/check_thin_handlers.py` | 20 contracts kept; 72 handlers within 25 statements |
| `uv run scripts/lock_prompts.py --check`, `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py` | OK |
| `uv run scripts/validate_specs.py` | OK: 619 files |

### Mutants

Run against the stance, label and sitting tests, `test_landscape_evaluation_breakdown.py` and
`test_evaluation_pipeline_score.py`, each mutant restored after its run:

| Mutant | Caught by |
|---|---|
| `scored_stance` ignores the role | 5 tests |
| `scored_stance` ignores the file's side | 10 |
| A file disclosed by both sides answers | 1 |
| The right position with any stance is correct | 4 |
| The second label takes the first's stance | 4 |
| A wrong stance is not counted | 2 |
| The headings' placement is scored without its stance | 1 |
| `judge` ignores the model's stance | 4 |
| 1.2.0 is asked without a stance (`>` for `>=`) | 12 failures, the schema-by-version and stage-schema assertions among them (7 fixtures also errored) |
| The `at:` prefix is read with case | 3 |
| `at:none` is taken | 3 |
| A second label refused as its first when only the id matches | 1 |
| The sitting is not shuffled | 1 |
| Every shown row is written as changed | 2 |
| Controls may come from the listed rows | 2 |

A planted break of the `--check-sample` JSON (`by_stance` emptied) failed the smoke check and two CLI
tests for its reason, and was restored.

## The proposal (2026-11-04, for the PM's ruling, kept as written)

Counted on the operator's Mac with a scratch script that replays the kept 1.1.0 cassettes of both routes
through the evaluation's own path (29 seconds, no model called) and prints ids, sides and flags only: each
labelled row's label, its label's side, the side its file was disclosed on, whether it sits under an
answer heading, and each route's outcome and answer id. No tag, heading or card text was printed. The
replay reproduces the recorded scores: Haiku 4.5 model alone 19 of 32, Sonnet 4.6 27 of 36.

### 1. The stance label

* **The label file.** The coach's CSV keeps its `position` and `also` columns. A cell holds `<id>` for a
  card that reads the position, `at:<id>` for one that answers it (`at:politics-da`), `none`, `unsure` or
  blank. The prefix is read without case (`AT:` too), and space after the colon is ignored. Refused by row:
  `at:none`, `at:` with no id, an id that is no active position. `also` takes the same forms; it may name
  the same id with the other stance (the coach accepts either stance), and a second label equal to the
  first in id and stance stays refused.
* **`--check-sample`** adds one key, `by_stance` (`{"answers": n, "reads": m}`, rows labelled a position);
  `by_label_kind` counts the position's kind whatever the stance.
* **The model's answer.** Prompt 1.2.0 names a new output schema,
  `debate_core.domain.landscape_classification.ModelStancedPositionAnswers`: each answer is today's
  (`item`, `position_id`, `confidence`, `rationale`) plus a required `stance`, `reads` or `answers`.
  1.0.0 and 1.1.0 keep `ModelPositionAnswers` unchanged, so their recorded answers still validate. The
  cassette key already covers the prompt version and the schema's path (`fixture_key`), so 1.2.0's calls
  have keys of their own and 1.1.0's recordings on both routes stay served as they are. The stage picks
  the schema by the version it runs.
* **What the stance becomes.** A 1.2.0 answer's stance sets its result's role: `answers` is
  `ANSWERS`, which the landscape report already never counts as a read. A 1.0.0 or 1.1.0 answer has no
  stance and keeps the role the headings give (`ANSWERS` under an answer heading). Stage one's role is
  unchanged. *Recommended:* the model's stance decides over the answer-heading flag for 1.2.0, because the
  model is sent that flag and its headings, and row 13 (below) is a card under an answer heading inside
  its own side's block.

### 2. How a wrong stance is scored

* **A placement's stance, as scored,** is the one the report gives it: `answers` when its role is
  `ANSWERS`, or when every readable side its file was disclosed on is the side opposite the position's
  (the report's rule: "a `Midterms DA` block in an affirmative file is the 2AC answering the DA",
  `landscape_report.py`); `reads` otherwise. A position read by both sides, or a file on no readable side,
  takes the role alone.
* **A new outcome, `wrong_stance`**: the answer names the label's position (or the second label's) with
  the other stance. It sits beside `correct`, `wrong_position_same_kind`, `wrong_kind`,
  `placed_labelled_none`, `refused` and `below_threshold`; a wrong position stays judged by kind as today.
* **The bar counts it as counted and wrong**, for the model alone and the pipeline alike: a report would
  have shown the card in the wrong place (a read that is an answer, or the reverse). The scores' JSON keeps
  its keys; `breakdown.outcomes` gains `wrong_stance`, each card's breakdown its label's stance and its
  answer's stance as scored, and the confusion table writes an answering label or answer as `at:<id>`.
* **What it does to the kept 1.1.0 recordings** (computed, not estimated):

| Labels | Haiku 4.5 pipeline | Sonnet 4.6 pipeline |
|---|---|---|
| Today's scoring, by position only | 21 of 33, 0.636 | 27 of 36, 0.750 |
| The stance rule, no relabel | 17 of 33, 0.515 | 22 of 36, 0.611 |
| The stance rule, the 11 opposite-side rows relabelled `at:` | 21 of 33, 0.636 | 26 of 36, 0.722 |
| The same, and row 13 `at:` too | 21 of 33, 0.636 | 27 of 36, 0.750 |

  Without the relabel, the cards the coach labelled under today's convention (an answering card labelled
  with the position it answers) count as wrong stance: that is the relabel's reason.

### 3. Prompt 1.2.0

Same variables, same user turn, the system turn changed as below (the template, no card text). Front
matter: `version: 1.2.0`, `output_schema: debate_core.domain.landscape_classification.ModelStancedPositionAnswers`,
and its changelog entry. Batches stay at 20, the rationale limit at 280.

```diff
-For each card, choose the argument the card is read as in a round, not the subject it is about. Many cards on one topic are about the same things: the plan, its costs, drugs, the economy. What tells their arguments apart is the claim the debater uses the card to make, and which side makes it.
+For each card, choose the argument the card is read as in a round, not the subject it is about, and its stance toward that argument. Many cards on one topic are about the same things: the plan, its costs, drugs, the economy. What tells their arguments apart is the claim the debater uses the card to make, and which side makes it.
+- The stance is reads when the card makes the position's own argument, and answers when the other side reads the card against the position.
 - Read the tag first: it states the claim the debater uses the card to make. The headings, the cite and the excerpt of the evidence help you decide.
 - A link, internal link or impact card belongs to the disadvantage, advantage or kritik whose story it tells. [unchanged]
 - A topicality card defines a word of the resolution or says a plan breaks a definition. [unchanged]
-- When the list has a generic position of a kind, whose description says it fits no named position of that kind, choose it for a card of that kind that fits no named one, rather than answering null.
-- When a card is marked as under an answer heading, it answers the position rather than reading it. Choose the position it answers.
-- Answer null when no listed position fits, or when the card is general (framing, an impact with no story, a claim about the round) and you cannot tell which position it serves. Never invent an id: use only the ids listed.
+- A card that answers a position belongs to the position it answers, with the stance answers: an affirmative's card against a disadvantage, counterplan or kritik belongs to that negative position, and a negative's card against an advantage or a plan belongs to that affirmative position. Do not choose the plan or advantage the card defends instead.
+- When a card is marked as under an answer heading, it answers the position the headings name: stance answers. A card under an answer heading inside the position's own block, answering the other side's answers to it, still reads it.
+- A kritik's card (its link, framework, impact or alternative) or a counterplan's card (its text, a plank or its solvency) belongs to a kritik or a counterplan even when it reads as general. Choose the named one it fits; when none fits and the list has a generic position of that kind, whose description says it fits no named position of that kind, choose the generic one. Never answer null for such a card.
+- A general card (an impact, a framing claim, an answer) under a heading that names a word of a position's label serves that position: choose it.
+- Answer null only when no listed position fits, or when the card is general and no heading names a word of a position, so nothing says which position it serves. Never invent an id: use only the ids listed.

-Give a confidence from 0 to 1: how likely your position is the one the coach would choose. Use 0.9 or more ...
+Give a confidence from 0 to 1: how likely your position and stance are the ones the coach would choose. Use 0.9 or more ...
```

(a) is the kritik and counterplan bullet, (b) the heading bullet with the narrowed null clause, (c) the
stance sentence and the two answering bullets. The tool's `stance` field carries the same two words.

### 4. The rows the coach relabels (13 of 47)

The stance changes only a card that answers a position, so the list is the cards whose file was disclosed
on the side opposite their label's, and the two under an answer heading. The coach keeps a row's id, adds
`at:`, or changes the id; nothing else in the sample changes.

| Rows | Why listed |
|---|---|
| 5, 16, 20, 33, 59 | An affirmative position's label, in a negative file |
| 11, 21, 26, 31, 41, 57 | A negative position's label, in an affirmative file |
| 13 | A negative position's label, under an answer heading in a negative file |
| 25 | An affirmative position's label, under an answer heading in an affirmative file |

Rows 5 and 25 are the two the Sonnet recording answered with the pharmaceutical DA.

### 5. The relabelling sitting

A script, `scripts/relabel_coach_sample.py` (in the spec's `scripts`), shows each listed row's tag and
headings from the coach's own CSV, with its current label and its file's side, in the terminal only, and
takes the coach's label (Enter keeps it). It keeps a copy of the CSV beside it before writing, refuses a
label that is no active position, and prints nothing but row numbers and counts when it ends. The block
then runs `landscape evaluate --check-sample`. One block, in the shape of `v1-e32-t41`'s.

### Deviations this needs

* **`tests/smoke/test_landscape_evaluate_smoke.py`**, outside the spec's packages: its in-process recording
  answers through the stage's default prompt version, and 1.2.0's schema needs a stance in each answer (as
  `v1-e32-t43`'s smoke edit, accepted).

## The PM's ruling (2026-11-05)

1. The label format, as proposed.
2. The model's answer, as proposed: 1.2.0's stance overrides the answer-heading flag (the flag is still
   sent).
3. Scoring, as proposed: `wrong_stance` is its own outcome, counted and wrong; the computed 1.1.0 figures
   are recorded in docs/data.
4. Prompt 1.2.0 as proposed.
5. The sitting, with an addition: the 13 rows mixed with 6 control rows drawn at random from the other
   labelled rows (seed stated), all 19 in random order and unmarked; each row's tag, headings and
   disclosed side shown, nothing of the model's answers, the recordings or the score; Enter keeps; a copy
   first; only changed labels written; counts only at the end, changed and unchanged, listed and control.
   Then `--check-sample`.
6. The re-record on two routes, `high_volume` and `deep_audit`, in one block, priced from
   `config/model_pricing.yaml`.

The smoke deviation was accepted.

## Files changed

* **`prompts/`**: `landscape/classify_position@1.2.0.md` (released), and its entry in `prompts.lock.json`.
* **`debate_core.domain.landscape_classification`**: `Stance`, `ModelStancedPositionAnswer(s)`.
* **`debate_core.arguments.landscape.model_stage`**: `answer_schema` (stanced from 1.2.0) and `judge`
  taking the role from a stance.
* **`debate_core.arguments.landscape.evaluation_breakdown`**: `scored_stance`, `labelled_as`,
  `CardOutcome.WRONG_STANCE` (counted), the stances on `CardBreakdown` and `DeterministicPlacement`, and the
  pipeline, confusion table and second-label count reading them.
* **`debate_core.application.landscape_model_stage`**: default 1.2.0, the schema picked by version.
* **`debate_core.application.landscape_model_evaluation`**: `coach_label`, `row_labels` and the `at:`
  rules; `stance_counts` and `CoachSampleCheck.by_stance`; the file sides through `ask_labelled_cards`; the
  evaluation's counts taken from the cards' breakdowns; `sample_sides` for the sitting.
* **`debate_core.application.coach_sample_relabel`** (new): the sitting's rows, order, screens, write and
  counts.
* **`scripts/relabel_coach_sample.py`** (new): the sitting's terminal half.
* **`debate_cli.commands.landscape`**: `by_stance` in `--check-sample`; each card's stances in the breakdown's
  JSON and lines.
* **Tests** (`packages/debate_core/tests`, `packages/debate_cli/tests`): three new files on invented cards
  (`test_answering_stance.py`, `test_coach_sample_stance.py`, `test_coach_sample_relabel.py`), new CLI tests,
  and scripted routers in six files answering with a stance when asked in the stanced schema.
* **Outside the packages**: `tests/smoke/test_landscape_evaluate_smoke.py` and
  `tests/fixtures/caselist/synthetic_archive/` (Deviations).
* **Docs**: [the evaluation's data page](../data/landscape-model-evaluation.md) (the rulings and the
  computed 1.1.0 figures), [the record runbook](../runbooks/landscape-model-evaluation-record.md) (the two
  blocks), [the replay runbook](../runbooks/landscape-model-evaluation-replay.md) (which checkout replays
  1.1.0), [the taxonomy guide](../guides/landscape-taxonomy.md) (`at:` labels).

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

1. **`tests/smoke/test_landscape_evaluate_smoke.py`**, outside the spec's packages: its in-process
   recording answers with a stance, its version pin reads 1.2.0, and its `--check-sample` check writes one
   `AT:` label and reads `by_stance`. Accepted by the PM in the ruling.
2. **`tests/fixtures/caselist/synthetic_archive/`**, outside the spec's packages: the end-to-end suite's one
   landscape cassette is keyed by the stage's default version, so its recorder now answers in the schema of
   that version (`answer_schema`) with `"stance": "reads"`, and the cassette was written again offline by
   its own script (`uv run --frozen python -m tests.fixtures.caselist.synthetic_archive.record_landscape_cassette`;
   no model). The diff is the key, the version, the schema's path and the stance. Not in the proposal; the
   same kind of edit as the smoke file.
3. **The session's own offline replay** of both routes' 1.1.0 cassettes (29 seconds, read-only, no model),
   to find the relabel rows and compute the figures: a read-only command over files on the operator's Mac,
   which agreement 2 lets a session run.
4. **The affected set** (324 files) was not run: over two minutes, so it is the pull request's `ci`
   (agreement 10). The changed test directories and the always-run list ran instead.

## Decisions and assumptions

1. **A placement's sides** are the `Side` values of every disclosure of its file; PF's pro and con count as
   aff and neg, `UNKNOWN` as no side. A file disclosed on both sides reads, as the report counts a round on
   the position's side.
2. **`wrong_stance` comes right after `correct`** in the outcomes, so `breakdown.outcomes` and its display
   list it first among the wrong ones. A wrong position is judged by kind as before, whatever its stance.
3. **The evaluation's counts come from the cards' breakdowns** (`model_alone_score`). They were counted in a
   loop of their own, which would have ignored the stance. Values are unchanged for every existing test.
4. **Two hand-worked expectations moved with the rule** in `test_landscape_evaluation_breakdown.py`. Its
   source is a negative file, so an answer naming `medicare-aff` there is scored as answering. The row-4
   second label is now written `at:medicare-aff` (the test's point, a card right on its second label,
   stands), and the confusion table reads `at:medicare-aff`. `outcomes` names `wrong_stance` 0.
5. **Scripted routers answer `reads`** when asked in the stanced schema. `test_position_classification.py`'s
   router answers `answers` for a card sent under an answer heading, as 1.2.0 asks, so its role assertions
   keep their meaning.
6. **The sitting shows the coach's current label** (Enter keeps it), and reads a typed label in lower case,
   as every id is written. A restart over a kept copy that still matches the sample byte for byte goes on
   (a sitting stopped early wrote nothing); one that differs stops. Every other row of the CSV keeps its
   bytes; a changed row keeps its other cells' values and its line ending.
7. **Seed 20261105** for the controls and the order, stated in the block.
8. **A landscape run asks again** about every card it cached under 1.1.0, since results are cached by prompt
   version. The hold on live runs stands, so nothing changes until the PM lifts it.
9. **Prices** from `config/model_pricing.yaml` (Haiku 4.5 $0.001 and $0.005 per 1,000 input and output
   tokens; Sonnet 4.6 $0.003 and $0.015), at the 1.1.0 recordings' tokens plus 1.2.0's 980 more characters
   of instructions per call and a stance per answer. The guard's ceilings price the variables, which 1.2.0
   does not change.

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

Both blocks are also in [the record runbook's last section](../runbooks/landscape-model-evaluation-record.md#prompt-120-the-coachs-relabelling-sitting-then-both-routes-v1-e32-t46),
with what to read. Run them in order, from this task's worktree until it merges (a checkout of `dev`
after). Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances
```

**1. ac1: the coach's relabelling sitting, then the check.** Charlie sits at the terminal. The 13 rows (5,
11, 13, 16, 20, 21, 25, 26, 31, 33, 41, 57, 59) are mixed with 6 controls drawn by seed 20261105, all 19 in
one random order and unmarked. Each card shows its tag, its headings and the side its file was disclosed
on. Type a label (`at:<id>` for a card that answers the position) or press Enter to keep it. About half a
minute to read the store, then the sitting at the coach's pace, then a few seconds for the check:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run python scripts/relabel_coach_sample.py --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --rows 5,11,13,16,20,21,25,26,31,33,41,57,59 --seed 20261105; then echo "STOP: the sitting stopped; paste its last line only"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; fi
```

Paste back **the sitting's last line** (`Done. Listed: ... Control: ...`) **and the JSON**, nothing else:
the cards stay in the terminal. Success: exit 0, `labelled` 47, and `by_stance` counting the `at:` labels.

**2. ac3: the re-record on both routes, then both breakdowns** (4 to 6 minutes; about $0.06 on
`high_volume` and $0.19 on `deep_audit`). Run it after block 1:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Paste back **the five JSON objects**, nothing else. Each recording: `prompt_version` `1.2.0`; `labelled`,
`found` and `asked` 47; `calls` 3 or 4 (the second with `route` `deep_audit`). Exit 1 `EVALUATION_BELOW_BAR`
carries the counts in `error.details`. A stop before any answer recorded nothing on that route: paste it and
run nothing again before the PM reads it.

**Only if a `scan` count is above zero**: read the hits in the terminal, and **never paste or copy them**.
Give each hit's number and whether its words name a team, a school or a tournament, or an ordinary word:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown; uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## Follow-up work

* **Stage one's role under an answer heading inside its own side's block.** The matcher gives ANSWERS to
  every card under an answer heading. Row 13's kind, a negative card answering the affirmative's answers
  to its own DA, therefore counts as an answer, in the pipeline's score and in the report. 1.2.0's model
  decides that by its stance; stage one does not. E32, the PM's to file if the relabel keeps row 13
  reading.
* **Replaying an older prompt version after the merge.** A checkout runs one prompt version, so 1.1.0's
  recordings replay only from a pre-merge checkout (as 1.0.0's did after `v1-e32-t40`). A
  `--prompt-version` on `landscape evaluate` would let one checkout replay both. E32, only if the PM wants
  the side by side again.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

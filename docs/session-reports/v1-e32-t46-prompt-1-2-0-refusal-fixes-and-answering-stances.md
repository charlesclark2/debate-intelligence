# Session report: v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances

| | |
|---|---|
| Task | `v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances` — Prompt 1.2.0: the refusal fixes and the coach's answering stance |
| Spec | [`plan_specs/v1/e32-argument-landscape/t46-prompt-1-2-0-refusal-fixes-and-answering-stances.yaml`](../../plan_specs/v1/e32-argument-landscape/t46-prompt-1-2-0-refusal-fixes-and-answering-stances.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## The proposal (2026-11-04, for the PM's ruling; nothing built yet)

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

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

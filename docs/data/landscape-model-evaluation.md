<!-- docs-index: The landscape model stage's evaluations against the coach's labels, broken down: counts and taxonomy ids only -->
# The landscape model stage's evaluation, broken down

What `landscape evaluate` measured on hspolicy26, and why: `v1-e32-t07`'s first recorded evaluation,
and `v1-e32-t39`'s breakdown of it, replayed from the kept cassettes with no model call. Counts and
taxonomy ids only (the ids are committed). No card text, tag, heading, cite, label note or scan hit is
written here; the hits were read in the operator's terminal and are counted here by kind and field.

## The first recorded evaluation (2026-11-01)

The operator's `landscape evaluate --model-mode record`: hspolicy26 at snapshot 2026-10-20, taxonomy
`policy-2026-27-nhi` 1.4.0, prompt `landscape.classify_position` 1.0.0, the `high_volume` route.

| | Count |
|---|---|
| Labelled | 47 |
| Found in the store | 47 |
| Asked about, in calls | 47, in 4 |
| Refused `NO_POSITION` | 8 |
| Placed below the review threshold (0.6) | 1 |
| Counted (placed at or above the threshold) | 38 |
| Correct among the counted | 14: **36.8%**, against the 85% bar |
| Counted that the coach labelled none | 4 |
| Tokens, input and output | 30,460 and 3,881 |

The scan: 3 prompt-input texts, 3 naming a school, 0 a team code, 3 a tournament; 3 cassettes, 3
naming a school, 3 a team code, 3 a tournament. Exit 1, `EVALUATION_BELOW_BAR`. The PM ruled no live
model run until this is diagnosed, and kept the cassettes.

## The coach sample (counted 2026-11-01, no text read)

`v1-e32-t21`'s sample, read from the rows file and the labelled CSV's `position` column only:

* 60 cards sampled; the coach labelled **47** (40 with a position, 7 none) and marked 13 unsure. The
  PM's belief (60 sampled, 47 labelled) is confirmed.
* **Every sampled card was one stage one left unplaced.** t21 drew only from unplaced cards; none was
  placed below the threshold. A run sends the model both kinds, so the sample covers the larger part of
  the set the bar applies to, not all of it.
* The sample is stratified by the proxy model's confidence, and the strata are not drawn in proportion:

| Stratum | Unplaced cards in it | Sampled |
|---|---|---|
| at-or-above-threshold | 12,752 | 30 |
| just-below-threshold | 22,089 | 20 |
| far-below-threshold | 21,820 | 10 |
| All | 56,661 | 60 |

  Half the sample comes from the stratum holding 22.5% of the unplaced cards, so an accuracy over the
  sample, unweighted, is not an estimate over the cards. The breakdown gives each stratum's score and an
  accuracy weighted to the populations.

## The cassettes on the operator's Mac (read by structure, 2026-11-01)

Read by their JSON structure, their item counts and their recorded problem types, with no field's text
printed:

* 3 `landscape.classify_position` cassettes, each filed under hspolicy26, for batches of **20, 20 and
  7** cards (`DEFAULT_BATCH_SIZE` 20).
* One of them holds a refused answer: its recorded problem is `string_too_long` at
  `answers[0].rationale`. The schema caps a rationale at 280 characters (`RATIONALE_LIMIT`), and one
  answer's was longer, so the whole batch of 20 failed validation.
* 1 `model.repair` cassette, filed under hspolicy26, repairing `landscape.classify_position@1.0.0`. Its
  answer has 20 answers and was used: the evaluation counted no `BATCH_REFUSED`. So the guard
  **repaired** the batch, no card was lost to it, and the 4 calls are 3 batches and 1 repair.
* The repair cassette carries the failed call's rendered prompt: all 20 cards' inputs and the taxonomy.
  The evaluation's cassette scan reads the classify prompt's directory only, so it never read this one.

## The breakdown (the operator's replay, 2026-11-01)

`landscape evaluate --breakdown --snapshot 2026-10-20`, replayed from the kept cassettes
([the runbook](../runbooks/landscape-model-evaluation-replay.md)). No model was called. The replay
matched the recording: labelled 47, found 47, asked 47 in 4 calls, counted 38, correct 14, and the same
token counts and scan counts as above.

### Every labelled card's outcome

| Outcome | Cards |
|---|---|
| Correct | 14 |
| A wrong position of the label's kind | 9 |
| A position of another kind | 11 |
| Placed, though the coach labelled none | 4 |
| Refused `NO_POSITION` (6 labelled a position, 2 labelled none) | 8 |
| Below the review threshold (labelled none) | 1 |
| Lost to a batch that failed validation | 0 |
| Not asked, not found | 0, 0 |
| **All** | **47** |

### Beside the headings, and the set the bar applies to

* **The headings alone place none of the 47.** At taxonomy 1.4.0 every labelled card is still unplaced,
  so all 47 are in the set a real run sends to the model. The accuracy on that set is the evaluation's
  own: 14 of 38, **36.8%**.
* Weighted to the strata's populations, the accuracy is **37.9%**:

| Stratum | Unplaced cards in it | Labelled | Counted | Correct | Accuracy |
|---|---|---|---|---|---|
| at-or-above-threshold | 12,752 | 24 | 19 | 8 | 42.1% |
| just-below-threshold | 22,089 | 17 | 15 | 4 | 26.7% |
| far-below-threshold | 21,820 | 6 | 4 | 2 | 50.0% |

* **No review threshold reaches the bar.** The counted cards' confidences, by threshold:

| Threshold | Counted | Correct | Accuracy |
|---|---|---|---|
| 0.6 (today's) | 38 | 14 | 36.8% |
| 0.7 | 34 | 13 | 38.2% |
| 0.75 | 29 | 13 | 44.8% |
| 0.8 | 23 | 12 | 52.2% |
| 0.85 | 15 | 10 | 66.7% |
| 0.9 | 6 | 4 | 66.7% |

  The right answers' mean confidence is 0.836, and the wrong ones' 0.768.

### By the kind of the coach's label

| Kind | Labelled | Correct | Same kind, wrong | Other kind | Refused | Placed though none | Below |
|---|---|---|---|---|---|---|---|
| advantage | 14 | 5 | 4 | 2 | 3 | | |
| k | 10 | 5 | | 2 | 3 | | |
| t | 7 | 1 | 3 | 3 | | | |
| da | 5 | 2 | 2 | 1 | | | |
| cp | 4 | 1 | | 3 | | | |
| none | 7 | | | | 2 | 4 | 1 |

### The batches

| Batch | Cards | Calls | What the guard did | Correct of counted |
|---|---|---|---|---|
| 1 | 20 | 2 | repaired (`string_too_long` 1) | 7 of 15 |
| 2 | 20 | 1 | answered | 5 of 16 |
| 3 | 7 | 1 | answered | 2 of 7 |

The repaired batch scored no worse than the others.

### What the wrong answers have in common (taxonomy ids)

* **The 9 wrong positions of the label's kind are all neighbours on the same side**:
  `multipayer-t` answered `single-payer-t` (2) and `nhi-t` (1), `rates-da` answered `economy-da`,
  `midterms-da` answered `politics-da`, `growth-advantage` answered `stagnation-advantage`,
  `stagnation-advantage` answered `economy-advantage`, `data-advantage` answered `bioterror-advantage`,
  and `inequality-advantage` answered `costs-advantage`. None is another's parent. Of the 34 positions
  these cards were labelled or answered with, only `kritikal-aff` has a description in the taxonomy, so
  the prompt gives the model each position's id and label alone to tell neighbours apart.
* **10 of the 11 other-kind answers name a position of the other side** (the eleventh is
  `generic-theory`, which applies to both). Seven are negative cards answered with an affirmative:
  * `single-payer-t` answered `nhi-aff` (2);
  * `cap-k` answered `nhi-aff`;
  * `states-cp` answered `single-payer-aff`;
  * `midterms-da` answered `medicare-for-all-aff`;
  * `colonialism-k` answered `kritikal-aff`;
  * `advantage-cp` answered `inequality-advantage`.

  Two are the reverse: `pharma-advantage` answered `pharma-da`, and `costs-advantage` answered
  `public-option-cp`. The model names what a card is about, not the argument it is read in.
* **Topicality is the weakest kind**: 1 of 7 right. The other six were answered with another T (3), the
  affirmative the T is about (2), or `generic-theory` (1).
* **`generic-k` is refused**: all 3 cards labelled `generic-k` were answered `NO_POSITION`. The one card
  the model answered `generic-k` was labelled none, and fell below the threshold.
* **The none labels**: of 7, the model named no position for 2, placed 1 below the threshold, and placed
  4 at 0.65 to 0.75.

### The scan's hits, by kind and field

Counted by the breakdown. The hits themselves were read in the operator's terminal.

| Text | Hits | School | Team-code word | Tournament list |
|---|---|---|---|---|
| Prompt inputs (3 batches) | 57 | across fields 47 | | heading path 9, tag 1 |
| Cassettes (3) | 408 | across fields 7, model rationale 30 | taxonomy positions 9, model rationale 3, cassette metadata 1 | taxonomy positions 309, model rationale 33, heading path 9, cassette metadata 6, tag 1 |
| Repair cassettes (1) | 182 | repaired prompt 25, model rationale 7 | repaired prompt 4 | repaired prompt 137, model rationale 7, cassette metadata 2 |

* In the prompt inputs, 1 hit is a taxonomy word.
* In the cassettes, 332 hits are taxonomy words and 43 tournament-list hits are a team's name.
* In the repair cassette, 112 hits are taxonomy words and 36 tournament-list hits are a team's name.

### What the hits are (the breakdown's marks)

A second JSON-only run (2026-11-01) counted each hit's marks: whether its words are a JSON key of the
text, words of the committed taxonomy, or words of the cards that text sent.

| Field | Hits | A JSON key | A taxonomy word | Neither: names in the cards sent |
|---|---|---|---|---|
| Prompt inputs, across fields (school) | 47 | 47 | 0 | |
| Prompt inputs, heading path (tournament list) | 9 | 0 | 0 | **9** |
| Prompt inputs, tag | 1 | 0 | 1 | |
| Cassettes, across fields | 7 | 7 | 0 | |
| Cassettes, model rationale | 66 | 60 | 6 | |
| Cassettes, taxonomy positions | 318 | 0 | 318 | |
| Cassettes, cassette metadata | 7 | 0 | 7 | |
| Cassettes, heading path and tag | 10 | 0 | 1 | **9** (the same as the inputs') |
| Repair cassette, repaired prompt | 166 | 50 | 110 | **6** (the repaired batch's, again) |
| Repair cassette, model rationale | 14 | 14 | 0 | |
| Repair cassette, cassette metadata | 2 | 0 | 2 | |
| **All** | **647** | **178** | **445** | **24** |

* **The school in every text is a JSON key.** One school on the caselist's list spells the same as a key
  of the prompt input's JSON, so the scan finds it once per card (47 in the inputs) and in every cassette.
  It is the same word, not a card's. The model's rationales use it too (60 of their 66 hits); their other
  6 are taxonomy words, and no rationale hit repeats a name the cards sent.
* **The team-code word in every cassette is taxonomy vocabulary.** All 13 team-code hits in the cassettes
  are words of the committed taxonomy: everyday words that are also words of a team's code.
* **The real names are in the heading paths, 9 of them.** They are on the scan's third list (disclosing
  teams' schools, codes and tournaments) and are neither a key nor a taxonomy word. The session read them,
  when the terminal listing reached it, as tournament and team names that headings carry. The scrub
  takes the disclosing team's own names and the caselist's schools out of a heading, not other teams'
  tournaments or codes.
* **The repair cassette holds the repaired batch again.** All 182 of its hits repeat its repaired prompt,
  6 of them the heading names. The evaluation's scan does not read it.


## Before the re-record: what `v1-e32-t40` changed (2026-11-01)

From the PM's rulings on `v1-e32-t39`'s six options. No count here yet: the re-record waits on the
coach's approval of the descriptions ([the record runbook](../runbooks/landscape-model-evaluation-record.md)).

* **Descriptions.** Every active position the Policy prompt sends now has a one-line description:
  102 drafted (81 of `policy-2026-27-nhi`'s, 21 of `generic.yaml`'s Policy positions), beside
  `kritikal-aff`'s, written in `v1-e32-t17`. Taxonomy `policy-2026-27-nhi` 1.4.1 and `generic` 1.1.1; no
  alias, id, kind or side changed, so no count moves. They are drafts until the coach approves or
  corrects them.
* **Prompt `landscape.classify_position` 1.1.0.** It asks for the argument a card is read as in a round,
  not the subject it is about, explains each position's side and description, sends a card of a kind no
  named position fits to that kind's generic position where the list has one, and states the
  280-character rationale limit. Batches stay at 20 cards.
* **The scrub.** The scan's whole third list, every disclosing team's school, team code and tournament
  in the reading, comes out of each card's heading path, tag, short cite and excerpt before it is sent.
  It is what put the 9 heading-path names above into the prompt inputs.
* **The scan.** It reads field values, never a JSON key (the 178 key hits above), leaves out the
  committed positions text (the taxonomy-word hits above), holds only the disclosing teams'
  tournaments on its third list, reads the repair cassettes of the prompt version filed under the
  caselist, and reads only the cassettes of the prompt version the evaluation ran. The scan counts in
  the sections above were taken by the earlier rules.
* **Unchanged:** the coach's labels, the 85% bar, the set it applies to, the review threshold of 0.6,
  and the 47 cards.

## The coach's review applied (`v1-e32-t41`, 2026-11-02)

The coach approved `v1-e32-t40`'s descriptions with nine corrections and answered its 13 disputed rows.
Taxonomy `policy-2026-27-nhi` 1.5.0 and `generic` 1.1.2 carry both; the re-record measures against them.

* **Nine descriptions corrected**, in the coach's words: `pharma-da`, `taxes-da`, `ai-da` (now a
  politics-style DA on AI regulation), `democracy-da`, `advantage-cp` and `trump-k` in the topic's file,
  `antiblackness-k`, `psychoanalysis-k` and `aspec` in `generic.yaml`.
* **Three positions added** for the rows no position fitted: `health-profiteering-advantage` (aff
  advantage), `free-market-cp` and `federalism-cp` (neg CPs; the coach ruled `federalism-cp` a different
  mechanism from `states-cp`). Their aliases are headings two or more teams use, counted first on the
  dev store (hspolicy26 2026.10.27-docx-7 through 2026-10-20: 3,825 sources, 126,681 cards), by placing
  every item under 1.4.1 and under 1.5.0:

| Position | Aliases | Cards it places | Of those, unplaced today | Under another position today |
|---|---|---|---|---|
| `health-profiteering-advantage` | 8 | 1,106 | 934 | 172: `single-payer-aff` 129, `medicare-for-all-aff` 34, `global-budgets-aff` 8, `reproductive-health-aff` 1 |
| `free-market-cp` | 4 | 114 | 112 | 2: `voucher-aff` 1, `value-based-reimbursement-aff` 1 |
| `federalism-cp` | 2 | 62 | 58 | 4: `ucf-cp` 3, `states-cp` 1 |

  The cards moving from an affirmative sit under an advantage heading inside that aff's file, nearer
  the card than the aff's own heading, which is how every other advantage is placed. No card moves
  from `cap-k`, `costs-advantage` or any DA. The one `states-cp` card sits directly under a heading
  that is this alias, in one team's file. Headings counted beside these and left out are named by kind
  in the task's session report.
* **A second label.** The sample takes an optional `also` column: a second position the coach accepts.
  An answer naming either label is scored correct; the breakdown counts those right on the second label,
  and its confusion table and kinds stay on the first. A sample without the column scores as before.
* **The relabel** is the coach's, in the coach's own CSV (the session report's operator follow-ups): rows 11,
  30, 31 and 59 to the new positions, rows 32, 38 and 47 to the model's answers, rows 34 and 58 with
  the model's answer as a second label. Its counts by label kind are recorded here when the PM has them.

## The relabelled sample and the re-record under 1.1.0 (2026-11-02)

Recorded by the PM from the operator's JSON. Counts, ids and row numbers only.

* **The relabel** (`landscape evaluate --check-sample`, taxonomy 1.5.0): labelled 47; by the coach's
  label kind advantage 16, cp 6, da 5, k 10, none 3, t 7; two rows with a second label, both
  advantages. The coach kept `multipayer-t` on rows 32 and 38.
* **The re-record** (prompt 1.1.0, taxonomy 1.5.0, dev's `high_volume` route): asked 47 in 3 calls,
  38,881 input and 3,882 output tokens.

| | 1.0.0 (2026-11-01) | 1.1.0 (2026-11-02) |
|---|---|---|
| Counted | 38 | 32 |
| Correct | 14 | 19 |
| Accuracy (bar 0.85) | 0.368 | 0.594 |
| Refused `NO_POSITION` | 8 | 12 (10 labelled with a position, 2 labelled none) |
| Below the threshold | | 3 |
| Placed though labelled none | | 1 |
| Prompt-input scan | hits | clean (3 texts, 0 hits) |

* **Outcomes:** correct 19, wrong position of the same kind 6, wrong kind 6, placed though labelled
  none 1, refused 12, below threshold 3 (47).
* **By the label's kind:** advantage 7 correct, 3 same-kind wrong, 2 wrong kind, 4 refused; cp 1, 0, 2,
  2, and 1 below threshold; da 2 correct, 2 refused, 1 below threshold; k 4, 2, 1, 2, and 1 below
  threshold; t 5, 1, 1; none: 1 placed, 2 refused.
* **The refusals of labelled cards:** midterms-da 2, generic-k 2, and one each of inequality-advantage,
  data-advantage, pharma-advantage, coverage-advantage, states-cp and advantage-cp.
* **Second labels:** 2 cards, 0 correct on the second label (row 34 was correct on its first).
* **The model's set** (the 43 cards the deterministic stage sent): counted 29, correct 17, 0.586.
  The deterministic stage placed 4 (rows 11, 30, 31, 59), each naming the coach's label; the model
  answered two of them otherwise. The PM's estimate of the pipeline's score (deterministic first, the
  model for the rest): 21 of 33, about 0.64. Weighted by stratum: 0.491.
* **The cassette scan:** 27 hits across the 3 cassettes, all marked: 22 a JSON key's name and 5
  taxonomy words; none named a team and none was copied from a card. The operator read them in the
  terminal and judged all 27 ordinary words, so the 1.1.0 cassettes are kept.
* **What follows:** the hold on live model runs stands. `v1-e32-t43` reports the pipeline's score,
  explains the refusals and measures a second route; `v1-e32-t44` keeps a marked hit from making a
  text unclean.

## Scored as students meet it, and the refusals (`v1-e32-t43`, 2026-11-02)

The evaluation now scores the labelled cards two ways. **The pipeline**, as students meet them: a card
the headings place surely (a run never sends it) is scored on that placement, a card a coach's override
decides argues no position is not counted, and every other card on the model's answer. **The model
alone**: the model's answer for every card, the evaluation's score until now. The PM ruled that the bar
reads the pipeline's accuracy over its counted cards; the model-alone score and the weighted accuracy
stay reported. Coverage is the counted over the labelled.

The session's replay of the 1.1.0 cassettes (`landscape evaluate --breakdown --json`, snapshot
2026-10-20, taxonomy 1.5.0, 113 seconds, no model called):

| | Model alone | Pipeline |
|---|---|---|
| Labelled | 47 | 47 |
| Counted | 32 | 33 (4 by the headings, 29 by the model) |
| Correct | 19 | 21 |
| Accuracy (bar 0.85) | 0.594 | **0.636** |
| Refused `NO_POSITION` | 12 | 12 |
| Below the threshold | 3 | 2 |
| Coverage | 32 of 47, 0.681 | 33 of 47, 0.702 |

* The PM's estimate, 21 of 33, is the replay's figure. The headings place rows 11, 30, 31 and 59, each
  naming the coach's label; the model answered row 31 with a position of another kind and row 11 below
  the threshold, so the pipeline counts both rows right, and row 11 leaves the below-threshold count. No override decides a labelled card. The weighted accuracy stays 0.491 and the model's set 17
  of 29.
* Every refusal is of a card the headings leave unplaced, so the pipeline refuses the same 12.

### What the 10 refused cards labelled with a position had in front of the model

Counted through the evaluation's own scrubbed path; no tag, heading or label text is written here.

| | Refused, labelled a position (10) | Answered, labelled a position (34) |
|---|---|---|
| No heading sent | 6 (5 under no heading in their file; 1 whose only heading the scrub emptied) | 8 |
| A heading with a word of the label's position | 3 | 10 |
| A word of the label's position in the headings or the tag | 3 | 22 |
| A speech or structure heading (1NC, links, impacts) | 0 | 6 |
| Under an answer heading | 1 | 1 |
| Tag words, mean | 10.5 (all 10 have a tag) | 14.3 |
| A cite sent | 6 | 22 |
| Evidence under 300 words / 300 or more | 4 / 6 | 6 / 28 |
| In a file read by the label's side | 8 | 25 |
| Stage one: unplaced, sent | 10 | 30 |

* **Headings decide most of it.** Of the 14 cards labelled a position that reached the model with no
  heading, 6 were refused; of the 30 with one, 4.
* **By batch and stratum**: batches 1 and 2 hold 5 each and batch 3 (7 cards) none; 6 are from the
  at-or-above-threshold stratum, 2 just below, 2 far below. By the label's kind: advantage 4, da 2, cp 2,
  k 2.
* **The recorded answers**: each is `position_id` null, which the stage records as `NO_POSITION`. The
  model's own confidence on them is 0.15 to 0.3 in batch 1 and 0.5 to 0.7 in batch 2 (one model, one
  prompt). 6 of the 10 rationales call the card general or generic, and both cards labelled `generic-k`
  have a rationale naming a kritik or philosophy, though the prompt sends a card of a kind no named
  position fits to that kind's generic position.
* **What the cards are**, read by kind of claim: 3 state an impact or framing claim and name no
  position, 2 a link or internal link of an election story that names a party and no position, 2 a
  kritik's claim, 2 a counterplan's solvency, and 1 is a numbered answer in a frontline. Prompt 1.1.0 asks for null for a general card, "framing, an impact with no story,
  a claim about the round", when the model cannot tell which position it serves.
* **What would answer them**, and the proposal, are in the session report. Answering all 10 rightly would
  make the pipeline 31 of 43 (0.721): the refusals cost coverage, and the 12 wrong answers among the
  pipeline's counted cards are what keep it under the bar (6 a neighbour of the same kind, 5 another kind,
  1 placed though labelled none; 4 of the 5 other-kind answers are of cards in a file read by the side
  opposite the label's).

## A second route: Claude Sonnet 4.6 on `deep_audit` (`v1-e32-t43` ac3, 2026-11-03)

The operator's recording of the same 47 cards on dev's `deep_audit` route, with `landscape evaluate
--route deep_audit` (snapshot 2026-10-20, taxonomy 1.5.0, prompt 1.1.0), beside the 1.1.0 recording
on `high_volume`. Its cassettes are under `model-cassettes-deep_audit/`; the default directory was not
touched.

| | Claude Haiku 4.5 (`high_volume`) | Claude Sonnet 4.6 (`deep_audit`) |
|---|---|---|
| Pipeline, correct of counted (bar 0.85) | 21 of 33, 0.636 | **27 of 36, 0.750** |
| Model alone, correct of counted | 19 of 32, 0.594 | 27 of 36, 0.750 |
| Refused `NO_POSITION` | 12 | 0 |
| Below the threshold | 2 | 11 (1 of them names the coach's label) |
| Coverage, counted of labelled | 0.702 | 0.766 |
| Calls / cost of the 47 cards | 3 / $0.058 | 3 / $0.182 |

* **Sonnet answers every card.** The threshold then does its work: of the 11 answers below it, 10 are
  wrong and 1 names the label.
* **The 9 wrong answers among the 36 counted** are mostly a neighbouring advantage, and twice the
  pharmaceutical advantage read as the pharmaceutical DA: a card that answers a position read as the
  position, the case the coach's `at:` stance label is meant to separate (`v1-e32-t46`).
* **The scans.** The prompt-input scan was clean. The cassette scan found 42 hits, all marked by the
  breakdown (38 a JSON key's name in a rationale, 4 taxonomy words); none was copied from a card and none
  names a team. The operator read them in the terminal on 2026-11-03 and judged all 42 ordinary words, so
  the cassettes are kept.
* The bar still reads the pipeline, and neither route meets it. The hold on live runs stands.

## Prompt 1.2.0 and the answering stance (`v1-e32-t46`, ruled 2026-11-05)

The PM's rulings on `v1-e32-t46`'s proposal, built in that task. Counts, ids and row numbers only.

* **The coach's label carries a stance.** A plain id says the card reads the position; `at:<id>` (read
  without case) says it answers it. `at:none` and a bare `at:` are refused by row; the `also` column takes
  the same forms, and may name the same id with the other stance. `--check-sample` counts `by_stance`.
* **The model's answer carries one too.** Prompt `landscape.classify_position` 1.2.0 answers in
  `ModelStancedPositionAnswers`, each answer with a required `stance`, `reads` or `answers`, which sets the
  result's role (the answer-heading flag is still sent, and no longer decides it). 1.0.0 and 1.1.0 keep
  `ModelPositionAnswers`; the cassette key covers the version and the schema's path, so their recordings
  are neither replaced nor served to 1.2.0. 1.2.0 also carries the refusal fixes: (a) a kritik's or
  counterplan's card goes to its named or generic position, never null; (b) a general card under a heading
  naming a word of a position serves that position, and null stays for a general card under no such
  heading.
* **How a stance is scored.** A placement answers when its role is ANSWERS, or when every readable side
  its file was disclosed on is opposite the position's side, the report's own rule; it reads otherwise.
  The label's position (or the second label's) with the other stance is a new outcome, `wrong_stance`,
  which the bar counts as counted and wrong, for the model alone and the pipeline alike. The scores' JSON
  keeps its keys; `breakdown.outcomes` and each card's breakdown gain the stance.
* **The rows the coach relabels**: 5, 11, 16, 20, 21, 26, 31, 33, 41, 57 and 59 (a file disclosed on the
  side opposite the label's) and 13 and 25 (under an answer heading), mixed in the sitting with 6 control
  rows drawn from the other labelled rows by the seed 20261105, all in one order and unmarked.

### The kept 1.1.0 recordings, scored with the stance (computed 2026-11-04)

The session's replay of both routes' 1.1.0 cassettes (29 seconds, no model called), each labelled row's
file side read from the store, and the stance rule applied to the recorded answers (a 1.1.0 answer has no
stance: its role is the headings'). The replay reproduces the recorded model-alone scores, 19 of 32 and
27 of 36.

| Labels | Claude Haiku 4.5 (`high_volume`), pipeline | Claude Sonnet 4.6 (`deep_audit`), pipeline |
|---|---|---|
| Scored by position only (as recorded) | 21 of 33, 0.636 | 27 of 36, 0.750 |
| The stance rule, no relabel | 17 of 33, 0.515 | 22 of 36, 0.611 |
| The stance rule, the 11 opposite-side rows relabelled `at:` | 21 of 33, 0.636 | 26 of 36, 0.722 |
| The same, and row 13 `at:` too | 21 of 33, 0.636 | 27 of 36, 0.750 |

* With no relabel, Haiku's 4 lost cards are rows 11, 31 and 59 (placed by the headings) and 57 (the
  model): each names the label's position in a file disclosed only on the other side. Sonnet loses the
  same 4 and row 13, an answer heading's card it named rightly, whose 1.1.0 role is the heading's.
* The 1.2.0 re-record, on both routes, and the coach's relabel are recorded here by the PM when the
  operator has them.

## Marked hits leave a text clean (`v1-e32-t44`, 2026-11-05)

The PM's rulings of 2026-11-05. The scan's lists, its counts and the terminal listing are unchanged; only
`clean`, and the bar that reads it, changed.

* **The marks the rule trusts** are two, named in one place in the code,
  `MARKS_THAT_SET_A_HIT_ASIDE` in `debate_core.arguments.landscape.scan_hits`: **a JSON key's name**
  (`json_key`: every matched word is a word of a key of the text) and **a taxonomy word** (`in_taxonomy`:
  the matched words are words of the committed taxonomy). A mark added to a hit later sets nothing aside
  until a PM-reviewed change adds it there and here.
* **What keeps a hit counting**, whatever else it carries: **a team's name** (`team_name`) and **words the
  text's cards sent** (`in_input`, copied from a card). A hit with no mark counts too.
* **Text by text.** A text the scan names is set aside when each kind it counts in that text has a listed
  hit and every hit is set aside; otherwise the text is left, and the scan is unclean. A text with one
  unmarked hit beside marked ones is left. A count no listed hit answers for leaves the text.
* **The prompt inputs are never set aside**: every hit there is in the cards they send.
* **The record of what was excused.** Each `scan` entry of `landscape evaluate --json` carries `set_aside`:
  the texts set aside, their hits, and those hits by mark (a hit may carry both). Its counts of schools, team
  codes and tournaments, `breakdown.scan_hits` and the terminal listing count every hit as before.

### The kept 1.1.0 recordings' scans, judged by the rule (computed 2026-11-04)

The session's replay of both routes' 1.1.0 cassettes through the evaluation's own path at prompt 1.1.0
(`break_down`, replay mode, 62 seconds for both, nothing written, no model called). Counts only.

| Text | Claude Haiku 4.5 (`high_volume`) | Claude Sonnet 4.6 (`deep_audit`) |
|---|---|---|
| Prompt inputs: texts, hits | 3, 0 | 3, 0 |
| Cassettes: texts naming a school / team code / tournament | 3 / 1 / 2 | 3 / 2 / 1 |
| Cassettes: hits; a JSON key, a taxonomy word | 27; 22, 5 | 42; 38, 4 |
| Cassettes: hits a team's name, hits in the cards sent | 0, 0 | 0, 0 |
| Cassettes set aside, of 3 | 3 (27 hits) | 3 (42 hits) |
| Repair cassettes | 0 | 0 |
| `clean`, every scan | **true** | **true** |

* The hits and their marks are the recordings' as the PM recorded them above (27: 22 and 5; 42: 38 and 4).
* Both recordings would now pass the scan; neither meets the bar, which this task did not change.

## The sitting and the re-record under 1.2.0 (`v1-e32-t46`, 2026-11-05)

Recorded by the PM from the operator's output. Counts, ids and row numbers only.

* **The coach's sitting** (2026-11-04): the 13 listed rows and 6 controls, unmarked and in one order.
  Listed: 9 changed, 4 kept (rows 13, 16, 33 and 57). Controls: 1 changed (row 40), 5 kept. The rows now
  labelled `at:` are 5, 11, 20, 21, 25, 26, 31, 40, 41 and 59.
* **The sample** (`--check-sample`, taxonomy 1.5.0): labelled 47; by the label's kind advantage 15, cp 7,
  da 6, k 10, none 2, t 7; by stance answers 10, reads 35; two rows with a second label, both advantages.
* **The re-record** (prompt 1.2.0, both routes, 2026-11-05): 47 found and asked in 3 calls on each route;
  40,237 input and 4,282 output tokens on `high_volume`, 40,240 and 4,847 on `deep_audit`.

| | Claude Haiku 4.5 (`high_volume`) | Claude Sonnet 4.6 (`deep_audit`) |
|---|---|---|
| Pipeline under 1.1.0, by position only (2026-11-02/03) | 21 of 33, 0.636 | 27 of 36, 0.750 |
| **Pipeline under 1.2.0, with the stance (bar 0.85)** | **21 of 37, 0.568** | **23 of 33, 0.697** |
| The model alone under 1.2.0 | 20 of 37, 0.541 | 23 of 33, 0.697 |
| The same pipeline, a wrong stance counted right | 24 of 37, 0.649 | 27 of 33, 0.818 |
| Refused `NO_POSITION` | 6 (5 labelled with a position, 1 none) | 0 |
| Below the threshold | 4 | 14 (2 of them name the label: rows 25 and 45) |
| Placed though labelled none | 0 | 1 (row 15) |
| Coverage, counted of labelled | 0.787 | 0.702 |
| Weighted by stratum | 0.445 | 0.675 |

* **Outcomes.** Haiku: correct 20, wrong stance 3, wrong position of the same kind 6, wrong kind 8,
  refused 6, below the threshold 4. Sonnet: correct 23, wrong stance 4, same kind 1, wrong kind 4, placed
  though labelled none 1, below the threshold 14. The headings placed 4 cards, each naming the label.
* **Where Sonnet is wrong.** A wrong stance on rows 7, 13, 17 and 57 (each answered as answering a
  position the coach labelled as read; Haiku the same on 17 and 57, and on 39). The wrong kind on row 5
  (`at:pharma-advantage` answered as reading `pharma-da`, both routes), rows 21 and 40 (`at:delay-cp`
  answered as `at:should-t`, both routes) and row 26 (`at:cap-k` answered as reading `nhi-aff`). Row 47 a
  neighbouring advantage. `generic-k` (rows 46, 50 and 60) is counted right on neither route.
* **The scans.** The prompt-input scans were clean. The cassette scans found 23 hits on `high_volume` (19 a
  JSON key's name, 4 taxonomy words) and 44 on `deep_audit` (37 and 7); none named a team and none was in
  the cards sent. The operator read them in the terminal on 2026-11-05 and judged all 67 ordinary words, so
  the 1.2.0 cassettes are kept. Under `v1-e32-t44`'s rule, merged after this recording, both scans read
  clean.
* **The coach's rulings** (2026-11-05). A card that answers an advantage is not the matching DA
  (pharmaceutical, innovation, growth against economy), so the taxonomy declares no mirror pairs and rows 5,
  28 and 34 stay wrong when so answered. Rows 21 and 40 take no `should-t` second label.
* **How far the sample reaches.** Sonnet counts 33 cards, so one card moves the score about three points,
  and the 95% interval on 23 of 33 runs from about 0.53 to 0.83.
* **What follows:** neither route meets the bar, and the hold on live model runs stands. `v1-e32-t49`
  carries prompt 1.3.0 and stage one's own-side rule, tuned on `deep_audit`; `v1-e32-t50` draws a second
  labelled sample, held out from tuning, before any route is read as meeting the bar.

## Prompt 1.3.0 and the own-side rule (`v1-e32-t49`, ruled 2026-11-05)

The PM's rulings on `v1-e32-t49`'s proposal, built in that task. Counts, ids and row numbers only.

* **The own-side rule.** A placement in a file disclosed only on its position's own side reads that
  position, whatever its answer heading or the model's stance says. It is a card defending its own side's
  position against the other side's answers. The rule applies to stage one's placements and the model's
  answers alike, card by card, as the landscape run returns them. The evaluation scores a stance by the same
  function. It mirrors `v1-e32-t46`'s rule, under which a placement in a file disclosed only on the other
  side answers it. A file disclosed on both sides or on no readable side, and a position either side reads,
  keep the role they have. Stage one's cache keeps the role it gave, since cards read alike in files on
  different sides share a cache key.
* **Prompt 1.3.0**, the stage's default: the own side's answers, the coach's rulings of 2026-11-05 and
  `generic-k`. In detail:
  * an advantage and a disadvantage about the same subject are different positions;
  * an answer is never the answering side's own case, in either direction;
  * a definition the affirmative reads against a counterplan answers that counterplan;
  * a named kritik is chosen only by its theory, and a kritik's framework card is never topicality;
  * a generic position may carry 0.9 or more when the card is plainly its kind's.

  The variables, user turn and stanced schema are 1.2.0's, so 1.2.0's recordings keep their keys.
* **The PM's condition on the generic-confidence clause.** `--breakdown` counts the answers naming a
  generic position on their own (`breakdown.generic_answers`): how many, how many above the threshold,
  how many of those are right and wrong, and the rows labelled with a named kritik that were answered
  generic. If the generic answers above the threshold are wrong more often than right, the clause comes out
  in a 1.3.1 follow-up. Rows 12 and 55 (`cap-k`, right under 1.2.0) are the ones to watch.
* **Rows 16, 33 and 57** are labelled as read, in files disclosed only on the other side, so the side rule
  scores any answer there as answering. They go to the coach alongside `v1-e32-t50`. Per row, the coach
  chooses an `at:` label, a second label, or "the side rule is wrong here". The PM files a follow-up on the
  last.

### The kept 1.2.0 recordings under the own-side rule (computed 2026-11-05)

These are the session's replays of both routes' 1.2.0 cassettes through the evaluation's own path, at
prompt 1.2.0, with no model called (about a minute per route). The answers are identical on all 47 rows;
only the scoring changes.

| | Claude Haiku 4.5 (`high_volume`) | Claude Sonnet 4.6 (`deep_audit`) |
|---|---|---|
| Pipeline as recorded (bar 0.85) | 21 of 37, 0.568 | 23 of 33, 0.697 |
| The rule on stage one's placements only | 21 of 37, 0.568 | 23 of 33, 0.697 |
| **The rule on stage one's and the model's (built)** | **23 of 37, 0.622** | **26 of 33, 0.788** |

* The rows it turns right: Sonnet 7, 13 and 17; Haiku 17 and 39. Each was a wrong stance, and none is
  turned wrong.
* Of the wrong-stance rows, only row 13 sits under an answer heading. Rows 7, 17 and 39 sit under none, in
  files on their position's own side.
* Of the 45 rows labelled with a position, 32 read in files on their own side and all 10 `at:` rows sit in
  files on the other side. The other 3 are rows 16, 33 and 57, above.

### The own-side rule in a landscape run (counted 2026-11-05)

Stage one over the 126,681 cards of hspolicy26's 2026-10-20 snapshot. The PM accepted this as a product
change: these are a side's cards defending its own position against answers, which the report had been
dropping.

* **181 sure placements** (19 more below the threshold) change role from ANSWERS to READS. By kind: da 112,
  advantage 57, k 7, theory 4, t 1. On 146 of them the placing heading is itself the answer heading; on
  35 the answer heading is above it.
* They touch **20 positions in 61 files**: 75 position-and-file pairs. In 12 of those pairs the position
  already reads in that file through another card, so **63 pairs** add the position to that file's rounds.
* For scale: 62,535 sure placements already read. The 1,908 sure ANSWERS placements in files on the other
  side, and the 14 in files on both sides, keep their role.
* The model's answers in a run take the same rule; this count is stage one's alone.

The re-record of the 47 under 1.3.0, on `deep_audit` only as ruled, is recorded here by the PM when the
operator has it ([the record runbook](../runbooks/landscape-model-evaluation-record.md#prompt-130-the-re-record-on-deep_audit-v1-e32-t49)).

## The re-record under 1.3.0 (`v1-e32-t49` ac3, 2026-11-05)

Recorded by the PM from the operator's JSON. Counts, ids and row numbers only. `deep_audit` only, as ruled.

| Prompt, scored with the own-side rule | Pipeline (bar 0.85) | Below the threshold | Coverage |
|---|---|---|---|
| 1.2.0 (the session's replay of the kept cassettes) | 26 of 33, 0.788 | 14 | 0.702 |
| **1.3.0 (this re-record)** | **24 of 32, 0.750** | 15 | 0.681 |

* **The recording:** Claude Sonnet 4.6, 47 found and asked in 3 calls with no repair, 41,332 input and
  4,737 output tokens. Weighted by stratum 0.655. The 95% interval on 24 of 32 runs from about 0.58 to
  0.87, so the two prompts are not told apart on this sample.
* **What changed, row by row:** row 47 turned right and row 15 is no longer counted wrong; rows 9 and 53
  were right and fell below the threshold; row 58 was right and is now wrong; rows 41 and 45 went from
  below the threshold to wrong answers. The rows the coach's rulings aim at (5, 21, 40, 34) did not turn;
  row 26 moved from the affirmative's own case to `at:generic-k`.
* **The generic condition** (`breakdown.generic_answers`): 4 answers name a generic position, 1 above the
  threshold (row 26), right 0, wrong 1. By the PM's ruling the generic-confidence sentence comes out:
  `v1-e32-t55`, prompt 1.3.1. Rows 12 and 55 stayed right as `cap-k`.
* **The scans:** prompt inputs clean; cassettes 46 hits (41 a JSON key's name, 5 taxonomy words), none a
  team's name and none in the cards sent, all 3 texts set aside; the operator judged every hit an ordinary
  word in the terminal.
* **What follows:** the bar is not met and the hold on live model runs stands. `v1-e32-t50`'s held-out
  sample is measured on 1.3.1, chosen now and not on the held-out sample.


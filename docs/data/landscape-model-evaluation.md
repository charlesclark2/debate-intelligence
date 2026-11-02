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

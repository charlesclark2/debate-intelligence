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

## The breakdown (the operator's replay)

Pending: `landscape evaluate --breakdown`, replayed from these cassettes
([the runbook](../runbooks/landscape-model-evaluation-replay.md)). The counts go here when the operator
sends them.

# Session report: v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings

| | |
|---|---|
| Task | `v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings` — Prompt 1.3.0 and stage one: a card defending its own side's position reads it, and an answer is never the position it answers |
| Spec | [`plan_specs/v1/e32-argument-landscape/t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings.yaml`](../../plan_specs/v1/e32-argument-landscape/t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings` |
| Session status | IN PROGRESS: the proposal waits on the PM's ruling (ac1); no code yet <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The proposal below is for the PM's ruling before any code (ac1). It was counted by replaying the kept 1.2.0
cassettes of both routes offline (no model called); the replay reproduces the recorded 23 of 33 and 21 of
37. The PM should look first at two findings. **The own-side rule decides the stance far more than
answer headings do:** of the wrong-stance rows, only row 13 sits under an answer heading; rows 7, 17 and 39
sit under none, in files on their own position's side. Applied to every placement, stage one's and the
model's, the rule takes Sonnet from 23 to 26 of 33 (0.788) and Haiku from 21 to 23 of 37 (0.622). Applied to
stage one alone it changes nothing on the 47. **Three rows can never be scored right:** rows 16, 33 and 57
are labelled as read, in files disclosed only on the other side, and t46's side rule scores any answer
there as answering.

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

## The proposal (2026-11-05, for the PM's ruling, kept as written)

**How it was counted.** Two scratch scripts, not committed, ran on the operator's Mac from this worktree.
Both are read-only, call no model and write nothing. The first replays the kept 1.2.0 cassettes of each
route through the evaluation's own path (`LandscapeModelEvaluationService.break_down`, replay mode, about
59 seconds per route). For each labelled row it prints the label, the outcome, the answer's id and scored
stance, the confidence, the sides its file was disclosed on, one flag per heading (answer heading or not)
and stage one's placement. It then rescores the cards with the own-side rule. The second runs stage one
over every card of the 2026-10-20 snapshot (about 31 seconds) and counts placements by role and file side.
No tag, heading, cite or card text was printed. Both replays reproduce the recorded scores: Sonnet 4.6 23 of
33, Haiku 4.5 21 of 37.

### (a) The own side's answer heading

**The count.** These are the wrong-stance rows on each route, by row number and heading kind only. "Own
side" means the file was disclosed only on the side of the position the label names.

| Row | Wrong stance on | Label kind (position's side) | File disclosed on | Headings over the card | Answer heading | Stage one |
|---|---|---|---|---|---|---|
| 7 | Sonnet | t (neg) | neg only: own side | 2 | none | places nothing |
| 13 | Sonnet (Haiku: wrong kind) | da (neg) | neg only: own side | 2 | the inner one | places nothing |
| 17 | both routes | da (neg) | neg only: own side | 1 | none | places nothing |
| 39 | Haiku | cp (neg) | neg only: own side | 0 | none | places nothing |
| 57 | both routes | k (neg) | aff only: the other side | 2 | none | places nothing |

* **Row 13 is the only one under an answer heading inside its own side's block.** Its outer heading is
  not an answer heading and places nothing, so 1.2.0's "inside the position's own block" clause had no
  block heading for the model to see.
* **Rows 7, 17 and 39 sit under no answer heading.** They are in files on their own side, and the model
  still answered `answers`.
* **Row 57 is in a file disclosed only on the other side.** t46's side rule scores any placement there as
  answering, whatever the model says. No prompt reaches it (below, under *Three rows no answer can
  reach*).

**The stance follows the file's side.** The 45 rows labelled with a position break down like this:

* 32 are read, in files on their own side;
* 10 answer (`at:`), all in files on the other side;
* 3 are read in files on the other side (rows 16, 33 and 57).

No `at:` label sits in a file on its own side.

**The rule, proposed:** a placement whose file was disclosed only on its position's own side reads that
position, whatever its heading or stance says. It mirrors t46's rule, under which a placement whose file
was disclosed only on the other side answers it. A position either side reads, a file disclosed on both
sides, and a file on no readable side keep the role they have.

**Where the rule lives in stage one.** Not in the matcher's `place`. Stage one's results are cached by the
card's fingerprint (its headings and tag), which cards in files on different sides share. A side in the
fingerprint would re-key every cached result, and would change which card the model is asked about, so
1.2.0's recordings would no longer replay. Instead:

* one pure function in `debate_core.arguments.landscape`, `side_role(taxonomy, position_id, role,
  file_sides)`;
* applied in `PositionClassificationService.classify` where each card's result meets its own source, so
  the report receives the card's role after the rule. The cache keeps the matcher's role;
* `scored_stance` becomes the same function's stance, so the evaluation and the report keep one rule.

The report's own counting loop (`landscape_report.py`) does not change.

**Measured on the kept 1.2.0 cassettes** (pipeline score, bar 0.85):

| The own-side rule applied to | Claude Sonnet 4.6 (`deep_audit`) | Claude Haiku 4.5 (`high_volume`) |
|---|---|---|
| Nothing (as recorded) | 23 of 33, 0.697 | 21 of 37, 0.568 |
| Stage one's placements only | 23 of 33, 0.697 | 21 of 37, 0.568 |
| Stage one's and the model's (recommended) | **26 of 33, 0.788** (rows 7, 13, 17) | **23 of 37, 0.622** (rows 17, 39) |

No row that was right turns wrong. Stage one alone changes nothing here, because its 4 sure placements of
labelled cards are 3 `at:` rows in files on the other side and 1 read row on its own side.

**Stage one's change over the whole snapshot** (126,681 cards):

* 181 sure placements with role ANSWERS sit in files on their position's own side, plus 19 below the
  threshold. The report drops these today, and the rule would count them. By kind: da 112, advantage 57,
  k 7, theory 4, t 1.
* Where the answer heading sits: on 146 of them the placing heading is itself the answer heading; on 35
  it is above the placing heading.
* They touch 20 positions in 61 files. Of their 75 position-and-file pairs, 12 already have a sure
  reading card of that position in the same file, so 63 pairs would add the position to that file's
  rounds.
* For scale: 62,535 sure placements already read. 1,908 sure ANSWERS placements in files on the other
  side, and 14 in files disclosed on both sides, keep their role.

**The prompt's wording.** It replaces 1.2.0's answer-heading bullet, below. The model is not sent the
file's side. It is asked once per fingerprint, and one fingerprint can stand for cards in files on both
sides, so the deterministic rule decides the side and the prompt covers what the model can see:

> A card that defends a position against the other side's answers to it reads the position: a negative's
> card answering the affirmative's answers to its own disadvantage, counterplan or kritik (that it is not
> unique, that there is no link, a permutation), or an affirmative's card answering the negative's
> answers to its own advantage. Its stance is reads, even under an answer heading.

### (b) The coach's rulings of 2026-11-05, as prompt changes

The rows they aim at, as recorded under 1.2.0:

| Row | Label | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|---|
| 5 | `at:pharma-advantage` (file: neg) | `pharma-da`, reads | `pharma-da`, reads |
| 28 | `innovation-advantage` (file: aff) | right | `at:innovation-da` |
| 34 | `growth-advantage` (file: aff) | `at:economy-da`, below the threshold | right |
| 26 | `at:cap-k` (file: aff) | `nhi-aff`, reads | right |
| 21, 40 | `at:delay-cp` (file: aff) | `at:should-t` | `at:should-t` |

* **No mirror pairs (rows 5, 28, 34).** A new bullet: an advantage and a disadvantage about the same
  subject are different positions. A negative's card against an advantage answers the advantage, never
  the disadvantage about the same subject. An affirmative's card making an advantage's claim reads the
  advantage, even when the claim also answers a disadvantage about that subject.
* **An answer is the position answered, never the answering side's own case (row 26 and row 5).** The
  answering bullet now names both directions: an affirmative's card against a negative position is not
  the affirmative's plan or advantage; a negative's card against an affirmative position is not the
  negative's own disadvantage, counterplan or kritik. 1.2.0 named only the first, and row 5 is the
  second.
* **A definition against a counterplan (rows 21, 40).** The topicality bullet gains a sentence: a
  definition the affirmative reads against a counterplan, to show it does not compete or is ruled out, is
  not topicality, and it answers that counterplan. There is no `should-t` second label.

Whether these turn the rows is measured only by the re-record; nothing offline can show it.

### (c) `generic-k`: what the model is missing

`generic-k`'s description defines it only by exclusion: a kritik card that fits no named kritik in the
list. Its one alias, the coach's queue heading, is not sent to the model. What the three rows show:

| Row | Headings | Words pointing at a position (the matcher's own word rules) | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|---|---|
| 46 | 2 | its headings share a word with two theory positions; nothing with a kritik | `cap-k`, answers, 0.52 | refused, `NO_POSITION` |
| 50 | 0 | none | `framework-t`, reads, 0.55 | refused, `NO_POSITION` |
| 60 | 2 | none | `cap-k`, answers, 0.55 | **`generic-k`, reads, 0.50** |

Every `generic-k` answer either route gave is below 0.6: Sonnet 0.40 and 0.55 (rows 16 and 37), Haiku 0.35
and 0.50 (rows 37 and 60). The model is missing three things:

1. **Confidence it is not allowed to give.** The prompt says 0.9 or more only when the tag or headings
   name the argument, and under 0.6 when choosing between positions. A tag or heading never names a
   generic position, so even a right `generic-k` answer, such as Haiku's row 60, stays below the review
   threshold (0.6). As written, the prompt cannot place a generic position.
2. **A positive picture of a generic kritik.** With no kritik named in headings or tag, Sonnet reaches for
   the named kritik nearest in subject (`cap-k`, rows 46 and 60), and Haiku does not see a kritik at all
   and refuses, against 1.2.0's never-null rule.
3. **A kritik's framework is not topicality's.** Row 50 went to `framework-t`. The word "framework" sits in
   `generic-k`'s description (a kritik's framework) and in `framework-t`'s label (topicality).

**Proposed prompt change (recommended):**

* the kritik and counterplan bullet: a named kritik only when the card argues its theory as its
  description says; otherwise the generic one, even when the subject is near a named one;
* a framework bullet: a kritik's framework card (how to weigh the round, representations or ontology
  first, the role of the ballot) belongs to a kritik, never to topicality, whose framework argument says
  the affirmative must defend a plan;
* the confidence paragraph: a generic position is never named by a tag or heading, so give it 0.9 or more
  when the card is plainly that kind's and no named one fits.

**The confidence clause's risk, computed on the recorded answers:** with every recorded `generic-k` answer
lifted over the threshold and nothing else changed, Sonnet would count rows 16 and 37 wrong (23 of 35,
0.657), and Haiku would gain row 60 and lose row 37 (22 of 39, 0.564). The clause pays only if the model
also chooses `generic-k` for rows like 46, 50 and 60. "Plainly that kind's" is meant to keep an advantage's
card (row 16) and a card labelled none (row 37) low. Only the re-record shows whether it does.

**A description change, for the coach's review (not made in this task):**

* `generic-k`: "A kritik card, a link, alternative, framework or impact, whose theory no named kritik in
  this list describes, such as a critique of the affirmative's ontology."

It takes the coach's own alias as its example. It would move the generic taxonomy to 1.1.3 and the topic
taxonomy with it, which re-keys the cassettes again. It is better made with the coach before `v1-e32-t50`'s
held-out sample than inside this re-record.

### Three rows no answer can reach (rows 16, 33, 57)

These three are labelled as read (an advantage on rows 16 and 33, `cap-k` on row 57), in files disclosed
only on the side opposite their position. The coach kept all three at the sitting, and was shown each
file's side. Under t46's side rule, which is the report's, any placement in those files scores as
answering, so none of the three can be counted right. Row 57 is counted wrong on both routes today. Rows 16
and 33 are below the threshold on Sonnet; on Haiku, 16 is refused and 33 is a wrong kind. The PM can choose
one of:

* (i) leave them; the bar's denominator keeps them;
* (ii) take them to the coach. A negative that reads an affirmative's advantage, for example a counterplan
  claiming to solve it, may be a second label the coach wants;
* (iii) an exception to the side rule. Not recommended: the report then counts a position for the side
  that does not read it.

*Recommended:* (ii), alongside `v1-e32-t50`.

### Prompt 1.3.0, the whole change

Same variables, same user turn, the same stanced schema, batches of 20. Front matter: `version: 1.3.0` and
its changelog entry. The system turn changes as below. 1,591 more characters, about 400 tokens per call:

```diff
 - A link, internal link or impact card belongs to ... [unchanged]
+- An advantage and a disadvantage about the same subject are different positions, and neither stands for the other. A negative's card against an advantage answers that advantage: never choose the disadvantage about the same subject for it. An affirmative's card that makes an advantage's claim reads the advantage, even when the claim also answers a disadvantage about the same subject.
-- A topicality card defines a word of the resolution or says a plan breaks a definition. Choose the topicality position whose interpretation it supports, not the affirmative it is read against.
+- A topicality card defines a word of the resolution or says a plan breaks a definition. Choose the topicality position whose interpretation it supports, not the affirmative it is read against. A definition the affirmative reads against a counterplan, to show that the counterplan does not compete or is ruled out, is not topicality: it answers that counterplan.
-- A card that answers a position belongs to the position it answers, with the stance answers: an affirmative's card against a disadvantage, counterplan or kritik belongs to that negative position, and a negative's card against an advantage or a plan belongs to that affirmative position. Do not choose the plan or advantage the card defends instead.
-- When a card is marked as under an answer heading, it answers the position the headings name: stance answers. A card under an answer heading inside the position's own block, answering the other side's answers to it, still reads it.
+- A card that answers a position belongs to the position it answers, with the stance answers, never to the answering side's own case: an affirmative's card against a disadvantage, counterplan, kritik or topicality argument belongs to that negative position, not to the affirmative's plan or advantage; a negative's card against an advantage or a plan belongs to that affirmative position, not to the negative's own disadvantage, counterplan or kritik.
+- A card that defends a position against the other side's answers to it reads the position: a negative's card answering the affirmative's answers to its own disadvantage, counterplan or kritik (that it is not unique, that there is no link, a permutation), or an affirmative's card answering the negative's answers to its own advantage. Its stance is reads, even under an answer heading.
+- When a card is marked as under an answer heading and does not defend the position the headings name, it answers that position: stance answers.
 - A kritik's card (its link, framework, impact or alternative) or a counterplan's card (its text, a plank or its solvency) belongs to a kritik or a counterplan even when it reads as general.
-  Choose the named one it fits; when none fits and the list has a generic position of that kind, whose description says it fits no named position of that kind, choose the generic one. Never answer null for such a card.
+  Choose a named one only when the card argues its theory or its text, as its description says; when none does and the list has a generic position of that kind, whose description says it fits no named position of that kind, choose the generic one, even when the card's subject is near a named one. Never answer null for such a card.
+- A kritik's framework card (how the judge should weigh the round: that representations, ethics or ontology come before consequences, or the role of the ballot) belongs to a kritik, named or generic, never to a topicality position. A topicality framework argument says the affirmative must defend a plan.
 ...
 Give a confidence from 0 to 1: ... use less than 0.6 when you are choosing between positions or guessing from the evidence alone.
+A generic position is never named by a tag or heading: give it 0.9 or more when the card is plainly that kind's and no named position of the kind fits, and less than 0.6 when you are unsure the card is that kind's.
```

(The kritik bullet and the confidence paragraph are one line each in the file. They are split here only to
show the changed sentence.)

### What the build would hold, once ruled

* **Prompt.** `prompts/landscape/classify_position@1.3.0.md`, released and locked, and the stage's default.
  1.2.0's file, schema and cassette key are unchanged. A test proves that 1.2.0's recordings keep their key
  and that 1.3.0 finds none of them, as t46's does for 1.1.0.
* **The rule.** `side_role` in `debate_core.arguments.landscape`. It is applied per card in
  `PositionClassificationService.classify`, to stage one's result and the model's, and `scored_stance` is
  built on it.
* **Tests on invented cards, shown failing first:**
  * the rule's cases: own side, other side, both sides, no readable side, and a position either side reads;
  * the service giving READS to a card under an answer heading in a file on its own side, while its twin
    by fingerprint in a file on the other side keeps ANSWERS;
  * the scoring of a model answer of `answers` in an own-side file;
  * the 1.3.0 prompt's text pins;
  * the version and key tests.
* **Docs.** The evaluation's data page (the rulings and the computed figures), and the record runbook's
  block for the re-record.

**The re-record, after the build.** The 47 on `deep_audit` only, unless the PM rules Haiku in. Priced from
`config/model_pricing.yaml` at 1.2.0's recorded tokens plus about 1,200 input tokens for the 3 calls:

* `deep_audit` (Claude Sonnet 4.6, $0.003 and $0.015 per 1,000 input and output tokens): about 41,400
  input and 4,850 output tokens, **about $0.20**;
* `high_volume` if ruled (Claude Haiku 4.5, $0.001 and $0.005): **about $0.06**.

**Deviations this needs:** none expected. `tests/smoke` and `docs/runbooks` are in the spec's packages. If
the synthetic archive's end-to-end cassette is keyed by the default version again, it is rewritten offline
by its own script, as in t46, and that is outside the packages.

## The PM's ruling (2026-11-05)

1. **The own-side rule: (A).** `side_role` is applied in `PositionClassificationService.classify` to stage
   one's placements and the model's answers alike, and `scored_stance` is built on the same function, so the
   report and the evaluation keep one rule. It does not go in the matcher; the fingerprint reasoning is
   accepted. The 181 sure placements across the snapshot that change role to reads are accepted as a
   product change: they are a side's cards defending its own position against answers (da 112, advantage
   57, k 7, theory 4, t 1), which the report has been dropping. The report keeps those counts as the
   production effect, with the 63 position-and-file pairs it adds. The tests, on invented cards and shown
   failing first:
   * own side reads under an answer heading;
   * own side reads when the model says answers;
   * the other side still answers;
   * a file on both sides, and a position either side reads, keep their role;
   * 1.2.0's recordings replay unchanged.
2. **Prompt 1.3.0: accepted as written**, all three groups, the generic-confidence clause included, on one
   condition. The re-record's breakdown counts the answers naming a generic position on their own: how
   many, how many above the threshold, and how many of those are right and wrong. If generic answers above
   the threshold are wrong more often than right, the clause comes out in a 1.3.1 follow-up, not in this
   task. Rows 12 and 55 (`cap-k`, right today) are to be watched: a `cap-k` card turning `generic-k` is
   the clause's other risk, and the report names any such row.
3. **Rows 16, 33 and 57: (ii)**, to the coach alongside `v1-e32-t50`. They may not be mislabels: a
   negative can read an affirmative's advantage (an advantage counterplan claiming to solve it, rows 16 and
   33), and a kritikal affirmative can read a kritik's theory (row 57). Per row, the coach chooses an `at:`
   label, a second label, or "the side rule is wrong here". The third becomes a PM-filed follow-up on t46's
   other-side rule. (iii) is not built now.
4. **The `generic-k` description change** is a separate follow-up for the coach's review before
   `v1-e32-t50`'s sitting, filed by the PM. It is not in this re-record.
5. **The re-record runs on `deep_audit` only.** The operator block reads the cost from
   `config/model_pricing.yaml`. It guards on a set `DEBATE_` variable, a running caselist pull and the
   Bedrock profile's sign-in, as t46's did.

The build order: `side_role` and its tests; then 1.3.0 with its version, lock and cassette key; then the
operator's re-record block. The bar, the threshold and the coach's labels do not change.

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

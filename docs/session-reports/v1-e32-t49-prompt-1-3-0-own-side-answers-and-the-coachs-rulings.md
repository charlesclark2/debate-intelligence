# Session report: v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings

| | |
|---|---|
| Task | `v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings` — Prompt 1.3.0 and stage one: a card defending its own side's position reads it, and an answer is never the position it answers |
| Spec | [`plan_specs/v1/e32-argument-landscape/t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings.yaml`](../../plan_specs/v1/e32-argument-landscape/t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings` |
| Session status | COMPLETE (the Goal stays InProgress: ac3's re-record on `deep_audit` is the operator's) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The Goal stays InProgress.** ac3 is the operator's re-record on `deep_audit`. Its block is under
[Operator follow-ups](#operator-follow-ups), and the PM records the result. Everything else is built as the
PM ruled on 2026-11-05 ([the ruling](#the-pms-ruling-2026-11-05)), with tests on invented cards shown
failing first.

**What was built:**

* **The own-side rule.** A placement in a file disclosed only on its position's own side reads it.
  `side_role` lives in a new module, `debate_core.arguments.landscape.side_role`. It is applied per card in
  `PositionClassificationService.classify`, to stage one's placements and the model's answers alike, and
  `scored_stance` is built on it.
* **Prompt 1.3.0.** Released, locked and the stage's default, exactly as proposed. It keeps 1.2.0's
  variables, user turn and stanced schema.
* **The generic count.** `--breakdown` counts the answers naming a generic position on their own
  (`generic_answers`), as the ruling's condition on the generic-confidence clause asks.

**What it measures, on the operator's kept 1.2.0 recordings** (replayed from this branch at 1.2.0, no model
called): every answer is identical, and the rule alone takes Sonnet from 23 to 26 of 33 (0.788) and Haiku
from 21 to 23 of 37 (0.622), the figures the proposal computed.

**What the PM should look at first:**

* In `classify`, the rule decides only the own-side half. The other side's half stays per round in the
  report, so its `other_side_position_rounds` tally is unchanged ([decision 1](#decisions-and-assumptions)).
* Two of t46's hand-worked expectations moved with the ruling ([decision 6](#decisions-and-assumptions)).
## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prompt-1-3-0-own-side-answers-and-the-co` (Prompt 1.3.0) | Done | Built in the ruled order: `side_role` and its tests, then 1.3.0 (version, lock, cassette key), then the generic count the condition needs, then the operator's block. Its criterion passes (1,244 tests). ac3 waits on the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal (the own-side rule for the prompt and stage one, with its counts; the prompt's changes for (b); the generic-k finding) ruled on by the PM before any code | PASS | Proposed in `c8c1209`, before any code ([the proposal](#the-proposal-2026-11-05-for-the-pms-ruling-kept-as-written)). The PM ruled on 2026-11-05 ([the ruling](#the-pms-ruling-2026-11-05)). The first code commit is `ff5ebc0` |
| ac2: prompt 1.3.0 and stage one carry what is ruled, by tests on invented cards shown failing first, with the version bumped and its cassettes keyed by it, and 1.2.0's recordings replaying unchanged | PASS | See [How ac2 was shown](#how-ac2-was-shown) below |
| ac3: the operator's re-record of the 47 under 1.3.0 on the ruled routes, its breakdown and scans, recorded in docs/data beside 1.2.0's (operator, recorded by the PM) | NOT RUN (operator) | The PM ruled `deep_audit` only. The block is under [Operator follow-ups](#operator-follow-ups) and in [the record runbook's last section](../runbooks/landscape-model-evaluation-record.md#prompt-130-the-re-record-on-deep_audit-v1-e32-t49); the PM records the result |
| Node: Prompt 1.3.0 tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/arguments/landscape` → 1,244 passed in 12 s |

### How ac2 was shown

**Red, each step against a skeleton that keeps today's behaviour:**

* **The own-side rule:** `side_role` returned the role it was given, and `classify` called it. 15 failed,
  37 passed. Every failure was a role or stance assertion.
* **The cache guard** (the cache keeps stage one's role) is green on the skeleton by design: it guards
  against the rule moving into the matcher or the cache.
* **Prompt 1.3.0:** before the prompt file existed, 20 failed, 40 passed. 18 failed on the missing 1.3.0,
  1 on the default still being 1.2.0, and 1 on the default finding 1.2.0's recording.
* **The generic count:** a skeleton counting nothing. 2 failed, both on the count assertions.

**Green:**

* 1.3.0 is released and locked (`scripts/lock_prompts.py`, then `--check` OK). It is the stage's default
  (`CLASSIFY_POSITION_VERSION`), in the stanced schema.
* 1.2.0's key is kept and 1.3.0 never finds it:
  `test_1_2_0_recordings_replay_unchanged_and_1_3_0_finds_none_of_them`.

**The kept 1.2.0 recordings replay unchanged:**

* The session replayed the operator's real 1.2.0 cassettes on both routes from this branch, with the stage
  pinned to 1.2.0 (read-only, no model, about 1 minute per route). No `MISSING_FIXTURE`.
* All 47 answers, confidences and refusals are identical to the pre-task replay on each route.
* Only rows 7, 13 and 17 (Sonnet) and 17 and 39 (Haiku) change outcome, from wrong stance to correct.
  Pipeline: 26 of 33 and 23 of 37.

**Mutants:** all 12 caught ([below](#mutants)).

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 294 of 699 test files (42.1%) from 23 changed files |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124) before the run finished. Left to the pull request's `ci` (agreement 10) |
| The changed test directories and the always-run list: `packages/debate_core/tests/{arguments/landscape,domain,integrations/models,integrations/landscape}`, every `test_landscape_*`, `test_coach_sample_*` and `test_position_classification.py` in `debate_core/tests/application`, `debate_cli/tests/test_landscape*.py`, `tests/smoke/test_landscape*.py`, `tests/integration/test_e2e_caselist.py`, `tests/fixtures/caselist/test_synthetic_archive.py`, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, with `-m "slow or not slow"` | 4,131 passed in 59 s |
| `uv run ruff format --check .`, `uv run ruff check .` | 1,958 files formatted; all checks passed |
| `uv run pyright packages/debate_core packages/debate_cli`, and `tests/smoke/test_landscape_evaluate_smoke.py` | 0 errors |
| `uv run lint-imports`, `uv run python scripts/check_thin_handlers.py` | 20 contracts kept; 72 handlers within 25 statements |
| `uv run scripts/lock_prompts.py --check`, `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py` | OK (3,597 links and anchors) |
| `uv run scripts/validate_specs.py` (the Goal left InProgress: ac3 is the operator's) | OK: 629 files, 41 epics, 566 tasks, 22 releases |

### Mutants

Run against the landscape argument tests, `test_position_classification.py`, `test_coach_sample_stance.py`,
`test_landscape_evaluation_breakdown.py` (and the CLI tests for the generic count). Each mutant was
restored after its run (`git checkout HEAD --`):

| Mutant | Caught by |
|---|---|
| Own side means any side the file holds (a file on both sides reads) | 7 tests |
| `UNKNOWN` counts as a readable side | 6 |
| PF's pro is not read as aff | 1 |
| `classify` does not apply the rule | 2 |
| `classify` applies it to stage one only, not the model's answers | 1 |
| The rule also turns a read in a file on the other side into ANSWERS (the report's half) | 2 |
| A changed result's rationale gains no note | 3 |
| `scored_stance` ignores `side_role` | 7 |
| A below-threshold generic answer is counted | 2 |
| A generic answer the coach accepts on a second label is a named-label row | 1 |
| A named label of another kind is a named-label row | 1 |
| The breakdown carries no generic positions | 1 |

One planned mutant was equivalent, and the check it targeted was deleted (`d9b1bf9`). `side_role` had
required the position to be read by one side. A position either side reads has the side `both`, which never
equals a file's readable sides (only aff or neg), so the guard could never matter.

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

* **`prompts/`**: `landscape/classify_position@1.3.0.md` (released; its body is the proposal's), and its
  entry in `prompts.lock.json`.
* **`debate_core.arguments.landscape.side_role`** (new): `side_role`, `on_own_side`, the readable sides.
* **`debate_core.arguments.landscape.evaluation_breakdown`**: `scored_stance` built on `side_role`; and
  `GENERIC_POSITION_PREFIX`, `generic_positions`, `GenericAnswers` and `generic_answer_counts`.
* **`debate_core.arguments.landscape.model_stage`**: its docstring (the model is never sent the side).
* **`debate_core.application.position_classification`**: each item's result through `on_own_side`, and its
  docstring.
* **`debate_core.application.landscape_model_stage`**: default 1.3.0.
* **`debate_core.application.landscape_model_evaluation`**: `EvaluationBreakdown.generic` and
  `generic_answers`.
* **`debate_cli.commands.landscape`**: `breakdown.generic_answers` in `--breakdown`'s JSON (Deviation 1).
* **Tests:**
  * new: `test_side_role.py` and `test_generic_answers.py`;
  * `test_position_classification.py`: the own-side section;
  * `test_answering_stance.py` and `test_coach_sample_stance.py`: the rule's scoring, and 1.3.0's version,
    replay and text;
  * `test_landscape_command.py`: the generic count, and the version pins;
  * the smoke version pin.
* **Outside the packages:** `tests/fixtures/caselist/synthetic_archive/` (Deviation 2).
* **Docs:**
  * [the evaluation's record](../data/landscape-model-evaluation.md#prompt-130-and-the-own-side-rule-v1-e32-t49-ruled-2026-11-05):
    the rulings, the computed 1.2.0 figures and the production effect;
  * [the record runbook](../runbooks/landscape-model-evaluation-record.md#prompt-130-the-re-record-on-deep_audit-v1-e32-t49):
    the block;
  * [the replay runbook](../runbooks/landscape-model-evaluation-replay.md): which checkout replays 1.2.0.

## Deviations from the spec

1. **`debate_cli.commands.landscape`**, outside the spec's packages. The ruling's condition on the
   generic-confidence clause asks the breakdown to count the generic answers, and `--breakdown`'s JSON is
   written there. The counting is in `debate_core`; the CLI writes one key, `generic_answers`. No smoke
   check pins the breakdown's key set.
2. **`tests/fixtures/caselist/synthetic_archive/`**, outside the spec's packages, as in t46. The end-to-end
   suite's one landscape cassette is keyed by the stage's default version, so it was written again offline
   by its own script (`uv run --frozen python -m tests.fixtures.caselist.synthetic_archive.record_landscape_cassette`;
   no model). The diff is the key and the prompt version, nothing else.
3. **The session's own read-only replays** of both routes' kept cassettes, and a stage-one pass over the
   snapshot. These found the proposal's counts and showed 1.2.0's recordings replaying. Each is a read-only
   command over files on the operator's Mac, about a minute long, which agreement 2 lets a session run.
   Nothing was written and no model was called.
4. **The affected set** (294 files) was stopped at 115 seconds and is left to the pull request's `ci`
   (agreement 10). The changed test directories and the always-run list ran instead.

## Decisions and assumptions

1. **`classify` applies only the own-side half.** The report reads a READS card in a round on the other
   side as `other_side_position_rounds`, per round. Turning those cards into ANSWERS in `classify` would
   have emptied that tally. So `side_role` only gives READS on the position's own side. The other-side half
   stays the report's (per round) and `scored_stance`'s (per file), as t46 left it. A mutant adding it to
   `classify` is caught.
2. **The cache keeps the role stage one or the model gave.** The rule is applied as each result meets its
   card's own file. A card read alike in a file on the other side keeps ANSWERS from the same cached result,
   by test.
3. **Every item goes through the rule, sections included.** One rule for every placement. The report counts
   only cards, so sections change no count.
4. **A changed result says so in its rationale.** `OWN_SIDE_NOTE` is added at the end, and the rationale is
   cut first so the whole stays within the 280-character limit. The matcher's own text ("an answer heading
   makes the role ANSWERS") would otherwise contradict the role.
5. **A generic position is one whose id starts `generic-`.** Today these are `generic-k` and
   `generic-theory`, the two the prompt calls "a generic position of that kind"; no other id starts so.
   `named_label_rows` names a row labelled with a named position of a generic's kind, answered with that
   generic, unless the answer scores right on a second label (the coach accepts it). It counts at any
   confidence, so a row below the threshold is named too.
6. **Two of t46's hand-worked expectations moved with the ruling.**
   * In `test_answering_stance.py`, a placement with role ANSWERS in a negative file, under a negative
     position, now scores reads. One pinned stance case and one outcome case changed, and the cases were
     extended (own side, other side, both sides, no side, a position either side reads).
   * In `test_coach_sample_stance.py`, row 2 (a negative file, the model saying `answers`) is now correct.
     The test exists to show a wrong stance counted through the evaluation's path. A seventh row in a file
     disclosed on both sides keeps one, and the hand-worked table and its counts (7 counted, 5 right) were
     redone by hand.
   * t46's two tests on the stage's default version now name 1.2.0 explicitly.
7. **The model is not sent the file's side.** As proposed and ruled: the model is asked once per
   fingerprint, and the deterministic rule decides the side.
8. **The budget ceiling.** The guard prices each call's ceiling from its variables only
   (`usage_router.structured_ceiling`), and 1.3.0 leaves them as 1.2.0 had them. So the block quotes t46's
   ceiling ($1.106 for Sonnet's three calls).
9. **A landscape run asks again** about every card cached under 1.2.0, since results are cached by prompt
   version. The hold on live runs stands.

## Operator follow-ups

**ac3: the re-record of the 47 under 1.3.0 on `deep_audit`, then its breakdown.** It is also in
[the record runbook's last section](../runbooks/landscape-model-evaluation-record.md#prompt-130-the-re-record-on-deep_audit-v1-e32-t49),
with what to read. It costs about $0.20, priced from `config/model_pricing.yaml` ($0.003 and $0.015 per
1,000 input and output tokens for Claude Sonnet 4.6) at 1.2.0's recorded tokens plus 1.3.0's longer
instructions. Expected runtime: 2 to 4 minutes. Run it from this task's worktree until it merges, or a
checkout of `dev` after. Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings
```

Then the block. It refuses a set `DEBATE_` variable, a running caselist pull, a failed sample check and a
Bedrock profile that is not signed in, each before any model call:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Paste back **the three JSON objects**, nothing else.

* **Success:** the sample check exits 0 with `labelled` 47. The recording shows `prompt_version` `1.3.0`,
  `route` `deep_audit`, and `labelled`, `found` and `asked` 47. The breakdown has `outcomes` summing to 47
  and `generic_answers` present.
* **Below the bar:** exit 1 `EVALUATION_BELOW_BAR` carries the counts in `error.details`.
* **A stop before any answer:** nothing was recorded. Paste it and run nothing again before the PM reads
  it.

**Only if a `scan` count is above zero:** read the hits in the terminal, and **never paste or copy them**.
Give each hit's number and whether its words name a team, a school or a tournament, or an ordinary word:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## The re-record, as the operator returned it (2026-11-05)

The operator ran the block above from this worktree and pasted the three JSON objects. They read the scan's
hits in the terminal only and judged every one an ordinary word. **ac3 stays NOT RUN until the PM records
it in docs/data**, as the criterion says. The figures below come from the pasted JSON. The comparison with
1.2.0 uses the session's replay of 1.2.0's cassettes under this branch's scoring
([How ac2 was shown](#how-ac2-was-shown)).

**The recording and its scans:**

* The sample check: `labelled` 47, `by_stance` answers 10 and reads 35, as 1.2.0 left it.
* The recording: prompt 1.3.0 on `deep_audit` (Claude Sonnet 4.6), taxonomy 1.5.0; 47 found and asked in 3
  calls, with no repair. 41,332 input and 4,737 output tokens: $0.195 at `config/model_pricing.yaml`'s
  $0.003 and $0.015 per 1,000 (estimated about $0.20).
* The scans:
  * the prompt inputs: clean, 0 hits;
  * the cassettes: 46 hits (41 a JSON key's name, 5 taxonomy words), none naming a team and none in the
    cards sent. All 3 texts were set aside, so `clean` is true;
  * no repair cassettes.

**The score:**

| Prompt, scored with the own-side rule | Pipeline (bar 0.85) | Below the threshold | Coverage |
|---|---|---|---|
| 1.2.0 (the session's replay of the kept cassettes) | 26 of 33, 0.788 | 14 | 0.702 |
| **1.3.0 (this re-record)** | **24 of 32, 0.750** | 15 | 0.681 |

* Outcomes under 1.3.0: correct 24, wrong stance 1 (row 57), wrong position of the same kind 3 (26, 45,
  58), wrong kind 4 (5, 21, 40, 41), below the threshold 15.
* The headings placed 4 cards (rows 11, 30, 31, 59), each naming the label.
* Weighted by stratum: 0.655.

**Where 1.3.0 differs from 1.2.0 under the same rule** (pipeline outcomes, row by row):

| Row | Label | 1.2.0 | 1.3.0 |
|---|---|---|---|
| 47 | `costs-advantage` | wrong position, same kind | **correct** |
| 15 | `none` | placed though labelled none | below the threshold (no longer counted wrong) |
| 9 | `rates-da` | correct | below the threshold (0.50) |
| 53 | `single-payer-t` | correct | below the threshold (0.55) |
| 58 | `stagnation-advantage` | correct | wrong position, same kind (`costs-advantage`) |
| 41 | `at:colonialism-k` | below the threshold | wrong kind (`kritikal-aff`, 0.62) |
| 45 | `data-advantage` | below the threshold | wrong position, same kind (`bioterror-advantage`, 0.72) |
| 26 | `at:cap-k` | wrong kind (`nhi-aff`) | wrong position, same kind (`at:generic-k`, 0.62) |

Every other row has the same outcome.

* Net: two rows gained, or one gained and one no longer counted wrong (47, 15). Five lost: two right
  answers fell below the threshold (9, 53), one right answer turned wrong (58), and two answers that had been
  below the threshold became wrong ones (41, 45).
* One card moves the score about three points. A difference of this size between two recordings is within
  what the sample can tell apart: the 95% interval on 24 of 32 runs from about 0.58 to 0.87 (Wilson).

**The coach's rulings (b):** none of the rows they aim at turned right.

* Row 5 is still `pharma-da`, and rows 21 and 40 are still `at:should-t`.
* Row 34 is still `at:economy-da`, below the threshold.
* Row 26 left the affirmative's own case (`nhi-aff`) and now has the stance right, but the position is
  `generic-k`.
* Row 28 is right on both.

**The PM's condition on the generic-confidence clause (ruling 2).** `breakdown.generic_answers`:

| Answers naming a generic position | Above the threshold | Right | Wrong | Named-label rows |
|---|---|---|---|---|
| 4 (rows 16, 26, 37, 46) | 1 (row 26, 0.62) | 0 | 1 | 26 |

* The generic answers above the threshold are wrong more often than right (0 to 1). **By the ruling, the
  clause comes out in a 1.3.1 follow-up**, not in this task.
* Rows 12 and 55 (`cap-k`) stayed right.
* The one named-label row is 26: an `at:cap-k` card answered `at:generic-k`, the risk the PM named.
* On the three `generic-k` rows, neither the clause nor the framework bullet changed the outcome:
  * row 46 is answered `generic-k`, the right position, but at 0.55, still below the threshold;
  * row 50 is still `framework-t` (0.55);
  * row 60 is still `cap-k` (0.50).

## Follow-up work

* **The analytic texts' roles.** `analytic_texts.py` places overviews, CP texts and alternatives with
  `matcher.place`. Under an answer heading in a file on the position's own side they are ANSWERS, and the
  report counts them "elsewhere". This is the same gap the ruling closed for cards, but it is outside
  `classify`. E32, the PM's to file.
* **The PM's own follow-ups, as ruled:**
  * 1.3.1, removing the generic-confidence clause, if the re-record's `generic_answers` above the
    threshold are wrong more often than right;
  * the `generic-k` description for the coach's review;
  * rows 16, 33 and 57 for the coach alongside `v1-e32-t50`, and a follow-up on t46's other-side rule if
    the coach rules it wrong for any of them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Built exactly as ruled, measured honestly, and the condition the ruling set was read and reported as
failing rather than argued around.

1. **ac1 passes.** Proposed in `c8c1209` with counts from replays that reproduce the recorded scores;
   ruled before the first code commit.
2. **ac2 passes.** `side_role` red against a skeleton (15 failed, each a role or stance assertion), 1.3.0
   red before its file existed, the generic count red against a skeleton; 1.3.0 released, locked and the
   default; 1.2.0's key kept and its real recordings replaying with every answer identical, the rule alone
   giving 26 of 33 and 23 of 37 as proposed. Twelve mutants caught, the one equivalent guard removed.
3. **Decisions accepted**, 1 in particular: `classify` applies only the own-side half, so the report's
   other-side tally per round is untouched, and a mutant adding the other half is caught. Decision 6's
   moved t46 expectations follow the ruling, redone by hand.
4. **Deviations accepted:** the one `generic_answers` key in the CLI; the synthetic archive's cassette
   rewritten offline by its own script, as in t46; the read-only replays (agreement 2); the affected set
   left to `ci` (agreement 10).
5. **ac3, the re-record, is in** and the PM records it in docs/data in the next batch: 24 of 32 (0.750) on
   `deep_audit`, below the 0.85 bar; the scans clean, the operator judging all 46 hits ordinary words.
   Against 1.2.0 under the same rule (26 of 33) it is within what 47 cards can separate (24 of 32: about
   0.58 to 0.87). The hold on live model runs stands.
6. **The generic condition fails** (above the threshold: 0 right, 1 wrong, row 26), so by the ruling the
   clause comes out in a 1.3.1 follow-up the PM files. Rows 12 and 55 stayed right.
7. **The operator's questions, ruled:**
   - **v1-e32-t50's prompt is 1.3.1**: 1.3.0 less the generic-confidence sentence, every other bullet
     kept. The (b) bullets and the framework and kritik bullets state the coach's rulings and the taxonomy's
     meaning; on this sample they neither gain nor measurably lose, and the choice is made now, on that
     ground, not on the held-out sample, so t50 measures one prompt it did not choose. Rows 9 and 53 (right
     under 1.2.0, below the threshold under 1.3.0) are the ones to watch in t50's breakdown.
   - **The (b) bullets stay** (above). If t50's held-out score falls below 1.2.0-with-the-rule's on the
     same rows, that comes back to the PM as its own question.
8. **Follow-ups the PM files:** 1.3.1 (E32, p2, before t50); the analytic texts' own-side role (E32, p3).
   The generic-k description (v1-e32-t53) and rows 16, 33 and 57 (on v1-e32-t50) are already filed.
9. **Closing checks:** the changed directories and the always-run list (4,131 passed), ruff, pyright,
   lint-imports, thin handlers, the prompt lock, command blocks, links and the specs are clean; the
   294-file affected set is the pull request's `ci`. Its search tests include
   `test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer`,
   which fails on the real clock (v1-e07-t16): if `ci` fails on it alone, re-run the failed job.
10. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the PM
    records ac3 in docs/data.

## Operator records (recorded by the PM, 2026-11-05)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3: the operator's re-record of the 47 under 1.3.0 on the ruled routes, its breakdown and scans, recorded in docs/data beside 1.2.0's (operator, recorded by the PM) | NOT RUN (operator) | PASS | deep_audit, 2026-11-05, prompt 1.3.0, taxonomy 1.5.0: 47 found and asked in 3 calls, 41,332 input and 4,737 output tokens. Pipeline 24 of 32 (0.750, bar 0.85), below the threshold 15, coverage 0.681, weighted 0.655; against 1.2.0 under the same rule 26 of 33 (0.788), within what the sample separates. Scans clean: prompt inputs 0 hits; cassettes 46 hits (41 a JSON key, 5 taxonomy words), all set aside, and the operator judged every one an ordinary word. The generic condition failed (above the threshold: 0 right, 1 wrong, row 26), so the clause comes out in v1-e32-t55. Recorded in docs/data |

ac3 passes, so the Goal is `Succeeded`. A scope addition the PM ruled after the review: commit def4453 on this branch put `test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer` on PacerTime, through crossref_factory's own clock and sleep, which unblocked dev's push runs; no production code changed, and v1-e07-t16 finished the sweep.

# Session report: v1-e32-t65-a-card-inherits-its-blocks-position

| | |
|---|---|
| Task | `v1-e32-t65-a-card-inherits-its-blocks-position` — A card the matcher could not place inherits the position of the block it is read in, measured first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t65-a-card-inherits-its-blocks-position.yaml`](../../plan_specs/v1/e32-argument-landscape/t65-a-card-inherits-its-blocks-position.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t65-a-card-inherits-its-blocks-position` |
| Session status | COMPLETE: measured, ruled on, and closed with no inheritance built, as the PM's ruling of 2026-11-20 provides. The Goal is Succeeded <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The task ends on the measurement, with no matcher code. `scripts/count_block_inheritance.py` places every card
with the real matcher and counts what each card left for review could inherit from its block. The operator ran
it four times over this Mac's store at 2026-11-03: three times on 2026-11-20 and once on 2026-11-25.

**Inheritance is never right on the coach's labels:**
* **The 120-rule set-agreement grid:** 0 right on the first sample, of up to 19 inherited cards, for every rule.
* **The one rule chosen there, scored once on the holdout:** 0 of 10 (95% interval 0.0 to 0.278).
* **The PM's 12 carry-forward variants in file order, on the first sample only:** 0 right of 3 to 14 carried
  cards each. The holdout was not read.

The wrong answers are always another position: another kind, or another position of the same kind. None is the
label's position with the other stance or a related one.

The PM's bar for keeping inheritance open was more than a third right, and no variant met it. So, as the PM's
ruling provides, ac2 is amended to "the measurement is recorded and the PM rules no inheritance", and the Goal
is set Succeeded.

[`docs/data/landscape-block-inheritance.md`](../data/landscape-block-inheritance.md) records every count. It
also records that the parser gives no block boundaries.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-card-inherits-its-blocks-position` (Block inheritance) | DONE | Measured and ruled on; no inheritance built. Its criterion is amended to the measurement's tests (Deviation 6). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the measurement, and the proposed rule with its score on the first sample and once on the holdout, are ruled on by the PM before code | PASS | The operator's three runs of 2026-11-20 (76.6 s, 92.6 s, 88.0 s), all `OK`, and the relay prompt below. The PM ruled on 2026-11-20 (quoted below), before any matcher code. |
| ac2 (amended per the PM's ruling): the measurement is recorded and the PM rules no inheritance | PASS | The carry-forward run of 2026-11-25 (61.5 s, `OK`): all 12 variants are at 0 right, under the ruling's one-third bar. The record is in [the data document](../data/landscape-block-inheritance.md#carry-forward-in-file-order-on-the-first-sample-only). |
| Node criterion (amended): `uv run pytest tests/scripts/test_count_block_inheritance.py` | PASS | 16 passed in 2.12 s. |

## Files changed

* `scripts/count_block_inheritance.py`: the measurement. It prints counts as JSON only: no tag, heading, path,
  school, team, row or item id. It has two refusals:
  * it scores the holdout only with one named rule, and refuses without one;
  * `--carry-forward` measures the PM's 12 file-order variants on the first sample, and refuses any holdout
    file.
* `tests/scripts/test_count_block_inheritance.py`: 16 tests on a planted synthetic store, with every expected
  count worked out by hand. Six planted bugs were each caught:
  * inheriting from a disagreeing block;
  * a card counted as its own neighbour;
  * the answer flag dropped from the grid;
  * the shell stop ignored;
  * the distance limit ignored;
  * the answer flag dropped from the carry.
* `docs/data/landscape-block-inheritance.md`: the counts and scores (aggregates and position kinds only), the
  PM's ruling, and the fact that the parser gives no block boundaries.
* The task spec: ac2 and the node criterion amended (Deviation 6), and the Goal set Succeeded.

## Deviations from the spec

1. **The snapshot.** The spec says the newest hspolicy26 and hsld26 snapshots. The PM's context of 2026-11-20
   says this Mac's store at 2026-11-03, parsed at `2026.10.27-docx-7`, and that is what was read. hspolicy26's
   newest version directory on the Mac is `2026.10.27-docx-7`, as the run recorded.
2. **LD has no counts.** At 2026-11-03, hsld26 has 2 sources on the de-extinction topic (Florida Blue Key only)
   and 10 cards, all unplaced, parsed at `2026.10.20-docx-6`. The PM ruled (c): no newer hsld26 measurement.
3. **The first sample was read at 2026-11-03**, not at its own 2026-10-20, following the PM's one-snapshot
   instruction. All 47 labelled cards were found. Headings place 4, all right. That is the same count
   `v1-e32-t43` recorded; t43 did not print which rows, so the match is by count only.
4. **How the counts came back.** The JSON is counts only. The operator wrote it to the session's scratchpad,
   and the session read it there, instead of the operator pasting about 3,000 lines. Nothing else was read
   from the store.
5. **Two grid runs before the holdout, not one.** The first grid scored 0 everywhere and could not say why. So
   a second run added the outcome breakdown and the `naming-nothing` choice, still on the first sample only.
   The holdout was read once, in the third run, with one rule.
6. **ac2 and the node criterion amended; no matcher code.**
   * ac2's text is the PM's, from the ruling.
   * The node criterion was `uv run pytest packages/debate_core/tests -k inherit`, a test of matcher code that
     the ruling means is never written. It now runs the measurement's own tests,
     `tests/scripts/test_count_block_inheritance.py`. This change is the session's, made to match ac2, and it
     is the PM's to confirm.
7. **A fourth run.** The carry-forward measurement is the one the PM asked for, run on the first sample only.
   The holdout was used once in all.

## Decisions and assumptions

* **The block.** The store keeps cards and their raw heading paths, never a heading paragraph. So a "run of
  cards between headings" is approximated by neighbouring cards with equal paths. Run-mates share every
  heading, so headings place them alike, and the counts confirm it: 0 of 57,132 cards have a run-mate placed by
  headings. The reader's section item and wider sections were measured beside the run. As (b) asks, this
  definition is left written as found.
* **The rule chosen for the holdout:**
  `level=nearest,placed=counted,agreement=unanimous,minimum=1,own=naming-nothing,role=answer-heading`. No rule
  scored better than another on the first sample. This one is the spec's example (placed cards agree), kept to
  cards with no own heading that might name another argument. It was chosen before the holdout was read.
* **Reading the carry-forward variants.**
  * The ruling's three choices are "nearest placed card only, or across one unplaced gap", "a shell-opening
    list, or none" and "the deciding section, or the document".
  * "Nearest only" and "one gap" are read as distance limits: the placed card is right before the card, or
    one unplaced card lies between.
  * The ruling's first bullet carries until the next placed card or a shell opener. That is a third distance,
    `until-stop`. With it, the grid is 3 × 2 × 2 = 12 variants, the ruling's maximum.
  * The deciding section is the deepest section over the card that holds an earlier placed card.
  * A card the coach's rulings decide is never carried to. The script counts separately how many would be.
* **The placement kind's name**, had any been built: `BLOCK_INHERITED`. `INHERITED` already means "placed by a
  heading further up" (`ClassificationMethod.INHERITED`).

### The relay prompt for the PM (2026-11-20, before the ruling)

```text
v1-e32-t65 (a card inherits its block's position): measured, scored once on the holdout, stopped for your ruling before code.

Facts (docs/data/landscape-block-inheritance.md has every count; counts only):
- hspolicy26 at 2026-11-03, parsed at 2026.10.27-docx-7, taxonomy 1.5.1: 126,681 cards. 64,661 counted, 1,329 placed by a tag keyword alone (0.5), 4,888 decided by the coach's no-position rulings, 55,803 unplaced. 57,132 left for review.
- The parser gives no heading paragraphs, only each card's raw heading path. A "run of cards between headings" can only be neighbouring cards with equal paths, and run-mates share every heading. So headings place them alike: 0 of 57,132 cards have a run-mate placed by headings. Only wider blocks hold placed neighbours: the reader's section with its subsections (117 agree), the parent section (8,022), the nearest section holding a placed card (15,673 agree, 25,180 disagree, 16,279 nothing placed), the document (8,934).
- First sample (v1-e32-t21, 47 labelled, all found, 4 placed by headings and all right): a 120-rule grid. It crossed five blocks, counted or counted+keyword neighbours, unanimous or two thirds, a minimum of 1 to 3, any own headings or only cards whose own headings name nothing, and answering or the block's role under an answer heading. Every rule inherits 0 right, of up to 19. The wrong answers are another kind (up to 12) or another position of the same kind (up to 8), never the label's position with the other stance, never a related id.
- Holdout (v1-e32-t50, 111 labelled, none placed by headings), scored once under the rule chosen on the first sample (nearest block, counted neighbours, unanimous, minimum 1, own headings naming nothing, answering under an answer heading): 10 inherit, 0 right (95% Wilson 0.0 to 0.278).
- That rule over the caselist: 6,491 cards inherit (4,611 under an advantage). The placed share goes from 0.510 to 0.562. The review queue goes from 57,132 queued cards to 50,641. Its heading rows stay 1,308 (a section is placed by its headings alone), or 1,273 if a section leaves once every card under it is placed.
- The other items you asked for, under the nearest/counted/unanimous/minimum-1 rule (15,673 inherit):
  - Answer headings: 1,118 inheriting cards sit under one, 1,107 of them below the deciding section. The matcher's own rule (Spending DA > AT: Link Turn reads) would call those the reading team's own block. The block reads for 918 of them and answers for 189.
  - Link-shaped tags: 77 of 684 cards inheriting a CP are link-shaped.
  - Name: BLOCK_INHERITED, since INHERITED already names heading inheritance.
  - These do not change the result: the role setting moved no outcome, and no inherited labelled card was link-shaped.
- LD: hsld26 at 2026-11-03 has 2 sources on the de-extinction topic, 10 cards, all unplaced (parsed at docx-6). It has no counts to give, and a newer snapshot would be needed.

Recommendation: build no inheritance. Every inherited placement on either sample is wrong: 0 of 12 on the first sample under the plain agreement rule, 0 of 10 on the holdout under the strictest one. A placement that is never right would put about 6,500 to 28,600 wrong cards into the report's counts, and it would take cards out of the review queue, the one place the coach would see them. Concretely:
  (a) rule that ac2 is not built. Close t65 on the measurement: amend ac2 and the node criterion to "the measurement is recorded and the PM rules no inheritance", then set Succeeded. Or set Cancelled with this record. Your call which.
  (b) say whether v1-e32-t66 (the block given to a model) still goes ahead. It depends on t65 for the block's definition. This measurement says the placed neighbours name another argument; it says nothing about what a block's tags in order would tell a model.
  (c) say whether LD wants these counts at a newer hsld26 snapshot. I recommend not, given the Policy result; if yes, name the snapshot.

Not recommended: building the chosen rule off by default, or as a suggestion column in the review queue. On these labels the suggestion would be wrong every time.

Reply with: a ruling on (a), (b) and (c), and any amendment text for the spec.
```

### The PM's ruling (2026-11-20), as received

```text
PM ruling, v1-e32-t65, 2026-11-20.

The set-agreement rules are ruled out: 0 right on either sample, and none is built, off by default or as a suggestion.

One more measurement before closing, on the first sample only, with the holdout not touched. The product owner's point is about order: a counterplan's text, then its solvency and net benefit; a disadvantage's uniqueness, then link, internal link and impact. None of the 120 rules read file order. So measure a carry-forward rule:
- within the deciding section, in file order, an unplaced card takes the position of the nearest preceding card placed by its headings or tag keyword;
- the carry ends at the next placed card, or at a tag that opens a new shell (for example "Text:", "Interpretation", "Uniqueness", a plan or counterplan text), whichever comes first;
- under an answer heading it carries as answering.
Try at most 12 variants: carry from the nearest placed card only, or across one unplaced gap; a shell-opening list, or none; the deciding section, or the document. Report right, wrong (by the same breakdown: another kind, another position of the same kind) and coverage on the first sample, plus the caselist-wide counts of what each variant would inherit. Counts only, as before. Then stop.

If no variant gets more than a third of its inherited labelled cards right on the first sample, inheritance is closed: ac2 is amended to "the measurement is recorded and the PM rules no inheritance", and the Goal is Succeeded on the measurement. If one does, the PM rules whether it is scored on the holdout, which would be the holdout's second and last use, recorded as such.

(b) v1-e32-t66: no work in this task. The PM decides its scope with the product owner after this measurement. Leave the block's definition written as found: the parser gives heading paths, not heading paragraphs.

(c) LD: no newer hsld26 measurement. The 2026-11-03 store has 10 de-extinction cards, and nothing here would change with more.

Write the finding into docs/data/landscape-block-inheritance.md, including that the parser gives no block boundaries, so a later task that needs them knows.
```

### The carry-forward result (2026-11-25)

On the first sample, every variant carries 0 right. The `shells` setting changed no first-sample outcome, so
the table pairs the variants:

| Variants | Carried | Right | Wrong: another kind, same kind | 95% upper bound | Coverage (before 0.085) | Carried across hspolicy26 |
|---|---|---|---|---|---|---|
| adjacent, section or document | 3 | 0 | 2, 1 | 0.561 | 0.149 | 2,855 to 3,417 |
| one-gap, section or document | 4 | 0 | 3, 1 | 0.490 | 0.170 | 5,210 to 6,284 |
| until-stop, section | 13 | 0 | 7, 6 | 0.228 | 0.362 | 15,011 to 15,092 |
| until-stop, document | 14 | 0 | 8, 6 | 0.215 | 0.383 | 21,274 to 21,632 |

No variant is over the third, so by the ruling inheritance is closed. The per-variant caselist counts are in the
data document: by kind, from keyword-placed cards, under an answer heading, decided cards, and placed share.

## Checks run (2026-11-25)

* **Affected set.** `uv run scripts/affected_tests.py --run --slow` covers 59 files. Bounded with
  `scripts/hard_stop.py 115`, it stopped at its limit past 96%, with no failure printed. It is over two
  minutes, so it is left to the pull request's `ci` (agreement 10). The 2026-11-20 run, before the carry-forward
  commit, stopped the same way.
* **Tests.** `pytest tests/scripts/test_count_block_inheritance.py tests/specs`: 98 passed.
  `uv run pytest tests/scripts/test_count_block_inheritance.py` (the node criterion): 16 passed.
* **Linters and checks:**
  * `ruff format --check` and `ruff check` on the script and its tests: clean;
  * `pyright` (whole project): 0 errors;
  * `lint-imports`: 20 kept, 0 broken;
  * `scripts/validate_specs.py`: OK, 690 files;
  * `scripts/docs_index.py --check-descriptions`: OK;
  * `scripts/check_command_blocks.py --base origin/dev`: OK.
* **The spec against `origin/dev`.** It matched apart from the phase. This used the local ref of 2026-11-20,
  not fetched.

## Operator follow-ups

None outstanding. The four runs done are listed here for the record. Each ran from the task worktree, with the
standard check that no `DEBATE_` variable is set and no `caselist pull` is running. Each wrote counts-only JSON
to the session's scratchpad.

```bash
uv run python scripts/count_block_inheritance.py --snapshot 2026-11-03 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
```

```bash
uv run python scripts/count_block_inheritance.py --snapshot 2026-11-03 --caselist hspolicy26 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
```

```bash
uv run python scripts/count_block_inheritance.py --snapshot 2026-11-03 --caselist hspolicy26 --holdout-sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-holdout-sample-labelled.csv --holdout-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-holdout-2026-11-03-sample.jsonl --holdout-rule level=nearest,placed=counted,agreement=unanimous,minimum=1,own=naming-nothing,role=answer-heading
```

```bash
uv run python scripts/count_block_inheritance.py --carry-forward --snapshot 2026-11-03 --caselist hspolicy26 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
```

## Follow-up work

* **`v1-e32-t66`:** no work was done here. The PM decides its scope with the product owner after this
  measurement. Any block it needs must come from paths or file order; the parser records no block boundaries.
* **`v1-e32-t64`:** its placements listing has no `BLOCK_INHERITED` to list.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-25

**Notes:**

Accepted. ac1, the amended ac2 and the amended node criterion pass, and the Goal is `Succeeded` on
the measurement, as the PM's ruling of 2026-11-20 provided.

* **The answer is unambiguous, and it was reached honestly.**
  * The 120-rule set-agreement grid inherits 0 right on the first sample.
  * The one rule chosen there inherits 0 of 10 on the holdout, scored once.
  * The 12 carry-forward variants in file order, run on the first sample only with the holdout not
    read, carry 0 right of 3 to 14 each.

  Every wrong answer is another position: another kind, or the same kind's other position. The
  holdout was used once in all, and every parameter was chosen before it was read.
* **The finding that matters most for later work is recorded:** the parser keeps heading paths, not
  heading paragraphs, so the store has no block boundaries. Run-mates share every heading, and a
  card's placed neighbours in the wider sections read other arguments. Any later block work starts
  from paths and file order, and the data document says so.
* **Deviations 1 to 7 are accepted.**
  * The snapshot, LD's counts and the first sample's read date follow the PM's context and ruling.
  * The counts came back as counts-only JSON read from the scratchpad, never pasted.
  * The second grid run before the holdout added only the breakdown and a choice, on the first
    sample.
  * **The node criterion: keep it.** The original selected tests of matcher code the ruling means is
    never written. `tests/scripts/test_count_block_inheritance.py`'s 16 tests are what this task
    built, checked against planted documents with hand-worked counts. The PM records the amended node
    in the next batch.
* **The checks.** The affected set (59 files) stopped past 96% with no failure and goes to `ci` under
  agreement 10. The measurement's tests, the spec tests, pyright and the import contracts are green.
  If `scripts/task pr` asks, `scripts/task sync`.
* **Follow-ups:**
  * `v1-e32-t64` needs no `BLOCK_INHERITED`.
  * `v1-e32-t66`'s premise, a block that "t65's inheritance leaves unplaced", is amended by the PM
    in the next batch: the block is taken from file order within the deciding section, and its
    proposal must show on the first sample alone that a model reading the tags in order does better
    than the per-card stage, before any build.

`scripts/task pr`

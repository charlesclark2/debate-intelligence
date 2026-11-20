# Session report: v1-e32-t65-a-card-inherits-its-blocks-position

| | |
|---|---|
| Task | `v1-e32-t65-a-card-inherits-its-blocks-position` — A card the matcher could not place inherits the position of the block it is read in, measured first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t65-a-card-inherits-its-blocks-position.yaml`](../../plan_specs/v1/e32-argument-landscape/t65-a-card-inherits-its-blocks-position.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t65-a-card-inherits-its-blocks-position` |
| Session status | PARTIAL: measured, scored once on the holdout, and stopped for the PM's ruling before code (ac1). The Goal stays InProgress <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The measurement asked for in step 1 is done, with no rule built. `scripts/count_block_inheritance.py` places
every card with the real matcher. For each card left for review, it counts what its block's placed cards say
under five block definitions, and scores a 120-rule grid on `v1-e32-t21`'s first sample. The operator ran it
three times over this Mac's store at 2026-11-03.

**No rule inherits a single right card.** It is 0 of up to 19 on the first sample, for every rule. Under the
one rule chosen there, it is 0 of 10 on `v1-e32-t50`'s holdout (95% interval 0.0 to 0.278). The wrong answers
are other positions, never the label's position with the other stance or a related one.

[`docs/data/landscape-block-inheritance.md`](../data/landscape-block-inheritance.md) records every count. The
proposal step 2 asks for is in the relay prompt below, and it recommends building no inheritance. The PM should
read the holdout line and the recommendation first.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-card-inherits-its-blocks-position` (Block inheritance) | IN PROGRESS | Measured and proposed; stopped for the PM's ruling before code, as ac1 asks. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the measurement, and the proposed rule with its score on the first sample and once on the holdout, are ruled on by the PM before code | NOT RUN: waiting for the PM's ruling | Measured: the operator's three runs of `scripts/count_block_inheritance.py`, 2026-11-20 (76.6 s, 92.6 s, 88.0 s), all `OK`; [the record](../data/landscape-block-inheritance.md). The proposal is the relay prompt under Decisions. |
| ac2: a card inherits its block's position only as ruled, every inherited placement named as inherited, tests shown failing first | NOT RUN | Waits on the ruling; the recommendation is to build none (below). |
| Node criterion: `uv run pytest packages/debate_core/tests -k inherit` | NOT RUN | No matcher code yet. |

## Files changed

* `scripts/count_block_inheritance.py`: the measurement. It prints counts as JSON only: no tag, heading,
  path, school, team, row or item id. It scores the holdout only with one named rule, and refuses to without
  one.
* `tests/scripts/test_count_block_inheritance.py`: 12 tests on a planted synthetic store, with every expected
  count worked out by hand. Three planted bugs were each caught, by 4, 2 and 1 failing tests: inheriting from
  a disagreeing block, a card counted as its own neighbour, and the answer flag dropped.
* `docs/data/landscape-block-inheritance.md`: the counts and scores (aggregates and position kinds only).

## Deviations from the spec

1. **The snapshot.** The spec says the newest hspolicy26 and hsld26 snapshots. The PM's context of 2026-11-20
   says this Mac's store at 2026-11-03, parsed at `2026.10.27-docx-7`, and that is what was read. hspolicy26's
   newest version directory on the Mac is `2026.10.27-docx-7`, as the run recorded.
2. **LD has no counts.** At 2026-11-03 hsld26 has 2 sources on the de-extinction topic (Florida Blue Key only),
   10 cards, all unplaced, parsed at `2026.10.20-docx-6`. Counts need a newer snapshot, and the PM asked to be
   told why before one is used; the question is in the relay prompt. No run was made.
3. **The first sample was read at 2026-11-03**, not at its own 2026-10-20, following the PM's one-snapshot
   instruction. All 47 labelled cards were found. Headings place 4, all right, the same count as
   `v1-e32-t43` recorded (which rows was not printed, so not checked).
4. **How the counts came back.** The JSON is counts only. The operator wrote it to the session's scratchpad
   and the session read it there, instead of the operator pasting about 3,000 lines. Nothing else was read
   from the store.
5. **Two runs before the holdout, not one.** The first grid scored 0 everywhere and could not say why, so a
   second run added the outcome breakdown and the `naming-nothing` choice, still on the first sample only. The
   holdout was read once, in the third run, with one rule.

## Decisions and assumptions

* **The block.** The store keeps cards and their raw heading paths, never a heading paragraph, so a "run of
  cards between headings" is approximated by neighbouring cards with equal paths. Run-mates share every
  heading, so headings place them alike, and the counts confirm it: 0 of 57,132 cards have a run-mate placed by
  headings. The reader's section item and wider sections were measured beside the run.
* **The rule chosen for the holdout**, with no rule better than another on the first sample:
  `level=nearest,placed=counted,agreement=unanimous,minimum=1,own=naming-nothing,role=answer-heading`. It is
  the spec's example (placed cards agree), kept to cards with no own heading that might name another argument.
  It was chosen before the holdout was read.
* **The placement kind's name**, if any is built: `BLOCK_INHERITED`. `INHERITED` already means "placed by a
  heading further up" (`ClassificationMethod.INHERITED`, in the cache, the JSON and the counts).

### The relay prompt for the PM

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

## Operator follow-ups

None outstanding. The three runs done are listed here for the record. Each ran from the task worktree, with the
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

## Follow-up work

* `v1-e32-t66` depends on this task's block definition. Whether it goes ahead is in the relay (b).
* `v1-e32-t64`'s placements listing lists `BLOCK_INHERITED` only if inheritance is built.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

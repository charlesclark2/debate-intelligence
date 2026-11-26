# Session report: v1-e32-t64-every-placement-can-be-corrected

| | |
|---|---|
| Task | `v1-e32-t64-every-placement-can-be-corrected` — The coach can correct any heading's placement, not only the headings the review queue lists |
| Spec | [`plan_specs/v1/e32-argument-landscape/t64-every-placement-can-be-corrected.yaml`](../../plan_specs/v1/e32-argument-landscape/t64-every-placement-can-be-corrected.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t64-every-placement-can-be-corrected` |
| Session status | IN PROGRESS: measured, proposal sent, waiting for the PM's ruling before code (ac1) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The measurement is done and the proposal is sent. No listing code has been written yet, as the spec and the
PM's context of 2026-11-25 ask.

`scripts/count_heading_placements.py` places every item of hspolicy26 at 2026-11-03 (parsed at
`2026.10.27-docx-7`, taxonomy 1.5.1) with the real matcher, then counts the headings that place them. The
operator ran it once, in 39.1 s, and it printed counts only. Its totals match `v1-e32-t65`'s for the same store:
* 126,681 cards;
* 64,661 counted;
* 1,329 placed by a tag keyword alone;
* 4,888 decided by the coach's no-position rulings;
* 57,132 queued, in 1,308 rows.

A placements listing would hold 337 rows: 292 placed and 45 ruled none. The 25 largest rows hold 59.6% of the
listed cards. The matcher already reads an override before an alias, and `apply_decisions` already accepts any
heading. So most of the work is the listing itself.

## The measurement (2026-11-25)

The operator ran `scripts/count_heading_placements.py --snapshot 2026-11-03 --caselist hspolicy26`, read-only,
in 39.1 s. It read 3,825 sources, 126,681 cards and 48,094 sections, under 45 overrides (30 of them ruled none).
The script's 10 tests on a planted store, with every count worked out by hand, pass. Five planted breaks in the
script were each caught at an assertion:
* the none rows counting every card under the heading;
* the `minimum_teams` rule dropped;
* a tag naming a child counted as another position;
* inheritance never credited to an override;
* the none decision simulated with the placing heading kept.

**Cards by how they were placed:**

| How placed | Cards | Documents | Teams | Placing headings |
|---|---|---|---|---|
| Alias, the heading directly over the card | 40,215 | 2,462 | 447 | 287 |
| Override, directly over | 2,803 | 614 | 201 | 28 |
| A heading further up (`INHERITED`), an alias | 21,094 | 1,390 | 263 | 201 |
| A heading further up (`INHERITED`), an override | 467 | 71 | 47 | 11 |
| Tag keyword under a placing heading (a child, 0.9) | 82 | 62 | 22 | 1 |
| Tag keyword alone (0.5), under a heading the coach can still decide | 879 | 556 | 238 | none |
| Tag keyword alone (0.5), under headings all ruled none | 188 | 99 | 69 | none |
| Tag keyword alone (0.5), under no heading | 262 | 164 | 95 | none |
| The coach's no-position decision | 4,888 | 714 | 275 | none |
| Unplaced | 55,803 | 3,258 | 499 | none |

Placing headings are counted as (heading, answer flag) pairs, as the queue keys its rows.

**Listing rows:**

* **A placed row** is the heading that places items: the nearest alias or override with a position. Its cards
  are the ones it places, directly or further down.
* **A none row** is a heading the coach ruled names no position. Its cards are the ones under it that no
  nearer heading places, which are the cards a changed decision on it would move.
* **Rows fewer than two teams use** are left out and counted, as in the queue.

| Row kind | Rows | Distinct headings | Answer rows | Listed rows: cards, documents, teams | Left out (under 2 teams): rows, cards |
|---|---|---|---|---|---|
| alias | 298 | 219 | 80 | 267: 61,266 cards, 2,719, 456 | 31, 125 |
| override | 28 | 15 | 13 | 25: 3,260 cards, 653, 209 | 3, 10 |
| none | 49 | 30 | 19 | 45: 22,244 cards, 2,112, 400 | 4, 14 |

* **Inherited cards:** of the listed alias rows' cards, 21,173 are placed by the heading from further up, and of
  the override rows', 467.
* **Tags naming another position:** of the listed alias rows' cards, 910, in 112 rows, have a tag naming a
  position outside the row's own line (itself, its ancestors and descendants). Of the listed override rows'
  cards, 50, in 10 rows.
* **Rows under more than one position:** one row puts its cards under two (its 82 tag-refined cards).
* **The review queue beside it:** 1,308 rows of 5,891 headings (4,583 left out). Its 22,646 queued items sit
  under no heading left to decide.

**The coach's `none` on a placed heading**, applied to every placed card's own placing heading:

| Where the card would go | Cards |
|---|---|
| A heading above still places it, under the same position | 6,247 |
| A heading above places it, under another position | 7,121 |
| Its tag keyword alone (0.5, so to the queue) | 873 |
| Nothing places it (to the queue, or decided when every heading over it is ruled none) | 50,420 |

**How the listed placed rows spread:**
* 292 rows hold 64,526 cards.
* The largest 25 rows hold 38,446 cards (59.6%), the largest 50 hold 48,763 (75.6%), and the largest 100 hold
  57,593 (89.3%).
* By teams: 40 rows have 2 teams, 55 have 3 to 5, 118 have 6 to 20, and 79 have 21 or more.
* The rows fall under 83 positions: at most 13 rows per position, median 3.

### The relay prompt for the PM (2026-11-25, before the ruling)

```text
v1-e32-t64 (every placement can be corrected): measured, stopped for your ruling before code.

Facts (hspolicy26 at 2026-11-03, parsed at 2026.10.27-docx-7, taxonomy 1.5.1; counts only, one operator run of 39.1 s; totals match t65's):
- Cards by how placed (cards / documents / teams / placing headings):
  - alias, directly over: 40,215 / 2,462 / 447 / 287
  - override, directly over: 2,803 / 614 / 201 / 28
  - INHERITED from a heading further up: by an alias 21,094 / 1,390 / 263 / 201; by an override 467 / 71 / 47 / 11
  - tag keyword under a placing heading (a child, 0.9): 82 / 62 / 22 / 1
  - tag keyword alone (0.5, under the threshold, so already in the queue and not counted): 1,329 in all
    - 879 under a heading the coach can still decide (a queue row)
    - 188 under headings all ruled none
    - 262 under no heading
  - the coach's no-position decision: 4,888 / 714 / 275
  - unplaced: 55,803
- Placed rows (heading + answer flag, as the queue keys them):
  - alias: 298 rows (219 headings, 80 answer rows); 267 listed (61,266 cards), 31 left out under minimum_teams (125 cards)
  - override: 28 rows; 25 listed (3,260 cards), 3 left out (10 cards)
- Headings ruled none: 49 rows; 45 listed, 4 left out (14 cards). Their cards are those under them that no nearer heading places: 22,244.
- So the listing would be 337 rows (292 placed + 45 none). The queue is 1,308.
- The coach's "none" on a placed heading, today's matcher rule (the heading is passed over), for its 64,661 cards:
  - 6,247 stay under a heading above, same position
  - 7,121 move to a heading above's other position
  - 873 fall to their tag keyword alone (0.5, so to the queue)
  - 50,420 are placed by nothing (to the queue under their other headings, or decided when every heading over them is ruled none)
- Finding the wrong ones:
  - The confidences are fixed per rule (1.0 directly over, 0.9 further up), so "least sure first" means nothing here.
  - The largest 25 rows hold 59.6% of the listed cards, 50 hold 75.6%, 100 hold 89.3%.
  - Rows fall under 83 positions: at most 13 per position, median 3.
  - 960 counted cards (1.5%), in 122 rows, have a tag naming a position outside the row's own line (itself, its ancestors and descendants).

What already works:
- The matcher reads an override before any alias, and an override digest is in the cache key.
- apply_decisions accepts any heading, replaces a changed decision, and refuses an id the taxonomy lacks before writing.
So a decision on an alias-placed heading already replaces it from the next run once the coach can see the heading. The work is the listing.

Proposal:
1. Shape: the queue's columns plus three. normalized_heading, answer, placed_by (alias | override | none), position (the current id; blank for none), documents, teams, aff_teams, neg_teams, cards, cards_inherited, cards_tag_names_another, candidate_positions, decision. No school, team, path, file or tag.
2. Its own file, <data dir>/landscape/review/<caselist>/<topic id>-placements.csv, written by the same run as the queue. The queue stays byte for byte as it is, so its own decisions behave exactly as before. The jobs differ: the queue is filled, and the listing is checked.
3. Command: none new. Every classification run (scripts/classify_landscape_positions.py classify and the report run) writes both files and prints the listing's location and row count beside the queue's. apply-decisions takes either file unchanged (it reads only normalized_heading and decision).
4. Applying: the same apply step and OverrideRules. A decision naming no taxonomy position is refused before anything is written, as today. A decision that only repeats an alias's own position is counted unchanged and written nowhere, so the overrides file holds corrections, not confirmations. One heading's reading and answer rows take one decision, as today (two different ones are refused).
5. "none" on a placed heading: keep today's rule. The heading is passed over, so its cards go to a heading above, else their tag keyword (0.5, the queue), else the queue, or are decided when every heading over them is ruled none. On today's counts that sends most of the cards to the queue (50,420 of 64,661), which is what "names no position" means. The guide will say so plainly.
6. Finer than a heading: not needed in V1.
   - The 450 tag-alone cards under headings that name nothing (188 ruled none, 262 no heading) are under the threshold. The report counts none of them, so a per-card correction would change no count.
   - The 82 tag-refined cards sit under 1 heading.
   - The 960 cards whose tags name another position are 1.5% of what is counted. They show up as the cards_tag_names_another column, so the coach can open those rows first.
   If the coach finds a heading right as a heading but wrong for some of its cards, that is a follow-up task.
7. Order: placed rows by cards, most first, then the none rows by cards. With 337 rows and 89% of the cards in the first 100, the coach reads from the top. The spreadsheet's sort by position or by cards_tag_names_another is the filter. No CLI filter is needed.

Scope: writing the file goes through the classification store (debate_core.integrations.landscape.classification_store), and the run's output line goes in scripts/classify_landscape_positions.py. Neither is in constraints.packages. The measurement script and its tests are in scripts/ and tests/scripts/, as t65's were. Please add debate_core.integrations and scripts to constraints.packages, or say which to leave out.

Reply with: a ruling on 1-7 (or changes), and the scope amendment.
```

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

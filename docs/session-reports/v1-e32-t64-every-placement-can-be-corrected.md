# Session report: v1-e32-t64-every-placement-can-be-corrected

| | |
|---|---|
| Task | `v1-e32-t64-every-placement-can-be-corrected` — The coach can correct any heading's placement, not only the headings the review queue lists |
| Spec | [`plan_specs/v1/e32-argument-landscape/t64-every-placement-can-be-corrected.yaml`](../../plan_specs/v1/e32-argument-landscape/t64-every-placement-can-be-corrected.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t64-every-placement-can-be-corrected` |
| Session status | COMPLETE: measured, ruled on by the PM, built as ruled; the Goal is Succeeded <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The coach can now correct any heading's placement. The ruling came after the measurement and before any listing
code.

* **The listing.** Every classification run writes a placements listing beside the review queue: every
  normalized heading that places cards, or that the coach ruled names no position. It has the queue's columns
  plus `placed_by`, `position`, `cards_inherited` and `cards_tag_names_another`, placed rows first, most cards
  first. At hspolicy26's 2026-11-03 snapshot it would hold 337 rows, where the queue holds 1,308.
* **The queue is unchanged**, byte for byte, pinned by a test committed alone before the change.
* **Correcting.** A decision written in the listing goes through the same apply step and becomes an override,
  which the matcher reads before any alias. So it replaces an alias's placement from the next run.
* **The safeguard the PM added.** `apply-decisions` now shows, for each changed decision, how many cards move
  where, and writes only with `--execute`.

What the PM should look at first:
* the apply step's new two-step command, which applies to the queue's decisions too (Deviation 2);
* the smoke check outside the packages the ruling added (Deviation 1).

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

### The PM's ruling (2026-11-25), as received

```text
PM ruling, v1-e32-t64, 2026-11-25.

1. Accepted: the queue's columns plus placed_by, position, cards_inherited and cards_tag_names_another. No school, team, path, file or tag.

2. Accepted: its own file, <data dir>/landscape/review/<caselist>/<topic id>-placements.csv, written by the same run as the queue. The queue stays byte for byte as it is, pinned by a test.

3. Accepted: no new command. Every classification run writes both files and prints the listing's location and row count beside the queue's. apply-decisions takes either file.

4. Accepted. A decision that repeats an alias's own position is counted unchanged and written nowhere. A decision naming no taxonomy position is refused before anything is written. Two different decisions for one heading's reading and answer rows are refused.

5. Accepted, with one safeguard. Keep today's rule for "none" on a placed heading. But one "none" on a large heading moves tens of thousands of cards: 50,420 of 64,661 on today's counts would go to the queue. So before anything is written, apply-decisions shows, for each decision that changes a placement, its heading and how many cards it moves where: to a heading above's position (same or other), to their tag keyword (the queue), to the queue, or decided. Follow the apply step's existing pattern: if it already has a dry run, the summary is the dry run's and writing needs the existing confirmation; if it has none, print the summary and write only with --execute. Test it, including a mutant that writes without the summary.

6. Accepted: nothing finer than a heading in V1. The cards_tag_names_another column is how the coach finds a heading that is right as a heading but wrong for some cards. Name that use in the guide. A per-card correction is a follow-up only if he finds one.

7. Accepted: placed rows by cards, most first, then the none rows by cards. No CLI filter.

Scope: debate_core.integrations, scripts and tests/scripts join constraints.packages. Record them as a Deviation citing this ruling; the PM amends the spec in the next batch.

The guide (the review section docs/guides/landscape-taxonomy.md or the queue's guide uses) says how to correct a placement, what "none" on a placed heading does, and that the summary shows the effect before anything is written.
```

## What was built after the ruling

* **The listing.** Every classification run now writes
  `<data dir>/landscape/review/<caselist>/<topic id>-placements.csv` beside the queue. That covers the classify
  script and `debate-research landscape report`; a dry run writes neither file. It has the queue's columns plus
  `placed_by`, `position`, `cards_inherited` and `cards_tag_names_another`. Placed rows come first, by cards,
  then the none rows, by cards. Rows under `minimum_teams` are left out and counted.
  * The classify script prints the listing's location, its rows (placed and ruled none) and the headings left
    out.
  * The report command prints `Placements listing: N rows (<path>).` and adds a `placements` key to its JSON.
* **The queue is unchanged**, byte for byte. The pin was committed alone first (`1d8fe86`) and passed on the
  pre-change code. It passes after the change too, including on the run after a placement is corrected.
* **The apply step.** `apply-decisions` takes either file, because the queue's reader reads only
  `normalized_heading` and `decision`. It now also takes `--caselist`, and optionally `--snapshot`,
  `--data-dir`, `--version` and `--threshold`. It runs in this order:
  1. It refuses a caselist that topics.yaml puts on another topic, then a decision naming no position of the
     taxonomy. Both happen before the store is read.
  2. It places the caselist's cards under today's rules and under the new ones, and prints one line per
     changed decision: the heading, what decided it before, what it names now, and where its cards go.
  3. Without `--execute` it ends `Dry run: nothing written.` With `--execute` it prints the same summary, then
     writes the overrides file.
* **Confirmations are not written.** A decision repeating an alias's own position is counted unchanged.
* **The guide.** `docs/guides/landscape-taxonomy.md`'s review section now has
  [Correcting a placement](../guides/landscape-taxonomy.md#correcting-a-placement):
  * the listing's columns and order, and how to find the wrong rows;
  * the use of `cards_tag_names_another`;
  * what each value written in `decision` does, `none` on a placed heading included;
  * the two-step apply, as two command blocks (working agreement 11).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `every-placement-can-be-corrected` (Correct a placement) | DONE | Measured, proposed, ruled on, then built as the ruling says. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal, with its counts, is ruled on by the PM before code | PASS | The operator's measurement of 2026-11-25 (39.1 s, `OK`) and the relay prompt above. The PM's ruling of 2026-11-25 is quoted above. Before the ruling the branch held only the measurement script, its tests and the report (`b91062b`, `6d87655`); the listing code starts at `1d8fe86`. |
| ac2: a decision on a heading an alias placed replaces that placement from the next run, and the review queue's own decisions behave as before, by tests on synthetic disclosures shown failing first | PASS | `test_placement_override_on_a_heading_an_alias_placed_replaces_it_next_run`: the alias-placed cards are `OVERRIDE`/`INHERITED` under the decision's position on the next run, and the queue's bytes are unchanged. The queue's own decision tests in `test_position_classification.py` and `test_classify_landscape_positions.py` pass, and so does the byte pin. The red run is below. |
| Node criterion: `uv run pytest packages/debate_core/tests -k "override or placement"` | PASS | 187 passed in 82.72 s (bounded with `scripts/hard_stop.py 115`). |
| Ruling 4: a decision naming no position is refused before anything is written | PASS | `test_placement_override_naming_no_position_on_an_alias_heading_is_refused`, `test_apply_decisions_refuses_a_decision_naming_no_position` (the overrides directory is never created). |
| Ruling 5: the summary before anything is written, `--execute` to write | PASS | `test_apply_decisions_without_execute_prints_the_summary_and_writes_nothing`, `test_apply_decisions_on_a_placed_heading_shows_where_its_cards_go`, `test_apply_decisions_writes_overrides_that_place_the_heading_next_run` (summary lines before `Applied`), and the planted breaks below. |

### Red run (tests against a skeleton that builds nothing and writes without the summary)

The skeleton:
* the placements module had its real types, with bodies that built nothing;
* `ClassificationRun` had empty defaults;
* `apply-decisions` accepted the new flags, wrote as before and printed no summary.

The run (`pytest test_placements.py test_position_classification.py test_classify_landscape_positions.py -n 0`):
17 failed, 60 passed. Every new test failed. 15 failed at an assertion on the empty listing or the missing
summary. Two failed by error, each because the skeleton never wrote the listing:
* the decision reader refused an empty file ("a decisions file is a review queue CSV");
* the service test read the empty location as a directory.

The queue's own tests and the byte pin passed throughout.

### Planted breaks (one at a time, each restored from HEAD; the three test files above)

| Break | Result |
|---|---|
| An alias wins over the coach's decision (the matcher reads the alias first on an alias heading) | Caught: 4 failed, including the next-run test (`('spending-da', 'ALIAS', 1.0)` where the decision's `states-cp` was expected) |
| The `minimum_teams` rule dropped from the listing | Caught: 5 failed (the hand-written listing, the left-out count, the service's bytes, the classify line) |
| The dry run writes without `--execute` | Caught: 2 failed |
| `--execute` writes without the summary | Caught: 1 failed (`test_apply_decisions_writes_overrides_that_place_the_heading_next_run`) |
| A repeat of an alias's own position is written | Caught: 2 failed |
| A change counted under the outermost changed heading, not the nearest | Survived the first run: no planted card sat under two changed headings. `test_placement_changes_count_a_card_under_the_nearest_changed_heading` was added (`3d11108`), and the break then failed it |
| A none row counts cards a nearer heading places | Caught: 1 failed |
| A tag naming the placement's own line counts as another position | Caught: 1 failed |
| None rows sorted among the placed rows | Caught: 2 failed |

Every failure was at an assertion. The measurement script's five breaks before the ruling were also each
caught (see above).

## Checks run (2026-11-25)

* **Affected set.** `uv run scripts/affected_tests.py --run --slow` chose 341 test files. Bounded with
  `scripts/hard_stop.py 115`, it stopped at its limit at 51%, with no failure printed. It is over two minutes,
  so it is left to the pull request's `ci` (agreement 10).
* **Within the bound instead:**
  * the test directories of what changed: `debate_core` `arguments/landscape`, `integrations/landscape`, and
    the landscape run and classification tests under `application`, with both script test files. 1635 passed
    in 5.18 s.
  * the always-run list (`tests/architecture`, `tests/specs`, the CLI's wiring tests), with
    `packages/debate_cli/tests/test_landscape_command.py` and `tests/smoke/test_landscape_smoke.py`. 520 passed
    in 28.69 s.
* **Linters and checks:**
  * `ruff format --check .`: 2160 files already formatted;
  * `ruff check .`: clean;
  * `pyright` (whole project): 0 errors;
  * `lint-imports`: 20 kept, 0 broken;
  * `scripts/check_thin_handlers.py`: OK;
  * `scripts/check_links.py`: OK;
  * `scripts/docs_index.py --check-descriptions`: OK;
  * `scripts/check_command_blocks.py --base origin/dev`: OK;
  * `scripts/validate_specs.py`: OK, 690 files.
* **The spec against `origin/dev`** (fetched 2026-11-25): it matches apart from the phase.

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/placements.py` (new): the listing (rows, counts,
  CSV) and the apply step's summary (`placement_changes`). Pure.
* `arguments/landscape/matcher.py`: public `heading_placement`, `heading_rule`, `ruled_none` and `lineage`
  (cached), so the listing reads the matcher's own rule rather than repeating it.
* `arguments/landscape/review_queue.py`: `apply_decisions` counts a repeat of an alias's position unchanged and
  returns the headings whose rule changed.
* `application/position_classification.py`, `application/ports/classification_store.py`,
  `application/landscape_run.py`: the service builds and writes the listing through a new
  `ClassificationStore.write_placements`. A dry run's read-only store writes nothing.
* `integrations/landscape/classification_store.py`: `write_placements` and `placements_path`.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: the report's `placements` JSON key and its line.
* `scripts/classify_landscape_positions.py`: the listing line in `classify`, and `apply-decisions`' summary and
  `--execute`.
* `scripts/count_heading_placements.py` (new): the measurement, counts only.
* Tests:
  * `packages/debate_core/tests/arguments/landscape/test_placements.py` (new);
  * new tests and the queue's byte pin in `packages/debate_core/tests/application/test_position_classification.py`;
  * the new apply flow in `tests/scripts/test_classify_landscape_positions.py`;
  * `tests/scripts/test_count_heading_placements.py` (new);
  * `packages/debate_cli/tests/test_landscape_command.py`;
  * `tests/smoke/test_landscape_smoke.py`.
* `docs/guides/landscape-taxonomy.md`: correcting a placement, and the two-step apply.
* The task spec: the Goal set Succeeded.

## Deviations from the spec

1. **Packages outside `constraints.packages`.** The PM's ruling of 2026-11-25 adds `debate_core.integrations`,
   `scripts` and `tests/scripts` to the packages and amends the spec in the next batch; this session did not
   edit the constraint. One more path is outside both the spec and the ruling: `tests/smoke/test_landscape_smoke.py`.
   It checks that the report run writes the listing with headings and counts only. Working agreement 5 asks for
   a smoke check on a changed user-facing surface. It is the PM's to confirm.
2. **apply-decisions' command changed for the queue too.** The apply step had no dry run, so, as the ruling
   says, it now writes only with `--execute`, and it needs `--caselist` to count cards. This holds for a filled
   review queue as for the listing. What a queue decision does is unchanged, and its tests pass. The guide's
   single apply block is now two.
3. **The measurement's snapshot** is this Mac's store at 2026-11-03, parsed at `2026.10.27-docx-7`, not the
   newest hspolicy26 snapshot the spec names. The PM's context of 2026-11-25 asked for it, as `v1-e32-t65` used.

## Decisions and assumptions

* **A row's `position`** is the placing heading's own position. A card that its tag moves to a child of that
  position is still counted in the row; there are 82 such cards on hspolicy26, all under 1 heading.
* **`cards_tag_names_another`** counts a card whose tag holds a keyword of a position outside the line of the
  card's own placement (the position, its ancestors and its descendants). A tag naming the row's child is
  therefore not "another".
* **Candidates on a placed row** leave out the row's own position. So after a correction, the alias's old
  position shows as a candidate (`spending da` → `states-cp` lists `spending-da`).
* **The summary counts cards only**, not sections, and puts each moved card under the nearest heading over it
  whose decision changed. A decision that moves no card in that caselist is counted on one line. Its wording is
  "under a heading above, the same position" / "another position", "to their tag keyword (the queue)", "to the
  queue", and "decided (every heading over them ruled none)".
* **Order of refusals in apply-decisions:** first the caselist's topic, then the decisions file and its ids.
  The store is read only after both, so a typo is refused in seconds rather than after a 40-second read.
* **A decision that names a position for a heading already decided by an override with the alias's own
  position** replaces the override, as any changed decision does; only a heading no override decides is
  "confirmed" and not written.

## Operator follow-ups

None outstanding. The one run done is listed for the record. It ran from the task worktree, with the check that no
`DEBATE_` variable was set, and wrote counts-only JSON to the session's scratchpad:

```bash
uv run python scripts/count_heading_placements.py --snapshot 2026-11-03 --caselist hspolicy26
```

Once this merges, the coach's next pass of decisions is applied in two steps, as the guide says: the dry run
first, then the same command with `--execute`.

## Follow-up work

* **Per-card corrections:** none built, by the ruling (6). A task only if the coach finds a heading that is right
  as a heading but wrong for some of its cards, through `cards_tag_names_another`.
* **The spec amendment** the ruling names: `debate_core.integrations`, `scripts`, `tests/scripts` (and, if the PM
  agrees, `tests/smoke`) in `constraints.packages`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-25

**Notes:**

Accepted. ac1, ac2, the node criterion and rulings 4 and 5 pass, and the Goal is `Succeeded`.

* **The order was kept.** The measurement and its report came before the ruling (`b91062b`, `6d87655`),
  and the listing code starts at `1d8fe86`, the queue's byte pin committed alone and passing on the
  pre-change code.
* **The measurement reconciles.**
  * The ten placement classes sum to the 126,681 cards read.
  * The `none` simulation's four outcomes sum to the 64,661 placed cards.
  * The listed placed rows' 64,526 cards plus the 135 left out are the same 64,661.
  * 292 placed rows plus 45 none rows make the 337-row listing.
  * The tags naming another position, 910 plus 50, are the relay's 960 in 122 rows.
  * One count is not explained: `cards_inherited` on the listed alias rows is 21,173, against 21,094
    cards `INHERITED` from an alias. It is consistent with the 82 tag-refined cards being counted as
    inherited, less 3 left out. Not blocking: the column's rule is tested on hand-counted plants. A later
    session touching the listing states it.
* **Built as ruled, 1 to 7.** The listing's columns, its own file, no new command, confirmations not
  written, refusals before the store is read, and the summary with `--execute`.
* **The evidence.**
  * Red run: 17 failed, 15 at an assertion. The 2 errors come from the skeleton writing no listing, and
    the report says so.
  * Planted breaks: 9. Eight were caught the first time. The survivor, the nearest-heading rule, got a
    new test (`3d11108`), which then caught it.
  * The ruling's mutant (`--execute` writing without the summary) is among them, and caught.
* **Deviations accepted.**
  * **1:** the packages per the ruling, and `tests/smoke` too, since working agreement 5 asks for the
    smoke check. All four go in the next batch's amendment.
  * **2:** the queue's apply now takes `--caselist` and writes only with `--execute`. That is the
    ruling's pattern, since the step had no dry run. The guide carries both blocks. No other doc gives a
    stale one-step command: `first-run-policy.md` is a historical record, and `v1-e32-t05` is Succeeded.
  * **3:** the 2026-11-03 snapshot, as the PM's context asked.
* **The checks.** The affected set stopped at 51% of its 115-second bound with no failure, so the pull
  request's `ci` is the full run (agreement 10). **Merge only on a green `ci`.**
* **Follow-ups.** Per-card corrections are filed only if the coach finds a heading that is right as a
  heading but wrong for some of its cards.

`scripts/task pr`

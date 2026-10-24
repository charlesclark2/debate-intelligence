<!-- docs-index: Counts from the first Policy argument landscape reports on hspolicy26 (`v1-e32-t05`): classification coverage, review queue and scan; aggregates only -->
# First Policy landscape run: hspolicy26

The first argument landscape reports for the Policy team's 2026-27 national health insurance topic,
from the hspolicy26 store (`v1-e32-t05-landscape-cli` ac5). The team first competes on 2026-11-07.

**Aggregate numbers only.** Nothing here names a school, team code, tournament, file, tag, cite or
person, as the data-use policy requires of `docs/data/`. The scan's hits are counted by kind; the
words themselves stay in the operator's terminal and the local acceptance log.

**Classification coverage** is given two ways, as the report's header gives it:

* **by cards**: the cards placed under a position at or above the review threshold, over every card
  of the topic's sources through the snapshot;
* **by rounds**: the disclosed rounds in which at least one card reads a position, over every round.

## Before the coach's pass over the review queue

Measured by the session on 2026-10-24, read-only, on the operator's Mac: no `DEBATE_*` variable was
set, no `caselist pull` was running, and the classification cache and the review queue had the same
checksums after as before. Snapshot 2026-10-20, taxonomy 1.0.0, overrides digest `none`, parser
`2026.10.20-docx-6`, prompt version `none`, model calls 0.

### From `landscape report --dry-run`

The command itself, without `--publish`, so no bucket was asked and nothing was written. 46 s.

| Count | Value |
|---|---|
| Sources on the topic; cards | 3,825; 126,681 |
| Cards by method | ALIAS 39,196; INHERITED 21,791; unplaced 65,694 |
| **Classification coverage by cards** | **60,987 of 126,681 (48.1%)** |
| Rounds; teams | 4,352 rounds by 567 teams |
| **Classification coverage by rounds** | **2,201 of 4,352 (50.6%)** |
| Affirmative rounds with no identified aff | 1,998 of 2,192 (91.1%) |
| Negative rounds with no placed negative position | 1,389 of 2,160 (64.3%) |
| Position-rounds set aside as answers (other side) | 4,734 |
| Positions read; top-card rows | 68; 318 |
| Review queue | 1,433 rows |
| Cache | 107,203 keys looked up, all hits; nothing written |
| Staleness | newest snapshot 2026-10-20, 4 days old, 0 archives awaiting download: current |
| Scan before sharing | 6 hits, all in `top_cards.csv`: 3 school names, 2 team codes, 1 tournament. None in `report.md` or `positions.csv` |
| Planned keys | `reports/landscape/hspolicy26/2026-10-20/` `positions.csv`, `top_cards.csv`, `report.md` |

These are the numbers `v1-e32-t03`'s preview recorded for the same snapshot, so the command builds
the report the preview did.

### Coverage by side and kind

`v1-e32-t02`'s measure, from its cache, with the same rules: a document is affirmative (or negative)
when a live disclosure of it is on that side; it has a kind when one of its cards reads a position of
that kind at or above the threshold; a team counts when any of its documents on that side does.
34.6 s.

| Side and kind | Documents | Share | Teams | Share |
|---|---|---|---|---|
| Aff: all | 1,770 | | 552 | |
| Aff: aff | 159 | 9.0% | 77 | 13.9% |
| Aff: advantage | 1,129 | 63.8% | 365 | 66.1% |
| Aff: either | 1,168 | 66.0% | 378 | 68.5% |
| Neg: all | 2,070 | | 392 | |
| Neg: da | 562 | 27.1% | 155 | 39.5% |
| Neg: cp | 322 | 15.6% | 122 | 31.1% |
| Neg: k | 151 | 7.3% | 67 | 17.1% |
| Neg: t | 138 | 6.7% | 65 | 16.6% |
| Neg: theory | 24 | 1.2% | 17 | 4.3% |
| Neg: any of the five | 742 | 35.8% | 183 | 46.7% |

## After the coach's pass over the review queue

Not yet measured: it waits on the coach's filled sheet of the queue's top 50 headings.

## The first dev run

Not yet run. It is the operator's, after the merge: a dry run, then the publish with the scan's
digest once the hits are read (the session report's operator follow-ups).

## The coach's review

Not yet given.

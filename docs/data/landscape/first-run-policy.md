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

The coach filled the queue's top 50 headings on 2026-10-24. Under the PM's rulings of that day:
* **seven positions were added from it:**
  * three DAs and two advantages in the topic's taxonomy, now 1.1.0;
  * a generic K and one generic theory position in `generic.yaml`, now 1.1.0 (Policy only);
  * each takes the queue headings the coach placed under it as aliases. The topic stays at the
    unreleased 1.1.0;
* **45 of the 50 decisions were applied** with `v1-e32-t02`'s `apply-decisions`: 30 `none` and 15
  position ids. One is `uq`, "uniqueness" as the coach confirmed, which the configuration's
  personal-data check first refused as shaped like a team code.

Five headings are not decided yet:
* two the coach flagged as possibly naming a school or tournament;
* two he left blank;
* one read on both sides, as an advantage and as a DA.

Measured by the session the same day: read-only, by the same rules as above, with every card placed
in memory (the version bump changes every cache key) and the cache's checksum unchanged. 38.0 s and
34.5 s. The last column also includes `v1-e32-t09`'s change to the heading normalizer, which strips
an advantage's number before its name. That change alone places 32 more cards and adds 3 aff
documents with a placed advantage.

| Count | Before (1.0.0, no decisions) | 1.1.0, no decisions | **After the pass** |
|---|---|---|---|
| **Classification coverage by cards** | 60,987 (48.1%) | 61,735 (48.7%) | **63,494 (50.1%)** |
| Aff documents with a placed aff | 159 (9.0%) | 159 (9.0%) | 156 (8.8%) |
| Aff documents with a placed advantage | 1,129 (63.8%) | 1,145 (64.7%) | 1,164 (65.8%) |
| Aff documents with either | 1,168 (66.0%) | 1,184 (66.9%) | 1,202 (67.9%) |
| Aff teams with either | 378 (68.5%) | 380 (68.8%) | 384 (69.6%) |
| Neg documents with a placed da | 562 (27.1%) | 632 (30.5%) | 662 (32.0%) |
| Neg documents with a placed cp | 322 (15.6%) | 322 (15.6%) | 322 (15.6%) |
| Neg documents with a placed k | 151 (7.3%) | 151 (7.3%) | 163 (7.9%) |
| Neg documents with a placed t | 138 (6.7%) | 138 (6.7%) | 138 (6.7%) |
| Neg documents with a placed theory position | 24 (1.2%) | 24 (1.2%) | 83 (4.0%) |
| Neg documents with any of the five | 742 (35.8%) | 804 (38.8%) | 877 (42.4%) |
| Neg teams with any of the five | 183 (46.7%) | 211 (53.8%) | 231 (58.9%) |

The shares are of 1,770 affirmative and 2,070 negative documents. The "1.1.0, no decisions" column
has the topic's five new positions and not yet the two generic ones. Classification coverage by
rounds is the report header's, from the first dev run below.

**The coach's decision on `framework`: it names no position.** He first placed it under framework
T. Under a K's own block, though, "framework" is the K's framework, so a measurement with that
decision moved 96 cards from Ks to T. He then chose `none`, and those cards stay with the K:

| | Before | With framework T | With `none` (as applied) |
|---|---|---|---|
| Neg documents with a placed k | 151 | 145 | 151 |
| Neg documents with a placed t | 138 | 209 | 138 |

Both are before the generic K was added, which takes K documents to 163.

**Three aff documents lose their placed aff.** No decision takes a placement away from a card, but
a decided heading lower on a card's path wins over an alias above it. So cards under an advantage
heading inside a plan's block move from the aff to the advantage, since advantages stand alone in
this taxonomy.

**The overrides digest** the report's header names is
`e1c2367c363ef95718cddb8aa5f59a138013b410386fcb91552102cc95f60ca5`. The bump invalidates
`v1-e32-t02`'s cache, so the first run under 1.1.0 classifies every card again. `v1-e32-t09`'s
plan-text cache stays valid: the pass added no aff position, so its vocabulary digest is unchanged.
All 1,770 affirmative documents are cached under it.

### The report as the first run will build it

The command's own dry run after the pass, with `v1-e32-t09`'s aff assignments wired in: read-only,
without `--publish`, 42 s. The classification cache, the plan-text cache and the review queue had
the same checksums after it.

| Count | Before the pass | After the pass, with the affs |
|---|---|---|
| **Classification coverage by cards** | 60,987 of 126,681 (48.1%) | 63,494 (50.1%) |
| **Classification coverage by rounds** | 2,201 of 4,352 (50.6%) | **2,622 (60.2%)** |
| Affirmative rounds with no identified aff | 1,998 of 2,192 (91.1%) | **940 (42.9%)** |
| How affirmative rounds are identified | placed card 194 | plan text 959, team carry 226, placed card 67 |
| Negative rounds with no placed negative position | 1,389 of 2,160 (64.3%) | 1,238 (57.3%) |
| Position-rounds set aside as answers | 4,734 | 4,965 |
| Positions read; top-card rows | 68; 318 | 75; 353 |
| Review queue | 1,433 rows | 1,340 rows |
| Scan before sharing | 6 hits in `top_cards.csv` | 6 hits in `top_cards.csv`: 3 school names, 2 team codes, 1 tournament |

## The first dev run

Not yet run. It is the operator's, after the merge: a dry run, then the publish with the scan's
digest once the hits are read (the session report's operator follow-ups).

## The coach's review

Not yet given.

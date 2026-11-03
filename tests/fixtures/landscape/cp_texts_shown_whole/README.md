# CP texts shown whole

The inputs `v1-e32-t35-cp-texts-shown-whole` is tested against: invented States CP blocks in seven
negative files of the synthetic caselist (`../synthetic_caselist`), read by the analytic-text reader
itself (not written as readings by hand). Every text here is invented. The file names are the synthetic
caselist's negative files, so their rounds and teams are its own: `b1` is YY's and JJ's, `b2` QQ's, `b3`
and `b6` WW's, `b4` YY's, `b5` ZZ's and `b8` KK's, all on the negative and in range through 2026-09-15.
`report_section.md` is what report.md's "Counterplan texts" part should say, **written by hand from the
tables below** (working agreement 6), never by running the report.

## Files

| File | What it holds |
|---|---|
| `sources.yaml` | Each file's paragraphs (element index, unit, text), the CP texts' actors and the heading decision placing `States CP` |
| `report_section.md` | The "Counterplan texts" part of report.md, by hand |

A heading (`POCKET`, `HAT`, `BLOCK`) is over every paragraph after it until a heading of its level or
above. A `TAG` and the `EVIDENCE` after it are a card the store keeps. Every CP text is a block's first
`should` analytic.

## The rule (the PM's review of 2026-10-31)

CP texts are grouped and ranked by their opening paragraph's words, by the distinct teams reading it. A
group shows its commonest whole text: the one the most of the group's teams read word for word, the first
by source and paragraph on a tie. A whole text naming a school of the caselist, in any line, is passed over
for the next. The row says how many of the group's teams read the text shown when its planks are shown.

## The texts, by group

**The fifty states and all relevant territories should**, opening 9 copies, read by 6 teams (YY, JJ, QQ,
WW, ZZ, KK). Its whole texts:

| Whole text | Copies | Teams |
|---|---|---|
| The opening with a colon, then two list planks (clinics, prize) | b1, b2 | YY, JJ, QQ: 3 |
| The opening with a colon, then the clinics plank and a plank naming `Birchmoor`, a school of the caselist | b3, b4, b5, b8 | WW, YY, ZZ, KK: 4 |
| The opening at a bare `should`, continued by the two planks as `- ...` analytics | b3 (second block), b6 (two blocks) | WW: 1 |

The 4-team text names a school, so it is passed over and counted withheld. The text shown is the 3-team
one, with its two planks: "6 teams, 3 with these planks". The 1-team text has the most copies but the
fewest teams, so it is not shown.

**Congress should fund sample clinics.**: b4's and b8's second blocks, YY and KK, 2 teams. It has no
lines.

So the States CP shows two rows: rank 1 with 6 teams (3 reading the planks shown), and rank 2 with 2
teams. Found: 11 CP texts in 7 files, all 11 counted, none unplaced, elsewhere, left out by the actor
guard or unread, and 1 text withheld for naming a school.

## What each part tells apart

* **The planks dropped** (a colon text keeps no lines): the six colon copies are the opening alone, read
  by all 6 teams, and that is the text shown, with no planks.
* **A plank naming a school shown** (the school check on the first line only): the 4-team text is
  shown, with `Birchmoor`.
* **Grouping on the whole text**: the colon list and the dash continuation have the same words, so they
  are one group of 4 teams (YY, JJ, QQ, WW), and rank 1 says 4 teams; the named text's group is withheld.
* **The text shown chosen by copies, not teams**: once the named text is passed over, the 3-copy,
  1-team text is shown.
* **No fall-through** (a group withheld when its commonest whole text names a school): only the
  Congress text is shown.
* **The read-back checked on the opening only** is not seen here, since every file reads back as it was
  read: the unit tests change a plank between the reading and the read-back.

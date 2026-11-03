# The kritikal-affirmatives caselist

The inputs `v1-e32-t17-kritikal-affirmatives` is tested against: eight invented rounds of
`synthpolicy26` on 2026-09-15, with `v1-e32-t09`'s and this task's assignments given beside them, the
files holding a K-aff marker, the K families each file's headings name, and the round the advantage
guard refused. Every school, team code, tournament and position here is synthetic, and no file holds a
tag, cite, card text or advocacy statement: a card is only the position `v1-e32-t02` placed it under,
and a marker only the fact that a file holds one. `report_section.md` is what report.md's "Kritikal
affirmatives" section should say, and `method_table.md` the identification table under "Unclassified",
**written by hand from the table below** (working agreement 6), never by running the report.

## Files

| File | What it holds |
|---|---|
| `taxonomy.yaml` | Single payer, Kritikal affirmative, an advantage and a K |
| `rounds.yaml` | The schools, the eight rounds (team, side, tournament, round, files, assigned aff and method, or the advantage guard's refusal), each file's placed cards, and the K-aff inputs: the position, the families' labels in the config's order, the marker files and each file's heading families |
| `report_section.md`, `method_table.md` | The section and the table, by hand |

A card listed by its position alone is READS, `ALIAS`, confidence 1.0. A file `c1` is the digest
`c1c1…c1`.

## The rounds

| Round | Files | Marker files | Heading families | Assigned | What it counts as |
|---|---|---|---|---|---|
| AA, Fictional Invitational R1 | c1 | c1 | c1: cap, settler colonialism | Kritikal affirmative, `KRITIKAL_AFF_MARKER` | a K aff by its own marker |
| AA, Imaginary Classic R1 | c2 | | c2: cap | Kritikal affirmative, `KRITIKAL_AFF_CARRY` | a K aff by carry |
| AA, Pretend Open R1 | c3 (costs) | | c3: queer | none: the advantage guard refused the carry | unidentified, refused |
| BB, Fictional Invitational R1 | c4 (costs), c5 | c4 | c4: afropessimism; c5: cap | Kritikal affirmative, `KRITIKAL_AFF_MARKER` | a K aff by its own marker, reading an advantage |
| CC, Fictional Invitational R1 | d1 | d1 | | Single payer, `PLAN_TEXT` | the control |
| DD, Fictional Invitational R1 | d2 | | d2: feminism | none | unidentified |
| EE, Fictional Invitational R1 | e1 (single payer) | e1 | | none: a placed Single payer card | `PLACED_CARD`; the control |
| EE, Imaginary Classic R1, negative | f1 (cap K) | f1 | | | not an affirmative round: counted nowhere |

## What each part exercises, counted by hand

* **The group:** the K-aff rounds are AA's first two and BB's: **3 rounds by 2 teams**, 2 by a marker
  in their own file (AA Fictional, BB) and 1 by carry (AA Imaginary).
* **The advantage guard:** AA's Pretend Open round was refused, **1 round**. It stays unidentified.
  BB's round reads an advantage too, but by its own marker, which the guard does not touch.
* **The families** count only the K-aff rounds' files, c1, c2, c4 and c5, and only their headings:
  * cap in c1, c2 (AA) and c5 (BB): **3 files, 2 teams**;
  * settler colonialism in c1 (AA): 1 file, 1 team;
  * afropessimism in c4 (BB): 1 file, 1 team.

  The order is files, then teams, then the config's order, so settler colonialism, listed before
  afropessimism, comes first of the two tied. c3's queer and d2's feminism are in files of rounds that
  are not K affs, and are not counted.
* **Still unidentified:** of the **7 affirmative rounds**, 5 are identified (AA's first two, BB, CC by
  plan text, EE by a placed card). **2 are not** (AA Pretend Open, DD): 28.6%.
* **The method table:** `KRITIKAL_AFF_CARRY` 1, `KRITIKAL_AFF_MARKER` 2, `PLACED_CARD` 1, `PLAN_TEXT`
  1, in method order, then Not identified 2, of which refused by the advantage guard 1.
* **The control:** marker files in affirmative rounds another method identifies: d1 (CC's plan-text
  round) and e1 (EE's placed-card round), **2 files in 2 rounds**. c1 and c4 are K affs, so they are
  not the control, and f1 is in a negative round.

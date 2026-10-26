# The transition-plan caselist

The inputs `v1-e32-t24-unlabelled-plan-affs` is tested against: thirteen invented affirmative rounds of
`synthpolicy26` on 2026-09-15 and one negative round. For each file the fixture gives what the readers
found, never a word of it:
* `v1-e32-t09`'s verdict over its own plan texts;
* this task's verdict over its plan texts under `Thus the plan`, `Thus plan` or `Thus`;
* whether it holds a K-aff marker (`v1-e32-t17`);
* the positions its cards were placed under.

The real assignment (`build_aff_assignments`) runs over them, and the report counts what it assigns.
`method_table.md` is the identification table under "Unclassified", **written by hand from the table
below** (working agreement 6), never by running the report.

Every school, team code, tournament and position here is synthetic. No file holds a tag, cite, card
text or plan text: a verdict stands for what a plan text named.

## Files

| File | What it holds |
|---|---|
| `taxonomy.yaml` | Single payer with its Global budgets mechanism, Public option, Kritikal affirmative, an advantage and a K |
| `rounds.yaml` | The schools, the rounds (team, side, tournament, round, files), and per file: t09's verdict (`t09`), the transition verdict (`thus`), a marker (`marker`) and its placed cards (`cards`) |
| `method_table.md` | The table, by hand |

A verdict is `NONE`, `UNNAMED`, `CONFLICTING`, or the aff id it names. A file the fixture gives no `thus`
holds no plan text under a transition label. A card is READS, `ALIAS`, confidence 1.0. A file `a1` is
the digest `a1a1…a1`.

## The rounds

| Round | Files: t09, thus | Marker | Cards | Assigned | Why |
|---|---|---|---|---|---|
| AA, Fictional Invitational R1 | a1: NONE | a1 | | Kritikal affirmative, `KRITIKAL_AFF_MARKER` | its own marker |
| AA, Imaginary Classic R1 | a2: NONE, single payer | | | Single payer, `TRANSITION_PLAN_TEXT` | the K-aff carry is refused, because its own file's plan text under `Thus` names a policy aff; it then falls to that plan text |
| AA, Pretend Open R1 | a3: NONE | | | Kritikal affirmative, `KRITIKAL_AFF_CARRY` | AA's carry, as t17's |
| AA, Make-Believe Cup R1 | a4: NONE, single payer | | costs advantage | Single payer, `TRANSITION_PLAN_TEXT` | the K-aff carry is refused by the advantage guard first, so it counts there, not as a transition refusal |
| BB, Fictional Invitational R1 | b1: NONE, global budgets | | | Global budgets, `TRANSITION_PLAN_TEXT` | its plan text under `Thus` |
| BB, Imaginary Classic R1 | b2: NONE | | | Global budgets, `TRANSITION_PLAN_CARRY` | BB's carry: no plan text of its own |
| BB, Pretend Open R1 | b3: NONE, UNNAMED | | | none | BB's carry refused: its own plan text under `Thus` names nothing |
| CC, Fictional Invitational R1 | c1: public option | | | Public option, `PLAN_TEXT` | t09 |
| CC, Imaginary Classic R1 | c2: NONE, single payer | | | Public option, `TEAM_CARRY` | t09's carry stays; the control |
| DD, Fictional Invitational R1 | d1: NONE, single payer; d2: NONE, public option | | | none | the two files name two affs: a conflict |
| EE, Fictional Invitational R1 | e1: UNNAMED; e2: NONE, single payer | | | none | never into a round whose own file holds a plan text t09 reads |
| FF, Fictional Invitational R1 | f1: NONE, public option | f1 | | Kritikal affirmative, `KRITIKAL_AFF_MARKER` | its own marker stays; the control |
| HH, Fictional Invitational R1 | 01: public option; 02: NONE, single payer | | | Public option, `PLAN_TEXT` | t09's plan text names another aff, and wins; the control |
| HH, Imaginary Classic R1, negative | 03: NONE, single payer | | cap K | | not an affirmative round: counted nowhere |

## What each part exercises, counted by hand

* **The rounds:** 13 affirmative rounds by 7 teams.
* **By method, in method order:**
  * `KRITIKAL_AFF_CARRY` 1 (AA Pretend Open);
  * `KRITIKAL_AFF_MARKER` 2 (AA Fictional, FF);
  * `PLAN_TEXT` 2 (CC Fictional, HH);
  * `TEAM_CARRY` 1 (CC Imaginary);
  * `TRANSITION_PLAN_CARRY` 1 (BB Imaginary);
  * `TRANSITION_PLAN_TEXT` 3 (AA Imaginary, AA Make-Believe, BB Fictional).

  So 10 are identified. **3 are not:** BB Pretend Open, DD and EE.
* **t17's advantage row** counts the rounds the advantage guard refused that are still unidentified. AA
  Make-Believe was refused, but its own plan text identifies it, so the row is **0**.
* **t17's marker control:** the marker files a1 and f1 are both in K-aff rounds, so it is **0 files in 0
  rounds**.
* **The refused K-aff carries:** AA Imaginary, **1 round**. AA Make-Believe counts under the advantage
  guard instead.
* **The control:** rounds another method identifies whose own file holds a plan text under `Thus`
  naming another aff. That is CC Imaginary (`TEAM_CARRY`), FF (`KRITIKAL_AFF_MARKER`) and HH
  (`PLAN_TEXT`): **3 rounds**, 1 each. The negative round is not counted.

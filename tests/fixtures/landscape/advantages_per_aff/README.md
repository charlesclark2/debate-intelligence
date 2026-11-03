# The advantages-per-aff caselist

The inputs `v1-e32-t15-advantages-per-aff` is tested against: twelve invented rounds of
`synthpolicy26` on 2026-09-15, with `v1-e32-t09`'s assignments given beside them. Every school,
team code, tournament and position here is synthetic, and no file holds a tag, cite or card text: a
card is only the position `v1-e32-t02` placed it under. `report_section.md` is what report.md's
"Advantages by affirmative" section should say, **written by hand from the table below**
(working agreement 6), never by running the report.

## Files

| File | What it holds |
|---|---|
| `taxonomy.yaml` | Single payer with two mechanisms (Global budgets, Nanomedicine coverage), Public option, Vouchers, seven advantages and a DA |
| `rounds.yaml` | The schools, the twelve rounds (team, side, tournament, round, files, assigned aff and method) and each file's placed cards |
| `report_section.md` | The section, by hand |

A card listed by its position alone is READS, `ALIAS`, confidence 1.0. A file `a1` is the digest
`a1a1…a1`.

## The rounds, and what each counts under

| Round | Files | Assigned | Advantages read |
|---|---|---|---|
| XX, Fictional Invitational R1 | a1 | Single payer | costs, coverage, disease (pandemics only answered) |
| XX, Imaginary Classic R1 | a2 | Global budgets | costs, budgets |
| YY, Fictional Invitational R1 | a3 | Single payer | costs, coverage, inequality, innovation, pandemics |
| ZZ, Fictional Invitational R1 | a4 | Global budgets | costs, budgets |
| QQ, Fictional Invitational R1 | a5, a9 | Single payer | disease (a5), coverage (a9) |
| QQ, Imaginary Classic R1 | a6 | Public option | innovation, pandemics (budgets below the threshold) |
| VV, Fictional Invitational R1 | a7 | Nanomedicine coverage | none |
| WW, Fictional Invitational R1 | a8 | Vouchers | none |
| JJ, Fictional Invitational R1 | aa | none: a placed Public option card | coverage, costs |
| KK, Fictional Invitational R1 | ab | none | costs |
| KK, Imaginary Classic R1 | ac | none | disease |
| WW, Imaginary Classic R1, negative | b1 | | none: its costs card is on the other side |

## What each part exercises

* **A mechanism's rounds count under it and once under its aff.** Single payer's section has its own
  three rounds, Global budgets' two and Nanomedicine's one: 6 rounds by 5 teams (XX, YY, ZZ, QQ, VV),
  4 of them reading an advantage. XX reads costs under Single payer itself (a1) and under Global
  budgets (a2), and is one of costs' 3 teams there (XX, YY, ZZ), not two.
* **The ranking.** Under Single payer: costs 3 and coverage 3 (XX, YY, QQ), then budgets 2 (XX, ZZ)
  and disease 2 (XX, QQ), then inequality, innovation and pandemics, 1 each (YY). Ties go by id.
* **The cut-off.** The top 5 are shown. Innovation and pandemics are the 2 more, read by 1 team: YY
  reads both, so the distinct teams are 1 where a sum would say 2. With a cut-off of 3, disease,
  inequality, innovation and pandemics are the 4 more, read by 3 teams (XX, QQ, YY), not 5.
* **Another aff's round is never counted.** QQ reads innovation and pandemics in its Public option
  round. Under Single payer they stay YY's alone, and Public option shows neither QQ's disease nor its
  coverage, which QQ read in its Single payer round.
* **Nothing is taken from an advantage's taxonomy parent.** `costs-advantage` names Public option as
  its parent, and Public option's round reads no costs card, so costs is not under it.
* **A mechanism and an aff with no advantage read** go in one closing line, with their rounds:
  Nanomedicine coverage (1 round) and Vouchers (1 round). Neither has a section.
* **The reads with no assigned aff.** JJ's round (coverage, costs) and KK's two (costs; disease): 4
  advantage reads in 3 affirmative rounds, by 2 teams. A placed card identifies JJ's round's aff
  (Public option), and its advantages still count here, not under Public option.
* **What is not a read**, as in `v1-e32-t03`: a1's pandemics card ANSWERS, a6's budgets card is
  placed below the review threshold (0.5), and b1's costs card is in a negative round.
* **The order.** Affs by their teams, then rounds, then id: Single payer (5 teams), then Public option
  and Vouchers (1 team and 1 round each), Public option first by id. A mechanism follows its aff, in
  the same order: Global budgets (2 teams), then Nanomedicine coverage (1).

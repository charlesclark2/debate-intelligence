# The synthetic caselist with a coach's scenario list (`v1-e32-t22`)

The synthetic three-snapshot caselist (`../synthetic_caselist/`, read unchanged) with one scenario
list added to its taxonomy: [`scenarios.yaml`](scenarios.yaml) gives the Costs advantage two forms
merged under one name and one form dropped as no scenario. Every other position has no list and keeps
`v1-e32-t14`'s rule. The taxonomy's version is unchanged, so every header line is as in
`../golden/`.

| File | What it holds |
|---|---|
| `scenarios.yaml` | The list, by position id, as a topic's taxonomy file writes it |
| `impact_sections.md` | report.md's "Advantages: impact cards" and "Disadvantages: impact cards" sections, written by hand |
| `impact_cards.csv` | The whole impact_cards.csv, written by hand |

Everything else report.md holds is `../golden/report.md`'s, and the test checks that too.

## What the list changes, through 2026-09-15

`v1-e32-t14` reads these scenario words from the Costs advantage's counted cards (README of
`../synthetic_caselist/`, "Scenarios and link chains"):

| Card | Sub-heading | t14's words | Team |
|---|---|---|---|
| `a1` copies `a` and `d`, cluster 2 | `scenario 1 economic collapse` (numbered) | `economic collapse` | `XX` |
| `a5` copy, cluster 2 | `economic collapse` (named) | `economic collapse` | `QQ` |
| `a4`, cluster 3 | `drug prices impact` (beside an impact label) | `drug prices` | `KK` |
| `a3`, cluster 37 | `debt crisis impact` (beside an impact label) | `debt crisis` | `VV` |

Without the list, `economic collapse` shows (two teams) and the other two do not (one team each).
With it:

* **Merged and renamed.** `drug prices` and `debt crisis` are one scenario, `Rising costs`, read by
  `KK` and `VV`: two teams, so it shows. Rank 2 (cluster 3, `a4`) and rank 3 (cluster 37, `a3`) each
  have one labelled copy filed under one of its forms, so both rows show `Rising costs`. The rows
  with a scenario go from 1 of 3 to 2 of 3.
* **Dropped.** `economic collapse` is no scenario. Rank 1 (cluster 2, labelled only by `a1`'s copy
  `d`) shows none. `a5`'s `economic collapse` was a named heading, so it is no longer a scenario
  heading; `a5`'s other card (cluster 38) is tagged `U: ...`, which labels no role, so `a5` becomes
  a document with no scenario heading and no role label: 2 of 6 advantage documents (`a5`, `a6`), not
  1 of 6. `a1`'s heading is numbered: the team wrote `Scenario 1`, so it stays a scenario heading,
  with no name, and `a1` carries t10's impact label anyway.
* **Nothing withheld.** `rising` and `costs` are no word of a caselist school (`Ashgrove`,
  `Birchmoor`, `Cedarvale`, `Driftwood`, `Fictional`), team code or tournament (`Invitational`,
  `Imaginary`, `Classic`, `Later`, `Tournament`): 0 withheld, as before.
* **The internal links, the card above, the link chain** and every role count are as before: the list
  names scenarios and labels no role.

**The Spending DA has no list,** so t14's rule stands: rank 3 shows `recession` (`b5`'s
`recession impact` and `b2`'s `recession`, two teams), and `cedarvale crash` (two teams) is withheld
and counted. The DA section is `../golden/report.md`'s, unchanged.

In impact_cards.csv, the `scenario` column of `costs-advantage` rank 1 is empty, and ranks 2 and 3
hold `Rising costs`. Every other cell is `../golden/impact_cards.csv`'s.

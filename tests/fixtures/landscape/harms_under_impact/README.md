# The synthetic caselist with harms headings (`v1-e32-t29`)

The coach, 2026-10-27: Policy debate no longer says "Harms"; debaters call that part of an advantage its
impact. Since `v1-e32-t29` (the PM's ruling of 2026-10-27), a sub-heading saying `harms` or `harm` under an
**advantage** labels the cards under it as the advantage's **impact**, exactly where the Harms role read
it before: below the heading that placed the card, not an answer, naming no other role. The link-chain
table has no Harms row, and every card the Harms role carried is counted under Impact: in the impact
table, impact_cards.csv, the chain's Impact row and the count of documents with no labelled impact. A
DA's `harms` heading labels nothing, as before.

This directory's [`edits.yaml`](edits.yaml) changes five cards' headings and nothing else:

| File | What it holds |
|---|---|
| `edits.yaml` | The five heading edits, by file and paragraph |
| `impact_sections.md` | report.md's "Advantages: impact cards" and "Disadvantages: impact cards" sections, written by hand |
| `impact_cards.csv` | The whole impact_cards.csv, written by hand from `../golden/impact_cards.csv` |

Everything else report.md holds is `../golden/report.md`'s, and the test checks that too.

## The edits, through 2026-09-15, by hand

Teams: `a3` is `VV`, `a4` `KK`, `a5` `QQ`, `a6` `JJ`, `b5` `ZZ`.

| Card | Cluster | New headings | What it shows |
|---|---|---|---|
| `a4` paragraph 0 | 6 | `innovation advantage` > `harms` | **An advantage with only harms headings.** It had no impact card. |
| `a6` paragraph 3 | 6 | `innovation advantage` > `harm` | The same advantage, a second team. |
| `a3` paragraph 3 | 2 | `costs advantage` > `harm` | **An advantage with both.** A copy of the Costs advantage's impact rank 1, read by a second team. |
| `a5` paragraph 9 | 38 | `costs advantage` > `harms` | A harms card that ranks fourth: counted, not shown. |
| `b5` paragraph 3 | 14 | `spending da` > `harms` | **A DA, untouched.** A copy of the Spending DA's link cluster. |

## What the report says

**Innovation advantage.** Its impact cards are cluster 6's harms copies, `a4`'s (`KK`) and `a6`'s (`JJ`):
two teams. The row shows the commonest tag and cite, then the lowest text: `Independently, research
funding prevents extinction` (`a6`) sorts before `Single payer frees capital for research` (`a4`), both
`Moreau 25`. Neither copy has a scenario: a bare `harms` or `harm` heading names none, as a bare `impact`
heading names none. Neither has a card above it under the position heading (`a4`'s is its file's first
card, `a6`'s card above is under no heading), so no internal link, link or card above: the rank is named
by its tag. Its chain: internal link cluster 6 (`a2`'s `i l`, as before), Impact cluster 6 with two teams.

**Costs advantage.** Cluster 2's labelled copies are `a1`'s copy `d` (`XX`, its tag) and now `a3`'s (`VV`,
`harm`): two teams, so rank 1 stays cluster 2, with 2 teams. The shown copy is still `a1`'s: `2.
Extinction from economic collapse` sorts first. Its scenario is still `economic collapse` (`a1` and `a5`);
`a3`'s `harm` names nothing. Clusters 3, 37 and 38 have one team each and rank by cluster id: 3 and 37 are
ranks 2 and 3, as before, and 38 (`a5`'s harms card) is rank 4, not shown. The chain's Impact row is
cluster 2 with 2 teams.

**Advantage documents.** A labelled impact is now in `a1`, `a3`, `a4`, `a5` and `a6`: 1 of 6 has none
(`a2`), down from 3. `a6`'s only advantage card is now labelled, so no advantage document is without a
scenario heading or a role label: 0 of 6, down from 1.

**Advantage lines.** Impact rows 4 (Costs 3, Innovation 1), 1 with a scenario. Ranks named by a scenario
1, by the tag 3. Positions with no labelled card: uniqueness 2 of 2, link 2 of 2, internal link 1 of 2,
impact 0 of 2, inherency 2 of 2, solvency 1 of 2. No harms entry: the role is gone.

**Spending DA, untouched.** `b5`'s `harms` heading labels no role for a DA, so its copy of cluster 14 is
no impact card: cluster 14's impact rank keeps one team (`b2`'s `impact` copy). `harms` is a named
scenario heading for a DA, as any other word is, used by one team, so no name shows. The DA section is
`../golden/report.md`'s, unchanged.

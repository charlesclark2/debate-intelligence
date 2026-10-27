# The synthetic caselist with tags the tables withhold and tags they show (`v1-e32-t28`)

Since `v1-e32-t28` (the PM's ruling (b) of 2026-10-27), the report withholds a tag holding a word of a
caselist **school** (over three characters) or **team code** (at any length) everywhere it quotes one:
the lines under "What each impact runs through" (`v1-e32-t25`), the impact table's Tag column and
impact_cards.csv's `tag`, the link-chain table, and top_cards.csv. A **tournament's** words are no longer
withheld anywhere. In a table, a withheld tag leaves its cell empty, and the row stays, with its rank,
teams, cite and source. report.md's header counts the tags each table left empty.

This directory's [`edits.yaml`](edits.yaml) is `../readable_impact_chains/edits.yaml` (t25's two tag
edits and two scenario lists) and four tags more, each on a cluster with a single copy, so the edited tag
is the tag its rows show:

| File | What it holds |
|---|---|
| `edits.yaml` | The six tag edits, by file and paragraph, and t25's two scenario lists |
| `impact_sections.md` | report.md's "Advantages: impact cards" and "Disadvantages: impact cards" sections, written by hand |
| `impact_cards.csv` | The whole impact_cards.csv, written by hand from `../readable_impact_chains/impact_cards.csv` |
| `top_cards.csv` | The whole top_cards.csv, written by hand from `../golden/top_cards.csv` |

Everything else report.md holds is `../golden/report.md`'s but for the header's count of tags left
empty, and the test checks that too.

## The words

Schools `Ashgrove Fictional`, `Birchmoor`, `Cedarvale Fictional`, `Driftwood Fictional`: the withheld
school words are `ashgrove`, `birchmoor`, `cedarvale`, `driftwood` and `fictional`. Team codes `XX`,
`YY`, `QQ`, `ZZ`, `VV`, `WW`, `JJ`, `KK`: all eight are withheld. Tournaments `Fictional Invitational`,
`Imaginary Classic`, `Later Tournament`: `invitational`, `imaginary`, `classic`, `later` and
`tournament` are no longer withheld. `fictional` is a school's word too, so it still is. No tag of the
unchanged caselist holds any of these words.

## The edits, through 2026-09-15, by hand

| Card | New tag | Holds | Where it shows |
|---|---|---|---|
| `a1` paragraph 6 (t25's) | `2. Extinction from a Cedarvale collapse` | `cedarvale`, a school word: **withheld** | Costs advantage impact rank 1; the Costs link chain's Impact row |
| `a3` paragraph 15 (t25's) | none | nothing | Costs impact rank 3; top_cards.csv costs-advantage rank 4 |
| `a4` paragraph 3 | `Bulk purchasing lowers drug prices later` | `later`, a tournament word only: **shown** | Costs impact rank 2; top_cards.csv costs-advantage rank 2 |
| `b5` paragraph 6 | `Spending is at a classic record high now` | `classic`, a tournament word only: **shown** | the Spending DA link chain's Uniqueness row; top_cards.csv spending-da rank 4 |
| `b6` paragraph 0 | `Insurance means private carriers too, per Birchmoor` | `birchmoor`, a school word: **withheld** | top_cards.csv nhi-t rank 2 |
| `a5` paragraph 3 | `Conditionality is a voting issue for VV` | `vv`, a team code: **withheld** | top_cards.csv condo-bad rank 1 |

None of the four new tags changes a card's place, role or impact label: each keeps its first words, `a4`
paragraph 3 is an impact card by its heading `drug prices impact`, `b5` paragraph 6 is the Spending DA's
uniqueness by its heading `u`, and `a5` paragraph 3 and `b6` paragraph 0 are placed by their
classifications under no heading.

### Costs advantage

* **Rank 1 (cluster 2, `a1` paragraph 6).** Its tag holds `cedarvale`. The impact table keeps the row,
  `| 1 | 1 |  | Okafor 25 |  |`, its tag cell empty. The line under it is t25's: the tag is withheld
  and counted, and the card above names it, `Single payer cuts administrative costs (card above)`.
  It is the link chain's Impact row too: `| Impact | 1 |  | Okafor 25 |`. In impact_cards.csv its `tag`
  is empty.
* **Rank 2 (cluster 3, `a4` paragraph 3).** Its tag holds `later`, a tournament's word, and nothing
  withheld. It shows in the table, in impact_cards.csv and in its line, `Bulk purchasing lowers drug
  prices later (tag)`. Under t25's words its line would have been withheld and the row left out, since
  `a4`'s paragraph 0 above it is in another block (`innovation advantage`).
* **Rank 3 (cluster 37, `a3` paragraph 15).** No tag, as t25 has it: an empty cell, left out of the
  lines, counted.

Per kind, as t25's: named by a tag 1, the card above 1; left out 1; tags withheld 1; scenario names
withheld 0.

### Spending DA

Its impact rows and lines are t25's. Its link chain's Uniqueness row, cluster 40 (`b5` paragraph 6),
quotes `Spending is at a classic record high now`: `classic` is a tournament's word only. That card is
above rank 3 in `b5`, but rank 3's labelled internal link (`b5` paragraph 9) is nearer and names it, so
no line reaches it.

### top_cards.csv

Every row is `../golden/top_cards.csv`'s, with the same 23 rows in the same order, but:
* `costs-advantage` rank 2: `Bulk purchasing lowers drug prices later`;
* `costs-advantage` rank 4 (cluster 37): no tag, as t25 has it;
* `condo-bad` rank 1: the tag is **empty**, withheld for `vv`, and the row keeps its rank, its 1 team,
  `Feldman 22` and its source;
* `spending-da` rank 4: `Spending is at a classic record high now`;
* `nhi-t` rank 2: the tag is **empty**, withheld for `birchmoor`, and the row keeps its rank, its 1
  team, `Lund 21` and its source.

The `costs-advantage` rank 1 row shows `a1` paragraph 3's tag, the one most copies of cluster 2 carry,
which holds no caselist word.

### The header's count

Tags left empty: 1 in the impact cards (Costs rank 1), 1 in the link chains (the Costs Impact row) and
2 in top_cards.csv (`condo-bad` rank 1 and `nhi-t` rank 2).

# The synthetic caselist with a link naming an impact rank (`v1-e32-t27`)

`v1-e32-t27` adds a source to `v1-e32-t25`'s order. An impact rank under "What each impact runs
through" is named by the first of these it has:
1. its scenario;
2. its labelled internal link;
3. **its labelled link**: the nearest card above the impact copy under the same position heading that
   is counted for the position and that `v1-e32-t14`'s reader labels a link, read as the internal link
   is read;
4. the impact card's own tag;
5. the card above it.

The mark is `(link)`. A link holding a word of a caselist school or team code is withheld
and counted, and the next source names the rank. A label that names an answer (`no link`, `link turn`,
`non-unique`) is no link (the PM's ruling of 2026-10-26).

## The unchanged caselist

`../golden/report.md` reaches `(link)` once, on the **Spending DA's rank 1** (cluster 15, `b1` paragraph
3, `YY` and `JJ`):
* Its scenario `cedarvale crash` is withheld, so no scenario shows.
* No card above it under `spending da` is labelled an internal link.
* `b1` paragraph 0 (cluster 14), under the sub-heading `link` in the same `spending da` section, is
  counted and labelled a link.
* So rank 1 reads `Spending triggers a debt spiral (link)`. Before this task, its own tag named it.

No other rank has a link above it:
* Rank 3 (`b5` paragraph 12) has `b5`'s paragraphs 9 (`internal link`), 6 (`u`) and 3 (`spending da`
  alone, its tag no label) above it, and the States CP's paragraph 0, another section, ends the walk.
* Rank 2's labelled copy is `b2` paragraph 0, with nothing above it.
* Hospital closures' rank 1 (`b4` paragraph 6) has `b4`'s paragraph 3, under no heading, above it.
* No advantage card is labelled a link: `a2` paragraph 0 is under `no link`, an answer.

Per kind: advantage, by a scenario 1, an internal link 0, a link 0, a tag 2, the card above 0. DA: 1,
0, **1**, 2, 0. impact_cards.csv has no link column, so it is unchanged.

## This directory's edits, through 2026-09-15, by hand

[`edits.yaml`](edits.yaml) changes three tags and drops `recession` from the Spending DA. Every other
input is the unchanged caselist's.

| File | What it holds |
|---|---|
| `edits.yaml` | The three tag edits, by file and paragraph, and the Spending DA's `not_scenarios` |
| `impact_sections.md` | report.md's "Advantages: impact cards" and "Disadvantages: impact cards" sections, written by hand |
| `impact_cards.csv` | The whole impact_cards.csv, written by hand from `../golden/impact_cards.csv` |

The caselist's withholding words are in `../readable_impact_chains/README.md`. `birchmoor` is a school
word.

### Spending DA (`not_scenarios: [recession]`)

The list holds drops only, so the position shows no scenario name (`v1-e32-t22`): `cedarvale crash` is
words no list holds, not a withheld name. Scenario names withheld: 0. Rows with a scenario: 0.

* **Rank 1 (cluster 15, `b1`).**
  * No scenario and no internal link.
  * Its link, `b1` paragraph 0, is now `Spending triggers a Birchmoor debt spiral`. It is **withheld
    and counted**.
  * Its own tag names it: `Debt ceiling fights are near (tag)`.
* **Rank 2 (cluster 14, `b2`'s copy).** Unchanged: `Spending triggers a debt spiral (tag)`.
* **Rank 3 (cluster 42, `b5` paragraph 12).**
  * `recession` is dropped, so no scenario.
  * Its internal link, `b5` paragraph 9, is now `Deficits spike Birchmoor rates`. It is **withheld and
    counted**, and kept off the row and the CSV, as `v1-e32-t25` keeps a withheld internal link.
  * The walk for a link goes on past paragraph 9 (an internal link, no link) and paragraph 6 (`u`). It
    reaches paragraph 3, whose tag now opens `Link:`, so `v1-e32-t14`'s reader labels it a link.
  * It names the rank: `Link: deficits follow new spending (link)`.
* **Hospital closures DA, rank 1.** Unchanged: `Rural hospitals close under single payer (tag)`.

Per kind: impact rows 4, with a scenario 0. By a scenario 0, an internal link 0, a link 1, a tag 3, the
card above 0; left out 0. Scenario names withheld 0. Tags withheld **2** (rank 1's link and rank 3's
internal link). Documents with no scenario heading and no role label: still 2 of 6 (`b3`, `b6`), as
`../readable_impact_chains/README.md` works out for the same drop.

**The Spending DA's link chain.** Since `v1-e32-t28` the table withholds a tag as the lines under "What
each impact runs through" do: its cell is left empty, and the row keeps its teams and cite.
* **Link.** Cluster 14's link-labelled copies are now `b1` paragraph 0 (`YY`, `JJ`) and `b5` paragraph
  3 (`ZZ`): 3 teams. Their tags differ, one copy each, so the first in text order shows: `Link:
  deficits follow new spending`, `b5`'s cite `Ito 2026`.
* **Internal link.** Cluster 41, `Lee 26`, 1 team. Its tag holds `birchmoor`, so the cell is empty.
* **Uniqueness and impact.** Unchanged.

### The advantages

Unchanged but for the per-kind line, which counts 0 by a link.

### impact_cards.csv

`spending-da` rank 3's `scenario` and `internal_link_tag` cells are empty: `recession` is dropped, and
the internal link is withheld. Every other cell is `../golden/impact_cards.csv`'s.

# The synthetic caselist with every source of an impact rank's name (`v1-e32-t25`)

`v1-e32-t25` names each impact rank under "What each impact runs through" by the first of these it
has: the scenario (`v1-e32-t14`, under the coach's list of `v1-e32-t22`), a labelled internal link, the
impact card's own tag, and the card above it in its block. A tag, internal link or card above holding a
word of a caselist school or team code is withheld, counted, and the next source names the rank
(`v1-e32-t28`: a tournament's words are not withheld). A rank with none of these is left out and counted.

On the synthetic caselist read unchanged (`../golden/report.md`), every impact card has a tag, so every
rank is named by its scenario or its tag. This directory's [`edits.yaml`](edits.yaml) changes two
cards' tags and gives two positions a scenario list, so that every source, a withheld tag and a left-out
rank are reached:

| File | What it holds |
|---|---|
| `edits.yaml` | The two tag edits, by file and paragraph, and the two scenario lists, by position id |
| `impact_sections.md` | report.md's "Advantages: impact cards" and "Disadvantages: impact cards" sections, written by hand |
| `impact_cards.csv` | The whole impact_cards.csv, written by hand from `../golden/impact_cards.csv` |

Everything else report.md holds is `../golden/report.md`'s, and the test checks that too.

The caselist's withholding words are the school words over three characters (`ashgrove`, `birchmoor`,
`cedarvale`, `driftwood`, `fictional`) and the team codes (`jj`, `kk`, `qq`, `vv`, `ww`, `xx`, `yy`,
`zz`). Since `v1-e32-t28` the tournament words (`classic`, `imaginary`, `invitational`, `later`,
`tournament`) are not. No tag of the unchanged caselist holds a school word, a team code or a tournament
word.

## Through 2026-09-15, by hand

### Costs advantage (`not_scenarios: [economic collapse]`)

The list drops `economic collapse`, so the position shows no scenario
(`../scenario_vocabulary/README.md` works out the same drop), and `a5`, whose only scenario heading was
the named heading `economic collapse`, becomes a document with no scenario heading and no role label:
2 of 6 (`a5`, `a6`).

* **Rank 1 (cluster 2, `a1`'s copy `d`, paragraph 6).** Its tag becomes `2. Extinction from a Cedarvale
  collapse`. It still opens `Extinction` past its enumerator, so it is still an impact card, rank 1 as
  before, and the impact of the link chain. No scenario (dropped); no labelled internal link (`a1`'s
  copy `a` above it labels no role). Its tag holds `cedarvale`, so it is **withheld and counted**, and
  the card above it in its block, copy `a` (`Single payer cuts administrative costs`, not an impact
  card), names it: `(card above)`.
* **Rank 2 (cluster 3, `a4`).** No scenario, no internal link, its tag names it: `Bulk purchasing lowers
  drug prices (tag)`.
* **Rank 3 (cluster 37, `a3`, paragraph 15).** Its tag becomes none. It is still an impact card, by its
  heading `debt crisis impact`. No scenario (the list holds no `debt crisis`); no internal link (`a3`'s
  cluster 36 above it answers the advantage); no tag; the card above it is in another block (`internal
  link`). Nothing names it: it is **left out**, and the position says 1 rank was. Its table row and its
  CSV row have an empty tag.

Per kind: rows with a scenario 0; named by a scenario 0, an internal link 0, a tag 1, the card above 1;
left out 1; tags withheld 1; scenario names withheld 0. The link chain's impact row is rank 1, with its
edited tag. Since `v1-e32-t28` the table's and the chain's Tag column withhold it too: rank 1's
table row and the chain's Impact row keep their teams and cite, with the tag cell empty.

### Spending DA (`Market crash` for `cedarvale crash`; `not_scenarios: [recession]`)

* **Rank 1 (cluster 15, `b1`, `YY` and `JJ`).** `cedarvale crash`, two teams, is listed under `Market
  crash`, which holds no caselist word, so it shows (as `test_scenario_vocabulary.py`'s
  `test_a_list_shows_its_names_and_no_words_it_does_not_hold` has it): `Market crash (scenario)`, and
  no name is withheld.
* **Rank 2 (cluster 14, `b2`'s copy `b`).** No scenario, no internal link: `Spending triggers a debt
  spiral (tag)`.
* **Rank 3 (cluster 42, `b5`).** `recession` is dropped, so no scenario. Its labelled internal link,
  `b5`'s cluster 41 above it under `internal link`, names it ahead of its own tag: `Deficits spike
  interest rates (internal link)`.
* **Hospital closures DA, rank 1** is unchanged: `Rural hospitals close under single payer (tag)`.

`b2`'s `recession` heading no longer names a scenario, but `b2` holds `b2`'s copy of cluster 14 under
`impact`, a role label, so the DA documents with no scenario heading and no role label stay 2 of 6
(`b3`, `b6`).

Per kind: rows with a scenario 1; named by a scenario 1, an internal link 1, a tag 2, the card above 0;
left out 0; tags withheld 0; scenario names withheld 0.

In impact_cards.csv: `costs-advantage` rank 1's tag is withheld (`v1-e32-t28`) and its scenario is empty, rank 3's
tag is empty; `spending-da` rank 1's scenario is `Market crash` and rank 3's is empty. Every other cell
is `../golden/impact_cards.csv`'s.

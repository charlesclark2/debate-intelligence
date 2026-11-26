<!-- docs-index: What a card's block could give the cards the landscape matcher leaves unplaced, measured on hspolicy26 and scored on the coach's labels (counts only) -->
# What a card's block gives the cards the matcher leaves unplaced (`v1-e32-t65`)

The product owner's point of 2026-11-14 was that a card's argument comes from the block it is read in. Before
any rule was built, `scripts/count_block_inheritance.py` measured it: the operator ran it three times on
2026-11-20 and once on 2026-11-25, in their terminal, over this Mac's store. Counts, position kinds and scores
only. No tag, heading, cite, school, team, row or item id is written here or was printed.

**The finding:** on the coach's labels, inheritance from the block is never right. It scored 0 of up to 19
inherited cards on `v1-e32-t21`'s first sample, for every rule of a 120-rule grid, and 0 of 10 on
`v1-e32-t50`'s holdout, under the one rule chosen on the first sample. The PM then asked for one more try on
the first sample: carrying a placed card's position forward in file order. All 12 variants carried 0 right
cards, out of 3 to 14. **The PM ruled no inheritance (2026-11-20): none is built.**

**The parser gives no block boundaries.** The parsed store keeps each card's heading path, not the heading
paragraphs, so where a block starts and ends is never recorded. Every block below is approximated from those
paths, or from file order.

## What was read

| | hspolicy26 | hsld26 |
|---|---|---|
| Snapshot | 2026-11-03 | 2026-11-03 |
| Parsed version directory | `2026.10.27-docx-7` | `2026.10.20-docx-6` |
| Taxonomy | `policy-2026-27-nhi` 1.5.1 | `ld-2026-nov-dec-de-extinction` 1.0.0 |
| Sources on the topic | 3,825 | 2 |
| Cards | 126,681 | 10 |
| Counted (placed at or above the review threshold, 0.6) | 64,661 | 0 |
| Placed by a tag keyword alone (0.5, under the threshold) | 1,329 | 0 |
| Decided: the coach ruled that every heading over it names no position | 4,888 | 0 |
| Unplaced | 55,803 | 10 |
| **Left for review** (unplaced, or by a keyword alone) | **57,132** | **10** |

On 2026-11-03 hsld26 holds only the Florida Blue Key disclosures on the de-extinction topic: 2 sources. All
10 of their cards are unplaced, and every block holds nothing placed, so LD has no counts to give at that
snapshot.

The matcher ran with the coach's overrides and no cache or model, and each result took its file's own side
(`v1-e32-t49`), as a landscape run reads it.

## What a block can be

The parsed store keeps cards only. Each card has its tag, the raw pocket, hat and block headings over it, and
its paragraphs. No heading paragraph is kept, so a block is built from those paths:

* **run:** cards next to each other in file order whose paths are equal. This is the closest the store comes to
  "the cards between two headings": two headings written alike in a row (`OFF`, `OFF`) make one run.
* **section:** the reader's section item of the card's innermost heading, with the sections under it. A card
  under no heading has the document.
* **parent:** the section one heading further out.
* **nearest:** working outwards from the section, the first one with a placed card decides. If its placed
  cards disagree, nothing is inherited and no further section is read.
* **document:** the whole document.

**Cards of one run share every heading, so the matcher places them alike by headings.** Only a tag keyword can
place one card of a run apart from the others. The count bears this out: no card left for review has a run-mate
placed by headings.

## Where the cards left for review sit (hspolicy26)

The placed cards of each card's block are counted two ways: those counted by a report, and those plus the cards
placed by a tag keyword alone. A card is never its own block-mate.

| Block | Placed cards | Agree on one position | Disagree | of which two thirds agree | Nothing placed |
|---|---|---|---|---|---|
| run | counted | 0 | 0 | 0 | 57,132 |
| run | counted + keyword | 5,765 | 364 | 143 | 51,003 |
| section | counted | 117 | 20 | 3 | 56,995 |
| section | counted + keyword | 5,973 | 407 | 155 | 50,752 |
| parent | counted | 8,022 | 8,451 | 2,045 | 40,659 |
| parent | counted + keyword | 12,576 | 10,653 | 3,457 | 33,903 |
| nearest | counted | 15,673 | 25,180 | 6,500 | 16,279 |
| nearest | counted + keyword | 21,704 | 24,181 | 6,899 | 11,247 |
| document | counted | 8,934 | 31,919 | 5,744 | 16,279 |
| document | counted + keyword | 11,046 | 34,839 | 7,312 | 11,247 |

Of the 15,673 cards whose nearest block agrees (counted), the agreeing blocks hold 1 placed card for 2,712, 2
for 1,879, 3 or 4 for 4,167, and 5 or more for 6,915.

## Scored on the coach's labels

A card counts as the evaluation counts it (`v1-e32-t43`): a counted placement by headings is scored on that,
and otherwise on what it inherits. Its stance is scored with `scored_stance`, so the role and the file's sides
both count, and a card labelled `none` that is placed counts against.

### The grid, on the first sample only

The grid crosses:
* five blocks;
* the two kinds of placed card;
* unanimous agreement or two thirds;
* a minimum of 1, 2 or 3 placed cards;
* any own headings, or `naming-nothing` (inherit only when every heading over the card below the deciding
  section normalizes to nothing or is ruled to name no position);
* two roles under an answer heading: answering, or the block's role.

That is 120 rules. The first sample was read at the 2026-11-03 snapshot (all 47 labelled cards found, 4 of them
counted by headings and all 4 right).

**No rule inherits a right card.** The widest rule (nearest block, counted + keyword, two thirds, minimum 1)
inherits 19 of the 47 labelled cards: 12 get another kind of position and 7 another position of the same kind.
No inherited card has the label's position with the other stance, or a position related to it (an aff and its
advantage). The role under an answer heading changes no outcome.

| Rule (role: answering under an answer heading) | Inherited in the caselist | Placed share after (before 0.510) | First sample: inherited, right |
|---|---|---|---|
| nearest, counted, unanimous, minimum 1, any | 15,673 | 0.634 | 12, 0 |
| nearest, counted + keyword, two thirds, minimum 1, any | 28,603 | 0.736 | 19, 0 |
| parent, counted, unanimous, minimum 1, any | 8,022 | 0.574 | 10, 0 |
| document, counted, unanimous, minimum 1, any | 8,934 | 0.581 | 7, 0 |
| **nearest, counted, unanimous, minimum 1, naming-nothing** (chosen) | **6,491** | **0.562** | **2, 0** |

**The rule chosen.** With every rule at 0 right, nothing could be tuned. The rule chosen for the holdout is the
spec's example (inherit only when the block's placed cards agree), from the nearest section holding a placed
card, kept to cards whose own headings below that section name nothing. Of the rules the grid has, it is the one
most likely to be right before any score is read. On the first sample it inherits 2 cards, both a position of
another kind.

### Once, on the holdout

The held-out sample: 111 labelled cards, all found and none placed by headings. Under the chosen rule (answering
under an answer heading), scored once:

| | Counted | Right | Accuracy (95%, Wilson) | Coverage of the labelled |
|---|---|---|---|---|
| Before (headings alone) | 0 | 0 | none | 0 |
| Inherited | 10 | 0 | 0.0 (0.0 to 0.278) | 0.090 |

### Carry-forward in file order, on the first sample only

The PM's ruling of 2026-11-20 ruled out the set-agreement rules above and asked for one last measurement on
the first sample, with the holdout not read (the script refuses it in this mode). A card left for review
takes the position of the nearest earlier card in file order placed by its headings or by a tag keyword.
Under an answer heading it carries as answering. The PM's bar: inheritance stays open only if a variant gets
more than a third of its carried cards right.

The 12 variants cross three settings:
* **distance:** the placed card is the one right before (`adjacent`), or one unplaced card may lie between
  (`one-gap`), or any number may, up to a stop (`until-stop`);
* **shells:** a card that opens a shell stops the carry and is not carried to (`list`), or nothing stops it
  (`none`). The list is a plan or counterplan text (`Text:`, `CP:`, `Plan:` or the label alone), an
  interpretation and uniqueness;
* **scope:** the carry stays in the deciding section (the deepest section over the card holding an earlier
  placed card), or runs across the whole document.

A decided card is not carried to. The script counts separately how many of them would be.

**No variant carries a right card.** The `shells` setting changed nothing on the first sample, and `scope`
changed one card, so the table pairs them:

| Distance | Scope | First sample: carried, right | Wrong: another kind, same kind | 95% upper bound | Coverage (before 0.085) |
|---|---|---|---|---|---|
| adjacent | either | 3, 0 | 2, 1 | 0.561 | 0.149 |
| one-gap | either | 4, 0 | 3, 1 | 0.490 | 0.170 |
| until-stop | section | 13, 0 | 7, 6 | 0.228 | 0.362 |
| until-stop | document | 14, 0 | 8, 6 | 0.215 | 0.383 |

As in the grid, no carried card has the label's position with the other stance or a related one, and no card
labelled `none` was carried.

What each variant would carry across hspolicy26 (placed share before 0.510):

| Variant | Carried | From a keyword-placed card | Under an answer heading | Decided cards that would carry | Placed share after |
|---|---|---|---|---|---|
| adjacent, list, section | 2,855 | 797 | 304 | 239 | 0.533 |
| adjacent, none, section | 2,860 | 798 | 306 | 240 | 0.533 |
| adjacent, list, document | 3,403 | 824 | 359 | 315 | 0.537 |
| adjacent, none, document | 3,417 | 825 | 362 | 317 | 0.537 |
| one-gap, list, section | 5,210 | 1,451 | 548 | 435 | 0.552 |
| one-gap, none, section | 5,222 | 1,454 | 552 | 438 | 0.552 |
| one-gap, list, document | 6,254 | 1,522 | 657 | 569 | 0.560 |
| one-gap, none, document | 6,284 | 1,525 | 663 | 575 | 0.560 |
| until-stop, list, section | 15,011 | 4,533 | 1,447 | 1,627 | 0.629 |
| until-stop, none, section | 15,092 | 4,569 | 1,453 | 1,651 | 0.630 |
| until-stop, list, document | 21,274 | 5,437 | 2,299 | 2,447 | 0.678 |
| until-stop, none, document | 21,632 | 5,508 | 2,327 | 2,507 | 0.681 |

By kind, the widest variant (until-stop, none, document) carries 8,828 cards to an advantage, 5,697 to an aff,
3,294 to a DA, 1,625 to a CP, 914 to a K, 859 to T and 415 to theory. The shell list removes at most 358 carries
in any pairing (until-stop, document).

## What the chosen rule would do to the caselist

* **Inherited:** 6,491 cards: 4,611 under an advantage, 535 a DA, 527 theory, 466 a K, 173 T, 113 a CP and 66 an
  aff. 160 of them had been placed by a keyword alone. The cards counted would go from 51.0% of the caselist to
  56.2%.
* **The review queue** (minimum two teams a row), before and after:

  | | Items | Cards | Heading rows written | Distinct headings | Under no heading |
  |---|---|---|---|---|---|
  | Before | 80,494 | 57,132 | 1,308 | 5,891 | 22,646 |
  | After, every section kept | 74,003 | 50,641 | 1,308 | 5,891 | 19,063 |
  | After, a section leaves once every card under it is placed | 70,462 | 50,641 | 1,273 | 5,692 | 17,116 |

  The queue lists headings, and a section is placed by its headings alone. So a card that inherits leaves the
  queue, but its heading's row stays unless its section's items leave too.
* **Decided cards:** 1,443 of the 4,888 cards the coach's rulings decide would inherit too, if they were let.

## Answer headings and link-shaped tags

Both are counted under the nearest block, counted placed cards, unanimous, minimum 1, any own headings: 15,673
cards inherit under that rule.

* **Answer headings:** 2,934 of the 57,132 cards left for review sit under one. 1,118 of them inherit, and for
  1,107 of those the answer heading lies below the deciding section, where the matcher's own rule
  (`Spending DA > AT: Link Turn` reads) would call it the reading team's own block. For 918 of the 1,107 the
  block's placed cards read the position, and for 189 they answer it; for 20 cards the answer heading lies in
  the deciding section. The block's cards read for 14,927 of the inheriting cards, answer for 704, and are mixed
  for 42.
* **Link-shaped:** a tag opening as a link, an internal link or uniqueness, or a heading over the card labelling
  one. Of the inheriting cards by inherited kind: 77 of 684 under a CP, 212 of 2,232 under a DA, 379 of 10,079
  under an advantage, 31 of 1,026 under a K, 13 of 86 under an aff, 22 of 1,040 under theory and 9 of 526 under
  T. None of the first sample's inherited cards was link-shaped.

## Why it fails: measured, not explained

One explanation fits the grid's wider rules. A card is left unplaced because no heading over it places it, so
inside a block that holds placed cards it usually sits under a heading of its own that places nothing: a block
the team named its own way, which is a different argument from its neighbours.

The `naming-nothing` rules test exactly that, and it is not the whole story. They keep only cards with no such
heading, and their inherited cards are still never right: 2 of 2 on the first sample and 10 of 10 on the holdout
are wrong. Carrying forward in file order, which needs no agreement at all, is wrong for all 14 cards it
carries at its widest. Where the labelled cards went wrong is counted (another kind, or another position of the same kind);
why is not. Reading the cards would say, and that is a sitting with the coach, not a count.

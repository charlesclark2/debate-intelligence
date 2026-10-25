# The synthetic three-snapshot caselist

The inputs `v1-e32-t03-landscape-report`, `v1-e32-t10-impact-cards-per-position`,
`v1-e32-t14-scenarios-and-link-chains` and `v1-e32-t04-trend-and-school-views` are tested against: one invented Policy caselist,
`synthpolicy26`, written by `scripts/make_landscape_fixture.py`. Every school, team code,
tournament, tag and cite here is synthetic. Team codes are doubled letters (`XX`, `YY`, `ZZ`,
`QQ`, `VV`, `WW`, `JJ`, `KK`) at four fictional schools, so a scan of a report for them means
something (ac4). `Birchmoor` is one word, as the real archive spells a school, and the other three
are display names with a space, so the school view links only Birchmoor's teams to their
openCaselist pages (`v1-e32-t18`).

What the report should say about these inputs is in `../golden/`, written by hand from the table
in the generator (working agreement 6), never by running the report. `expected_trends.csv` here is
the same: the trends of the third window, worked out by hand below.

## Files

| File | What it holds |
|---|---|
| `taxonomy.yaml` | 14 positions: 2 affs, 2 advantages, 4 DAs, 2 CPs, a K, a T and 2 theory positions read by the aff; the DAs, advantages and K carry the heading the cards name them by as an alias |
| `overrides.yaml` | One coach decision: the heading `extra` names no position |
| `disclosures.jsonl` | 24 E30 disclosure rows over three weekly snapshots, 2026-09-08, 2026-09-15 and 2026-09-22 |
| `cards.jsonl` | 65 cards of 20 sources, each with its exact fingerprint and E31 cluster, and the DA and advantage cards with the normalized headings over them and which of them answer |
| `classifications.jsonl` | The `v1-e32-t02` classification of each card |
| `expected_trends.csv` | The trend rows of a report through 2026-09-22, by hand (`v1-e32-t04` ac1) |
| `analytic_texts.json` | `v1-e32-t11`'s readings of CP texts, alternatives, roles of the ballot and overviews, written by hand (below) |

Source digests read at a glance: `a1a1…` is an affirmative file, `b1b1…` a negative one. Cluster
`n` is `nn` repeated; copy `a` of cluster 2 is `0202…020a`.

## What each part exercises

The report is built through 2026-09-15, with 2026-09-08 as the previous snapshot.

* **Rounds.** 16 in range by 8 teams: 7 affirmative, 8 negative and 1 on no readable side (`b7`,
  whose filename gave no side, tournament or round).
* **One round listed twice.** `a1`'s first-tournament round is in both weekly windows, carried
  from one to the next. It is one round, first seen on 2026-09-08.
* **One file, two rounds.** `b1` was disclosed by two teams, so its cards count in two rounds.
* **A team with two rounds on one file.** `a1` was read by one team at both tournaments.
* **Out of range.** `b9` and the rest of the third window are disclosed on 2026-09-22, after the
  report's date; their cards (`b9`'s `cap-k` and `spending-da` reads among them) must change nothing.
* **ANSWERS are not reads.** `a1`'s answer to `spending-da`, `b1`'s answer to `costs-advantage`
  and `b8`'s answer to `pics-bad`, which nobody reads, so `pics-bad` has no row. Those three are
  also in rounds on the other side; `b7`'s answer to `nhi-t` is in a round on no readable side, so
  only its role keeps it from counting.
* **A placement on the other side.** `a6`, an affirmative file, has a `spending-da` block with no
  `AT:` marker, which `v1-e32-t02` records as a read. It is the 2AC answering the DA, so the report
  counts it apart and not as a read.
* **Below the threshold.** `a2`'s `public-option-aff` and `b3`'s `courts-cp`, placed by tag keyword
  at 0.5; `courts-cp` has no row. With 8 unplaced cards they make the 10 Unclassified cards of the 56 in range.
* **The coach's decision.** `a5`'s third card is under a heading ruled to name no position: neither
  counted nor Unclassified.
* **Near-duplicates.** Cluster 2 has four exact fingerprints; one team (`a1`) reads two copies of
  it, and it counts once for that team.
* **New this week.** `condo-bad`, `hospital-closures-da` and `provider-strikes-da` are first seen
  on 2026-09-15.
* **Ties.** `hospital-closures-da` and `provider-strikes-da` have equal teams and rounds, so the
  position id orders them. `nhi-t`'s two clusters have one team each, so the cluster id orders them.
* **Unidentified affs.** 3 of the 7 affirmative rounds have no card placed under an aff.
* **A position read on no readable side.** `cap-k` is read in `b7`'s round, which counts in its
  rounds and teams but not in its neg split or its share of negative teams.

## Impact cards (`v1-e32-t10`)

The rule: an `impact` or `impacts` heading over a card (not `no impact`, `impact defense` or
`impact turn(s)`), a `turns case` heading, or a tag opening with an impact word after one leading
enumerator. Only DAs and advantages are listed.

* **Only the labelled copies count.** Cluster 2 (Costs advantage) is read by four teams, but only
  `a1`'s copy `d`, tagged `2. Extinction from economic collapse`, is labelled, so it has one team.
  The tag is labelled only once its enumerator `2.` is skipped.
* **Teams rank, not cluster ids.** Spending DA's cluster 15 (`turns case`, two teams) ranks above
  cluster 14, whose one labelled copy (`b2`) one team reads, although the others make it four.
* **Ties.** Costs advantage's clusters 2 and 3 have one labelled team each, so the cluster id
  orders them; cluster 3 is labelled by an `impact` heading in `a4`.
* **The exclusions.** `b3`'s `no impact`, `b4`'s `impact defense` and `b6`'s `impact turns` label
  nothing, so the Midterms and Provider strikes DAs have no impact card. `a2`'s `i l` heading and
  `a6`'s tag opening `Independently` label nothing either, so the Innovation advantage has none.
* **Never impact cards.** `a6`'s `spending-da` card under an `impact` heading is in a round on the
  other side. `b7`'s new answer to `election-da`, under `impact` and tagged `2. Extinction
  outweighs`, is in a round on no readable side, so only its ANSWERS role keeps it out. `b1`'s
  answer to the Costs advantage is both. `b9`'s is out of range. `b2`'s `cap-k` card under `impact`
  is a K's.
* **No labelled impact.** Advantage documents: 3 of 6 (`a1`, `a3` and `a4` carry one). DA documents: 2
  of 6 (`b1`, `b2`, `b4` and `b5` do). `a3`'s and `b5`'s are `v1-e32-t14`'s cards below.

## Scenarios and link chains (`v1-e32-t14`)

A card's sub-headings are the headings below the alias that placed it. A role label is a sub-heading's
or a tag opening's (`u` only as a heading's first word, never in a tag); the impact role is t10's
impact card. A scenario name is a numbered heading's words after `scenario N`, a named sub-heading, or
the words beside an impact or internal-link label, and shows only when two or more teams of the
position use it. Through 2026-09-15:

* **Costs advantage, rank 1 (cluster 2, `a1` copy `d`, `XX`).** Its scenario is `economic collapse`:
  `a1` files it under `Scenario 1 economic collapse` and `a5` (`QQ`) under `economic collapse`, two
  teams. No card above it is labelled an internal link, so the card directly above it in its block,
  `a1`'s copy `a`, is shown as the card above it in the file.
* **Costs advantage, rank 2 (cluster 3, `a4`, `KK`).** `drug prices impact` names `drug prices`, but
  only `KK` uses it, so no scenario shows. The card above it in `a4` is in another block.
* **Costs advantage, rank 3 (cluster 37, `a3`, `VV`).** The card above it under the position is
  `a3`'s cluster 36, under `internal link`, but it ANSWERS the advantage, so it fills no role and the
  row has no labelled internal link. `debt crisis impact` names `debt crisis`, one team.
* **Spending DA, rank 1 (cluster 15, `b1`, `YY` and `JJ`).** `cedarvale crash` is used by two teams,
  but it holds `cedarvale`, a word of a caselist school, so it is withheld and counted. `b1`'s card
  above it under the position is labelled a link, not an internal link.
* **Spending DA, rank 3 (cluster 42, `b5`, `ZZ`).** Its internal link is `b5`'s cluster 41, under
  `internal link` above it. Its scenario `recession` is the words beside `recession impact`, and
  `b2` (`QQ`) files cluster 39 under `recession`: two teams.
* **The link chains.** Spending DA: uniqueness `b5`'s cluster 40 (`u`), link cluster 14 (`b1`'s copy
  `a`, `link`, two teams), internal link cluster 41, impact its rank 1. Costs advantage: impact its
  rank 1 and solvency `a3`'s cluster 35; nothing else. Innovation advantage: internal link cluster 6
  (`a2`'s `i l`). Midterms DA: link `b4`'s cluster 44, by its tag `The link: ...`.
* **What fills no role.** `a1`'s `uq` card ANSWERS the Spending DA, in a round on the other side.
  `a2`'s copy `b` of cluster 2 is under `no link`. `a5`'s cluster 38 is tagged `U: ...`: `u` never
  labels in a tag. `b3`'s cluster 43 is under `AT: Uniqueness`, an answer sub-heading. `a6`'s cluster
  45, under `internal link` of the Midterms DA, is in a round on the other side. Not scenarios either:
  `b3`'s `no impact`, `b4`'s `impact defense`, `b6`'s `impact turns`.
* **Per kind.** Advantage documents with no scenario heading and no role label: 1 of 6 (`a6`). DA
  documents: 2 of 6 (`b3` and `b6`). Rows with a scenario: advantage 1 of 3, DA 1 of 4. With a labelled
  internal link: advantage 0, DA 1; the card above shown instead: advantage 1, DA 0. Names withheld:
  advantage 0, DA 1.
* **The rest of the report.** The 11 new cards are in files that already read their positions, so no
  round, team, trend or school-view row changes. Coverage is 45 of 56 cards; `top_cards.csv` gains the
  new clusters (Costs advantage 35, 37 and 38, Spending DA 39 to 41, Midterms DA 43 and 44); `a6`'s
  Midterms card is a second round placing a card under a position of the other side.

## Trends (`v1-e32-t04`)

A week's disclosures are the rounds first seen in that snapshot's window: a round is the team, side,
tournament and round its file was disclosed for, never the path. A position's weekly teams are the
teams of that week's rounds that read it on its own side, and its weekly share is those over the
week's teams disclosing on that side. RISING and FALLING need a change of at least 5 points and at
least 3 teams reading it in one of the two weeks; a change the team floor holds back is STEADY and
says so.

| Window | Aff teams disclosing | Neg teams disclosing |
|---|---|---|
| 2026-09-08 | 3 (`XX`, `ZZ`, `VV`) | 4 (`YY`, `QQ`, `WW`, `JJ`) |
| 2026-09-15 | 4 (`XX`, `KK`, `QQ`, `JJ`) | 4 (`YY`, `ZZ`, `WW`, `KK`) |
| 2026-09-22 | 3 (`XX`, `ZZ`, `VV`) | 3 (`YY`, `QQ`, `KK`) |

`VV`'s `b7` round, on no readable side, is in no side's count.

* **The third window** (`ac`, `ad`, `ae`, `bc`, `bd` and `b9`) has a rising position, the
  Innovation advantage (2 of 4 aff teams, then all 3: +50.0 points), and the Capitalism K (1 of 4,
  then 3 of 3: +75.0); a falling one, the Costs advantage (3 of 4, then none: -75.0); and a new one,
  the Courts CP, whose only earlier placement (`b3`'s, by tag keyword at 0.5) was below the
  threshold and so never counted.
* **The team floor.** The Spending DA goes from 1 of 4 to 1 of 3 (+8.3 points) and Single payer from
  2 of 4 to 1 of 3 (-16.7), but neither has 3 teams in either week, so both are STEADY, held back.
  So are the six positions one team read in the second window and none in the third (-25.0 each).
* **A file carried under a new path.** `a4` (`KK`'s Imaginary Classic Round 1 affirmative) is listed
  again in the third window, unchanged, under a path whose sequence number went from none to `2`. It
  is the same round, first seen on 2026-09-15, so `KK` is not one of the third window's affirmative
  teams, and its Innovation and Costs advantage cards do not count there. Keyed on the path, `KK`
  would make 4 aff teams, the Innovation advantage 4 of 4 and the Costs advantage 1 of 4.
* **Through the second snapshot** (the t03 golden bundle, `../golden/trends.csv`), the Costs
  advantage (3 of 3, then 3 of 4: -25.0) and the Spending DA (3 of 4, then 1 of 4: -50.0) fall;
  Condo bad and the Hospital closures and Provider strikes DAs are new; the Midterms DA, the
  Capitalism K and T hold at 1 of 4; Single payer, the Innovation advantage (+16.7 each), the Public
  option (-33.3) and the States CP (-25.0) are held back by the team floor.

## School view (`v1-e32-t04`)

`../golden/schools.csv` lists, per school and team code as disclosed and per side, the positions its
rounds read through 2026-09-15, with their rounds: school plus team code, never more (the PM's ruling
of 2026-10-24 dropped the last tournament). The same reads as
the report: no ANSWERS, nothing below the threshold, no placement in a round on the other side.
`VV`'s `b7` round reads the Capitalism K on no readable side, so it is left out and counted.

## Analytic texts (`v1-e32-t11`)

`analytic_texts.json` is written by hand, not by the generator: what `v1-e32-t11`'s reader would keep of
each file's CP texts, alternatives, roles of the ballot and overviews, with the words each reading was
made from and what reading the file again returns. The golden report's two text sections were written
by hand from it. Through 2026-09-15:

* **The States CP's texts rank by teams.** The first text is in `b1` (YY and JJ), `b2` (QQ, after its
  `Text:` label) and `b3` (WW, in capitals and without its full stop, so the commoner wording shows): 4
  teams. The second is in `b4` (YY), `b6` (WW) and `b8` (KK), whose copy could not be read again, so KK
  counts and `b4`'s copy shows: 3. The third is in `b5` (ZZ) and `b4` (YY): 2. `b6`'s other text is
  the 1 more text, read by 1 team.
* **A text naming a school is withheld.** `b5`'s text names `Ashgrove Fictional`, a school of the
  caselist: it is counted and not shown.
* **A CP no card counts still shows its text.** `b3`'s Courts CP text, though `courts-cp` has no row.
* **Placed elsewhere:** `b2`'s text under the Midterms DA, and `a6`'s copy of the first text, in a
  round on the other side. **Not placed:** `b4`'s under headings that place nothing, `b8`'s and `b6`'s
  labelled text with no actor (paragraph 50, whose list the guard refuses, below) under none.
  **The actor guard** left out 2 paragraphs of `b6` (and 5 of `b9`, out of range).
* **The alternatives.** The first is in `b2` (QQ), `b8` (KK) and `b7` (VV), whose round has no side
  and so is not the other side: 3 teams. `a1`'s copy answers the K. `b4`'s two are under no heading and
  `b6`'s under headings that place nothing.
* **One role of the ballot** is placed, `b2`'s; `b6`'s is not.
* **Overviews, counted only:** the Midterms DA's in `b1` (YY, JJ) and `b4` (YY) on the negative and
  `a6` (JJ) on the affirmative, so 2 teams, 1 aff and 2 neg; the Costs advantage's in `a3` (VV); the
  States CP's in `b5` (ZZ). `a1`'s answers the Spending DA; `b3`'s and `b8`'s are not placed.

## Planks (`v1-e32-t16`)

`analytic_texts.json` also holds what `v1-e32-t16`'s reader would keep of the States CP's planks: each
plank's CP text (`stem`) and the advantages it solves. The golden report's planks under the States CP
were worked out by hand from it, through 2026-09-15. The planks, by their words, with the files and teams
holding each where they count:

| Plank | Files (teams) | Teams | Solves |
|---|---|---|---|
| `Expand sample clinics to cut costs.` | `b1` (YY, JJ), `b6` (WW), `b8` (KK, its copy not read again) | 4 | Costs |
| `Cap sample drug prices to cut costs and spur innovation.` | `b2` (QQ), `b5` (ZZ, in lower case after `Second,`), `b6` (WW) | 3 | Costs, Innovation |
| `The fifty states should also cap sample premiums.` | `b3` (WW), `b4` (YY) | 2 | Costs |
| `The fifty states should cap sample hospital costs.` | `b2` (QQ) | 1 | Costs |
| `Fund a sample research prize.` | `b6` (WW), after the label `Innovation` | 1 | Innovation |
| `Publish a sample price list.` | `b1` (YY, JJ), `b6` (WW) | 3 | not named |
| `Hire sample navigators.` | `b4` (YY) | 1 | not named |
| `Ashgrove Fictional should host a sample pilot to cut costs and spur innovation.` | `b5` (ZZ) | 1 | Costs, Innovation; withheld |

* **`b6`'s second CP text ends in a colon** and lists four planks (paragraphs 20 to 24), one of them
  after a paragraph that is only an advantage's alias (21). The others are separate planks, labelled
  (`Plank 2:`, `2.`, `Second,`) or `should` analytics past the guard.
* **Grouped by what they solve,** the top 3 per advantage: Costs shows the first three by teams (4, 3
  and 2), then 1 more plank read by 1 team (QQ). Innovation shows 3 and 1. "not named" shows 3 and 1.
  `b5`'s plank naming a school names both advantages, and is withheld from both and counted once.
  Costs comes first, with 6 teams (YY, JJ, WW, KK, QQ, ZZ)
  against Innovation's 3 (QQ, ZZ, WW); "not named" is always last.
* **The totals count a plank once:** 8 distinct planks, the one naming both advantages once, read by 6
  teams, 1 of the planks withheld.
* **Where the 16 planks in range went:** 14 counted. `b8`'s plank under its text under no heading is
  not placed. `a6`'s copy of the first plank, in a round on the other side, is placed elsewhere, and so
  its card saying `solves` with other words is not counted. `b2`'s second plank has such a card: 1.
* **The guard and the labels:** `b6`'s labelled text with no actor (paragraph 50) has 2 list planks the
  guard refuses, and `b6` 1 alias-only label. `b9`'s plank, label and refusals are out of range.
